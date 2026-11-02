"""Pure produce-stage persistence and Run DTO replay guards."""
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

from app.models.tables import WorkflowStep
from app.pipeline.outputs import workflow_step_to_response
from app.tools.video.production.stages import (
    apply_production_stage,
    production_stage_record,
    render_stage_kind,
)

RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
START = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)
END = datetime(2026, 10, 30, 8, 1, tzinfo=UTC)


def stage(kind="validate", *, attempt=1, status="running", facts=None, started_at=START):
    return production_stage_record(
        kind=kind,
        run_id=RUN_ID,
        step_id=STEP_ID,
        attempt=attempt,
        status=status,
        started_at=started_at,
        finished_at=END if status != "running" else None,
        facts=facts,
    )


def response(spec, *, attempt=1):
    node = SimpleNamespace(
        id=STEP_ID,
        kind="produce_video",
        status="running",
        seq=1,
        attempt=attempt,
        error=None,
        cost=None,
        estimate=None,
        spec=spec,
        output_refs=[],
        inputs=[],
        started_at=START,
        finished_at=None,
    )
    return workflow_step_to_response(cast(WorkflowStep, node), ratio=100)


def test_stage_append_settle_and_run_dto_share_the_persistent_records():
    running = apply_production_stage({}, stage(), current_attempt=1)
    queued = apply_production_stage(
        running,
        stage(
            "render_queue",
            status="completed",
            facts={"item_count": 1, "reused_count": 1, "raw_url": True},
        ),
        current_attempt=1,
    )
    assert [row["seq"] for row in queued["production_stages"]] == [0, 1]

    settled = apply_production_stage(queued, stage(status="completed"), current_attempt=1)
    first, second = settled["production_stages"]
    assert first["status"] == "completed"
    assert datetime.fromisoformat(first["started_at"]) == START
    assert datetime.fromisoformat(first["finished_at"]) == END
    assert first["seq"] == 0
    assert "raw_url" not in second

    # Replayed start/terminal frames cannot reopen or move the first terminal fact.
    assert apply_production_stage(settled, stage(), current_attempt=1) is settled
    assert apply_production_stage(settled, stage(status="failed"), current_attempt=1) is settled

    dto = response(settled)
    assert [row.model_dump(mode="json") for row in dto.production_stages] == settled[
        "production_stages"
    ]


def test_old_attempt_cannot_settle_or_replace_the_current_attempt():
    old = apply_production_stage({}, stage(attempt=1), current_attempt=1)
    current = apply_production_stage(old, stage(attempt=2), current_attempt=2)
    stale_tail = stage(attempt=1, status="completed")
    assert apply_production_stage(current, stale_tail, current_attempt=2) is current

    settled = apply_production_stage(current, stage(attempt=2, status="completed"), current_attempt=2)
    dto = response(settled, attempt=2)
    assert dto.attempt == 2
    assert [(row.attempt, row.status) for row in dto.production_stages] == [
        (1, "running"),
        (2, "completed"),
    ]


def test_old_runs_and_malformed_stage_entries_read_tolerantly():
    assert response({}).production_stages == []
    valid = stage("output_resume", status="completed", facts={"reused": True})
    spec = {"production_stages": [None, {"event_id": "broken"}, valid]}
    dto = response(spec)
    assert [row.kind for row in dto.production_stages] == ["output_resume"]
    assert dto.production_stages[0].reused is True


def test_render_queue_completion_is_not_render_execution_or_delivery():
    spec = apply_production_stage(
        {}, stage("render_queue", status="completed"), current_attempt=1
    )
    dto = response(spec)
    assert [(row.kind, row.status) for row in dto.production_stages] == [
        ("render_queue", "completed")
    ]
    assert all(row.kind not in {"render", "delivery"} for row in dto.production_stages)


def test_render_and_delivery_are_distinct_ordered_stage_facts():
    running = apply_production_stage({}, stage("render"), current_attempt=1)
    rendered = apply_production_stage(
        running, stage("render", status="completed"), current_attempt=1
    )
    delivered = apply_production_stage(
        rendered, stage("delivery", status="completed"), current_attempt=1
    )
    dto = response(delivered)
    assert [(row.kind, row.status, row.seq) for row in dto.production_stages] == [
        ("render", "completed", 0),
        ("delivery", "completed", 1),
    ]


def test_failed_render_has_no_delivery_fact():
    running = apply_production_stage({}, stage("render"), current_attempt=1)
    failed = apply_production_stage(
        running, stage("render", status="failed"), current_attempt=1
    )
    dto = response(failed)
    assert [(row.kind, row.status) for row in dto.production_stages] == [
        ("render", "failed")
    ]


def test_upload_only_recovery_never_reads_as_a_new_render():
    assert render_stage_kind(upload_only=True) == "upload"
    assert render_stage_kind(upload_only=False) == "render"
    running = apply_production_stage(
        {}, stage(render_stage_kind(upload_only=True)), current_attempt=2
    )
    uploaded = apply_production_stage(
        running, stage("upload", attempt=2, status="completed"), current_attempt=2
    )
    assert [(row.kind, row.status) for row in response(uploaded, attempt=2).production_stages] == [
        ("upload", "completed")
    ]
