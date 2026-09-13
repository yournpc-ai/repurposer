"""Diagnose the 2026-09-12 write_carousel ai_unreadable failure.

Reproduces the exact carousel_writer funnel inputs of the failed run
(task book: instruction="主题：产学研合作", no material, no persona, zh,
count=6) and makes ONE real MiniMax call, printing the rendered prompt and
the raw completion / validation error. Read-only: no DB, no storage writes.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.agents.base import jinja_env  # noqa: E402
from app.models.schemas import (  # noqa: E402
    CarouselResponse,
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
)
from app.providers.llm.minimax import MiniMaxClient, MiniMaxError  # noqa: E402


def render_prompt() -> str:
    context = GenerationContext(target_language="zh", instruction="主题：产学研合作")
    understanding = MaterialUnderstanding(core_thesis="")
    storyboard = Storyboard()
    slot = {}
    kwargs = {
        "asset_texts": [],
        "context": context.model_dump(),
        "understanding": understanding.model_dump(),
        "slot": slot,
        "count": slot.get("count") or 6,
        # NOTE: the real funnel also sets packs=pack_instructions(["carousel"]),
        # but carousel.j2 never renders {{ packs }} — dropped. Kept out here so
        # the render is byte-identical to what the writer actually sent.
    }
    return jinja_env.get_template("carousel.j2").render(**kwargs)


async def main() -> None:
    prompt = render_prompt()
    print("=" * 30, "RENDERED PROMPT", "=" * 30)
    print(prompt)
    print("=" * 30, "CALLING MINIMAX (1 attempt)", "=" * 30)
    client = MiniMaxClient()
    messages = [
        {
            "role": "system",
            "content": "You are a social carousel copy expert. "
            "You only output valid JSON with no additional commentary.",
        },
        {"role": "user", "content": [{"type": "text", "text": prompt}]},
    ]
    try:
        result = await client.generate(
            messages=messages, response_model=CarouselResponse, temperature=0.4
        )
        print("VALID — model output:")
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    except MiniMaxError as exc:
        print("SCHEMA/ERROR:", str(exc)[:3000])


asyncio.run(main())
