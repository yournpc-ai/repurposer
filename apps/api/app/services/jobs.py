"""Postgres-backed job queue primitives.

The database *is* the queue: pending work lives as rows (``Asset`` rows awaiting
processing, ``WorkflowRun`` rows awaiting generation). Workers claim a row with
``SELECT ... FOR UPDATE SKIP LOCKED``, which lets multiple workers run
concurrently without ever grabbing the same row. No Redis/broker required.

The claim helpers atomically flip a row out of its pending state before
returning it, so a claimed row is invisible to other workers' claim queries.
``reap_stale`` recovers rows orphaned by a crashed worker (left mid-flight in a
running state) on startup.

To scale horizontally later, only the claim mechanism here changes (e.g. swap
to arq/Celery + Redis); callers stay the same.
"""

from uuid import UUID

import structlog
from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetStatus, RenderStatus, WorkflowStatus
from app.models.tables import Asset, Clip, WorkflowRun

logger = structlog.get_logger()


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


async def claim_pending_run(db: AsyncSession) -> UUID | None:
    """Atomically claim one pending generation run, flipping it to RUNNING.

    Returns the claimed run id, or None if no run is pending.
    """
    result = await db.execute(
        select(WorkflowRun.id)
        .where(WorkflowRun.status == WorkflowStatus.PENDING)
        .order_by(WorkflowRun.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    run_id = result.scalar_one_or_none()
    if run_id is None:
        return None

    run_id = await db.scalar(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .values(status=WorkflowStatus.RUNNING)
        .returning(WorkflowRun.id)
    )
    await db.commit()
    return run_id


async def claim_pending_render(db: AsyncSession) -> UUID | None:
    """Atomically claim one clip awaiting render, flipping it to RENDERING."""
    result = await db.execute(
        select(Clip.id)
        .where(Clip.render_status == RenderStatus.PENDING)
        .order_by(Clip.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    clip_id = result.scalar_one_or_none()
    if clip_id is None:
        return None

    clip_id = await db.scalar(
        update(Clip)
        .where(Clip.id == clip_id)
        .values(render_status=RenderStatus.RENDERING, render_error=None)
        .returning(Clip.id)
    )
    await db.commit()
    return clip_id


async def reap_stale(db: AsyncSession) -> None:
    """Reset rows orphaned by a crashed worker back to pending.

    Run once on worker startup. In dev there is a single worker, so anything
    still in an in-flight state at boot must be from a previous crashed run.

    TODO: track attempts + backoff so a row that crashes the worker on every
    run does not loop forever; for now a stuck row can be reset via reprocess.
    """
    assets = await db.execute(
        update(Asset)
        .where(Asset.processing_status == AssetStatus.PROCESSING)
        .values(processing_status=AssetStatus.PENDING)
    )
    runs = await db.execute(
        update(WorkflowRun)
        .where(WorkflowRun.status == WorkflowStatus.RUNNING)
        .values(status=WorkflowStatus.PENDING)
    )
    renders = await db.execute(
        update(Clip)
        .where(Clip.render_status == RenderStatus.RENDERING)
        .values(render_status=RenderStatus.PENDING)
    )
    await db.commit()
    asset_count = assets.rowcount if isinstance(assets, CursorResult) else 0
    run_count = runs.rowcount if isinstance(runs, CursorResult) else 0
    render_count = renders.rowcount if isinstance(renders, CursorResult) else 0
    if asset_count or run_count or render_count:
        logger.info(
            "reaped_stale_jobs",
            assets=asset_count,
            runs=run_count,
            renders=render_count,
        )
