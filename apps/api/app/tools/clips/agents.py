"""Clip writer — the clips tool's private agent declaration (N-30).

Plans vertical clips from the shared GenerationContext, the understand node's
MaterialUnderstanding (step 1), and its aggregate Storyboard slot (step 2):
segment selection plus clip scripts in one call.
"""

from app.providers.llm.minimax import MiniMaxError
from app.models.schemas import (
    ClipPlans,
    GenerationContext,
    MaterialUnderstanding,
    MediaInput,
    Storyboard,
)

from app.agents.base import Agent, find_slot, trim_texts


def _assemble(
    asset_texts: list[str],
    context: GenerationContext,
    understanding: MaterialUnderstanding,
    storyboard: Storyboard,
    asset_media: list[MediaInput] | None = None,
    clip_count: int = 3,
    anchored_transcript: str | None = None,
    music_pieces: list[dict[str, str]] | None = None,
):
    """Inputs for clip planning.

    ``anchored_transcript``: the full-talk transcript with ``[start-end]``
    line anchors (``app.tools.clips.transcript.build_anchored_transcript``) so the
    agent can output exact ``start_seconds`` / ``end_seconds``.
    ``music_pieces``: available music library pieces (``id``/``mood``/
    ``title``) the agent selects from per clip.
    """
    if not asset_texts and not asset_media:
        raise MiniMaxError("No source texts or media provided for clip planning")
    media = asset_media or []
    trimmed = trim_texts(asset_texts)
    if not trimmed and not media:
        raise MiniMaxError("No usable text or media found")

    # Resolve the clips slot's argument ids to their text so the prompt
    # reads as guidance, not cross-references.
    slot = find_slot(storyboard, "clips")
    if slot.get("argument_ids"):
        arg_text_by_id = {a.id: a.text for a in understanding.key_arguments}
        slot["argument_texts"] = [
            arg_text_by_id[i] for i in slot["argument_ids"] if i in arg_text_by_id
        ]

    return (
        {
            "asset_texts": trimmed,
            "asset_media": media,
            "clip_count": clip_count,
            "context": context.model_dump(),
            "understanding": understanding.model_dump(),
            "slot": slot,
            "anchored_transcript": anchored_transcript,
            "music_pieces": music_pieces or [],
        },
        media,
    )


clip_writer: Agent[ClipPlans] = Agent(
    name="clip_writer",
    prompt="clip_agent.j2",
    schema=ClipPlans,
    system=(
        "You are a senior content strategist and short-form video "
        "director. You output valid JSON only, with no extra commentary."
    ),
    temperature=0.4,
    assemble=_assemble,
    media_text_fallback=True,
)
