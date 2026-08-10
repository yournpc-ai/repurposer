"""Reviser — the revise_script skill's private agent declaration (N-30).

Revises clip metadata (hook / titles / music mood / duration) from human
feedback, using the source segment and persona for grounding.
"""

from app.models.schemas import (
    ClipRevision,
    FeedbackRequest,
    Segment,
    PersonaContext,
)

from app.agents.base import Agent


def _assemble(
    clip_hook: str,
    clip_duration: int,
    clip_title_options: list[str],
    clip_music_mood: str,
    segment: Segment,
    feedback: FeedbackRequest,
    persona: PersonaContext | None,
):
    return (
        {
            "hook": clip_hook,
            "duration": clip_duration,
            "title_options": clip_title_options,
            "music_mood": clip_music_mood,
            "segment": segment,
            "feedback": feedback,
            "persona": persona,
        },
        [],
    )


reviser: Agent[ClipRevision] = Agent(
    name="reviser",
    prompt="reviser.j2",
    schema=ClipRevision,
    system=(
        "You are a short-form video clip revision specialist."
        "You only output valid JSON with no additional explanation."
    ),
    temperature=0.4,
    assemble=_assemble,
)
