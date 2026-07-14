"""Summary Agent: generate a multi-language summary from source texts."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.base import _find_derivative_plan
from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import ContentPlan, GenerationContext, Summary

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_TEXT = 150_000


class SummaryAgent:
    """Agent that generates a structured summary from source texts."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
    ) -> Summary:
        """Generate a TL;DR + key points + full summary in the target language."""
        if not asset_texts:
            raise MiniMaxError("No source texts provided for summary generation")

        trimmed_texts = [
            t[:_MAX_CHARS_PER_TEXT] for t in asset_texts if t and t.strip()
        ]
        if not trimmed_texts:
            raise MiniMaxError("No usable text found in source texts")

        derivative_plan = _find_derivative_plan(content_plan, "summary")

        template = _jinja_env.get_template("summary.j2")
        user_prompt = template.render(
            asset_texts=trimmed_texts,
            context=context.model_dump(),
            content_plan=content_plan.model_dump(),
            derivative_plan=derivative_plan,
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
