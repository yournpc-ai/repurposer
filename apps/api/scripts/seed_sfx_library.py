"""Import a JSON array of licensed recording entries with paths relative to the manifest."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import TypeAdapter

from app.catalog.sfx_ingest import Recording, ingest_recording
from app.models.database import AsyncSessionLocal


async def seed(manifest: Path):
    entries = TypeAdapter(list[Recording]).validate_json(manifest.read_bytes())
    async with AsyncSessionLocal.begin() as db:
        for entry in sorted(entries, key=lambda e: e.slug):
            await ingest_recording(db, entry, manifest.parent)
    print(f"Imported {len(entries)} recordings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1] / "assets/sfx/manifest.json",
    )
    asyncio.run(seed(parser.parse_args().manifest))
