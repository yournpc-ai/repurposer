"""Re-stamp one project's DRAFT graph from its docked task book (边对账律
heal, ADR-062, 2026-09-10).

The draft graph's rows are the compile's persisted truth — when the
compiler's law changes (ADR-061 变体并行律: modifiers fan out parallel, never
chain off siblings), an already-docked book keeps the OLD compile's edges.
The next Start would re-compile and re-stamp anyway, but the on-screen draft
stays wrong until then. This script replays the dock's own stamp
(``stamp_draft_graph`` — same fill keys, so nodes are reused in place) with
the current compiler; the stamp's edge reconciliation (ADR-062) retracts the
stale topology and the canvas heals WITHOUT starting the run.

Read source = the Start path's own: ``project.pending_brief`` → PendingBrief
→ intent.tasks. A project without a docked book (or with a run-born graph
only) is skipped — there is no draft to heal.

Usage (from apps/api/):
    uv run python scripts/restamp_draft_graph.py <project_id> [--lang zh]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import PendingBrief  # noqa: E402
from app.models.tables import Project  # noqa: E402

logger = structlog.get_logger()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id")
    # The stamp recomposes the book text / node summaries in this language
    # (graph_fill falls back to "en" on None) — pass the project's UI locale
    # or the heal rewrites a Chinese draft's labels to English.
    parser.add_argument("--lang", default="en")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, args.project_id)
        if project is None:
            raise SystemExit(f"project not found: {args.project_id}")
        pending = (
            PendingBrief.model_validate(project.pending_brief)
            if isinstance(project.pending_brief, dict)
            else None
        )
        if pending is None or pending.intent is None or not pending.intent.tasks:
            logger.info("restamp_skipped_no_docked_book", project_id=args.project_id)
            return
        from app.pipeline.graph_fill import stamp_draft_graph  # deferred: import cycle

        # 判词④ prose law: the docked verdict's own answer is the face.
        await stamp_draft_graph(
            db,
            project,
            list(pending.intent.tasks),
            args.lang,
            pending.intent.answer,
        )
        await db.commit()
        logger.info(
            "restamp_done",
            project_id=args.project_id,
            tasks=len(pending.intent.tasks),
            lang=args.lang,
        )


if __name__ == "__main__":
    asyncio.run(main())
