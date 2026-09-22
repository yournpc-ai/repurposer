"""Pure tests for the Agent Activity Projection (ADR-087 §3 — Phase 2).

No DB, no LLM, no HTTP. The matrix is the Phase 2 brief's §Preflight P6
(T1~T16, with T16 split into the 2026-09-19 ruled double invariant) locked
against ``ActivityProjector`` — internal loop events in, user-safe frames
out. The two frozen invariants made executable:

- T16-A (blind window): while the turn has work in flight, the projection
  always has something user-visible active (an active activity) — the
  invariant's projector half (the prose half lives client-side).
- T16-B (liveness): every active activity reaches an explicit terminal
  (completed / failed / cancelled), and after the envelope sweep zero
  activities are active — a dangling activity is structurally impossible.

Plus the contract pins: deterministic ordering (T12/T13), the no-leak
field whitelist (T11), N→1 repair aggregation (T4), 1→0 filtering
(T6/T10), and the U6 single-owner gate (T17: every declared tool name
lands in exactly one bucket).
"""

import ast
import asyncio
import json
from pathlib import Path

import pytest

from app.agents.tool_loop import (
    LoopExhausted,
    ReadAccepted,
    TerminalAccepted,
    ToolRejected,
)
from app.chat.activity import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    ActivityProjector,
    all_known_tool_names,
    kind_for_tool,
)
from app.chat.perception import PERCEPTION_TOOLS
from app.chat.turn_tools import CHAT_READ_TOOLS, CHAT_TOOLS, PLAN_READ_TOOLS, PLAN_TOOLS

MUSIC = "chat.inspecting.music"
MUSIC_DONE = "chat.inspectingDone.music"
ASSET = "chat.inspecting.asset"
ASSET_DONE = "chat.inspectingDone.asset"
DRAFT = "chat.activity.draft"
DRAFT_DONE = "chat.activity.draftDone"
RUN = "chat.activity.run"
RUN_DONE = "chat.activity.runDone"
REPAIR = "chat.activity.repair"
REPAIR_DONE = "chat.activity.repairDone"


def _summary(frames):
    """Frames as comparable tuples: (activity_id, seq, kind, status, key)."""
    return [(f.activity_id, f.seq, f.kind, f.status, f.key) for f in frames]


def _feed(p: ActivityProjector, *events) -> list:
    """Feed a full sequence, collecting every frame."""
    out = []
    for e in events:
        if isinstance(e, str):  # a bare string = the name-known beat
            out.extend(p.name_known(e))
        else:
            out.extend(p.feed_event(e))
    return out


# T1 — a single read: started at name-known, completed at the accept.
def test_t1_single_read_lifecycle():
    p = ActivityProjector()
    frames = _feed(p, "search_music", ReadAccepted("search_music"))
    assert _summary(frames) == [
        ("a1", 1, "read", STATUS_ACTIVE, MUSIC),
        ("a1", 2, "read", STATUS_COMPLETED, MUSIC_DONE),
    ]


# T2 — two reads chain: distinct identities, order = event order.
def test_t2_two_reads_ordered():
    p = ActivityProjector()
    frames = _feed(
        p,
        "search_music", ReadAccepted("search_music"),
        "get_asset", ReadAccepted("get_asset"),
    )
    assert _summary(frames) == [
        ("a1", 1, "read", STATUS_ACTIVE, MUSIC),
        ("a1", 2, "read", STATUS_COMPLETED, MUSIC_DONE),
        ("a2", 3, "read", STATUS_ACTIVE, ASSET),
        ("a2", 4, "read", STATUS_COMPLETED, ASSET_DONE),
    ]


# T3 — a read rejected at params validation AFTER its name-known frame:
# the read is cancelled (explicit terminal), the repair span opens.
def test_t3_read_rejected_after_name_known():
    p = ActivityProjector()
    frames = _feed(p, "get_asset", ToolRejected("params_validation", "get_asset"))
    assert _summary(frames) == [
        ("a1", 1, "read", STATUS_ACTIVE, ASSET),
        ("a1", 2, "read", STATUS_CANCELLED, ASSET),
        ("a2", 3, "repair", STATUS_ACTIVE, REPAIR),
    ]


