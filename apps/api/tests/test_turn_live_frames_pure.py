"""Live conversation frames carry persisted row and opening-turn identity."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.chat.routes import _interim_prose_frame, _make_candidates_hook


def _payload(frame: str) -> dict:
    return json.loads(frame.split("data: ", 1)[1])


def test_interim_prose_frame_carries_row_seq_and_turn_identity():
    turn_id = uuid4()
    row_id = uuid4()
    identified = _payload(
        _interim_prose_frame(
            "Found it", "2026-10-30T00:00:00Z", str(row_id), 17, turn_id
        )
    )
    assert identified == {
        "text": "Found it",
        "at": "2026-10-30T00:00:00Z",
        "message_id": str(row_id),
        "seq": 17,
        "turn_id": str(turn_id),
    }


@pytest.mark.asyncio
async def test_candidate_live_frame_adds_identity_without_changing_persisted_event():
    queue = asyncio.Queue()
    sink = []
    turn_id = uuid4()
    hook = _make_candidates_hook(queue, sink, turn_id)
    event = {
        "kind": "selection",
        "candidate_set_id": "set-1",
        "selected": [1],
    }
    await hook(event)
    assert sink == [event]
    wire = _payload(await queue.get())
    assert wire == {**event, "turn_id": str(turn_id)}

    anonymous = _make_candidates_hook(queue, [], None)
    await anonymous(event)
    assert _payload(await queue.get())["turn_id"] is None


@pytest.mark.asyncio
async def test_streaming_interim_prose_commits_short_session_before_sse(monkeypatch):
    from app.chat import service

    events = []
    row_id = uuid4()

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def commit(self):
            events.append("commit")

    session = Session()

    async def persist(db, *args):
        assert db is session
        events.append("create")
        return SimpleNamespace(
            id=row_id,
            seq=23,
            created_at=datetime.now(UTC),
        )

    async def on_interim_prose(text, at, message_id, seq):
        events.append(f"emit:{text}:{message_id}:{seq}")

    monkeypatch.setattr(service, "persist_interim_prose", persist)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", lambda: session)
    callback = service._interim_prose_callback(
        object(), uuid4(), on_interim_prose, uuid4()
    )
    await callback("interim_prose")
    assert events == ["create", "commit", f"emit:interim_prose:{row_id}:23"]
