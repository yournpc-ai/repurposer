"""Standalone script to seed the demo project using the real pipeline.

Run from the api directory:
    uv run python scripts/seed_demo.py
    uv run python scripts/seed_demo.py --force   # delete existing clips/outputs and regenerate

This is useful for (re)generating demo outputs without starting the full API.
The regular API startup also calls ``seed_demo_project()`` automatically.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete

from app.models.database import AsyncSessionLocal
from app.models.tables import Asset, Output, WorkflowRun
from app.services.demo_seed import DEMO_PROJECT_ID, seed_demo_project
from app.services.storage import delete_prefix, get_project_output_dir


async def _reset_demo_outputs() -> None:
    """Delete existing demo outputs, runs, and rendered files.

    The demo Asset row is removed too: ``seed_demo_project`` skips ASR when the
    asset is already COMPLETED, so without this a swapped demo video would be
    re-generated from the OLD transcript. The asset is recreated as PENDING,
    which re-triggers ASR on whatever now lives at the demo video object key.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Output).where(Output.project_id == DEMO_PROJECT_ID))
        await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == DEMO_PROJECT_ID))
        await db.execute(delete(Asset).where(Asset.project_id == DEMO_PROJECT_ID))
        await db.commit()

    output_prefix = get_project_output_dir(DEMO_PROJECT_ID, "demo")
    await delete_prefix(output_prefix)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo project")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing demo clips/outputs and regenerate from scratch",
    )
    args = parser.parse_args()

    if args.force:
        await _reset_demo_outputs()

    await seed_demo_project()


if __name__ == "__main__":
    asyncio.run(main())
