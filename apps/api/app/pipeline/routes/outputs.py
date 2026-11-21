"""Owned video Output reads, playback posters, rendering and deletion.

Composition content changes belong to Chat's saved-version write door.
This route exposes only owned video media, rendering and recovery.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text

from app.config import settings
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import OutputPosterResponse, OutputResponse, RenderStatus
from app.models.tables import User
from app.pipeline.output_posters import ensure_output_poster
from app.pipeline.outputs import (
    composition_version_number,
    delete_outputs_fk_safe,
    output_to_response,
)
from app.platform.project_context import get_output_for_user
from app.providers.storage import delete_file, is_private_export, presign_download, private_export_key, resolve_stored_url

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
    if key != private_export_key(current_user.id, output.project_id, output.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Private export file unavailable")
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
    if is_private_export(video_key) and video_key != private_export_key(current_user.id, output.project_id, output.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Private export file unavailable")
    try:
        key = await ensure_output_poster(output)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    poster_url = await presign_download(key) if is_private_export(key) else resolve_stored_url(key)
    if poster_url is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Poster URL could not be resolved")
    return OutputPosterResponse(output_id=output.id, poster_url=poster_url)


@router.delete("/{output_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output(
    output_id: UUID, db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    output = await get_output_for_user(db, output_id, UUID(str(current_user.id)))
    files = output.files or {}
    for key in (files.get("video"), files.get("image")):
        await delete_file(key)
    await delete_file((output.publishing or {}).get("cover_image_url"))
    await delete_outputs_fk_safe(db, [output_id])
    await db.execute(
        text(
            "UPDATE workflow_steps SET status = 'skipped', updated_at = now() "
            "WHERE kind = 'render' AND status = 'pending' "
            "AND spec->>'output_id' = :oid"
        ), {"oid": str(output_id)},
    )
    await db.commit()


@router.post("/{output_id}/render", response_model=OutputResponse, status_code=status.HTTP_202_ACCEPTED)
async def render_output_endpoint(
    output_id: UUID, db: DBDep,
    current_user: User = Depends(get_current_user_required),
):
    output = await get_output_for_user(db, output_id, UUID(str(current_user.id)))
    from app.models.tables import ExportJob
    if await db.get(ExportJob, output.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A verified export is immutable")
    if output.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Archived Output is read-only")
    if output.type != "video":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This output cannot render")
    if output.render_status in (RenderStatus.PENDING, RenderStatus.RENDERING):
        return output
    if not output.render_spec:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Video has no render_spec")
    from app.pipeline.jobs import reset_output_render

    reset_output_render(output)
    await db.commit()
    await db.refresh(output)
    return output
