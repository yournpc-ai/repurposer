"""Background worker process.

Run as ``python -m app.worker``. Polls the database for pending work and runs
it in a process separate from the API, so heavy jobs (text extraction, LLM
node execution, video rendering) never compete with online request handling.

Each tick claims at most one asset, up to ``_NODE_CONCURRENCY`` ready plan
nodes, and one render job via the ``FOR UPDATE SKIP LOCKED`` helpers in
:mod:`app.services.jobs`. Node execution runs as asyncio tasks so sibling
nodes of a run keep the parallelism the retired asyncio.gather fan-out had.
When all sources are empty the loop sleeps for
``settings.worker_poll_interval`` seconds. Processor failures are recorded on
the row and never crash the loop.
"""

import asyncio
from uuid import UUID

import structlog

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.services.asset_processing import process_asset
from app.services.distribution import (
    claim_due_publication,
    process_publication,
    reap_stale_publications,
)
from app.services.jobs import (
    claim_pending_asset,
    claim_pending_render,
    claim_ready_node,
    reap_stale,
)
from app.services.orchestrator import execute_node, finalize_stuck_runs
from app.services.rendering import render_output

logger = structlog.get_logger()

_NODE_CONCURRENCY = 4

_running_node_tasks: set[asyncio.Task] = set()


async def _tick() -> bool:
    """Claim and run units of work. Returns True if anything was processed."""
    did_work = False

    # Publications first (DISTRIBUTION.md §6): a scheduled publish is a time
    # promise to the user and must not queue behind ASR / nodes / renders.
    # The table is usually empty, so the check is nearly free.
    async with AsyncSessionLocal() as db:
        pub_id = await claim_due_publication(db)
    if pub_id is not None:
        did_work = True
        await process_publication(pub_id)

    async with AsyncSessionLocal() as db:
        asset_id = await claim_pending_asset(db)
    if asset_id is not None:
        did_work = True
        await process_asset(asset_id)

    # Fill up to the concurrency cap with ready nodes; each runs as its own
    # asyncio task (contextvars metering stays per-node).
    while len(_running_node_tasks) < _NODE_CONCURRENCY:
        async with AsyncSessionLocal() as db:
            node_id: UUID | None = await claim_ready_node(db)
        if node_id is None:
            break
        did_work = True
        task = asyncio.create_task(execute_node(node_id))
        _running_node_tasks.add(task)
        task.add_done_callback(_running_node_tasks.discard)

    async with AsyncSessionLocal() as db:
        render_id = await claim_pending_render(db)
    if render_id is not None:
        did_work = True
        await render_output(render_id)

    return did_work


async def run_worker() -> None:
    """Worker entrypoint: recover orphaned jobs, then poll forever."""
    logger.info("worker_starting", poll_interval=settings.worker_poll_interval)
    async with AsyncSessionLocal() as db:
        await reap_stale(db)
        await reap_stale_publications(db)
    await finalize_stuck_runs()

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
