"""Agent Activity Projection (ADR-087 §3 — Lifecycle Phase 2).

Internal Agent Events → USER-SAFE activity events. The projector is a pure
per-turn state machine: it eats the loop's typed internal events
(``app/agents/tool_loop.py`` LoopEvent — the kernel says WHAT HAPPENED and
never learns what the user is told, U1 裁定) plus the existing name-known
hook, and emits ordered activity frames for the SSE ``assistant.activity``
channel. Zero DB, zero Domain reads, zero Lifecycle predicates — it is a
visibility mechanism, never an authority (对账规则 7/8/10).

Frozen semantics (用户裁定 2026-09-19, PASS WITH CONDITIONS):

- ``kind`` is a USER-SEMANTIC category (read / draft / run / repair),
  never a tool name — the moment kinds name tools this is a Tool Log with
  better branding.
- ``key`` is the user-safe vocabulary identity: read kinds reuse the
  perception registry's ``activity_key`` (referenced, never duplicated);
  the terminal kinds ride the ``chat.activity.*`` family. Each frame's key
  matches its STATUS (the active frame carries the progressive copy, the
  completed frame the past-tense copy) so the wire schema stays flat.
- Continuity ≠ periodic refresh: an ``active`` activity may legitimately
  span a whole LLM window; what is structural is that every active
  activity reaches an explicit terminal (T16-B) — the envelope sweep
  (``sweep``) is the I-PFA-06 终帧律's activity twin: no activity outlives
  its turn.
- The name→kind mapping's canonical owner is THIS module (U6 裁定); the
  declared tool sets (turn_tools / perception registry) are referenced,
  and the pure suite gates that every declared name lands in exactly one
  bucket (drift = loud, never silent).

Rejected-at-the-moment (拒绝当时): a rejection cancels the call's own
half-started activity (params validation can reject AFTER the name-known
frame started one) and opens ONE aggregated ``repair`` activity; further
rejections keep the same activity (N→1, 对账规则 3). The repair completes
when the NEXT call is accepted (read or terminal), fails on
``LoopExhausted``, and — if the model instead ends the turn with a bare
reply — is swept to completed by the envelope.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.tool_loop import (
    LoopEvent,
    LoopExhausted,
    ReadAccepted,
    TerminalAccepted,
    ToolRejected,
)
from app.chat.perception import PERCEPTION_TOOLS

# The user-semantic kind vocabulary (冻结: user-semantic, never tool names).
KIND_READ = "read"
KIND_DRAFT = "draft"
KIND_RUN = "run"
KIND_REPAIR = "repair"

# Frame statuses (对账规则 6 — the explicit lifecycle).
STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"  # schema-complete; see the module docstring

# The terminal-tool buckets. ask_user / answer are the Assistant
# Conversation layer (their user face is the docked pill / the prose
# itself) — they never open an activity (1→0, 对账规则 4), but their
# rejections still count as repair work. Unknown (hallucinated) names open
# nothing either — the loop already rejects them.
_DRAFT_TOOLS = frozenset({"present_plan", "propose_tasks", "apply_edit_ops", "edit_graph"})
_RUN_TOOLS = frozenset({"start_run"})
_CONVERSATION_TOOLS = frozenset({"ask_user", "answer"})

# Copy keys for the terminal kinds (U7: active/completed status-forms; a
# FAILED frame reuses the ACTIVE key — the ✗ says the work did not land,
# the label keeps saying what the work WAS).
_ACTIVITY_KEYS = {
    KIND_DRAFT: ("chat.activity.draft", "chat.activity.draftDone"),
    KIND_RUN: ("chat.activity.run", "chat.activity.runDone"),
    KIND_REPAIR: ("chat.activity.repair", "chat.activity.repairDone"),
}

# A read's done-form key derives from its registry activity_key by family
# swap (chat.inspecting.* → chat.inspectingDone.*) — the registry stays the
# single vocabulary source, the done family mirrors it in i18n.
_INSPECTING_PREFIX = "chat.inspecting."
_INSPECTING_DONE_PREFIX = "chat.inspectingDone."


def kind_for_tool(tool_name: str) -> str | None:
    """The name→kind mapping's ONE seat. None = the call opens no activity
    (conversation-layer terminal tools / unknown names)."""
    if tool_name in PERCEPTION_TOOLS:
        return KIND_READ
    if tool_name in _DRAFT_TOOLS:
        return KIND_DRAFT
    if tool_name in _RUN_TOOLS:
        return KIND_RUN
    return None


def all_known_tool_names() -> frozenset[str]:
    """Every name the projector can classify — the pure suite's consistency
    gate compares this against the declared tool sets (U6: reference the
    registries, never duplicate them silently)."""
    return frozenset(
        PERCEPTION_TOOLS.keys() | _DRAFT_TOOLS | _RUN_TOOLS | _CONVERSATION_TOOLS
    )


@dataclass(frozen=True)
class ActivityFrame:
    """One user-safe activity frame (the SSE ``assistant.activity`` payload).
    Field whitelist is the contract: id / seq / kind / status / key — never
    params, results, or reasoning text (简报 Prohibited #2, T11)."""

    activity_id: str
    seq: int
    kind: str
    status: str
    key: str | None

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "seq": self.seq,
            "kind": self.kind,
            "status": self.status,
            "key": self.key,
        }


