"""Forensic: conversation b1d6403b — activity timing chain + storyboard outcome."""
import asyncio
from pathlib import Path

import asyncpg


async def main() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    url = None
    for line in env.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    convs = await conn.fetch(
        "SELECT id FROM conversations WHERE project_id=$1",
        "b1d6403b-f3aa-4b5c-a4c1-86c7b2867af2",
    )
    if not convs:
        conv = await conn.fetchrow(
            "SELECT id FROM conversations WHERE id=$1",
            "b1d6403b-f3aa-4b5c-a4c1-86c7b2867af2",
        )
        convs = [conv] if conv else []
    if not convs:
        print("no conversation")
        return
    cid = str(convs[0]["id"])
    rows = await conn.fetch(
        """SELECT seq, role, intent, left(content, 200) AS content, created_at
           FROM messages WHERE conversation_id=$1 ORDER BY seq""",
        cid,
    )
    for r in rows:
        intent = str(r["intent"])[:260] if r["intent"] else ""
        content = (r["content"] or "")[:120].replace("\n", " | ")
        print(f"seq={r['seq']} {r['role']:<9} at={r['created_at']}\n   {intent}\n   {content}")
    await conn.close()


asyncio.run(main())
