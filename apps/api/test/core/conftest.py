"""Shared disposable-database fixtures for core API tests."""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.database import Base


@pytest.fixture
def installed_promo(tmp_path, monkeypatch):
    release = tmp_path / "promo-video" / "test-release"
    release.mkdir(parents=True)
    (release / "SKILL.md").write_text(
        "---\nname: video-shotcraft\ndescription: Test creative method\n---\nUse real source evidence.\n"
    )
    monkeypatch.setattr(settings, "managed_skill_root", tmp_path)
    monkeypatch.setattr(settings, "managed_skill_versions", {"promo-video": "test-release"})


@pytest_asyncio.fixture
async def database():
    name = f"rep_core_test_{uuid4().hex[:12]}"
    server = settings.database_url.rsplit("/", 1)[0]
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(f"{server}/{name}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()
