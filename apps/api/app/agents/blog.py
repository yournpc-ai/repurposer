"""Blog Agent: generate a blog post from source texts."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.base import _find_derivative_plan
from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import BlogPost, ContentPlan, GenerationContext

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_TEXT = 150_000


class BlogAgent:
    """Agent that generates a blog post from source texts."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
    ) -> BlogPost:
        """Generate a title + markdown blog post in the target language."""
        if not asset_texts:
            raise MiniMaxError("No source texts provided for blog generation")

        trimmed_texts = [
            t[:_MAX_CHARS_PER_TEXT] for t in asset_texts if t and t.strip()
        ]
        if not trimmed_texts:
            raise MiniMaxError("No usable text found in source texts")

        derivative_plan = _find_derivative_plan(content_plan, "blog")

        template = _jinja_env.get_template("blog.j2")
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
                    "You are a professional blog writer. You only output valid JSON, with no additional explanations."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info("blog_generation_started")
        try:
            result = await self.client.generate(
                messages=messages,
                response_model=BlogPost,
                temperature=0.6,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("blog_generation_failed", error=str(e))
            raise MiniMaxError(f"Blog generation failed: {e}") from e

        logger.info("blog_generation_completed")
        return result


blog_agent = BlogAgent()
