"""Quotes writer — the write_quotes tool's private agent declaration (N-30).

The quote-card craft lives in the ``quote-cards`` skill pack (N-42 指令包) —
woven in at assembly time, never loaded by the model."""

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
    # 2026-08-25 copy-writer lift (RECIPES §4.6 sixth gate): empty
    # asset_texts is allowed — quote cards without source material draw
    # from persona + user instruction. See posts/agents.py for the broader
    # rationale.
    trimmed = trim_texts(asset_texts)
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
    packs=["quote-cards"],
)
