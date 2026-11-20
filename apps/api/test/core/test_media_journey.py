import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.tool_loop import ChatTool, ToolObservation
from app.chat.media_journey import (
    allowed_media_tools,
    continue_media_journey,
    initial_media_journey,
    media_actions,
)
from app.chat.plan_turn import PlanTurn
from app.models.schemas import ChatRequest, WorkflowStatus
from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration
from app.tools.video.media_analysis import IMAGE_REVIEWER_VERSION, image_reviewer_version
from app.tools.video.visual_assets import SceneAssetSpec


def draft_with_scene():
    spec = SceneAssetSpec(
        scene_id="intro",
        intent="Opening with source evidence",
        source={"kind": "minimax_image", "prompt": "A paper and symbol of verified evidence"},
    )
    return {
        "content": {"scenes": [{"scene_id": "intro"}]},
        "design": {"scene_assets": [spec.model_dump(mode="json")]},
    }, spec


def result_for(spec, status, **extra):
    return {
        "scene_id": spec.scene_id,
        "request_digest": spec.request_digest(),
        "content_review": {"status": status, "reviewer_version": image_reviewer_version(spec.source.kind)},
        **extra,
    }


def test_scene_asset_receipt_tracks_changes_and_reviewed_images():
    from app.chat.media_journey import scene_asset_changes

    draft, spec = draft_with_scene()
    initial = scene_asset_changes({}, draft, [])
    assert initial["changed_scene_ids"] == initial["prepare_scene_ids"] == ["intro"]
    ready = scene_asset_changes(draft, draft, [result_for(spec, "pass")])
    assert ready["reusable_scene_ids"] == ["intro"]
    assert ready["changed_scene_ids"] == ready["prepare_scene_ids"] == []
    reviewed = scene_asset_changes(draft, draft, [result_for(spec, "fail")])
    assert reviewed["repair_scene_ids"] == ["intro"]
    assert reviewed["reusable_scene_ids"] == []

    updated = spec.model_copy(update={"intent": "Show the source paper"})
    second = spec.model_copy(update={"scene_id": "end"})
    current = {
        "content": {"scenes": [{"scene_id": "intro"}, {"scene_id": "end"}]},
        "design": {"scene_assets": [updated.model_dump(mode="json"), second.model_dump(mode="json")]},
    }
    previous = {
        **current, "design": {"scene_assets": [spec.model_dump(mode="json"), second.model_dump(mode="json")]},
    }
    partial = scene_asset_changes(previous, current, [result_for(spec, "fail"), result_for(second, "pass")])
    assert partial["changed_scene_ids"] == partial["prepare_scene_ids"] == ["intro"]
    assert partial["reusable_scene_ids"] == ["end"]


def test_staged_media_preserves_original_intent_and_enforces_current_images():
    opening = SimpleNamespace(
        id=uuid4(), role="user", content="给 https://www.legitevi.com/en 做一只宣传片",
    )
    assert initial_media_journey(opening) == {"opening_id": str(opening.id)}
    opening.content = "分析 https://www.legitevi.com/en 的宣传片"
    assert initial_media_journey(opening) is None
    draft, spec = draft_with_scene()
    assert "prepare_narration" not in allowed_media_tools(media_actions(
        draft, []
    )["phase"])
    review = result_for(spec, "unavailable")
    assert media_actions(draft, [review])["review_retry_scene_ids"] == ["intro"]
    assert media_actions(
        draft, [review, {**review, "review_retry_of": {"digest": "r"}}]
    )["phase"] == "images_blocked"
    passed = result_for(spec, "pass")
    assert media_actions(draft, [passed])["phase"] == "audio"
    changed = spec.model_copy(update={"intent": "New scene intent"})
    draft["design"]["scene_assets"] = [changed.model_dump(mode="json")]
    assert media_actions(draft, [passed])["phase"] == "images"


def test_existing_image_repair_uses_current_evidence_review_and_keeps_attempt_bound():
    spec = SceneAssetSpec(
        scene_id="process", intent="Show the four steps", on_screen_copy="From paper to post",
        source={"kind": "existing_image", "snapshot_id": uuid4(), "snapshot_digest": "a" * 64,
                "visible_evidence": "The Process diagram with the four numbered steps"},
    )
    draft = {
        "content": {"scenes": [{"scene_id": spec.scene_id}]},
        "design": {"scene_assets": [spec.model_dump(mode="json")]},
    }
    old = result_for(spec, "pass")
    old["content_review"]["reviewer_version"] = IMAGE_REVIEWER_VERSION
    assert media_actions(draft, [old])["missing_scene_ids"] == ["process"]
    wrong_section = result_for(spec, "fail", execution={"run_id": "first"})
    wrong_section["content_review"]["summary"] = "The footer has no process diagram."
    state = media_actions(draft, [wrong_section])
    assert state["repair_scene_ids"] == ["process"]
    assert state["scene_failures"][0]["detail"] == "The footer has no process diagram."

    changed = spec.model_copy(update={"source": spec.source.model_copy(update={
        "snapshot_id": uuid4(), "snapshot_digest": "b" * 64,
    })})
    draft["design"]["scene_assets"] = [changed.model_dump(mode="json")]
    for status, phase in [("fail", "images_blocked"), ("pass", "audio")]:
        retry = result_for(changed, status, execution={"run_id": "second"})
        retry["content_review"]["summary"] = "The fourth step is cropped."
        state = media_actions(draft, [wrong_section, retry])
        assert state["phase"] == phase
        if status == "fail":
            assert state["scene_failures"][0]["detail"] == "The fourth step is cropped."


