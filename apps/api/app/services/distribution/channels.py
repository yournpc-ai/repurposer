"""Channel connection lifecycle (DISTRIBUTION.md §4, §10.3).

OAuth ``state`` is a stateless HMAC nonce (signed with ``jwt_secret_key``):
``base64url(json{uid, platform, nonce, exp}).base64url(hmac)`` — no table
needed, 10-minute expiry, CSRF-safe.

Credentials are Fernet-encrypted (ADR-031) by ``core.encrypt_credentials``
before touching ``credentials_enc``; only this module and ``publishing``
decrypt them.
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.schemas import ChannelAccountStatus, ChannelPlatform
from app.models.tables import ChannelAccount
from app.services.distribution.adapters import get_adapter
from app.services.distribution.adapters.base import PlatformAdapter
from app.services.distribution.core import (
    DistributionError,
    decrypt_credentials,
    encrypt_credentials,
)

logger = structlog.get_logger()

_STATE_TTL_SECONDS = 600
_REFRESH_MARGIN = timedelta(minutes=5)


def redirect_uri(platform: ChannelPlatform) -> str:
    """Derived from ``api_public_url`` — never env-configured (§4.1)."""
    base = settings.api_public_url.rstrip("/")
    return f"{base}/api/v1/channels/{platform.value}/callback"


# ─────────────────────────────────────────────────────────────────────────────
# OAuth state nonce (stateless, HMAC-signed)
# ─────────────────────────────────────────────────────────────────────────────


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _sign(payload_b64: str) -> str:
    sig = hmac.new(
        settings.jwt_secret_key.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    return _b64e(sig)


def issue_oauth_state(user_id: UUID, platform: ChannelPlatform) -> str:
    body = {
        "uid": str(user_id),
        "platform": platform.value,
        "nonce": secrets.token_urlsafe(16),
        "exp": int((datetime.now(UTC) + timedelta(seconds=_STATE_TTL_SECONDS)).timestamp()),
    }
    payload_b64 = _b64e(json.dumps(body, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_oauth_state(state: str, platform: ChannelPlatform) -> UUID:
    """Return the initiating user id, or raise ``invalid_state``."""
    try:
        payload_b64, sig = state.split(".", 1)
        if not hmac.compare_digest(sig, _sign(payload_b64)):
            raise ValueError("bad signature")
        body = json.loads(_b64d(payload_b64))
        if body["platform"] != platform.value:
            raise ValueError("platform mismatch")
        if int(body["exp"]) < int(datetime.now(UTC).timestamp()):
            raise ValueError("expired")
        return UUID(body["uid"])
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise DistributionError("invalid_state", str(e)) from e


# ─────────────────────────────────────────────────────────────────────────────
# Channel lifecycle
# ─────────────────────────────────────────────────────────────────────────────


def _configured(platform: ChannelPlatform) -> None:
    """Presence-gating (§4.1): an unconfigured channel is a 404, not a flag."""
    configured = {
        ChannelPlatform.LINKEDIN: bool(settings.linkedin_client_id),
        ChannelPlatform.TIKTOK: bool(settings.tiktok_client_key),
    }[platform]
    if not configured:
        raise DistributionError("channel_not_configured", platform.value)


def connect_start(platform: ChannelPlatform, user_id: UUID) -> str:
    """Build the provider authorization URL with a CSRF state nonce."""
    _configured(platform)
    adapter: PlatformAdapter = get_adapter(platform)
    return adapter.oauth_url(
        redirect_uri=redirect_uri(platform),
        state=issue_oauth_state(user_id, platform),
    )


async def connect_finish(
    db: AsyncSession, platform: ChannelPlatform, *, code: str, state: str
) -> ChannelAccount:
    """Exchange the code, fetch the profile, upsert the channel account."""
    user_id = verify_oauth_state(state, platform)
    adapter = get_adapter(platform)
    payload = await adapter.exchange_code(code=code, redirect_uri=redirect_uri(platform))

    existing = (
        await db.execute(
            select(ChannelAccount).where(
                ChannelAccount.user_id == user_id,
                ChannelAccount.platform == platform,
                ChannelAccount.platform_user_id == payload.platform_user_id,
            )
        )
    ).scalar_one_or_none()

    account = existing or ChannelAccount(user_id=user_id, platform=platform)
    account.platform_user_id = payload.platform_user_id
    account.display_name = payload.display_name
    account.avatar_url = payload.avatar_url
    account.scopes = payload.scopes
    account.credentials_enc = encrypt_credentials(payload.credentials)
    account.token_expires_at = payload.token_expires_at
    account.status = ChannelAccountStatus.ACTIVE
    account.last_refreshed_at = datetime.now(UTC)
    db.add(account)
    await db.flush()
    logger.info(
        "channel_connected",
        platform=platform.value,
        account_id=str(account.id),
        user_id=str(user_id),
    )
    return account


async def list_channels(db: AsyncSession, user_id: UUID) -> list[ChannelAccount]:
    stmt = (
        select(ChannelAccount)
        .where(ChannelAccount.user_id == user_id)
        .order_by(ChannelAccount.created_at)
    )
    return list((await db.execute(stmt)).scalars().all())


async def disconnect(db: AsyncSession, account_id: UUID, user_id: UUID) -> None:
    """Delete the account row; publication history survives via payload's
    channel snapshot (``channel_account_id`` FK is ON DELETE SET NULL)."""
    account = await db.get(ChannelAccount, account_id)
    if account is None or account.user_id != user_id:
        raise DistributionError("channel_not_found")
    await db.execute(delete(ChannelAccount).where(ChannelAccount.id == account_id))
    await db.flush()
    logger.info("channel_disconnected", account_id=str(account_id))


async def refresh_if_needed(
    db: AsyncSession, account: ChannelAccount, *, force: bool = False
) -> ChannelAccount:
    """Refresh the access token when it expires within the safety margin.

    ``force=True`` refreshes regardless of expiry — used after the platform
    rejected a supposedly-valid token (§7: refresh once, then give up).
    """
    if not force and (
        # Unknown expiry (None) = assume valid; never force-refresh blindly.
        account.token_expires_at is None
        or account.token_expires_at > datetime.now(UTC) + _REFRESH_MARGIN
    ):
        return account
    adapter = get_adapter(account.platform)
    credentials = decrypt_credentials(account.credentials_enc)
    payload = await adapter.refresh(credentials)
    account.credentials_enc = encrypt_credentials(payload.credentials)
    account.token_expires_at = payload.token_expires_at
    account.last_refreshed_at = datetime.now(UTC)
    account.status = ChannelAccountStatus.ACTIVE
    db.add(account)
    await db.flush()
    logger.info("channel_token_refreshed", account_id=str(account.id))
    return account


def usable_credentials(account: ChannelAccount) -> dict:
    """Decrypted token bundle with ``platform_user_id`` injected for adapters."""
    creds = decrypt_credentials(account.credentials_enc)
    creds["platform_user_id"] = account.platform_user_id
    return creds
