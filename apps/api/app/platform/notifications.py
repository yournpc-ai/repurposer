"""Notification service — writers and readers of the ``notifications`` table.

Platform-layer event stream (MODULE_ARCHITECTURE §4): thin events (publish
succeeded/failed, channel expired; feature announcements later) surface in
the bell dropdown instead of growing dedicated pages. This module only
depends on tables — keep it import-safe from any service (writers import it
lazily at the call site).
"""

from datetime import timedelta
from uuid import UUID

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tables import Notification, User, now_utc
from app.platform.email import RESEND_API_URL


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
    if type in ("publish_failed", "publish_unknown", "channel_expired"):
        user = await db.get(User, user_id)
        if user and (user.settings or {}).get("publish_alerts") is True:
            notification.email_due_at = now_utc()
            notification.payload = {**payload, "email_locale": (user.settings or {}).get("locale")}
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


async def deliver_due_alert(db: AsyncSession) -> bool:
    """One committed event per delivery. Concurrent workers skip the locked row."""
    event = await db.scalar(
        select(Notification)
        .where(Notification.email_due_at <= now_utc())
        .order_by(Notification.email_due_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return False
    user = await db.get(User, event.user_id)
    event.email_due_at = None
    if (
        user
        and (user.settings or {}).get("publish_alerts") is True
        and event.created_at > now_utc() - timedelta(hours=23)
    ):
        zh = event.payload.get("email_locale") == "zh"
        subject = "视频发布需要处理" if zh else "Your video publication needs attention"
        message = (
            "打开 Rookie 的通知查看发布详情。"
            if zh
            else "Open your notifications in Rookie to review this publication."
        )
        # Keep the body stable for every retry of this idempotency key.
        subject = "Rookie · " + subject
        event.email_attempts += 1
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Idempotency-Key": f"publication-alert/{event.id}",
                    },
                    json={
                        "from": settings.from_email,
                        "to": [user.email],
                        "subject": subject,
                        "text": message,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError:
            structlog.get_logger().warning(
                "publication_alert_delivery_failed",
                event_id=str(event.id),
                attempt=event.email_attempts,
            )
            if event.email_attempts < 6:
                event.email_due_at = now_utc() + timedelta(minutes=2**event.email_attempts)
    await db.commit()
    return True
