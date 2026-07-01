"""Analyzer Agent: extract high-potential segments from project materials."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import ContentAnalysis

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_MATERIAL = 150_000


class AnalyzerAgent:
    """Agent that analyzes speech materials and extracts viral segments."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def analyze(
        self,
        materials: list[str],
        clip_count: int,
        event_name: str | None = None,
        target_language: str = "en",
        instruction: str | None = None,
    ) -> ContentAnalysis:
        """Analyze materials and return high-potential segments.

        Args:
            materials: Extracted text from project assets.
            clip_count: Number of segments to extract.
            event_name: Optional event name for context.
            target_language: ISO language code for segment content (e.g. en/zh/fr).
            instruction: Optional user steering prompt (what to focus on / produce).

        Returns:
            ContentAnalysis model.
        """
        if not materials:
            raise MiniMaxError("No materials provided for analysis")

        trimmed_materials = [
            m[:_MAX_CHARS_PER_MATERIAL] for m in materials if m and m.strip()
        ]
        if not trimmed_materials:
            raise MiniMaxError("No usable text found in materials")

        template = _jinja_env.get_template("analyzer.j2")
        user_prompt = template.render(
            materials=trimmed_materials,
            clip_count=clip_count,
            event_name=event_name,
            target_language=target_language,
            instruction=(instruction or "").strip() or None,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior content strategy analyst."
                    "You only output valid JSON, with no additional explanations."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "content_analysis_started",
            material_count=len(trimmed_materials),
            clip_count=clip_count,
            target_language=target_language,
        )

        try:
            analysis = await self.client.generate(
                messages=messages,
                response_model=ContentAnalysis,
                temperature=0.3,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("content_analysis_failed", error=str(e))
            raise MiniMaxError(f"Content analysis failed: {e}") from e

        logger.info(
            "content_analysis_completed",
            segment_count=len(analysis.segments),
            top_score=max((s.virality_score for s in analysis.segments), default=0),
        )
        return analysis


analyzer_agent = AnalyzerAgent()
