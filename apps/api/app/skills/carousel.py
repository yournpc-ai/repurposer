"""Carousel Agent: generate a LinkedIn/social carousel from source texts."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.skills.base import _find_slot
from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import (
    CarouselResponse,
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
)

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_TEXT = 150_000


class CarouselAgent:
    """Agent that generates a swipeable carousel (cover -> points -> CTA)."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        understanding: MaterialUnderstanding,
        storyboard: Storyboard,
    ) -> CarouselResponse:
        """Generate a carousel from source texts.

        Args:
            asset_texts: Extracted text from project assets.
            context: Shared generation context.
            understanding: Material understanding from director step 1.
            storyboard: Storyboard from director step 2 (this output's slot).

        Returns:
            CarouselResponse model.
        """
        if not asset_texts:
            raise MiniMaxError("No source texts provided for carousel generation")

        trimmed_texts = [
            t[:_MAX_CHARS_PER_TEXT] for t in asset_texts if t and t.strip()
        ]
        if not trimmed_texts:
            raise MiniMaxError("No usable text found in source texts")

        slot = _find_slot(storyboard, "carousel")
        count = slot.get("count") or 6

        template = _jinja_env.get_template("carousel.j2")
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
                    "You are a LinkedIn carousel copy expert."
                    "You only output valid JSON with no additional commentary."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info("carousel_generation_started", count=count)

        try:
            result = await self.client.generate(
                messages=messages,
                response_model=CarouselResponse,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("carousel_generation_failed", error=str(e))
            raise MiniMaxError(f"Carousel generation failed: {e}") from e

        logger.info("carousel_generation_completed", slides=len(result.slides))
        return result


carousel_agent = CarouselAgent()
