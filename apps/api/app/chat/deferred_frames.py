"""Deferred SSE frames — the speech-commit protocol's terminal buffer (言语提交协议).

Speech that depends on a terminal call's adjudication never commits before
the adjudication lands (ADR-099 §7). On the SSE path every turn arms this
buffer unconditionally: iteration 0 is the only streaming iteration, so its
prose deltas and tool-structure frames are exactly the speech at risk — a
rejected call (loop-level schema/unknown/params, or an execute guardrail)
retracts them, and retracted speech must leave ZERO trace in the message
flow / envelope (activity-stream forensics excepted — G1's seat).

Four-state machine — OPEN → BUFFERING → ACCEPT→FLUSH / REJECT→DROP→RETRY:

- OPEN: armed, queue empty — frames queue in arrival order instead of
  streaming live (BUFFERING on the first frame);
- terminal ACCEPT (clean turn) → :meth:`flush` replays the queue through
  the real hooks in order (the client paces it with the usual typewriter —
  buffering never teleports prose), then :meth:`disarm` closes the turn;
- REJECT (any ToolRejected) → :meth:`retract` clears the stale queue AT
  ONCE and marks the turn's speech retracted, STAYING ARMED — the retry
  re-arms by construction (RETRY); a turn once rejected closes frame-silent
  (:meth:`drop` at the resolution — the settled envelope paces out whole,
  the zero-delta path's law);
- mid-turn release stays armed: a read's acceptance keeps the queue (read
  speech rides the speech ledger into the envelope), and the checkpoint
  channel flushes FIRST (its frame goes out live mid-loop) without
  disarming — prose spoken before a read must land before the read's
  statement, and frames after a checkpoint stay buffered until the close.

Liveness never suffers: reasoning keepalives, phase labels, and activity
frames ride their own channels, undeferred. The StatusLine covers the
validation dead-window (``chatBusy && !proseActive`` — no delta has
reached the client while the terminal call adjudicates).
"""

from collections.abc import Awaitable, Callable
from typing import Any

Hook = Callable[..., Awaitable[None]]


class DeferredFrames:
    """One turn's order-preserving SSE frame buffer. Armed once per turn by
    the runner on the SSE path; ``armed`` reads False after a
    flush-then-:meth:`disarm` close or a :meth:`drop` — later frames pass
    through. ``rejected`` marks a turn whose speech was retracted: its
    close drops instead of flushing (retracted speech leaves no trace)."""

    def __init__(self, hooks: dict[str, Hook | None]) -> None:
        self._hooks = hooks
        self._frames: list[tuple[str, tuple[Any, ...]]] = []
        self._armed = True
        self._rejected = False

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def rejected(self) -> bool:
        return self._rejected

    def wrap(self, kind: str) -> Hook | None:
        """Queueing wrapper for one hook (the runners buffer 'delta' and
        'tool_ready' — prose and the adjudication-dependent preview;
        'tool_call' stays live: the Activity projector's name_known feed
        and the phase-clear are liveness chrome, never retracted speech).
        Returns None when the real hook is None — the one-shot path arms
        nothing (its caller gates on on_delta)."""
        hook = self._hooks.get(kind)
        if hook is None:
            return None

        async def queued(*args: Any) -> None:
            if self._armed:
                self._frames.append((kind, args))
            else:
                await hook(*args)

        return queued

    def retract(self) -> None:
        """REJECT seat: a rejected call's queued prose is retracted speech —
        clear the stale queue at once and mark the turn, STAYING ARMED (the
        retry re-arms by construction; its frames queue fresh). The close
        drops: the settled envelope paces the final words whole."""
        self._frames.clear()
        self._rejected = True

    async def flush(self) -> None:
        """Replay the queue in arrival order through the real hooks, STAYING
        ARMED — mid-turn releases (the checkpoint channel's flush-first)
        and the clean close share this seat; the close follows with
        :meth:`disarm`. Replays each queued frame exactly once."""
        frames, self._frames = self._frames, []
        for kind, args in frames:
            hook = self._hooks.get(kind)
            if hook is not None:
                await hook(*args)

    def drop(self) -> None:
        """Terminal discard: clear unsent and disarm (the rejected turn's
        close — every queued word was retracted speech; the stale
        material-pending commitment; the exhaustion degrade)."""
        self._frames.clear()
        self._armed = False

    def disarm(self) -> None:
        """Terminal close after a flush: later frames pass through live.
        Idempotent (a drop already disarmed)."""
        self._armed = False


__all__ = ["DeferredFrames"]
