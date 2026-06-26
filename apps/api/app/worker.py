"""Background worker process.

Run as ``python -m app.worker``. Polls the database for pending work and runs
it in a process separate from the API, so heavy jobs (text extraction today;
ASR / OCR / video rendering later) never compete with online request handling.

Each tick claims at most one asset and one generation run via the
``FOR UPDATE SKIP LOCKED`` helpers in :mod:`app.services.jobs`; when both
sources are empty the loop sleeps for ``settings.worker_poll_interval`` seconds.
Processor failures are recorded on the row and never crash the loop.
"""

import asyncio

import structlog

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.services.asset_processing import process_asset
from app.services.generation import run_generation
from app.services.jobs import (
    claim_pending_asset,
    claim_pending_render,
    claim_pending_run,
    reap_stale,
)
from app.services.rendering import render_clip

logger = structlog.get_logger()


async def _tick() -> bool:
    """Claim and run one unit of work. Returns True if anything was processed."""
    did_work = False

    async with AsyncSessionLocal() as db:
        asset_id = await claim_pending_asset(db)
    if asset_id is not None:
        did_work = True
        await process_asset(asset_id)

    async with AsyncSessionLocal() as db:
        run_id = await claim_pending_run(db)
    if run_id is not None:
        did_work = True
        await run_generation(run_id)

    async with AsyncSessionLocal() as db:
        render_id = await claim_pending_render(db)
    if render_id is not None:
        did_work = True
        await render_clip(render_id)

    return did_work


async def run_worker() -> None:
    """Worker entrypoint: recover orphaned jobs, then poll forever."""
    logger.info("worker_starting", poll_interval=settings.worker_poll_interval)
    async with AsyncSessionLocal() as db:
        await reap_stale(db)

    while True:
        try:
            did_work = await _tick()
        except Exception as e:  # noqa: BLE001 — keep the loop alive on any error
            logger.error("worker_tick_failed", error=str(e))
            did_work = False
        if not did_work:
            await asyncio.sleep(settings.worker_poll_interval)


def main() -> None:
    """Synchronous entrypoint for ``python -m app.worker``."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("worker_stopped")


if __name__ == "__main__":
    main()
