"""Post writer — the write_post tool's private agent declaration (N-30).

The LinkedIn long-form craft lives in the ``linkedin-longform`` skill pack
(N-42 指令包) — woven in at assembly time, never loaded by the model."""

from app.models.schemas import (
    GenerationContext,
    MaterialUnderstanding,
    Post,
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
    # asset_texts is allowed — the prompt template's ``{% for text in
    # asset_texts %}`` loop gracefully renders no source texts, the
    # understanding fields fall back to their empty defaults, and
    # ``slot.focus`` / ``slot.cta`` fall back to the prompt's defaults or
    # the persona's. The chat safety net guarantees the run is a copy-writer
    # chain before this path is taken (any non-copy-writer row in the book
    # would have caused the chain to need real material upstream).
    trimmed = trim_texts(asset_texts)
    return (
        {
            "asset_texts": trimmed,
            "context": context.model_dump(),
            "understanding": understanding.model_dump(),
            "slot": find_slot(storyboard, "post"),
        },
        [],
    )


post_writer: Agent[Post] = Agent(
    name="post_writer",
    prompt="post.j2",
    schema=Post,
    system=(
        "You are a professional social content strategist. "
        "You only output valid JSON without any additional explanation."
    ),
    temperature=0.5,
    assemble=_assemble,
    packs=["linkedin-longform"],
)
