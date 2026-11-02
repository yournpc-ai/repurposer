"""One exact C4 Output review, then a byte-stable same-request reuse check."""
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

OUTPUT_ID = UUID("8674d76e-4dc8-4e91-82c2-75d0686f7e7e")
REPORT_PATH = Path("/Users/sylas/repurposer/scratch/c4-blur-slide-review.json")
ARGS = ReviewVideoArgs(
    output_id=OUTPUT_ID,
    requirements=(
        "Create a four-second word-by-word blur-slide title animation with "
        "the exact supplied English title and subtitle. All words must finish "
        "fully visible, legible and uncropped. No narration or soundtrack is required."
    ),
    at_seconds=[0.4, 0.8, 1.5, 3.5],
)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(Project.user_id)
                .join(Output, Output.project_id == Project.id)
                .where(Output.id == OUTPUT_ID)
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("C4 Output not found")
        first = await review_video(db, owner_id=row.user_id, args=ARGS)
    async with AsyncSessionLocal() as db:
        second = await review_video(db, owner_id=row.user_id, args=ARGS)
    assert first == second, "same-request review was not reused exactly"
    REPORT_PATH.write_text(json.dumps(first, ensure_ascii=False, indent=2))
    print(json.dumps({
        "output_id": first["output_id"],
        "schema_version": first["schema_version"],
        "frames": [{"id": f["frame_id"], "frame": f["frame"]} for f in first["frames"]],
        "summary": first["summary"],
        "findings": first["findings"],
        "media_inspection": first["media_inspection"],
        "exact_reuse": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
