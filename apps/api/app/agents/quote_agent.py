"""Quote Agent: generate quote cards from project materials."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.base import _find_derivative_plan
from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import ContentPlan, GenerationContext, QuoteCardsResponse

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_MATERIAL = 150_000


class QuoteAgent:
    """Agent that generates quote cards from speech materials."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        materials: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
    ) -> QuoteCardsResponse:
        """Generate quote cards.

        Args:
            materials: Extracted text from project assets.
            context: Shared generation context.
            content_plan: Unified content plan.

        Returns:
            QuoteCardsResponse model.
        """
        if not materials:
            raise MiniMaxError("No materials provided for quote card generation")

        trimmed_materials = [
            m[:_MAX_CHARS_PER_MATERIAL] for m in materials if m and m.strip()
        ]
        if not trimmed_materials:
            raise MiniMaxError("No usable text found in materials")

        derivative_plan = _find_derivative_plan(content_plan, "quote_card")
        count = derivative_plan.get("count") or 3

        template = _jinja_env.get_template("quote_agent.j2")
        user_prompt = template.render(
            materials=trimmed_materials,
            context=context.model_dump(),
            content_plan=content_plan.model_dump(),
            derivative_plan=derivative_plan,
            count=count,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert quote-card copywriter. "
                    "You only output valid JSON with no additional commentary."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info("quote_card_generation_started", count=count)

        try:
            result = await self.client.generate(
                messages=messages,
                response_model=QuoteCardsResponse,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("quote_card_generation_failed", error=str(e))
            raise MiniMaxError(f"Quote card generation failed: {e}") from e

        logger.info(
            "quote_card_generation_completed",
            quotes=len(result.quotes),
        )
        return result


quote_agent = QuoteAgent()
