import asyncio
import json
import sys

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select, text

from app.models.database import AsyncSessionLocal
from app.models.tables import Message

PID = "e3d354a3-334f-40f5-9d9a-86e4225bae65"


async def main():
    async with AsyncSessionLocal() as db:
        conv_id = (
            await db.execute(
                text("SELECT id FROM conversations WHERE project_id = :pid"),
                {"pid": PID},
            )
        ).scalar_one()
        msgs = list(
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id)
                    .order_by(Message.created_at)
                )
            )
            .scalars()
            .all()
        )
        for m in msgs:
            print("===", m.role, m.created_at)
            print("content:", (m.content or "")[:400])
            for attr in ("intent", "question", "answer", "candidates"):
                v = getattr(m, attr, None)
                if v:
                    print(f"{attr}:", json.dumps(v, ensure_ascii=False, default=str)[:1200])
        runs = (
            await db.execute(
                text("SELECT count(*) FROM workflow_runs WHERE project_id = :pid"),
                {"pid": PID},
            )
        ).scalar_one()
        print("runs:", runs)


asyncio.run(main())
