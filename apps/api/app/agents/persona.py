"""Persona Agent: generate speaker style and content memory from source texts."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field

from app.clients.minimax import MiniMaxClient, MiniMaxError

logger = structlog.get_logger()

# Load templates from app/prompts directory
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

# Maximum characters to send per text to stay well within 1M context
_MAX_CHARS_PER_TEXT = 150_000


class _ExtractedSpeakerMemory(BaseModel):
    """Internal extraction result; maps directly to Speaker DB columns."""

    core_values: list[str] = Field(default_factory=list)
    favorite_metaphors: list[str] = Field(default_factory=list)
    sentence_style: str = ""
    emotional_tone: str = "rational"
    typical_hooks: list[str] = Field(default_factory=list)
    avoid_words: list[str] = Field(default_factory=list)
    voice: str | None = None
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None


class PersonaAgent:
    """Agent that analyzes source texts and produces extracted memory."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        speaker_name: str,
        speaker_title: str | None,
        language: str,
        asset_texts: list[str],
    ) -> _ExtractedSpeakerMemory:
        """Generate speaker style and content memory from extracted asset texts.

        Args:
            speaker_name: Speaker name.
            speaker_title: Speaker title/role.
            language: Primary language (zh, en, etc.).
            asset_texts: List of extracted text from project assets.

        Returns:
            Extracted memory mapped to Speaker DB columns.
        """
        if not asset_texts:
            raise MiniMaxError("No source texts provided for persona generation")

        # Truncate each text to avoid blowing context
        trimmed_texts = [
            t[:_MAX_CHARS_PER_TEXT] for t in asset_texts if t and t.strip()
        ]

        template = _jinja_env.get_template("persona.j2")
        user_prompt = template.render(
            speaker_name=speaker_name,
            speaker_title=speaker_title,
            language=language,
            asset_texts=trimmed_texts,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional speaking-style analyst."
                    "You only output valid JSON, with no additional commentary."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "speaker_extraction_started",
            speaker_name=speaker_name,
            text_count=len(trimmed_texts),
            total_chars=sum(len(t) for t in trimmed_texts),
        )

        try:
            memory = await self.client.generate(
                messages=messages,
                response_model=_ExtractedSpeakerMemory,
                temperature=0.3,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("speaker_extraction_failed", error=str(e))
            raise MiniMaxError(f"Speaker extraction failed: {e}") from e

        logger.info(
            "speaker_extraction_completed",
            speaker_name=speaker_name,
            emotional_tone=memory.emotional_tone,
        )
        return memory


persona_agent = PersonaAgent()
