"""Replay the 02:23 stuck turn against the live stack over SSE:
fresh project → upload xy_2_15s.mp4 (real bytes from TOS) → immediately
POST /chat with Accept: text/event-stream while the asset is still
processing → print every SSE frame with timestamps. Proves whether the
terminal turn.completed frame leaves the server.
"""
import asyncio
import json
import sys
import time
import uuid

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

import httpx

from app.platform.auth import create_access_token
from app.providers.storage import presign_download

BASE = "http://127.0.0.1:8000/api/v1"
OWNER = uuid.UUID("52037604-9321-4b70-9212-445ccf5ade60")
SRC_KEY = "52037604-9321-4b70-9212-445ccf5ade60/uploads/projects/5f1a090b-7111-4cad-85cd-44bc370f0464/xy_2_15s-1789583015-HB6_Hw.mp4"
MSG = "Caption my video in Chinese and French — Chinese as bilingual subtitles."


async def main():
    token = create_access_token(OWNER)
    async with httpx.AsyncClient(base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=60) as c:
        # 1. fetch the real bytes
        dl = await presign_download(SRC_KEY, ttl=300)
        vid = httpx.get(dl, timeout=120)
        vid.raise_for_status()
        print(f"· source bytes: {len(vid.content)}")

        # 2. fresh project + upload via the real endpoints
        proj = (await c.post("/projects", json={"title": "sse-replay"})).json()
        pid = proj["id"]
        up = (await c.post(f"/projects/{pid}/assets/upload-url",
                           json={"filename": "xy_2_15s.mp4", "content_type": "video/mp4"})).json()
        put = httpx.put(up["upload_url"], content=vid.content,
                        headers={"Content-Type": "video/mp4"}, timeout=120)
        put.raise_for_status()
        asset = (await c.post(f"/projects/{pid}/assets", json={
            "key": up["key"], "title": "xy_2_15s.mp4", "type": "video",
        })).json()
        print(f"· project {pid} asset {asset['id']} status={asset.get('processing_status')}")

        # 3. the chat turn over SSE — log every frame
        t0 = time.time()
        async with c.stream(
            "POST", "/chat",
            headers={"Accept": "text/event-stream"},
            json={"project_id": pid, "message": MSG},
            timeout=httpx.Timeout(300, connect=10),
        ) as res:
            print(f"· SSE open: {res.status_code}")
            event = ""
            async for line in res.aiter_lines():
                t = time.time() - t0
                if line.startswith("event:"):
                    event = line[6:].strip()
                    print(f"[{t:6.1f}] event: {event}")
                elif line.startswith("data:"):
                    data = line[5:].strip()
                    if event in ("assistant.delta",):
                        print(f"[{t:6.1f}]   delta {data[:60]}")
                    else:
                        print(f"[{t:6.1f}]   data {data[:200]}")
                elif line.startswith(":"):
                    print(f"[{time.time()-t0:6.1f}]   heartbeat")
        print(f"· stream closed by server at {time.time()-t0:.1f}s")


asyncio.run(main())
