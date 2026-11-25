"""Import a JSON array of licensed recording entries with paths relative to the manifest."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import TypeAdapter

from app.catalog.sfx_ingest import Recording, analyze_audio, ingest_recording, read_recording
from app.editing.catalog import SOUND_RECIPE_CATALOG


async def seed(manifest: Path, *, dry_run: bool = False):
    entries = TypeAdapter(list[Recording]).validate_json(manifest.read_bytes())
    categories = {(r["domain"], r["category"]) for r in SOUND_RECIPE_CATALOG.values()}
    if len({e.slug for e in entries}) != len(entries):
        raise ValueError("Duplicate recording slug in manifest")
    for e in entries:
        if (e.domain, e.category) not in categories:
            raise ValueError(f"{e.slug}: unknown category {e.domain}/{e.category}")

    rows = []
    if dry_run:
        for entry in entries:
            _, data = read_recording(entry, manifest.parent)
            facts = analyze_audio(data)
            rows.append(
                (
                    entry,
                    facts["duration_ms"],
                    facts["peak_offset_ms"],
                    facts["lufs"],
                    facts["waveform_peaks"],
                )
            )
    else:
        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal.begin() as db:
            for entry in sorted(entries, key=lambda e: e.slug):
                row = await ingest_recording(db, entry, manifest.parent)
                rows.append(
                    (entry, row.duration_ms, row.peak_offset_ms, row.lufs, row.waveform_peaks)
                )

    print("slug / domain / category / duration_ms / peak_offset_ms / lufs / peaks_len")
    for entry, duration, offset, loudness, peaks in rows:
        lufs = f"{loudness:.3f}" if loudness is not None else "silent"
        print(
            f"{entry.slug} / {entry.domain} / {entry.category} / {duration} / {offset} / {lufs} / {len(peaks)}"
        )
    print(f"{'Measured' if dry_run else 'Imported'} {len(rows)} recordings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1] / "assets/sfx/manifest.json",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and measure without importing."
    )
    args = parser.parse_args()
    asyncio.run(seed(args.manifest, dry_run=args.dry_run))
