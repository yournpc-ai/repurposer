"""Distribution service — sole writer of publication state (DISTRIBUTION.md §3).

P1 scope (2026-07-23 trimmed): personal flow, born-``scheduled`` publish orders
(create = publish now), LinkedIn + TikTok. The institutional path
(``draft``/``pending_review``/``approved`` + ``publication_events`` audit
table) is P2 — the state enum already carries it so the migration never
changes, but no P1 code path enters those states.

Rules (MODULE_ARCHITECTURE.md §4 — Distribution owns these tables):
- ``_transition`` is the ONLY state writer; routers / other modules never
  touch ``state``.
- ``payload`` is a frozen snapshot (creation time) — later output edits never
  sync into it; post-disconnect history stays readable via the channel
  snapshot inside it.
- Credentials are Fernet-encrypted at rest (ADR-031); only this module
  encrypts/decrypts them.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.schemas import ChannelAccountStatus, PublicationState
from app.models.tables import ChannelAccount, Output, Publication

logger = structlog.get_logger()


class DistributionError(Exception):
    """Domain error carrying a stable code for the API layer to translate."""

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        super().__init__(detail or code)


# ─────────────────────────────────────────────────────────────────────────────
# State machine (§3.3). published/cancelled are terminal; failed is
# user-resolvable (retry → scheduled, or cancel).
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED: dict[PublicationState, set[PublicationState]] = {
    PublicationState.DRAFT: {PublicationState.SCHEDULED, PublicationState.CANCELLED},
    PublicationState.SCHEDULED: {PublicationState.PUBLISHING, PublicationState.CANCELLED},
    PublicationState.PUBLISHING: {
        PublicationState.PUBLISHED,
        PublicationState.FAILED,
        # Backoff re-entry: a retryable platform failure parks the order back
        # into SCHEDULED with ``due_at`` = next attempt time.
        PublicationState.SCHEDULED,
        PublicationState.CANCELLED,
    },
    PublicationState.FAILED: {PublicationState.SCHEDULED, PublicationState.CANCELLED},
    # P2 institutional path (ADR-027) — declared, unreachable in P1.
    PublicationState.PENDING_REVIEW: {
        PublicationState.APPROVED,
        PublicationState.DRAFT,
        PublicationState.CANCELLED,
    },
    PublicationState.APPROVED: {PublicationState.SCHEDULED, PublicationState.CANCELLED},
}

TERMINAL_STATES = {PublicationState.PUBLISHED, PublicationState.CANCELLED}


async def _transition(
    db: AsyncSession,
    pub: Publication,
    to_state: PublicationState,
    *,
    error: str | None = None,
) -> Publication:
    """The only ``state`` writer. P2 will additionally append publication_events."""
    allowed = _ALLOWED.get(pub.state, set())
    if to_state not in allowed:
        raise DistributionError(
            "illegal_transition", f"{pub.state.value} -> {to_state.value}"
        )
    pub.state = to_state
    if error is not None:
        pub.last_error = error
    if to_state == PublicationState.PUBLISHED:
        pub.published_at = datetime.now(UTC)
    await db.flush()
    logger.info(
        "publication_transition",
        publication_id=str(pub.id),
        to_state=to_state.value,
    )
    return pub


# ─────────────────────────────────────────────────────────────────────────────
# Credential encryption (ADR-031: Fernet + env key; empty key = plaintext dev)
# ─────────────────────────────────────────────────────────────────────────────

_SENSITIVE_CREDENTIAL_KEYS = ("access_token", "refresh_token", "secret")


def _fernet() -> Fernet | None:
    key = settings.channel_credentials_key
    return Fernet(key.encode()) if key else None


def encrypt_credentials(creds: dict[str, Any]) -> dict[str, Any]:
    """Fernet-encrypt sensitive values for ``credentials_enc`` storage."""
    f = _fernet()
    if f is None:
        logger.warning(
            "channel_credentials_plaintext",
            detail="CHANNEL_CREDENTIALS_KEY unset — storing tokens unencrypted (dev only)",
        )
        return dict(creds)
    out = dict(creds)
    for k in _SENSITIVE_CREDENTIAL_KEYS:
        v = out.get(k)
        if isinstance(v, str) and v:
            out[k] = f.encrypt(v.encode()).decode()
    return out


def decrypt_credentials(enc: dict[str, Any]) -> dict[str, Any]:
    """Inverse of ``encrypt_credentials``; tolerates plaintext dev rows."""
    f = _fernet()
    if f is None:
        return dict(enc)
    out = dict(enc)
    for k in _SENSITIVE_CREDENTIAL_KEYS:
        v = out.get(k)
        if isinstance(v, str) and v:
            try:
                out[k] = f.decrypt(v.encode()).decode()
            except InvalidToken:
                # Pre-encryption dev row (or key rotated) — pass through.
                logger.warning("channel_credential_decrypt_failed", key=k)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Publication lifecycle
# ─────────────────────────────────────────────────────────────────────────────


def _classify_ai_disclosure(output: Output) -> bool:
    """ADR-026 classifier: synthetic tracks → disclose; pure edits exempt.

    - ``provenance=generated`` (virtual outputs, ADR-029/030) → True
    - clip-spec carries a dub track (voice clone) → True
    - pure cut/subtitle edits of real footage → False (exempt); AI music does
      not flip the flag (licensed generation; main track remains real).
    """
    if output.provenance == "generated":
        return True
    spec = output.render_spec or {}
    return bool(spec.get("dub"))


def _idempotency_key(
    output_id: UUID,
    channel_account_id: UUID,
    scheduled_at: datetime,
    client_key: str | None,
) -> str:
    """DB-level dedup: double-click / refresh / resubmit never creates two rows.

    Two shapes:
    - ``client_key`` present (immediate publish): the dialog generates one key
      per publish intent; retries reuse it → same row. Server-generated
      ``scheduled_at = now()`` would differ per call and never dedup.
    - Absent (scheduled publish): target + channel + user-chosen time hash —
      the time is stable across retries by construction.
    """
    if client_key:
        return hashlib.sha256(f"client:{channel_account_id}:{client_key}".encode()).hexdigest()
    raw = f"{output_id}:{channel_account_id}:{scheduled_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_payload(
    output: Output,
    channel: ChannelAccount,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    """Frozen publish snapshot prefilled from the output's publishing suite.

    Includes a channel snapshot so history stays readable after disconnect.
    ``overrides`` are the user's dialog edits (edit = confirm, ADR-027).
    """
    publishing = output.publishing or {}
    files = output.files or {}
    payload: dict[str, Any] = {
        "title": publishing.get("title") or "",
        "caption": publishing.get("description") or "",
        "hashtags": publishing.get("hashtags") or [],
        "cover_image_url": publishing.get("cover_image_url"),
        "media": {
            "video": files.get("video"),
            "srt": files.get("srt"),
            "image": files.get("image"),
        },
        "output_type": output.type,
        "language": output.language,
        "channel": {
            "platform": channel.platform.value,
            "platform_user_id": channel.platform_user_id,
            "display_name": channel.display_name,
        },
    }
    if overrides:
        payload.update(overrides)
    return payload


async def create_publication(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID,
    output_id: UUID,
    channel_account_id: UUID,
    overrides: dict[str, Any] | None = None,
    when: datetime | None = None,
    client_key: str | None = None,
) -> Publication:
    """Create a publish order — P1 personal flow is born SCHEDULED (publish now).

    Idempotent: pass ``client_key`` (one per dialog publish intent) for
    immediate publishes; scheduled publishes dedup on (output, channel, when).
    A duplicate submit returns the existing row instead of creating another.
    """
    output = await db.get(Output, output_id)
    if output is None or output.project_id != project_id:
        raise DistributionError("output_not_found")
    channel = await db.get(ChannelAccount, channel_account_id)
    if channel is None or channel.user_id != user_id:
        raise DistributionError("channel_not_found")
    if channel.status != ChannelAccountStatus.ACTIVE:
        raise DistributionError("channel_not_active", channel.status.value)

    scheduled_at = when or datetime.now(UTC)
    key = _idempotency_key(output_id, channel_account_id, scheduled_at, client_key)
    existing = (
        await db.execute(
            select(Publication).where(Publication.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    pub = Publication(
        user_id=user_id,
        project_id=project_id,
        output_id=output_id,
        channel_account_id=channel_account_id,
        payload=_build_payload(output, channel, overrides),
        ai_disclosure=_classify_ai_disclosure(output),
        state=PublicationState.SCHEDULED,
        scheduled_at=scheduled_at,
        due_at=scheduled_at,
        idempotency_key=key,
    )
    db.add(pub)
    await db.flush()
    logger.info(
        "publication_created",
        publication_id=str(pub.id),
        output_id=str(output_id),
        platform=channel.platform.value,
        ai_disclosure=pub.ai_disclosure,
    )
    return pub


async def cancel_publication(
    db: AsyncSession, pub_id: UUID, user_id: UUID
) -> Publication:
    """Cancel any pre-published order (published is terminal, §3.3)."""
    pub = await db.get(Publication, pub_id)
    if pub is None or pub.user_id != user_id:
        raise DistributionError("publication_not_found")
    if pub.state == PublicationState.PUBLISHED:
        raise DistributionError("already_published")
    return await _transition(db, pub, PublicationState.CANCELLED)


async def get_publication(db: AsyncSession, pub_id: UUID, user_id: UUID) -> Publication:
    pub = await db.get(Publication, pub_id)
    if pub is None or pub.user_id != user_id:
        raise DistributionError("publication_not_found")
    return pub


async def list_publications(
    db: AsyncSession,
    user_id: UUID,
    *,
    state: PublicationState | None = None,
    project_id: UUID | None = None,
    limit: int = 100,
) -> list[Publication]:
    """Read-only listing (records page). All modules may read; only this
    service writes state."""
    stmt = (
        select(Publication)
        .where(Publication.user_id == user_id)
        .order_by(Publication.created_at.desc())
        .limit(limit)
    )
    if state is not None:
        stmt = stmt.where(Publication.state == state)
    if project_id is not None:
        stmt = stmt.where(Publication.project_id == project_id)
    return list((await db.execute(stmt)).scalars().all())