# T4 — two rejections then an accept aggregate into ONE repair span (N→1).
def test_t4_repair_aggregation():
    p = ActivityProjector()
    frames = _feed(
        p,
        "present_plan", ToolRejected("params_validation", "present_plan"),
        "present_plan", ToolRejected("execute_guardrail", "present_plan"),
        "present_plan", TerminalAccepted("present_plan"),
    )
    assert _summary(frames) == [
        ("a1", 1, "draft", STATUS_ACTIVE, DRAFT),
        ("a1", 2, "draft", STATUS_CANCELLED, DRAFT),
        ("a2", 3, "repair", STATUS_ACTIVE, REPAIR),
        ("a3", 4, "draft", STATUS_ACTIVE, DRAFT),
        ("a3", 5, "draft", STATUS_CANCELLED, DRAFT),
        ("a4", 6, "draft", STATUS_ACTIVE, DRAFT),
        ("a2", 7, "repair", STATUS_COMPLETED, REPAIR_DONE),  # repair closes FIRST
        ("a4", 8, "draft", STATUS_COMPLETED, DRAFT_DONE),
    ]


# T5 — exhaustion fails the repair span explicitly (never swept completed).
def test_t5_exhausted_fails_repair():
    p = ActivityProjector()
    frames = _feed(
        p,
        "present_plan", ToolRejected("params_validation", "present_plan"),
        LoopExhausted(iterations=6),
    )
    assert _summary(frames)[-1] == ("a2", 4, "repair", STATUS_FAILED, REPAIR)
    assert not p.has_active()


# T6 — a bare-reply turn emits zero activity frames (1→0 is legal).
def test_t6_bare_reply_zero_frames():
    p = ActivityProjector()
    assert _feed(p) == []
    assert p.sweep("completed") == []


# T7 — a plan-shaped call: active at name-known, completed at the accept.
def test_t7_draft_lifecycle():
    p = ActivityProjector()
    frames = _feed(p, "propose_tasks", TerminalAccepted("propose_tasks"))
    assert _summary(frames) == [
        ("a1", 1, "draft", STATUS_ACTIVE, DRAFT),
        ("a1", 2, "draft", STATUS_COMPLETED, DRAFT_DONE),
    ]


# T8 — start_run: the run-birth span.
def test_t8_run_lifecycle():
    p = ActivityProjector()
    frames = _feed(p, "start_run", TerminalAccepted("start_run"))
    assert _summary(frames) == [
        ("a1", 1, "run", STATUS_ACTIVE, RUN),
        ("a1", 2, "run", STATUS_COMPLETED, RUN_DONE),
    ]


# T9 — the terminal sweep: a failed turn fails what is still active; a
# completed turn completes it (the bare-reply-after-rejection case).
def test_t9_envelope_sweep():
    p = ActivityProjector()
    _feed(p, "present_plan", ToolRejected("params_validation", "present_plan"))
    frames = p.sweep("completed")  # the retry answered with bare prose
    assert _summary(frames) == [("a2", 4, "repair", STATUS_COMPLETED, REPAIR_DONE)]
    assert not p.has_active()

    p2 = ActivityProjector()
    _feed(p2, "search_music")  # stream died mid-read
    frames2 = p2.sweep("failed")
    assert _summary(frames2) == [("a1", 2, "read", STATUS_FAILED, MUSIC)]
    assert not p2.has_active()


# T10 — filtering (1→0): conversation-layer calls and unknown names open
# nothing; their acceptance still closes an open repair span.
def test_t10_conversation_calls_filtered():
    p = ActivityProjector()
    frames = _feed(p, "ask_user", TerminalAccepted("ask_user"))
    assert frames == []

    p2 = ActivityProjector()
    frames2 = _feed(
        p2,
        ToolRejected("schema_truncation", None),  # truncation: name unknown
        "answer", TerminalAccepted("answer"),
    )
    assert _summary(frames2) == [
        ("a1", 1, "repair", STATUS_ACTIVE, REPAIR),
        ("a1", 2, "repair", STATUS_COMPLETED, REPAIR_DONE),
    ]


