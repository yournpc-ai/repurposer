"""Quote Agent: generate quote cards from source texts."""

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

_MAX_CHARS_PER_TEXT = 150_000


class QuoteAgent:
    """Agent that generates quote cards from source texts."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
    ) -> QuoteCardsResponse:
        """Generate quote cards.

        Args:
            asset_texts: Extracted text from project assets.
            context: Shared generation context.
            content_plan: Unified content plan.

        Returns:
            QuoteCardsResponse model.
        """
        if not asset_texts:
            raise MiniMaxError("No source texts provided for quote card generation")

        trimmed_texts = [
            t[:_MAX_CHARS_PER_TEXT] for t in asset_texts if t and t.strip()
        ]
        if not trimmed_texts:
            raise MiniMaxError("No usable text found in source texts")

        derivative_plan = _find_derivative_plan(content_plan, "quote_card")
        count = derivative_plan.get("count") or 3

        template = _jinja_env.get_template("quote_agent.j2")
        user_prompt = template.render(
            asset_texts=trimmed_texts,
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
