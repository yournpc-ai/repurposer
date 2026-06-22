"""Speaker router."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agents.persona import persona_agent
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep
from app.models.schemas import (
    AssetType,
    SpeakerCreate,
    SpeakerPersona,
    SpeakerResponse,
    SpeakerUpdate,
)
from app.models.tables import Asset, Speaker
from app.services.extraction import extract_text
from app.services.storage import delete_file, delete_speaker_files

router = APIRouter()


@router.post("", response_model=SpeakerResponse, status_code=status.HTTP_201_CREATED)
async def create_speaker(data: SpeakerCreate, db: DBDep) -> Speaker:
    """Create a new speaker."""
    speaker = Speaker(**data.model_dump())
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


@router.get("", response_model=list[SpeakerResponse])
async def list_speakers(db: DBDep, skip: int = 0, limit: int = 100) -> list[Speaker]:
    """List all speakers."""
    result = await db.execute(select(Speaker).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.get("/{speaker_id}", response_model=SpeakerResponse)
async def get_speaker(speaker_id: UUID, db: DBDep) -> Speaker:
    """Get speaker by ID."""
    result = await db.execute(select(Speaker).where(Speaker.id == speaker_id))
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )
    return speaker


@router.put("/{speaker_id}", response_model=SpeakerResponse)
async def update_speaker(speaker_id: UUID, data: SpeakerUpdate, db: DBDep) -> Speaker:
    """Update speaker."""
    result = await db.execute(select(Speaker).where(Speaker.id == speaker_id))
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(speaker, field, value)

    await db.commit()
    await db.refresh(speaker)
    return speaker


@router.delete("/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_speaker(speaker_id: UUID, db: DBDep) -> None:
    """Delete speaker and all associated materials."""
    result = await db.execute(select(Speaker).where(Speaker.id == speaker_id))
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )

    # Delete associated assets (files + DB rows)
    result = await db.execute(select(Asset).where(Asset.speaker_id == speaker_id))
    assets = list(result.scalars().all())
    for asset in assets:
        delete_file(asset.file_url)
        await db.delete(asset)

    await db.delete(speaker)
    await db.commit()

    # Remove speaker upload directory after DB commit
    delete_speaker_files(speaker_id)


@router.post("/{speaker_id}/persona/generate", response_model=SpeakerPersona)
async def generate_persona(speaker_id: UUID, db: DBDep) -> SpeakerPersona:
    """Generate speaker persona from uploaded past materials."""
    result = await db.execute(select(Speaker).where(Speaker.id == speaker_id))
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )

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

    # Ensure all materials have extracted text
    materials: list[str] = []
    for asset in assets:
        if not asset.extracted_text and asset.file_url:
            asset.extracted_text = extract_text(asset.file_url)
            asset.processed_at = datetime.now(UTC)
            db.add(asset)
        if asset.extracted_text:
            materials.append(asset.extracted_text)

    if not materials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract text from any uploaded material",
        )

    await db.commit()

    try:
        persona = await persona_agent.generate(
            speaker_name=speaker.name,
            speaker_title=speaker.title,
            language=speaker.language,
            materials=materials,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    speaker.persona = persona.model_dump()
    await db.commit()
    await db.refresh(speaker)
    return persona
