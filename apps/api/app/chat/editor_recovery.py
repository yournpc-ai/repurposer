"""Reconcile interrupted Chat replies from editor writes in the immutable store."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select

from app.models.tables import Composition, CompositionVersion, Conversation, Message, Project, WorkflowRun


def editor_lock_key(turn_id):
    # Stable signed bigint in PostgreSQL's advisory-lock key space.
    return int.from_bytes(turn_id.bytes[:8], "big", signed=True)


async def report_committed_edits(db, opening):
    from app.chat.editor import EDITOR_TOOLS
    from app.chat.service import _create_message, _prefers_zh

    markers = (opening.intent or {}).get("editor_commits") or []
    if not markers:
        return
    conversation = await db.get(Conversation, opening.conversation_id)
    rows = await db.scalars(
        select(CompositionVersion)
        .join(Composition, Composition.id == CompositionVersion.composition_id)
        .where(
            CompositionVersion.request_id.in_([m["request"] for m in markers]),
            Composition.owner_id == conversation.user_id,
            Composition.origin_project_id == conversation.project_id,
        )
    )
    versions = {v.request_id: v for v in rows}
    labels = {
        "create_video": ("创建初稿", "create draft"),
        "insert_audio": ("插入音频", "insert audio"),
        "split_clip": ("分割", "split"),
        "trim_clip": ("裁剪", "trim"),
        "extend_still": ("延长片尾画面", "extend closing still"),
        "move_clip": ("移动片段", "move"),
        "translate": ("平移画面", "translation"),
        "scale": ("缩放", "scale"),
    }
    zh = _prefers_zh(opening.content)
    saved = []
    done = {}
    for marker in markers:
        version = versions.get(marker["request"])
        if version is None:
            continue
        name = marker["tool"]
        action = labels[name][0 if zh else 1]
        saved.append(
            f"{action}（版本 {version.version}）" if zh else f"{action} (version {version.version})"
        )
        if marker.get("activity_row"):
            done[UUID(marker["activity_row"])] = next(t.presentation.done_key for t in EDITOR_TOOLS if t.name == name)
    if not saved:
        return
    activities = await db.scalars(
        select(Message).where(
            Message.turn_id == opening.id,
            Message.intent["type"].astext == "activity",
            Message.intent["frame"]["status"].astext.in_(["active", "cancelled"]),
        )
    )
    for row in activities:
        frame = dict(row.intent["frame"])
        if row.id in done:
            frame.update(status="completed", key=done[row.id])
        elif frame["status"] == "active":
            frame["status"] = "cancelled"
        if frame.get("group_id"):
            frame["call_state"] = "not_executed" if frame.get("call_state") == "queued" else frame["status"]
        frame["settled_at"] = datetime.now(UTC).isoformat()
        row.intent = {**row.intent, "frame": frame}
    text = (
        "本轮已中断。已保存的修改有" + "、".join(saved) + "。可以从当前作品继续。"
        if zh
        else "This turn was interrupted. Saved edits: "
        + ", ".join(saved)
        + ". You can continue from the current work."
    )
    await _create_message(
        db,
        opening.conversation_id,
        "assistant",
        text,
        turn_id=opening.id,
        intent={"type": "editor_recovery"},
    )


async def settle_interrupted_members(db, turn_id):
    active = await db.scalars(select(Message).where(
        Message.turn_id == turn_id, Message.intent["frame"].has_key("group_id"),
        Message.intent["frame"]["status"].astext == "active"))
    for member in active:
        frame = dict(member.intent["frame"])
        frame.update(status="cancelled", settled_at=datetime.now(UTC).isoformat(),
                     call_state="not_executed" if frame["call_state"] == "queued" else "cancelled")
        member.intent = {**member.intent, "frame": frame}


async def recover_interrupted_edits(db, conversation_id):
    """Called on history load and next submission. A live writer owns the
    advisory lock until its outer Chat transaction commits or rolls back."""
    recovered = await recover_media_receipts(db, conversation_id)
    media_turns = select(Message.turn_id).where(
        Message.conversation_id == conversation_id, Message.intent.has_key("editor_media"))
    batch_turns = select(Message.turn_id).where(
        Message.conversation_id == conversation_id, Message.intent["frame"].has_key("group_id"))
    ids = list(
        await db.scalars(
            select(Message.id).where(
                Message.conversation_id == conversation_id,
                Message.turn_state == "in_flight",
                or_(Message.intent.has_key("editor_commits"), Message.id.in_(media_turns), Message.id.in_(batch_turns)),
            )
        )
    )
    for turn_id in ids:
        # The original native execution can finish after its API process dies.
        # The existing trigger dispatcher owns continuation; history only delivers recorded results.
        result = await db.scalar(select(Message).where(Message.turn_id == turn_id,
            Message.intent.has_key("editor_media"), Message.intent.has_key("media_result"),
            Message.workflow_run_id.is_not(None)).order_by(Message.seq.desc()).limit(1))
        if result is not None:
            opening = await db.get(Message, turn_id)
            if opening and not (opening.intent or {}).get("resumed_media"):
                from app.chat.trigger_turn import fire_trigger, TRIGGER_RUN_COMPLETED

                run = await db.get(WorkflowRun, result.workflow_run_id)
                fire_trigger(run.project_id, TRIGGER_RUN_COMPLETED, str(run.id))
                continue
        if not await db.scalar(select(func.pg_try_advisory_xact_lock(editor_lock_key(turn_id)))):
            continue
        row = await db.get(Message, turn_id, with_for_update=True, populate_existing=True)
        if row is not None and row.turn_state == "in_flight":
            media = list(await db.scalars(select(Message).where(
                Message.turn_id == row.id, Message.intent.has_key("editor_media"),
            ).order_by(Message.seq)))
            pending = any(m.workflow_run_id and not m.intent.get("media_result") for m in media)
            if pending:
                continue
            for receipt in media:
                await settle_media_activity(db, receipt)
            await report_committed_edits(db, row)
            await settle_interrupted_members(db, turn_id)
            row.turn_state = "failed"
            await db.flush()
            recovered = True
    return recovered


async def recover_media_receipts(db, conversation_id=None):
    from botocore.exceptions import BotoCoreError, ClientError
    import structlog
    from app.chat.editor_media import settle_media_receipt
    from app.models.schemas import WorkflowStatus

    query = select(WorkflowRun, Project).join(Project, Project.id == WorkflowRun.project_id).join(
        Message, Message.workflow_run_id == WorkflowRun.id
    ).where(Message.intent.has_key("editor_media"), ~Message.intent.has_key("media_result"),
            WorkflowRun.status.in_([WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED]))
    if conversation_id:
        query = query.where(Message.conversation_id == conversation_id)
    settled = False
    for run, project in (await db.execute(query.order_by(WorkflowRun.id))).all():
        try:
            await settle_media_receipt(db, project, run)
            settled = True
        except (OSError, BotoCoreError, ClientError) as exc:
            structlog.get_logger().warning("media_delivery_unavailable", run_id=str(run.id),
                                           error_type=type(exc).__name__)
    return settled


async def resume_finished_media(db):
    from sqlalchemy.orm import aliased
    from app.chat.trigger_turn import fire_trigger, TRIGGER_RUN_COMPLETED

    opening = aliased(Message)
    rows = await db.execute(select(WorkflowRun.project_id, WorkflowRun.id)
        .join(Message, Message.workflow_run_id == WorkflowRun.id)
        .join(opening, opening.id == Message.turn_id)
        .where(opening.turn_state == "in_flight", Message.intent.has_key("editor_media"),
               Message.intent.has_key("media_result")).order_by(Message.seq.desc()))
    for project_id, run_id in rows:
        fire_trigger(project_id, TRIGGER_RUN_COMPLETED, str(run_id))


async def settle_media_activity(db, receipt):
    from app.chat.editor import EDITOR_TOOLS

    name = receipt.intent.get("tool")
    tool = next((t for t in EDITOR_TOOLS if t.name == name), None)
    if tool is None:
        return
    activity_id = receipt.intent.get("activity_id")
    query = select(Message).where(Message.turn_id == receipt.turn_id,
        Message.intent["frame"]["key"].astext == tool.presentation.active_key,
        Message.intent["frame"]["status"].astext == "active")
    if activity_id:
        query = query.where(Message.id == UUID(activity_id))
    activity = await db.scalar(query.order_by(Message.seq.desc()).limit(1))
    if activity:
        success = (receipt.intent.get("media_result") or {}).get("status") == "available"
        frame = {**activity.intent["frame"], "status": "completed" if success else "failed",
                 "settled_at": datetime.now(UTC).isoformat()}
        if frame.get("group_id"):
            result_status = (receipt.intent.get("media_result") or {}).get("status")
            frame["call_state"] = "provider_unknown" if result_status == "provider_unknown" else frame["status"]
        if success:
            frame["key"] = tool.presentation.done_key
        activity.intent = {**activity.intent, "frame": frame}
