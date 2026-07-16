"""Asset router for projects and speakers."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetCreateRequest,
    AssetResponse,
    AssetStatus,
    AssetType,
    AssetUploadUrlRequest,
    AssetUploadUrlResponse,
    SpeakerAssetCreateRequest,
)
from app.models.tables import Asset, Project, Speaker, User
from app.services.storage import (
    delete_file,
    exists,
    get_project_upload_dir,
    get_speaker_upload_dir,
    get_upload_path,
    presign_upload,
    save_speaker_upload,
    save_upload,
)

router = APIRouter()
speaker_assets_router = APIRouter()


async def _get_user_project(project_id: UUID, user_id: UUID | None, db: DBDep) -> Project:
    """Fetch a project and ensure it belongs to the given user or is the demo."""
    from app.services.project_context import DEMO_PROJECT_ID

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if user_id is not None and project.user_id == user_id:
        return project
    if project.id == DEMO_PROJECT_ID:
        return project
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found",
    )


async def _get_user_speaker(speaker_id: UUID, user_id: UUID | None, db: DBDep) -> Speaker:
    """Fetch a speaker and ensure it belongs to the given user or defaults."""
    from app.dependencies.auth import DEFAULT_USER_ID

    result = await db.execute(select(Speaker).where(Speaker.id == speaker_id))
    speaker = result.scalar_one_or_none()
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found",
        )
    if user_id is not None and speaker.user_id == user_id:
        return speaker
    if speaker.user_id == DEFAULT_USER_ID:
        return speaker
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Speaker not found",
    )


# ---------------------------------------------------------------------------
# Project assets
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/assets/upload-url",
    response_model=AssetUploadUrlResponse,
)
async def create_project_asset_upload_url(
    project_id: UUID,
    request: AssetUploadUrlRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> AssetUploadUrlResponse:
    """Return a presigned PUT URL so the client can upload directly to object storage."""
    await _get_user_project(project_id, current_user.id, db)

    key = str(await get_upload_path(project_id, current_user.id, request.filename))
    upload_url = await presign_upload(
        key,
        content_type=request.content_type,
    )
    if upload_url is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        )
    return AssetUploadUrlResponse(key=key, upload_url=upload_url)


@router.post(
    "/{project_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset_from_key(
    project_id: UUID,
    request: AssetCreateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Create an asset record after the client uploaded the file directly to storage."""
    await _get_user_project(project_id, current_user.id, db)

    # The key must be one this server issued for this project+user, and the
    # object must actually exist — never trust a client-reported key blindly.
    expected_prefix = get_project_upload_dir(project_id, current_user.id)
    if not request.key.startswith(f"{expected_prefix}/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid upload key",
        )
    if not await exists(request.key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file not found in storage; upload it first",
        )

    asset = Asset(
        user_id=current_user.id,
        project_id=project_id,
        type=request.type,
        file_url=request.key,
        processing_status=AssetStatus.PENDING,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.post(
    "/{project_id}/assets/upload",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset(
    project_id: UUID,
    type: AssetType = Form(...),  # noqa: A002
    file: UploadFile = File(...),
    db: DBDep = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Upload an asset through the API (local development / fallback).

    Prefer ``POST /{project_id}/assets/upload-url`` for direct-to-storage uploads.
    """
    await _get_user_project(project_id, current_user.id, db)

    filename = file.filename or "unnamed"
    relative_path = await save_upload(file.file, project_id, current_user.id, filename)

    # Processing (text extraction / ASR / OCR) runs in the worker; the asset is
    # created PENDING and the client polls until it settles.
    asset = Asset(
        user_id=current_user.id,
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
async def get_asset(
    project_id: UUID,
    asset_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> Asset:
    """Get a single project asset (used to poll processing status)."""
    await _get_user_project(project_id, current_user.id if current_user else None, db)
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
async def reprocess_asset(
    project_id: UUID,
    asset_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Re-queue a project asset for processing (e.g. after a failure)."""
    await _get_user_project(project_id, current_user.id, db)
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
async def list_assets(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[Asset]:
    """List assets for a project."""
    await _get_user_project(project_id, current_user.id if current_user else None, db)
    result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{project_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    project_id: UUID,
    asset_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a project asset."""
    await _get_user_project(project_id, current_user.id, db)
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    await delete_file(asset.file_url)
    await db.delete(asset)
    await db.commit()


# ---------------------------------------------------------------------------
# Speaker assets (source material for persona generation)
# ---------------------------------------------------------------------------


@speaker_assets_router.post(
    "/{speaker_id}/assets/upload-url",
    response_model=AssetUploadUrlResponse,
)
async def create_speaker_asset_upload_url(
    speaker_id: UUID,
    request: AssetUploadUrlRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> AssetUploadUrlResponse:
    """Return a presigned PUT URL for direct upload of a speaker asset."""
    await _get_user_speaker(speaker_id, current_user.id, db)

    from app.services.storage import get_speaker_upload_path

    key = str(await get_speaker_upload_path(speaker_id, current_user.id, request.filename))
    upload_url = await presign_upload(key, content_type=request.content_type)
    if upload_url is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        )
    return AssetUploadUrlResponse(key=key, upload_url=upload_url)


@speaker_assets_router.post(
    "/{speaker_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_speaker_asset_from_key(
    speaker_id: UUID,
    request: SpeakerAssetCreateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Create a speaker asset record after direct upload to storage."""
    await _get_user_speaker(speaker_id, current_user.id, db)

    # Same trust rules as project assets: server-issued key + object present.
    expected_prefix = get_speaker_upload_dir(speaker_id, current_user.id)
    if not request.key.startswith(f"{expected_prefix}/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid upload key",
        )
    if not await exists(request.key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file not found in storage; upload it first",
        )

    asset = Asset(
        user_id=current_user.id,
        speaker_id=speaker_id,
        type=AssetType.PAST_MATERIAL,
        file_url=request.key,
        processing_status=AssetStatus.PENDING,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@speaker_assets_router.post(
    "/{speaker_id}/assets/upload",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_speaker_asset(
    speaker_id: UUID,
    file: UploadFile = File(...),
    db: DBDep = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Upload a past material asset through the API (local/fallback)."""
    await _get_user_speaker(speaker_id, current_user.id, db)

    filename = file.filename or "unnamed"
    relative_path = await save_speaker_upload(file.file, speaker_id, current_user.id, filename)

    asset = Asset(
        user_id=current_user.id,
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
async def list_speaker_assets(
    speaker_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[Asset]:
    """List past material assets for a speaker."""
    await _get_user_speaker(speaker_id, current_user.id if current_user else None, db)
    result = await db.execute(
        select(Asset).where(Asset.speaker_id == speaker_id).order_by(Asset.created_at.desc())
    )
    return list(result.scalars().all())


@speaker_assets_router.delete(
    "/{speaker_id}/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_speaker_asset(
    speaker_id: UUID,
    asset_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a speaker asset."""
    await _get_user_speaker(speaker_id, current_user.id, db)
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.speaker_id == speaker_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    await delete_file(asset.file_url)
    await db.delete(asset)
    await db.commit()
