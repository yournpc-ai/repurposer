"""Forensics: project a40b264a — did the storyboard approval reply double-persist
or only double-render? Read-only."""

import asyncio

import asyncpg


async def main():
    conn = await asyncpg.connect(
        "postgresql://postgres:postgres@localhost:5432/repurposer"
    )
    proj = await conn.fetchrow(
        "SELECT id, title, created_at FROM projects WHERE id = 'a40b264a-3403-4ce9-9b2b-4b8f744aefc2'"
    )
    print("project:", dict(proj) if proj else None)
    conv = await conn.fetchrow(
        "SELECT id FROM conversations WHERE project_id = 'a40b264a-3403-4ce9-9b2b-4b8f744aefc2'"
    )
    if not conv:
        print("no conversation")
        return
    print("conversation:", conv["id"])
    rows = await conn.fetch(
        """SELECT id, role, turn_state, created_at,
                  left(content, 60) AS head,
                  intent IS NOT NULL AS has_intent,
                  question IS NOT NULL AS has_question,
                  workflow_run_id
           FROM messages
           WHERE conversation_id = $1
           ORDER BY created_at""",
        conv["id"],
    )
    print(f"messages: {len(rows)}")
    for r in rows:
        d = dict(r)
        print(
            d["created_at"].strftime("%H:%M:%S.%f")[:-3],
            str(d["id"])[:8],
            d["role"][:9].ljust(9),
            (d["turn_state"] or "-").ljust(9),
            "q" if d["has_question"] else "-",
            "run" if d["workflow_run_id"] else "-",
            repr(d["head"]),
        )
    # intent dumps of assistant rows (trigger / design seats)
    intents = await conn.fetch(
        """SELECT id, intent FROM messages
           WHERE conversation_id = $1 AND role = 'assistant' AND intent IS NOT NULL
           ORDER BY created_at""",
        conv["id"],
    )
    for r in intents:
        print(str(r["id"])[:8], "intent:", str(r["intent"])[:160])
    await conn.close()


asyncio.run(main())
