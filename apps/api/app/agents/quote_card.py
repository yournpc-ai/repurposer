"""Quote Card Agent: generate quote cards from project materials."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import QuoteCardsResponse

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_MATERIAL = 150_000


class QuoteCardAgent:
    """Agent that generates quote cards from speech materials."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        materials: list[str],
        speaker_name: str,
        speaker_title: str | None,
        event_name: str | None = None,
        count: int = 3,
        target_language: str = "en",
        instruction: str | None = None,
    ) -> QuoteCardsResponse:
        """Generate quote cards.

        Args:
            materials: Extracted text from project assets.
            speaker_name: Speaker name for attribution.
            speaker_title: Speaker title.
            event_name: Optional event name.
            count: Number of quote cards to generate.
            target_language: ISO language code for the generated quotes.

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

        template = _jinja_env.get_template("quote_card.j2")
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


quote_card_agent = QuoteCardAgent()
