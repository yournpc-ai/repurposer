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
frame started one) and opens ONE aggregated ``repair`` span; further
rejections keep the same span (N→1, 对账规则 3).

The repair span's visibility law (言语提交协议批 — 事故③ 修宪): the span
is work-state bookkeeping first, user-facing only when its TERMINAL is
itself a user-relevant fact. It opens SILENTLY (no active frame — the
retry window is an ordinary LLM window, covered by the think row /
StatusLine; narrating the retry itself is 宪法② machinery speech) and its
terminal follows the judgment tree:

- close by an accepted READ (incl. the exploration observation verbs) →
  SILENT: the read's own row narrates the work in flight, and the retried
  terminal may still come — a redirection claim would be premature;
- close by an accepted TERMINAL whose name is among the span's rejected
  names (同形 retry) → SILENT: the final call's own evidence (the dock,
  the reply) is the whole story — nothing was publicly committed, so
  nothing needs accounting;
- close by an accepted TERMINAL whose name is NOT among the rejected
  names, all of which are known (实质工作变化 — the guardrail redirected
  the turn's form, e.g. present_plan → ask_user) → ONE born-terminal
  COMPLETED frame saying the work change (``chat.activity.repairDone``),
  never a model self-reflection; unprovable (any rejected name unknown —
  a truncation severed it) → SILENT (无依据则不言);
- ``LoopExhausted``, or a failed turn's sweep → ONE born-terminal FAILED
  frame (``chat.activity.repair``) — the honest failure evidence;
- a completed turn's sweep (the retry ended in a bare reply) → SILENT:
  the reply IS the final form.

Silent spans emit nothing and persist nothing; the two terminal frames
carry the span's real elapsed as ``duration_ms`` (the retry window was
genuine server work). The rejection FORENSICS never depend on visibility:
every rejection lands in the projector's ``_rejections`` ledger (tool
name / kind / iteration / detail / at), persisted beside the settled
frames in the activity_log row — the user stream stays clean while the
attempt stays auditable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.agents.tool_loop import (
    LoopEvent,
    LoopExhausted,
    ReadAccepted,
    ReadExecuting,
    TerminalAccepted,
    ToolRejected,
)
from app.chat.exploration_tools import EXPLORATION_TOOLS
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
# revise_output (iter-3 S3, N-58): its user face is the SAME revision-work
# row as edit_graph's (the wiring dispatch seat is shared) — draft bucket.
# edit_output (S3, N-59): the precise edit's user face is the draft-work row
# too (op write + re-pend + re-render).
# (Final Hardening B1, 2026-09-24: apply_edit_ops retired — removed here.)
_DRAFT_TOOLS = frozenset({"present_plan", "propose_tasks", "edit_graph", "revise_output", "edit_output"})
_RUN_TOOLS = frozenset({"start_run"})
_CONVERSATION_TOOLS = frozenset({"ask_user", "answer"})
# The exploration proposal verbs (iter-2 ⑤/⑥, ADR-088 旅程四): their user
# face is the milestone frame (``explore_milestone`` below) + the canvas
# card + the decision package dock — never a per-call activity (the
# conversation tools' 1→0 同律). Referenced from the registry (U6 — never
# re-typed), and their rejections still count as repair work.
_EXPLORATION_VERBS: frozenset[str] = frozenset(EXPLORATION_TOOLS)

# Copy keys for the terminal kinds (U7: active/completed status-forms; a
# FAILED frame reuses the ACTIVE key — the ✗ says the work did not land,
# the label keeps saying what the work WAS). The draft kind speaks TWO key
# pairs (2026-09-25 文案批): proposing a plan reads as 整理方案, revising
# existing work reads as 修改 — one kind, picked by tool at open time.
# The draft/run DONE keys ride the live wire only: their settles never
# persist and never render (落定即退役 2026-09-28 draft, 2026-09-29 run —
# the docked plan card / the start speech + RunTaskList receipt is the
# settled evidence).
_ACTIVITY_KEYS = {
    KIND_DRAFT: ("chat.activity.draft", "chat.activity.draftDone"),
    KIND_RUN: ("chat.activity.run", "chat.activity.runDone"),
    KIND_REPAIR: ("chat.activity.repair", "chat.activity.repairDone"),
}

