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
from pathlib import Path

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
