"""Summary Agent: generate a multi-language summary from project materials."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import SpeakerPersona, Summary

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_MATERIAL = 150_000


class SummaryAgent:
    """Agent that generates a structured summary from speech materials."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        materials: list[str],
        persona: SpeakerPersona | None,
        event_name: str | None = None,
        target_language: str = "en",
        instruction: str | None = None,
    ) -> Summary:
        """Generate a TL;DR + key points + full summary in the target language."""
        if not materials:
            raise MiniMaxError("No materials provided for summary generation")

        trimmed_materials = [
            m[:_MAX_CHARS_PER_MATERIAL] for m in materials if m and m.strip()
        ]
        if not trimmed_materials:
            raise MiniMaxError("No usable text found in materials")

        template = _jinja_env.get_template("summary.j2")
        user_prompt = template.render(
            materials=trimmed_materials,
            persona=persona,
            event_name=event_name,
            target_language=target_language,
            instruction=(instruction or "").strip() or None,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional content editor. You only output valid JSON, with no additional explanations."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info("summary_generation_started")
        try:
            result = await self.client.generate(
                messages=messages,
                response_model=Summary,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("summary_generation_failed", error=str(e))
            raise MiniMaxError(f"Summary generation failed: {e}") from e

        logger.info("summary_generation_completed", points=len(result.key_points))
        return result


summary_agent = SummaryAgent()
