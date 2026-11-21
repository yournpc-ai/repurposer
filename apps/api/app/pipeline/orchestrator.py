"""Cancellation and settlement of outstanding Run records."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    AnswerPayload,
    ProjectStatus,
    RenderStatus,
    WorkflowStatus,
)
from app.models.tables import Message, Output, WorkflowStep, Project, WorkflowRun
# Graph fill/back-write (ADR-057 K2) — top-level is cycle-free: graph_fill's
# module-level chain (graph / graph_store / outputs / billing) never points
# back here; its own import of THIS module stays function-level inside
# stamp_draft_graph.
from app.pipeline.run_review import output_is_delivered
# Graph fill/back-write (ADR-057 K2) — top-level is cycle-free: graph_fill's
# module-level chain (graph / graph_store / outputs / billing) never points
# back here; its own import of THIS module stays function-level inside
# stamp_draft_graph.
from app.platform.billing import (
    release_run,
)

logger = structlog.get_logger()

async def cancel_run(
    db: AsyncSession,
    run: WorkflowRun,
    project: Project,
) -> WorkflowRun:
    """Cancel an owned active Run using the existing step/render fences.

    The caller locks project then run. This transaction revokes every active
    claim and releases only the unconsumed hold; completed Outputs, previous
    deliveries and captures are deliberately left untouched. No completion or
    failure trigger is emitted for CANCELLED.
    """
    if run.status in {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }:
        return run

    nodes = list((
        await db.execute(
            select(WorkflowStep)
            .where(WorkflowStep.run_id == run.id)
            .with_for_update()
        )
    ).scalars().all())
    output_ids = {
        UUID(str(output_id))
        for node in nodes
        for output_id in [
            *(node.output_refs or []),
            *((node.spec or {}).get("output_id"),),
        ]
        if output_id
    }
    now = datetime.now(UTC)
    for node in nodes:
        if node.status in {"pending", "running", "waiting"}:
            node.status = "cancelled"
            node.claim_token = None
            node.finished_at = now
            node.updated_at = now

    outputs = list((
        await db.execute(select(Output).where(Output.id.in_(output_ids)).with_for_update())
    ).scalars().all()) if output_ids else []
    any_landed = any(output_is_delivered(output) for output in outputs)
    for output in outputs:
        if output.render_status in {RenderStatus.PENDING, RenderStatus.RENDERING}:
            output.render_status = RenderStatus.CANCELLED
            output.render_claim_token = None

    # A cancelled direction checkpoint must not rebuild as a pending dock on
    # refresh. It settles through the existing answer payload, not a new UI
    # control or message model.
    pending_questions = list((
        await db.execute(
            select(Message).where(
                Message.workflow_run_id == run.id,
                Message.role == "assistant",
                Message.question.is_not(None),
                Message.answer.is_(None),
            )
        )
    ).scalars().all())
    for message in pending_questions:
        message.answer = AnswerPayload(
            kind="bail", text="cancelled", answered_at=now
        ).model_dump(mode="json")

    journey = (run.context or {}).get("media_journey")
    if journey:
        # The active plan and its Run were persisted together. Settle that
        # same transcript marker atomically with cancellation for live/replay.
        plan = await db.scalar(select(Message).where(
            Message.workflow_run_id == run.id,
            Message.intent["media_journey"]["opening_id"].as_string() == journey["opening_id"],
            Message.intent["media_journey"]["state"].as_string() == "active",
        ).order_by(Message.seq.desc()).limit(1))
        if plan is not None:
            plan.intent = {**plan.intent, "media_journey": {**journey, "state": "stopped"}}
        run.context = {**run.context, "media_continuation_finished": True}

    run.status = WorkflowStatus.CANCELLED
    run.error = None
    run.updated_at = now
    settled = sum(
        node.status in {"done", "failed", "skipped", "cancelled"} for node in nodes
    )
    run.progress = int(settled / len(nodes) * 100) if nodes else 100
    project.status = ProjectStatus.REVIEW if any_landed else ProjectStatus.DRAFT
    project.updated_at = now
    await release_run(db, user_id=project.user_id, run_id=run.id)
    await db.commit()
    logger.info("run_cancelled", run_id=str(run.id), project_id=str(project.id))
    return run
