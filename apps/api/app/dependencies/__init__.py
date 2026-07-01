"""FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user, get_current_user_optional
from app.models.database import AsyncSessionLocal

__all__ = [
    "DBDep",
    "get_current_user",
    "get_current_user_optional",
    "get_db",
]


async def get_db() -> AsyncSession:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


DBDep = Annotated[AsyncSession, Depends(get_db)]