# T11 — the no-leak whitelist: every frame's dict touches exactly the five
# contracted fields, whatever the event sequence.
def test_t11_frame_field_whitelist():
    p = ActivityProjector()
    frames = _feed(
        p,
        "get_understanding", ReadAccepted("get_understanding"),
        "present_plan", ToolRejected("execute_guardrail", "present_plan"),
        "propose_tasks", TerminalAccepted("propose_tasks"),
    ) + p.sweep("completed")
    for f in frames:
        assert set(f.to_dict()) == {"activity_id", "seq", "kind", "status", "key"}
        assert f.kind in ("read", "draft", "run", "repair")
        assert f.status in (STATUS_ACTIVE, STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED)
        assert f.key is None or f.key.startswith(("chat.inspecting", "chat.activity."))


# T12 — determinism: the same event sequence yields the byte-same frames.
def test_t12_determinism():
    seq = (
        "search_music", ReadAccepted("search_music"),
        "present_plan", ToolRejected("params_validation", "present_plan"),
        "present_plan", TerminalAccepted("present_plan"),
    )
    a = _summary(_feed(ActivityProjector(), *seq))
    b = _summary(_feed(ActivityProjector(), *seq))
    assert a == b


# T13 — ordering stability: seq strictly increases across any interleaving.
def test_t13_sequence_monotonic():
    p = ActivityProjector()
    frames = _feed(
        p,
        "search_music", ReadAccepted("search_music"),
        ToolRejected("schema_truncation", None),
        "edit_graph", TerminalAccepted("edit_graph"),
    ) + p.sweep("completed")
    seqs = [f.seq for f in frames]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


# T15 — flagship negative: reject → retry → reject → exhaust. The repair
# span gets exactly one active start and exactly one failed terminal; never
# two actives, never dangling.
def test_t15_flagship_repair_exhaustion():
    p = ActivityProjector()
    frames = _feed(
        p,
        "present_plan", ToolRejected("params_validation", "present_plan"),
        "present_plan", ToolRejected("execute_guardrail", "present_plan"),
        LoopExhausted(iterations=6),
    )
    assert p.sweep("completed") == []  # nothing left for the envelope
    repair_frames = [f for f in frames if f.kind == "repair"]
    assert _summary(repair_frames) == [
        ("a2", 3, "repair", STATUS_ACTIVE, REPAIR),
        ("a2", 6, "repair", STATUS_FAILED, REPAIR),
    ]
    assert not p.has_active()


# T16-B — liveness: WHATEVER the event sequence, after the envelope sweep
# zero activities are active (the dangling-activity impossibility).
def test_t16b_no_dangling_after_sweep():
    scenarios = [
        ("search_music",),
        ("present_plan",),
        ("start_run",),
        (ToolRejected("schema_truncation", None),),
        ("get_asset", ToolRejected("params_validation", "get_asset"), "search_music"),
        ("search_music", ReadAccepted("search_music"), "present_plan"),
    ]
    for seq in scenarios:
        for outcome in ("completed", "failed"):
            p = ActivityProjector()
            _feed(p, *seq)
            p.sweep(outcome)
            assert not p.has_active(), f"dangling after {seq} / {outcome}"


# T16-A (projector half) — while a tool call's work is in flight the
# projection has an active activity; a rejection keeps one (repair) alive.
def test_t16a_work_in_flight_always_visible():
    p = ActivityProjector()
    p.name_known("present_plan")
    assert p.has_active()  # the draft span covers the dock-work window
    p.feed_event(ToolRejected("execute_guardrail", "present_plan"))
    assert p.has_active()  # the repair span covers the retry window


# T14 — phase coexistence is structural: the projector never sees the
# phase channel at all (its inputs are name-known + LoopEvent only), so a
# turn with the projector emits phase frames identically to one without —
# pinned here as "the projector's API surface carries no phase concept".
def test_t14_projector_has_no_phase_surface():
    assert not hasattr(ActivityProjector, "on_phase")
    assert "phase" not in ActivityProjector.__dict__.get("__annotations__", {})


