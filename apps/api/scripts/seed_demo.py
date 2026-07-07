"""Standalone script to seed the demo project using the real pipeline.

Run from the api directory:
    uv run python scripts/seed_demo.py

This is useful for (re)generating demo outputs without starting the full API.
The regular API startup also calls ``seed_demo_project()`` automatically.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.demo_seed import seed_demo_project


async def main() -> None:
    await seed_demo_project()


if __name__ == "__main__":
    asyncio.run(main())
