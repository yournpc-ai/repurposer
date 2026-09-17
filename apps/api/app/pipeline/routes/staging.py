"""Staging upload router (Product Flow Alignment Batch A, contract
``docs/tasks/product-flow-alignment.md`` §5).

Pre-project uploads: the composer starts uploading the moment a file is
picked, so Generate never waits on the wire. Objects live under
``{user_id}/uploads/staging/{session_id}/`` — ownership is proven by the
key's user prefix, exactly like the project/persona upload gates. Attach
(``POST /projects/{id}/assets/from-staging`` in ``assets.py``) points an
asset row at the staging key as-is; unreferenced objects are reaped by
``app.pipeline.staging.reap_stale_staging_uploads``.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user_required
from app.models.schemas import AssetUploadUrlResponse, StagingUploadUrlRequest
from app.models.tables import User
from app.providers.storage import (
    delete_file,
    get_staging_upload_path,
    get_staging_upload_prefix,
    presign_upload,
)

router = APIRouter()


@router.post("/upload-url", response_model=AssetUploadUrlResponse)
async def create_staging_upload_url(
    request: StagingUploadUrlRequest,
    current_user: User = Depends(get_current_user_required),
) -> AssetUploadUrlResponse:
    """Return a presigned PUT URL for a pre-project staging upload."""
    key = str(
        await get_staging_upload_path(current_user.id, request.session_id, request.filename)
    )
    upload_url = await presign_upload(key, content_type=request.content_type)
    if upload_url is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        )
    return AssetUploadUrlResponse(key=key, upload_url=upload_url)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staging_object(
    key: str = Query(...),
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Best-effort delete of a staged object (the chip's × gesture).

    Only keys under the caller's own staging prefix are deletable — the same
    ownership rule as every other upload gate. Missing objects are fine
    (idempotent ×); anything the × misses is the reaper's job.
    """
    prefix = get_staging_upload_prefix(current_user.id)
    if not key.startswith(f"{prefix}/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid staging key",
        )
    await delete_file(key)
