"""One-time generator for the 3 default music pieces (calm/uplifting/corporate).

Generates each catalog piece via MiniMax (``DEFAULTS_MODEL``) and writes it to
``assets/music/{default_music_id(mood)}.mp3`` — the deterministic uuid5 path
that ``services/music.seed_default_music`` reconciles into ``Music`` rows at app
startup. This script does NOT touch the DB; it only produces the audio files
(committed to git so a fresh clone/CI has them without an API call).

Idempotent: skips any mood whose file already exists, so re-running never
re-spends budget. Force a regenerate with ``--force``.

Usage (from apps/api/):
    uv run python scripts/seed_default_music.py            # generate missing
    uv run python scripts/seed_default_music.py --force    # regenerate all
    uv run python scripts/seed_default_music.py --mood calm

Requires ``MINIMAX_API_KEY`` in the environment / apps/api/.env.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog  # noqa: E402

from app.clients.minimax import MiniMaxError  # noqa: E402
from app.services.music import (  # noqa: E402
    DEFAULT_MUSIC_CATALOG,
    default_music_id,
)
from app.services.music_generation import (  # noqa: E402
    DEFAULTS_MODEL,
    generate_music,
    music_disk_path,
    persist_music,
)

logger = structlog.get_logger()


async def _seed_one(entry: dict[str, str], *, force: bool) -> bool:
    """Generate + persist one catalog piece. Returns True if a file was written."""
    mood = entry["mood"]
    music_id = default_music_id(mood)
    disk_path = music_disk_path(music_id)
    if disk_path.is_file() and not force:
        print(f"  [skip] {mood}: already exists at {disk_path}")
        return False

    print(f"  [gen ] {mood}: '{entry['title']}' via {DEFAULTS_MODEL} …")
    generated = await generate_music(entry["prompt"], model=DEFAULTS_MODEL)
    rel_path, size = persist_music(music_id, generated)
    print(
        f"  [ok  ] {mood}: wrote {size} bytes -> {rel_path} "
        f"(id={music_id}, duration={generated.duration_seconds}s)"
    )
    return True


async def _main(moods: list[str] | None, *, force: bool) -> int:
    entries = [e for e in DEFAULT_MUSIC_CATALOG if not moods or e["mood"] in moods]
    if not entries:
        print(f"No catalog entries match moods={moods}", file=sys.stderr)
        return 1

    written = 0
    for entry in entries:
        try:
            if await _seed_one(entry, force=force):
                written += 1
        except MiniMaxError as e:
            print(f"  [FAIL] {entry['mood']}: {e}", file=sys.stderr)
            return 2

    print(f"\nDone. {written} file(s) written; run the API to seed Music rows.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the 3 default music pieces.")
    parser.add_argument(
        "--force", action="store_true", help="Regenerate even if the file exists."
    )
    parser.add_argument(
        "--mood",
        action="append",
        dest="moods",
        help="Only generate this mood (repeatable). Default: all.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.moods, force=args.force)))


if __name__ == "__main__":
    main()
