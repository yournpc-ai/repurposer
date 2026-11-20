"""Stop outstanding work referenced by an existing Chat receipt."""

from sqlalchemy import select

from app.models.tables import Message, WorkflowRun


async def stop_media_journey(db, opening, conversation) -> dict | None:
    """Fence the next automatic Start even when its preceding Run is already complete."""
    from datetime import UTC, datetime

    from app.models.schemas import WorkflowStatus
    from app.models.tables import Project
    from app.pipeline.orchestrator import cancel_run

    opening_id = opening.id
    project_id = conversation.project_id
    await db.refresh(opening, with_for_update={"key_share": True})
    marker = await db.scalar(select(Message).where(
        Message.conversation_id == conversation.id,
        Message.intent["media_journey"]["opening_id"].as_string() == str(opening_id),
    ).order_by(Message.seq.desc().nulls_last()).limit(1).execution_options(populate_existing=True))
    if marker is None or opening.turn_state != "settled":
        return None
    journey = marker.intent["media_journey"]
    if journey["state"] not in {"active", "stopped"}:
        return {"seq": marker.seq, "intent": {"media_journey": journey}}
    stopped = {**journey, "state": "stopped"}
    receipt = {"seq": marker.seq, "intent": {"media_journey": stopped}}
    if not (opening.intent or {}).get("stop_requested_at"):
        opening.intent = {**(opening.intent or {}), "stop_requested_at": datetime.now(UTC).isoformat()}
    marker.intent = {**marker.intent, "media_journey": stopped}
    # Once the opening is fenced no further Start can commit. In the handoff
    # gap there is no Run to lock. If Start won, cancel in project → Run order.
    active_id = await db.scalar(select(WorkflowRun.id).where(
        WorkflowRun.project_id == project_id,
        WorkflowRun.context["media_journey"]["opening_id"].as_string() == str(opening_id),
        WorkflowRun.status.in_([WorkflowStatus.PENDING, WorkflowStatus.RUNNING, WorkflowStatus.WAITING_HUMAN]),
    ).limit(1))
    await db.commit()
    if active_id is not None:
        project = await db.get(Project, project_id, with_for_update=True, populate_existing=True)
        active = await db.get(WorkflowRun, active_id, with_for_update=True, populate_existing=True)
        if active is not None:
            await cancel_run(db, active, project)
    return receipt
