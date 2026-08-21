"""Quotes writer — the write_quotes tool's private agent declaration (N-30)."""

from app.providers.llm.minimax import MiniMaxError
from app.models.schemas import (
    GenerationContext,
    MaterialUnderstanding,
    Quotes,
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
        raise MiniMaxError("No source texts provided for quotes generation")
    trimmed = trim_texts(asset_texts)
    if not trimmed:
        raise MiniMaxError("No usable text found in source texts")
    slot = find_slot(storyboard, "quotes")
    return (
        {
            "asset_texts": trimmed,
            "context": context.model_dump(),
            "understanding": understanding.model_dump(),
            "slot": slot,
            "count": slot.get("count") or 3,
        },
        [],
    )


quotes_writer: Agent[Quotes] = Agent(
    name="quotes_writer",
    prompt="quotes.j2",
    schema=Quotes,
    system=(
        "You are an expert quote-card copywriter. "
        "You only output valid JSON with no additional commentary."
    ),
    temperature=0.4,
    assemble=_assemble,
)
