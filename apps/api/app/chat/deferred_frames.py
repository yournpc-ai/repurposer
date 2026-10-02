"""Deferred SSE frames for the material-pending lane (落地时刻压制批).

A turn whose assemble saw files still processing MAY close on the
material-pending commitment — the one-clause "understood + I will speak
once the read lands" reply. That clause is written against the
assemble-time world, and short material routinely finishes processing
MID-TURN (a 15s video reads in ~10s; the router's own call takes longer).
When the understanding beat has already landed, the commitment arrives
stale: a promise whose fulfillment (the world-fired review turn) is
already queued behind this turn's close, waiting on the politeness gate.

So while the lane is possible, this buffer holds the turn's prose deltas
and tool-structure frames in arrival order instead of streaming them live:

- terminal ACCEPT → :meth:`flush` replays the queue through the real hooks
  in order (the client paces it with the usual typewriter — buffering
  never teleports prose); an accept that followed a rejection DROPS
  instead — the queued words were retracted speech, and the settled
  envelope paces out whole exactly like the zero-delta path;
- the marked commitment landing STALE (the beat exists) → :meth:`drop`
  discards the queue unsent, the turn closes silent, and the review turn
  speaks next — one narrator, no expired promise;
- the checkpoint channel flushes FIRST (its frame goes out live mid-loop):
  prose spoken before a read must land before the read's statement.

Liveness never suffers: reasoning keepalives, phase labels, and activity
frames ride their own channels, undeferred.
"""

from collections.abc import Awaitable, Callable
from typing import Any

Hook = Callable[..., Awaitable[None]]


class DeferredFrames:
    """One turn's order-preserving SSE frame buffer. Armed at most once per
    turn (the runner, when the assemble stamped files-still-processing);
    ``armed`` reads False after a flush/drop — later frames pass through."""

    def __init__(self, hooks: dict[str, Hook | None]) -> None:
        self._hooks = hooks
        self._frames: list[tuple[str, tuple[Any, ...]]] | None = []
        self.saw_rejection = False

    @property
    def armed(self) -> bool:
        return self._frames is not None

    def wrap(self, kind: str) -> Hook | None:
        """Queueing wrapper for one hook ('delta' / 'tool_call' /
        'tool_ready'). Returns None when the real hook is None — the
        one-shot path arms nothing (its caller gates on on_delta)."""
        hook = self._hooks.get(kind)
        if hook is None:
            return None

        async def queued(*args: Any) -> None:
            if self._frames is not None:
                self._frames.append((kind, args))
            else:
                await hook(*args)

        return queued

    def note_rejection(self) -> None:
        """A rejected call's queued prose is retracted speech — the accept's
        flush becomes a drop (the envelope paces the settled words whole)."""
        self.saw_rejection = True

    async def flush(self) -> None:
        """Replay the queue in arrival order through the real hooks, then
        disarm. No-op once disarmed (the suppress path drops first)."""
        frames, self._frames = self._frames, None
        for kind, args in frames or []:
            hook = self._hooks.get(kind)
            if hook is not None:
                await hook(*args)

    def drop(self) -> None:
        """Discard unsent (the stale commitment; the exhaustion degrade —
        every queued word was rejected speech)."""
        self._frames = None


__all__ = ["DeferredFrames"]
