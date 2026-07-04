"""Content Director: produces a unified ContentPlan from source materials.

The director performs a single analysis pass over the project's materials and
media inputs, then emits a ContentPlan that all downstream agent executors
share. This guarantees that clips, LinkedIn posts, quote cards, carousels,
summaries, and blog posts reinforce the same core thesis and brand strategy.
"""

from typing import Any

import structlog

from app.agents.base import MiniMaxAgentBase
from app.clients.minimax import MiniMaxError
from app.models.schemas import (
    ContentPlan,
    DerivativeType,
    GenerationContext,
    MediaInput,
)

logger = structlog.get_logger()


class ContentDirectorAgent(MiniMaxAgentBase):
    """Agent that produces a unified content plan from source materials."""

    async def plan(
        self,
        materials: list[str],
        context: GenerationContext,
        media_inputs: list[MediaInput] | None = None,
        requested_derivatives: list[DerivativeType] | None = None,
    ) -> ContentPlan:
        """Generate a ContentPlan from materials and generation context.

        Args:
            materials: Extracted text / transcripts from project assets.
            context: Shared generation context (speaker, brand, tone, language).
            media_inputs: Optional images/videos/short audio snippets.
            requested_derivatives: Derivative types the user asked for.

        Returns:
            ContentPlan containing core thesis, themes, audience, and per-output
            derivative plans.
        """
        if not materials and not media_inputs:
            raise MiniMaxError("No materials or media provided for content planning")

        media_inputs = media_inputs or []
        requested_derivatives = requested_derivatives or []
        trimmed_materials = self._trim_materials(materials)
        if not trimmed_materials and not media_inputs:
            raise MiniMaxError("No usable text or media found")

        user_prompt = self.jinja_env.get_template("content_director.j2").render(
            materials=trimmed_materials,
            media_inputs=media_inputs,
            context=context.model_dump(),
            requested_derivatives=[d.value for d in requested_derivatives],
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a senior content strategist. You analyze source "
                    "materials and output a single coherent content plan as valid "
                    "JSON, with no extra commentary."
                ),
            },
            self._build_user_message(user_prompt, media_inputs),
        ]

        logger.info(
            "content_director_started",
            material_count=len(trimmed_materials),
            media_count=len(media_inputs),
            derivative_count=len(requested_derivatives),
            target_language=context.target_language,
        )

        try:
            plan = await self._generate_with_fallback(
                messages=messages,
                user_prompt=user_prompt,
                media_inputs=media_inputs,
                response_model=ContentPlan,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("content_director_failed", error=str(e))
            raise MiniMaxError(f"Content director failed: {e}") from e

        logger.info(
            "content_director_completed",
            core_thesis=plan.core_thesis,
            theme_count=len(plan.themes),
            derivative_count=len(plan.derivatives),
        )
        return plan


content_director_agent = ContentDirectorAgent()
