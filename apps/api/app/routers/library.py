"""Library router: aggregates all user assets, clips, and derivatives."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user
from app.models.schemas import (
    AssetResponse,
    ClipResponse,
    DerivativeResponse,
    DerivativeType,
    LibraryItemResponse,
    LibraryItemType,
)
from app.models.tables import Asset, Clip, Derivative, Project, User
from app.services.storage import stream_url

router = APIRouter()


def _derivative_title(d: DerivativeResponse) -> str:
    if d.type == DerivativeType.LINKEDIN_POST:
        return "LinkedIn post"
    if d.type == DerivativeType.QUOTE_CARD:
        return "Quote card"
    if d.type == DerivativeType.SUMMARY:
        return "Summary"
    if d.type == DerivativeType.BLOG:
        return "Blog post"
    if d.type == DerivativeType.CAROUSEL:
        return "Carousel"
    return "Derivative"


def _derivative_preview(d: DerivativeResponse) -> str | None:
    content = d.content or {}
    if d.type == DerivativeType.LINKEDIN_POST:
        return content.get("content", "")[:200]
    if d.type == DerivativeType.QUOTE_CARD:
        quotes = content.get("quotes", [])
        if quotes:
            return quotes[0].get("quote", "")[:200]
        return None
    if d.type == DerivativeType.SUMMARY:
        return content.get("tldr", "")[:200]
    if d.type == DerivativeType.BLOG:
        return content.get("title", "")[:200]
    return None


def _derivative_download_url(d: DerivativeResponse) -> str | None:
    if d.type == DerivativeType.QUOTE_CARD:
        return d.image_url
    return None


def _upload_title(a: AssetResponse) -> str:
    if a.file_url:
        return a.file_url.split("/")[-1]
    return "Upload"


def _upload_type(a: AssetResponse) -> LibraryItemType:
    return LibraryItemType.UPLOAD


@router.get("", response_model=list[LibraryItemResponse])
async def list_library(
    type: LibraryItemType | None = None,  # noqa: A002
    db: DBDep = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user),
) -> list[LibraryItemResponse]:
    """Return the current user's assets, clips, and derivatives as a flat timeline."""
    db = db  # satisfy type checker when DBDep is optional
    project_ids_sub = select(Project.id).where(Project.user_id == current_user.id)

    items: list[LibraryItemResponse] = []

    if type is None or type == LibraryItemType.UPLOAD:
        result = await db.execute(
            select(Asset)
            .where(Asset.user_id == current_user.id, Asset.project_id.in_(project_ids_sub))
            .order_by(Asset.created_at.desc())
        )
        for asset in result.scalars().all():
            items.append(
                LibraryItemResponse(
                    id=asset.id,
                    type=LibraryItemType.UPLOAD,
                    title=_upload_title(asset),
                    project_id=asset.project_id,
                    created_at=asset.created_at,
                    preview=None,
                    download_url=stream_url(asset.file_url),
                )
            )

    if type is None or type == LibraryItemType.CLIP:
        result = await db.execute(
            select(Clip)
            .where(Clip.project_id.in_(project_ids_sub))
            .order_by(Clip.created_at.desc())
        )
        for clip in result.scalars().all():
            items.append(
                LibraryItemResponse(
                    id=clip.id,
                    type=LibraryItemType.CLIP,
                    title=clip.hook or "Clip",
                    project_id=clip.project_id,
                    created_at=clip.created_at,
                    preview=f"{clip.duration}s" if clip.duration else None,
                    download_url=clip.video_url,
                )
            )

    if type is None or type in {
        LibraryItemType.LINKEDIN,
        LibraryItemType.QUOTE,
        LibraryItemType.SUMMARY,
    }:
        type_filter: list[DerivativeType] = []
        if type == LibraryItemType.LINKEDIN:
            type_filter = [DerivativeType.LINKEDIN_POST]
        elif type == LibraryItemType.QUOTE:
            type_filter = [DerivativeType.QUOTE_CARD]
        elif type == LibraryItemType.SUMMARY:
            type_filter = [DerivativeType.SUMMARY]
        else:
            type_filter = [
                DerivativeType.LINKEDIN_POST,
                DerivativeType.QUOTE_CARD,
                DerivativeType.SUMMARY,
            ]

        result = await db.execute(
            select(Derivative)
            .where(
                Derivative.project_id.in_(project_ids_sub),
                Derivative.type.in_(type_filter),
            )
            .order_by(Derivative.created_at.desc())
        )
        for derivative in result.scalars().all():
            library_type = LibraryItemType.LINKEDIN
            if derivative.type == DerivativeType.QUOTE_CARD:
                library_type = LibraryItemType.QUOTE
            elif derivative.type == DerivativeType.SUMMARY:
                library_type = LibraryItemType.SUMMARY

            items.append(
                LibraryItemResponse(
                    id=derivative.id,
                    type=library_type,
                    title=_derivative_title(derivative),
                    project_id=derivative.project_id,
                    created_at=derivative.created_at,
                    preview=_derivative_preview(derivative),
                    download_url=_derivative_download_url(derivative),
                )
            )

    # Flattened timeline: newest first.
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items
