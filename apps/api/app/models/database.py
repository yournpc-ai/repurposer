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
    # Dead-connection detection at checkout: the 2026-10-19 incident window
    # showed asyncpg `InterfaceError: connection is closed` surfacing on
    # unrelated requests — stale pooled connections served as healthy.
    # pre_ping runs a cheap liveness probe at checkout and transparently
    # recycles dead connections. `pool_recycle` is deliberately NOT set: it
    # only helps against a fixed server-side idle TTL, and no such TTL is
    # evidenced in this deployment — a guessed value would churn healthy
    # connections without addressing the observed failure mode.
    pool_pre_ping=True,
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
