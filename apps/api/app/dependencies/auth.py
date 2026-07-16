"""Authentication dependencies.

Supports JWT bearer tokens for real users, with an optional fallback to the
seeded default user for local development.
"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.tables import User
from app.services.auth import decode_access_token

DEFAULT_USER_EMAIL = "default@repurposer.local"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _header_token(authorization: str | None = Header(None)) -> str | None:
    """Extract a bearer token from the Authorization header, if present."""
    if not authorization:
        return None
    parts = authorization.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


async def _get_default_user(db: AsyncSession) -> User:
    """Return the seeded default user; create it if missing."""
    result = await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=DEFAULT_USER_ID, email=DEFAULT_USER_EMAIL, name="Default User")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _get_user_from_token(db: AsyncSession, token: str) -> User | None:
    """Resolve a user from a JWT bearer token."""
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    authorization: str | None = Depends(_header_token),
) -> User:
    """Resolve the current user.

    - If a valid bearer token is provided, return the corresponding user.
    - Otherwise, when ``auth_allow_default_user`` is True, fall back to the
      seeded default user (local development).
    - Otherwise, raise 401.
    """
    async with AsyncSessionLocal() as db:
        if authorization:
            user = await _get_user_from_token(db, authorization)
            if user is not None:
                return user

        if settings.auth_allow_default_user:
            return await _get_default_user(db)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_required(
    authorization: str | None = Depends(_header_token),
) -> User:
    """Require a valid JWT bearer token; no default-user fallback."""
    async with AsyncSessionLocal() as db:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = await _get_user_from_token(db, authorization)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


async def get_current_user_optional(
    authorization: str | None = Depends(_header_token),
) -> User | None:
    """Optional variant: return the user if authenticated, else None."""
    async with AsyncSessionLocal() as db:
        if authorization:
            user = await _get_user_from_token(db, authorization)
            if user is not None:
                return user
        if settings.auth_allow_default_user:
            result = await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
            return result.scalar_one_or_none()
        return None
