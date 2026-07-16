"""Speaker router."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agents.persona import persona_agent
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetType,
    SpeakerContext,
    SpeakerCreate,
    SpeakerUpdate,
)
from app.models.tables import Asset, Speaker, User
from app.services.extraction import extract_text
from app.services.storage import delete_file, delete_speaker_files

router = APIRouter()


@router.post("", response_model=SpeakerContext, status_code=status.HTTP_201_CREATED)
async def create_speaker(
    data: SpeakerCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Speaker:
    """Create a new speaker."""
    speaker = Speaker(**data.model_dump(), user_id=current_user.id)
    db.add(speaker)
    try:
        await db.commit()
        await db.refresh(speaker)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Speaker creation failed",
        )
    return speaker


@router.get("", response_model=list[SpeakerContext])
async def list_speakers(
    db: DBDep,
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> list[Speaker]:
    """List speakers for the current user."""
    result = await db.execute(
        select(Speaker)
        .where(Speaker.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _get_user_speaker(speaker_id: UUID, user_id: UUID, db: DBDep) -> Speaker:
    """Fetch a speaker and ensure it belongs to the given user."""
    result = await db.execute(
        select(Speaker).where(Speaker.id == speaker_id, Speaker.user_id == user_id)
    )
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )
    return speaker


@router.get("/{speaker_id}", response_model=SpeakerContext)
async def get_speaker(
    speaker_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Speaker:
    """Get speaker by ID."""
    return await _get_user_speaker(speaker_id, current_user.id, db)


@router.put("/{speaker_id}", response_model=SpeakerContext)
async def update_speaker(
    speaker_id: UUID,
    data: SpeakerUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Speaker:
    """Update speaker."""
    speaker = await _get_user_speaker(speaker_id, current_user.id, db)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(speaker, field, value)

    await db.commit()
    await db.refresh(speaker)
    return speaker


@router.delete("/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_speaker(
    speaker_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete speaker and all associated source assets."""
    speaker = await _get_user_speaker(speaker_id, current_user.id, db)

    # Delete associated assets (files + DB rows)
    result = await db.execute(select(Asset).where(Asset.speaker_id == speaker_id))
    assets = list(result.scalars().all())
    for asset in assets:
        delete_file(asset.file_url)
        await db.delete(asset)

    await db.delete(speaker)
    await db.commit()

    # Remove speaker upload directory after DB commit
    delete_speaker_files(speaker_id, current_user.id)


@router.post("/{speaker_id}/persona/generate", response_model=SpeakerContext)
async def generate_persona(
    speaker_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> SpeakerContext:
    """Generate speaker persona and content memory from uploaded source assets."""
    speaker = await _get_user_speaker(speaker_id, current_user.id, db)

    # Find speaker's past material assets
    result = await db.execute(
        select(Asset).where(
            Asset.speaker_id == speaker_id,
            Asset.type == AssetType.PAST_MATERIAL,
        )
    )
    assets = list(result.scalars().all())
    if not assets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No past materials uploaded for this speaker",
        )

    # Ensure all source assets have extracted text
    asset_texts: list[str] = []
    for asset in assets:
        if not asset.extracted_text and asset.file_url:
            asset.extracted_text = extract_text(asset.file_url)
            asset.processed_at = datetime.now(UTC)
            db.add(asset)
        if asset.extracted_text:
            asset_texts.append(asset.extracted_text)

    if not asset_texts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract text from any uploaded source asset",
        )

    await db.commit()

    try:
        memory = await persona_agent.generate(
            speaker_name=speaker.name,
            speaker_title=speaker.title,
            language=speaker.language,
            asset_texts=asset_texts,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    speaker.core_values = memory.core_values or []
    speaker.favorite_metaphors = memory.favorite_metaphors or []
    speaker.sentence_style = memory.sentence_style or ""
    speaker.emotional_tone = memory.emotional_tone or "rational"
    speaker.typical_hooks = memory.typical_hooks or []
    speaker.avoid_words = memory.avoid_words or []
    speaker.voice = memory.voice
    speaker.audience = memory.audience
    speaker.guidelines = memory.guidelines
    speaker.cta = memory.cta
    await db.commit()
    await db.refresh(speaker)
    return speaker
