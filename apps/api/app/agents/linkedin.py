"""LinkedIn Agent: generate LinkedIn posts from project materials."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.base import _find_derivative_plan
from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import ContentPlan, GenerationContext, LinkedInPost

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_MATERIAL = 150_000


class LinkedInAgent:
    """Agent that generates LinkedIn posts from speech materials."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def generate(
        self,
        materials: list[str],
        context: GenerationContext,
        content_plan: ContentPlan,
    ) -> LinkedInPost:
        """Generate a LinkedIn post.

        Args:
            materials: Extracted text from project assets.
            context: Shared generation context.
            content_plan: Unified content plan.

        Returns:
            LinkedInPost model.
        """
        if not materials:
            raise MiniMaxError("No materials provided for LinkedIn generation")

        trimmed_materials = [
            m[:_MAX_CHARS_PER_MATERIAL] for m in materials if m and m.strip()
        ]
        if not trimmed_materials:
            raise MiniMaxError("No usable text found in materials")

        derivative_plan = _find_derivative_plan(
            content_plan, "linkedin_post"
        )

        template = _jinja_env.get_template("linkedin.j2")
        user_prompt = template.render(
            materials=trimmed_materials,
            context=context.model_dump(),
            content_plan=content_plan.model_dump(),
            derivative_plan=derivative_plan,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional LinkedIn content strategist. "
                    "You only output valid JSON without any additional explanation."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        logger.info("linkedin_generation_started")

        try:
            post = await self.client.generate(
                messages=messages,
                response_model=LinkedInPost,
                temperature=0.5,
            )
        except MiniMaxError:
            raise
        except Exception as e:
            logger.error("linkedin_generation_failed", error=str(e))
            raise MiniMaxError(f"LinkedIn generation failed: {e}") from e

        logger.info("linkedin_generation_completed", hashtags=len(post.hashtags))
        return post


linkedin_agent = LinkedInAgent()
