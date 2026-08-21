"""Carousel writer — the write_carousel tool's private agent declaration (N-30)."""

from app.providers.llm.minimax import MiniMaxError
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
    if not asset_texts:
        raise MiniMaxError("No source texts provided for carousel generation")
    trimmed = trim_texts(asset_texts)
    if not trimmed:
        raise MiniMaxError("No usable text found in source texts")
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
)
