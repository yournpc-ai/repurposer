"""Persona Agent: generate persona style and content memory from source texts."""

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


class _ExtractedPersonaMemory(BaseModel):
    """Internal extraction result; maps directly to Persona DB columns."""

    # LLM-synthesized persona label (e.g. "Pragmatic AI evangelist") — used as
    # the Persona.name when the pipeline auto-creates a persona, so the row is
    # never named after an uploaded file. Ignored on manual regenerate, where
    # the user owns the name.
    name: str = ""
    core_values: list[str] = Field(default_factory=list)
    favorite_metaphors: list[str] = Field(default_factory=list)
    sentence_style: str = ""
    emotional_tone: str = "rational"
    typical_hooks: list[str] = Field(default_factory=list)
    avoid_words: list[str] = Field(default_factory=list)
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None


class PersonaAgent:
    """Agent that analyzes source texts and produces extracted memory."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        persona_name: str,
        persona_title: str | None,
        language: str,
        asset_texts: list[str],
    ) -> _ExtractedPersonaMemory:
        """Generate persona style and content memory from extracted asset texts.

        Args:
            persona_name: Persona name.
            persona_title: Persona title/role.
            language: Primary language (zh, en, etc.).
            asset_texts: List of extracted text from project assets.

        Returns:
            Extracted memory mapped to Persona DB columns.
        """
        if not asset_texts:
            raise MiniMaxError("No source texts provided for persona generation")

        # Truncate each text to avoid blowing context
        trimmed_texts = [
            t[:_MAX_CHARS_PER_TEXT] for t in asset_texts if t and t.strip()
        ]

        template = _jinja_env.get_template("persona.j2")
        user_prompt = template.render(
            persona_name=persona_name,
            persona_title=persona_title,
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
            "persona_extraction_started",
            persona_name=persona_name,
            text_count=len(trimmed_texts),
            total_chars=sum(len(t) for t in trimmed_texts),
        )

        try:
            memory = await self.client.generate(
                messages=messages,
                response_model=_ExtractedPersonaMemory,
                temperature=0.3,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("persona_extraction_failed", error=str(e))
            raise MiniMaxError(f"Persona extraction failed: {e}") from e

        logger.info(
            "persona_extraction_completed",
            persona_name=persona_name,
            emotional_tone=memory.emotional_tone,
        )
        return memory


persona_agent = PersonaAgent()
