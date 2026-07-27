"""Quotes Agent: generate quote cards from source texts."""

import structlog

from app.skills.base import MiniMaxAgentBase, _find_slot
from app.clients.minimax import MiniMaxError
from app.models.schemas import (
    GenerationContext,
    MaterialUnderstanding,
    Quotes,
    Storyboard,
)

logger = structlog.get_logger()


class QuotesAgent(MiniMaxAgentBase):
    """Agent that generates quote cards from source texts."""

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        understanding: MaterialUnderstanding,
        storyboard: Storyboard,
    ) -> Quotes:
        """Generate quote cards.

        Args:
            asset_texts: Extracted text from project assets.
            context: Shared generation context.
            understanding: Material understanding from director step 1.
            storyboard: Storyboard from director step 2 (this output's slot).

        Returns:
            Quotes model.
        """
        if not asset_texts:
            raise MiniMaxError("No source texts provided for quotes generation")

        trimmed_texts = self._trim_texts(asset_texts)
        if not trimmed_texts:
            raise MiniMaxError("No usable text found in source texts")

        slot = _find_slot(storyboard, "quotes")
        count = slot.get("count") or 3

        template = self.jinja_env.get_template("quotes.j2")
        user_prompt = template.render(
            asset_texts=trimmed_texts,
            context=context.model_dump(),
            understanding=understanding.model_dump(),
            slot=slot,
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

        logger.info("quotes_generation_started", count=count)

        try:
            result = await self.client.generate(
                messages=messages,
                response_model=Quotes,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("quotes_generation_failed", error=str(e))
            raise MiniMaxError(f"Quotes generation failed: {e}") from e

        logger.info(
            "quotes_generation_completed",
            quotes=len(result.quotes),
        )
        return result


quotes_agent = QuotesAgent()
