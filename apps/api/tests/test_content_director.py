"""Tests for the Content Director agent."""

from unittest.mock import AsyncMock

import pytest

from app.agents.content_director import ContentDirectorAgent
from app.models.schemas import (
    ContentPlan,
    DerivativePlan,
    DerivativeType,
    GenerationContext,
)


@pytest.fixture
def director_client():
    """Return a ContentDirectorAgent with a mocked MiniMax client."""
    client = AsyncMock()
    agent = ContentDirectorAgent(client=client)
    return agent, client


def _make_context() -> GenerationContext:
    return GenerationContext(
        speaker_name="Ada",
        speaker_title="Dr.",
        event_name="Test Event",
        target_language="en",
        instruction="focus on ethics",
    )


async def test_director_returns_content_plan(director_client):
    agent, client = director_client
    client.generate.return_value = ContentPlan(
        core_thesis="AI needs guardrails",
        themes=["ethics", "regulation"],
        target_audience="policymakers",
        derivatives=[
            DerivativePlan(derivative_type=DerivativeType.LINKEDIN_POST)
        ],
    )

    plan = await agent.plan(
        materials=["material"],
        context=_make_context(),
        requested_derivatives=[DerivativeType.LINKEDIN_POST],
    )

    assert plan.core_thesis == "AI needs guardrails"
    assert plan.themes == ["ethics", "regulation"]
    assert len(plan.derivatives) == 1
    assert plan.derivatives[0].derivative_type == DerivativeType.LINKEDIN_POST

    call = client.generate.call_args
    assert call.kwargs["response_model"] == ContentPlan
    assert call.kwargs["temperature"] == 0.4


async def test_director_requires_materials_or_media(director_client):
    agent, _client = director_client

    with pytest.raises(Exception):  # MiniMaxError
        await agent.plan(
            materials=[],
            context=_make_context(),
            media_inputs=[],
            requested_derivatives=[],
        )


async def test_director_falls_back_to_text_on_multimodal_failure(director_client):
    agent, client = director_client
    client.generate.side_effect = [
        ValueError("multimodal rejected"),
        ContentPlan(
            core_thesis="fallback",
            derivatives=[
                DerivativePlan(derivative_type=DerivativeType.QUOTE_CARD)
            ],
        ),
    ]

    from app.models.schemas import MediaInput, MediaInputType

    media = MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/png",
        data_url="data:image/png;base64,abc",
        caption="slide",
    )

    await agent.plan(
        materials=["material"],
        context=_make_context(),
        media_inputs=[media],
        requested_derivatives=[DerivativeType.QUOTE_CARD],
    )

async def test_director_falls_back_to_text_on_any_media_failure(director_client):
    """Any failure with media inputs should fall back to text-only, not just
    errors that mention multimodal keywords. This protects against provider-side
    crashes like 'tuple index out of range' when sending video data URLs."""
    agent, client = director_client
    client.generate.side_effect = [
        IndexError("tuple index out of range"),
        ContentPlan(
            core_thesis="fallback_from_tuple_error",
            derivatives=[
                DerivativePlan(derivative_type=DerivativeType.QUOTE_CARD)
            ],
        ),
    ]

    from app.models.schemas import MediaInput, MediaInputType

    media = MediaInput(
        type=MediaInputType.VIDEO,
        mime="video/mp4",
        data_url="data:video/mp4;base64,abc",
        caption="talk",
    )

    plan = await agent.plan(
        materials=["material"],
        context=_make_context(),
        media_inputs=[media],
        requested_derivatives=[DerivativeType.QUOTE_CARD],
    )

    assert plan.core_thesis == "fallback_from_tuple_error"
    assert client.generate.await_count == 2
