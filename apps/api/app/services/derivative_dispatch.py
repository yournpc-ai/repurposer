"""Thin derivative agent dispatcher.

Maps a ``DerivativeType`` to its executor agent and forwards a shared
``GenerationContext`` + ``ContentPlan``. All agent-specific parameter handling
lives in the agents themselves; this module only provides the registry and a
uniform call site.
"""

from app.agents.blog import blog_agent
from app.agents.carousel import carousel_agent
from app.agents.linkedin import linkedin_agent
from app.agents.quote_agent import quote_agent
from app.agents.summary import summary_agent
from app.models.schemas import ContentPlan, DerivativeType, GenerationContext, validate_derivative_content

_AGENTS = {
    DerivativeType.LINKEDIN_POST: linkedin_agent,
    DerivativeType.QUOTE_CARD: quote_agent,
    DerivativeType.CAROUSEL: carousel_agent,
    DerivativeType.SUMMARY: summary_agent,
    DerivativeType.BLOG: blog_agent,
}


async def generate_derivative(
    derivative_type: DerivativeType,
    materials: list[str],
    context: GenerationContext,
    content_plan: ContentPlan,
) -> dict:
    """Generate a single derivative by dispatching to the appropriate agent.

    Args:
        derivative_type: The type of derivative to generate.
        materials: Extracted text from project assets.
        context: Shared generation context.
        content_plan: Unified content plan from the Content Director.

    Returns:
        The agent's generated content as a plain dict. Callers are responsible
        for persisting it.
    """
    agent = _AGENTS.get(derivative_type)
    if agent is None:
        raise ValueError(f"Unsupported derivative type: {derivative_type}")

    result = await agent.generate(
        materials=materials,
        context=context,
        content_plan=content_plan,
    )
    return validate_derivative_content(derivative_type, result.model_dump())
