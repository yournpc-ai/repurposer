"""Repro: drive-4 /chat 500 — pinned edit turn landing while an ambiguity
question is docked.

Scene (no ASR/render needed — fake clip with a caption_track, S-edit style):
  1. seed project + active clip output with word-ish cues where "of" repeats
  2. chat 「把『of』删掉」 (NO pin) → resolver ambiguity → agent docks a question
  3. chat 「『been told before』这段也删掉」 WITH pin → drive 4 returned 500 here

    cd apps/api && uv run python ../../scratch/repro_chat_500.py
    SCENARIO_API_BASE=http://127.0.0.1:8001/api/v1 (to aim at own API)
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(API_DIR / "scripts"))

import chat_scenarios as cs  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Output  # noqa: E402


async def seed_clip(pid: str) -> str:
    """An active clip version with a caption_track — enough for edit_output's
    resolver path (no render)."""
    cues = []
    t = 0.0
    for word in "I have been told before that being a woman online is fun".split():
        cues.append({"start": t, "end": t + 0.6, "text": word})
        t += 0.6
    for word in ["some", "of", "it", "is", "the", "fear", "of", "AI"]:
        cues.append({"start": t, "end": t + 0.6, "text": word})
        t += 0.6
    spec = {
        "aspect": "9:16",
        "source": {"asset_id": str(uuid.uuid4()), "kind": "video", "url": ""},
        "segments": [{"start": 0.0, "end": t}],
        "caption_track": cues,
        "caption_style_preset": "clean-bottom",
        "title": {"text": "demo", "enabled": True},
    }
    async with AsyncSessionLocal() as db:
        row = Output(
            project_id=uuid.UUID(pid),
            workflow_step_id=None,
            type="clip",
            language="en",
            provenance="real",
            payload={"duration": t},
            render_spec=spec,
        )
        db.add(row)
        await db.flush()
        oid = str(row.id)
        await db.commit()
        return oid


async def main() -> None:
    user_id = await cs.make_user()
    ctx = cs.Ctx(user_id, keep=False)
    pid = await ctx.new_project("repro chat 500")
    try:
        clip = await seed_clip(pid)
        await cs.seed_completed_run(pid)  # projects with runs go to the CHAT path (drive-4's shape)
        # Turn 1: ambiguous quote, no pin → ambiguity question docks
        t1 = await ctx.chat(pid, "把『of』删掉")
        q = (t1.get("assistant_message") or {}).get("question")
        print("turn1 intent:", (t1.get("assistant_message") or {}).get("intent"))
        print("turn1 question docked:", bool(q), (q or {}).get("question", "")[:80])
        # Turn 2: pinned edit while the question is open → drive-4's 500 slot
        res = await ctx.client.post(
            "/chat",
            json={
                "project_id": pid,
                "message": "『been told before』这段也删掉",
                "mentions": [{"type": "output", "id": clip, "label": "clip"}],
            },
        )
        print("turn2 status:", res.status_code)
        print("turn2 body:", res.text[:500])
    finally:
        await ctx.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
