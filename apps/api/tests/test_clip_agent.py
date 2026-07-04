"""Tests for the Clip Agent."""

from unittest.mock import AsyncMock

import pytest

from app.agents.clip_agent import ClipAgent
from app.models.schemas import (
    ClipPlan,
    ClipPlans,
    ContentPlan,
    GenerationContext,
)


@pytest.fixture
def clip_client():
    """Return a ClipAgent with a mocked MiniMax client."""
    client = AsyncMock()
    agent = ClipAgent(client=client)
    return agent, client


def _make_context() -> GenerationContext:
    return GenerationContext(
        speaker_name="Ada",
        target_language="en",
    )


def _make_plan() -> ContentPlan:
    return ContentPlan(core_thesis="AI needs guardrails")


async def test_clip_agent_returns_plans(clip_client):
    agent, client = clip_client
    client.generate.return_value = ClipPlans(
        clips=[
            ClipPlan(
                id="clip_001",
                source_text="AI ethics matters",
                start_marker="start",
                end_marker="end",
                hook="Ethics first",
            )
        ]
    )

    plans = await agent.generate(
        materials=["material"],
        context=_make_context(),
        content_plan=_make_plan(),
        clip_count=1,
    )

    assert len(plans.clips) == 1
    assert plans.clips[0].hook == "Ethics first"

    call = client.generate.call_args
    assert call.kwargs["response_model"] == ClipPlans
    assert call.kwargs["temperature"] == 0.4


async def test_clip_agent_requires_materials_or_media(clip_client):
    agent, _client = clip_client

    with pytest.raises(Exception):  # MiniMaxError
        await agent.generate(
            materials=[],
            context=_make_context(),
            content_plan=_make_plan(),
            media_inputs=[],
            clip_count=1,
        )


async def test_clip_agent_falls_back_to_text_on_multimodal_failure(clip_client):
    agent, client = clip_client
    client.generate.side_effect = [
        ValueError("multimodal rejected"),
        ClipPlans(clips=[ClipPlan(id="clip_001", source_text="fallback", start_marker="start", end_marker="end", hook="Fallback hook")]),
    ]

    from app.models.schemas import MediaInput, MediaInputType

    media = MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/png",
        data_url="data:image/png;base64,abc",
        caption="slide",
    )

    plans = await agent.generate(
        materials=["material"],
        context=_make_context(),
        content_plan=_make_plan(),
        media_inputs=[media],
        clip_count=1,
    )

    assert plans.clips[0].hook == "Fallback hook"
    assert client.generate.await_count == 2
