"""Forensic: dump conversation b0ab991f full turn chain with intents + turn_state."""
import asyncio
import json
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
    rows = await conn.fetch(
        """SELECT seq, role, left(content, 1500) AS content, intent, turn_state,
                  question IS NOT NULL AS has_question, workflow_run_id, created_at
           FROM messages WHERE conversation_id=$1 ORDER BY seq""",
        cid,
    )
    for r in rows:
        print(f"--- seq={r['seq']} role={r['role']} run={r['workflow_run_id']} q={r['has_question']} at={r['created_at']}")
        if r["intent"]:
            print("intent:", str(r["intent"])[:300])
        if r["turn_state"]:
            print("turn_state:", str(r["turn_state"])[:300])
        print(r["content"])
        print()
    await conn.close()


asyncio.run(main())
