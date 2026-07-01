"""Persona Agent: generate speaker style persona from materials."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import SpeakerPersona

logger = structlog.get_logger()

# Load templates from app/prompts directory
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

# Maximum characters to send per material to stay well within 1M context
_MAX_CHARS_PER_MATERIAL = 150_000


class PersonaAgent:
    """Agent that analyzes speaker materials and produces a SpeakerPersona."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        speaker_name: str,
        speaker_title: str | None,
        language: str,
        materials: list[str],
    ) -> SpeakerPersona:
        """Generate a speaker persona from raw text materials.

        Args:
            speaker_name: Speaker name.
            speaker_title: Speaker title/role.
            language: Primary language (zh, en, etc.).
            materials: List of extracted text from past materials.

        Returns:
            SpeakerPersona model.
        """
        if not materials:
            raise MiniMaxError("No materials provided for persona generation")

        # Truncate each material to avoid blowing context
        trimmed_materials = [
            m[:_MAX_CHARS_PER_MATERIAL] for m in materials if m and m.strip()
        ]

        template = _jinja_env.get_template("persona.j2")
        user_prompt = template.render(
            speaker_name=speaker_name,
            speaker_title=speaker_title,
            language=language,
            materials=trimmed_materials,
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
            "persona_generation_started",
            speaker_name=speaker_name,
            material_count=len(trimmed_materials),
            total_chars=sum(len(m) for m in trimmed_materials),
        )

        try:
            persona = await self.client.generate(
                messages=messages,
                response_model=SpeakerPersona,
                temperature=0.3,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("persona_generation_failed", error=str(e))
            raise MiniMaxError(f"Persona generation failed: {e}") from e

        logger.info(
            "persona_generation_completed",
            speaker_name=speaker_name,
            emotional_tone=persona.emotional_tone,
        )
        return persona


persona_agent = PersonaAgent()