# The dropped-parallel-call mirror: extra name-knowns while a call slot is
# open are ignored (the loop executes call[0] only).
def test_extra_name_known_while_open_ignored():
    p = ActivityProjector()
    frames = _feed(p, "search_music", "get_asset", ReadAccepted("search_music"))
    assert _summary(frames) == [
        ("a1", 1, "read", STATUS_ACTIVE, MUSIC),
        ("a1", 2, "read", STATUS_COMPLETED, MUSIC_DONE),
    ]


# ---- iter-2 ⑥: the work-session family (chat.explore.*, N-57) ------------------

SEARCHING = "chat.explore.searching"
SEARCHING_DONE = "chat.explore.searchingDone"


def test_explore_read_done_key_is_same_family():
    """search_transcript re-homed (改籍): the read frame rides the
    work-session vocabulary and its done mirror is key + "Done" (the
    family's own law — never the inspectingDone prefix swap)."""
    p = ActivityProjector()
    frames = _feed(p, "search_transcript", ReadAccepted("search_transcript"))
    assert _summary(frames) == [
        ("a1", 1, "read", STATUS_ACTIVE, SEARCHING),
        ("a1", 2, "read", STATUS_COMPLETED, SEARCHING_DONE),
    ]


def test_explore_milestone_is_born_completed_with_count():
    """A milestone is a fact: one completed frame straight from the door
    success — never an active span, so the sweep has nothing to settle and
    the whitelist's one extension (count) rides the wire."""
    p = ActivityProjector()
    frame = p.explore_milestone("chat.explore.candidatesReady", count=5)
    assert frame.kind == "draft"
    assert frame.status == STATUS_COMPLETED
    assert frame.key == "chat.explore.candidatesReady"
    assert frame.count == 5
    assert frame.to_dict()["count"] == 5
    assert not p.has_active()
    # The sweep settles nothing (the milestone never opened a span).
    assert p.sweep("completed") == []


def test_explore_milestone_key_whitelist():
    """Only the three registered milestone keys fire (N-57 词表)."""
    p = ActivityProjector()
    for key in (
        "chat.explore.candidatesReady",
        "chat.explore.selectsReady",
        "chat.explore.plansReady",
    ):
        assert p.explore_milestone(key, count=1).key == key
    with pytest.raises(AssertionError):
        p.explore_milestone("chat.explore.madeUp", count=1)


def test_frame_count_absent_off_the_wire_otherwise():
    """读容忍/白名单纪律: non-milestone frames never carry the count key."""
    p = ActivityProjector()
    frames = _feed(p, "search_music", ReadAccepted("search_music"))
    assert all("count" not in f.to_dict() for f in frames)


def test_exploration_verbs_open_no_per_call_activity():
    """The exploration verbs' user face is the milestone frame + the canvas
    card + the dock (1→0 同律) — name-known opens nothing, and their
    rejections still count as repair work."""
    p = ActivityProjector()
    assert _feed(p, "propose_candidates") == []
    # A rejected exploration call opens the aggregated repair span.
    frames = _feed(p, "propose_plans", ToolRejected("params_validation", "propose_plans"))
    assert _summary(frames) == [("a1", 1, "repair", STATUS_ACTIVE, REPAIR)]
    # Every exploration verb classifies (T17's bucket law).
    for name in ("propose_candidates", "propose_selects", "propose_plans"):
        assert name in all_known_tool_names()
        assert kind_for_tool(name) is None


# T17 — U6 single-owner gate: every declared tool name (terminal sets +
# perception reads) classifies into exactly one bucket, and the projector
# knows every declared name.
def test_t17_every_declared_tool_classified():
    declared = {
        t.name for t in (*PLAN_TOOLS, *CHAT_TOOLS, *PLAN_READ_TOOLS, *CHAT_READ_TOOLS)
    } | set(PERCEPTION_TOOLS)
    known = all_known_tool_names()
    assert declared <= known, f"undeclared-to-projector tools: {declared - known}"
    # The kind mapping covers exactly the work kinds; conversation tools
    # classify to None by design.
    kinds = {name: kind_for_tool(name) for name in declared}
    assert kinds["ask_user"] is None and kinds["answer"] is None
    assert kinds["start_run"] == "run"
    assert kinds["present_plan"] == "draft"
    assert kinds["search_music"] == "read"


