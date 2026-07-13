"""Integration tests for the generation orchestration."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.schemas import (
    ClipPlan,
    ClipPlans,
    ContentPlan,
    DerivativePlan,
    DerivativeType,
    GenerationContext,
    ProjectStatus,
    WorkflowStatus,
)
from app.models.tables import Asset, Project, User, WorkflowRun


async def _make_project(db, materials=None):
    user = User(email="gen-test@example.com")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    project = Project(
        user_id=user.id,
        title="Generation Test",
        event_name="Test Event",
        language="en",
        status=ProjectStatus.PROCESSING,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    if materials:
        for text in materials:
            asset = Asset(
                project_id=project.id,
                user_id=user.id,
                type="transcript",
                extracted_text=text,
                meta={},
            )
            db.add(asset)
        await db.commit()

    return project


@pytest.fixture
def mock_agents():
    """Patch all agents used by run_generation."""
    with (
        patch("app.services.generation.content_director_agent") as director,
        patch("app.services.generation.clip_agent") as clip,
        patch(
            "app.services.generation.generate_derivative",
            new=AsyncMock(return_value={"mock": "content"}),
        ) as dispatch,
    ):
        director.plan = AsyncMock(
            return_value=ContentPlan(
                core_thesis="Test thesis",
                themes=["theme1"],
                target_audience="testers",
                derivatives=[
                    DerivativePlan(derivative_type=DerivativeType.LINKEDIN_POST),
                    DerivativePlan(derivative_type=DerivativeType.QUOTE_CARD),
                ],
            )
        )
        clip.generate = AsyncMock(
            return_value=ClipPlans(
                clips=[
                    ClipPlan(
                        id="clip_001",
                        source_text="source",
                        start_marker="start",
                        end_marker="end",
                        hook="Hook",
                    )
                ]
            )
        )
        yield director, clip, dispatch


@pytest.fixture
def patched_session(db):
    """Patch AsyncSessionLocal so run_generation uses the test session."""
    from app.services import generation as generation_module

    class _SessionProxy:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _SessionMaker:
        def __call__(self):
            return _SessionProxy()

    with patch.object(generation_module, "AsyncSessionLocal", _SessionMaker()):
        yield


async def test_run_generation_calls_director_first(db, mock_agents, patched_session):
    from app.services.generation import run_generation

    director, clip, dispatch = mock_agents
    project = await _make_project(db, materials=["Some speech text"])
    run = WorkflowRun(
        project_id=project.id,
        status=WorkflowStatus.PENDING,
        context={
            "outputs": ["clips", "linkedin", "quote_cards"],
            "clip_count": 1,
            "target_language": "en",
        },
    )
    db.add(run)
    await db.commit()

    await run_generation(run.id)

    await db.refresh(run)
    assert run.status == WorkflowStatus.COMPLETED
    assert run.current_step == "done"

    # Director should be called exactly once and before any other agent.
    director.plan.assert_awaited_once()
    clip.generate.assert_awaited_once()
    assert dispatch.await_count == 2

    # Verify the director received a GenerationContext and requested derivatives.
    director_call = director.plan.call_args.kwargs
    assert isinstance(director_call["context"], GenerationContext)
    assert DerivativeType.LINKEDIN_POST in director_call["requested_derivatives"]
    assert DerivativeType.QUOTE_CARD in director_call["requested_derivatives"]

    # Verify clip agent received context + content_plan.
    clip_call = clip.generate.call_args.kwargs
    assert isinstance(clip_call["context"], GenerationContext)
    assert isinstance(clip_call["content_plan"], ContentPlan)

    # Verify derivative dispatch received context + content_plan.
    for call in dispatch.call_args_list:
        kwargs = call.kwargs
        assert isinstance(kwargs["context"], GenerationContext)
        assert isinstance(kwargs["content_plan"], ContentPlan)


async def test_run_generation_keeps_legacy_step_order(db, mock_agents, patched_session):
    from app.services.generation import run_generation

    director, clip, dispatch = mock_agents
    director.plan.return_value = ContentPlan(
        core_thesis="Test thesis",
        themes=["theme1"],
        target_audience="testers",
        derivatives=[
            DerivativePlan(derivative_type=DerivativeType.LINKEDIN_POST),
            DerivativePlan(derivative_type=DerivativeType.QUOTE_CARD),
            DerivativePlan(derivative_type=DerivativeType.CAROUSEL),
            DerivativePlan(derivative_type=DerivativeType.SUMMARY),
            DerivativePlan(derivative_type=DerivativeType.BLOG),
        ],
    )
    project = await _make_project(db, materials=["Speech text"])
    run = WorkflowRun(
        project_id=project.id,
        status=WorkflowStatus.PENDING,
        context={
            "outputs": ["clips", "linkedin", "quote_cards", "carousel", "summary", "blog"],
            "clip_count": 1,
            "target_language": "en",
            "assistant_message_id": str(uuid4()),
        },
    )
    db.add(run)
    await db.commit()

    await run_generation(run.id)

    await db.refresh(run)
    assert run.status == WorkflowStatus.COMPLETED
    assert run.current_step == "done"
    # All requested derivative outputs should have been dispatched.
    assert dispatch.await_count == 5
    dispatched_types = [
        call.kwargs["derivative_type"] for call in dispatch.call_args_list
    ]
    assert DerivativeType.LINKEDIN_POST in dispatched_types
    assert DerivativeType.QUOTE_CARD in dispatched_types
    assert DerivativeType.CAROUSEL in dispatched_types
    assert DerivativeType.SUMMARY in dispatched_types
    assert DerivativeType.BLOG in dispatched_types
