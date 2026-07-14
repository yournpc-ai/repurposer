"""Post Agent: generate social posts from source texts."""

import structlog

from app.agents.base import MiniMaxAgentBase, _find_derivative_plan
from app.clients.minimax import MiniMaxError
from app.models.schemas import ContentPlan, GenerationContext, Post

logger = structlog.get_logger()


class PostAgent(MiniMaxAgentBase):
    """Agent that generates social posts from source texts."""

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
    ) -> Post:
        """Generate a social post.

        Args:
            asset_texts: Extracted text from project assets.
            context: Shared generation context.
            content_plan: Unified content plan.

        Returns:
            Post model.
        """
        if not asset_texts:
            raise MiniMaxError("No source texts provided for post generation")

        trimmed_texts = self._trim_texts(asset_texts)
        if not trimmed_texts:
            raise MiniMaxError("No usable text found in source texts")

        derivative_plan = _find_derivative_plan(content_plan, "post")

        template = self.jinja_env.get_template("post.j2")
        user_prompt = template.render(
            asset_texts=trimmed_texts,
            context=context.model_dump(),
            content_plan=content_plan.model_dump(),
            derivative_plan=derivative_plan,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional social content strategist. "
                    "You only output valid JSON without any additional explanation."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info("post_generation_started")

        try:
            post = await self.client.generate(
                messages=messages,
                response_model=Post,
                temperature=0.5,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("post_generation_failed", error=str(e))
            raise MiniMaxError(f"Post generation failed: {e}") from e

        logger.info("post_generation_completed", hashtags=len(post.hashtags))
        return post


post_agent = PostAgent()
