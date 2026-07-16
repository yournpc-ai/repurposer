"""Music library router.

Endpoints (prefix ``/api/v1/music``):

- ``GET  ""``                  list pieces (auth; public + caller's own).
- ``POST "/generate"``         generate a custom piece from a prompt (auth).
- ``GET  "/{music_id}/stream"`` redirect to a piece's public audio URL (no auth).
- ``PUT  "/{music_id}"``       update metadata (auth).
- ``DELETE "/{music_id}"``     delete (auth; 409 if referenced by any clip).
- ``GET "/{ref}"``             UUID → metadata (auth-free, public only).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import MusicGenerateRequest, MusicMetadataUpdate, MusicResponse
from app.models.tables import Music, User
from app.services.music import (
    MusicInUseError,
    create_music_from_generation,
    delete_music,
    get_music,
    list_music,
    update_music_metadata,
)
from app.services.music_generation import USER_MODEL
from app.services.music_generation import generate_music as generate_music_bytes
from app.services.storage import public_url

router = APIRouter()


def _to_response(music: Music) -> MusicResponse:
    """Build a MusicResponse with the stream URL (not stored on the ORM row)."""
    return MusicResponse(
        id=music.id,
        mood=music.mood,
        title=music.title,
        ext=music.ext,
        url=f"/api/v1/music/{music.id}/stream",
        size_bytes=music.size_bytes,
        duration_seconds=music.duration_seconds,
        prompt=music.prompt,
        model=music.model,
        license=music.license,
        source_url=music.source_url,
        attribution=music.attribution,
        is_public=music.is_public,
        created_at=music.created_at,
    )


async def _get_music_for_owner(db, music_id: UUID, user_id: UUID) -> Music:
    """Fetch a piece and ensure the caller created it.

    Platform/default pieces (``generated_by_user_id`` NULL) are immutable to
    regular users; user-generated pieces can only be touched by their creator.
    """
    music = await get_music(db, music_id)
    if music is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music not found"
        )
    if music.generated_by_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the creator can modify this music piece",
        )
    return music


@router.get("", response_model=list[MusicResponse])
async def list_music_endpoint(
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[MusicResponse]:
    """List available music pieces (public + the caller's own)."""
    pieces = await list_music(db, user_id=current_user.id if current_user else None)
    return [_to_response(m) for m in pieces]


@router.post("/generate", response_model=MusicResponse, status_code=status.HTTP_201_CREATED)
async def generate_music_endpoint(
    data: MusicGenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> MusicResponse:
    """Generate a new music piece from a prompt via MiniMax and persist it."""
    try:
        generated = await generate_music_bytes(
            data.prompt,
            model=USER_MODEL,
            is_instrumental=data.is_instrumental,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Music generation failed: {e}",
        ) from e
    music = await create_music_from_generation(
        db,
        prompt=data.prompt,
        generated=generated,
        mood=data.mood,
        title=data.title,
        user_id=current_user.id,
        is_public=True,
    )
    return _to_response(music)


@router.get("/{music_id}/stream")
async def stream_music_by_id(music_id: UUID, db: DBDep):
    """Redirect to a music piece's public audio URL (no auth)."""
    music = await get_music(db, music_id)
    if music is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music not found"
        )
    url = public_url(music.file_path)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music file not found"
        )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.put("/{music_id}", response_model=MusicResponse)
async def update_music_endpoint(
    music_id: UUID,
    data: MusicMetadataUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> MusicResponse:
    """Update a music piece's editable metadata (creator only)."""
    await _get_music_for_owner(db, music_id, current_user.id)
    music = await update_music_metadata(
        db,
        music_id,
        title=data.title,
        license=data.license,
        source_url=data.source_url,
        attribution=data.attribution,
        is_public=data.is_public,
    )
    if music is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music not found"
        )
    return _to_response(music)


@router.delete("/{music_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_music_endpoint(
    music_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a music piece (creator only); 409 if any clip references it."""
    await _get_music_for_owner(db, music_id, current_user.id)
    try:
        music = await delete_music(db, music_id)
    except MusicInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Music is referenced by {e.count} clip(s); remove it from "
            "those clips before deleting.",
        ) from e
    if music is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music not found"
        )


@router.get("/{ref}")
async def get_or_stream_music(ref: str, db: DBDep):
    """Return metadata for a public music piece by UUID."""
    try:
        music_id = UUID(ref)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music not found",
        )

    music = await get_music(db, music_id)
    if music is None or not music.is_public:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music not found"
        )
    return _to_response(music)
