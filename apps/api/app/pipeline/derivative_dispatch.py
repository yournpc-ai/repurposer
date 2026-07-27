"""Thin derivative agent dispatcher.

Maps a ``DerivativeType`` to its executor agent and forwards a shared
``GenerationContext`` + ``MaterialUnderstanding`` + ``Storyboard``. All
agent-specific parameter handling lives in the agents themselves; this module
only provides the registry and a uniform call site.
"""

from app.skills.article import article_agent
from app.skills.carousel import carousel_agent
from app.skills.post import post_agent
from app.skills.quotes import quotes_agent
from app.models.schemas import (
    DerivativeType,
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
    validate_derivative_content,
)

_AGENTS = {
    DerivativeType.POST: post_agent,
    DerivativeType.QUOTES: quotes_agent,
    DerivativeType.CAROUSEL: carousel_agent,
    DerivativeType.ARTICLE: article_agent,
}


async def generate_derivative(
    derivative_type: DerivativeType,
    asset_texts: list[str],
    context: GenerationContext,
    understanding: MaterialUnderstanding,
    storyboard: Storyboard,
) -> dict:
    """Generate a single derivative by dispatching to the appropriate agent.

    Args:
        derivative_type: The type of derivative to generate.
        asset_texts: Extracted text from project assets.
        context: Shared generation context.
        understanding: Material understanding from director step 1.
        storyboard: Storyboard from director step 2 (this output's slot).

    Returns:
        The agent's generated content as a plain dict. Callers are responsible
        for persisting it.
    """
    agent = _AGENTS.get(derivative_type)
    if agent is None:
        raise ValueError(f"Unsupported derivative type: {derivative_type}")

    result = await agent.generate(
        asset_texts=asset_texts,
        context=context,
        understanding=understanding,
        storyboard=storyboard,
    )
    return validate_derivative_content(derivative_type, result.model_dump())
