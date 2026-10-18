"""Probe: stream the exact storyboarder call for 309340c6 and watch the tokens.

Answers: does MiniMax return at all? how fast do bytes arrive? what does the
raw generation look like (schema-conformant JSON or runaway ramble)?
Non-destructive: one read-only LLM call, no DB writes.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Project  # noqa: E402
from app.providers.llm.minimax import minimax_client  # noqa: E402
from app.tools.film.storyboard import (  # noqa: E402
    DraftStoryboard,
    film_storyboarder,
    load_storyboard_pages,
    page_media_inputs,
)

PID = "309340c6-06e9-464d-8e8d-029feb10a912"
PROMPT_FILE = Path(__file__).resolve().parents[1] / "scratch" / "replay_storyboard_prompt.md"
CAP_S = 300.0


async def main() -> None:
    user_prompt = PROMPT_FILE.read_text()
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, PID)
        pages = await load_storyboard_pages(db, project)
    media = await page_media_inputs(pages)
    print(f"prompt {len(user_prompt)} chars, media parts {len(media)}")
    # Byte-faithful to agents/base.py:_user_message — media parts first
    # (each with its optional caption), the text prompt LAST.
    content_parts: list[dict] = []
    for m in media:
        key = f"{m.type}_url"
        content_parts.append({"type": key, key: {"url": m.data_url}})
        if m.caption:
            content_parts.append({"type": "text", "text": m.caption})
    content_parts.append({"type": "text", "text": user_prompt})
    messages = [
        {"role": "system", "content": film_storyboarder.system},
        {"role": "user", "content": content_parts},
    ]
    t0 = time.monotonic()
    state = {"chars": 0, "first": None, "last_print": 0.0}

    async def on_delta(fragment: str) -> None:
        state["chars"] += len(fragment)
        if state["first"] is None:
            state["first"] = time.monotonic() - t0
            print(f"[{state['first']:.1f}s] FIRST BYTES")
        now = time.monotonic() - t0
        if now - state["last_print"] >= 10:
            state["last_print"] = now
            print(f"[{now:.1f}s] received {state['chars']} chars")

    async def on_reasoning(fragment: str) -> None:
        pass

    try:
        result = await asyncio.wait_for(
            minimax_client.generate_stream(
                messages=messages,
                response_model=DraftStoryboard,
                temperature=0.5,
                on_delta=on_delta,
                on_reasoning=on_reasoning,
            ),
            timeout=CAP_S,
        )
        dt = time.monotonic() - t0
        print(f"[{dt:.1f}s] DONE — validated DraftStoryboard, {len(result.scenes)} scenes")
        for i, s in enumerate(result.scenes):
            print(f"  scene[{i}] {s.type} {s.seconds}s")
    except asyncio.TimeoutError:
        print(f"[{CAP_S:.0f}s] HARD CAP — stream still open, {state['chars']} chars received")
    except Exception as e:
        dt = time.monotonic() - t0
        print(f"[{dt:.1f}s] ERROR after {state['chars']} chars: {type(e).__name__}: {e}")


asyncio.run(main())
