"""Article Agent: generate an article / blog post from source texts."""

import structlog

from app.agents.base import MiniMaxAgentBase, _find_derivative_plan
from app.clients.minimax import MiniMaxError
from app.models.schemas import Article, ContentPlan, GenerationContext

logger = structlog.get_logger()


class ArticleAgent(MiniMaxAgentBase):
    """Agent that generates an article / blog post from source texts."""

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
    ) -> Article:
        """Generate a title + markdown article in the target language."""
        if not asset_texts:
            raise MiniMaxError("No source texts provided for article generation")

        trimmed_texts = self._trim_texts(asset_texts)
        if not trimmed_texts:
            raise MiniMaxError("No usable text found in source texts")

        derivative_plan = _find_derivative_plan(content_plan, "article")

        template = self.jinja_env.get_template("article.j2")
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
                    "You are a professional article writer. You only output valid "
                    "JSON, with no additional explanations."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info("article_generation_started")
        try:
            result = await self.client.generate(
                messages=messages,
                response_model=Article,
                temperature=0.6,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("article_generation_failed", error=str(e))
            raise MiniMaxError(f"Article generation failed: {e}") from e

        logger.info("article_generation_completed")
        return result


article_agent = ArticleAgent()
