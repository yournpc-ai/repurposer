"""Forensic: dump the conversation 0cb1bb62 turns (user question + assistant answer)."""
import asyncio
import os
from pathlib import Path

import asyncpg


async def main() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    url = None
    for line in env.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    cid = "0cb1bb62-28c2-4d24-934a-b17b0d5fe6d7"

    conv = await conn.fetchrow("SELECT id, project_id FROM conversations WHERE id=$1", cid)
    if conv is None:
        proj = await conn.fetchrow("SELECT id FROM projects WHERE id=$1", cid)
        print("project hit:", proj)
        convs = await conn.fetch("SELECT id FROM conversations WHERE project_id=$1", cid)
        print("conversations:", [str(c["id"]) for c in convs])
        if not convs:
            return
        cid = str(convs[0]["id"])
    rows = await conn.fetch(
        """SELECT seq, role, intent, left(content, 2000) AS content, created_at
           FROM messages WHERE conversation_id=$1 ORDER BY seq DESC LIMIT 12""",
        cid,
    )
    for r in reversed(rows):
        print(f"--- seq={r['seq']} role={r['role']} intent={r['intent']} at={r['created_at']}")
        print(r["content"])
        print()
    await conn.close()


asyncio.run(main())
