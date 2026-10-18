"""Forensic: storyboard drafting timeline for project b0ab991f — start, end, duration, outcome."""
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
        "b0ab991f-dab5-4e38-aef8-04062a39d253",
    )
    cid = str(convs[0]["id"])

    print("=== messages seq>=7 ===")
    rows = await conn.fetch(
        """SELECT seq, role, intent, left(content, 300) AS content, created_at
           FROM messages WHERE conversation_id=$1 AND seq >= 7 ORDER BY seq""",
        cid,
    )
    for r in rows:
        print(f"seq={r['seq']} role={r['role']} at={r['created_at']}")
        print("  intent:", str(r["intent"])[:400])
        if r["content"]:
            print("  content:", r["content"][:200].replace("\n", " | "))

    print("\n=== assets (web pages) ===")
    assets = await conn.fetch(
        """SELECT id, type, processing_status, created_at, updated_at
           FROM assets WHERE project_id=$1 ORDER BY created_at""",
        "b0ab991f-dab5-4e38-aef8-04062a39d253",
    )
    for a in assets:
        print(f"  {a['type']} status={a['processing_status']} created={a['created_at']} updated={a['updated_at']}")

    print("\n=== workflow runs ===")
    runs = await conn.fetch(
        """SELECT id, status, created_at, updated_at FROM workflow_runs
           WHERE project_id=$1 ORDER BY created_at""",
        "b0ab991f-dab5-4e38-aef8-04062a39d253",
    )
    for r in runs:
        print(f"  run {r['id']} status={r['status']} created={r['created_at']} updated={r['updated_at']}")

    print("\n=== project pending_brief keys ===")
    proj = await conn.fetchrow(
        "SELECT pending_brief FROM projects WHERE id=$1",
        "b0ab991f-dab5-4e38-aef8-04062a39d253",
    )
    pb = proj["pending_brief"]
    print("  pending_brief present:", pb is not None, str(pb)[:300] if pb else "")
    await conn.close()


asyncio.run(main())
