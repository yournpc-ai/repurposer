"""Claim scheduled publications and reconcile platform receipts without reposting."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.schemas import ChannelAccountStatus, PublicationState
from app.models.tables import ChannelAccount, Publication
from app.distribution.adapters import get_adapter
from app.distribution.adapters.base import (
    JobHandle,
    PlatformError,
    PlatformErrorKind,
)
from app.distribution.channels import refresh_if_needed, usable_credentials
from app.distribution.core import _transition
from app.providers.storage import resolve_stored_url

logger = structlog.get_logger()

POLL_INTERVAL = timedelta(seconds=30)
# Lease for one begin/poll execution. It MUST dominate the slowest possible
# begin_publish — a LinkedIn video upload can legitimately run for minutes
# (httpx timeout 300s). A shorter lease lets the next tick re-claim the row
# while the first worker is still mid-upload → double post, and the
# platform_job_id anchor does not exist yet to reconcile against (§7).
BEGIN_LEASE = timedelta(minutes=10)
# Retryable-error backoff by claim count (§7: 指数退避改写 due_at).
_BACKOFF_SECONDS = [60, 300, 900, 3600]
# ~1h of 30s polls + retries; beyond this the order is failed as timed out.
_MAX_CLAIMS = 120


# ─────────────────────────────────────────────────────────────────────────────
# Claiming (called from the worker tick)
# ─────────────────────────────────────────────────────────────────────────────


async def claim_due_publication(db: AsyncSession) -> tuple[UUID, UUID] | None:
    """Claim one due order. An expired public-post dispatch may only be reconciled."""
    pub = await db.scalar(
        select(Publication).where(
            Publication.state.in_((PublicationState.SCHEDULED, PublicationState.PUBLISHING)),
            Publication.due_at <= func.now(),
        ).order_by(Publication.due_at, Publication.id).with_for_update(skip_locked=True).limit(1)
    )
    if pub is None:
        return None
    if pub.state == PublicationState.SCHEDULED:
        await _transition(db, pub, PublicationState.PUBLISHING)
    if pub.dispatch_started_at is not None:
        await _mark_unknown(db, pub)
        await db.commit()
        return None
    token = uuid4()
    pub.claim_token = token
    pub.due_at = func.now() + BEGIN_LEASE
    pub.attempt_count += 1
    await db.commit()
    return pub.id, token


async def _mark_unknown(db, pub):
    pub.due_at = None
    if pub.state != PublicationState.UNKNOWN:
        await _transition(db, pub, PublicationState.UNKNOWN, error="platform_outcome_unconfirmed")


async def reap_stale_publications(db: AsyncSession) -> None:
    """Defensive startup sweep: publishing rows with a NULL lease become due.

    Normal crash recovery is lease expiry — no reset needed. This only covers
    rows written before the lease discipline existed.
    """
    stale = (
        await db.execute(
            select(Publication).where(
                Publication.state == PublicationState.PUBLISHING,
                Publication.due_at.is_(None),
            )
        )
    ).scalars().all()
    for pub in stale:
        pub.due_at = datetime.now(UTC)
    if stale:
        await db.commit()
        logger.info("reaped_stale_publications", count=len(stale))


# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────


def _adapter_payload(pub: Publication) -> dict:
    """Frozen snapshot + derived fields the adapters need.

    Media storage keys are resolved to public object URLs here (platforms pull
    / we relay from these); ``ai_disclosure`` rides along for platforms with a
    disclosure field (ADR-026).
    """
    payload = dict(pub.payload or {})
    media = dict(payload.get("media") or {})
    for key in ("video", "srt", "image"):
        if media.get(key):
            media[key] = resolve_stored_url(media[key])
    payload["media"] = media
    if payload.get("cover_image_url"):
        payload["cover_image_url"] = resolve_stored_url(payload["cover_image_url"])
    payload["ai_disclosure"] = pub.ai_disclosure
    return payload


async def process_publication(pub_id: UUID, token: UUID) -> None:
    async with AsyncSessionLocal() as db:
        # Polling an uploaded LinkedIn video can itself issue the public POST.
        # The adapter calls before_publish immediately before that request.
        pub = await db.scalar(select(Publication).where(
            Publication.id == pub_id, Publication.claim_token == token,
            Publication.state == PublicationState.PUBLISHING, Publication.due_at > func.clock_timestamp(),
        ).with_for_update())
        if pub is None:
            return
        if pub.attempt_count > _MAX_CLAIMS:
            if pub.platform_job_id:
                await _mark_unknown(db, pub)
            else:
                await _transition(db, pub, PublicationState.FAILED, error="publish_timeout")
            await db.commit()
            return

        channel = await db.get(ChannelAccount, pub.channel_account_id) if pub.channel_account_id else None
        if channel is None or channel.status != ChannelAccountStatus.ACTIVE:
            if pub.platform_job_id:
                await _mark_unknown(db, pub)
            else:
                await _transition(db, pub, PublicationState.FAILED,
                                  error="channel_disconnected" if channel is None else "channel_token_expired")
            await db.commit()
            return

        async def before_publish():
            if not await db.scalar(select(Publication.id).where(
                Publication.id == pub_id, Publication.claim_token == token,
                Publication.state == PublicationState.PUBLISHING, Publication.due_at > func.clock_timestamp(),
            )):
                raise RuntimeError("Publication claim expired before dispatch")
            if pub.dispatch_started_at is not None:
                raise RuntimeError("A public post is already awaiting reconciliation")
            pub.dispatch_started_at = func.clock_timestamp()
            await db.commit()

        async def owns_result():
            await db.refresh(pub, with_for_update=True)
            return pub.claim_token == token and pub.state in (PublicationState.PUBLISHING, PublicationState.UNKNOWN)

        adapter = get_adapter(channel.platform)
        try:
            account = await refresh_if_needed(db, channel)
            creds = usable_credentials(account)
            payload = _adapter_payload(pub)
            if pub.platform_job_id:
                result = await adapter.await_publish(creds, JobHandle(job_id=pub.platform_job_id),
                                                     payload, before_publish=before_publish)
                job_id = pub.platform_job_id
                published = result.status == "published"
            else:
                result = await adapter.begin_publish(creds, payload, before_publish=before_publish)
                job_id = result.job_id
                published = bool(result.post_id)
            if not await owns_result():
                return
            pub.platform_job_id = job_id
            pub.dispatch_started_at = pub.claim_token = None
            pub.last_error = None
            if published:
                pub.platform_post_id, pub.platform_post_url = result.post_id, result.post_url
                pub.due_at = None
                await _transition(db, pub, PublicationState.PUBLISHED)
            else:
                if pub.state == PublicationState.UNKNOWN:
                    await _transition(db, pub, PublicationState.PUBLISHING)
                pub.due_at = func.now() + POLL_INTERVAL
        except Exception as exc:
            if not await owns_result():
                return
            uncertain = not isinstance(exc, PlatformError) or exc.kind in (
                PlatformErrorKind.TRANSIENT, PlatformErrorKind.UNKNOWN,
            )
            if pub.dispatch_started_at is not None and uncertain:
                await _mark_unknown(db, pub)
            elif isinstance(exc, PlatformError):
                if pub.state == PublicationState.UNKNOWN:
                    await _transition(db, pub, PublicationState.PUBLISHING)
                pub.dispatch_started_at = pub.claim_token = None
                await _handle_platform_error(db, pub, channel, exc)
            else:
                raise
        await db.commit()


async def _handle_platform_error(
    db: AsyncSession,
    pub: Publication,
    channel: ChannelAccount,
    error: PlatformError,
) -> None:
    """Map a unified platform error onto the state machine (§7)."""
    detail = str(error)[:500]
    now = datetime.now(UTC)

    if error.kind == PlatformErrorKind.TOKEN:
        # Refresh once inline and retry immediately; if the refresh itself is
        # rejected the grant is dead → mark the channel expired. Per §7 this
        # is not counted as a publish failure (UI shows "重新连接").
        try:
            account = await refresh_if_needed(db, channel, force=True)
            creds = usable_credentials(account)
            if not creds.get("access_token"):
                raise PlatformError(PlatformErrorKind.TOKEN, "no access token")
        except PlatformError:
            channel.status = ChannelAccountStatus.EXPIRED
            db.add(channel)
            if pub.platform_job_id:
                await _mark_unknown(db, pub)
            else:
                await _transition(db, pub, PublicationState.FAILED, error="channel_token_expired")
            return
        await _transition(db, pub, PublicationState.SCHEDULED)
        pub.due_at = now
        return

    if error.kind == PlatformErrorKind.PUBLISH_FAILED:
        pub.platform_job_id = None
        await _transition(db, pub, PublicationState.FAILED, error=detail)
        return
    if error.kind in (PlatformErrorKind.VALIDATION, PlatformErrorKind.CONTENT_POLICY):
        if pub.platform_job_id and channel.platform.value == "tiktok":
            # Failure to read status does not prove the remote post failed.
            await _mark_unknown(db, pub)
            return
        # Deterministic — retrying changes nothing.
        await _transition(db, pub, PublicationState.FAILED, error=detail)
        return

    # rate_limit / transient / unknown → back off and retry.
    if pub.platform_job_id is not None:
        # Poll phase: the platform already holds our job — a wobble here says
        # nothing about the content. Park at the poll cadence without
        # consuming the begin-phase backoff budget; ``_MAX_CLAIMS`` in
        # ``process_publication`` remains the eventual timeout.
        await _transition(db, pub, PublicationState.SCHEDULED)
        pub.due_at = now + POLL_INTERVAL
        pub.last_error = detail
        return
    if pub.attempt_count >= len(_BACKOFF_SECONDS) + 1:
        await _transition(db, pub, PublicationState.FAILED, error=detail)
        return
    delay = _BACKOFF_SECONDS[min(pub.attempt_count - 1, len(_BACKOFF_SECONDS) - 1)]
    await _transition(db, pub, PublicationState.SCHEDULED)
    pub.due_at = now + timedelta(seconds=delay)
    pub.last_error = detail


async def reconcile_publication(pub_id: UUID, *, evidence: str, post_id: str | None) -> bool:
    """Record an operator's confirmed platform outcome, with no external publishing call."""
    evidence = evidence.strip()
    if not evidence or len(evidence) > 1000 or (post_id is not None and not 0 < len(post_id.strip()) <= 512):
        raise ValueError("A concrete platform evidence reference and a valid outcome are required")
    async with AsyncSessionLocal() as db:
        pub = await db.get(Publication, pub_id, with_for_update=True)
        if pub is None or pub.state != PublicationState.UNKNOWN:
            return False
        pub.reconciliation = {
            "confirmed_at": datetime.now(UTC).isoformat(), "evidence": evidence,
            "outcome": "published" if post_id else "confirmed_not_published",
            "claim_token": str(pub.claim_token) if pub.claim_token else None,
            "platform_job_id": pub.platform_job_id,
        }
        pub.dispatch_started_at = pub.claim_token = pub.due_at = None
        pub.platform_post_id = post_id
        if post_id:
            pub.last_error = None
            await _transition(db, pub, PublicationState.PUBLISHED)
        else:
            pub.platform_job_id = None
            await _transition(db, pub, PublicationState.FAILED, error="confirmed_not_published")
        await db.commit()
        return True


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Record a verified external publication outcome.")
    parser.add_argument("publication", type=UUID)
    parser.add_argument("--evidence", required=True, help="Platform case or immutable evidence reference")
    outcome = parser.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--post-id")
    outcome.add_argument("--confirmed-not-published", action="store_true",
                         help="Original sender is stopped and the platform confirmed the request cannot publish")
    args = parser.parse_args()
    changed = asyncio.run(reconcile_publication(args.publication, evidence=args.evidence, post_id=args.post_id))
    print("Recorded." if changed else "No unresolved publication.")
