"""Clip Agent: select segments and write clip scripts.

This agent replaces the previous ContentPlannerAgent. It receives the shared
GenerationContext, the director's MaterialUnderstanding (step 1), and its
aggregate Storyboard slot (step 2), then plans vertical clips that reinforce
the same core thesis and brand strategy.
"""

from typing import Any

import structlog

from app.skills.base import MiniMaxAgentBase, _find_slot
from app.clients.minimax import MiniMaxError
from app.models.schemas import (
    ClipPlans,
    GenerationContext,
    MaterialUnderstanding,
    MediaInput,
    Storyboard,
)

logger = structlog.get_logger()


class ClipAgent(MiniMaxAgentBase):
    """Agent that plans clips from the understanding and source texts/media."""

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        understanding: MaterialUnderstanding,
        storyboard: Storyboard,
        asset_media: list[MediaInput] | None = None,
        clip_count: int = 3,
        anchored_transcript: str | None = None,
        music_pieces: list[dict[str, str]] | None = None,
    ) -> ClipPlans:
        """Plan clips from source texts and/or raw media.

        Args:
            asset_texts: Extracted text / transcripts from project assets.
            context: Shared generation context (persona, brand, tone, language).
            understanding: Material understanding from director step 1.
            storyboard: Storyboard from director step 2 (aggregate clips slot).
            asset_media: Optional images/videos/short audio snippets from assets.
            clip_count: Number of clips to plan.
            anchored_transcript: Full-talk transcript with ``[start-end]`` line
                anchors (``app.tools.transcript.build_anchored_transcript``) so
                the agent can output exact ``start_seconds`` / ``end_seconds``.
            music_pieces: Available music library pieces (``id``/``mood``/
                ``title``/``description``) the agent selects from per clip.

        Returns:
            ClipPlans containing analysis and a list of ClipPlan objects.
        """
        if not asset_texts and not asset_media:
            raise MiniMaxError("No source texts or media provided for clip planning")

        asset_media = asset_media or []
        trimmed_texts = self._trim_texts(asset_texts)
        if not trimmed_texts and not asset_media:
            raise MiniMaxError("No usable text or media found")

        # Resolve the clips slot's argument ids to their text so the prompt
        # reads as guidance, not cross-references.
        slot = _find_slot(storyboard, "clips")
        if slot.get("argument_ids"):
            arg_text_by_id = {a.id: a.text for a in understanding.key_arguments}
            slot["argument_texts"] = [
                arg_text_by_id[i] for i in slot["argument_ids"] if i in arg_text_by_id
            ]

        user_prompt = self.jinja_env.get_template("clip_agent.j2").render(
            asset_texts=trimmed_texts,
            asset_media=asset_media,
            clip_count=clip_count,
            context=context.model_dump(),
            understanding=understanding.model_dump(),
            slot=slot,
            anchored_transcript=anchored_transcript,
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
            self._build_user_message(user_prompt, asset_media),
        ]

        logger.info(
            "clip_planning_started",
            text_count=len(trimmed_texts),
            media_count=len(asset_media),
            clip_count=clip_count,
            target_language=context.target_language,
        )

        try:
            plans = await self._generate_with_fallback(
                messages=messages,
                user_prompt=user_prompt,
                media_inputs=asset_media,
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
            top_score=max((c.recommendation_score for c in plans.clips), default=0),
        )
        return plans


clip_agent = ClipAgent()
