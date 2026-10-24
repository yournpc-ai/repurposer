"""Read-only forensics part 3: full intent JSON per turn, run ctx digests."""

import asyncio
import json

import asyncpg

PROJECT = "d08af2af-02d4-4a04-9483-4db03ff6ef0d"


async def main():
    conn = await asyncpg.connect(
        "postgresql://postgres:postgres@localhost:5432/repurposer"
    )

    msgs = await conn.fetch(
        """SELECT m.seq, m.role, m.intent
           FROM messages m JOIN conversations c ON c.id = m.conversation_id
           WHERE c.project_id=$1 AND m.intent IS NOT NULL ORDER BY m.seq""",
        PROJECT)
    for m in msgs:
        intent = m["intent"]
        if isinstance(intent, str):
            intent = json.loads(intent)
        print(f"\n--- seq={m['seq']} role={m['role']}")
        print(json.dumps(intent, ensure_ascii=False, default=str)[:3000])

    print("=" * 100)
    runs = await conn.fetch(
        "SELECT id, context FROM workflow_runs WHERE project_id=$1 ORDER BY created_at",
        PROJECT)
    for r in runs:
        ctx = r["context"]
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        print(f"\nrun {str(r['id'])[:8]}:")
        for k in ("film_storyboard_content_digest", "film_storyboard_fingerprint",
                  "film_storyboard_version", "film_created_via", "film_base_version",
                  "instruction"):
            print(f"  {k}:", json.dumps(ctx.get(k), ensure_ascii=False, default=str)[:400])

    await conn.close()


asyncio.run(main())
