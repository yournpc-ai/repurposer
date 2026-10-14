import asyncio
import json
import sys

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.tables import Output, WorkflowStep


async def main():
    async with AsyncSessionLocal() as db:
        step = await db.get(WorkflowStep, "52dbb2a6-8bb8-4b8b-9aaa-face36f4c0ef")
        sb = (step.spec or {}).get("storyboard") or {}
        print("=== storyboard ===")
        for i, s in enumerate(sb.get("scenes") or []):
            print(i, json.dumps(s, ensure_ascii=False)[:220])
        out = await db.get(Output, "0bdf005c-fa9a-48e8-a7da-235ccffa0498")
        spec = out.render_spec or {}
        print("=== film spec scenes (frames) ===")
        for i, s in enumerate(spec.get("scenes") or []):
            keep = {k: v for k, v in s.items() if k in ("type", "frames", "dark", "image", "url")}
            keep["frames_cum"] = sum(x.get("frames", 0) for x in (spec.get("scenes") or [])[: i + 1])
            print(i, json.dumps(keep, ensure_ascii=False)[:220])


asyncio.run(main())
