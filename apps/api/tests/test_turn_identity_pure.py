"""Turn identity survives auto-start without adopting recovered plans."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.chat import service


async def _run_auto_start(monkeypatch, *, opening_turn_id, persisted_turn_id):
    run_id = uuid4()
    pending = SimpleNamespace(
        id=uuid4(),
        answer=None,
        turn_id=persisted_turn_id,
        question={"kind": "task_book", "requires_confirmation": False},
        intent={"action": "draft", "tasks": []},
        workflow_run_id=None,
        content="Plan",
    )
    project = SimpleNamespace(id=uuid4(), pending_brief={})
    answer = AsyncMock(return_value=(pending, None))

    async def _start(*args, **kwargs):
        pending.workflow_run_id = run_id
        return await answer(*args, **kwargs)

    monkeypatch.setattr(service, "latest_pending_question", AsyncMock(return_value=pending))
    monkeypatch.setattr(service, "is_pending_plan", lambda row: row is pending)
    monkeypatch.setattr(service, "answer_question", _start)
    monkeypatch.setattr(
        "app.pipeline.lifecycle.project_lifecycle",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr("app.pipeline.lifecycle.evaluate_start_gate", lambda **kwargs: None)

    started = await service._auto_start_docked_plan(
        SimpleNamespace(),
        user_id=uuid4(),
        conversation_id=uuid4(),
        project=project,
        turn_id=opening_turn_id,
    )
    assert started == (pending, run_id)
    return pending, answer


@pytest.mark.asyncio
async def test_new_auto_start_dock_carries_opening_user_turn(monkeypatch):
    opening_turn_id = uuid4()
    pending, answer = await _run_auto_start(
        monkeypatch,
        opening_turn_id=opening_turn_id,
        persisted_turn_id=None,
    )
    assert pending.turn_id == opening_turn_id
    assert answer.await_args.kwargs["turn_id"] == opening_turn_id


@pytest.mark.asyncio
async def test_presentation_recovery_does_not_reparent_old_plan(monkeypatch):
    original_turn_id = uuid4()
    pending, answer = await _run_auto_start(
        monkeypatch,
        opening_turn_id=None,
        persisted_turn_id=original_turn_id,
    )
    assert pending.turn_id == original_turn_id
    assert answer.await_args.kwargs["turn_id"] is None
