"""Platform adapter contract (DISTRIBUTION.md §10.1).

One adapter per platform; platform-specific quirks (LinkedIn's multi-step
video upload, TikTok's ``creator_info`` pre-check) stay inside the adapter and
never leak into the service layer. Publishing is two-phase — ``begin_publish``
returns a platform job handle the service persists immediately (the
reconciliation anchor after a crash), ``await_publish`` polls it.

Platform error codes are normalized into ``PlatformError.kind``; the service
layer only ever handles the unified kinds.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import wraps
from typing import Any, Protocol

import httpx


class PlatformErrorKind(StrEnum):
    """Unified error taxonomy the service layer switches on (§7)."""

    TOKEN = "token"  # 401 / invalid grant → refresh once, then mark channel expired
    RATE_LIMIT = "rate_limit"  # back off and retry
    CONTENT_POLICY = "content_policy"  # platform rejected content → fail, no retry
    VALIDATION = "validation"  # our payload is wrong for this platform → fail, no retry
    TRANSIENT = "transient"  # timeout / 5xx / uncertain → reconcile via job handle
    UNKNOWN = "unknown"


class PlatformError(Exception):
    """Adapter-raised error carrying a unified kind."""

    def __init__(self, kind: PlatformErrorKind, detail: str):
        self.kind = kind
        super().__init__(detail)


def normalize_network_errors(fn):
    """Translate httpx transport failures (timeout / connect / DNS) into
    ``PlatformError(TRANSIENT)`` so the service layer's backoff path sees
    them; without this they bypass error handling and only the claim lease
    bounds them. Apply to every public adapter method that does HTTP."""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except httpx.HTTPError as e:
            raise PlatformError(
                PlatformErrorKind.TRANSIENT, f"{fn.__qualname__}: {e}"
            ) from e

    return wrapper


@dataclass
class ChannelAccountPayload:
    """Result of an OAuth code exchange: profile + token bundle."""

    platform_user_id: str
    display_name: str
    avatar_url: str | None
    scopes: list[str]
    credentials: dict[str, Any]  # access_token / refresh_token / … (pre-encryption)
    token_expires_at: datetime | None


@dataclass
class JobHandle:
    """Platform-side publish job anchor, persisted as ``platform_job_id``."""

    job_id: str
    # Some platforms complete synchronously (e.g. LinkedIn text posts) — when
    # they do, the adapter fills these and the service skips polling entirely.
    post_id: str | None = None
    post_url: str | None = None


@dataclass
class PublishResult:
    """Outcome of one ``await_publish`` poll.

    Contract: a return value is always ``published`` or ``pending`` — every
    failure path raises ``PlatformError`` instead.
    """

    status: str  # "published" | "pending"
    post_id: str | None = None
    post_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(Protocol):
    """Per-platform OAuth + two-phase publish contract.

    The ``credentials`` dict passed to publish methods is the decrypted token
    bundle with ``platform_user_id`` injected by the service layer (adapters
    need it to build author/owner URNs without a DB dependency).
    """

    def oauth_url(self, *, redirect_uri: str, state: str) -> str: ...

    async def exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> ChannelAccountPayload: ...

    async def refresh(self, credentials: dict[str, Any]) -> ChannelAccountPayload: ...

    async def begin_publish(
        self, credentials: dict[str, Any], payload: dict[str, Any]
    ) -> JobHandle: ...

    async def await_publish(
        self, credentials: dict[str, Any], job: JobHandle, payload: dict[str, Any]
    ) -> PublishResult: ...
