"""Revise skill's private procedures (ADR-039: domain orchestration lives in
the skill package, not in the agent declaration)."""

from app.models.schemas import (
    ClipRevision,
    FeedbackReason,
    FeedbackRequest,
    FeedbackScope,
    Segment,
    PersonaContext,
)

from app.skills.revise.agents import reviser


async def revise_by_instruction(
    clip_hook: str,
    clip_duration: int,
    clip_title_options: list[str],
    clip_music_mood: str,
    segment: Segment,
    instruction: str,
    persona: PersonaContext | None,
    scope: str = "full_script",
) -> ClipRevision:
    """Revise clip metadata from a free-text user instruction.

    Converts the instruction into a FeedbackRequest and delegates to the
    reviser declaration so the same prompt template is reused.
    """
    # Note: ``scope in FeedbackScope`` is Python 3.12+ only; on 3.11
    # (our floor) enum-class membership raises TypeError — use try/except.
    try:
        fb_scope = FeedbackScope(scope)
    except ValueError:
        fb_scope = FeedbackScope.FULL_SCRIPT
    feedback = FeedbackRequest(
        scope=fb_scope,
        reason=FeedbackReason.DIFFERENT_EXPRESSION,
        detail=instruction,
    )
    return await reviser.call(
        clip_hook=clip_hook,
        clip_duration=clip_duration,
        clip_title_options=clip_title_options,
        clip_music_mood=clip_music_mood,
        segment=segment,
        feedback=feedback,
        persona=persona,
    )
