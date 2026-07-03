"""Unified derivative agent dispatch.

Background generation and derivative regeneration both need to call the same
set of content agents (LinkedIn, quote cards, carousel, summary, blog). This
module provides a single dispatcher so the orchestration code does not repeat
agent-specific parameter handling.
"""

from app.agents.blog import blog_agent
from app.agents.carousel import carousel_agent
from app.agents.linkedin import linkedin_agent
from app.agents.quote_card import quote_card_agent
from app.agents.summary import summary_agent
from app.models.schemas import DerivativeType, SpeakerPersona
from app.models.tables import Project, Speaker

_AGENTS = {
    DerivativeType.LINKEDIN_POST: linkedin_agent,
    DerivativeType.QUOTE_CARD: quote_card_agent,
    DerivativeType.CAROUSEL: carousel_agent,
    DerivativeType.SUMMARY: summary_agent,
    DerivativeType.BLOG: blog_agent,
}


def _build_agent_kwargs(
    derivative_type: DerivativeType,
    speaker: Speaker | None,
    persona: SpeakerPersona | None,
) -> dict:
    """Build agent-specific kwargs from resolved speaker/persona."""
    if derivative_type in (
        DerivativeType.LINKEDIN_POST,
        DerivativeType.SUMMARY,
        DerivativeType.BLOG,
    ):
        return {"persona": persona}

    if derivative_type == DerivativeType.QUOTE_CARD:
        return {
            "speaker_name": speaker.name if speaker is not None else "",
            "speaker_title": speaker.title if speaker is not None else None,
            "count": 3,
        }

    if derivative_type == DerivativeType.CAROUSEL:
        return {
            "speaker_name": speaker.name if speaker is not None else "",
            "speaker_title": speaker.title if speaker is not None else None,
            "count": 6,
        }

    raise ValueError(f"Unsupported derivative type: {derivative_type}")


async def generate_derivative(
    project: Project,
    derivative_type: DerivativeType,
    materials: list[str],
    target_language: str,
    instruction: str | None,
    speaker: Speaker | None,
    persona: SpeakerPersona | None,
) -> dict:
    """Generate a single derivative by dispatching to the appropriate agent.

    Returns the agent's generated content as a plain dict. Callers are
    responsible for persisting it (creating a new :class:`Derivative` or
    updating an existing one).
    """
    agent = _AGENTS.get(derivative_type)
    if agent is None:
        raise ValueError(f"Unsupported derivative type: {derivative_type}")
    kwargs = _build_agent_kwargs(derivative_type, speaker, persona)

    result = await agent.generate(
        materials=materials,
        event_name=project.event_name,
        target_language=target_language,
        instruction=instruction,
        **kwargs,
    )

    return result.model_dump()
