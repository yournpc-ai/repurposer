"""一次性取证脚本：复盘 4427f90f 事故的投递面——同一句话打活 API 的 SSE，
逐帧记时间戳，看读帧之后 ~46s 生成窗内 heartbeat 是否在流、
turn.completed 是否抵达。跑完清理项目与用户。不入库任何断言库，
纯观察。"""

import asyncio
import json
import os
import sys
import time
import uuid

import httpx

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps", "api"
    ),
)

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import User  # noqa: E402
from app.platform.auth import create_access_token  # noqa: E402

BASE = os.getenv("SCENARIO_API_BASE", "http://127.0.0.1:8000/api/v1")
MESSAGE = "https://www.zymix.ai/en/ 看看这个网站呢"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = User(email=f"sse-probe-{uuid.uuid4().hex[:8]}@test.local", name="sse-probe")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = uuid.UUID(str(user.id))
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=None) as client:
        res = await client.post("/projects", json={"title": "sse probe", "event_name": ""})
        res.raise_for_status()
        pid = res.json()["id"]
        print(f"project={pid}", flush=True)

        t0 = time.monotonic()
        last = t0
        event = ""
        frames = 0
        try:
            async with client.stream(
                "POST",
                "/chat",
                json={"project_id": pid, "message": MESSAGE},
                headers={"Accept": "text/event-stream"},
            ) as res:
                print(f"[{time.monotonic()-t0:7.2f}s] OPEN status={res.status_code}", flush=True)
                async for line in res.aiter_lines():
                    now = time.monotonic()
                    gap = now - last
                    last = now
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        frames += 1
                        head = line[5:].strip()[:120]
                        print(f"[{now-t0:7.2f}s] (+{gap:5.2f}s) {event}: {head}", flush=True)
                        if event == "turn.completed":
                            payload = json.loads(line[5:].strip())
                            content = (payload.get("assistant_message") or {}).get("content") or ""
                            print(f">>> ANSWER LANDED, {len(content)} chars", flush=True)
                        if event in ("turn.completed", "turn.failed"):
                            break
                    elif line.startswith(":"):
                        print(f"[{now-t0:7.2f}s] (+{gap:5.2f}s) HEARTBEAT {line!r}", flush=True)
                    elif line == "":
                        pass
        except Exception as e:  # noqa: BLE001 — 取证脚本，全类型都报
            print(f"[{time.monotonic()-t0:7.2f}s] STREAM ENDED WITH {type(e).__name__}: {e}", flush=True)
        print(f"total frames: {frames}", flush=True)

        # 清理（FK 顺序：项目删除级联消息；用户最后）
        res = await client.delete(f"/projects/{pid}")
        print(f"cleanup project: {res.status_code}", flush=True)
    async with AsyncSessionLocal() as db:
        u = await db.get(User, user_id)
        if u is not None:
            await db.delete(u)
            await db.commit()
    print("cleanup user: done", flush=True)


asyncio.run(main())
