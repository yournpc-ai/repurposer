import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Phase 1 zh variant: 中文 prompt + 中文 answer."""
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
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000/api/v1",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    ) as client:
        res = await client.post("/projects", json={"title": "zh phase1", "event_name": ""})
        pid = res.json()["id"]

        # 中文 prompt
        res = await client.post("/chat", json={"project_id": pid, "message": "做一张金句卡"})
        if res.status_code != 201: fail("zh turn1", res.text)
        turn1 = res.json()
        q = turn1["assistant_message"].get("question")
        if not q: fail("must dock a question", turn1)
        if q.get("kind") != "choice": fail("must be choice", q)
        labels = [o["label"] for o in q.get("options", [])]
        if not any("双语" in lbl for lbl in labels):
            fail("expected zh labels with 双语", labels)
        ok(f"zh dock question labels: {labels}")
        qid = turn1["assistant_message"]["id"]

        # source_only
        res = await client.post(
            f"/chat/messages/{qid}/answer",
            json={"kind": "option", "option_id": "caption_mode_source_only"},
        )
        if res.status_code not in (200, 201): fail("answer", res.text)
        follow = res.json().get("follow_up")
        if not follow or follow.get("question", {}).get("kind") != "task_book":
            fail("expected task_book follow_up", res.json())
        ok("zh answer → task_book follow_up")

        # 验证 caption_mode
        res = await client.get(f"/projects/{pid}/results")
        if res.status_code != 200: fail("results", res.text)
        intent = res.json().get("pending_intent", {}).get("intent", {})
        if intent.get("caption_mode") != "source_only":
            fail("expected caption_mode=source_only", intent)
        ok(f"pending_intent.caption_mode = {intent['caption_mode']!r}")

asyncio.run(main())
print()
print("ZH VARIANT GREEN")
