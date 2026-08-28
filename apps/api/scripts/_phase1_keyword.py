import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Phase 1 keyword escape hatch: bilingual/双语 in user prompt → no question."""
import asyncio
import sys
import httpx
from app.platform.auth import create_access_token
from app.models.tables import User
from app.models.database import AsyncSessionLocal
from sqlalchemy import select


def fail(msg, ctx=None):
    print(f"✗ {msg}")
    if ctx:
        import json
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"✓ {msg}")


async def main():
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        token = create_access_token(user.id)
    prompts = [
        "make a bilingual quote card",
        "做一张中英双语的 quote card",
        "中英对照 quote card",
    ]
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000/api/v1",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    ) as client:
        for prompt in prompts:
            res = await client.post("/projects", json={"title": f"kw {prompt[:20]}", "event_name": ""})
            pid = res.json()["id"]
            res = await client.post("/chat", json={"project_id": pid, "message": prompt})
            turn1 = res.json()
            q = turn1["assistant_message"].get("question")
            if q and q.get("kind") == "choice" and any(
                o.get("id", "").startswith("caption_mode_") for o in q.get("options", [])
            ):
                fail(f"keyword escape hatch should skip caption_mode question: {prompt!r}", q)
            # check caption_mode in pending_intent
            res = await client.get(f"/projects/{pid}/results")
            intent = res.json().get("pending_intent", {}).get("intent", {})
            if intent.get("caption_mode") != "bilingual":
                fail(f"keyword escape hatch should land bilingual, got {intent.get('caption_mode')}", intent)
            ok(f"[kw] {prompt!r} → auto-bilingual (no question)")

asyncio.run(main())
print()
print("KEYWORD ESCAPE HATCH GREEN")
