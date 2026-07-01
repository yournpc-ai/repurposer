"""Script Agent: generate clip scripts from analyzed segments and persona."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import ClipScript, Segment, SpeakerPersona, ToneSettings

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)


class ScriptAgent:
    """Agent that turns analyzed segments into clip scripts."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        segment: Segment,
        persona: SpeakerPersona | None,
        tone_settings: ToneSettings | None,
        target_audience: str,
        target_language: str = "en",
        instruction: str | None = None,
    ) -> ClipScript:
        """Generate a clip script for a segment.

        Args:
            segment: Analyzed segment from AnalyzerAgent.
            persona: Speaker style persona.
            tone_settings: Optional tone overrides.
            target_audience: Target audience description.
            target_language: ISO language code for hook/subtitles (e.g. en/zh/fr).
            instruction: Optional user steering prompt (hook angle / emphasis).

        Returns:
            ClipScript model.
        """
        tone = tone_settings or ToneSettings()

        template = _jinja_env.get_template("script.j2")
        user_prompt = template.render(
            segment=segment,
            persona=persona,
            target_audience=target_audience,
            target_language=target_language,
            duration_seconds=segment.duration_seconds,
            academic_vs_casual=tone.academic_vs_casual,
            rational_vs_passionate=tone.rational_vs_passionate,
            concise_vs_detailed=tone.concise_vs_detailed,
            instruction=(instruction or "").strip() or None,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a top-tier short-form video script strategist."
                    "You only output valid JSON, with no additional commentary."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "script_generation_started",
            segment_id=segment.id,
            duration=segment.duration_seconds,
        )

        try:
            script = await self.client.generate(
                messages=messages,
                response_model=ClipScript,
                temperature=0.5,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("script_generation_failed", error=str(e))
            raise MiniMaxError(f"Script generation failed: {e}") from e

        # Inherit virality score from segment if model omitted it
        if script.virality_score is None:
            script.virality_score = segment.virality_score

        logger.info(
            "script_generation_completed",
            segment_id=segment.id,
            hook=script.hook,
            virality_score=script.virality_score,
        )
        return script


script_agent = ScriptAgent()
