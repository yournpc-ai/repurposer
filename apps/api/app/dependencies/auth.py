"""Authentication dependencies.

Supports JWT bearer tokens for real users. Anonymous requests are represented
by ``None``; routes that need public read access can fall back to shared
default-user data explicitly in the router. There is no local-development
bypass: login always requires a verification code.
"""

from datetime import timedelta

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.tables import LoginSession, User, now_utc
from app.platform.auth import session_claims

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


async def _get_user_from_token(db: AsyncSession, token: str, agent: str) -> User | None:
    claims = session_claims(token)
    if claims is None:
        return None
    user_id, session_id, expires, legacy = claims
    session = await db.get(LoginSession, session_id)
    user = await db.get(User, user_id)
    if user is None:
        return None
    if session is None and legacy:
        await db.execute(
            insert(LoginSession)
            .values(
                id=session_id,
                user_id=user_id,
                user_agent=agent[:512],
                expires_at=expires,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        await db.commit()
        session = await db.get(LoginSession, session_id)
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        return None
    if now_utc() - session.last_seen_at > timedelta(minutes=5):
        session.last_seen_at = now_utc()
        await db.commit()
    return user


async def get_current_user(
    request: Request,
    authorization: str | None = Depends(_header_token),
) -> User | None:
    """Resolve the current user from a JWT bearer token.

    - Returns the authenticated user for valid tokens.
    - Returns ``None`` for anonymous requests (no token).
    - Raises 401 for invalid or expired tokens.

    Endpoints that need public read access can accept ``None`` and fall back to
    shared default-user data explicitly in the router.
    """
    async with AsyncSessionLocal() as db:
        if not authorization:
            return None
        user = await _get_user_from_token(db, authorization, request.headers.get("user-agent", ""))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


async def get_current_user_required(
    request: Request,
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
        user = await _get_user_from_token(db, authorization, request.headers.get("user-agent", ""))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


async def get_current_user_optional(
    request: Request,
    authorization: str | None = Depends(_header_token),
) -> User | None:
    """Alias for ``get_current_user``."""
    return await get_current_user(request, authorization)
