"""Permanent voiceprint library router.

Endpoints (prefix ``/api/v1/voices``):
- ``GET  ""``                  list/search visible permanent voices (platform curated + owner's own).
- ``POST "/design"``           design & persist a new voiceprint via MiniMax ``/voice_design`` (auth).
- ``GET  "/{voice_id}/audio"`` stream preview audio with auth + scope visibility check.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import VoiceDesignRequest, VoiceResponse
from app.models.tables import User, Voice
from app.pipeline.voices import design_and_save_voice, get_visible_voice, search_voices
from app.providers import storage
from app.providers.voice import VoiceError

router = APIRouter()


def _to_response(voice: Voice) -> VoiceResponse:
    return VoiceResponse(
        id=voice.id,
        owner_id=voice.owner_id,
        scope=voice.scope,
        status=voice.status,
        source_kind=voice.source_kind,
        name=voice.name,
        description=voice.description,
        design_prompt=voice.design_prompt,
        languages=list(voice.languages or []),
        gender=voice.gender,
        age_band=voice.age_band,
        tone_tags=list(voice.tone_tags or []),
        compatible_styles=list(voice.compatible_styles or []),
        provider=voice.provider,
        provider_voice_id=voice.provider_voice_id,
        preview_url=(
            f"/api/v1/voices/{voice.id}/audio"
            if (voice.preview_audio_key or voice.reference_audio_key)
            else None
        ),
        use_count=int(voice.use_count or 0),
        is_favorite=bool(voice.is_favorite),
        created_at=voice.created_at,
        updated_at=voice.updated_at,
    )


@router.get("", response_model=list[VoiceResponse])
async def list_voices_endpoint(
    db: DBDep,
    language: str | None = Query(default=None),
    style_preset: str | None = Query(default=None),
    tone: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User | None = Depends(get_current_user),
) -> list[VoiceResponse]:
    """List/search permanent voices visible to the caller."""
    rows = await search_voices(
        db,
        owner_id=current_user.id if current_user else None,
        language=language,
        style_preset=style_preset,
        tone=tone,
        query=query,
        limit=limit,
    )
    return [_to_response(row) for row in rows]


@router.post("/design", response_model=VoiceResponse, status_code=status.HTTP_201_CREATED)
async def design_voice_endpoint(
    data: VoiceDesignRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> VoiceResponse:
    """Design a custom MiniMax voiceprint and persist it in the user's permanent library."""
    try:
        row = await design_and_save_voice(
            db,
            owner_id=current_user.id,
            name=data.name,
            prompt=data.prompt,
            preview_text=data.preview_text,
            languages=data.languages,
            tone_tags=data.tone_tags,
            compatible_styles=data.compatible_styles,
            gender=data.gender,
            age_band=data.age_band,
            scope="user",
            status="ready",
            description=data.description,
        )
    except VoiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Voice design failed: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _to_response(row)


@router.get("/{voice_id}/audio")
async def stream_voice_preview_audio(
    voice_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> Response:
    """Stream preview audio for a visible voiceprint with auth + scope check."""
    row = await get_visible_voice(
        db,
        voice_id=voice_id,
        owner_id=current_user.id if current_user else None,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice not found")
    key = row.preview_audio_key or row.reference_audio_key
    if not key or not await storage.exists(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice preview audio not found")
    audio_bytes = await storage.read(key)
    return Response(content=audio_bytes, media_type="audio/mpeg")
