"""Import the curated local Mixkit objects without generation or DB access.

The required argument is Shotcraft's ``assets/audio/bgm`` directory. Each MP3 is
decoded with PyAV, hashed and uploaded under the deterministic music object key.
Startup reconcile creates the corresponding ``Music`` rows.

Existing objects are reused only when their bytes exactly match the local file;
a mismatch is an error and is never overwritten.

Usage (from apps/api/):
    uv run python scripts/import_library_music.py /path/to/assets/audio/bgm
"""

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.music import (  # noqa: E402
    AUDIO_EXT,
    CURATED_MUSIC_CATALOG,
    CuratedMusicAudio,
    CuratedMusicEntry,
    default_music_id,
    music_disk_path,
    music_file_path,
    persist_music,
    probe_music_duration_seconds,
)
from app.providers.storage import read  # noqa: E402


async def _import_one(bgm_dir: Path, entry: CuratedMusicEntry) -> bool:
    """Import one curated object. Returns True only when bytes were uploaded."""
    source = bgm_dir / entry["original_filename"]
    if not source.is_file():
        raise ValueError(f"required source file is missing: {source}")
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    duration_seconds = probe_music_duration_seconds(data)

    music_id = default_music_id(entry["mood"])
    key = music_file_path(music_id)
    if await music_disk_path(music_id):
        existing = await read(key)
        if existing != data:
            raise ValueError(
                f"refusing to overwrite {key}: existing bytes do not match {source.name}"
            )
        print(
            f"  [skip] {entry['mood']}: identical object at {key} "
            f"(sha256={digest}, duration={duration_seconds}s)"
        )
        return False

    audio = CuratedMusicAudio(
        audio_bytes=data,
        ext=AUDIO_EXT,
        duration_seconds=duration_seconds,
        size_bytes=len(data),
        content_sha256=digest,
    )
    file_path, size = await persist_music(music_id, audio)
    print(
        f"  [ok  ] {entry['mood']}: {source.name} -> {file_path} "
        f"(id={music_id}, bytes={size}, duration={duration_seconds}s, sha256={digest})"
    )
    return True


async def _main(bgm_dir: Path) -> int:
    if not bgm_dir.is_dir():
        print(f"Source BGM directory does not exist: {bgm_dir}", file=sys.stderr)
        return 1

    written = 0
    for entry in CURATED_MUSIC_CATALOG:
        try:
            if await _import_one(bgm_dir, entry):
                written += 1
        except Exception as e:  # noqa: BLE001 — stop before importing later pieces
            print(f"  [FAIL] {entry['mood']}: {e}", file=sys.stderr)
            return 2

    print(f"\nDone. {written} object(s) written; run the API to reconcile Music rows.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the five curated local Mixkit tracks without generation."
    )
    parser.add_argument(
        "bgm_dir",
        type=Path,
        help="Shotcraft assets/audio/bgm directory containing the five curated MP3s.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.bgm_dir)))


if __name__ == "__main__":
    main()
