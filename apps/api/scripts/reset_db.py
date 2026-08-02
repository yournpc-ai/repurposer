"""Reset a deployment to a clean slate: wipe the database AND purge
user-owned object storage — while PRESERVING the frozen asset prefixes.

Preserved object-storage prefixes (never touched, by design):

- ``demo/`` — landing + recipe-card marketing assets. Their content-hashed
  URLs are baked into the web bundle (``apps/web/src/lib/recipes.assets.ts``),
  generated ONCE via ``scripts/upload_recipe_assets.py``. They must survive
  every deploy and every reset: production never regenerates them.
- ``music/`` — platform seed tracks. ``seed_default_music.py`` reconciles
  Music rows against existing objects WITHOUT spending MiniMax quota (it
  skips any object that already exists); deleting the objects would force
  paid regeneration after every reset.

Everything else in the bucket (``{user_id}/uploads|outputs|speakers|
brand-media/...`` and any stray top-level prefix) is deleted, and every row
is deleted from every table (users, projects, assets, outputs, operations,
publications, workflow runs/steps, chat, music, channel accounts,
notifications, verification codes).

Dry-run by default — prints the DB row counts and the storage plan (per
top-level prefix: object count + bytes). Pass ``--yes`` to execute.

Usage (from apps/api/):
    uv run python scripts/reset_db.py                       # dry-run
    uv run python scripts/reset_db.py --yes                 # wipe DB + purge storage
    uv run python scripts/reset_db.py --yes --db-only       # DB only
    uv run python scripts/reset_db.py --yes --storage-only  # storage only

After the wipe:
- restart the API / worker with SKIP_DEMO_SEED=true or the next startup
  re-creates the demo project
- restore platform music rows with
  ``uv run python scripts/seed_default_music.py`` — reconciles against the
  preserved ``music/`` objects, no quota spent
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import (  # noqa: E402
    Asset,
    BrandTemplate,
    ChannelAccount,
    Conversation,
    Message,
    Music,
    Notification,
    Operation,
    Output,
    Project,
    Publication,
    Speaker,
    User,
    VerificationCode,
    WorkflowRun,
)
from app.tools.storage import _get_s3_client  # noqa: E402

# Prefixes the storage purge never touches (see module docstring).
PROTECTED_PREFIXES = ("demo/", "music/")


def _plan() -> list[tuple[str, object]]:
    """Deletion steps in FK-safe order: (label, table). Every row goes."""
    return [
        # operations reference outputs/projects/users/messages — first.
        ("operations", Operation),
        # publications.output_id is RESTRICT — must precede outputs.
        ("publications", Publication),
        ("notifications", Notification),
        ("messages", Message),
        ("conversations", Conversation),
        ("outputs", Output),
        # workflow_steps cascade away with workflow_runs (run_id FK ondelete=CASCADE).
        ("workflow_runs", WorkflowRun),
        ("assets", Asset),
        ("brand_templates", BrandTemplate),
        ("projects", Project),
        ("speakers", Speaker),
        ("music", Music),
        ("channel_accounts", ChannelAccount),
        ("users", User),
        ("verification_codes", VerificationCode),
    ]


def _is_protected(key: str) -> bool:
    return key.startswith(PROTECTED_PREFIXES)


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


async def _scan_bucket() -> tuple[dict[str, list[int]], dict[str, list[int]], list[str]]:
    """List every object in the bucket once.

    Returns (purge_stats, protected_stats, purge_keys) where stats map a
    top-level prefix to [object_count, total_bytes].
    """
    client = _get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    pages = await asyncio.to_thread(
        lambda: list(paginator.paginate(Bucket=settings.s3_bucket_name))
    )
    purge: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    keep: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    purge_keys: list[str] = []
    for page in pages:
        for obj in page.get("Contents", []):
            key, size = obj["Key"], obj["Size"]
            top = key.split("/", 1)[0] + "/" if "/" in key else "(root)"
            stats = keep if _is_protected(key) else purge
            stats[top][0] += 1
            stats[top][1] += size
            if stats is purge:
                purge_keys.append(key)
    return purge, keep, purge_keys


async def _purge_storage(keys: list[str]) -> int:
    """Batch-delete the given object keys (1000 per delete_objects call)."""
    client = _get_s3_client()
    deleted = 0
    for i in range(0, len(keys), 1000):
        batch = [{"Key": k} for k in keys[i : i + 1000]]
        resp = await asyncio.to_thread(
            client.delete_objects,
            Bucket=settings.s3_bucket_name,
            Delete={"Objects": batch, "Quiet": True},
        )
        deleted += len(batch)
        for err in resp.get("Errors", []):
            print(f"  [warn] delete failed: {err['Key']}: {err['Message']}")
        print(f"  storage purge: {deleted}/{len(keys)} objects")
    return deleted


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete. Without this flag the script only prints the plan.",
    )
    parser.add_argument("--db-only", action="store_true", help="Skip the storage purge.")
    parser.add_argument(
        "--storage-only", action="store_true", help="Skip the database wipe."
    )
    args = parser.parse_args()
    if args.db_only and args.storage_only:
        parser.error("--db-only and --storage-only are mutually exclusive")

    do_db = not args.storage_only
    do_storage = not args.db_only

    # Environment banner — on a server this is the last chance to notice
    # you're pointing at the wrong target before anything is deleted.
    db_url = make_url(settings.database_url)
    print(f"target database: {db_url.drivername}://{db_url.host}:{db_url.port}/{db_url.database}")
    print(f"target bucket:   {settings.s3_bucket_name} ({settings.s3_endpoint_url})")
    print(f"protected:       {', '.join(PROTECTED_PREFIXES)}")
    print()

    steps = _plan()

    if do_db:
        async with AsyncSessionLocal() as db:
            if not args.yes:
                print("DRY-RUN — database rows that would be deleted:")
                total = 0
                for label, table in steps:
                    count = await db.scalar(select(func.count()).select_from(table))
                    total += count or 0
                    print(f"  {label:24} {count}")
                print(f"  {'TOTAL':24} {total}")
            else:
                print("Wiping ALL database rows (nothing is preserved)...")
                for label, table in steps:
                    result = await db.execute(delete(table))
                    print(f"  {label:24} deleted {result.rowcount}")
                await db.commit()
                print("Database is empty.")
        print()

    if do_storage:
        print("Scanning bucket for the storage plan...")
        purge, keep, purge_keys = await _scan_bucket()
        if not args.yes:
            print("DRY-RUN — storage objects that would be deleted:")
            total_n, total_b = 0, 0
            for top in sorted(purge):
                n, b = purge[top]
                total_n, total_b = total_n + n, total_b + b
                print(f"  {top:24} {n:6} objects  {_fmt_bytes(b)}")
            print(f"  {'TOTAL':24} {total_n:6} objects  {_fmt_bytes(total_b)}")
            print("Preserved (never touched):")
            for top in sorted(keep):
                n, b = keep[top]
                print(f"  {top:24} {n:6} objects  {_fmt_bytes(b)}")
        else:
            if purge_keys:
                print(f"Purging {len(purge_keys)} storage objects (protected prefixes kept)...")
                await _purge_storage(purge_keys)
            else:
                print("Storage already clean — nothing outside the protected prefixes.")
            print(f"Preserved: {sum(n for n, _ in keep.values())} objects under {', '.join(PROTECTED_PREFIXES)}")

    if not args.yes:
        print("\nPass --yes to execute.")
        return

    print("\nDone. Next steps:")
    print("  1. Restart API / worker with SKIP_DEMO_SEED=true (or the demo project is re-seeded).")
    print("  2. uv run python scripts/seed_default_music.py  # reconcile music rows, free")


if __name__ == "__main__":
    asyncio.run(main())
