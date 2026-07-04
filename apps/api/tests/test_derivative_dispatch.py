"""Tests for derivative_dispatch dispatcher."""

from unittest.mock import AsyncMock

import pytest

from app.models.schemas import ContentPlan, DerivativePlan, DerivativeType, GenerationContext
from app.services.derivative_dispatch import _AGENTS, generate_derivative


def _model_dump(self):
    return {"type": "mocked"}


@pytest.fixture
def mock_agents(monkeypatch):
    """Replace all derivative agents with deterministic mocks."""
    mocks = {}
    for derivative_type in _AGENTS:
        mock = AsyncMock()
        mock.generate.return_value = type("Result", (), {"model_dump": _model_dump})()
        monkeypatch.setitem(_AGENTS, derivative_type, mock)
        mocks[derivative_type] = mock
    return mocks


def _make_context() -> GenerationContext:
    return GenerationContext(target_language="en")


def _make_plan(derivative_type: DerivativeType) -> ContentPlan:
    return ContentPlan(
        core_thesis="Test thesis",
        derivatives=[DerivativePlan(derivative_type=derivative_type)]
    )


async def test_generate_derivative_dispatches_linkedin(mock_agents):
    context = _make_context()
    plan = _make_plan(DerivativeType.LINKEDIN_POST)

    content = await generate_derivative(
        derivative_type=DerivativeType.LINKEDIN_POST,
        materials=["material"],
        context=context,
        content_plan=plan,
    )

    assert content == {"type": "mocked"}
    mock_agents[DerivativeType.LINKEDIN_POST].generate.assert_awaited_once_with(
        materials=["material"],
        context=context,
        content_plan=plan,
    )


async def test_generate_derivative_dispatches_quote_card(mock_agents):
    context = _make_context()
    plan = _make_plan(DerivativeType.QUOTE_CARD)

    content = await generate_derivative(
        derivative_type=DerivativeType.QUOTE_CARD,
        materials=["material"],
        context=context,
        content_plan=plan,
    )

    assert content == {"type": "mocked"}
    mock_agents[DerivativeType.QUOTE_CARD].generate.assert_awaited_once_with(
        materials=["material"],
        context=context,
        content_plan=plan,
    )


async def test_generate_derivative_dispatches_carousel(mock_agents):
    context = _make_context()
    plan = _make_plan(DerivativeType.CAROUSEL)

    content = await generate_derivative(
        derivative_type=DerivativeType.CAROUSEL,
        materials=["material"],
        context=context,
        content_plan=plan,
    )

    assert content == {"type": "mocked"}
    mock_agents[DerivativeType.CAROUSEL].generate.assert_awaited_once_with(
        materials=["material"],
        context=context,
        content_plan=plan,
    )


async def test_generate_derivative_rejects_unknown_type():
    context = _make_context()
    plan = ContentPlan(core_thesis="Test thesis")

    with pytest.raises(ValueError, match="Unsupported derivative type"):
        await generate_derivative(
            derivative_type=DerivativeType.MULTILINGUAL_SCRIPT,
            materials=["material"],
            context=context,
            content_plan=plan,
        )
