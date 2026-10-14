import asyncio
import sys

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import text

from app.models.database import AsyncSessionLocal

PID = "e3d354a3-334f-40f5-9d9a-86e4225bae65"


async def main():
    async with AsyncSessionLocal() as db:
        for table in ("graph_nodes", "graph_edges"):
            try:
                rows = (
                    await db.execute(
                        text(f"SELECT * FROM {table} WHERE project_id = :pid"),
                        {"pid": PID},
                    )
                ).mappings().all()
                print(f"=== {table} ({len(rows)}) ===")
                for r in rows:
                    print({k: str(v)[:60] for k, v in r.items() if v is not None and k not in ("created_at", "updated_at")})
            except Exception as e:
                print(table, "ERR", str(e)[:100])


asyncio.run(main())
