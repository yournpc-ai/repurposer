"""Reviser Agent: regenerate a clip script based on human feedback."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import ClipScript, FeedbackRequest, Segment, SpeakerPersona

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)


class ReviserAgent:
    """Agent that revises clip scripts based on human feedback."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def revise(
        self,
        script: ClipScript,
        segment: Segment,
        feedback: FeedbackRequest,
        persona: SpeakerPersona | None,
    ) -> ClipScript:
        """Revise a clip script based on feedback.

        Args:
            script: Original generated clip script.
            segment: Source segment for context.
            feedback: Human feedback.
            persona: Speaker style persona.

        Returns:
            Revised ClipScript model.
        """
        template = _jinja_env.get_template("reviser.j2")
        user_prompt = template.render(
            script=script,
            segment=segment,
            feedback=feedback,
            persona=persona,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a short-form video script revision specialist."
                    "You only output valid JSON with no additional explanation."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "script_revision_started",
            scope=feedback.scope,
            reason=feedback.reason,
        )

        try:
            revised = await self.client.generate(
                messages=messages,
                response_model=ClipScript,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("script_revision_failed", error=str(e))
            raise MiniMaxError(f"Script revision failed: {e}") from e

        if revised.virality_score is None:
            revised.virality_score = script.virality_score

        logger.info(
            "script_revision_completed",
            hook=revised.hook,
            virality_score=revised.virality_score,
        )
        return revised


reviser_agent = ReviserAgent()
