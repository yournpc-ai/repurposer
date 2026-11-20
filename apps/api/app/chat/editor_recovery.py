"""Reconcile interrupted Chat replies from editor writes in the immutable store."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select

from app.models.tables import Composition, CompositionVersion, Conversation, Message


def editor_lock_key(turn_id):
    # Stable signed bigint in PostgreSQL's advisory-lock key space.
    return int.from_bytes(turn_id.bytes[:8], "big", signed=True)


async def report_committed_edits(db, opening):
    from app.chat.editor import WRITE_TOOLS
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
        "split_clip": ("分割", "split"),
        "trim_clip": ("裁剪", "trim"),
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
            done[UUID(marker["activity_row"])] = WRITE_TOOLS[name].presentation.done_key
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


async def recover_interrupted_edits(db, conversation_id):
    """Called on history load and next submission. A live writer owns the
    advisory lock until its outer Chat transaction commits or rolls back."""
    ids = list(
        await db.scalars(
            select(Message.id).where(
                Message.conversation_id == conversation_id,
                Message.turn_state == "in_flight",
                Message.intent.has_key("editor_commits"),
            )
        )
    )
    recovered = False
    for turn_id in ids:
        if not await db.scalar(select(func.pg_try_advisory_xact_lock(editor_lock_key(turn_id)))):
            continue
        row = await db.get(Message, turn_id, with_for_update=True, populate_existing=True)
        if row is not None and row.turn_state == "in_flight":
            await report_committed_edits(db, row)
            row.turn_state = "failed"
            await db.flush()
            recovered = True
    return recovered
