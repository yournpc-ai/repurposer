"""Authentication router: email verification code login."""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.dependencies import DBDep
from app.services.auth import (
    RateLimitError,
    create_access_token,
    create_verification_code,
    get_or_create_user,
    verify_code,
)
from app.services.email import send_verification_email

router = APIRouter()


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


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(
    data: SendCodeRequest,
    request: Request,
    db: DBDep,
) -> SendCodeResponse:
    """Send a verification code to the given email."""
    email = data.email.lower().strip()
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
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    return SendCodeResponse(message="Verification code sent")

    return SendCodeResponse(message="Verification code sent")


@router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_code_endpoint(
    data: VerifyCodeRequest,
    db: DBDep,
) -> VerifyCodeResponse:
    """Verify the code and return a JWT."""
    vc = await verify_code(db, data.email, data.code)
    if vc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user = await get_or_create_user(db, data.email)
    token = create_access_token(user.id)

    return VerifyCodeResponse(
        token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
        ),
    )
