"""Forensic: dump conversation b0ab991f activity/tool events around the web-page read."""
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
    cid = "b0ab991f-dab5-4e38-aef8-04062a39d253"

    conv = await conn.fetchrow("SELECT id, project_id FROM conversations WHERE id=$1", cid)
    if conv is None:
        convs = await conn.fetch("SELECT id FROM conversations WHERE project_id=$1", cid)
        print("conversations:", [str(c["id"]) for c in convs])
        if not convs:
            return
        cid = str(convs[0]["id"])
    cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name='messages' ORDER BY ordinal_position"
    )
    print("message columns:", [c["column_name"] for c in cols])
    rows = await conn.fetch(
        """SELECT seq, role, left(content, 800) AS content, created_at
           FROM messages WHERE conversation_id=$1 ORDER BY seq DESC LIMIT 8""",
        cid,
    )
    for r in reversed(rows):
        print(f"--- seq={r['seq']} role={r['role']} at={r['created_at']}")
        print(r["content"])
        print()
    await conn.close()


asyncio.run(main())
