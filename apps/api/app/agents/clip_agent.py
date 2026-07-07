"""Clip Agent: select segments and write clip scripts from a content plan.

This agent replaces the previous ContentPlannerAgent. It receives the shared
GenerationContext and ContentPlan produced by the Content Director, then plans
vertical clips that reinforce the same core thesis and brand strategy.
"""

from typing import Any

import structlog

from app.agents.base import MiniMaxAgentBase
from app.clients.minimax import MiniMaxError
from app.models.schemas import ClipPlans, ContentPlan, GenerationContext, MediaInput

logger = structlog.get_logger()


class ClipAgent(MiniMaxAgentBase):
    """Agent that plans clips from a content plan and source materials."""

    async def generate(
        self,
        materials: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
        media_inputs: list[MediaInput] | None = None,
        clip_count: int = 3,
        source_words: list[dict[str, Any]] | None = None,
        music_pieces: list[dict[str, str]] | None = None,
    ) -> ClipPlans:
        """Plan clips from text materials and/or raw media.

        Args:
            materials: Extracted text / transcripts from project assets.
            context: Shared generation context (speaker, brand, tone, language).
            content_plan: Unified content plan from the Content Director.
            media_inputs: Optional images/videos/short audio snippets.
            clip_count: Number of clips to plan.
            source_words: Optional ASR word-level timestamps for the primary source
                so the agent can output exact ``start_seconds`` / ``end_seconds``.
            music_pieces: Available music library pieces (``id``/``mood``/
                ``title``/``description``) the agent selects from per clip.

        Returns:
            ClipPlans containing analysis and a list of ClipPlan objects.
        """
        if not materials and not media_inputs:
            raise MiniMaxError("No materials or media provided for clip planning")

        media_inputs = media_inputs or []
        trimmed_materials = self._trim_materials(materials)
        if not trimmed_materials and not media_inputs:
            raise MiniMaxError("No usable text or media found")

        user_prompt = self.jinja_env.get_template("clip_agent.j2").render(
            materials=trimmed_materials,
            media_inputs=media_inputs,
            clip_count=clip_count,
            context=context.model_dump(),
            content_plan=content_plan.model_dump(),
            source_words=source_words or [],
            music_pieces=music_pieces or [],
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a senior content strategist and short-form video "
                    "director. You output valid JSON only, with no extra commentary."
                ),
            },
            self._build_user_message(user_prompt, media_inputs),
        ]

        logger.info(
            "clip_planning_started",
            material_count=len(trimmed_materials),
            media_count=len(media_inputs),
            clip_count=clip_count,
            target_language=context.target_language,
        )

        try:
            plans = await self._generate_with_fallback(
                messages=messages,
                user_prompt=user_prompt,
                media_inputs=media_inputs,
                response_model=ClipPlans,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("clip_planning_failed", error=str(e))
            raise MiniMaxError(f"Clip planning failed: {e}") from e

        logger.info(
            "clip_planning_completed",
            clip_count=len(plans.clips),
            top_score=max((c.virality_score for c in plans.clips), default=0),
        )
        return plans


clip_agent = ClipAgent()