# The draft bucket's revision verbs → the edit key pair (the plan verbs
# propose_tasks / present_plan keep the kind default above).
_EDIT_TOOLS = frozenset({"edit_graph", "revise_output", "edit_output"})
_EDIT_KEYS = ("chat.activity.edit", "chat.activity.editDone")


def _active_key_for(kind: str, tool_name: str) -> str | None:
    """The open-time key: the draft kind's two user faces split by tool."""
    if kind == KIND_DRAFT and tool_name in _EDIT_TOOLS:
        return _EDIT_KEYS[0]
    pair = _ACTIVITY_KEYS.get(kind)
    return pair[0] if pair else None

# A read's done-form key derives from its registry activity_key by family
# swap (chat.inspecting.* → chat.inspectingDone.*) — the registry stays the
# single vocabulary source, the done family mirrors it in i18n.
_INSPECTING_PREFIX = "chat.inspecting."
_INSPECTING_DONE_PREFIX = "chat.inspectingDone."
# The failed-form family (ADR-102 §5): an unreadable read settles FAILED with
# this mirror — the done family's honest counterweight, never a silent lie.
_INSPECTING_FAILED_PREFIX = "chat.inspectingFailed."

# The work-session family (iter-2 ⑥, N-57): ``chat.explore.searching`` is
# search_transcript's re-homed activity_key (done mirror = key + "Done",
# same inspecting→inspectingDone 同律 at this family's shape); the three
# milestone keys fire ONE born-completed frame at each door success, with
# the artifact count as the only payload (Activity 十规则 — user-safe pure
# count, never params / excerpts / reasoning).
_EXPLORE_PREFIX = "chat.explore."
_EXPLORE_MILESTONE_KEYS: frozenset[str] = frozenset(
    {
        "chat.explore.candidatesReady",
        "chat.explore.selectsReady",
        "chat.explore.plansReady",
    }
)


def kind_for_tool(tool_name: str) -> str | None:
    """The name→kind mapping's ONE seat. None = the call opens no activity
    (conversation-layer terminal tools / the exploration verbs / unknown
    names)."""
    if tool_name in PERCEPTION_TOOLS:
        return KIND_READ
    if tool_name in _DRAFT_TOOLS:
        return KIND_DRAFT
    if tool_name in _RUN_TOOLS:
        return KIND_RUN
    return None


def frame_persistence(frame: ActivityFrame) -> str | None:
    """ADR-108 §2 — 每帧一行的持久化映射（唯一判定座，纯函数）:

    - ``"append"`` — born-terminal frames land as their OWN array row at
      emission: explore milestones (born-completed count facts) and repair
      terminals (the visibility law's one user-relevant frame);
    - ``"settle"`` — a READ span's terminal frame (completed / failed /
      cancelled): the row was appended at execute entry (ReadExecuting),
      the terminal UPDATEs it in place;
    - ``None`` — live-only: draft/run spans (落定即退役 — the docked plan
      card / the run receipt is their settled evidence) and the read's
      ACTIVE frame (the row appends at ReadExecuting, never at name_known —
      appending there would seat the row before the waiter checkpoint's).
    """
    if frame.kind == KIND_READ:
        return None if frame.status == STATUS_ACTIVE else "settle"
    if frame.kind == KIND_REPAIR and frame.status in (STATUS_COMPLETED, STATUS_FAILED):
        return "append"
    if frame.kind == KIND_DRAFT and frame.key in _EXPLORE_MILESTONE_KEYS:
        return "append"
    return None


