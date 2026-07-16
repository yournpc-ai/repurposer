"""Authentication dependencies.

Supports JWT bearer tokens for real users. Anonymous requests are represented
by ``None``; routes that need public read access can fall back to shared
default/demo data explicitly in the router. There is no local-development
bypass: login always requires a verification code.
"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _get_user_from_token(db: AsyncSession, token: str) -> User | None:
    """Resolve a user from a JWT bearer token."""
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    authorization: str | None = Depends(_header_token),
) -> User | None:
    """Resolve the current user from a JWT bearer token.

    - Returns the authenticated user for valid tokens.
    - Returns ``None`` for anonymous requests (no token).
    - Raises 401 for invalid or expired tokens.

    Endpoints that need public read access can accept ``None`` and fall back to
    shared default/demo data explicitly in the router.
    """
    async with AsyncSessionLocal() as db:
        if not authorization:
            return None
        user = await _get_user_from_token(db, authorization)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


async def get_current_user_required(
    authorization: str | None = Depends(_header_token),
) -> User:
    """Require a valid JWT bearer token; no anonymous or default-user fallback."""
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
    """Alias for ``get_current_user``."""
    return await get_current_user(authorization)
