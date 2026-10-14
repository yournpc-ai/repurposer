import asyncio
import sys

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

import httpx
from sqlalchemy import select, text

from app.models.database import AsyncSessionLocal
from app.models.tables import User
from app.platform.auth import create_access_token

DOOMED_TITLES = ("MG D3 failure-release probe",)
DOOMED_IDS = ["5c067fc1-ec3f-4a7f-ab30-01a341f09c07"]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).order_by(User.created_at).limit(1))).scalar_one()
        rows = (
            await db.execute(
                text("SELECT id FROM projects WHERE title IN :t").bindparams(
                    __import__("sqlalchemy").bindparam("t", expanding=True)
                ),
                {"t": list(DOOMED_TITLES)},
            )
        ).all()
    ids = DOOMED_IDS + [str(r[0]) for r in rows]
    print("deleting:", ids)
    token = create_access_token(user.id)
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    ) as http:
        r = await http.post("/api/v1/projects/bulk-delete", json={"ids": ids})
        print(r.status_code, r.text[:300])


asyncio.run(main())
