"""Reset the database while preserving demo/seed data (no regeneration needed).

Wipes every non-demo user and all of their data, in FK-safe order. Keeps:

- the demo user (``DEFAULT_USER_ID``) and everything it owns — demo project,
  demo speaker, its brand templates, assets, clips, derivatives, workflow
  runs, chat sessions and messages
- platform music pieces (``generated_by_user_id IS NULL``) and the demo
  user's own pieces
- brand templates owned by the demo user

Use this on an environment that needs a clean slate WITHOUT re-running the
demo seed (ASR + generation + rendering all cost MiniMax calls and time).

Object-storage files belonging to deleted users are NOT removed (orphaned
objects are harmless but may accumulate; clean them up separately if needed).

Dry-run by default — prints what would be deleted. Pass ``--yes`` to execute.

Usage (from apps/api/):
    uv run python scripts/reset_db.py            # dry-run
    uv run python scripts/reset_db.py --yes      # execute
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402

from app.dependencies.auth import DEFAULT_USER_ID  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import (  # noqa: E402
    Asset,
    BrandTemplate,
    ChatSession,
    Message,
    Music,
    Output,
    Project,
    Speaker,
    User,
    VerificationCode,
    WorkflowRun,
)

DEMO_USER_UUID = UUID(DEFAULT_USER_ID)


def _plan() -> list[tuple[str, object, object]]:
    """Deletion steps in FK-safe order: (label, table, where clause)."""
    non_demo_projects = select(Project.id).where(Project.user_id != DEMO_USER_UUID)
    non_demo_sessions = select(ChatSession.id).where(ChatSession.user_id != DEMO_USER_UUID)
    return [
        ("messages", Message, Message.session_id.in_(non_demo_sessions)),
        ("chat_sessions", ChatSession, ChatSession.user_id != DEMO_USER_UUID),
        ("outputs", Output, Output.project_id.in_(non_demo_projects)),
        # plan_nodes cascade away with workflow_runs (run_id FK ondelete=CASCADE).
        ("workflow_runs", WorkflowRun, WorkflowRun.project_id.in_(non_demo_projects)),
        ("assets", Asset, Asset.user_id != DEMO_USER_UUID),
        ("brand_templates", BrandTemplate, BrandTemplate.user_id != DEMO_USER_UUID),
        ("projects", Project, Project.user_id != DEMO_USER_UUID),
        ("speakers", Speaker, Speaker.user_id != DEMO_USER_UUID),
        (
            "music (user-generated)",
            Music,
            (Music.generated_by_user_id.isnot(None))
            & (Music.generated_by_user_id != DEMO_USER_UUID),
        ),
        ("users", User, User.id != DEMO_USER_UUID),
        ("verification_codes", VerificationCode, True),
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
            for label, table, where in steps:
                count = await db.scalar(
                    select(func.count()).select_from(table).where(where)  # type: ignore[arg-type]
                )
                print(f"  {label:24} {count}")
            kept = await db.scalar(
                select(func.count()).select_from(User).where(User.id == DEMO_USER_UUID)
            )
            print(f"Kept: demo user ({'exists' if kept else 'MISSING — will be re-seeded on next startup'})")
            return

        print("Deleting non-demo data (demo/seed data is preserved)...")
        for label, table, where in steps:
            result = await db.execute(delete(table).where(where))  # type: ignore[arg-type]
            print(f"  {label:24} deleted {result.rowcount}")
        await db.commit()
        print("Done. Demo project, seed brand templates, and music are intact;")


if __name__ == "__main__":
    asyncio.run(main())
