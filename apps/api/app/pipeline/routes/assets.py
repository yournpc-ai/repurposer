"""Asset router for projects and personas."""

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
    PersonaAssetCreateRequest,
    PersonaAssetUpdateRequest,
    PersonaMediaCreateRequest,
)
from app.models.tables import Asset, Persona, Project, User
from app.tools.storage import (
    delete_file,
    exists,
    get_project_upload_dir,
    get_persona_upload_dir,
    get_persona_upload_path,
    get_upload_path,
    presign_upload,
    save_persona_upload,
    save_upload,
    stream_url,
)

router = APIRouter()
persona_assets_router = APIRouter()


async def _get_user_project(project_id: UUID, user_id: UUID | None, db: DBDep) -> Project:
    """Fetch a project and ensure it belongs to the given user."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if user_id is not None and project.user_id == user_id:
        return project
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found",
    )


async def _get_user_persona(persona_id: UUID, user_id: UUID | None, db: DBDep, *, write: bool = False) -> Persona:
    """Fetch a persona and check access. Legacy default-user (shared)
    personas stay READABLE to any caller; writes are owner-only — a shared
    row must never gain, change, or lose assets through another user's
    session."""
    from app.dependencies.auth import DEFAULT_USER_ID

    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found",
        )
    if user_id is not None and persona.user_id == user_id:
        return persona
    if persona.user_id == DEFAULT_USER_ID and not write:
        return persona
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Persona not found",
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
        title=request.title,
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
# Persona assets (source material for persona generation)
# ---------------------------------------------------------------------------


@persona_assets_router.post(
    "/{persona_id}/assets/upload-url",
    response_model=AssetUploadUrlResponse,
)
async def create_persona_asset_upload_url(
    persona_id: UUID,
    request: AssetUploadUrlRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> AssetUploadUrlResponse:
    """Return a presigned PUT URL for direct upload of a persona asset."""
    await _get_user_persona(persona_id, current_user.id, db, write=True)

    from app.tools.storage import get_persona_upload_path

    key = str(await get_persona_upload_path(persona_id, current_user.id, request.filename))
    upload_url = await presign_upload(key, content_type=request.content_type)
    if upload_url is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        )
    return AssetUploadUrlResponse(key=key, upload_url=upload_url)


@persona_assets_router.post(
    "/{persona_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_persona_asset_from_key(
    persona_id: UUID,
    request: PersonaAssetCreateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Create a persona asset record after direct upload to storage."""
    await _get_user_persona(persona_id, current_user.id, db, write=True)

    # Same trust rules as project assets: server-issued key + object present.
    expected_prefix = get_persona_upload_dir(persona_id, current_user.id)
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
        persona_id=persona_id,
        type=AssetType(request.type),
        file_url=request.key,
        title=request.title,
        processing_status=AssetStatus.PENDING,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@persona_assets_router.post(
    "/{persona_id}/assets/upload",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_persona_asset(
    persona_id: UUID,
    file: UploadFile = File(...),
    db: DBDep = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Upload a past material asset through the API (local/fallback)."""
    await _get_user_persona(persona_id, current_user.id, db, write=True)

    filename = file.filename or "unnamed"
    relative_path = await save_persona_upload(file.file, persona_id, current_user.id, filename)

    asset = Asset(
        user_id=current_user.id,
        persona_id=persona_id,
        type=AssetType.PAST_MATERIAL,
        file_url=relative_path,
        title=file.filename or None,
        processing_status=AssetStatus.PENDING,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@persona_assets_router.get("/{persona_id}/assets", response_model=list[AssetResponse])
async def list_persona_assets(
    persona_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
    type: AssetType = AssetType.PAST_MATERIAL,
) -> list[Asset]:
    """List a persona's assets of one kind (default: past materials).

    Voice samples live on the same row family; the voice section reads them
    with ``type=voice_sample`` while the materials tab keeps this default.
    """
    await _get_user_persona(persona_id, current_user.id if current_user else None, db)
    result = await db.execute(
        select(Asset)
        .where(Asset.persona_id == persona_id, Asset.type == type)
        .order_by(Asset.created_at.desc())
    )
    return list(result.scalars().all())


@persona_assets_router.post(
    "/{persona_id}/media/upload-url",
    response_model=AssetUploadUrlResponse,
)
async def create_persona_media_upload_url(
    persona_id: UUID,
    request: AssetUploadUrlRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> AssetUploadUrlResponse:
    """Return a presigned PUT URL for skin intro/outro media (image/video)."""
    await _get_user_persona(persona_id, current_user.id, db, write=True)

    key = str(await get_persona_upload_path(persona_id, current_user.id, request.filename))
    upload_url = await presign_upload(key, content_type=request.content_type)
    if upload_url is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        )
    return AssetUploadUrlResponse(key=key, upload_url=upload_url)


@persona_assets_router.post("/{persona_id}/media", status_code=status.HTTP_201_CREATED)
async def create_persona_media_from_key(
    persona_id: UUID,
    request: PersonaMediaCreateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict[str, str | None]:
    """Confirm a directly-uploaded skin media file and return its stream URL."""
    await _get_user_persona(persona_id, current_user.id, db, write=True)

    # Same trust rules as persona assets: server-issued key + object present.
    expected_prefix = get_persona_upload_dir(persona_id, current_user.id)
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
    return {"url": stream_url(request.key)}


@persona_assets_router.put("/{persona_id}/assets/{asset_id}", response_model=AssetResponse)
async def update_persona_asset(
    persona_id: UUID,
    asset_id: UUID,
    request: PersonaAssetUpdateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Asset:
    """Rename a persona asset (the storage key is untouched)."""
    await _get_user_persona(persona_id, current_user.id, db, write=True)
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.persona_id == persona_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    asset.title = request.title
    await db.commit()
    await db.refresh(asset)
    return asset


@persona_assets_router.delete(
    "/{persona_id}/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_persona_asset(
    persona_id: UUID,
    asset_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a persona asset."""
    await _get_user_persona(persona_id, current_user.id, db, write=True)
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.persona_id == persona_id)
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
