"""Live pool-liveness proof (G0): a pooled connection that dies while idle
must be detected at checkout and transparently replaced.

Needs the configured local Postgres. Skips (not fails) when the database is
unreachable or not Postgres. Touches no data — connections only.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio


async def _kill_idle_pooled_connection(engine):
    """Check out a healthy connection, return it, then kill the underlying
    driver connection — the incident's shape: the connection dies while
    sitting idle in the pool, so nothing notices until the next checkout."""
    conn = await engine.connect()
    raw = await conn.get_raw_connection()
    driver_connection = getattr(raw, "driver_connection", None)
    if driver_connection is None:
        await conn.close()
        pytest.skip("driver connection shape not recognized")
    await conn.close()  # healthy checkin; pool holds the wrapper
    await driver_connection.close()  # server-side drop, while idle


async def _reachable(url: str) -> bool:
    probe = create_async_engine(url)
    try:
        async with probe.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await probe.dispose()


async def test_pre_ping_heals_stale_pooled_connection():
    from app.config import settings

    if not settings.database_url.startswith("postgresql"):
        pytest.skip("configured database is not Postgres")
    if not await _reachable(settings.database_url):
        pytest.skip("local database unreachable")

    # Control: WITHOUT pre_ping, the dead pooled connection is served as
    # healthy and the first use fails — the incident's InterfaceError.
    blind = create_async_engine(settings.database_url)
    try:
        await _kill_idle_pooled_connection(blind)
        with pytest.raises(Exception, match="(?i)closed"):
            async with blind.connect() as conn:
                await conn.execute(text("SELECT 1"))
    finally:
        await blind.dispose()

    # Mechanism: WITH pre_ping, checkout detects the corpse and replaces it.
    healing = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        await _kill_idle_pooled_connection(healing)
        async with healing.connect() as conn:
            assert (await conn.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await healing.dispose()
