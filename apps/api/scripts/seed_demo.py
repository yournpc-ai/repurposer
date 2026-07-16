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
from app.models.tables import Clip, Derivative
from app.services.demo_seed import DEMO_PROJECT_ID, seed_demo_project
from app.services.storage import delete_prefix, get_project_output_dir


async def _reset_demo_outputs() -> None:
    """Delete existing demo clips, derivatives, and rendered output objects."""
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Clip).where(Clip.project_id == DEMO_PROJECT_ID))
        await db.execute(delete(Derivative).where(Derivative.project_id == DEMO_PROJECT_ID))
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
