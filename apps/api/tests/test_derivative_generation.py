"""Tests for derivative_generation dispatcher."""

from unittest.mock import AsyncMock

import pytest

from app.models.schemas import DerivativeType, SpeakerPersona
from app.models.tables import Project, User
from app.services.derivative_generation import _AGENTS, generate_derivative


async def _make_project(db, email="test@example.com", title="Test"):
    user = User(email=email)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    project = Project(user_id=user.id, title=title)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@pytest.fixture
def mock_agents(monkeypatch):
    """Replace all derivative agents with deterministic mocks."""
    mocks = {}
    for derivative_type in _AGENTS:
        mock = AsyncMock()

        def _model_dump(self, dtype=derivative_type):
            return {"type": dtype.value}

        mock.generate.return_value = type("Result", (), {"model_dump": _model_dump})()
        monkeypatch.setitem(_AGENTS, derivative_type, mock)
        mocks[derivative_type] = mock
    return mocks


async def test_generate_derivative_dispatches_linkedin(db, mock_agents):
    project = await _make_project(db)
    persona = SpeakerPersona()

    content = await generate_derivative(
        project=project,
        derivative_type=DerivativeType.LINKEDIN_POST,
        materials=["material"],
        target_language="en",
        instruction=None,
        speaker=None,
        persona=persona,
    )

    assert content == {"type": DerivativeType.LINKEDIN_POST.value}
    mock_agents[DerivativeType.LINKEDIN_POST].generate.assert_awaited_once_with(
        materials=["material"],
        event_name=None,
        target_language="en",
        instruction=None,
        persona=persona,
    )


async def test_generate_derivative_dispatches_quote_card_with_speaker(db, mock_agents):
    from app.models.tables import Speaker

    user = User(email="speaker@example.com")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    speaker = Speaker(user_id=user.id, name="Ada", title="Dr.")
    db.add(speaker)
    await db.commit()
    await db.refresh(speaker)

    project = await _make_project(db, email="proj@example.com", title="Quote Project")

    content = await generate_derivative(
        project=project,
        derivative_type=DerivativeType.QUOTE_CARD,
        materials=["material"],
        target_language="fr",
        instruction="make it punchy",
        speaker=speaker,
        persona=None,
    )

    assert content == {"type": DerivativeType.QUOTE_CARD.value}
    mock_agents[DerivativeType.QUOTE_CARD].generate.assert_awaited_once_with(
        materials=["material"],
        event_name=None,
        target_language="fr",
        instruction="make it punchy",
        speaker_name="Ada",
        speaker_title="Dr.",
        count=3,
    )


async def test_generate_derivative_dispatches_carousel_with_default_count(db, mock_agents):
    project = await _make_project(db)

    content = await generate_derivative(
        project=project,
        derivative_type=DerivativeType.CAROUSEL,
        materials=["material"],
        target_language="en",
        instruction=None,
        speaker=None,
        persona=None,
    )

    assert content == {"type": DerivativeType.CAROUSEL.value}
    called = mock_agents[DerivativeType.CAROUSEL].generate.call_args.kwargs
    assert called["count"] == 6


async def test_generate_derivative_rejects_unknown_type(db):
    project = await _make_project(db)

    with pytest.raises(ValueError, match="Unsupported derivative type"):
        await generate_derivative(
            project=project,
            derivative_type=DerivativeType.MULTILINGUAL_SCRIPT,
            materials=["material"],
            target_language="en",
            instruction=None,
            speaker=None,
            persona=None,
        )
