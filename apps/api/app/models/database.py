"""Database setup."""

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

Base = declarative_base()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_alembic_config() -> AlembicConfig:
    """Return an Alembic config pointing at the project migrations."""
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return alembic_cfg


async def init_db() -> None:
    """Initialize database by running Alembic migrations to head."""
    alembic_cfg = get_alembic_config()
    command.upgrade(alembic_cfg, "head")
