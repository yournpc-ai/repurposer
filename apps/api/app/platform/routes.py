"""Platform-layer routes: file streaming / auth / notifications.

File streaming: the object storage bucket is public-read, so these endpoints
only perform ownership checks and redirect callers to the public object URL.
Range requests and delivery are handled entirely by the object store.

``?proxy=1`` streams the bytes through the API instead of redirecting, for
callers that ``fetch()`` the file programmatically: the 307 hop to the storage
origin is subject to CORS, and the bucket does not send ``Vary: Origin`` — a
no-cors ``<video>`` copy of the same object (e.g. a Remotion preview) poisons
the browser cache and makes later CORS fetches fail with "no ACAO header".
"""

import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import NotificationListResponse
from app.models.tables import User
from app.platform import notifications as svc
from app.platform.auth import (
    RateLimitError,
    create_access_token,
    create_verification_code,
    get_or_create_user,
    verify_code,
)
from app.platform.email import InvalidRecipientError, send_verification_email
from app.tools.storage import (
    download_to_temp,
    owner_from_path,
    presign_download,
    public_url,
)

files_router = APIRouter()


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


@files_router.get("/files/{file_path:path}")
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


@files_router.get("/outputs/{file_path:path}")
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


# ---- Auth (email verification code login) -----------------------------

auth_router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(raw: str) -> str:
    email = raw.lower().strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email address",
        )
    return email


class SendCodeRequest(BaseModel):
    email: str


class SendCodeResponse(BaseModel):
    message: str


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None


class VerifyCodeResponse(BaseModel):
    token: str
    user: UserResponse


@auth_router.post("/send-code", response_model=SendCodeResponse)
async def send_code(
    data: SendCodeRequest,
    request: Request,
    db: DBDep,
) -> SendCodeResponse:
    """Send a verification code to the given email."""
    email = _normalize_email(data.email)
    ip_address = request.client.host if request.client else None

    try:
        vc = await create_verification_code(db, email, ip_address)
    except RateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        ) from e
    try:
        await send_verification_email(email, vc.code)
    except InvalidRecipientError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    return SendCodeResponse(message="Verification code sent")


@auth_router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_code_endpoint(
    data: VerifyCodeRequest,
    db: DBDep,
) -> VerifyCodeResponse:
    """Verify the code and return a JWT."""
    email = _normalize_email(data.email)
    vc = await verify_code(db, email, data.code)
    if vc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user = await get_or_create_user(db, email)
    token = create_access_token(user.id)

    return VerifyCodeResponse(
        token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
        ),
    )


# ---- Notifications ----------------------------------------------------

notifications_router = APIRouter()


@notifications_router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    db: DBDep,
    user: User = Depends(get_current_user_required),
    limit: int = Query(default=30, le=100),
) -> NotificationListResponse:
    items, unread = await svc.list_notifications(db, user.id, limit=limit)
    return NotificationListResponse(items=items, unread_count=unread)


@notifications_router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> None:
    await svc.mark_all_read(db, user.id)
    await db.commit()
