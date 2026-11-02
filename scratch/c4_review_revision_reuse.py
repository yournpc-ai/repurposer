"""Review both real C4 Outputs once each, then verify exact same-request reuse."""
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

CASES = [
    (
        "revision",
        ReviewVideoArgs(
            output_id=UUID("b7b562f2-ae31-40ed-8670-6f83ffdefbbc"),
            requirements=(
                "Revise the existing blur-slide to a dark background with light text. "
                "Change the first title to 'Turn every insight' and the subtitle to "
                "'Your research and expertise shaped into content people remember'; "
                "keep 'move clearly' and the word-by-word reveal. All final text must "
                "be legible and uncropped. No narration or soundtrack is required."
            ),
            at_seconds=[0.4, 0.8, 1.5, 3.5],
        ),
    ),
    (
        "reuse",
        ReviewVideoArgs(
            output_id=UUID("7468027d-e763-467f-afa4-82b74b0250a0"),
            requirements=(
                "Reuse the blur-slide method with the new title 'Grow your audience / "
                "share boldly' and subtitle 'Turn your hard earned expertise into "
                "stories worth following', on a dark background with light text. "
                "Keep the word-by-word reveal; all final text must be legible and "
                "uncropped. No narration or soundtrack is required."
            ),
            at_seconds=[0.4, 0.8, 1.5, 3.5],
        ),
    ),
]
ROOT = Path("/Users/sylas/repurposer/scratch")


async def main() -> None:
    summaries = []
    for label, args in CASES:
        async with AsyncSessionLocal() as db:
            owner_id = (
                await db.execute(
                    select(Project.user_id)
                    .join(Output, Output.project_id == Project.id)
                    .where(Output.id == args.output_id)
                )
            ).scalar_one()
            first = await review_video(db, owner_id=owner_id, args=args)
        async with AsyncSessionLocal() as db:
            second = await review_video(db, owner_id=owner_id, args=args)
        assert first == second, f"{label}: same-request review was not reused exactly"
        (ROOT / f"c4-{label}-review.json").write_text(
            json.dumps(first, ensure_ascii=False, indent=2)
        )
        summaries.append({
            "label": label,
            "output_id": first["output_id"],
            "schema_version": first["schema_version"],
            "frames": [frame["frame"] for frame in first["frames"]],
            "summary": first["summary"],
            "findings": first["findings"],
            "issues": first["media_inspection"]["issues"],
            "audio_expected": first["media_inspection"]["audio"]["expected"],
            "exact_reuse": True,
        })
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
