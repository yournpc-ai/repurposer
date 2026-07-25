"""Notification service — writers and readers of the ``notifications`` table.

Platform-layer event stream (MODULE_ARCHITECTURE §4): thin events (publish
succeeded/failed, channel expired; feature announcements later) surface in
the bell dropdown instead of growing dedicated pages. This module only
depends on tables — keep it import-safe from any service (writers import it
lazily at the call site).
"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Notification, now_utc


async def create_notification(
    db: AsyncSession,
    *,
    user_id: UUID,
    type: str,
    payload: dict,
) -> Notification:
    """Append one notification row. Callers commit (writes ride the caller's
    session so a notification commits atomically with the event it reports)."""
    notification = Notification(user_id=user_id, type=type, payload=payload)
    db.add(notification)
    await db.flush()
    return notification


async def list_notifications(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int = 30,
) -> tuple[list[Notification], int]:
    """Recent notifications (newest first) + unread count for the bell dot."""
    items = list(
        (
            await db.execute(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    unread = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
    ).scalar_one()
    return items, unread


async def mark_all_read(db: AsyncSession, user_id: UUID) -> None:
    """Opening the bell panel marks everything read (bell dot clears)."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=now_utc())
    )
