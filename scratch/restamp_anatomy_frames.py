"""Re-stamp legacy node frames born before the card-anatomy reservations
(ADR-113 转写稿折叠 / ADR-115 NLE 检视轴) — a ONE-OFF corrective, not a
script worth keeping (一次性迁移, git 历史即档案).

The frame law is birth-pinned, but these frames were born against an
anatomy that did not exist yet; the read face absorbs the gap by crushing
the media (an asset card's 16:9 stage renders 98px tall in a 295px frame).
The oracle is the birth seat itself — ``_frame_of(type, spec)``: a row is
re-stamped only when its stored frame is EXACTLY the current birth height
minus the missing reservation (text-bearing asset: _TRANSCRIPT_SECTION_PX;
tracked clip: _NLE_AXIS_PX). Any other mismatch is reported and left
untouched. Widths never change. Island members are refused (their y is
island-relative and the reserved bottom is a frozen island mirror).

Growing a frame pushes same-column followers down so each keeps the
law's gap (_GAP_CROSS); followers with a larger original gap keep it.
Dry-run is the default; ``--yes`` applies.

Usage (from apps/api/):
    uv run python ../../scratch/restamp_anatomy_frames.py [--yes]
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

import structlog  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import GraphNode  # noqa: E402
from app.pipeline.graph_store import (  # noqa: E402
    _frame_of,
    _GAP_CROSS,
    _NLE_AXIS_PX,
    _TRACKED_CLIP_TOOLS,
    _TRANSCRIPT_SECTION_PX,
)

logger = structlog.get_logger()


def _missing_reservation(node: GraphNode) -> tuple[int, int] | None:
    """(delta, expected_h) when the stored frame is exactly one anatomy
    reservation short of today's birth law; None otherwise."""
    spec = node.spec or {}
    h = (node.layout or {}).get("h")
    if not isinstance(h, int):
        return None
    expected = _frame_of(node.type, spec)[1]
    if spec.get("asset_type") in ("video", "audio"):
        delta = _TRANSCRIPT_SECTION_PX
    elif str(spec.get("tool") or "") in _TRACKED_CLIP_TOOLS:
        delta = _NLE_AXIS_PX
    else:
        return None
    if h == expected - delta:
        return delta, expected
    return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="apply (default: dry-run)")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(GraphNode))).scalars().all()
        by_project: dict[str, list[GraphNode]] = {}
        for row in rows:
            by_project.setdefault(str(row.project_id), []).append(row)

        changed: set = set()
        now = datetime.now(UTC)
        for project_id, nodes in by_project.items():
            members = [n for n in nodes if not (n.spec or {}).get("island")]
            grown = [n for n in members if _missing_reservation(n) is not None]
            for node in grown:
                _delta, expected = _missing_reservation(node)  # type: ignore[misc]
                logger.info(
                    "restamp",
                    project=project_id[:8],
                    node=str(node.id)[:8],
                    type=node.type,
                    h=f"{node.layout['h']} -> {expected}",
                )
                # Apply in memory now so the column walk below sees the
                # grown bottom (rolled back with the session on dry-run).
                node.layout = {**node.layout, "h": expected}
                node.updated_at = now
                changed.add(node.id)

            # Same-column followers keep the law's gap under a grown node.
            grown_x = {(n.layout or {}).get("x") for n in grown}
            for x in grown_x:
                col = [n for n in members if (n.layout or {}).get("x") == x]
                col.sort(key=lambda n: (n.layout or {}).get("y") or 0)
                bottom: int | None = None
                for node in col:
                    lay = node.layout
                    y, h = lay.get("y") or 0, lay.get("h") or 0
                    if bottom is not None and y < bottom + _GAP_CROSS:
                        new_y = bottom + _GAP_CROSS
                        logger.info(
                            "shift",
                            project=project_id[:8],
                            node=str(node.id)[:8],
                            y=f"{y} -> {new_y}",
                        )
                        node.layout = {**lay, "y": new_y}
                        node.updated_at = now
                        changed.add(node.id)
                        y = new_y
                    bottom = y + h

        if not changed:
            print("no legacy frames found — nothing to do")
            return
        print(f"{len(changed)} node(s) touched")
        if not args.yes:
            print("dry-run — re-run with --yes to apply")
            await db.rollback()
            return

        await db.commit()
        print(f"applied: {len(changed)} node(s) re-stamped/shifted")


if __name__ == "__main__":
    asyncio.run(main())
