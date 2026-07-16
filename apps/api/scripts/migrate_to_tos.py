"""One-time migration: upload local MVP assets to object storage.

Uploads the files that used to live under ``assets/`` to the configured
object-storage bucket using the same keys the application now expects:

- Demo source video: ``demo/uploads/demo_talk.mp4``
- Demo rendered outputs: ``demo/outputs/clip_{1,2,3}.mp4``,
  ``demo/outputs/clip_{1,2,3}.srt``,
  ``demo/outputs/quote_1.png``
- Default music catalog: ``music/{default_music_id(mood)}.mp3``

The script is idempotent: existing objects are overwritten only when ``--force``
is passed. After uploading, it HEADs each public URL to verify the object is
readable.

Usage (from apps/api/):
    uv run python scripts/migrate_to_tos.py
    uv run python scripts/migrate_to_tos.py --force

Requires S3 credentials in the environment / ``.env``.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import httpx
import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services.music import DEFAULT_MUSIC_CATALOG  # noqa: E402
from app.services.storage import exists, public_url, save  # noqa: E402

logger = structlog.get_logger()

REPO_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = REPO_ROOT / "assets"

DEFAULT_MUSIC_FILES: list[tuple[str, str]] = [
    (mood["mood"], f"music/{uuid5(NAMESPACE_DNS, 'repurposer:music:' + mood['mood'])}.mp3")
    for mood in DEFAULT_MUSIC_CATALOG
]

MVP_FILES: list[tuple[Path, str]] = [
    (ASSETS_DIR / "demo/uploads/demo_talk.mp4", "demo/uploads/demo_talk.mp4"),
    (ASSETS_DIR / "demo/outputs/clip_1.mp4", "demo/outputs/clip_1.mp4"),
    (ASSETS_DIR / "demo/outputs/clip_1.srt", "demo/outputs/clip_1.srt"),
    (ASSETS_DIR / "demo/outputs/clip_2.mp4", "demo/outputs/clip_2.mp4"),
    (ASSETS_DIR / "demo/outputs/clip_2.srt", "demo/outputs/clip_2.srt"),
    (ASSETS_DIR / "demo/outputs/clip_3.mp4", "demo/outputs/clip_3.mp4"),
    (ASSETS_DIR / "demo/outputs/clip_3.srt", "demo/outputs/clip_3.srt"),
    (ASSETS_DIR / "demo/outputs/quote_1.png", "demo/outputs/quote_1.png"),
]


def _content_type_for_key(key: str) -> str | None:
    ext = Path(key).suffix.lower()
    mapping = {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".srt": "text/srt",
        ".png": "image/png",
    }
    return mapping.get(ext)


async def _upload_one(local_path: Path, key: str, *, force: bool) -> tuple[str, bool]:
    if not local_path.is_file():
        return f"[skip] {key}: local file missing ({local_path})", False

    if not force and await exists(key):
        return f"[skip] {key}: already exists in storage", False

    data = local_path.read_bytes()
    await save(key, data, content_type=_content_type_for_key(key))
    return f"[ok  ] {key}: uploaded {len(data)} bytes", True


async def _verify_one(key: str) -> tuple[str, bool]:
    url = public_url(key)
    if url is None:
        return f"[FAIL] {key}: public_url is None", False
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.head(url)
            response.raise_for_status()
            return f"[verify] {key}: OK ({response.status_code})", True
        except httpx.HTTPError as exc:
            return f"[FAIL] {key}: {exc}", False


async def _main(*, force: bool, verify: bool) -> int:
    if not settings.s3_access_key_id or not settings.s3_secret_access_key:
        print(
            "ERROR: S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be set in the "
            "environment or .env file.",
            file=sys.stderr,
        )
        return 1

    missing_locals = [str(p) for p, _ in MVP_FILES if not p.is_file()]
    missing_locals += [
        str(ASSETS_DIR / "music" / Path(key).name)
        for _, key in DEFAULT_MUSIC_FILES
        if not (ASSETS_DIR / "music" / Path(key).name).is_file()
    ]
    if missing_locals:
        print("Local files missing:", file=sys.stderr)
        for path in missing_locals:
            print(f"  - {path}", file=sys.stderr)
        return 1

    files = MVP_FILES + [
        (ASSETS_DIR / "music" / Path(key).name, key)
        for _, key in DEFAULT_MUSIC_FILES
    ]

    print(f"Uploading {len(files)} object(s) to bucket '{settings.s3_bucket_name}' …")
    upload_results = await asyncio.gather(
        *[_upload_one(path, key, force=force) for path, key in files]
    )
    uploaded = 0
    for msg, was_uploaded in upload_results:
        print(msg)
        if was_uploaded:
            uploaded += 1
    print(f"\nUploaded {uploaded} new object(s).")

    if verify:
        print("\nVerifying public URLs …")
        verify_results = await asyncio.gather(
            *[_verify_one(key) for _, key in files]
        )
        failed = [msg for msg, ok in verify_results if not ok]
        for msg, _ in verify_results:
            print(msg)
        if failed:
            print(f"\n{len(failed)} verification(s) failed.", file=sys.stderr)
            return 2
        print("\nAll public URLs are accessible.")

    print("\nMigration complete.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload MVP assets to object storage.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite objects that already exist in storage.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip public-URL accessibility checks.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(force=args.force, verify=not args.no_verify)))


if __name__ == "__main__":
    main()
