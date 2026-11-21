"""Owned Output reads, playback, posters and deletion."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select

from app.config import settings
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import OutputPosterResponse, OutputResponse, PublicationState
from app.models.tables import Output, Project, Publication, User
from app.pipeline.output_posters import ensure_output_poster
from app.pipeline.outputs import (
    composition_version_number,
    output_to_response,
)
from app.platform.project_context import get_output_for_user
from app.providers.storage import delete_file, is_export_location, presign_download, matches_export_location, resolve_stored_url

router = APIRouter()


@router.get("/{output_id}", response_model=OutputResponse)
async def get_output(
    output_id: UUID, db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> OutputResponse:
    output = await get_output_for_user(
        db, output_id, UUID(str(current_user.id)) if current_user else None
    )
    return output_to_response(
        output, composition_version_number=await composition_version_number(db, output)
    )


@router.get("/{output_id}/playback")
async def playback(output_id: UUID, db: DBDep, response: Response, download: bool = False,
                   current_user: User = Depends(get_current_user_required)):
    output = await get_output_for_user(db, output_id, current_user.id)
    key = (output.files or {}).get("video")
    if not matches_export_location(key, current_user.id, output.project_id, output.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export file unavailable")
    response.headers["Cache-Control"] = "private, no-store"
    ttl = settings.private_playback_ttl_seconds
    url = await presign_download(key, ttl=ttl, filename=f"{output.id}.mp4" if download else None)
    return {"url": url, "expires_in": ttl}


@router.post("/{output_id}/poster", response_model=OutputPosterResponse)
async def ensure_poster(
    output_id: UUID, db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> OutputPosterResponse:
    output = await get_output_for_user(db, output_id, UUID(str(current_user.id)))
    video_key = (output.files or {}).get("video")
    if is_export_location(video_key) and not matches_export_location(video_key, current_user.id, output.project_id, output.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export file unavailable")
    try:
        key = await ensure_output_poster(output)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    poster_url = await presign_download(key) if is_export_location(key) else resolve_stored_url(key)
    if poster_url is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Poster URL could not be resolved")
    return OutputPosterResponse(output_id=output.id, poster_url=poster_url)


@router.delete("/{output_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output(
    output_id: UUID, db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    output = await get_output_for_user(db, output_id, current_user.id)
    # Admission for a publication takes these locks in the same order.
    await db.scalar(select(Project.id).where(Project.id == output.project_id).with_for_update(read=True, key_share=True))
    output = await db.get(Output, output_id, populate_existing=True, with_for_update=True)
    if output is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output not found")
    pending = await db.scalar(select(Publication.id).where(
        Publication.output_id == output.id,
        Publication.state.in_((PublicationState.SCHEDULED, PublicationState.PUBLISHING, PublicationState.UNKNOWN)),
    ).limit(1))
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This video has a scheduled publication or a pending platform result.")
    files = output.files or {}
    keys = (files.get("video"), files.get("image"), (output.publishing or {}).get("cover_image_url"))
    await db.execute(delete(Publication).where(Publication.output_id == output.id))
    await db.delete(output)
    await db.commit()
    for key in keys:
        if key:
            await delete_file(key)