@pytest.mark.asyncio
async def test_rejected_verified_plan_can_retry_without_searching_or_saving(monkeypatch):
    project = SimpleNamespace(id=uuid4(), language="zh")
    run = SimpleNamespace(context={})
    run_id = uuid4()
    calls = []
    db = SimpleNamespace()

    async def get(cls, key):
        assert key == run_id
        return run

    db.get = get
    turn = PlanTurn(
        db, uuid4(), SimpleNamespace(id=uuid4()), project,
        ChatRequest(project_id=project.id, message="English · 16:9"),
    )
    turn.media_state = {"phase": "images"}
    turn.media_journey = {"opening_id": str(uuid4())}
    exact_params = {
        "draft_ref": {"draft_id": "draft", "draft_digest": "a" * 64},
        "scene_ids": ["intro"],
        "review_existing": False,
    }

    async def dispatch(name, params, prose):
        assert name == "prepare_visual_assets"
        return ToolObservation(json.dumps({
            "cache": "miss",
            "plan_task": {"tool": name, "params": exact_params},
        }))

    async def present(params, prose):
        calls.append((params, prose))
        if len(calls) == 1:
            return "The saved draft changed before quotation."
        turn.outcome = (None, run_id, None, [])
        return None

    monkeypatch.setattr(turn, "_dispatch", dispatch)
    monkeypatch.setattr(turn, "_present_plan", present)
    first = await turn.execute("prepare_visual_assets", None, "")
    assert not first.ok and not first.stop_after_observation
    assert "changed before quotation" in first.text
    assert isinstance(await turn.execute("search_music", None, ""), str)
    assert isinstance(await turn.execute("design_video", SimpleNamespace(save=True), ""), str)
    accepted = await turn.execute("prepare_visual_assets", None, "")
    assert json.loads(accepted.text)["run_id"] == str(run_id)
    assert json.loads(accepted.text)["execution"] == "run_created"
    assert accepted.ok and accepted.stop_after_observation
    assert run.context["media_journey"] == turn.media_journey
    assert all(
        params.production_intent is True and params.tasks[0].params == exact_params and prose
        for params, prose in calls
    )

    async def held_plan(params, prose):
        turn.outcome = (SimpleNamespace(intent={}), None, None, [])
        return None

    monkeypatch.setattr(turn, "_present_plan", held_plan)
    held = await turn.execute("prepare_visual_assets", None, "")
    assert not held.ok and held.stop_after_observation
    assert json.loads(held.text)["execution"] == "run_not_created"
    assert json.loads(held.text)["run_id"] is None


@pytest.mark.asyncio
async def test_media_stop_reports_the_scene_from_the_failed_image_write(monkeypatch):
    from unittest.mock import AsyncMock

    from app.agents.working_drafts import WorkingDraftRejected, WorkingDraftUpdated
    from app.chat import video_turn_seats

    project = SimpleNamespace(id=uuid4(), language="zh")
    turn = PlanTurn(None, uuid4(), SimpleNamespace(id=uuid4()), project, ChatRequest(
        project_id=project.id, message="继续制作",
    ))
    turn.media_state = {"phase": "audio", "approved_images": []}
    scene = SimpleNamespace(scene_id="demo", snapshot_id=uuid4())
    draft = {"content": {"scenes": [{"scene_id": "opening"}, {"scene_id": "demo"}]}}
    failed = WorkingDraftRejected(
        "source snapshot is missing or not prepared",
        [{"type": "source_not_ready", "loc": ["scene", "snapshot_id"]}],
        draft,
    )
    monkeypatch.setattr(video_turn_seats, "video_request_id", AsyncMock(return_value="request"))
    monkeypatch.setattr(video_turn_seats, "design_video_seat", AsyncMock(side_effect=[
        (None, failed), (None, WorkingDraftUpdated(draft)),
    ]))
    params = SimpleNamespace(scene=scene)
    await turn._design_video(params)
    assert "第 2 幕" in turn._media_stop_text()
    await turn._design_video(params)
    assert "第 2 幕" not in turn._media_stop_text()


