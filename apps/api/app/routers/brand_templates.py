"""Brand template router: CRUD for video/brand templates."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user
from app.models.schemas import (
    BrandTemplateCreate,
    BrandTemplateResponse,
    BrandTemplateUpdate,
)
from app.models.tables import BrandTemplate, User
from app.services.storage import save_brand_media_upload, stream_url

router = APIRouter()


async def _get_user_brand_template(
    template_id: UUID, user_id: UUID, db: DBDep
) -> BrandTemplate:
    """Fetch a brand template and ensure it belongs to the given user."""
    result = await db.execute(
        select(BrandTemplate).where(
            BrandTemplate.id == template_id,
            BrandTemplate.user_id == user_id,
        )
    )
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
) -> list[BrandTemplate]:
    """List brand templates for the current user, newest first."""
    result = await db.execute(
        select(BrandTemplate)
        .where(BrandTemplate.user_id == current_user.id)
        .order_by(BrandTemplate.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/media", status_code=status.HTTP_201_CREATED)
async def upload_brand_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | None]:
    """Upload an intro/outro image or video; returns its storage-seam URL.

    Not scoped by template_id (a draft may not have one yet) — placed before
    the ``/{template_id}`` routes so ``media`` is never parsed as a UUID.
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
    current_user: User = Depends(get_current_user),
) -> BrandTemplate:
    """Get a brand template by ID."""
    return await _get_user_brand_template(template_id, current_user.id, db)


@router.put("/{template_id}", response_model=BrandTemplateResponse)
async def update_brand_template(
    template_id: UUID,
    data: BrandTemplateUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a brand template."""
    template = await _get_user_brand_template(template_id, current_user.id, db)
    await db.delete(template)
    await db.commit()
