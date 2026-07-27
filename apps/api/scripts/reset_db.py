"""Wipe ALL data from the database — nothing is preserved.

Deletes every row from every table (users, projects, assets, outputs,
operations, publications, workflow runs/steps, chat, music, channel
accounts, notifications, verification codes), including the former demo
user's data and platform-seeded music. Demo seed is retired, so this is a
true clean slate.

Object-storage files belonging to deleted rows are NOT removed (orphaned
objects are harmless but may accumulate; clean them up separately if needed).

After the wipe:
- if the API still runs with demo seeding enabled, the next startup
  re-creates the demo project (set SKIP_DEMO_SEED=true to prevent that)
- default music tracks are gone; re-seed with
  ``uv run python scripts/seed_default_music.py`` (spends MiniMax quota)

Dry-run by default — prints what would be deleted. Pass ``--yes`` to execute.

Usage (from apps/api/):
    uv run python scripts/reset_db.py            # dry-run
    uv run python scripts/reset_db.py --yes      # execute
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402

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


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete. Without this flag the script only prints counts.",
    )
    args = parser.parse_args()

    steps = _plan()
    async with AsyncSessionLocal() as db:
        if not args.yes:
            print("DRY-RUN — rows that would be deleted (pass --yes to execute):")
            total = 0
            for label, table in steps:
                count = await db.scalar(select(func.count()).select_from(table))
                total += count or 0
                print(f"  {label:24} {count}")
            print(f"  {'TOTAL':24} {total}")
            return

        print("Wiping ALL data (nothing is preserved)...")
        for label, table in steps:
            result = await db.execute(delete(table))
            print(f"  {label:24} deleted {result.rowcount}")
        await db.commit()
        print("Done. Database is empty.")
        print("Note: set SKIP_DEMO_SEED=true or the next API startup re-seeds the demo project.")


if __name__ == "__main__":
    asyncio.run(main())
