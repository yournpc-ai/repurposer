"""Caption Translate Agent: translate subtitle lines into a target language.

Line-by-line translation that preserves count and order, so the caller can map
each translated line back onto the original line's source-time span.
"""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import CaptionTranslation

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)


class CaptionTranslateAgent:
    """Agent that translates an ordered list of caption lines."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def translate(self, lines: list[str], target_language: str) -> list[str]:
        """Translate ``lines`` into ``target_language``, preserving count & order.

        Returns a list the same length as ``lines``. If the model returns a
        mismatched count, it is padded/truncated so the caller's 1:1 timing
        mapping stays valid (never raises on length drift).
        """
        if not lines:
            return []

        template = _jinja_env.get_template("caption_translate.j2")
        user_prompt = template.render(lines=lines, target_language=target_language)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional subtitle translator. You only output valid JSON, with no additional explanation."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "caption_translation_started",
            lines=len(lines),
            target_language=target_language,
        )
        try:
            result = await self.client.generate(
                messages=messages,
                response_model=CaptionTranslation,
                temperature=0.3,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("caption_translation_failed", error=str(e))
            raise MiniMaxError(f"Caption translation failed: {e}") from e

        out = list(result.lines)
        if len(out) != len(lines):
            logger.warning(
                "caption_translation_count_mismatch",
                expected=len(lines),
                got=len(out),
            )
            if len(out) < len(lines):
                out += lines[len(out):]  # fall back to source text for missing lines
            else:
                out = out[: len(lines)]
        return out


caption_translate_agent = CaptionTranslateAgent()
