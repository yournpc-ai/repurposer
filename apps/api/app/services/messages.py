"""Helpers for maintaining chat message state during generation."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Message


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_marker(
    label: str,
    marker_type: str = "status",
    meta: dict | None = None,
) -> dict:
    return {
        "id": str(uuid4()),
        "type": marker_type,
        "label": label,
        "timestamp": _now_iso(),
        "meta": meta or {},
    }


async def create_assistant_message(
    db: AsyncSession,
    project_id: UUID,
    params: dict | None = None,
) -> Message:
    """Create the assistant message that will track a generation run."""
    message = Message(
        project_id=project_id,
        role="assistant",
        content="",
        attachments=[],
        meta={
            "status": "pending",
            "progress": 0,
            "current_step": "queued",
            "markers": [_make_marker("Queued for generation", "status")],
            "results": {"clip_ids": [], "derivative_ids": []},
            "params": params or {},
        },
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def update_message_meta(
    db: AsyncSession,
    message_id: UUID,
    status: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    error: str | None = None,
) -> None:
    """Update mutable metadata on a message."""
    message = await db.get(Message, message_id)
    if message is None:
        return

    meta = dict(message.meta or {})
    if status is not None:
        meta["status"] = status
    if progress is not None:
        meta["progress"] = progress
    if current_step is not None:
        meta["current_step"] = current_step
    if error is not None:
        meta["error"] = error
    message.meta = meta
    await db.commit()


async def append_message_marker(
    db: AsyncSession,
    message_id: UUID,
    label: str,
    marker_type: str = "status",
    meta: dict | None = None,
) -> None:
    """Append an inline marker to an assistant message."""
    message = await db.get(Message, message_id)
    if message is None:
        return

    msg_meta = dict(message.meta or {})
    markers = list(msg_meta.get("markers", []))
    markers.append(_make_marker(label, marker_type, meta))
    msg_meta["markers"] = markers
    message.meta = msg_meta
    await db.commit()


async def add_result_refs(
    db: AsyncSession,
    message_id: UUID,
    clip_ids: list[UUID] | None = None,
    derivative_ids: list[UUID] | None = None,
) -> None:
    """Append result references to an assistant message."""
    message = await db.get(Message, message_id)
    if message is None:
        return

    msg_meta = dict(message.meta or {})
    results = dict(msg_meta.get("results", {"clip_ids": [], "derivative_ids": []}))
    existing_clips = set(results.get("clip_ids", []))
    existing_derivatives = set(results.get("derivative_ids", []))

    if clip_ids:
        existing_clips.update(str(cid) for cid in clip_ids)
    if derivative_ids:
        existing_derivatives.update(str(did) for did in derivative_ids)

    results["clip_ids"] = list(existing_clips)
    results["derivative_ids"] = list(existing_derivatives)
    msg_meta["results"] = results
    message.meta = msg_meta
    await db.commit()
