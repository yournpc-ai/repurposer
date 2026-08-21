"""Post writer — the write_post tool's private agent declaration (N-30).

The LinkedIn long-form craft lives in the ``linkedin-longform`` skill pack
(N-42 指令包) — woven in at assembly time, never loaded by the model."""

from app.providers.llm.minimax import MiniMaxError
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
    if not asset_texts:
        raise MiniMaxError("No source texts provided for post generation")
    trimmed = trim_texts(asset_texts)
    if not trimmed:
        raise MiniMaxError("No usable text found in source texts")
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
