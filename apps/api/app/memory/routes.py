"""Memory module routes: speakers + brand templates."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.skills.persona import persona_agent
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.dependencies.auth import DEFAULT_USER_ID
from app.models.schemas import (
    AssetType,
    AssetUploadUrlRequest,
    AssetUploadUrlResponse,
    BrandMediaCreateRequest,
    BrandTemplateCreate,
    BrandTemplateResponse,
    BrandTemplateUpdate,
    SpeakerContext,
    SpeakerCreate,
    SpeakerUpdate,
)
from app.models.tables import Asset, BrandTemplate, Speaker, User
from app.tools.extraction import extract_text
from app.tools.storage import (
    delete_file,
    delete_speaker_files,
    get_brand_media_path,
    presign_upload,
    save_brand_media_upload,
    stream_url,
)

speakers_router = APIRouter()


@speakers_router.post("", response_model=SpeakerContext, status_code=status.HTTP_201_CREATED)
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


@speakers_router.get("", response_model=list[SpeakerContext])
async def list_speakers(
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> list[Speaker]:
    """List the current user's own speakers.

    Default-user (shared) speakers are intentionally excluded: project creation
    rejects speaker_ids the caller does not own, so listing them would offer
    options that always 404 when selected. Anonymous callers get an empty
    list (generation requires login anyway).
    """
    if current_user is None:
        return []
    result = await db.execute(
        select(Speaker)
        .where(Speaker.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _get_user_speaker(
    speaker_id: UUID, user_id: UUID | None, db: DBDep
) -> Speaker:
    """Fetch a speaker and ensure it belongs to the given user or defaults."""
    query = select(Speaker).where(Speaker.id == speaker_id)
    if user_id is None:
        query = query.where(Speaker.user_id == DEFAULT_USER_ID)
    else:
        query = query.where(Speaker.user_id.in_([user_id, DEFAULT_USER_ID]))
    result = await db.execute(query)
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )
    return speaker


@speakers_router.get("/{speaker_id}", response_model=SpeakerContext)
async def get_speaker(
    speaker_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> Speaker:
    """Get speaker by ID."""
    return await _get_user_speaker(
        speaker_id, current_user.id if current_user else None, db
    )


@speakers_router.put("/{speaker_id}", response_model=SpeakerContext)
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


@speakers_router.delete("/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@speakers_router.post("/{speaker_id}/persona/generate", response_model=SpeakerContext)
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


# ---- Brand templates --------------------------------------------------

brand_templates_router = APIRouter()


async def _get_user_brand_template(
    template_id: UUID, user_id: UUID | None, db: DBDep
) -> BrandTemplate:
    """Fetch a brand template and ensure it belongs to the given user or defaults."""
    query = select(BrandTemplate).where(BrandTemplate.id == template_id)
    if user_id is None:
        query = query.where(BrandTemplate.user_id == DEFAULT_USER_ID)
    else:
        query = query.where(BrandTemplate.user_id.in_([user_id, DEFAULT_USER_ID]))
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand template not found",
        )
    return template


@brand_templates_router.post("", response_model=BrandTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_template(
    data: BrandTemplateCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> BrandTemplate:
    """Create a brand template."""
    template = BrandTemplate(**data.model_dump(), user_id=current_user.id)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@brand_templates_router.get("", response_model=list[BrandTemplateResponse])
async def list_brand_templates(
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[BrandTemplate]:
    """List brand templates for the current user plus the system defaults."""
    user_ids = [current_user.id, DEFAULT_USER_ID] if current_user else [DEFAULT_USER_ID]
    result = await db.execute(
        select(BrandTemplate)
        .where(
            BrandTemplate.user_id.in_(user_ids)
        )
        .order_by(BrandTemplate.created_at.desc())
    )
    return list(result.scalars().all())


@brand_templates_router.post("/media/upload-url", response_model=AssetUploadUrlResponse)
async def create_brand_media_upload_url(
    request: AssetUploadUrlRequest,
    current_user: User = Depends(get_current_user_required),
) -> AssetUploadUrlResponse:
    """Return a presigned PUT URL for direct upload of brand intro/outro media."""
    key = str(await get_brand_media_path(current_user.id, request.filename))
    upload_url = await presign_upload(key, content_type=request.content_type)
    if upload_url is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        )
    return AssetUploadUrlResponse(key=key, upload_url=upload_url)


@brand_templates_router.post("/media", status_code=status.HTTP_201_CREATED)
async def create_brand_media_from_key(
    request: BrandMediaCreateRequest,
    current_user: User = Depends(get_current_user_required),
) -> dict[str, str | None]:
    """Confirm a directly-uploaded brand media file and return its stream URL."""
    return {"url": stream_url(request.key)}


@brand_templates_router.post("/media/upload", status_code=status.HTTP_201_CREATED)
async def upload_brand_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user_required),
) -> dict[str, str | None]:
    """Upload an intro/outro image or video through the API (local/fallback).

    Prefer ``POST /media/upload-url`` for direct-to-storage uploads.
    """
    if not (file.content_type or "").startswith(("image/", "video/")):
        raise HTTPException(status_code=422, detail="File must be an image or video")
    relative_path = await save_brand_media_upload(
        file.file, current_user.id, file.filename or "upload"
    )
    return {"url": stream_url(relative_path)}


@brand_templates_router.get("/{template_id}", response_model=BrandTemplateResponse)
async def get_brand_template(
    template_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> BrandTemplate:
    """Get a brand template by ID."""
    return await _get_user_brand_template(
        template_id, current_user.id if current_user else None, db
    )


@brand_templates_router.put("/{template_id}", response_model=BrandTemplateResponse)
async def update_brand_template(
    template_id: UUID,
    data: BrandTemplateUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> BrandTemplate:
    """Update a brand template."""
    template = await _get_user_brand_template(template_id, current_user.id, db)

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(template, key, value)

    await db.commit()
    await db.refresh(template)
    return template


@brand_templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_template(
    template_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a brand template."""
    template = await _get_user_brand_template(template_id, current_user.id, db)
    await db.delete(template)
    await db.commit()
