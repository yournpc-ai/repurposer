"""Root pytest configuration for Rookie Cut's 4-Layer Chat-Origin Test Architecture.

Performance architecture:
- ONE disposable PostgreSQL database is created once per pytest session via synchronous
  psycopg2 + ``Base.metadata.create_all`` with ``synchronous_commit = off`` (~2 s once)
  and dropped once at session end.
- Every DB test receives a pristine schema via a single pooled-connection batched
  ``DELETE`` across all 31 tables (~5-7 ms per test instead of ~2,100 ms per-test
  ``CREATE DATABASE`` + ``create_all`` or ~600-6,800 ms ``TRUNCATE`` relfilenode fsyncs).
- Each test binds a fresh ``AsyncEngine`` to its own asyncio event loop and disposes it
  cleanly in ``finally`` so zero connection-pool warnings or cross-loop errors occur.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models import (
    tables as _tables,  # noqa: F401 -- ensure all tables register on Base.metadata
)
from app.models.database import Base
from test.support.db_helpers import disposable_postgres
from test.support.sfx_import import sfx_import_race  # noqa: F401 -- shared fixture


@pytest.fixture(scope="session")
def _disposable_postgres():
    with disposable_postgres() as (async_db_url, sync_db_url):
        # Keep 1 persistent sync connection so per-test cleanup avoids TCP/auth reconnect overhead
        cleanup_engine = create_engine(sync_db_url, pool_size=1, max_overflow=0)
        try:
            Base.metadata.create_all(cleanup_engine)
            reverse_tables = [t.name for t in reversed(Base.metadata.sorted_tables)]
            delete_stmts = "".join(f'DELETE FROM "{t}";' for t in reverse_tables)

            replica_sql = text(f"SET LOCAL session_replication_role = 'replica'; {delete_stmts}")
            fallback_sql = text(
                f'UPDATE "compositions" SET current_version_id = NULL; {delete_stmts}'
            )
            try:
                with cleanup_engine.begin() as conn:
                    conn.execute(replica_sql)
                cleanup_sql = replica_sql
            except Exception:
                with cleanup_engine.begin() as conn:
                    conn.execute(fallback_sql)
                cleanup_sql = fallback_sql

            yield async_db_url, cleanup_engine, cleanup_sql
        finally:
            cleanup_engine.dispose()


@pytest_asyncio.fixture
async def database(_disposable_postgres):
    async_db_url, cleanup_engine, cleanup_sql = _disposable_postgres
    with cleanup_engine.begin() as conn:
        conn.execute(cleanup_sql)

    engine = create_async_engine(async_db_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def installed_promo(tmp_path, monkeypatch):
    release = tmp_path / "promo-video" / "test-release"
    release.mkdir(parents=True)
    (release / "SKILL.md").write_text(
        "---\nname: video-shotcraft\ndescription: Test creative method\n---\nUse real source evidence.\n"
    )
    monkeypatch.setattr(settings, "managed_skill_root", tmp_path)
    monkeypatch.setattr(settings, "managed_skill_versions", {"promo-video": "test-release"})


@pytest.fixture
def cleanup_calls(monkeypatch):
    projects = import_module("app.pipeline.routes.projects")
    unlink, prefix = AsyncMock(), AsyncMock()
    monkeypatch.setattr(projects, "delete_file", unlink)
    monkeypatch.setattr(projects, "delete_project_files", prefix)
    return unlink, prefix


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Automatically apply layer markers (`unit`, `chat_origin`, `infra`) by directory."""
    for item in items:
        parts = Path(str(item.fspath)).parts
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "chat_origin" in parts:
            item.add_marker(pytest.mark.chat_origin)
        elif "infra" in parts:
            item.add_marker(pytest.mark.infra)
