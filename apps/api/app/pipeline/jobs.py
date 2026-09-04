"""Postgres-backed job queue primitives.

The database *is* the queue: pending work lives as rows (``Asset`` rows awaiting
processing, ``workflow_steps`` awaiting execution, ``outputs`` awaiting render).
Workers claim a row with ``SELECT ... FOR UPDATE SKIP LOCKED``, which lets
multiple workers run concurrently without ever grabbing the same row.
No Redis/broker required.

The claim helpers atomically flip a row out of its pending state before
returning it, so a claimed row is invisible to other workers' claim queries.
``reap_stale`` recovers rows orphaned by a crashed worker (left mid-flight in a
running state): at startup with no threshold (the historical full sweep), and
from every tick with an age threshold (nodes only — see the docstring).

To scale horizontally later, only the claim mechanism here changes (e.g. swap
to arq/Celery + Redis); callers stay the same.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import CursorResult, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetStatus, RenderStatus
from app.models.tables import Asset, Output, WorkflowStep
from app.pipeline.graph import runtime_fanout_kinds

logger = structlog.get_logger()


def _runtime_fanout_sql() -> str:
    """Fan-out kinds (render, D2) as a SQL literal list — node-declared
    (`runtime_fanout`), consumed kernel-wide. Built lazily: this module is
    imported before the registry door opens, so a module-level constant would
    freeze an empty set. Values are code constants, never user input."""
    return ", ".join(f"'{k}'" for k in sorted(runtime_fanout_kinds()))


async def claim_pending_asset(db: AsyncSession) -> UUID | None:
    """Atomically claim one pending asset, flipping it to PROCESSING.

    Returns the claimed asset id, or None if no asset is pending. Uses
    ``FOR UPDATE SKIP LOCKED`` so concurrent workers never claim the same row.
    """
    result = await db.execute(
        select(Asset.id)
        .where(Asset.processing_status == AssetStatus.PENDING)
        .order_by(Asset.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    asset_id = result.scalar_one_or_none()
    if asset_id is None:
        return None

    asset_id = await db.scalar(
        update(Asset)
        .where(Asset.id == asset_id)
        .values(processing_status=AssetStatus.PROCESSING, processing_error=None)
        .returning(Asset.id)
    )
    await db.commit()
    return asset_id


async def claim_ready_node(db: AsyncSession) -> UUID | None:
    """Atomically claim one ready workflow step, flipping it to ``running``.

    A node is ready when it is pending and every upstream node (its ``inputs``
    edge list) is done. Render nodes are excluded — they are claimed through
    ``outputs.render_status`` (D2: the render chain owns their lifecycle).
    Runs whose project still has assets being processed are gated off, exactly
    like the retired run-level claim.

    Single UPDATE...RETURNING statement, so the claim is atomic under
    concurrent workers. Also flips the owning run PENDING -> RUNNING.
    """
    node_id = (
        await db.execute(
            text(
                f"""
                UPDATE workflow_steps pn
                SET status = 'running',
                    started_at = now(),
                    attempt = attempt + 1,
                    updated_at = now()
                WHERE pn.id = (
                    SELECT pn2.id
                    FROM workflow_steps pn2
                    JOIN workflow_runs r ON r.id = pn2.run_id
                    WHERE pn2.status = 'pending'
                      AND pn2.kind NOT IN ({_runtime_fanout_sql()})
                      AND NOT EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements_text(pn2.inputs) AS up(id)
                        JOIN workflow_steps upn ON upn.id = up.id::uuid
                        WHERE upn.status <> 'done'
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM assets a
                        WHERE a.project_id = r.project_id
                          AND a.processing_status IN ('PENDING', 'PROCESSING')
                      )
                    ORDER BY pn2.seq, pn2.created_at
                    LIMIT 1
                    FOR UPDATE OF pn2 SKIP LOCKED
                )
                RETURNING pn.id
                """
            )
        )
    ).scalar_one_or_none()
    if node_id is None:
        return None

    await db.execute(
        text(
            "UPDATE workflow_runs SET status = 'RUNNING', updated_at = now() "
            "WHERE id = (SELECT run_id FROM workflow_steps WHERE id = :nid) "
            "AND status = 'PENDING'"
        ),
        {"nid": node_id},
    )
    await db.commit()
    return node_id


async def claim_pending_render(db: AsyncSession) -> UUID | None:
    """Atomically claim one clip output awaiting render, flipping it to RENDERING."""
    result = await db.execute(
        select(Output.id)
        .where(Output.type == "clip")
        .where(Output.render_status == RenderStatus.PENDING)
        .order_by(Output.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    output_id = result.scalar_one_or_none()
    if output_id is None:
        return None

    output_id = await db.scalar(
        update(Output)
        .where(Output.id == output_id)
        .values(render_status=RenderStatus.RENDERING, render_error=None)
        .returning(Output.id)
    )
    # Mirror the fan-out node (if any) to running.
    await db.execute(
        text(
            f"UPDATE workflow_steps SET status = 'running', started_at = now(), "
            "updated_at = now() "
            f"WHERE kind IN ({_runtime_fanout_sql()}) AND status = 'pending' "
            "AND spec->>'output_id' = :oid"
        ),
        {"oid": str(output_id)},
    )
    await db.commit()
    return output_id


# Age threshold for the periodic (per-tick) node reap, in seconds
# (chat-flow-sequencing D2): healthy LLM nodes finish ≤ ~180s (the provider
# client bounds every call at 120–180s), so 900s is a wide lane — a node
# older than this is orphaned by a dead event loop, not working.
STALE_NODE_REAP_SECONDS = 900.0


async def reap_stale(db: AsyncSession) -> None:
    """Startup full sweep: reset rows orphaned by a crashed worker.

    Every in-flight row is a crash leftover — the single-worker dev
    assumption. That assumption has a documented hazard: a stale ORPHAN
    worker process (same dev box, days-old code) can still hold rows it
    will never finish; the startup sweep of the LIVE worker then resets
    those rows to pending, which is the wanted rescue — but under that
    same single-instance assumption a startup sweep on a second live
    worker would reset its healthy in-flight rows too. Age-based reaping
    (``reap_stale_nodes_older_than``, the worker's every-tick sweep) is
    immune to that, which is one reason the periodic sweep exists.

    TODO: track attempts + backoff so a row that crashes the worker on
    every run does not loop forever; for now a stuck row can be reset via
    reprocess.
    """
    assets = await db.execute(
        update(Asset)
        .where(Asset.processing_status == AssetStatus.PROCESSING)
        .values(processing_status=AssetStatus.PENDING)
    )
    nodes = await db.execute(
        update(WorkflowStep)
        .where(WorkflowStep.status == "running")
        .values(status="pending")
    )
    renders = await db.execute(
        update(Output)
        .where(Output.render_status == RenderStatus.RENDERING)
        .values(render_status=RenderStatus.PENDING)
    )
    await db.commit()
    asset_count = assets.rowcount if isinstance(assets, CursorResult) else 0
    node_count = nodes.rowcount if isinstance(nodes, CursorResult) else 0
    render_count = renders.rowcount if isinstance(renders, CursorResult) else 0
    if asset_count or node_count or render_count:
        logger.info(
            "reaped_stale_jobs",
            assets=asset_count,
            nodes=node_count,
            renders=render_count,
        )


async def reap_stale_nodes_older_than(db: AsyncSession, older_than_seconds: float) -> None:
    """Periodic age-based sweep (the worker's every tick): NODES ONLY, and
    only ones in ``running`` longer than the threshold (``started_at <
    now() - threshold``). Assets and renders stay startup-sweep-only on
    purpose: rendering already carries its own 900s httpx fence, and ASR of
    a long video legitimately outlives any threshold we can confidently
    set — reaping those mid-work would loop the reprocessing, not rescue
    it. Split out of ``reap_stale`` (2026-09-05 减法批): the threshold was
    a ``None`` sentinel switching WHICH tables get touched — a mode switch
    dressed as a filter, now two honestly-named operations.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
    nodes = await db.execute(
        update(WorkflowStep)
        .where(WorkflowStep.status == "running")
        .where(WorkflowStep.started_at < cutoff)
        .values(status="pending")
    )
    await db.commit()
    node_count = nodes.rowcount if isinstance(nodes, CursorResult) else 0
    if node_count:
        logger.info(
            "reaped_stale_nodes",
            nodes=node_count,
            older_than_seconds=older_than_seconds,
        )
