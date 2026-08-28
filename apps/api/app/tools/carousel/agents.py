"""Carousel writer — the write_carousel tool's private agent declaration (N-30).

The carousel craft lives in the ``carousel`` skill pack (N-42 指令包) —
woven in at assembly time, never loaded by the model."""

from app.models.schemas import (
    CarouselResponse,
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
)

from app.agents.base import Agent, find_slot, trim_texts


def _assemble(
    asset_texts: list[str],
    context: GenerationContext,
    understanding: MaterialUnderstanding,
    storyboard: Storyboard,
):
    # 2026-08-25 copy-writer lift (RECIPES §4.6 sixth gate): empty
    # asset_texts is allowed — carousel slides draw from persona + topic.
    # See posts/agents.py for the broader rationale.
    trimmed = trim_texts(asset_texts)
    slot = find_slot(storyboard, "carousel")
    return (
        {
            "asset_texts": trimmed,
            "context": context.model_dump(),
            "understanding": understanding.model_dump(),
            "slot": slot,
            "count": slot.get("count") or 6,
        },
        [],
    )


carousel_writer: Agent[CarouselResponse] = Agent(
    name="carousel_writer",
    prompt="carousel.j2",
    schema=CarouselResponse,
    system=(
        "You are a LinkedIn carousel copy expert."
        "You only output valid JSON with no additional commentary."
    ),
    temperature=0.4,
    assemble=_assemble,
    packs=["carousel"],
)
