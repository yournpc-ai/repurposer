"""Render the two pinned C4 versions through the existing run-less Output queue."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Composition, CompositionVersion, Output, Project
from app.tools.video.produce import queue_composition_render

VERSION_IDS = [
    UUID("8aa96258-a37a-4b2b-9860-b36fd89b051c"),
    UUID("4056529e-26a4-473d-893a-e15ad93505aa"),
]
OUT = Path("/Users/sylas/repurposer/scratch/c4-revision-reuse-renders.json")
TERMINAL = {RenderStatus.COMPLETED, RenderStatus.FAILED}


async def queue() -> list[UUID]:
    output_ids: list[UUID] = []
    async with AsyncSessionLocal() as db:
        for version_id in VERSION_IDS:
            existing = await db.scalar(
                select(Output)
                .where(Output.composition_version_id == version_id)
                .order_by(Output.created_at.desc())
                .limit(1)
            )
            if existing is not None:
                output_ids.append(existing.id)
                continue
            version = await db.get(CompositionVersion, version_id)
            composition = await db.get(Composition, version.composition_id)
            project = await db.get(Project, composition.origin_project_id)
            output = await queue_composition_render(
                db,
                project=project,
                composition=composition,
                version=version,
                execution_id=f"c4-native-{version_id}",
            )
            output_ids.append(output.id)
        await db.commit()
    return output_ids


async def wait(output_ids: list[UUID]) -> list[dict]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 600
    while True:
        rows: list[dict] = []
        async with AsyncSessionLocal() as db:
            for output_id in output_ids:
                output = await db.get(Output, output_id)
                rows.append({
                    "output_id": str(output.id),
                    "composition_id": str(output.composition_id),
                    "composition_version_id": str(output.composition_version_id),
                    "render_status": output.render_status.value,
                    "duration_seconds": (output.payload or {}).get("duration_seconds"),
                    "files": output.files,
                    "quality": output.quality,
                    "charged_credits": 0,
                    "charge_scope": "run-less adapter render; no Run or render mirror",
                })
        if all(row["render_status"] in {status.value for status in TERMINAL} for row in rows):
            OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            if any(row["render_status"] != RenderStatus.COMPLETED.value for row in rows):
                raise RuntimeError("at least one C4 render failed")
            return rows
        if loop.time() >= deadline:
            raise TimeoutError(json.dumps(rows))
        await asyncio.sleep(2)


async def main() -> None:
    await wait(await queue())


if __name__ == "__main__":
    asyncio.run(main())
