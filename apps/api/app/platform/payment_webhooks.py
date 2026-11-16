"""Persistent Stripe webhook receipts and asynchronous payment alerts.

The receipt table is an audit trail and an alert outbox, never a payment
ledger. Financial idempotency remains owned by payment_orders and
credit_transactions. Only verified provider events get an event-specific row;
rejected public requests are aggregated hourly to bound unauthenticated storage
growth. Raw payloads, signatures, secrets and recipient addresses are never
stored on the receipt.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
import structlog
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.tables import PaymentWebhookEvent, now_utc

logger = structlog.get_logger()

_ALERT_IGNORED_REASONS = {
    "invalid_session",
    "order_not_found",
    "provider_mismatch",
    "livemode_mismatch",
    "checkout_session_mismatch",
    "order_metadata_mismatch",
    "package_mismatch",
    "user_mismatch",
    "amount_mismatch",
    "currency_mismatch",
    "invalid_order_state",
    "event_payload_mismatch",
}
_ALERT_MAX_ATTEMPTS = 5
_ALERT_LEASE = timedelta(seconds=60)
_ALERT_BACKOFF = (60, 300, 900, 3600)
_PROCESSING_TIMEOUT = timedelta(minutes=10)


def should_alert(status: str, reason_code: str | None) -> bool:
    """Only failures and security/configuration-relevant ignores alert."""
    return status == "failed" or (
        status == "ignored" and reason_code in _ALERT_IGNORED_REASONS
    )


def payload_digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _event_key(event_id: str) -> str:
    return f"stripe:event:{event_id}"


def _rejected_key(reason_code: str, at: datetime) -> str:
    # Invalid signatures are untrusted input. One row per reason/hour records
    # the outage without letting an unauthenticated caller create unbounded rows.
    return f"stripe:rejected:{reason_code}:{at.strftime('%Y%m%d%H')}"


async def record_rejected_delivery(
    db: AsyncSession,
    *,
    payload: bytes,
    signature_valid: bool,
    reason_code: str,
    response_status: int,
) -> None:
    """Persist one hourly aggregate for a rejected delivery and request an alert."""
    now = now_utc()
    key = _rejected_key(reason_code, now)
    values = {
        "provider": "stripe",
        "dedupe_key": key,
        "event_id": None,
        "event_type": None,
        "livemode": None,
        "order_id": None,
        "checkout_session_id": None,
        "payload_hash": payload_digest(payload),
        "signature_valid": signature_valid,
        "status": "failed",
        "reason_code": reason_code,
        "response_status": response_status,
        "attempt_count": 1,
        "first_received_at": now,
        "last_received_at": now,
        "processed_at": now,
        "alert_status": "pending",
        "alert_attempt_count": 0,
        "alert_next_attempt_at": now,
    }
    stmt = pg_insert(PaymentWebhookEvent).values(**values)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["dedupe_key"],
            set_={
                "attempt_count": PaymentWebhookEvent.attempt_count + 1,
                "last_received_at": now,
                "response_status": response_status,
                # A prior alert remains sent/failed; the next hourly bucket
                # creates the next notification instead of re-alerting here.
            },
        )
    )
    await db.commit()
    logger.info(
        "payment_webhook_rejected_recorded",
        reason_code=reason_code,
        response_status=response_status,
        signature_valid=signature_valid,
    )


async def begin_verified_event(
    db: AsyncSession,
    *,
    event_id: str,
    event_type: str,
    event_livemode: bool | None,
    payload: bytes,
    order_id: UUID | None,
    checkout_session_id: str | None,
) -> bool:
    """Create/claim the durable receipt before applying the business event.

    Returns False if a provider event id was reused with different bytes. The
    caller must not apply such an event; it is audited and alerted instead.
    """
    now = now_utc()
    digest = payload_digest(payload)
    values = {
        "provider": "stripe",
        "dedupe_key": _event_key(event_id),
        "event_id": event_id,
        "event_type": event_type,
        "livemode": event_livemode,
        "order_id": order_id,
        "checkout_session_id": checkout_session_id,
        "payload_hash": digest,
        "signature_valid": True,
        "status": "processing",
        "reason_code": None,
        "response_status": None,
        "attempt_count": 1,
        "first_received_at": now,
        "last_received_at": now,
        "processed_at": None,
        "alert_status": None,
        "alert_attempt_count": 0,
    }
    stmt = pg_insert(PaymentWebhookEvent).values(**values)
    stored_digest = (
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["dedupe_key"],
                set_={
                    "attempt_count": PaymentWebhookEvent.attempt_count + 1,
                    "last_received_at": now,
                    "status": "processing",
                    "reason_code": None,
                    "response_status": None,
                },
            ).returning(PaymentWebhookEvent.payload_hash)
        )
    ).scalar_one()
    await db.commit()
    return stored_digest == digest


async def finish_verified_event(
    db: AsyncSession,
    *,
    event_id: str,
    status: str,
    reason_code: str | None,
    response_status: int,
) -> None:
    """Record the exact business outcome and enqueue at most one alert per event."""
    if status not in {"processed", "ignored", "failed"}:
        raise ValueError(f"invalid webhook receipt status: {status}")
    event = (
        await db.execute(
            select(PaymentWebhookEvent)
            .where(PaymentWebhookEvent.dedupe_key == _event_key(event_id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if event is None:
        raise RuntimeError(f"missing webhook receipt for {event_id}")

    now = now_utc()
    event.status = status
    event.reason_code = reason_code
    event.response_status = response_status
    event.last_received_at = now
    if status != "failed":
        event.processed_at = event.processed_at or now
    if should_alert(status, reason_code):
        if event.alert_status is None:
            event.alert_status = "pending"
            event.alert_next_attempt_at = now
    elif event.alert_status == "pending":
        # A retry recovered before the worker claimed the alert.
        event.alert_status = None
        event.alert_next_attempt_at = None
    await db.commit()
    logger.info(
        "payment_webhook_receipt_finished",
        event_id=event_id,
        status=status,
        reason_code=reason_code,
        response_status=response_status,
        alert_status=event.alert_status,
    )


async def flag_stale_webhook_events(db: AsyncSession) -> int:
    """Turn abandoned processing receipts into alertable failures.

    A process crash cannot execute the request's exception handler. Stripe may
    retry, but the durable receipt must not remain silently processing forever.
    """
    cutoff = now_utc() - _PROCESSING_TIMEOUT
    events = (
        (
            await db.execute(
                select(PaymentWebhookEvent)
                .where(
                    PaymentWebhookEvent.status == "processing",
                    PaymentWebhookEvent.last_received_at < cutoff,
                )
                .order_by(PaymentWebhookEvent.last_received_at)
                .with_for_update(skip_locked=True)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for event in events:
        event.status = "failed"
        event.reason_code = "processing_timeout"
        event.response_status = None
        if event.alert_status is None:
            event.alert_status = "pending"
            event.alert_next_attempt_at = now_utc()
        logger.error(
            "payment_webhook_processing_timeout",
            receipt_id=str(event.id),
            provider_event_id=event.event_id,
            order_id=str(event.order_id) if event.order_id else None,
        )
    if events:
        await db.commit()
    return len(events)


@dataclass(frozen=True)
class PaymentAlertClaim:
    receipt_id: UUID
    claim_token: UUID


@dataclass(frozen=True)
class _AlertSnapshot:
    receipt_id: UUID
    claim_token: UUID
    attempt: int
    provider_event_id: str | None
    event_type: str | None
    livemode: bool | None
    order_id: UUID | None
    checkout_session_id: str | None
    status: str
    reason_code: str | None
    response_status: int | None
    delivery_attempt_count: int


async def claim_payment_alert(db: AsyncSession) -> PaymentAlertClaim | None:
    """Claim one due alert with a lease; receipt rows are the outbox queue."""
    if not settings.payment_alert_recipient_list:
        return None
    now = datetime.now(UTC)
    while True:
        event = (
            await db.execute(
                select(PaymentWebhookEvent)
                .where(
                    or_(
                        (
                            (PaymentWebhookEvent.alert_status == "pending")
                            & (
                                PaymentWebhookEvent.alert_next_attempt_at.is_(None)
                                | (PaymentWebhookEvent.alert_next_attempt_at <= now)
                            )
                        ),
                        (
                            (PaymentWebhookEvent.alert_status == "sending")
                            & (PaymentWebhookEvent.alert_started_at <= now - _ALERT_LEASE)
                        ),
                    )
                )
                .order_by(PaymentWebhookEvent.first_received_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if event is None:
            return None
        if event.alert_attempt_count >= _ALERT_MAX_ATTEMPTS:
            event.alert_status = "failed"
            event.alert_claim_token = None
            event.alert_started_at = None
            event.alert_last_error = "delivery_attempt_cap"
            await db.commit()
            logger.error(
                "payment_alert_attempt_cap",
                receipt_id=str(event.id),
                provider_event_id=event.event_id,
            )
            continue
        token = uuid4()
        event.alert_status = "sending"
        event.alert_attempt_count += 1
        event.alert_claim_token = token
        event.alert_started_at = now
        event.alert_last_error = None
        await db.commit()
        return PaymentAlertClaim(receipt_id=event.id, claim_token=token)


async def _load_alert_snapshot(claim: PaymentAlertClaim) -> _AlertSnapshot | None:
    async with AsyncSessionLocal() as db:
        event = await db.get(PaymentWebhookEvent, claim.receipt_id)
        if event is None or event.alert_claim_token != claim.claim_token:
            return None
        return _AlertSnapshot(
            receipt_id=event.id,
            claim_token=claim.claim_token,
            attempt=event.alert_attempt_count,
            provider_event_id=event.event_id,
            event_type=event.event_type,
            livemode=event.livemode,
            order_id=event.order_id,
            checkout_session_id=event.checkout_session_id,
            status=event.status,
            reason_code=event.reason_code,
            response_status=event.response_status,
            delivery_attempt_count=event.attempt_count,
        )


def _alert_text(snapshot: _AlertSnapshot) -> str:
    def value(item: Any) -> str:
        return "unknown" if item is None else str(item)

    return "\n".join(
        [
            "Rookie Cut payment webhook needs attention.",
            f"Provider event: {value(snapshot.provider_event_id)}",
            f"Event type: {value(snapshot.event_type)}",
            f"Livemode: {value(snapshot.livemode)}",
            f"Outcome: {snapshot.status}",
            f"Reason: {value(snapshot.reason_code)}",
            f"HTTP response: {value(snapshot.response_status)}",
            f"Order: {value(snapshot.order_id)}",
            f"Checkout Session: {value(snapshot.checkout_session_id)}",
            f"Stripe delivery attempts recorded: {snapshot.delivery_attempt_count}",
            f"Internal receipt: {snapshot.receipt_id}",
        ]
    )


async def _send_alert_email(snapshot: _AlertSnapshot) -> None:
    recipients = settings.payment_alert_recipient_list
    if not settings.resend_api_key or not recipients:
        raise RuntimeError("payment alert email is not configured")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.from_email,
                "to": recipients,
                "subject": (
                    "[Rookie Cut] Payment webhook "
                    f"{snapshot.status}: {snapshot.reason_code or 'unknown'}"
                ),
                "text": _alert_text(snapshot),
            },
        )
        response.raise_for_status()


async def process_payment_alert(claim: PaymentAlertClaim) -> None:
    """Deliver one claimed alert, then fence the terminal write by claim token."""
    snapshot = await _load_alert_snapshot(claim)
    if snapshot is None:
        return
    error: str | None = None
    try:
        await _send_alert_email(snapshot)
    except Exception as exc:  # noqa: BLE001 — the outbox must retain every failure
        error = f"{type(exc).__name__}: {str(exc)[:300]}"

    async with AsyncSessionLocal() as db:
        event = await db.get(PaymentWebhookEvent, claim.receipt_id)
        if event is None or event.alert_claim_token != claim.claim_token:
            return
        now = now_utc()
        event.alert_claim_token = None
        event.alert_started_at = None
        if error is None:
            event.alert_status = "sent"
            event.alerted_at = now
            event.alert_last_error = None
            logger.info(
                "payment_alert_sent",
                receipt_id=str(event.id),
                provider_event_id=event.event_id,
                attempt=snapshot.attempt,
            )
        else:
            event.alert_status = (
                "failed" if snapshot.attempt >= _ALERT_MAX_ATTEMPTS else "pending"
            )
            event.alert_last_error = error
            backoff_seconds = _ALERT_BACKOFF[
                min(snapshot.attempt - 1, len(_ALERT_BACKOFF) - 1)
            ]
            event.alert_next_attempt_at = (
                None
                if event.alert_status == "failed"
                else now + timedelta(seconds=backoff_seconds)
            )
            logger.error(
                "payment_alert_failed",
                receipt_id=str(event.id),
                provider_event_id=event.event_id,
                attempt=snapshot.attempt,
                alert_status=event.alert_status,
                error=error,
            )
        await db.commit()
