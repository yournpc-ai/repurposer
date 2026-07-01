"""Multimodal Content Planner: select segments and write clip scripts in one call.

This agent replaces the previous two-step analyzer + script pipeline. MiniMax-M3
is natively multimodal, so we feed it the original media (short videos, slide
images, photos) alongside extracted text and let it both pick the best moments
and write the hook/script for each clip.
"""

from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import ClipPlans, MediaInput

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_MATERIAL = 150_000


class ContentPlannerAgent:
    """Agent that plans clips directly from multimodal source materials."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def plan(
        self,
        materials: list[str],
        clip_count: int,
        media_inputs: list[MediaInput] | None = None,
        event_name: str | None = None,
        target_language: str = "en",
        instruction: str | None = None,
        persona: dict[str, Any] | None = None,
        tone_settings: dict[str, Any] | None = None,
    ) -> ClipPlans:
        """Plan clips from text materials and/or raw media.

        Args:
            materials: Extracted text / transcripts from project assets.
            clip_count: Number of clips to plan.
            media_inputs: Optional images/videos/short audio snippets.
            event_name: Optional event name for context.
            target_language: ISO language code for all output text.
            instruction: Optional user steering prompt.
            persona: Optional speaker persona dict for style matching.
            tone_settings: Optional tone override dict.

        Returns:
            ClipPlans containing analysis and a list of ClipPlan objects.
        """
        if not materials and not media_inputs:
            raise MiniMaxError("No materials or media provided for planning")

        media_inputs = media_inputs or []
        trimmed_materials = [
            m[:_MAX_CHARS_PER_MATERIAL] for m in materials if m and m.strip()
        ]
        if not trimmed_materials and not media_inputs:
            raise MiniMaxError("No usable text or media found")

        template = _jinja_env.get_template("planner.j2")
        user_prompt = template.render(
            materials=trimmed_materials,
            media_inputs=media_inputs,
            clip_count=clip_count,
            event_name=event_name,
            target_language=target_language,
            instruction=(instruction or "").strip() or None,
            persona=persona,
            tone_settings=tone_settings,
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
            target_language=target_language,
        )

        try:
            plans = await self._plan_with_fallback(messages, user_prompt, media_inputs)
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

    def _build_user_message(
        self, user_prompt: str, media_inputs: list[MediaInput]
    ) -> dict[str, Any]:
        """Build a user message mixing text prompt and media content parts."""
        content: list[dict[str, Any]] = []
        for media in media_inputs:
            part_key = f"{media.type}_url"
            content.append({"type": part_key, part_key: {"url": media.data_url}})
            if media.caption:
                content.append({"type": "text", "text": media.caption})
        content.append({"type": "text", "text": user_prompt})
        return {"role": "user", "content": content}

    async def _plan_with_fallback(
        self,
        messages: list[dict[str, Any]],
        user_prompt: str,
        media_inputs: list[MediaInput],
    ) -> ClipPlans:
        """Call M3; if multimodal input is rejected, retry with text only."""
        try:
            return await self.client.generate(
                messages=messages,
                response_model=ClipPlans,
                temperature=0.4,
            )
        except Exception as first_error:  # noqa: BLE001
            if not media_inputs:
                raise
            logger.warning(
                "multimodal_planning_failed_falling_back_to_text",
                error=str(first_error),
                media_count=len(media_inputs),
            )
            text_only_messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": (
                        "You are a senior content strategist and short-form video "
                        "director. You output valid JSON only, with no extra commentary."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ]
            return await self.client.generate(
                messages=text_only_messages,
                response_model=ClipPlans,
                temperature=0.4,
            )


planner_agent = ContentPlannerAgent()
