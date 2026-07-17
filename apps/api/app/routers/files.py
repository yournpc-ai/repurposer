"""File streaming endpoints.

The object storage bucket is public-read, so these endpoints only perform
ownership checks and redirect callers to the public object URL. Range requests
and delivery are handled entirely by the object store.

``?proxy=1`` streams the bytes through the API instead of redirecting, for
callers that ``fetch()`` the file programmatically: the 307 hop to the storage
origin is subject to CORS, and the bucket does not send ``Vary: Origin`` — a
no-cors ``<video>`` copy of the same object (e.g. a Remotion preview) poisons
the browser cache and makes later CORS fetches fail with "no ACAO header".
"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

from app.dependencies import get_current_user
from app.models.tables import User
from app.services.storage import (
    download_to_temp,
    owner_from_path,
    presign_download,
    public_url,
)

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
    background: BackgroundTasks,
    proxy: bool = False,
    current_user: User | None = Depends(get_current_user),
):
    """Stream an uploaded source file by key."""
    _authorize_path(file_path, current_user)
    if proxy:
        tmp = await download_to_temp(file_path)
        if tmp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )
        background.add_task(tmp.unlink, missing_ok=True)
        return FileResponse(tmp, filename=Path(file_path).name)
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
    """Stream a rendered output (MP4/SRT) by key.

    ``?download=true`` redirects to a presigned GET carrying
    ``Content-Disposition: attachment`` so the browser saves the file instead
    of playing it inline.
    """
    _authorize_path(file_path, current_user)
    if download:
        url = await presign_download(file_path, filename=Path(file_path).name)
    else:
        url = public_url(file_path)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
