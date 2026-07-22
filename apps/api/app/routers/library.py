"""Library router: aggregates all user uploads and outputs."""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user_required
from app.models.schemas import (
    AssetResponse,
    LibraryItemResponse,
    LibraryItemType,
)
from app.models.tables import Asset, Output, Project, User
from app.services.outputs import visible_outputs_stmt
from app.services.storage import resolve_stored_url, stream_url

router = APIRouter()


_DERIVATIVE_TITLES = {
    "post": "Social post",
    "quotes": "Quotes",
    "article": "Article",
    "carousel": "Carousel",
}


def _output_preview(output: Output) -> str | None:
    payload = output.payload or {}
    if output.type == "post":
        return (payload.get("content") or "")[:200]
    if output.type == "quotes":
        quotes = payload.get("quotes") or []
        if quotes:
            return (quotes[0].get("quote") or "")[:200]
        return None
    if output.type == "article":
        return (payload.get("title") or "")[:200]
    return None


def _upload_title(a: AssetResponse) -> str:
    if a.file_url:
        return a.file_url.split("/")[-1]
    return "Upload"


@router.get("", response_model=list[LibraryItemResponse])
async def list_library(
    type: LibraryItemType | None = None,  # noqa: A002
    db: DBDep = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user_required),
) -> list[LibraryItemResponse]:
    """Return the current user's uploads and outputs as a flat timeline."""
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

    if type is None or type != LibraryItemType.UPLOAD:
        stmt = visible_outputs_stmt().where(Output.project_id.in_(project_ids_sub))
        if type is not None:
            stmt = stmt.where(Output.type == type.value)
        result = await db.execute(stmt.order_by(Output.created_at.desc()))
        for output in result.scalars().all():
            payload = output.payload or {}
            publishing = output.publishing or {}
            files = output.files or {}
            if output.type == "clip":
                items.append(
                    LibraryItemResponse(
                        id=output.id,
                        type=LibraryItemType.CLIP,
                        title=publishing.get("title") or payload.get("hook") or "Clip",
                        project_id=output.project_id,
                        created_at=output.created_at,
                        preview=(
                            f"{payload['duration']}s" if payload.get("duration") else None
                        ),
                        download_url=resolve_stored_url(files.get("video")),
                    )
                )
            else:
                items.append(
                    LibraryItemResponse(
                        id=output.id,
                        type=LibraryItemType(output.type),
                        title=_DERIVATIVE_TITLES.get(output.type, "Output"),
                        project_id=output.project_id,
                        created_at=output.created_at,
                        preview=_output_preview(output),
                        download_url=(
                            resolve_stored_url(files.get("image"))
                            if output.type == "quotes"
                            else None
                        ),
                    )
                )

    # Flattened timeline: newest first.
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items
