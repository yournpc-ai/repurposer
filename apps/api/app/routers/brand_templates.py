"""Brand template router: CRUD for video/brand templates."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.dependencies.auth import DEFAULT_USER_ID
from app.models.schemas import (
    AssetUploadUrlRequest,
    AssetUploadUrlResponse,
    BrandMediaCreateRequest,
    BrandTemplateCreate,
    BrandTemplateResponse,
    BrandTemplateUpdate,
)
from app.models.tables import BrandTemplate, User
from app.services.storage import (
    get_brand_media_path,
    presign_upload,
    save_brand_media_upload,
    stream_url,
)

router = APIRouter()


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


@router.post("", response_model=BrandTemplateResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("", response_model=list[BrandTemplateResponse])
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


@router.post("/media/upload-url", response_model=AssetUploadUrlResponse)
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


@router.post("/media", status_code=status.HTTP_201_CREATED)
async def create_brand_media_from_key(
    request: BrandMediaCreateRequest,
    current_user: User = Depends(get_current_user_required),
) -> dict[str, str | None]:
    """Confirm a directly-uploaded brand media file and return its stream URL."""
    return {"url": stream_url(request.key)}


@router.post("/media/upload", status_code=status.HTTP_201_CREATED)
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


@router.get("/{template_id}", response_model=BrandTemplateResponse)
async def get_brand_template(
    template_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> BrandTemplate:
    """Get a brand template by ID."""
    return await _get_user_brand_template(
        template_id, current_user.id if current_user else None, db
    )


@router.put("/{template_id}", response_model=BrandTemplateResponse)
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


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_template(
    template_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a brand template."""
    template = await _get_user_brand_template(template_id, current_user.id, db)
    await db.delete(template)
    await db.commit()