def all_known_tool_names() -> frozenset[str]:
    """Every name the projector can classify — the pure suite's consistency
    gate compares this against the declared tool sets (U6: reference the
    registries, never duplicate them silently)."""
    return frozenset(
        PERCEPTION_TOOLS.keys()
        | _DRAFT_TOOLS
        | _RUN_TOOLS
        | _CONVERSATION_TOOLS
        | _EXPLORATION_VERBS
    )


@dataclass(frozen=True)
class ActivityFrame:
    """One user-safe activity frame (the SSE ``assistant.activity`` payload).
    Field whitelist is the contract: id / seq / kind / status / key — never
    params, results, or reasoning text (简报 Prohibited #2, T11). Iter-2 ⑥
    (N-57) extends the whitelist by ONE key: ``count`` — the work-session
    milestone's pure artifact count, present only on milestone frames.
    Iter-3 S7 (E7) extends it by TWO more: ``at`` — the frame's birth stamp
    (ISO UTC, EVERY frame — the web timeline interleaves activity rows with
    messages by real moments) and ``duration_ms`` — the real elapsed of a
    span that was genuinely ACTIVE, present only on its settling frame (a
    born-completed milestone is an instant fact — it carries no fake zero)."""

    activity_id: str
    seq: int
    kind: str
    status: str
    key: str | None
    count: int | None = None
    at: str = ""
    duration_ms: int | None = None

    def to_dict(self) -> dict:
        d = {
            "activity_id": self.activity_id,
            "seq": self.seq,
            "kind": self.kind,
            "status": self.status,
            "key": self.key,
            "at": self.at,
        }
        if self.count is not None:
            d["count"] = self.count
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d


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
        # the repair span's rejected tool names in span order (None = a
        # truncation severed the name) — the terminal's 同形/变化 judgment
        # reads this (see the module docstring's visibility law)
        self._repair_rejected: list[str | None] = []
        # The turn's rejection FORENSIC ledger (rejection 取证批): every
        # ToolRejected as one plain-fact record {tool_name, kind, iteration,
        # detail, at} — the SSE route persists it beside the settled frames
        # in the activity_log row, so a rejected attempt is auditable after
        # the fact even when the span itself stays invisible.
        self._rejections: list[dict] = []
        # still-active activities in birth order: id -> (kind, active key,
        # monotonic start — the S7 duration_ms source; monotonic, never the
        # wall clock, so a clock adjustment never fabricates a negative span)
        self._active: dict[str, tuple[str, str | None, float]] = {}
        # The turn's durable history (activity 持久化, 2026-09-25): every
        # frame that reached a TERMINAL state, in emission order — minus
        # draft/run spans, whose settles never persist (落定即退役
        # 2026-09-28 draft, 2026-09-29 run: the docked plan card / the start
        # speech + RunTaskList receipt is the evidence). The
        # envelope sweep's 终帧律 guarantees zero active at turn end, so
        # this list IS the whole story — the SSE route persists it as one
        # activity_log message row so a refresh replays the settled rows
        # (they were memory-only before, and the flow changed on F5).
        self._settled: list[ActivityFrame] = []

    # -- frame factory -------------------------------------------------

    def _frame(
        self,
        activity_id: str,
        kind: str,
        status: str,
        key: str | None,
        *,
        count: int | None = None,
        duration_ms: int | None = None,
    ) -> ActivityFrame:
        self._seq += 1
        return ActivityFrame(
            activity_id=activity_id, seq=self._seq, kind=kind, status=status, key=key,
            count=count, at=datetime.now(UTC).isoformat(), duration_ms=duration_ms,
        )

    def _start(self, kind: str, key: str | None) -> tuple[str, ActivityFrame]:
        self._count += 1
        activity_id = f"a{self._count}"
        self._active[activity_id] = (kind, key, time.monotonic())
        return activity_id, self._frame(activity_id, kind, STATUS_ACTIVE, key)

    def _settle(self, activity_id: str, status: str, key: str | None) -> ActivityFrame:
        kind, _, started = self._active.pop(activity_id)
        # 诚实耗时 (2026-09-25): the whisper shows only a GENUINE span.
        # Read / repair spans cover real server work (the query, the rework
        # loop) — honest. A read span's start is RE-ANCHORED at execute
        # entry by ReadExecuting (ADR-104 排序律 — ``_on_read_executing``),
        # so the measured span is the real work and the settled row's walk
        # key (settle − duration) lands after the waiter checkpoint.
        # Terminal-kind spans (draft / run) open at name_known, AFTER the
        # LLM already did the drafting — the measured ~1s is validation
        # noise that reads as a lie ("计划已起草 ·1s" after a 30s draft),
        # so those settles carry none.
        duration_ms = (
            max(0, int((time.monotonic() - started) * 1000))
            if kind in (KIND_READ, KIND_REPAIR)
            else None
        )
        frame = self._frame(activity_id, kind, status, key, duration_ms=duration_ms)
        # 落定即退役 (2026-09-28 用户拍板; 2026-09-29 扩到 run 跨度): a
        # draft/run span's settle rides the live wire (the row leaves the
        # now-line at the right beat) but NEVER persists — the docked plan
        # card / the start speech + run receipt IS the settled evidence, and
        # the hollow receipt rows (方案整理好了 / 改好了 / 已开工) retired
        # from the flow (the web timeline filters legacy rows). Explore
        # milestones append through their own seat (``explore_milestone``) —
        # they are born-completed count facts, untouched by this law.
        if kind not in (KIND_DRAFT, KIND_RUN):
            self._settled.append(frame)
        return frame

    @staticmethod
    def _done_key(kind: str, active_key: str | None) -> str | None:
        if kind == KIND_READ and active_key is not None:
            if active_key.startswith(_INSPECTING_PREFIX):
                return _INSPECTING_DONE_PREFIX + active_key[len(_INSPECTING_PREFIX):]
            # chat.explore.* (iter-2 ⑥): the done mirror is the same key +
            # "Done" (searching → searchingDone) — the family's own law.
            assert active_key.startswith(_EXPLORE_PREFIX)
            return active_key + "Done"
        if active_key == _EDIT_KEYS[0]:
            return _EDIT_KEYS[1]
        pair = _ACTIVITY_KEYS.get(kind)
        return pair[1] if pair else None

    def explore_milestone(self, key: str, *, count: int) -> ActivityFrame:
        """One work-session milestone frame (iter-2 ⑥, N-57): fired at the
        exploration door's successes — BORN-COMPLETED (a milestone is a
        fact, never an in-progress span, so it never joins ``_active`` and
        the terminal sweep has nothing to settle). ``count`` is the only
        payload (Activity 十规则 — the whitelist's one extension)."""
        assert key in _EXPLORE_MILESTONE_KEYS, f"unknown explore milestone {key!r}"
        self._count += 1
        frame = self._frame(
            f"a{self._count}", KIND_DRAFT, STATUS_COMPLETED, key, count=count
        )
        self._settled.append(frame)
        return frame

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
            else _active_key_for(kind, tool_name)
        )
        activity_id, frame = self._start(kind, key)
        self._open_call = (tool_name, activity_id)
        return [frame]

    def feed_event(self, event: LoopEvent) -> list[ActivityFrame]:
        """The typed loop-event seam (U1)."""
        if isinstance(event, ToolRejected):
            return self._on_rejection(event)
        if isinstance(event, ReadExecuting):
            self._on_read_executing()
            return []
        if isinstance(event, (ReadAccepted, TerminalAccepted)):
            return self._on_accepted(event)
        if isinstance(event, LoopExhausted):
            return self._on_exhausted()
        raise AssertionError(f"unknown loop event: {event!r}")  # exhaustive union

    def _open_repair_span(self) -> None:
        """Open (or keep) the ONE aggregated repair span — SILENTLY (the
        visibility law): the span is tracked like any activity (T16's
        internal state holds — the retry window is work in flight) but its
        active frame never streams; the terminal decides what, if anything,
        the user ever sees of it."""
        if self._repair_id is None:
            self._count += 1
            self._repair_id = f"a{self._count}"
            self._active[self._repair_id] = (
                KIND_REPAIR,
                _ACTIVITY_KEYS[KIND_REPAIR][0],
                time.monotonic(),
            )

    def _close_repair_silently(self) -> None:
        """Settle the repair span with zero trace (the judgment tree's
        silent branches): no frame, no durable history — nothing was
        publicly committed, so nothing needs accounting."""
        if self._repair_id is not None:
            self._active.pop(self._repair_id, None)
            self._repair_id = None
        self._repair_rejected = []

    def _on_rejection(self, event: ToolRejected) -> list[ActivityFrame]:
        """拒绝当时: cancel the call's half-started activity (if the
        name-known beat started one), open/keep the ONE repair span
        SILENTLY, and record the forensic fact."""
        frames: list[ActivityFrame] = []
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None:
                kind, key, _started = self._active[activity_id]
                frames.append(self._settle(activity_id, STATUS_CANCELLED, key))
            self._open_call = None
        self._open_repair_span()
        self._repair_rejected.append(event.tool_name)
        self._rejections.append(
            {
                "tool_name": event.tool_name,
                "kind": event.kind,
                "iteration": event.iteration,
                "detail": event.detail,
                "duration_ms": event.duration_ms,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        return frames

    def _on_accepted(self, event: ReadAccepted | TerminalAccepted) -> list[ActivityFrame]:
        """An accepted call closes the open repair span FIRST (the rework
        resolved), then completes the call's own activity. The repair
        span's close follows the visibility law's judgment tree: a READ
        close and a 同形 terminal close stay silent; a provable redirection
        (实质工作变化) earns ONE born-terminal completed frame saying the
        work change."""
        frames: list[ActivityFrame] = []
        if self._repair_id is not None:
            redirected = (
                isinstance(event, TerminalAccepted)
                and self._repair_rejected  # a span always has ≥1, defensive
                and all(name is not None for name in self._repair_rejected)
                and event.tool_name not in self._repair_rejected
            )
            if redirected:
                frames.append(
                    self._settle(
                        self._repair_id,
                        STATUS_COMPLETED,
                        _ACTIVITY_KEYS[KIND_REPAIR][1],
                    )
                )
                self._repair_id = None
                self._repair_rejected = []
            else:
                self._close_repair_silently()
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None:
                kind, key, _started = self._active[activity_id]
                if (
                    isinstance(event, ReadAccepted)
                    and not event.ok
                    and kind == KIND_READ
                    and key is not None
                    and key.startswith(_INSPECTING_PREFIX)
                ):
                    # 失败帧 (ADR-102 §5): the read's target is unreadable —
                    # settle FAILED with the failed-form mirror, never the
                    # done family's lie.
                    frames.append(
                        self._settle(
                            activity_id,
                            STATUS_FAILED,
                            _INSPECTING_FAILED_PREFIX + key[len(_INSPECTING_PREFIX):],
                        )
                    )
                else:
                    frames.append(
                        self._settle(activity_id, STATUS_COMPLETED, self._done_key(kind, key))
                    )
            self._open_call = None
        return frames

    def _on_read_executing(self) -> None:
        """读活开工戳 (ADR-104 排序律): re-anchor the open read span's
        honest-duration start at execute entry. name_known births the span
        mid-generation (liveness); anchoring the duration THERE would make
        the settled row's walk key (close − duration) precede the waiter
        checkpoint's created_at and invert the 服务员话 → 读活动 → 读后回复
        order at settle time. Emitted after the checkpoint seat, before
        execute — sequential same-process stamps."""
        if self._open_call is None:
            return
        _name, activity_id = self._open_call
        if activity_id is None or activity_id not in self._active:
            return
        kind, key, _started = self._active[activity_id]
        self._active[activity_id] = (kind, key, time.monotonic())

    def _fail_repair(self) -> ActivityFrame | None:
        """The repair span's honest failure terminal (LoopExhausted / a
        failed turn's sweep): ONE born-terminal FAILED frame — the rework
        did not land, the ✗ and the real elapsed say so."""
        if self._repair_id is None:
            return None
        frame = self._settle(
            self._repair_id, STATUS_FAILED, _ACTIVITY_KEYS[KIND_REPAIR][0]
        )
        self._repair_id = None
        self._repair_rejected = []
        return frame

    def _on_exhausted(self) -> list[ActivityFrame]:
        """The honest-degradation fact: the repair span FAILED (never swept
        to completed by the cannot-do envelope — T5/T15)."""
        frames: list[ActivityFrame] = []
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None:
                kind, key, _started = self._active[activity_id]
                frames.append(self._settle(activity_id, STATUS_CANCELLED, key))
            self._open_call = None
        failed = self._fail_repair()
        if failed is not None:
            frames.append(failed)
        return frames

    def sweep(self, outcome: str) -> list[ActivityFrame]:
        """The envelope's closing sweep (终帧律的活动同形 — T16-B): anything
        still active when the turn ends is settled NOW. A still-open repair
        span follows the visibility law: a COMPLETED turn (the retry ended
        in a bare reply — the reply IS the final form) closes it SILENTLY;
        a FAILED turn fails it explicitly (the honest failure evidence).
        Other still-active spans settle as before — ``completed`` on a
        completed turn, ``failed`` on a failed turn. After the sweep, zero
        activities are active, structurally."""
        status = STATUS_COMPLETED if outcome == "completed" else STATUS_FAILED
        frames: list[ActivityFrame] = []
        if self._repair_id is not None:
            if status == STATUS_COMPLETED:
                self._close_repair_silently()
            else:
                failed = self._fail_repair()
                if failed is not None:
                    frames.append(failed)
        if self._open_call is not None:
            _name, activity_id = self._open_call
            if activity_id is not None and activity_id in self._active:
                kind, key, _started = self._active[activity_id]
                frames.append(
                    self._settle(
                        activity_id,
                        status,
                        self._done_key(kind, key) if status == STATUS_COMPLETED else key,
                    )
                )
            self._open_call = None
        return frames

    def open_activity(self) -> tuple[str, str, str | None] | None:
        """The open call's in-flight activity as (activity_id, kind, key) —
        the row-append seat's descriptor (ADR-108 §2): the SSE route appends
        the read span's array row at EXECUTE ENTRY (ReadExecuting), never at
        name_known — appending at name_known would seat the row BEFORE the
        waiter checkpoint's row and invert 服务员话 → 读活动 的数组序."""
        if self._open_call is None:
            return None
        _name, activity_id = self._open_call
        if activity_id is None or activity_id not in self._active:
            return None
        kind, key, _started = self._active[activity_id]
        return (activity_id, kind, key)

    def has_active(self) -> bool:
        return bool(self._active)

    def settled_frames(self) -> list[ActivityFrame]:
        """The turn's durable activity history (2026-09-25 activity 持久化):
        every frame that reached a terminal state, in emission (seq) order.
        Read it AFTER the envelope sweep — the 终帧律 guarantees zero active
        at that point, so the list is the complete settled story. Active
        frames never join (the live wire owns the in-flight face; only the
        settled form is durable)."""
        return list(self._settled)

    def rejected_calls(self) -> list[dict]:
        """The turn's rejection forensic ledger (rejection 取证批): every
        rejected call as {tool_name, kind, iteration, detail, duration_ms,
        at} — plain loop facts for after-the-fact audit, persisted beside
        the settled frames. Independent of the visibility law: a
        silently-closed repair span still leaves its rejections on the
        record."""
        return list(self._rejections)


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
    "frame_persistence",
    "kind_for_tool",
]
