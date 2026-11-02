"""One paid review of the revised two-shot Output, plus exact reuse verification."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import ReviewVideoArgs
from app.models.tables import Output, Project
from app.tools.video.review import review_video

ARGS = ReviewVideoArgs(
    output_id=UUID("de749105-fe48-4e5d-8b15-ffd1d2f60fcc"),
    requirements=(
        "Create a two-scene product title sequence on a dark background. Scene one "
        "uses the word-by-word blur-slide with 'Make every idea / move clearly' and "
        "the supplied subtitle. Scene two reveals 'Shape' as a large centered title, "
        "then continuously demotes it to a small upper-left section label while three "
        "lines enter below: 'Upload the material you already have', 'Choose the exact "
        "content you need', and 'Review and refine every version'. The second line is "
        "the only revised content from v1. Final text must be legible and uncropped. "
        "No narration or soundtrack is required."
    ),
    at_seconds=[3.5, 4.4, 5.8, 7.2],
)
OUT = Path("/Users/sylas/repurposer/scratch/c4-multishot-v2-review.json")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        owner_id = (
            await db.execute(
                select(Project.user_id)
                .join(Output, Output.project_id == Project.id)
                .where(Output.id == ARGS.output_id)
            )
        ).scalar_one()
        first = await review_video(db, owner_id=owner_id, args=ARGS)
    async with AsyncSessionLocal() as db:
        second = await review_video(db, owner_id=owner_id, args=ARGS)
    assert first == second
    OUT.write_text(json.dumps(first, ensure_ascii=False, indent=2))
    print(json.dumps({
        "output_id": first["output_id"],
        "frames": [frame["frame"] for frame in first["frames"]],
        "summary": first["summary"],
        "findings": first["findings"],
        "issues": first["media_inspection"]["issues"],
        "audio_expected": first["media_inspection"]["audio"]["expected"],
        "exact_reuse": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
