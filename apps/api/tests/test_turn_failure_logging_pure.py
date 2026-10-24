"""G0 regression: SSE turn failures must leave a locatable log (stack + ids),
and the user-facing frame mapping must not change.

Covers the two terminal exception seats (``_turn_stream`` / ``_answer_stream``)
and the ``_failure_detail`` mapping they share. Pure: the DB session and all
persistence helpers are stubbed; no DB, no LLM, no HTTP.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import structlog.testing
from fastapi import HTTPException

from app.chat import routes as chat_routes
from app.chat.routes import _failure_detail
from app.pipeline.errors import USER_ERROR_LINES
from app.providers.llm.base import LLMError

# ---------------------------------------------------------------------------
# _failure_detail — the user-facing mapping is pinned unchanged
# ---------------------------------------------------------------------------


def test_failure_detail_http_str_detail_passes_through():
    exc = HTTPException(422, "bad input")
    assert _failure_detail(exc, "en") == "bad input"


def test_failure_detail_http_structured_detail_passes_as_object():
    detail = {"error": "credits.insufficient", "needed": 10}
    exc = HTTPException(402, detail)
    assert _failure_detail(exc, "en") is detail


def test_failure_detail_llm_error_rides_localized_line():
    exc = LLMError("provider boom", user_key="step_failed")
    assert _failure_detail(exc, "en") == USER_ERROR_LINES["step_failed"]["en"]


def test_failure_detail_user_key_exception_rides_localized_line():
    exc = Exception("innards")
    exc.user_key = "film_views_missing"
    assert _failure_detail(exc, "en") == USER_ERROR_LINES["film_views_missing"]["en"]


def test_failure_detail_generic_never_leaks_innards():
    assert (
        _failure_detail(RuntimeError("db password hunter2"), "en")
        == "Internal server error"
    )


# ---------------------------------------------------------------------------
# Stream seats — exception logs stack + identifiers; frame stays safe
# ---------------------------------------------------------------------------


class _DummySession:
    """Stand-in AsyncSession: context-managed, answer stream's conversation
    lookup returns a fixed id. Nothing else is reachable in the failure
    paths under test."""

    conversation_id = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):
        conv_id = self.conversation_id
        return SimpleNamespace(scalar_one=lambda: conv_id)


async def _noop_async(*args, **kwargs):
    return None


def _stub_common(monkeypatch, conversation_id):
    _DummySession.conversation_id = conversation_id
    monkeypatch.setattr(
        "app.models.database.AsyncSessionLocal", lambda: _DummySession()
    )
    monkeypatch.setattr(chat_routes, "stamp_turn_failed", _noop_async)
    monkeypatch.setattr(chat_routes, "persist_turn_failed_line", _noop_async)
    monkeypatch.setattr(chat_routes, "_persist_activity_forensics", _noop_async)
    monkeypatch.setattr(chat_routes, "_persist_candidates_log", _noop_async)


@pytest.mark.asyncio
async def test_turn_stream_exception_logs_stack_and_keeps_safe_frame(monkeypatch):
    user_id, project_id, conv_id, msg_id = uuid4(), uuid4(), uuid4(), uuid4()
    _stub_common(monkeypatch, conv_id)

    prepared = SimpleNamespace(
        user_message=SimpleNamespace(id=msg_id), conversation_id=conv_id
    )

    async def _prepare(*args, **kwargs):
        return prepared

    async def _boom(*args, **kwargs):
        raise RuntimeError("sentinel-boom")

    monkeypatch.setattr(chat_routes, "prepare_chat_turn", _prepare)
    monkeypatch.setattr(chat_routes, "execute_chat_turn", _boom)

    data = SimpleNamespace(project_id=project_id)
    with structlog.testing.capture_logs() as logs:
        frames = [f async for f in chat_routes._turn_stream(user_id, data, "en")]

    # The terminal frame is unchanged: safe generic detail, no innards leak.
    terminal = [f for f in frames if f.startswith("event: turn.failed")]
    assert terminal, f"no terminal frame in {frames!r}"
    payload = json.loads(terminal[0].split("data: ", 1)[1])
    assert payload["detail"] == "Internal server error"
    assert payload["persisted"] is True
    assert "sentinel-boom" not in terminal[0]

    # The server-side log carries the stack and the turn identifiers.
    events = [log for log in logs if log.get("event") == "chat_turn_failed"]
    assert len(events) == 1, f"expected one chat_turn_failed log, got {logs!r}"
    entry = events[0]
    assert entry.get("exc_info"), "exception logged without stack info"
    assert entry["conversation_id"] == str(conv_id)
    assert entry["user_message_id"] == str(msg_id)
    assert entry["project_id"] == str(project_id)
    assert entry["user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_answer_stream_exception_logs_stack_and_keeps_safe_frame(monkeypatch):
    user_id, conv_id, message_id = uuid4(), uuid4(), uuid4()
    _stub_common(monkeypatch, conv_id)

    async def _boom(*args, **kwargs):
        raise RuntimeError("sentinel-boom")

    monkeypatch.setattr(chat_routes, "answer_question", _boom)

    with structlog.testing.capture_logs() as logs:
        frames = [
            f
            async for f in chat_routes._answer_stream(
                user_id, message_id, SimpleNamespace(), "en"
            )
        ]

    terminal = [f for f in frames if f.startswith("event: answer.failed")]
    assert terminal, f"no terminal frame in {frames!r}"
    payload = json.loads(terminal[0].split("data: ", 1)[1])
    assert payload["detail"] == "Internal server error"
    assert "sentinel-boom" not in terminal[0]

    events = [log for log in logs if log.get("event") == "answer_turn_failed"]
    assert len(events) == 1, f"expected one answer_turn_failed log, got {logs!r}"
    entry = events[0]
    assert entry.get("exc_info"), "exception logged without stack info"
    assert entry["conversation_id"] == str(conv_id)
    assert entry["message_id"] == str(message_id)
    assert entry["user_id"] == str(user_id)


# ---------------------------------------------------------------------------
# Engine configuration — the pre_ping seat is on the app's real engine
# ---------------------------------------------------------------------------


def test_app_engine_has_pre_ping_enabled():
    from app.models.database import engine

    assert getattr(engine.sync_engine.pool, "_pre_ping", None) is True
