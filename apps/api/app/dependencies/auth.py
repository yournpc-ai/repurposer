"""Authentication dependencies.

The MVP ships without a login UI. All data is owned by a seeded default user.
When real authentication is added, ``get_current_user`` can parse a JWT from the
``Authorization`` header and return the corresponding user without changing
router signatures.
"""

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.tables import User

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


async def get_current_user(
    authorization: str | None = Depends(_header_token),
) -> User:
    """Resolve the current user.

    - If a bearer token is provided, it is currently ignored and the default user
      is returned. JWT parsing will be wired here later.
    - Otherwise the seeded default user is returned.

    Callers receive a real ``User`` row and can scope queries by ``user.id``.
    """
    async with AsyncSessionLocal() as db:
        # TODO: parse JWT from ``authorization`` and look up the real user.
        _ = authorization  # reserved for future JWT auth
        return await _get_default_user(db)


async def get_current_user_optional(
    authorization: str | None = Depends(_header_token),
) -> User | None:
    """Optional variant: returns the default user or None if not seeded."""
    async with AsyncSessionLocal() as db:
        _ = authorization
        result = await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
        return result.scalar_one_or_none()
