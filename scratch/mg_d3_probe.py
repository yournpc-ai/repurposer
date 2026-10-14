import asyncio
import sys

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import text

from app.models.database import AsyncSessionLocal

PIDS = ("5c067fc1-ec3f-4a7f-ab30-01a341f09c07", "e3d354a3-334f-40f5-9d9a-86e4225bae65")


async def main():
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT r.id, r.status, r.project_id, r.created_at FROM workflow_runs r "
                    "WHERE r.project_id::text IN :pids ORDER BY r.created_at"
                ).bindparams(__import__("sqlalchemy").bindparam("pids", expanding=True)),
                {"pids": list(PIDS)},
            )
        ).all()
        for r in rows:
            print("run", r)
        rows = (
            await db.execute(
                text(
                    "SELECT s.kind, s.status, s.run_id FROM workflow_steps s "
                    "JOIN workflow_runs r ON r.id = s.run_id "
                    "WHERE r.project_id::text IN :pids ORDER BY s.seq"
                ).bindparams(__import__("sqlalchemy").bindparam("pids", expanding=True)),
                {"pids": list(PIDS)},
            )
        ).all()
        for s in rows:
            print("step", s)


asyncio.run(main())
