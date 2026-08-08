"""Content Director: two-step planning (RunPlan Phase 2).

Step 1 ``understand`` reads the source material (texts + media) and produces a
material-scoped ``MaterialUnderstanding`` — pure of persona/tone/instruction/
language so it stays reusable across runs (asset-hash invalidation lives in
the ``director_understand`` node runner).

Step 2 ``plan`` reads ONLY the understanding plus the task book and produces a
request-scoped ``Storyboard`` (self-sufficiency contract: it never sees the
raw sources — the understanding must be enough).
"""

from typing import Any

import structlog

from app.skills.base import MiniMaxAgentBase
from app.clients.minimax import MiniMaxError
from app.models.schemas import (
    GenerationContext,
    MaterialUnderstanding,
    MediaInput,
    Storyboard,
)

logger = structlog.get_logger()


class ContentDirectorAgent(MiniMaxAgentBase):
    """Two-step director: material understanding → storyboard."""

    async def understand(
        self,
        asset_texts: list[str],
        asset_media: list[MediaInput] | None = None,
    ) -> MaterialUnderstanding:
        """Produce the material-scoped understanding from source texts/media.

        Deliberately takes no GenerationContext: persona, tone, instruction,
        and target language would all poison reuse (they change per request;
        the understanding changes only with the material).
        """
        if not asset_texts and not asset_media:
            raise MiniMaxError("No source texts or media provided for understanding")

        asset_media = asset_media or []
        trimmed_texts = self._trim_texts(asset_texts)
        if not trimmed_texts and not asset_media:
            raise MiniMaxError("No usable text or media found")

        user_prompt = self.jinja_env.get_template("director_understand.j2").render(
            asset_texts=trimmed_texts,
            asset_media=asset_media,
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a senior content strategist. You analyze source "
                    "material and output a faithful, self-contained material "
                    "understanding as valid JSON, with no extra commentary."
                ),
            },
            self._build_user_message(user_prompt, asset_media),
        ]

        logger.info(
            "director_understand_started",
            text_count=len(trimmed_texts),
            media_count=len(asset_media),
        )

        try:
            understanding = await self._generate_with_fallback(
                messages=messages,
                user_prompt=user_prompt,
                media_inputs=asset_media,
                response_model=MaterialUnderstanding,
                temperature=0.3,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("director_understand_failed", error=str(e))
            raise MiniMaxError(f"Director understand failed: {e}") from e

        logger.info(
            "director_understand_completed",
            core_thesis=understanding.core_thesis,
            argument_count=len(understanding.key_arguments),
            quote_count=len(understanding.quote_candidates),
        )
        return understanding

    async def plan(
        self,
        understanding: MaterialUnderstanding,
        context: GenerationContext,
        task_book: dict[str, Any],
    ) -> Storyboard:
        """Produce the request-scoped storyboard from the understanding.

        Self-sufficiency contract: this call never sees the raw sources —
        only the understanding, the shared context (persona/tone/language/
        instruction), and the task book (the requested IntentSlots).
        """
        user_prompt = self.jinja_env.get_template("director_plan.j2").render(
            understanding=understanding.model_dump(),
            context=context.model_dump(),
            task_book=task_book,
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a senior content strategist. You assign content "
                    "work from a material understanding and output a storyboard "
                    "as valid JSON, with no extra commentary."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "director_plan_started",
            slots=len(task_book.get("slots", [])),
            target_language=context.target_language,
        )

        try:
            storyboard = await self.client.generate(
                messages=messages,
                response_model=Storyboard,
                temperature=0.4,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("director_plan_failed", error=str(e))
            raise MiniMaxError(f"Director plan failed: {e}") from e

        logger.info(
            "director_plan_completed",
            slot_count=len(storyboard.slots),
        )
        return storyboard


content_director_agent = ContentDirectorAgent()
