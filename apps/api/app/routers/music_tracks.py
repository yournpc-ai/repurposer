"""Music track library router: official-catalog metadata + personal uploads.

See ADR-022 in docs/DECISIONS.md. This is a management layer only — it does
NOT change how music is resolved for actual rendering:
``services/brand.py:music_from_template`` and
``services/storage.py:resolve_music_safe`` still read official tracks
straight off disk at ``data/music/{mood}.<ext>`` via the untouched mood-keyed
``GET /api/v1/music/{mood}`` route in ``files.py``. Uploading an "official"
track through here is simply how that file gets written; the render path is
unaware this router exists.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from starlette.responses import FileResponse

from app.dependencies import DBDep, get_current_user
from app.models.schemas import MusicTrackResponse
from app.models.tables import MusicTrack, User
from app.services.storage import (
    delete_music_track_file,
    resolve_music_track_file_safe,
    save_official_music_upload,
    save_personal_music_upload,
)

router = APIRouter()


@router.get("", response_model=list[MusicTrackResponse])
async def list_music_tracks(
    db: DBDep,
    current_user: User = Depends(get_current_user),
    scope: str | None = None,
) -> list[MusicTrack]:
    """List tracks. ``scope=official`` | ``personal`` filters; omit for both.

    Personal results are always scoped to the current user.
    """
    query = select(MusicTrack)
    if scope == "official":
        query = query.where(MusicTrack.user_id.is_(None))
    elif scope == "personal":
        query = query.where(MusicTrack.user_id == current_user.id)
    else:
        query = query.where(
            (MusicTrack.user_id.is_(None)) | (MusicTrack.user_id == current_user.id)
        )
    result = await db.execute(query.order_by(MusicTrack.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=MusicTrackResponse, status_code=status.HTTP_201_CREATED)
async def upload_music_track(
    db: DBDep,
    file: UploadFile = File(...),
    title: str = Form(...),
    scope: str = Form("personal"),
    mood: str | None = Form(None),
    duration_seconds: float | None = Form(None),
    source_note: str | None = Form(None),
    current_user: User = Depends(get_current_user),
) -> MusicTrack:
    """Upload a track.

    ``scope="official"`` requires ``mood`` and writes to the same
    ``data/music/{mood}.<ext>`` file the renderer reads (replacing any prior
    file for that mood, matching the existing "one file per mood" reality).
    ``scope="personal"`` (default) stores the file under a per-user directory;
    it is never read by the render pipeline, only listed/played back here.
    """
    filename = file.filename or "unnamed"

    if scope == "official":
        if not mood:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mood is required for official tracks",
            )
        relative_path = await save_official_music_upload(file.file, mood, filename)
        existing = await db.execute(
            select(MusicTrack).where(MusicTrack.mood == mood, MusicTrack.user_id.is_(None))
        )
        track = existing.scalar_one_or_none()
        if track is None:
            track = MusicTrack(mood=mood, user_id=None)
            db.add(track)
        track.title = title
        track.filename = filename
        track.file_url = relative_path
        track.duration_seconds = duration_seconds
        track.source_note = source_note
    elif scope == "personal":
        track_id = uuid4()
        relative_path = await save_personal_music_upload(
            file.file, current_user.id, track_id, filename
        )
        track = MusicTrack(
            id=track_id,
            user_id=current_user.id,
            mood=None,
            title=title,
            filename=filename,
            file_url=relative_path,
            duration_seconds=duration_seconds,
            source_note=source_note,
        )
        db.add(track)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope must be 'official' or 'personal'",
        )

    await db.commit()
    await db.refresh(track)
    return track


async def _get_deletable_music_track(track_id: UUID, user_id: UUID, db: DBDep) -> MusicTrack:
    """Fetch a track the user may delete: their own personal track, or any official one."""
    result = await db.execute(select(MusicTrack).where(MusicTrack.id == track_id))
    track = result.scalar_one_or_none()
    if track is None or (track.user_id is not None and track.user_id != user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music track not found"
        )
    return track


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_music_track(
    track_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a track (own personal track, or any official track)."""
    track = await _get_deletable_music_track(track_id, current_user.id, db)
    delete_music_track_file(track.file_url)
    await db.delete(track)
    await db.commit()


@router.get("/track/{track_id}")
async def stream_music_track(track_id: UUID, db: DBDep) -> FileResponse:
    """Stream a track by id (Range-capable).

    Used for personal tracks and official-track previews alike; the
    mood-keyed ``/music/{mood}`` route in ``files.py`` remains the one the
    renderer actually calls.
    """
    result = await db.execute(select(MusicTrack).where(MusicTrack.id == track_id))
    track = result.scalar_one_or_none()
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Music track not found")
    path = resolve_music_track_file_safe(track.file_url)
    if path is None or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music track file not found"
        )
    return FileResponse(path)
