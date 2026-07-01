"""Carousel Agent: generate a LinkedIn/social carousel from project materials."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import CarouselResponse

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_MATERIAL = 150_000


class CarouselAgent:
    """Agent that generates a swipeable carousel (cover -> points -> CTA)."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        materials: list[str],
        speaker_name: str,
        speaker_title: str | None,
        event_name: str | None = None,
        count: int = 6,
        target_language: str = "en",
        instruction: str | None = None,
    ) -> CarouselResponse:
        """Generate a carousel from speech materials.

        Args:
            materials: Extracted text from project assets.
            speaker_name: Speaker name for attribution.
            speaker_title: Speaker title.
            event_name: Optional event name.
            count: Number of slides (cover + points + CTA).
            target_language: ISO language code for the generated copy.

        Returns:
            CarouselResponse model.
        """
        if not materials:
            raise MiniMaxError("No materials provided for carousel generation")

        trimmed_materials = [
            m[:_MAX_CHARS_PER_MATERIAL] for m in materials if m and m.strip()
        ]
        if not trimmed_materials:
            raise MiniMaxError("No usable text found in materials")

        template = _jinja_env.get_template("carousel.j2")
        user_prompt = template.render(
            materials=trimmed_materials,
            speaker_name=speaker_name,
            speaker_title=speaker_title,
            event_name=event_name,
            count=count,
            target_language=target_language,
            instruction=(instruction or "").strip() or None,
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
