"""Content Director: produces a unified ContentPlan from source texts and media.

The director performs a single analysis pass over the project's source texts and
media inputs, then emits a ContentPlan that all downstream agent executors
share. This guarantees that clips, social posts, quote cards, carousels, and
articles reinforce the same core thesis and brand strategy.
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
    """Agent that produces a unified content plan from source texts and media."""

    async def plan(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        asset_media: list[MediaInput] | None = None,
        requested_derivatives: list[DerivativeType] | None = None,
    ) -> ContentPlan:
        """Generate a ContentPlan from source texts and generation context.

        Args:
            asset_texts: Extracted text / transcripts from project assets.
            context: Shared generation context (speaker, brand, tone, language).
            asset_media: Optional images/videos/short audio snippets from assets.
            requested_derivatives: Derivative types the user asked for.

        Returns:
            ContentPlan containing core thesis, themes, audience, and per-output
            derivative plans.
        """
        if not asset_texts and not asset_media:
            raise MiniMaxError("No source texts or media provided for content planning")

        asset_media = asset_media or []
        requested_derivatives = requested_derivatives or []
        trimmed_texts = self._trim_texts(asset_texts)
        if not trimmed_texts and not asset_media:
            raise MiniMaxError("No usable text or media found")

        user_prompt = self.jinja_env.get_template("content_director.j2").render(
            asset_texts=trimmed_texts,
            asset_media=asset_media,
            context=context.model_dump(),
            requested_derivatives=[d.value for d in requested_derivatives],
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a senior content strategist. You analyze source "
                    "texts and media and output a single coherent content plan as valid "
                    "JSON, with no extra commentary."
                ),
            },
            self._build_user_message(user_prompt, asset_media),
        ]

        logger.info(
            "content_director_started",
            text_count=len(trimmed_texts),
            media_count=len(asset_media),
            derivative_count=len(requested_derivatives),
            target_language=context.target_language,
        )

        try:
            plan = await self._generate_with_fallback(
                messages=messages,
                user_prompt=user_prompt,
                media_inputs=asset_media,
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
