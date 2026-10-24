"""Read-only forensics part 2: question/answer payloads, raw pending_brief,
full file keys, run prepared_storyboard scenes."""

import asyncio
import json

import asyncpg

PROJECT = "d08af2af-02d4-4a04-9483-4db03ff6ef0d"


async def main():
    conn = await asyncpg.connect(
        "postgresql://postgres:postgres@localhost:5432/repurposer"
    )

    print("=" * 100)
    print("RAW pending_brief (repr, first 200 chars)")
    pb = await conn.fetchval("SELECT pending_brief FROM projects WHERE id=$1", PROJECT)
    print(repr(pb)[:200])

    print("=" * 100)
    print("MESSAGES with question/answer")
    msgs = await conn.fetch(
        """SELECT m.seq, m.created_at, m.role, m.content, m.question, m.answer
           FROM messages m JOIN conversations c ON c.id = m.conversation_id
           WHERE c.project_id=$1 AND (m.question IS NOT NULL OR m.answer IS NOT NULL)
           ORDER BY m.seq""",
        PROJECT)
    for m in msgs:
        print(f"\n--- seq={m['seq']} {m['created_at']}")
        print("  Q:", json.dumps(m["question"], ensure_ascii=False, default=str)[:2000])
        print("  A:", json.dumps(m["answer"], ensure_ascii=False, default=str)[:2000])

    print("=" * 100)
    print("RUN prepared_storyboard scenes")
    runs = await conn.fetch(
        "SELECT id, context FROM workflow_runs WHERE project_id=$1 ORDER BY created_at",
        PROJECT)
    for r in runs:
        ctx = r["context"]
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        print(f"\n--- run {str(r['id'])[:8]} version={ctx.get('film_storyboard_version')} created_via={ctx.get('film_created_via')}")
        print("    film_execution:", json.dumps(ctx.get("film_execution"), ensure_ascii=False, default=str)[:400])
        print("    confirmed_scope:", json.dumps(ctx.get("confirmed_scope"), ensure_ascii=False, default=str)[:300])
        print("    scope:", json.dumps(ctx.get("scope"), ensure_ascii=False, default=str)[:200])
        print("    film_base_version:", ctx.get("film_base_version"))
        print("    film_draft_token:", ctx.get("film_draft_token"))
        board = ctx.get("prepared_storyboard") or {}
        if isinstance(board, str):
            board = json.loads(board)
        scenes = board.get("scenes") if isinstance(board, dict) else None
        if scenes:
            for i, s in enumerate(scenes):
                keep = {k: s[k] for k in ("id", "type", "seconds", "dark", "motion", "enter", "lines") if k in s}
                print(f"    scene[{i}]:", json.dumps(keep, ensure_ascii=False, default=str)[:300])

    print("=" * 100)
    print("OUTPUT full file keys")
    outs = await conn.fetch(
        "SELECT id, files FROM outputs WHERE project_id=$1 ORDER BY created_at", PROJECT)
    for o in outs:
        print(o["id"], json.dumps(o["files"], ensure_ascii=False))

    await conn.close()


asyncio.run(main())
