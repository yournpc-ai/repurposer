"""Article writer — the write_article tool's private agent declaration (N-30)."""

from app.clients.minimax import MiniMaxError
from app.models.schemas import (
    Article,
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
        raise MiniMaxError("No source texts provided for article generation")
    trimmed = trim_texts(asset_texts)
    if not trimmed:
        raise MiniMaxError("No usable text found in source texts")
    return (
        {
            "asset_texts": trimmed,
            "context": context.model_dump(),
            "understanding": understanding.model_dump(),
            "slot": find_slot(storyboard, "article"),
        },
        [],
    )


article_writer: Agent[Article] = Agent(
    name="article_writer",
    prompt="article.j2",
    schema=Article,
    system=(
        "You are a professional article writer. You only output valid "
        "JSON, with no additional explanations."
    ),
    temperature=0.6,
    assemble=_assemble,
)
