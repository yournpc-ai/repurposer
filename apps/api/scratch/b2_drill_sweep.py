"""One-off: sweep the crashed §10.2 drill's leftover rows (FK-safe)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.tables import Asset, Conversation, Message, Output, Project, User, Wallet


async def main():
    async with AsyncSessionLocal() as db:
        projects = (
            (await db.execute(select(Project).where(Project.title == "B2 10.2 drill")))
            .scalars()
            .all()
        )
        for p in projects:
            pid, uid = p.id, p.user_id
            for o in (
                (await db.execute(select(Output).where(Output.project_id == pid))).scalars().all()
            ):
                await db.delete(o)
            for a in (
                (await db.execute(select(Asset).where(Asset.project_id == pid))).scalars().all()
            ):
                await db.delete(a)
            for cv in (
                (await db.execute(select(Conversation).where(Conversation.project_id == pid)))
                .scalars()
                .all()
            ):
                for m in (
                    (await db.execute(select(Message).where(Message.conversation_id == cv.id)))
                    .scalars()
                    .all()
                ):
                    await db.delete(m)
                await db.delete(cv)
            await db.flush()
            await db.delete(p)
            await db.commit()
            print("cleaned", pid)
        if not projects:
            print("no leftovers")


asyncio.run(main())
