"""Reviser Agent: regenerate clip metadata based on human feedback."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import (
    ClipRevision,
    FeedbackReason,
    FeedbackRequest,
    FeedbackScope,
    Segment,
    SpeakerContext,
)

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)


class ReviserAgent:
    """Agent that revises clip metadata based on feedback."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def revise(
        self,
        clip_hook: str,
        clip_duration: int,
        clip_title_options: list[str],
        clip_music_mood: str,
        segment: Segment,
        feedback: FeedbackRequest,
        speaker: SpeakerContext | None,
    ) -> ClipRevision:
        """Revise clip metadata based on feedback.

        Args:
            clip_hook: Current hook text.
            clip_duration: Current duration in seconds.
            clip_title_options: Current title options.
            clip_music_mood: Current music mood.
            segment: Source segment for context.
            feedback: Human feedback.
            speaker: Speaker context for style guidance.

        Returns:
            Revised ClipRevision model.
        """
        template = _jinja_env.get_template("reviser.j2")
        user_prompt = template.render(
            hook=clip_hook,
            duration=clip_duration,
            title_options=clip_title_options,
            music_mood=clip_music_mood,
            segment=segment,
            feedback=feedback,
            speaker=speaker,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a short-form video clip revision specialist."
                    "You only output valid JSON with no additional explanation."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "clip_revision_started",
            scope=feedback.scope,
            reason=feedback.reason,
        )

        try:
            revised = await self.client.generate(
                messages=messages,
                response_model=ClipRevision,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("clip_revision_failed", error=str(e))
            raise MiniMaxError(f"Clip revision failed: {e}") from e

        logger.info(
            "clip_revision_completed",
            hook=revised.hook,
            virality_score=revised.virality_score,
        )
        return revised

    async def revise_by_instruction(
        self,
        clip_hook: str,
        clip_duration: int,
        clip_title_options: list[str],
        clip_music_mood: str,
        segment: Segment,
        instruction: str,
        speaker: SpeakerContext | None,
        scope: str = "full_script",
    ) -> ClipRevision:
        """Revise clip metadata from a free-text user instruction.

        Converts the instruction into a FeedbackRequest and delegates to
        :meth:`revise` so the same prompt template is reused.
        """
        feedback = FeedbackRequest(
            scope=FeedbackScope(scope) if scope in FeedbackScope else FeedbackScope.FULL_SCRIPT,
            reason=FeedbackReason.DIFFERENT_EXPRESSION,
            detail=instruction,
        )
        return await self.revise(
            clip_hook,
            clip_duration,
            clip_title_options,
            clip_music_mood,
            segment,
            feedback,
            speaker,
        )


reviser_agent = ReviserAgent()
