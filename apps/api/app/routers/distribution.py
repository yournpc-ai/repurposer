"""Distribution router — channels (OAuth) + publications (DISTRIBUTION.md §10.2).

Routes mirror the state machine: one explicit verb endpoint per transition.
Routers only validate params and call service functions; state transitions,
idempotency, and ``due_at`` math live in ``services.distribution``.

Mounted at ``/api/v1`` (URL names the resource, not the module, §1.1):
``/channels/*`` and ``/publications/*``.
"""

from typing import Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import DBDep, get_current_user_required
from app.models.schemas import (
    ChannelAccountResponse,
    ChannelPlatform,
    PublicationResponse,
    PublicationState,
)
from app.models.tables import User
from app.services import distribution as dist
from app.services.distribution.adapters.base import PlatformError
from app.services.project_context import get_project_for_user

router = APIRouter()


class OAuthUrlResponse(BaseModel):
    url: str


class CreatePublicationRequest(BaseModel):
    """One publication per channel (§13: no blast-marketing multi-post)."""

    output_id: UUID
    channel_account_id: UUID
    # Dialog edits — edit = confirm (ADR-027). Keys merge over the prefilled
    # snapshot (title / caption / hashtags / cover_image_url).
    overrides: dict[str, Any] | None = None
    # One per dialog publish intent; retries reuse it → same row (§7).
    client_key: str | None = Field(default=None, max_length=128)


_ERROR_STATUS = {
    "output_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_configured": status.HTTP_404_NOT_FOUND,
    "publication_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_state": status.HTTP_400_BAD_REQUEST,
    "illegal_transition": status.HTTP_409_CONFLICT,
    "already_published": status.HTTP_409_CONFLICT,
    "channel_not_active": status.HTTP_409_CONFLICT,
}


def _raise_domain(e: dist.DistributionError) -> NoReturn:
    raise HTTPException(
        status_code=_ERROR_STATUS.get(e.code, status.HTTP_400_BAD_REQUEST),
        detail=e.code,
    ) from e


def _web_redirect(params: str) -> RedirectResponse:
    base = settings.web_public_url.rstrip("/")
    return RedirectResponse(url=f"{base}/settings?{params}", status_code=302)


# ─────────────────────────────────────────────────────────────────────────────
# Channels
# ─────────────────────────────────────────────────────────────────────────────


class PlatformAvailability(BaseModel):
    platform: ChannelPlatform
    configured: bool


@router.get("/channels/platforms", response_model=list[PlatformAvailability])
async def list_platforms(
    user: User = Depends(get_current_user_required),
) -> list[PlatformAvailability]:
    """Per-platform presence-gating for the UI ("coming soon" state, §4.1)."""
    return [
        PlatformAvailability(platform=p, configured=dist.is_configured(p))
        for p in ChannelPlatform
    ]


@router.get("/channels/{platform}/oauth-url", response_model=OAuthUrlResponse)
async def channel_oauth_url(
    platform: ChannelPlatform,
    user: User = Depends(get_current_user_required),
) -> OAuthUrlResponse:
    try:
        return OAuthUrlResponse(url=dist.connect_start(platform, user.id))
    except dist.DistributionError as e:
        _raise_domain(e)


@router.get("/channels/{platform}/callback")
async def channel_oauth_callback(
    platform: ChannelPlatform,
    db: DBDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Provider redirect target — no auth header; identity comes from the
    HMAC-signed ``state`` nonce. Always redirects back to the web app."""
    if error or not code or not state:
        return _web_redirect(f"error={error or 'missing_params'}&platform={platform.value}")
    try:
        await dist.connect_finish(db, platform, code=code, state=state)
        await db.commit()
    except dist.DistributionError as e:
        return _web_redirect(f"error={e.code}&platform={platform.value}")
    except PlatformError:
        return _web_redirect(f"error=platform_error&platform={platform.value}")
    return _web_redirect(f"connected={platform.value}")


@router.get("/channels", response_model=list[ChannelAccountResponse])
async def list_channels(
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> list:
    return await dist.list_channels(db, user.id)


@router.delete("/channels/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_channel(
    account_id: UUID,
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> None:
    try:
        await dist.disconnect(db, account_id, user.id)
        await db.commit()
    except dist.DistributionError as e:
        _raise_domain(e)


# ─────────────────────────────────────────────────────────────────────────────
# Publications
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/publications",
    response_model=PublicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_publication(
    project_id: UUID,
    body: CreatePublicationRequest,
    db: DBDep,
    user: User = Depends(get_current_user_required),
):
    """Create a publish order — P1 personal flow is born ``scheduled``
    (publish now); the worker picks it up on the next tick."""
    await get_project_for_user(db, project_id, user.id)
    try:
        pub = await dist.create_publication(
            db,
            user_id=user.id,
            project_id=project_id,
            output_id=body.output_id,
            channel_account_id=body.channel_account_id,
            overrides=body.overrides,
            client_key=body.client_key,
        )
        await db.commit()
        return pub
    except dist.DistributionError as e:
        _raise_domain(e)


@router.post("/publications/{pub_id}/cancel", response_model=PublicationResponse)
async def cancel_publication(
    pub_id: UUID,
    db: DBDep,
    user: User = Depends(get_current_user_required),
):
    try:
        pub = await dist.cancel_publication(db, pub_id, user.id)
        await db.commit()
        return pub
    except dist.DistributionError as e:
        _raise_domain(e)


@router.post("/publications/{pub_id}/retry", response_model=PublicationResponse)
async def retry_publication(
    pub_id: UUID,
    db: DBDep,
    user: User = Depends(get_current_user_required),
):
    try:
        pub = await dist.retry_publication(db, pub_id, user.id)
        await db.commit()
        return pub
    except dist.DistributionError as e:
        _raise_domain(e)


@router.get("/publications", response_model=list[PublicationResponse])
async def list_publications(
    db: DBDep,
    user: User = Depends(get_current_user_required),
    state: PublicationState | None = None,
    project_id: UUID | None = None,
    limit: int = Query(default=100, le=500),
):
    return await dist.list_publications(
        db, user.id, state=state, project_id=project_id, limit=limit
    )


@router.get("/publications/{pub_id}", response_model=PublicationResponse)
async def get_publication(
    pub_id: UUID,
    db: DBDep,
    user: User = Depends(get_current_user_required),
):
    try:
        return await dist.get_publication(db, pub_id, user.id)
    except dist.DistributionError as e:
        _raise_domain(e)
