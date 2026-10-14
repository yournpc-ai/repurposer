"""Backfill the text leg on legacy pure-cut chains (2026-10-11 拍板 —
文字流接线): graphs stamped before the law carry only the video edge
asset→select_clips, so the T wire (transcript-section out-anchor → text
lane's in-anchor) never renders on them. The rule mirrors graph_fill's
birth law exactly: wherever a 'video' edge runs from a text-bearing media
asset (spec.asset_type ∈ {video, audio}) to a select_clips node and no
'text' edge exists for the same pair, insert one (out:text → in:text).
mode② chains are untouched (their video edge comes from a producer node,
not an asset); image/slides assets grow no text leg (no transcript).

A ONE-OFF corrective, not a script worth keeping (git 历史即档案).
Dry-run is the default; ``--yes`` applies.

Usage (from apps/api/):
    uv run python ../../scratch/backfill_text_wire.py [--yes]
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

import structlog  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import GraphEdge, GraphNode  # noqa: E402

logger = structlog.get_logger()


async def main(yes: bool) -> None:
    async with AsyncSessionLocal() as db:
        nodes = (
            (await db.execute(select(GraphNode.id, GraphNode.project_id, GraphNode.type, GraphNode.spec)))
            .all()
        )
        by_id = {str(n.id): n for n in nodes}
        edges = (
            await db.execute(
                select(GraphEdge.from_node, GraphEdge.to_node, GraphEdge.edge_type)
            )
        ).all()
        have = {(str(f), str(t), et) for f, t, et in edges}

        candidates: list[tuple[GraphNode, GraphNode]] = []
        for f, t, et in edges:
            if et != "video":
                continue
            src, dst = by_id.get(str(f)), by_id.get(str(t))
            if src is None or dst is None:
                continue
            if src.type != "asset":
                continue  # mode②: producer-fed chains never grow the leg here
            if (src.spec or {}).get("asset_type") not in ("video", "audio"):
                continue  # no transcript section → no T anchor (image/slides)
            if str((dst.spec or {}).get("tool") or "") != "select_clips":
                continue  # translate/dub roots keep the doc-station transit
            if (str(f), str(t), "text") in have:
                continue  # already wired (born after the law)
            candidates.append((src, dst))

        for src, dst in candidates:
            logger.info(
                "text_leg_candidate",
                project=str(src.project_id),
                from_node=str(src.id),
                to_node=str(dst.id),
                asset_type=(src.spec or {}).get("asset_type"),
            )
        logger.info("backfill_plan", mode="apply" if yes else "dry-run", count=len(candidates))
        if not yes:
            return
        for src, dst in candidates:
            db.add(
                GraphEdge(
                    id=uuid4(),
                    project_id=src.project_id,
                    from_node=src.id,
                    from_port="out:text",
                    to_node=dst.id,
                    to_port="in:text",
                    edge_type="text",
                )
            )
        await db.commit()
        logger.info("backfill_applied", count=len(candidates))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="apply (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(main(args.yes))
