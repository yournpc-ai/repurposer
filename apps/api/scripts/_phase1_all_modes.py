import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Phase 1 all-modes matrix: en/zh × bilingual/source_only/target_only."""
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

    matrix = [
        ("make a quote card", "bilingual", "en"),
        ("做一张金句卡", "source_only", "zh"),
        ("Make a quote card", "target_only", "en"),
        ("做一张金句卡", "bilingual", "zh"),
    ]
    for prompt, mode, lang in matrix:
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:8000/api/v1",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        ) as client:
            res = await client.post("/projects", json={"title": f"m {mode} {lang}", "event_name": ""})
            pid = res.json()["id"]
            res = await client.post("/chat", json={"project_id": pid, "message": prompt})
            if res.status_code != 201: fail(f"chat {prompt!r}", res.text)
            turn1 = res.json()
            q = turn1["assistant_message"].get("question")
            if not q or q.get("kind") != "choice":
                fail(f"{prompt!r} must dock choice", turn1["assistant_message"])
            qid = turn1["assistant_message"]["id"]
            res = await client.post(
                f"/chat/messages/{qid}/answer",
                json={"kind": "option", "option_id": f"caption_mode_{mode}"},
            )
            if res.status_code not in (200, 201): fail("answer", res.text)
            res = await client.get(f"/projects/{pid}/results")
            intent = res.json().get("pending_intent", {}).get("intent", {})
            if intent.get("caption_mode") != mode:
                fail(f"expected {mode}", intent)
            ok(f"[{lang}] {prompt!r} → caption_mode={mode}")

asyncio.run(main())
print()
print("ALL 4 MATRIX COMBOS GREEN")
