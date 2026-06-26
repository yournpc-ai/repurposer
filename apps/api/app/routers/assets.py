"""Asset router for projects and speakers."""

from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.dependencies import DBDep
from app.models.schemas import AssetResponse, AssetStatus, AssetType
from app.models.tables import Asset, Project, Speaker
from app.services.storage import (
    delete_file,
    save_speaker_upload,
    save_upload,
)

router = APIRouter()
speaker_assets_router = APIRouter()


# ---------------------------------------------------------------------------
# Project assets
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset(
    project_id: UUID,
    type: AssetType = Form(...),  # noqa: A002
    file: UploadFile = File(...),
    db: DBDep = None,  # type: ignore[assignment]
) -> Asset:
    """Upload an asset to a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    filename = file.filename or "unnamed"
    relative_path = await save_upload(file.file, project_id, filename)

    # Processing (text extraction / ASR / OCR) runs in the worker; the asset is
    # created PENDING and the client polls until it settles.
    asset = Asset(
        project_id=project_id,
        type=type,
        file_url=relative_path,
        processing_status=AssetStatus.PENDING,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("/{project_id}/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(project_id: UUID, asset_id: UUID, db: DBDep) -> Asset:
    """Get a single project asset (used to poll processing status)."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    return asset


@router.post(
    "/{project_id}/assets/{asset_id}/reprocess",
    response_model=AssetResponse,
)
async def reprocess_asset(project_id: UUID, asset_id: UUID, db: DBDep) -> Asset:
    """Re-queue a project asset for processing (e.g. after a failure)."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    asset.processing_status = AssetStatus.PENDING
    asset.processing_error = None
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("/{project_id}/assets", response_model=list[AssetResponse])
async def list_assets(project_id: UUID, db: DBDep) -> list[Asset]:
    """List assets for a project."""
    result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{project_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(project_id: UUID, asset_id: UUID, db: DBDep) -> None:
    """Delete a project asset."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    delete_file(asset.file_url)
    await db.delete(asset)
    await db.commit()


# ---------------------------------------------------------------------------
# Speaker assets (past materials for persona generation)
# ---------------------------------------------------------------------------


@speaker_assets_router.post(
    "/{speaker_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_speaker_asset(
    speaker_id: UUID,
    file: UploadFile = File(...),
    db: DBDep = None,  # type: ignore[assignment]
) -> Asset:
    """Upload a past material asset for a speaker."""
    result = await db.execute(select(Speaker).where(Speaker.id == speaker_id))
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )

    filename = file.filename or "unnamed"
    relative_path = await save_speaker_upload(file.file, speaker_id, filename)

    asset = Asset(
        speaker_id=speaker_id,
        type=AssetType.PAST_MATERIAL,
        file_url=relative_path,
        processing_status=AssetStatus.PENDING,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@speaker_assets_router.get("/{speaker_id}/assets", response_model=list[AssetResponse])
async def list_speaker_assets(speaker_id: UUID, db: DBDep) -> list[Asset]:
    """List past material assets for a speaker."""
    result = await db.execute(
        select(Asset).where(Asset.speaker_id == speaker_id).order_by(Asset.created_at.desc())
    )
    return list(result.scalars().all())


@speaker_assets_router.delete(
    "/{speaker_id}/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_speaker_asset(speaker_id: UUID, asset_id: UUID, db: DBDep) -> None:
    """Delete a speaker asset."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.speaker_id == speaker_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    delete_file(asset.file_url)
    await db.delete(asset)
    await db.commit()
