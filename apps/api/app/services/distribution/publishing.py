"""Worker-side publishing (DISTRIBUTION.md §6/§7/§10.3).

The publication table is the worker's **fourth claim source** (alongside
assets / plan nodes / renders), polled *first* each tick — a scheduled publish
is a time promise to the user and must not queue behind ASR or renders.

Claim predicate is ``due_at`` alone (§6): ``scheduled AND due_at <= now``
starts a publish attempt (→ ``publishing``); ``publishing AND due_at <= now``
is a poll lease (``due_at`` pushed forward so no other worker double-claims).
Crash recovery needs no reaper for the common path — an orphaned row's lease
simply expires and it is claimed again; ``platform_job_id`` is the
reconciliation anchor for uncertain outcomes (§7: 禁盲重试).

``attempt_count`` counts worker claims (attempts + polls); polls cap at
``_MAX_CLAIMS`` so a platform stuck in "processing" cannot spin forever.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.schemas import ChannelAccountStatus, PublicationState
from app.models.tables import ChannelAccount, Publication
from app.services.distribution.adapters import get_adapter
from app.services.distribution.adapters.base import (
    JobHandle,
    PlatformError,
    PlatformErrorKind,
)
from app.services.distribution.channels import refresh_if_needed, usable_credentials
from app.services.distribution.core import _transition
from app.services.storage import resolve_stored_url

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


async def claim_due_publication(db: AsyncSession) -> UUID | None:
    """Claim one due publication row. Returns its id, or None.

    Single query ordered by ``due_at`` (the oldest promise first). A
    ``scheduled`` row starts a publish attempt (→ ``publishing`` with a
    begin-length lease); a ``publishing`` row is a poll continuation (short
    lease). Both bump ``attempt_count``.
    """
    now = datetime.now(UTC)
    pub = (
        await db.execute(
            select(Publication)
            .where(
                Publication.state.in_(
                    [PublicationState.SCHEDULED, PublicationState.PUBLISHING]
                ),
                Publication.due_at <= now,
            )
            .order_by(Publication.due_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).scalar_one_or_none()
    if pub is None:
        return None
    if pub.state == PublicationState.SCHEDULED:
        await _transition(db, pub, PublicationState.PUBLISHING)
        pub.due_at = now + BEGIN_LEASE
    else:
        pub.due_at = now + POLL_INTERVAL  # poll lease
    pub.attempt_count += 1
    await db.commit()
    return pub.id


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


async def process_publication(pub_id: UUID) -> None:
    """Execute one claimed publication: begin publish or poll the job."""
    async with AsyncSessionLocal() as db:
        pub = await db.get(Publication, pub_id)
        if pub is None or pub.state != PublicationState.PUBLISHING:
            return
        if pub.attempt_count > _MAX_CLAIMS:
            await _transition(db, pub, PublicationState.FAILED, error="publish_timeout")
            await db.commit()
            return

        channel = (
            await db.get(ChannelAccount, pub.channel_account_id)
            if pub.channel_account_id
            else None
        )
        if channel is None:
            await _transition(db, pub, PublicationState.FAILED, error="channel_disconnected")
            await db.commit()
            return
        if channel.status != ChannelAccountStatus.ACTIVE:
            await _transition(
                db, pub, PublicationState.FAILED, error="channel_token_expired"
            )
            await db.commit()
            return

        adapter = get_adapter(channel.platform)
        payload = _adapter_payload(pub)
        now = datetime.now(UTC)
        try:
            account = await refresh_if_needed(db, channel)
            creds = usable_credentials(account)
            if pub.platform_job_id is None:
                handle = await adapter.begin_publish(creds, payload)
                # Persist the job anchor immediately — a crash after this
                # point reconciles via await_publish, never a blind re-post.
                pub.platform_job_id = handle.job_id
                if handle.post_id:
                    pub.platform_post_id = handle.post_id
                    pub.platform_post_url = handle.post_url
                    await _transition(db, pub, PublicationState.PUBLISHED)
                else:
                    pub.due_at = now + POLL_INTERVAL
            else:
                result = await adapter.await_publish(
                    creds, JobHandle(job_id=pub.platform_job_id), payload
                )
                if result.status == "published":
                    pub.platform_post_id = result.post_id
                    pub.platform_post_url = result.post_url
                    await _transition(db, pub, PublicationState.PUBLISHED)
                else:
                    pub.due_at = now + POLL_INTERVAL
            await db.commit()
            logger.info(
                "publication_processed",
                publication_id=str(pub.id),
                state=pub.state.value,
                job_id=pub.platform_job_id,
            )
        except PlatformError as e:
            await _handle_platform_error(db, pub, channel, e)
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
            await _transition(db, pub, PublicationState.FAILED, error="channel_token_expired")
            return
        await _transition(db, pub, PublicationState.SCHEDULED)
        pub.due_at = now
        return

    if error.kind in (PlatformErrorKind.VALIDATION, PlatformErrorKind.CONTENT_POLICY):
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