class ActivityProjector:
    """The per-turn projection state machine. Pure: feeds in events, returns
    the frames to emit (deterministic — the same event sequence always
    yields the byte-same frame sequence, T12). One instance per SSE turn;
    the one-shot JSON path never constructs one (no stream, no frames).

    Call-slot bookkeeping: the loop executes strictly one call at a time,
    so a name-known opens the slot and its rejection/acceptance closes it;
    extra name-knowns while a slot is open are the loop's dropped parallel
    calls (tool_loop logs and ignores them — the projector mirrors that).
    """

    def __init__(self) -> None:
        self._seq = 0
        self._count = 0
        # open call slot: (tool_name, activity_id | None)
        self._open_call: tuple[str, str | None] | None = None
        # the aggregated repair span's activity id (None = no repair open)
        self._repair_id: str | None = None
        # still-active activities in birth order: id -> (kind, active key)
        self._active: dict[str, tuple[str, str | None]] = {}

    # -- frame factory -------------------------------------------------

    def _frame(self, activity_id: str, kind: str, status: str, key: str | None) -> ActivityFrame:
        self._seq += 1
        return ActivityFrame(
            activity_id=activity_id, seq=self._seq, kind=kind, status=status, key=key
        )

    def _start(self, kind: str, key: str | None) -> tuple[str, ActivityFrame]:
        self._count += 1
        activity_id = f"a{self._count}"
        self._active[activity_id] = (kind, key)
        return activity_id, self._frame(activity_id, kind, STATUS_ACTIVE, key)

    def _settle(self, activity_id: str, status: str, key: str | None) -> ActivityFrame:
        kind, _ = self._active.pop(activity_id)
        return self._frame(activity_id, kind, status, key)

    @staticmethod
    def _done_key(kind: str, active_key: str | None) -> str | None:
        if kind == KIND_READ and active_key is not None:
            assert active_key.startswith(_INSPECTING_PREFIX)
            return _INSPECTING_DONE_PREFIX + active_key[len(_INSPECTING_PREFIX):]
        pair = _ACTIVITY_KEYS.get(kind)
        return pair[1] if pair else None

    # -- event feeds ----------------------------------------------------

    def name_known(self, tool_name: str) -> list[ActivityFrame]:
        """The existing on_tool_call seam: a call's name became known.
        Opens the call slot; starts the call's activity when the name maps
        to a user-semantic kind."""
        if self._open_call is not None:
            # The loop's dropped parallel extras (it executes call[0] only).
            return []
        kind = kind_for_tool(tool_name)
        if kind is None:
            self._open_call = (tool_name, None)
            return []
        key = (
            PERCEPTION_TOOLS[tool_name].activity_key
            if kind == KIND_READ
            else _ACTIVITY_KEYS[kind][0]
        )
        activity_id, frame = self._start(kind, key)
        self._open_call = (tool_name, activity_id)
        return [frame]

    def feed_event(self, event: LoopEvent) -> list[ActivityFrame]:
        """The typed loop-event seam (U1)."""
        if isinstance(event, ToolRejected):
            return self._on_rejection()
        if isinstance(event, (ReadAccepted, TerminalAccepted)):
            return self._on_accepted()
        if isinstance(event, LoopExhausted):
            return self._on_exhausted()
        raise AssertionError(f"unknown loop event: {event!r}")  # exhaustive union

    def _on_rejection(self) -> list[ActivityFrame]:
        """拒绝当时: cancel the call's half-started activity (if the
        name-known beat started one) and open/keep the ONE repair span."""
        frames: list[ActivityFrame] = []
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None:
                kind, key = self._active[activity_id]
                frames.append(self._settle(activity_id, STATUS_CANCELLED, key))
            self._open_call = None
        if self._repair_id is None:
            self._repair_id, frame = self._start(KIND_REPAIR, _ACTIVITY_KEYS[KIND_REPAIR][0])
            frames.append(frame)
        return frames

    def _on_accepted(self) -> list[ActivityFrame]:
        """An accepted call closes the open repair span FIRST (the rework
        succeeded), then completes the call's own activity."""
        frames: list[ActivityFrame] = []
        if self._repair_id is not None:
            frames.append(
                self._settle(
                    self._repair_id, STATUS_COMPLETED, _ACTIVITY_KEYS[KIND_REPAIR][1]
                )
            )
            self._repair_id = None
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None:
                kind, key = self._active[activity_id]
                frames.append(
                    self._settle(activity_id, STATUS_COMPLETED, self._done_key(kind, key))
                )
            self._open_call = None
        return frames

    def _on_exhausted(self) -> list[ActivityFrame]:
        """The honest-degradation fact: the repair span FAILED (never swept
        to completed by the cannot-do envelope — T5/T15)."""
        frames: list[ActivityFrame] = []
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None:
                kind, key = self._active[activity_id]
                frames.append(self._settle(activity_id, STATUS_CANCELLED, key))
            self._open_call = None
        if self._repair_id is not None:
            frames.append(
                self._settle(self._repair_id, STATUS_FAILED, _ACTIVITY_KEYS[KIND_REPAIR][0])
            )
            self._repair_id = None
        return frames

    def sweep(self, outcome: str) -> list[ActivityFrame]:
        """The envelope's closing sweep (终帧律的活动同形 — T16-B): anything
        still active when the turn ends is settled NOW — ``completed`` on a
        completed turn (e.g. a bare reply after rejections completes the
        repair), ``failed`` on a failed turn. After the sweep, zero
        activities are active, structurally."""
        status = STATUS_COMPLETED if outcome == "completed" else STATUS_FAILED
        frames: list[ActivityFrame] = []
        if self._repair_id is not None:
            key = (
                _ACTIVITY_KEYS[KIND_REPAIR][1]
                if status == STATUS_COMPLETED
                else _ACTIVITY_KEYS[KIND_REPAIR][0]
            )
            frames.append(self._settle(self._repair_id, status, key))
            self._repair_id = None
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None and activity_id in self._active:
                kind, key = self._active[activity_id]
                frames.append(
                    self._settle(
                        activity_id,
                        status,
                        self._done_key(kind, key) if status == STATUS_COMPLETED else key,
                    )
                )
            self._open_call = None
        return frames

    def has_active(self) -> bool:
        return bool(self._active)


__all__ = [
    "ActivityFrame",
    "ActivityProjector",
    "KIND_DRAFT",
    "KIND_READ",
    "KIND_REPAIR",
    "KIND_RUN",
    "STATUS_ACTIVE",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "all_known_tool_names",
    "kind_for_tool",
]
