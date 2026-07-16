"""File streaming endpoints.

The object storage bucket is public-read, so these endpoints only perform
ownership checks and redirect callers to the public object URL. Range requests
and delivery are handled entirely by the object store.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_current_user
from app.models.tables import User
from app.services.storage import owner_from_path, public_url

router = APIRouter()


def _authorize_path(file_path: str, current_user: User | None) -> None:
    """Refuse access unless the path belongs to the current user or is demo."""
    owner = owner_from_path(file_path)
    if owner == "demo":
        return
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    try:
        if UUID(owner) == current_user.id:
            return
    except ValueError:
        pass
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied",
    )


@router.get("/files/{file_path:path}")
async def stream_upload(
    file_path: str,
    current_user: User | None = Depends(get_current_user),
):
    """Stream an uploaded source file by key."""
    _authorize_path(file_path, current_user)
    url = public_url(file_path)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/outputs/{file_path:path}")
async def stream_output(
    file_path: str,
    download: bool = False,
    current_user: User | None = Depends(get_current_user),
):
    """Stream a rendered output (MP4/SRT) by key."""
    _authorize_path(file_path, current_user)
    url = public_url(file_path)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    if download:
        url = f"{url}?download=1"
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
