"""Memory module routes: personas + brand templates."""

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
    PersonaContext,
    PersonaCreate,
    PersonaUpdate,
)
from app.models.tables import Asset, BrandTemplate, Persona, User
from app.tools.extraction import extract_text
from app.tools.storage import (
    delete_file,
    delete_persona_files,
    get_brand_media_path,
    presign_upload,
    save_brand_media_upload,
    stream_url,
)

personas_router = APIRouter()


@personas_router.post("", response_model=PersonaContext, status_code=status.HTTP_201_CREATED)
async def create_persona(
    data: PersonaCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Persona:
    """Create a new persona."""
    persona = Persona(**data.model_dump(), user_id=current_user.id)
    db.add(persona)
    try:
        await db.commit()
        await db.refresh(persona)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Persona creation failed",
        )
    return persona


@personas_router.get("", response_model=list[PersonaContext])
async def list_personas(
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> list[Persona]:
    """List the current user's own personas.

    Default-user (shared) personas are intentionally excluded: project creation
    rejects persona_ids the caller does not own, so listing them would offer
    options that always 404 when selected. Anonymous callers get an empty
    list (generation requires login anyway).
    """
    if current_user is None:
        return []
    result = await db.execute(
        select(Persona)
        .where(Persona.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _get_user_persona(
    persona_id: UUID, user_id: UUID | None, db: DBDep
) -> Persona:
    """Fetch a persona and ensure it belongs to the given user or defaults."""
    query = select(Persona).where(Persona.id == persona_id)
    if user_id is None:
        query = query.where(Persona.user_id == DEFAULT_USER_ID)
    else:
        query = query.where(Persona.user_id.in_([user_id, DEFAULT_USER_ID]))
    result = await db.execute(query)
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found",
        )
    return persona


@personas_router.get("/{persona_id}", response_model=PersonaContext)
async def get_persona(
    persona_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> Persona:
    """Get persona by ID."""
    return await _get_user_persona(
        persona_id, current_user.id if current_user else None, db
    )


@personas_router.put("/{persona_id}", response_model=PersonaContext)
async def update_persona(
    persona_id: UUID,
    data: PersonaUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Persona:
    """Update persona."""
    persona = await _get_user_persona(persona_id, current_user.id, db)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(persona, field, value)

    await db.commit()
    await db.refresh(persona)
    return persona


@personas_router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(
    persona_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete persona and all associated source assets."""
    persona = await _get_user_persona(persona_id, current_user.id, db)

    # Delete associated assets (files + DB rows)
    result = await db.execute(select(Asset).where(Asset.persona_id == persona_id))
    assets = list(result.scalars().all())
    for asset in assets:
        delete_file(asset.file_url)
        await db.delete(asset)

    await db.delete(persona)
    await db.commit()

    # Remove persona upload directory after DB commit
    delete_persona_files(persona_id, current_user.id)


@personas_router.post("/{persona_id}/generate", response_model=PersonaContext)
async def generate_persona(
    persona_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> PersonaContext:
    """Generate persona style and content memory from uploaded source assets."""
    persona = await _get_user_persona(persona_id, current_user.id, db)

    # Find persona's past material assets
    result = await db.execute(
        select(Asset).where(
            Asset.persona_id == persona_id,
            Asset.type == AssetType.PAST_MATERIAL,
        )
    )
    assets = list(result.scalars().all())
    if not assets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No past materials uploaded for this persona",
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
            persona_name=persona.name,
            persona_title=persona.title,
            language=persona.language,
            asset_texts=asset_texts,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    persona.core_values = memory.core_values or []
    persona.favorite_metaphors = memory.favorite_metaphors or []
    persona.sentence_style = memory.sentence_style or ""
    persona.emotional_tone = memory.emotional_tone or "rational"
    persona.typical_hooks = memory.typical_hooks or []
    persona.avoid_words = memory.avoid_words or []
    persona.voice = memory.voice
    persona.audience = memory.audience
    persona.guidelines = memory.guidelines
    persona.cta = memory.cta
    await db.commit()
    await db.refresh(persona)
    return persona


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
