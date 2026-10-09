"""One-off backfill: stamp ``spec.cues`` (the transcript card's structured
hover-timeline rows) onto existing transcript document nodes from their
asset's ASR words, dropping the legacy ``spec.cued_text`` string bake.

The bake seat moved — ``graph_fill._transcript_cue_rows`` (the same ONE
``group_cues`` law, rows carrying preformatted ``m:ss–m:ss`` labels so the
client never formats time) — and this script heals rows born before the
move. New transcripts are stamped at birth and on every asset sync, so this
is a one-time migration, not a reconcile loop.

Per transcript document node (``type='document'``, ``spec.role='transcript'``):

- ``spec.cues`` already present → skipped (idempotent).
- Rows derive from the owning asset's ``meta.words``; assets without word
  timestamps (paste / extraction yields) keep the plain-text face — nothing
  is stamped.
- The legacy ``cued_text`` key pops wherever cues land (the card's read
  order prefers the rows; the string bake is dead weight afterwards).

Dry-run by default — prints the plan. Pass ``--yes`` to execute.

Usage (from apps/api/):
    uv run python scripts/backfill_transcript_cues.py           # dry-run
    uv run python scripts/backfill_transcript_cues.py --yes     # apply
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Asset, GraphNode  # noqa: E402

# The ONE bake seat + the role vocabulary's one home — never re-derived here.
from app.pipeline.graph_fill import _TRANSCRIPT_ROLE, _transcript_cue_rows  # noqa: E402


async def main(apply: bool) -> None:
    stamped = healed = wordless = 0
    async with AsyncSessionLocal() as db:
        nodes = (
            (
                await db.execute(
                    select(GraphNode).where(
                        GraphNode.type == "document",
                        GraphNode.spec["role"].as_string() == _TRANSCRIPT_ROLE,
                    )
                )
            )
            .scalars()
            .all()
        )
        planned: list[str] = []
        for node in nodes:
            spec = dict(node.spec or {})
            if spec.get("cues"):
                continue
            asset_id = spec.get("asset_id")
            asset = await db.get(Asset, UUID(str(asset_id))) if asset_id else None
            rows = (
                _transcript_cue_rows((asset.meta or {}).get("words"))
                if asset is not None
                else None
            )
            if rows is None:
                wordless += 1  # no word timestamps — the plain-text face stays
                continue
            spec["cues"] = rows
            healed += 1 if spec.pop("cued_text", None) is not None else 0
            stamped += 1
            planned.append(f"{node.id}  project={node.project_id}  cues={len(rows)}")
            if apply:
                node.spec = spec  # reassign, never mutate in place (JSONB dirty)
        print(
            f"{'APPLY' if apply else 'DRY-RUN'}: {len(nodes)} transcript nodes, "
            f"{stamped} to stamp ({healed} healing off cued_text), "
            f"{wordless} word-less (plain face kept)"
        )
        for line in planned:
            print(" ", line)
        if apply:
            await db.commit()
            print("committed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="apply (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(main(args.yes))
