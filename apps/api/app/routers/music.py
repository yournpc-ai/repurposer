"""Music library router.

Endpoints (prefix ``/api/v1/music``):

- ``GET  ""``                  list pieces (auth; public + caller's own).
- ``POST "/generate"``         generate a custom piece from a prompt (auth).
- ``GET  "/{music_id}/stream"`` stream a piece's audio by UUID (no auth — the
                                render service fetches without a bearer token).
- ``PUT  "/{music_id}"``       update metadata (auth).
- ``DELETE "/{music_id}"``     delete (auth; 409 if referenced by any clip).
- ``GET  "/{ref}"``            unified: UUID → metadata (auth-free, public
                                only); mood string → legacy audio stream
                                (no auth, Range-capable). Declared last so it
                                doesn't shadow ``/generate`` or ``/stream``.

The legacy ``GET /api/v1/music/{mood}`` audio stream (old clips' render_spec)
moved here from ``routers/files.py``; its URL is unchanged.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.responses import FileResponse

from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user
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
from app.services.storage import resolve_music_safe, resolve_safe

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


@router.get("", response_model=list[MusicResponse])
async def list_music_endpoint(
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> list[MusicResponse]:
    """List available music pieces (public + the caller's own)."""
    pieces = await list_music(db, user_id=current_user.id)
    return [_to_response(m) for m in pieces]


@router.post("/generate", response_model=MusicResponse, status_code=status.HTTP_201_CREATED)
async def generate_music_endpoint(
    data: MusicGenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> MusicResponse:
    """Generate a new music piece from a prompt via MiniMax and persist it.

    Sync in Phase 1 (the call is async so the event loop is not blocked); a
    chat-driven worker path is Phase 2 (see docs/MUSIC_ARCHITECTURE.md).
    """
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
async def stream_music_by_id(music_id: UUID, db: DBDep) -> FileResponse:
    """Stream a music piece's audio by UUID, with Range support (no auth)."""
    music = await get_music(db, music_id)
    if music is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music not found"
        )
    path = resolve_safe(music.file_path)
    if path is None or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music file not found"
        )
    return FileResponse(path)


@router.put("/{music_id}", response_model=MusicResponse)
async def update_music_endpoint(
    music_id: UUID,
    data: MusicMetadataUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> MusicResponse:
    """Update a music piece's editable metadata.

    MVP: the single default user is the platform admin, so any piece is
    editable. Future: restrict to the piece's ``generated_by_user_id``.
    """
    _ = current_user  # reserved for future ownership checks
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
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> None:
    """Delete a music piece; 409 if any clip still references it."""
    _ = current_user  # reserved for future ownership checks
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
    """Unified single-segment handler.

    - ``ref`` parses as a UUID → return the piece's metadata (public only).
    - otherwise → treat ``ref`` as a legacy mood key and stream the audio
      (preserves ``/api/v1/music/{mood}`` for old clips; Range-capable).
    """
    try:
        music_id = UUID(ref)
    except ValueError:
        path = resolve_music_safe(ref)
        if path is None or not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Music track not found",
            )
        return FileResponse(path)

    music = await get_music(db, music_id)
    if music is None or not music.is_public:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Music not found"
        )
    return _to_response(music)
