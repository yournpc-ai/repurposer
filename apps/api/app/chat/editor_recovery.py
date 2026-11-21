"""Reconcile interrupted Chat replies from editor writes in the immutable store."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select

from app.models.tables import Composition, CompositionVersion, Conversation, Message, Project


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
        "bind_clip_source": ("绑定固定素材", "bind fixed source"),
        "split_clip": ("分割", "split"),
        "remove_clip": ("移除片段", "remove clip"),
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
    recovered = False
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
        if not await db.scalar(select(func.pg_try_advisory_xact_lock(editor_lock_key(turn_id)))):
            continue
        row = await db.get(Message, turn_id, with_for_update=True, populate_existing=True)
        if row is not None and row.turn_state == "in_flight":
            media = list(await db.scalars(select(Message).where(
                Message.turn_id == row.id, Message.intent.has_key("editor_media"),
            ).order_by(Message.seq)))
            if any(m.intent.get("media_permission") and not m.answer for m in media):
                continue
            if any((m.intent.get("export_job") or m.intent.get("media_job")) and m.intent.get("media_result") and
                   not (row.intent or {}).get("resumed_media") for m in media):
                # The worker polls durable results and competes for the existing opening lock.
                continue
            pending = any((m.intent.get("export_job") or m.intent.get("media_job")) and not m.intent.get("media_result") for m in media)
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


async def resume_job_receipts():
    """One bounded scan; the live API and every worker share the opening lock."""
    from sqlalchemy.orm import aliased
    from app.models.database import AsyncSessionLocal
    from app.chat.editor_media import continue_media_turn

    opening = aliased(Message)
    later = aliased(Message)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Conversation.project_id, Message.id)
            .select_from(Message).join(Conversation, Conversation.id == Message.conversation_id)
            .join(opening, opening.id == Message.turn_id)
            .where(opening.turn_state == "in_flight", Message.intent.has_key("media_result"),
                   or_(Message.intent.has_key("media_job"), Message.intent.has_key("export_job"),
                       Message.intent["media_permission"]["recovery_quote"].as_boolean().is_(True)))
            .where(~select(later.id).where(later.turn_id == opening.id, later.seq > Message.seq,
                                         later.intent.has_key("editor_media")).exists())
            .order_by(Message.created_at).limit(32))).all()
    for project_id, receipt_id in rows:
        async with AsyncSessionLocal() as db:
            await continue_media_turn(db, await db.get(Project, project_id), await db.get(Message, receipt_id))
