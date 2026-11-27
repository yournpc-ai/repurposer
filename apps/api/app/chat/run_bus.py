"""In-process multi-subscriber Run Event Bus for seamless SSE re-attach.

Every active chat/answer/resume execution registers a RunState under its
conversation_id. The primary SSE stream and any re-attaching tab
(GET /api/v1/chat/conversations/{id}/events?after_seq=...) subscribe to the
same fan-out bus, while GET /api/v1/chat/conversation reads the live snapshot
(run_id, live_focus, steps, latest_seq) with zero DB polling overhead.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass
class RunState:
    run_id: str
    conversation_id: UUID
    turn_id: UUID | None = None
    status: str = "running"  # running | completed | failed | cancelled
    live_focus: str | None = None
    steps: list[dict[str, str]] | None = None
    latest_seq: int | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class RunEventBus:
    """Conversation-scoped fan-out bus for active runs."""

    def __init__(self) -> None:
        self._active: dict[UUID, RunState] = {}

    def start_run(
        self,
        conversation_id: UUID,
        *,
        run_id: str,
        turn_id: UUID | None = None,
    ) -> RunState:
        state = RunState(
            run_id=run_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )
        self._active[conversation_id] = state
        return state

    def bind_turn(self, conversation_id: UUID, run_id: str, turn_id: UUID | None) -> None:
        state = self._active.get(conversation_id)
        if state is not None and state.run_id == run_id and turn_id is not None:
            state.turn_id = turn_id

    def observe_frame(self, conversation_id: UUID, run_id: str, frame: Any) -> None:
        """Update live snapshot metadata and fan out serialized SSE frames to
        secondary subscribers (re-attached tabs)."""
        state = self._active.get(conversation_id)
        if state is None or state.run_id != run_id:
            return
        if isinstance(frame, str):
            self._inspect_sse_frame(state, frame)
            for sub in list(state.subscribers):
                try:
                    sub.put_nowait(frame)
                except asyncio.QueueFull:
                    pass

    def finish_run(
        self,
        conversation_id: UUID,
        run_id: str,
        status: str,
        terminal_sse: str | None = None,
    ) -> None:
        state = self._active.get(conversation_id)
        if state is None or state.run_id != run_id:
            return
        state.status = status
        if status != "running":
            state.live_focus = None
        for sub in list(state.subscribers):
            if terminal_sse is not None:
                try:
                    sub.put_nowait(terminal_sse)
                except asyncio.QueueFull:
                    pass
            try:
                sub.put_nowait(None)  # sentinel: run ended
            except asyncio.QueueFull:
                pass
        if self._active.get(conversation_id) is state:
            self._active.pop(conversation_id, None)

    def active_run(self, conversation_id: UUID) -> RunState | None:
        state = self._active.get(conversation_id)
        if state is not None and state.status == "running":
            return state
        return None

    def active_run_summary(self, conversation_id: UUID) -> dict[str, Any] | None:
        state = self.active_run(conversation_id)
        if state is None:
            return None
        return {
            "run_id": state.run_id,
            "turn_id": str(state.turn_id) if state.turn_id else None,
            "status": state.status,
            "live_focus": state.live_focus,
            "steps": state.steps,
            "latest_seq": state.latest_seq,
            "started_at": state.started_at,
        }

    @asynccontextmanager
    async def subscribe(self, conversation_id: UUID):
        state = self.active_run(conversation_id)
        if state is None:
            yield None, None
            return
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        state.subscribers.add(q)
        try:
            yield state, q
        finally:
            state.subscribers.discard(q)

    @staticmethod
    def _active_step_title(steps: list[dict[str, Any]] | None) -> str | None:
        if not steps:
            return None
        for step in steps:
            if isinstance(step, dict) and step.get("status") == "in_progress":
                title = step.get("title")
                if isinstance(title, str) and title.strip():
                    return title.strip()
        return None

    @staticmethod
    def _inspect_sse_frame(state: RunState, frame: str) -> None:
        """Parse lightweight snapshot fields (focus, steps, seq) from SSE frames."""
        if not frame.startswith("event: "):
            return
        lines = frame.splitlines()
        if len(lines) < 2 or not lines[1].startswith("data: "):
            return
        event = lines[0][7:].strip()
        raw = lines[1][6:]
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            return
        if not isinstance(payload, dict):
            return
        if event == "assistant.activity":
            kind = payload.get("kind")
            if kind == "focus":
                focus = payload.get("focus")
                state.live_focus = focus.strip() if isinstance(focus, str) and focus.strip() else None
            elif kind == "steps":
                steps = payload.get("steps")
                if isinstance(steps, list) and steps:
                    prev_active = RunEventBus._active_step_title(state.steps)
                    next_active = RunEventBus._active_step_title(steps)
                    if prev_active is not None and next_active != prev_active:
                        state.live_focus = None
                    state.steps = steps
        elif event == "assistant.interim_prose":
            state.live_focus = None
            seq = payload.get("seq")
            if isinstance(seq, int) and (state.latest_seq is None or seq > state.latest_seq):
                state.latest_seq = seq
        elif event == "assistant.row.append":
            row = payload.get("row")
            if isinstance(row, dict):
                seq = row.get("seq")
                if isinstance(seq, int) and (state.latest_seq is None or seq > state.latest_seq):
                    state.latest_seq = seq


run_bus = RunEventBus()


__all__ = ["RunEventBus", "RunState", "run_bus"]
