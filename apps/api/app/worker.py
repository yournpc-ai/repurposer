"""Background worker process.

Run as ``python -m app.worker``. Polls the database for pending work and runs
it in a process separate from the API, so heavy jobs (text extraction, LLM
node execution, video rendering) never compete with online request handling.

Each tick claims at most one asset, up to ``_NODE_CONCURRENCY`` ready plan
nodes, and one render job via the ``FOR UPDATE SKIP LOCKED`` helpers in
:mod:`app.pipeline.jobs`. Node execution runs as asyncio tasks so sibling
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
from app.pipeline.asset_processing import process_asset
from app.distribution import (
    claim_due_publication,
    process_publication,
    reap_stale_publications,
)
from app.pipeline.jobs import (
    STALE_NODE_REAP_SECONDS,
    claim_pending_asset,
    claim_pending_render,
    claim_ready_node,
    reap_stale,
    reap_stale_nodes_older_than,
)
from app.pipeline.orchestrator import (
    execute_step,
    expire_stale_interrupts,
    finalize_stuck_runs,
)
from app.pipeline.orchestrator import assert_runners_registered
from app.pipeline.rendering import render_output
from app.pipeline.staging import reap_stale_staging_uploads

# Composition-root seam wiring (ADR-087 §6): the trigger fires happen in this
# process (node runners / finalization), so the Agent Interface's trigger
# turn subscribes here at boot — the only legal pipeline → chat edge.
from app.chat.trigger_turn import fire_trigger as _trigger_turn_fire
from app.pipeline.trigger_events import register_trigger_handler

register_trigger_handler(_trigger_turn_fire)

logger = structlog.get_logger()

_NODE_CONCURRENCY = 4

# Staging GC (Batch A, I-PFA-08): S3 listing is not free, so the reaper runs
# on a slow cadence inside the tick loop rather than every tick.
_STAGING_REAP_INTERVAL_SECONDS = 3600
_last_staging_reap = 0.0

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
        task = asyncio.create_task(execute_step(node_id))
        _running_node_tasks.add(task)
        task.add_done_callback(_running_node_tasks.discard)

    # Expire interrupts parked past their TTL: the auto-answer unblocks
    # their runs (claimed on a later tick). Silent when nothing is parked.
    if await expire_stale_interrupts():
        did_work = True

    # Age-based node reap (chat-flow-sequencing D2): a node sitting in
    # ``running`` past the threshold was orphaned by a dead event loop (the
    # execute_step fence caps real work well under it) — reset it to pending
    # so a live tick claims it again. Runs every tick; cheap when empty.
    async with AsyncSessionLocal() as db:
        await reap_stale_nodes_older_than(db, STALE_NODE_REAP_SECONDS)

    async with AsyncSessionLocal() as db:
        render_id = await claim_pending_render(db)
    if render_id is not None:
        did_work = True
        await render_output(render_id)

    # Staging GC (Batch A): expired, unreferenced pre-project uploads.
    # Hourly cadence; failures stay inside the reaper (log + next pass).
    global _last_staging_reap  # noqa: PLW0603
    now = asyncio.get_running_loop().time()
    if now - _last_staging_reap >= _STAGING_REAP_INTERVAL_SECONDS:
        _last_staging_reap = now
        await reap_stale_staging_uploads()

    return did_work


async def run_worker() -> None:
    """Worker entrypoint: recover orphaned jobs, then poll forever."""
    assert_runners_registered()
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
