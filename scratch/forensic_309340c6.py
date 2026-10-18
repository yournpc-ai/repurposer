"""Forensic: project 309340c6 — dock/captures/blocks state after worker restart."""
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
    pid = "309340c6-06e9-464d-8e8d-029feb10a912"
    proj = await conn.fetchrow(
        "SELECT id, pending_brief IS NOT NULL AS has_brief FROM projects WHERE id=$1", pid
    )
    print("project:", dict(proj) if proj else None)
    assets = await conn.fetch(
        "SELECT type, processing_status, created_at FROM assets WHERE project_id=$1 ORDER BY created_at",
        pid,
    )
    for a in assets:
        print("asset:", a["type"], a["processing_status"], a["created_at"])
    convs = await conn.fetch("SELECT id FROM conversations WHERE project_id=$1", pid)
    for c in convs:
        cid = str(c["id"])
        rows = await conn.fetch(
            """SELECT seq, role, intent->>'type' AS itype, left(content, 90) AS content, created_at
               FROM messages WHERE conversation_id=$1 ORDER BY seq""",
            cid,
        )
        print(f"--- conversation {cid}")
        for r in rows:
            print(
                f"seq={r['seq']} {r['role']:<9} itype={r['itype'] or '-':<22} at={r['created_at']}  {(r['content'] or '').replace(chr(10), ' | ')}"
            )
    await conn.close()


asyncio.run(main())
