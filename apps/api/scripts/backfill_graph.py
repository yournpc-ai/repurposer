"""One-time graph backfill (ADR-057 K2, 简报 §3 存量数据).

Stamps the persistent graph (graph_nodes / graph_edges) for every existing
project from its LATEST run's persisted workflow_steps — the same
``stamp_run_graph`` create_run uses (the compile is fully persisted on the
step rows, so the replay is exact) — plus an asset node per asset row.

Dev-phase posture (简报): a per-project failure is logged and skipped, never
fatal to the batch — ``reset_db`` regeneration is the sanctioned fallback.

Usage (from apps/api/):
    uv run python scripts/backfill_graph.py
"""

import asyncio
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Asset, Project, WorkflowRun, WorkflowStep  # noqa: E402

logger = structlog.get_logger()


async def main() -> None:
    from app.pipeline.graph_fill import (
        stamp_asset_node,
        stamp_run_graph,
        stamp_transcript_node,
    )

    async with AsyncSessionLocal() as db:
        projects = list((await db.execute(select(Project))).scalars().all())
        stamped = skipped = 0
        for project in projects:
            try:
                assets = list(
                    (
                        await db.execute(
                            select(Asset).where(Asset.project_id == project.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for asset in assets:
                    await stamp_asset_node(db, project.id, asset)
                    # 转写稿 document — same idempotent ensure as the stamps.
                    await stamp_transcript_node(db, project.id, asset)
                latest_run = (
                    await db.execute(
                        select(WorkflowRun)
                        .where(WorkflowRun.project_id == project.id)
                        .order_by(WorkflowRun.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if latest_run is not None:
                    steps = list(
                        (
                            await db.execute(
                                select(WorkflowStep)
                                .where(WorkflowStep.run_id == latest_run.id)
                                .order_by(WorkflowStep.seq)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if steps:
                        await stamp_run_graph(db, project, latest_run, steps)
                        # The backfill replays HISTORY: the nodes leave the
                        # stamp at queued, then settle to the step family's
                        # terminal aggregate in one pass.
                        from app.pipeline.graph_fill import sync_graph_node_for_step

                        for step in steps:
                            await sync_graph_node_for_step(db, step)
                await db.commit()
                stamped += 1
            except Exception as exc:  # noqa: BLE001 — per-project isolation
                await db.rollback()
                skipped += 1
                logger.warning(
                    "graph_backfill_project_failed",
                    project_id=str(project.id),
                    error=str(exc),
                )
        logger.info("graph_backfill_done", projects=stamped, skipped=skipped)


if __name__ == "__main__":
    asyncio.run(main())