# Static audit (验收标准「grep 可证」落形): the projection module reads no
# Domain — no models / pipeline / db imports in its own source.
def test_activity_module_is_read_only_projection():
    tree = ast.parse(
        Path("app/chat/activity.py").read_text()  # run from apps/api
        if Path("app/chat/activity.py").exists()
        else Path(__file__).parents[1].joinpath("app/chat/activity.py").read_text()
    )
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    banned = [m for m in imported if m.startswith(("app.models", "app.pipeline", "sqlalchemy"))]
    assert not banned, f"Activity Projection must stay read-only, imports: {banned}"


# ---- Phase 2.5 Batch B-3: the route seam at stub level ----------------------
# The projector's laws are locked above; these tests pin the WIRE seam in
# app/chat/routes.py — _make_loop_event_hook (internal LoopEvents → queued
# user-safe frames) and _sweep_activities (T16-B's terminal cleanup) — with
# nothing but an asyncio.Queue, so the seam's contract is covered without a
# live turn.

from app.chat.routes import (  # noqa: E402  (after the pure projector block)
    _activity_frame,
    _make_loop_event_hook,
    _sweep_activities,
)


def _wire(queue: asyncio.Queue) -> list[tuple[str, dict]]:
    """Drain the stub queue into (event, payload) pairs."""
    out = []
    while not queue.empty():
        raw = queue.get_nowait()
        event_line, data_line = raw.splitlines()[:2]
        out.append((event_line.removeprefix("event: "),
                    json.loads(data_line.removeprefix("data: "))))
    return out


@pytest.mark.asyncio
async def test_route_seam_rejection_then_failed_sweep():
    """cancelled + failed across the seam: the name-known beat queues the
    active frame; the rejection cancels the half-started draft (active key
    kept) and opens the ONE repair span; the failed turn's sweep settles the
    repair FAILED. Zero active survives; every frame rides the
    assistant.activity event with the exact whitelist payload."""
    queue: asyncio.Queue = asyncio.Queue()
    p = ActivityProjector()
    hook = _make_loop_event_hook(queue, p)
    for f in p.name_known("present_plan"):
        await queue.put(_activity_frame(f))
    await hook(ToolRejected(kind="params_validation", tool_name="present_plan"))
    await _sweep_activities(queue, p, "failed")
    wire = _wire(queue)
    assert all(event == "assistant.activity" for event, _ in wire)
    assert [
        (d["activity_id"], d["kind"], d["status"], d["key"]) for _, d in wire
    ] == [
        ("a1", "draft", "active", DRAFT),
        ("a1", "draft", "cancelled", DRAFT),  # rejection → cancelled, key kept
        ("a2", "repair", "active", REPAIR),
        ("a2", "repair", "failed", REPAIR),  # failed turn sweeps repair FAILED
    ]
    for _, payload in wire:
        assert set(payload.keys()) == {"activity_id", "seq", "kind", "status", "key"}
    assert not p.has_active()


@pytest.mark.asyncio
async def test_route_seam_completed_sweep_settles_every_active():
    """The completed-turn sweep with TWO actives open (a repair span from a
    nameless truncation + an in-flight read): both settle COMPLETED in one
    sweep — repair first (span ordering), past-tense keys on the wire, zero
    dangling."""
    queue: asyncio.Queue = asyncio.Queue()
    p = ActivityProjector()
    hook = _make_loop_event_hook(queue, p)
    await hook(ToolRejected(kind="schema_truncation", tool_name=None))
    for f in p.name_known("search_music"):
        await queue.put(_activity_frame(f))
    await _sweep_activities(queue, p, "completed")
    wire = _wire(queue)
    assert [
        (d["activity_id"], d["kind"], d["status"], d["key"]) for _, d in wire
    ] == [
        ("a1", "repair", "active", REPAIR),
        ("a2", "read", "active", MUSIC),
        ("a1", "repair", "completed", REPAIR_DONE),
        ("a2", "read", "completed", MUSIC_DONE),
    ]
    assert not p.has_active()