@pytest.mark.asyncio
async def test_settled_read_handoff_ends_the_loop_without_an_extra_model_call(monkeypatch):
    class Provider:
        capabilities = ProviderCapabilities(supports_native_tools=True)
        calls = 0

        async def generate_with_tools(self, **kwargs):
            self.calls += 1
            return ToolGeneration(
                content="I’ll prepare the image.",
                tool_calls=[ToolCall(id="read", name="prepare_image", arguments={})],
            )

    provider = Provider()
    from app.chat.intent import intent_router

    monkeypatch.setattr(intent_router, "client", provider)
    tools = [ChatTool(
        name="prepare_image", description="Prepare", params_model=None, terminal=False,
    )]

    async def dispatch(name, params, prose):
        return ToolObservation("authorized preparation docked", stop_after_observation=True)

    outcome = await intent_router.call_loop(dispatch, tools=tools, message="prepare")
    assert outcome.tool_name == "prepare_image"
    assert provider.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", [None, "review", "stale", "stop", "newer", "pending", "missing_opening"])
async def test_visual_settlement_continues_at_most_once_in_original_chat(monkeypatch, stop_reason):
    from app.chat import media_journey, plan_turn, service
    from app.models.schemas import PendingPlan
    from app.models.tables import Message, WorkflowRun

    draft, spec = draft_with_scene()
    conversation = SimpleNamespace(
        id=uuid4(), context={"schema_version": 1, "items": [{
            "candidate": {"target_tool": "design_video", "active": True, "candidate_id": "draft",
                          "candidate_digest": "a" * 64},
            "executed_arguments": draft,
        }]},
    )
    opening = SimpleNamespace(
        id=uuid4(), conversation_id=conversation.id, turn_state="settled",
        intent={"stop_requested_at": "now"} if stop_reason == "stop" else {}, seq=1,
        content="给 https://www.legitevi.com/en 做一只宣传片",
    )
    run = SimpleNamespace(
        id=uuid4(), status=WorkflowStatus.COMPLETED,
        context={
            "media_journey": {"opening_id": str(opening.id)},
            "visual_asset_preparation": {"request": {"draft_ref": {
                "draft_id": "draft", "draft_digest": ("b" if stop_reason == "stale" else "a") * 64,
            }}},
            "creative_state": {},
        },
    )
    project = SimpleNamespace(id=uuid4(), user_id=uuid4())
    commits, resumed, blockers = [], [], []

    async def get(cls, key, **kwargs):
        assert key == (run.id if cls is WorkflowRun else opening.id)
        assert cls in {WorkflowRun, Message}
        return run if cls is WorkflowRun else None if stop_reason == "missing_opening" else opening

    async def absent(*args):
        return None

    async def results(*args):
        if stop_reason == "review":
            return [result_for(spec, "unavailable", review_retry_of={"digest": "retry"})]
        return [{
            "scene_id": spec.scene_id, "request_digest": spec.request_digest(),
            "code": "execution_error", "detail": "Render interrupted",
        }]

    async def resume(db, user_id, conversation, project, request, **kwargs):
        assert kwargs["turn_id"] == opening.id
        assert isinstance(kwargs["media_resume_pending"], PendingPlan)
        assert kwargs["media_resume_pending"].prompt == opening.content
        assert kwargs["media_resume_draft"].arguments == draft
        assert kwargs["media_resume_draft"].candidate_digest == "a" * 64
        resumed.append(True)
        return None, None, None, []

    async def commit():
        commits.append(True)

    async def create_message(db, conversation_id, role, content, **kwargs):
        assert conversation_id == conversation.id and role == "assistant" and content
        assert kwargs["workflow_run_id"] == run.id
        assert kwargs["turn_id"] == (None if stop_reason == "missing_opening" else opening.id)
        blockers.append(kwargs["intent"]["media_journey"])

    async def pending_question(*args):
        return object() if stop_reason == "pending" else None

    async def newer(*args):
        return uuid4() if stop_reason == "newer" else None

    monkeypatch.setattr(service, "latest_pending_question", pending_question)
    monkeypatch.setattr(service, "_create_message", create_message)
    monkeypatch.setattr(service, "list_conversation_messages", absent)
    monkeypatch.setattr(service, "fold_conversation_usage", lambda *a, **k: absent())
    monkeypatch.setattr(plan_turn, "run_plan_turn", resume)
    monkeypatch.setattr(media_journey, "visual_results", results)
    db = SimpleNamespace(get=get, refresh=absent, scalar=newer, commit=commit)
    await continue_media_journey(db, project, conversation, run)
    await continue_media_journey(db, project, conversation, run)
    assert run.context["media_continuation_finished"] is True
    assert commits == [True]
    assert resumed == ([] if stop_reason else [True])
    state = "stopped" if stop_reason in {"stop", "newer"} else "blocked"
    assert blockers == ([{"opening_id": str(opening.id), "state": state}] if stop_reason else [])


def test_audio_preparation_blocks_formal_work():
    from app.chat.media_journey import media_write_rejection
    assert media_write_rejection("audio", "design_video", SimpleNamespace(save=True))
    assert media_write_rejection("audio", "review_working_draft", None)
    assert media_write_rejection("audio", "produce_video", None)
