"""R2-B wiring tests — the film edit path's chat integration (stub DB, real
edit core + real validator; no LLM, no HTTP, no real DB).

The covered laws (设计 = docs/tasks/film-storyboard-orchestration.md §7.2):

1. **base 引用协议** — the stale-edit integration proof (read v1 → the live
   version moved to v2 → ops minted against v1 reject, v2 byte-untouched,
   the begin marker never written); the explicit @output pin on an OLD
   version branches from THAT version (永不静默换最新版); the commit-time
   recheck discards a patch whose live-pending base moved mid-flight.
2. **闸 2** — the patch path burns ZERO director/orchestration calls (the
   compose seats are patched to raise; the patch still lands).
3. **结构化拒绝** — unchanged / validation_failed / unknown ops echo a
   repair text into the loop (never a director re-design, never a 500), the
   draft marker clears, no version persists.
4. **授权 (ADR-134 修订)** — film_design_state's hold matrix: compose fresh
   defaults ON; patch adds no NEW hold and never releases a standing one as
   a side effect; the explicit param is the two-way escape door.
5. **报价分叉** — a versioned board quotes its ACTUAL seconds + full
   narration chars (interim = full re-synthesis, no reuse pre-claim).
6. **呈现契约** — the observation carries the system-computed change
   summary, the shared FULL current-version fact sheet and the next
   version's base_ref; the patched version's fingerprint recomputes equal
   at the approval dock (reuse, never a redraft).
7. **冻结时间轴 = 版本状态** — the established cut inherits across
   timeline-preserving edits (never keyed on this batch naming set_music);
   a structural change or a surviving recut re-establishes it fresh; an
   EXECUTED base whose spec is missing/corrupt (cut_state "unreadable")
   refuses timeline-keeping edits structurally — never a silent recompute.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import (
    DesignStoryboardArgs,
    FilmStoryboard,
    PendingPlan,
    WebPageResearch,
)
from app.tools.film.edits import (
    change_set_presentation,
    film_base_cut,
    film_edit_repair_echo,
    film_version_identity_digest,
)
from app.tools.film.storyboard import (
    DockStoryboard,
    build_film_execution_snapshot,
    canonical_film_params,
    execution_frames,
    film_design_state,
    storyboard_content_digest,
    storyboard_fingerprint,
)
from app.tools.film.storyboard import StoryboardPage

# ---------------------------------------------------------------------------
# Fixtures — a compliant board (real validator passes it) + its page world
# ---------------------------------------------------------------------------

_URL = "https://example.com/product"


def _page() -> StoryboardPage:
    research = WebPageResearch(
        url=_URL,
        title="Acme — Ship faster",
        description="Acme turns hours of release work into minutes.",
        h1=["Ship faster"],
        h2=["Why teams switch"],
        h3=[],
        buttons=["Start free"],
        links=["Docs"],
    )
    return StoryboardPage(
        asset_id="a1",
        research=research,
        screenshot_key="user/capture/shot.png",
        host="example.com",
        shots=(),
    )


def _board_scenes() -> list[dict]:
    """14 scenes ≈ 81s, grounded copy (the validator's window: 8..20 scenes,
    70..118s). No scene_ids — the legacy persisted shape; ensure/identity
    seats derive them positionally (s1..s14)."""
    return [
        {"type": "words", "seconds": 4.0, "dark": True, "lines": ["Ship faster"]},
        {"type": "hero", "seconds": 5.0, "word": "Ship faster",
         "sub": "Acme turns hours of release work into minutes.",
         "narration": "Meet Acme."},
        {"type": "ui", "seconds": 9.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}],
         "narration": "The dashboard does the work."},
        {"type": "divider", "seconds": 3.0, "label": "Why teams switch",
         "roll": ["Ship faster", "Start free"]},
        {"type": "ui", "seconds": 9.0, "page": 0, "frame": False,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}],
         "narration": "Why teams switch, in one walk."},
        {"type": "reveal", "seconds": 9.0, "lead": "One more thing.",
         "word": "Acme", "sub": "Start free", "lead_seconds": 4.5},
        {"type": "end", "seconds": 5.0, "name": "Acme", "tagline": "Ship faster",
         "narration": "Ship faster."},
        {"type": "words", "seconds": 4.0, "dark": True, "lines": ["pad one"]},
        {"type": "words", "seconds": 4.0, "dark": False, "lines": ["pad two"]},
        {"type": "words", "seconds": 4.0, "dark": True, "lines": ["pad three"]},
        {"type": "reveal", "seconds": 9.0, "lead": "Again.", "word": "Start free",
         "sub": "Why teams switch", "lead_seconds": 4.5},
        {"type": "hero", "seconds": 6.0, "word": "Acme", "sub": "Why teams switch"},
        {"type": "words", "seconds": 4.0, "dark": False, "lines": ["pad four"]},
        {"type": "end", "seconds": 6.0, "name": "Acme", "tagline": "Why teams switch"},
    ]


_PARAMS = {"focus": "product story", "language": "en", "aspect": "16:9"}


def _board(**over) -> FilmStoryboard:
    return FilmStoryboard.model_validate({"scenes": _board_scenes(), **over})


def _base_ref(
    board: FilmStoryboard, params: dict, *, version: int, cut=None
) -> str:
    return film_version_identity_digest(board, params, version=version, cut=cut)


def _pending_with_film(
    board: FilmStoryboard,
    params: dict,
    *,
    version: int,
    prompt: str = "给我做一支官网短片",
    hold: bool = True,
    token: str = "tok-live",
    track=None,
    kept_frames: list[int] | None = None,
    kept_reveal_onsets: list[int | None] | None = None,
) -> dict:
    return PendingPlan(
        prompt=prompt,
        film_storyboard=board.model_dump(mode="json"),
        film_storyboard_fingerprint=f"fp-v{version}",
        film_storyboard_version=version,
        film_storyboard_params=params,
        film_storyboard_content_digest=storyboard_content_digest(board),
        film_storyboard_execution=build_film_execution_snapshot(
            pages=[_page()], track=track
        ),
        film_review_hold=hold,
        film_draft_token=token,
        film_design_authorized_by="u1",
        film_kept_frames=kept_frames,
        film_kept_reveal_onsets=kept_reveal_onsets,
    ).model_dump(mode="json")


def _async_pages(pages):
    """A load_storyboard_pages-shaped stub (the read's page seat)."""

    async def _load(db, project):
        return pages

    return _load


def _provenance_base(
    board: FilmStoryboard, params: dict, *, version: int, cut_state=None,
    cut_reveal_onsets=None,
):
    """The resolve_film_revision_base-shaped namespace (run provenance)."""
    return SimpleNamespace(
        film_storyboard=board.model_dump(mode="json"),
        film_storyboard_fingerprint=f"fp-v{version}",
        film_storyboard_version=version,
        film_storyboard_params=params,
        film_storyboard_content_digest=storyboard_content_digest(board),
        film_storyboard_execution=build_film_execution_snapshot(
            pages=[_page()], track=None
        ),
        film_created_via="compose",
        film_base_version=None,
        film_change_set=None,
        film_cut_frames=None,
        film_cut_state=cut_state,
        film_cut_reveal_onsets=cut_reveal_onsets,
        film_constraints_choice=None,
        film_draft_token=None,
        film_draft_inflight=None,
        film_design_authorized_by=None,
        film_presented_message_id=None,
        film_review_hold=False,
    )


# ---------------------------------------------------------------------------
# Stub seats (DB session + the concurrency guards, recording variants)
# ---------------------------------------------------------------------------


class _StubDB:
    """The turn session stand-in: the authorizing-message lookup answers a
    fresh id; flush/refresh are no-ops (the marker seats are stubbed at
    their storyboard.py homes)."""

    async def execute(self, *args, **kwargs):
        return SimpleNamespace(scalar_one_or_none=lambda: uuid4())

    async def flush(self):
        return None

    async def refresh(self, *args):
        return None


_UNMOVED = object()  # the committed row IS the project's own live pending


class _GuardStubs:
    """Recording stubs for the begin/clear seats (patched onto
    app.tools.film.storyboard). The publish guard's committed-state read
    runs the REAL ``read_committed_film_state`` over a stubbed side session
    whose row carries ``committed`` (``_UNMOVED`` = the project's current
    pending — the world did not move) with THIS draft's marker injected
    (simulating our own begin's committed write)."""

    def __init__(self, *, marker_base_version=None, committed=_UNMOVED,
                 marker_started_at=None):
        self.begin_calls: list[dict] = []
        self.cleared: list[str] = []
        self.marker_base_version = marker_base_version
        self.committed = committed
        self.marker_started_at = marker_started_at
        self.marker_draft_id = "draft-test"  # flip to simulate a takeover
        self.project = None  # set by _patch_world

    async def begin(self, db, project, *, base_version, user_message_id):
        from app.tools.film.storyboard import FilmDraftBegin

        self.begin_calls.append({"base_version": base_version})
        return FilmDraftBegin(draft_id="draft-test")

    async def clear(self, db, project, *, draft_id):
        self.cleared.append(draft_id)

    def committed_row(self):
        raw = self.committed
        if raw is _UNMOVED:
            raw = self.project.pending_brief if self.project is not None else None
        if not isinstance(raw, dict):
            return raw
        pend = dict(raw)  # never mutate the project's own dict
        marker = {
            "draft_id": self.marker_draft_id,
            "base_version": self.marker_base_version,
        }
        if self.marker_started_at is not None:
            marker["started_at"] = self.marker_started_at
        pend["film_draft_inflight"] = marker
        return pend


def _patch_world(monkeypatch, guards: _GuardStubs, *, resolve_base=None,
                 project=None):
    """Wire the stub seats: marker machinery + revision-base resolution +
    the patch beat's DB dependencies (pages present, silent snapshot music).
    The committed-state read keeps its REAL seat — only the side session
    factory is stubbed, so the read's own extraction law stays under test.
    """
    import app.models.database as db_mod
    import app.tools.film.edits as edits_mod
    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "begin_film_draft", guards.begin)
    monkeypatch.setattr(sb_mod, "clear_film_draft_marker", guards.clear)
    guards.project = project

    class _CommittedSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, *args, **kwargs):
            pend = guards.committed_row()
            return SimpleNamespace(scalar_one_or_none=lambda: pend)

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _CommittedSession())
    if resolve_base is not None:
        monkeypatch.setattr(sb_mod, "resolve_film_revision_base", resolve_base)

    async def _pages(db, project):
        return [_page()]

    async def _no_track(db, project, params):
        return None

    monkeypatch.setattr(edits_mod, "load_storyboard_pages", _pages)
    monkeypatch.setattr(edits_mod, "film_snapshot_track", _no_track)


def _kill_switch(monkeypatch):
    """闸 2: every compose-side orchestration seat patched to raise — the
    patch path must never reach them."""
    import app.tools.film.storyboard as sb_mod

    async def _boom(*args, **kwargs):
        raise AssertionError("director/orchestration called on the patch path")

    monkeypatch.setattr(sb_mod, "prepare_dock_storyboard", _boom)
    monkeypatch.setattr(sb_mod, "orchestrate_storyboard", _boom)
    monkeypatch.setattr(
        sb_mod.film_director, "call", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("film_director.call on the patch path")
        )
    )


def _chat_turn(project, *, text="把第二章的旁白缩短一点", mentions=None):
    from app.chat.propose_turn import ChatTurn

    turn = ChatTurn.__new__(ChatTurn)
    turn.db = _StubDB()
    turn.user_id = uuid4()
    turn.conversation_id = uuid4()
    turn.project = project
    turn.text = text
    turn.on_phase = None
    turn.on_activity = None
    turn.on_candidates = None
    turn.on_row_append = None
    turn._presentation_pending = None
    turn._designed_this_turn = None
    turn._design_draft_id = None
    turn._design_begin_refusal = None
    turn._design_corrections = 0
    turn._design_shortfalls = []
    turn.pending = None
    turn.pending_judgable = False
    turn.context = {"text": ""}
    turn.mentions = mentions or []
    turn.settled_question = None
    turn.outcome = None
    turn._bailed_on_skip = []
    turn.deferred = None
    turn.suggestion_note = None
    return turn


def _edit_args(**kw) -> DesignStoryboardArgs:
    return DesignStoryboardArgs.model_validate(kw)


def _ledger_keys(turn) -> list[str]:
    """The shortfall ledger's mechanical keys (entries are
    ``design_call_record`` dicts — {key, target})."""
    return [e["key"] for e in turn._design_shortfalls]


def _plan_turn(project, *, text="换掉配乐"):
    """A PlanTurn mid-turn stand-in (the chat path's mirror — _chat_turn's
    plan-path twin)."""
    from app.chat.plan_turn import PlanTurn

    turn = PlanTurn.__new__(PlanTurn)
    turn.db = _StubDB()
    turn.user_id = uuid4()
    turn.conversation_id = uuid4()
    turn.project = project
    turn.request = SimpleNamespace(mentions=[], persona_id=None)
    turn.text = text
    turn.on_phase = None
    turn.on_activity = None
    turn.on_candidates = None
    turn.on_row_append = None
    turn._presentation_pending = None
    turn._designed_this_turn = None
    turn._design_draft_id = None
    turn._design_begin_refusal = None
    turn._design_corrections = 0
    turn._design_shortfalls = []
    turn.stored = None
    turn.mention_exemplar_id = None
    return turn


@pytest.fixture(autouse=True)
def _edits_gate_on(monkeypatch):
    """The edit capability's deployment gate (settings.film_edits_enabled)
    is ON for this suite — tests enable it explicitly; the production
    default is OFF. Gate-off tests re-set it to False locally (the last
    monkeypatch wins until teardown)."""
    monkeypatch.setattr("app.config.settings.film_edits_enabled", True)


# ---------------------------------------------------------------------------
# 1. base 引用协议 — the required integration proofs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_edit_rejects_and_the_live_version_stays_byte_identical(
    monkeypatch,
):
    """读取 v1 → 当前已更新为 v2 → 基于 v1 的 ops 必须拒绝，v2 字节不动."""
    v1 = _board()
    v2_scenes = _board_scenes()
    v2_scenes[1]["narration"] = "Meet the new Acme."  # content moved
    v2 = FilmStoryboard.model_validate({"scenes": v2_scenes})
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs()
    _patch_world(monkeypatch, guards, project=project)

    async def _patch_never_called(*args, **kwargs):
        raise AssertionError("prepare_film_patch reached on a stale base")

    import app.tools.film.edits as edits_mod

    monkeypatch.setattr(edits_mod, "prepare_film_patch", _patch_never_called)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "remove_scene", "scene_id": "s10"}],
            base_ref=_base_ref(v1, _PARAMS, version=1),  # minted against v1
        ),
        "",
    )
    assert isinstance(result, str)
    assert "moved since these edits were minted" in result
    assert "re-read" in result
    # v2 byte-identical, no marker was ever written, no draft cleared.
    assert project.pending_brief == pending_before
    assert guards.begin_calls == []
    assert guards.cleared == []


@pytest.mark.asyncio
async def test_pinned_old_output_branches_from_that_version(monkeypatch):
    """显式 @output 钉旧版本 = 以该版本为 base 的分支语义：live pending 是
    v3 也不静默换新版——patch 落在钉住的 v1 上，信封与 change_set 落库。"""
    v1 = _board()
    base = _provenance_base(v1, _PARAMS, version=1)
    base_dump_before = list(base.film_storyboard["scenes"])
    # A live pending at v3 EXISTS — the pin still wins (钉恒胜).
    pending_before = _pending_with_film(_board(), _PARAMS, version=3)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    output_id = uuid4()
    turn = _chat_turn(
        project, mentions=[SimpleNamespace(type="output", id=output_id)]
    )

    guards = _GuardStubs(
        marker_base_version=1  # committed world still holds the live v3 (UNMOVED)
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    _patch_world(monkeypatch, guards, resolve_base=_resolve, project=project)
    _kill_switch(monkeypatch)

    new_narration = "A tighter chapter walk."
    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {
                    "op": "update_scene",
                    "scene_id": "s5",
                    "narration": new_narration,
                }
            ],
            base_ref=_base_ref(v1, _PARAMS, version=1),
        ),
        "",
    )
    from app.agents.tool_loop import ToolObservation

    assert isinstance(result, ToolObservation), result
    # Branched lineage: v1 + 1 — never the live v3's line.
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 2
    assert pending.film_base_version == 1
    assert pending.film_created_via == "patch"
    assert pending.film_review_hold is False  # 授权已在场 (ADR-134 修订)
    assert pending.film_draft_token != "tok-live"  # fresh draft token
    # The change_set is the SYSTEM's diff: only s5's narration edited.
    change_set = pending.film_change_set
    assert change_set is not None
    assert change_set["edited"] == [
        {"scene_id": "s5", "fields": ["narration"], "notes": []}
    ]
    assert change_set["moved"] == [] and change_set["removed"] == []
    board = FilmStoryboard.model_validate(pending.film_storyboard)
    assert board.scenes[4].narration == new_narration
    # The untouched scenes' CONTENT stayed byte-identical to the base (构造
    # 保证); the derived scene_id (a handle, never content) is the one-time
    # legacy upgrade and rides along.
    def _content(dump: dict) -> dict:
        return {k: v for k, v in dump.items() if k != "scene_id"}

    for i, scene in enumerate(board.scenes):
        if i == 4:
            continue
        assert _content(scene.model_dump(mode="json")) == _content(base_dump_before[i])
    # The base object itself was never mutated.
    assert base.film_storyboard["scenes"] == base_dump_before
    # Fingerprint parity: the approval dock recomputes THIS key off the
    # version's canonical params + the FROZEN birth narrative (stored.prompt
    # wins over the turn's own words) → reuse, never redraft.
    assert pending.prompt == "给我做一支官网短片"
    assert pending.film_storyboard_fingerprint == storyboard_fingerprint(
        [{"tool": "launch_film", "params": pending.film_storyboard_params}],
        pending.prompt,
    )
    # The observation carries the computed delta, the FULL current fact
    # sheet, and the next base_ref — never a diff-only presentation.
    assert "PATCH of version 1" in result.text
    assert "edited — fields: narration" in result.text
    assert "FULL CURRENT SAVED BOARD" in result.text
    assert "scene 1" in result.text
    assert "never re-print the whole scene table" not in result.text
    next_ref = _base_ref(board, pending.film_storyboard_params, version=2)
    assert next_ref in result.text
    # 呈现挂号: finish will stamp the presentation's provenance.
    assert turn._presentation_pending == {"version": 2}
    # The marker machinery ran begin→publish, no clear.
    assert guards.begin_calls == [{"base_version": 1}]
    assert guards.cleared == []


@pytest.mark.asyncio
async def test_commit_time_recheck_discards_a_patch_whose_base_moved(
    monkeypatch,
):
    """并发回防: begin 之后 committed 版本从 v2 移到 v3 → patch 丢弃,
    pending 保持 v2 (in-memory 未动), 模型被告知重读."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(
        marker_base_version=2,
        committed=_pending_with_film(_board(), _PARAMS, version=3),
    )
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "remove_scene", "scene_id": "s10"}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "discarded" in result and "base_ref" in result
    assert project.pending_brief == pending_before
    # The discard RELEASES its own draft marker (never a leak that blocks
    # later edits / Start until the staleness sweep).
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_recut_only_new_version_invalidates_earlier_base_refs(
    monkeypatch,
):
    """R3c 评审 finding ③: 只重卡点的新版本（content/params 字节不动，仅
    version 前进）也必须让 v1 铸的 ref 快速拒绝——read 展示的冻结时间轴
    状态随版本移动，内容相同 ≠ base 相同."""
    v1 = _board()
    # A recut-only v2: the SAME board content and params, only the version moved.
    pending_before = _pending_with_film(v1, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs()
    _patch_world(monkeypatch, guards, project=project)

    async def _patch_never_called(*args, **kwargs):
        raise AssertionError("prepare_film_patch reached on a stale base")

    import app.tools.film.edits as edits_mod

    monkeypatch.setattr(edits_mod, "prepare_film_patch", _patch_never_called)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v1, _PARAMS, version=1),  # minted against v1
        ),
        "",
    )
    assert isinstance(result, str)
    assert "moved since these edits were minted" in result
    # The recut-only v2 stays byte-identical; no marker churn.
    assert project.pending_brief == pending_before
    assert guards.begin_calls == []
    assert guards.cleared == []


@pytest.mark.asyncio
async def test_provenance_base_publish_rechecks_a_committed_pending(
    monkeypatch,
):
    """R3c 评审 finding ④: base 从历史 run provenance 恢复（live pending 缺
    席）→ resolve 与 begin 之间另一个设计把 committed pending 推进到 v2 →
    publish 重检诚实丢弃本 patch（永不覆盖式版本），pending 保持无人在场."""
    v1 = _board()
    base = _provenance_base(v1, _PARAMS, version=1)
    project = SimpleNamespace(id=uuid4(), pending_brief={})  # 无 live pending
    turn = _chat_turn(project)

    guards = _GuardStubs(
        # 本 patch 的 begin 之后, committed pending 推进到 v2
        marker_base_version=1,
        committed=_pending_with_film(_board(), _PARAMS, version=2),
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    _patch_world(monkeypatch, guards, resolve_base=_resolve, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v1, _PARAMS, version=1),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "discarded" in result and "base_ref" in result
    assert project.pending_brief == {}  # 无 pending 被覆写
    assert guards.begin_calls == [{"base_version": 1}]
    # The discard releases its own marker (draft-scoped clear).
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_same_numbered_foreign_pending_discards_the_patch(monkeypatch):
    """复审遗留问题② + 全身份法: 版本号相同 ≠ 同一版本——base 从 provenance
    恢复 (v1, 读取时无 pending), resolve 与 begin 之间另一个设计提交了同为
    v1 但内容不同的 pending (分支同号异稿) → 发布重检按全身份识别异稿,
    诚实丢弃; 同号同稿同参数同冻结态 (字节级同一版本状态的再提交 — 「读取
    时无 pending、随后出现并发 pending」的唯一安全形) 照常发布."""
    v1 = _board()
    base = _provenance_base(v1, _PARAMS, version=1)
    project = SimpleNamespace(id=uuid4(), pending_brief={})
    turn = _chat_turn(project)

    foreign = _board()
    foreign.scenes[0].lines = ["a different opening"]  # 同号异内容
    guards = _GuardStubs(
        marker_base_version=1,
        # 与 base 同号 — 版本号比对看不出来; 内容 digest 才看出来
        committed=_pending_with_film(foreign, _PARAMS, version=1),
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    _patch_world(monkeypatch, guards, resolve_base=_resolve, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v1, _PARAMS, version=1),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "discarded" in result and "base_ref" in result
    assert project.pending_brief == {}
    assert guards.cleared == ["draft-test"]

    # 对照腿: 出现的 pending 与读取基准字节级同一版本状态 (同号同稿同参数
    # 同冻结态) — 世界未动, 照常发布.
    project2 = SimpleNamespace(id=uuid4(), pending_brief={})
    turn2 = _chat_turn(project2)
    guards2 = _GuardStubs(
        marker_base_version=1,
        committed=_pending_with_film(v1, _PARAMS, version=1),
    )
    _patch_world(monkeypatch, guards2, resolve_base=_resolve, project=project2)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result2 = await turn2._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v1, _PARAMS, version=1),
        ),
        "",
    )
    assert isinstance(result2, ToolObservation), result2
    pending2 = PendingPlan.model_validate(project2.pending_brief)
    assert pending2.film_storyboard_version == 2
    assert guards2.cleared == []


@pytest.mark.asyncio
async def test_publish_guard_full_identity_params_drift_discards(monkeypatch):
    """发布守卫全身份 (定点修复): committed pending 与 base 同号同内容但
    PARAMS 不同 (并发稿改了 music_mood) —— 旧的「版本号 + 内容 digest」比对
    放行此形, 全身份比对诚实丢弃; pending 字节不动, 本 draft marker 清,
    指引重读."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(
        marker_base_version=2,
        # 同号同内容, 参数已移动 (并发稿换音乐) —— 版本号与内容 digest 都
        # 看不出来, 只有全身份 (canonical params 在内) 看得出来.
        committed=_pending_with_film(
            v2, {**_PARAMS, "music_mood": "upbeat"}, version=2
        ),
    )
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "discarded" in result and "base_ref" in result
    assert project.pending_brief == pending_before
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_plan_publish_guard_full_identity_params_drift_discards(
    monkeypatch,
):
    """plan 路镜像 (双路行为一致): 同号同内容异参数 → 丢弃."""
    from app.chat.plan_turn import PlanTurn

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))

    turn = _plan_turn(project, text="把第五场的旁白缩短一点")

    guards = _GuardStubs(
        marker_base_version=2,
        committed=_pending_with_film(
            v2, {**_PARAMS, "music_mood": "upbeat"}, version=2
        ),
    )
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str) and "discarded" in result
    assert project.pending_brief == pending_before
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_publish_guard_full_identity_frozen_cut_drift_discards(
    monkeypatch,
):
    """同号同内容同参数但冻结时间轴不同 —— cut 三元组 (state/frames/onsets)
    是版本状态的一部分: 并发稿的冻结帧或落字拍漂移 ⇒ 诚实丢弃 (两腿)."""
    from app.tools.film.storyboard import draft_reveal_onsets, execution_frames

    v2 = _board()
    frames = execution_frames(v2, _OLD_BEATS)
    onsets = draft_reveal_onsets(
        v2, frames, {"bpm": 60.0, "beats": _OLD_BEATS}
    )
    # base = live pending v2 carrying a frozen cut (kept frames + onsets).
    pending_before = _pending_with_film(
        v2, _PARAMS, version=2,
        track=_track("calm", _OLD_BEATS),
        kept_frames=frames,
        kept_reveal_onsets=onsets,
    )
    base_cut = ("kept", frames, onsets)

    for moved_frames, moved_onsets in (
        ([frames[0] + 30] + frames[1:], onsets),  # frames 漂移
        (frames, [None] * 5 + [onsets[5] + 6] + [None] * 8),  # onsets 漂移
    ):
        project = SimpleNamespace(
            id=uuid4(), pending_brief=dict(pending_before)
        )
        turn = _chat_turn(project)
        guards = _GuardStubs(
            marker_base_version=2,
            committed=_pending_with_film(
                v2, _PARAMS, version=2,
                track=_track("calm", _OLD_BEATS),
                kept_frames=moved_frames,
                kept_reveal_onsets=moved_onsets,
            ),
        )
        _patch_world(monkeypatch, guards, project=project)
        _kill_switch(monkeypatch)

        result = await turn._design_storyboard(
            _edit_args(
                edits=[
                    {"op": "update_scene", "scene_id": "s5",
                     "narration": "A tighter chapter walk."}
                ],
                base_ref=_base_ref(v2, _PARAMS, version=2, cut=base_cut),
            ),
            "",
        )
        assert isinstance(result, str), (moved_frames[:1], result)
        assert "discarded" in result and "base_ref" in result
        assert project.pending_brief == pending_before
        assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_publish_guard_legacy_identity_provable_or_honest_discard(
    monkeypatch,
):
    """legacy 缺字段律: 版本号相等永不当身份证明 ——
    ① committed 行的 params 缺失 (无法证明身份) → 诚实丢弃并指引重读;
    ② committed 行缺 stored content digest 但板/参数/版本齐 (digest 从板
       自重算 = 可证明, legacy 无 scene_id 板同律派生) → 照常发布."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)

    # ① 无法证明: params 缺失 —— 同号同内容也丢弃 (fail closed).
    legacy_unprovable = _pending_with_film(v2, _PARAMS, version=2)
    legacy_unprovable["film_storyboard_params"] = None
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)
    guards = _GuardStubs(marker_base_version=2, committed=legacy_unprovable)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "discarded" in result and "base_ref" in result
    assert project.pending_brief == pending_before
    assert guards.cleared == ["draft-test"]

    # ② 可证明: stored digest 缺失不碍事 —— 身份从板本身重算, 照常发布.
    legacy_provable = _pending_with_film(v2, _PARAMS, version=2)
    legacy_provable["film_storyboard_content_digest"] = None
    project2 = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn2 = _chat_turn(project2)
    guards2 = _GuardStubs(marker_base_version=2, committed=legacy_provable)
    _patch_world(monkeypatch, guards2, project=project2)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result2 = await turn2._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result2, ToolObservation), result2
    pending2 = PendingPlan.model_validate(project2.pending_brief)
    assert pending2.film_storyboard_version == 3
    assert guards2.cleared == []


@pytest.mark.asyncio
async def test_publish_guard_stale_own_marker_discards(monkeypatch):
    """提交前检查→写入窗口的 fail-closed 半: 本 draft marker 已越过设计预算
    (staleness) ⇒ 所有权按协议失效 (接管者可能已合法进场) —— 诚实丢弃,
    永不覆盖; 对照腿 (live marker + 世界未动) 照常发布."""
    import time as _time

    from app.tools.film.storyboard import _DOCK_DRAFT_BUDGET_S

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)
    guards = _GuardStubs(
        marker_base_version=2,
        marker_started_at=_time.time() - _DOCK_DRAFT_BUDGET_S - 1.0,
    )
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5",
                 "narration": "A tighter chapter walk."}
            ],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "discarded" in result and "base_ref" in result
    assert project.pending_brief == pending_before
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_happy_path_on_the_live_pending_with_zero_director_calls(
    monkeypatch,
):
    """闸 2 + 版本信封: live pending v2 → patch → v3, envelope 落库,
    hold 延续 base 的 standing hold (编辑拍永不代释放), 全部导演座炸毁仍成功."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=True)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "reorder_scenes", "order": [
                "s1", "s2", "s4", "s5", "s3", "s6", "s7",
                "s8", "s9", "s10", "s11", "s12", "s13", "s14",
            ]}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    from app.agents.tool_loop import ToolObservation

    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 3
    assert pending.film_created_via == "patch"
    assert pending.film_base_version == 2
    # hold 延续: base 的 standing hold (True) 不被编辑拍代释放.
    assert pending.film_review_hold is True
    # The reorder: scene content digests unchanged, ids moved (the diff
    # lists them in RESULT order).
    assert pending.film_change_set["moved"] == [
        {"scene_id": "s4", "from_index": 3, "to_index": 2},
        {"scene_id": "s5", "from_index": 4, "to_index": 3},
        {"scene_id": "s3", "from_index": 2, "to_index": 4},
    ]
    assert pending.film_change_set["edited"] == []
    board = FilmStoryboard.model_validate(pending.film_storyboard)
    assert [s.scene_id for s in board.scenes][:6] == [
        "s1", "s2", "s4", "s5", "s3", "s6",
    ]
    # The board's content digest MOVED (顺序是有意义变化) but every scene's
    # own digest stands.
    assert (
        pending.film_storyboard_content_digest
        != storyboard_content_digest(v2)
    )
    assert "moved 3 → 5" in result.text  # 1-based presentation
    assert turn._presentation_pending == {"version": 3}


# ---------------------------------------------------------------------------
# 2. 结构化拒绝 (loop feedback, never a redesign, never a 500)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unchanged_batch_echoes_and_creates_no_version(monkeypatch):
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            # Same-order reorder = an exact permutation that changes nothing.
            edits=[{"op": "reorder_scenes", "order": [f"s{i}" for i in range(1, 15)]}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "changes nothing" in result
    assert guards.cleared == ["draft-test"]  # the marker cleared
    assert project.pending_brief == pending_before


@pytest.mark.asyncio
async def test_validation_failure_echoes_the_violations_verbatim(monkeypatch):
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {
                    "op": "update_scene",
                    "scene_id": "s2",
                    # The REAL validator's narration cap: 5s scene → cap 65
                    # speech units; this line is far over.
                    "narration": " ".join(["word"] * 120),
                }
            ],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "validation_failed" in result
    assert "speech units" in result  # the violation's own wording
    assert "re-issue" in result
    assert guards.cleared == ["draft-test"]
    assert project.pending_brief == pending_before


@pytest.mark.asyncio
async def test_unknown_scene_echoes_the_structural_rejection(monkeypatch):
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "remove_scene", "scene_id": "s99"}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "unknown_scene" in result
    assert "s99" in result
    assert guards.cleared == ["draft-test"]
    assert project.pending_brief == pending_before


@pytest.mark.asyncio
async def test_edit_without_a_base_is_an_honest_refusal(monkeypatch):
    project = SimpleNamespace(id=uuid4(), pending_brief=None)
    turn = _chat_turn(project)

    async def _resolve_none(db, project, *, output_id=None):
        return None

    _patch_world(monkeypatch, _GuardStubs(), resolve_base=_resolve_none, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "remove_scene", "scene_id": "s3"}],
            base_ref="anything",
        ),
        "",
    )
    assert isinstance(result, str)
    assert "no film storyboard version to edit" in result
    assert project.pending_brief is None


@pytest.mark.asyncio
async def test_music_gate_names_the_unresolvable_mood(monkeypatch):
    """set_music 的校验 (曲目可解): the NAMED mood must resolve by name —
    a mistyped mood rejects honestly, never a silent fallback to 'calm'."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    async def _no_named_track(db, project, mood):
        return None, None

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _no_named_track)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "epicc", "retime": "keep_cut"}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "music_unavailable" in result
    assert "epicc" in result
    assert project.pending_brief == pending_before


@pytest.mark.asyncio
async def test_set_music_success_rebuilds_the_snapshot_with_the_new_grid(
    monkeypatch,
):
    """音乐变更成功道: the strict gate resolves the named track, the new
    version's execution snapshot carries ITS grid, change_set.music reports
    the selection change + the surviving retime directive."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    track = SimpleNamespace(
        id=uuid4(), mood="upbeat", title="Upbeat",
        meta={"bpm": 120.0, "beats": [0.0, 0.5, 1.0, 1.5]},
    )

    async def _named_track(db, project, mood):
        assert mood == "upbeat"
        return track, track.meta["beats"]

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _named_track)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "recut"}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 3
    assert pending.film_storyboard_params.get("music_mood") == "upbeat"
    assert pending.film_change_set["music"] == {
        "mood_before": None,
        "mood_after": "upbeat",
        "retime": "recut",
    }
    snap_music = (pending.film_storyboard_execution or {}).get("music")
    assert snap_music is not None and snap_music["track_id"] == str(track.id)
    assert '"calm"' not in result.text and "upbeat" in result.text
    assert "re-cut" in result.text


@pytest.mark.asyncio
async def test_set_music_off_skips_the_track_gate_and_lands(monkeypatch):
    """音频三态 (闸 21): set_music('off') 是真实关闭态——严格曲目门对它不
    触发 (无可解曲目), 快照不带床, change_set 呈现 off; 版本照常落库."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    async def _gate_must_not_fire(*args, **kwargs):
        raise AssertionError("the strict track gate fired on the explicit OFF")

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _gate_must_not_fire)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "off", "retime": "keep_cut"}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 3
    assert pending.film_storyboard_params.get("music_mood") == "off"
    assert pending.film_change_set["music"]["mood_after"] == "off"
    assert (pending.film_storyboard_execution or {}).get("music") is None
    assert "off (no bed)" in result.text


@pytest.mark.asyncio
async def test_set_voiceover_on_patch_lands_with_zero_director_calls(monkeypatch):
    """闸 21 重开配音零重设计: set_voiceover(true) 让既有旁白行在 run 期
    走合成/复用——编辑拍只翻参数: 板字节不动、零导演调用 (_kill_switch)、
    版本落库、呈现行报 on."""
    from app.tools.film.edits import ensure_scene_ids

    v2 = _board()
    off_params = {**_PARAMS, "voiceover": False}
    pending_before = _pending_with_film(v2, off_params, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": True}],
            base_ref=_base_ref(v2, off_params, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 3
    assert pending.film_storyboard_params.get("voiceover") is True
    assert pending.film_change_set["voiceover"] is True
    # The board bytes ride through untouched — zero redesign.
    assert pending.film_storyboard == ensure_scene_ids(v2).model_dump(mode="json")
    assert "voiceover: now on" in result.text


@pytest.mark.asyncio
async def test_set_voiceover_on_without_narration_echoes_content_gap(monkeypatch):
    """旁白存在律 (闸 21): 零旁白行开配音 = 结构化内容缺口拒答 (点名先用
    update_scene 写旁白内容, 明示这不是 synthesis/voice 问题); 零版本落库,
    本 draft marker 清."""
    silent_board = FilmStoryboard.model_validate(
        {"scenes": [
            {k: v for k, v in s.items() if k != "narration"}
            for s in _board_scenes()
        ]}
    )
    off_params = {**_PARAMS, "voiceover": False}
    pending_before = _pending_with_film(silent_board, off_params, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": True}],
            base_ref=_base_ref(silent_board, off_params, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "voiceover_needs_narration" in result
    assert "update_scene" in result  # the ONE next move: author the lines
    assert "never a synthesis or voice problem" in result
    assert project.pending_brief == pending_before  # no version landed
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_music_off_short_circuits_the_resolution_chain(monkeypatch):
    """闸 21 off 不被重开: 明确关闭在解析链入口短路——persona 皮肤默认与
    calm 兜底永不重开被关闭的床; 未指定 (None) 照常走 persona 链 (对照腿)."""
    import app.memory.brand as brand_mod
    import app.tools.film.storyboard as sb_mod

    persona_calls: list[int] = []

    async def _persona(db, project):
        persona_calls.append(1)
        return SimpleNamespace(brand={"musicId": "brand-track-ref"})

    seen: list[str] = []

    async def _resolve_ref(db, ref):
        seen.append(ref)
        return SimpleNamespace(id=uuid4(), mood=ref, meta={})

    monkeypatch.setattr(sb_mod, "resolve_persona", _persona)
    monkeypatch.setattr(brand_mod, "resolve_music_ref", _resolve_ref)

    # OFF: returns None before the persona lookup — no ref is ever tried.
    assert await sb_mod.resolve_film_music(None, SimpleNamespace(), "off") is None
    assert persona_calls == [] and seen == []
    # Control: an UNSET mood still rides the persona skin default.
    assert await sb_mod.resolve_film_music(None, SimpleNamespace(), None) is not None
    assert seen == ["brand-track-ref"]


# ---------------------------------------------------------------------------
# 3. PlanTurn parity — the plan path's patch branch rides the same seats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_turn_patch_branch_lands_the_version(monkeypatch):
    from app.chat.plan_turn import PlanTurn

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))

    turn = _plan_turn(project)
    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 3
    assert pending.film_created_via == "patch"
    assert pending.film_storyboard_params.get("voiceover") is False
    assert pending.film_change_set["voiceover"] is False
    assert "voiceover: now off" in result.text
    # The plan path's proposal tool is named in the steering law.
    assert "present_plan" in result.text


# ---------------------------------------------------------------------------
# 4. 授权矩阵 (ADR-134 修订, 闸 15) — film_design_state pure
# ---------------------------------------------------------------------------


def _film(reused: bool) -> DockStoryboard:
    return DockStoryboard(
        presentation="x",
        storyboard=_board().model_dump(mode="json"),
        fingerprint="fp",
        reused=reused,
        execution=None,
    )


def _state(stored, *, review_hold=None, created_via="patch", change_set=None):
    return film_design_state(
        stored,
        film=_film(reused=False),
        design_params={"focus": "x"},
        review_hold=review_hold,
        authorized_by="u1",
        created_via=created_via,
        change_set=change_set,
    )


def test_hold_matrix_compose_fresh_defaults_on():
    state = _state(None, created_via="compose")
    assert state["film_review_hold"] is True
    assert state["film_created_via"] == "compose"
    assert state["film_base_version"] is None
    assert state["film_change_set"] is None


def test_compose_birth_stores_the_explicit_voiceover_pin():
    """默认无配音 (2026-10-21): the design seats pin voiceover EXPLICITLY at
    birth (film_voiceover_birth_pin) — the stored version params carry the
    pinned value byte-for-byte (the dock restore, the Start draft-match and
    the run's slot all read the same explicit key)."""
    off = film_design_state(
        None,
        film=_film(reused=False),
        design_params={"focus": "x", "voiceover": False},
        review_hold=None,
        authorized_by="u1",
        created_via="compose",
    )
    assert off["film_storyboard_params"]["voiceover"] is False
    on = film_design_state(
        None,
        film=_film(reused=False),
        design_params={"voiceover": True},
        review_hold=None,
        authorized_by="u1",
        created_via="compose",
    )
    assert on["film_storyboard_params"]["voiceover"] is True


def test_hold_matrix_patch_on_unheld_base_adds_no_hold():
    base = _provenance_base(_board(), _PARAMS, version=2)
    state = _state(base, created_via="patch", change_set={"moved": []})
    assert state["film_review_hold"] is False  # 不新增 hold
    assert state["film_base_version"] == 2
    assert state["film_change_set"] == {"moved": []}


def test_hold_matrix_patch_never_releases_a_standing_hold():
    base = SimpleNamespace(
        **_pending_with_film(_board(), _PARAMS, version=2, hold=True)
    )
    state = _state(base, created_via="patch")
    assert state["film_review_hold"] is True  # 既有 hold 跨版本延续


def test_hold_matrix_explicit_param_is_the_two_way_escape_door():
    base = _provenance_base(_board(), _PARAMS, version=2)
    held = _state(base, created_via="patch", review_hold=True)
    assert held["film_review_hold"] is True
    released = _state(base, created_via="compose", review_hold=False)
    assert released["film_review_hold"] is False


def test_reuse_representation_keeps_the_stored_envelope():
    stored = SimpleNamespace(
        **_pending_with_film(_board(), _PARAMS, version=4, hold=True)
    )
    # The stored envelope (a patch-born version's lineage).
    stored.film_base_version = 3
    stored.film_created_via = "patch"
    stored.film_change_set = {"edited": [{"scene_id": "s2", "fields": ["narration"]}]}
    stored.film_constraints_choice = None
    state = film_design_state(
        stored,
        film=_film(reused=True),
        design_params={},
        review_hold=None,
        authorized_by="u2",
    )
    assert state["film_storyboard_version"] == 4  # reuse never bumps
    assert state["film_review_hold"] is True
    assert state["film_created_via"] == "patch"
    assert state["film_base_version"] == 3
    assert state["film_change_set"]["edited"][0]["scene_id"] == "s2"


# ---------------------------------------------------------------------------
# 5. 报价分叉 (pure)
# ---------------------------------------------------------------------------


def test_quote_facts_from_a_versioned_pending():
    from app.pipeline.step_context import film_quote_facts_from_pending

    board = _board()
    facts = film_quote_facts_from_pending(
        {
            "film_storyboard": board.model_dump(mode="json"),
            "film_storyboard_params": _PARAMS,
        }
    )
    assert facts["film_board_seconds"] == pytest.approx(81.0)
    expected_chars = float(
        sum(len(s.narration) for s in board.scenes if s.narration)
    )
    assert facts["film_board_tts_chars"] == expected_chars


def test_quote_facts_voiceover_off_quotes_zero_tts():
    from app.pipeline.step_context import film_quote_facts_from_pending

    facts = film_quote_facts_from_pending(
        {
            "film_storyboard": _board().model_dump(mode="json"),
            "film_storyboard_params": {"voiceover": False},
        }
    )
    assert facts["film_board_tts_chars"] == 0.0


def test_quote_facts_absent_or_corrupt_board_contributes_nothing():
    from app.pipeline.step_context import film_quote_facts_from_pending

    assert film_quote_facts_from_pending(None) == {}
    assert film_quote_facts_from_pending({}) == {}
    assert film_quote_facts_from_pending({"film_storyboard": {"scenes": [{"bogus": 1}]}}) == {}


def test_launch_film_estimate_fork_reads_actual_facts():
    from app.tools.film.storyboard import ESTIMATE_FILM_SECONDS, LaunchFilm

    node = LaunchFilm()
    forked = node.estimate(
        {"film_board_seconds": 42.0, "film_board_tts_chars": 300.0}
    )
    assert forked["units"] == {"film_seconds": 42.0, "tts_chars": 300.0}
    # Facts absent → the typical-film constants stand (the pre-fork shape).
    plain = node.estimate({})
    assert plain["units"]["film_seconds"] == ESTIMATE_FILM_SECONDS
    assert plain["units"]["tts_chars"] == ESTIMATE_FILM_SECONDS * 14.0


# ---------------------------------------------------------------------------
# 6. 呈现契约 + 回声 (pure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_film_revision_without_production_intent_answers_before_any_dock(
    monkeypatch,
):
    """Both turn paths: a saved film revision without CURRENT production
    intent closes through answer, never a launch_film dock/run. An explicit
    current-turn delegation remains the existing proposal path; non-film
    proposals and turns without a fresh film design are untouched."""
    from app.models.schemas import PresentPlanArgs, ProposeTasksArgs
    from app.chat.turn_tools import film_revision_proposal_guard

    tasks = [{"tool": "launch_film", "params": {}}]
    assert film_revision_proposal_guard(
        designed_version=2, tasks=tasks, production_intent=True
    ) is None
    assert film_revision_proposal_guard(
        designed_version=None, tasks=tasks, production_intent=False
    ) is None
    assert film_revision_proposal_guard(
        designed_version=2,
        tasks=[{"tool": "write_post", "params": {}}],
        production_intent=False,
    ) is None

    for make_turn in (_chat_turn, _plan_turn):
        for intent in (None, False):
            project = SimpleNamespace(id=uuid4(), pending_brief={})
            turn = make_turn(project)
            turn._designed_this_turn = 2
            if make_turn is _chat_turn:
                monkeypatch.setattr(
                    "app.chat.propose_turn.validate_task_list", lambda _tasks: None
                )

                async def _dock_never(**_kwargs):
                    raise AssertionError("a revision without intent docked")

                monkeypatch.setattr(turn, "_dock_plan_as_question", _dock_never)
                result = await turn._propose_tasks(
                    ProposeTasksArgs.model_validate(
                        {"tasks": tasks, "production_intent": intent}
                    ),
                    "the revised board",
                )
            else:
                monkeypatch.setattr(
                    "app.chat.plan_turn.validate_task_list", lambda _tasks: None
                )
                result = await turn._present_plan(
                    PresentPlanArgs.model_validate(
                        {"tasks": tasks, "production_intent": intent}
                    ),
                    "the revised board",
                )
            assert isinstance(result, str), type(turn).__name__
            assert "Call answer" in result
            assert "FULL current saved-board facts" in result
            assert "review only" in result
            assert project.pending_brief == {}


def test_film_rejection_stop_is_narrow_and_bounded():
    from app.agents.tool_loop import ToolRejected
    from app.chat.turn_tools import film_rejection_stop

    first = ToolRejected("params_validation", "design_storyboard", 0, "same", 0)
    repeated = ToolRejected("params_validation", "design_storyboard", 1, "same", 0)
    changed = ToolRejected("params_validation", "design_storyboard", 1, "changed", 0)
    assert film_rejection_stop(repeated, (first,)) is True
    assert film_rejection_stop(repeated, ()) is False
    assert film_rejection_stop(changed, (first,)) is False
    # Different errors still get a repair attempt, but the THIRD failed
    # design in the same turn closes even when every signature differs.
    assert film_rejection_stop(
        ToolRejected("execute_guardrail", "design_storyboard", 2, "third", 0),
        (first, changed),
    ) is True
    assert film_rejection_stop(
        ToolRejected("execute_guardrail", "design_storyboard", 1, "same", 0),
        (first,),
    ) is False
    assert film_rejection_stop(
        ToolRejected("params_validation", "get_output_spec", 1, "same", 0),
        (first,),
    ) is False


def test_film_wiring_guard_blocks_only_the_bare_film_execution_paths():
    from app.chat.turn_tools import film_wiring_guard

    film_id = uuid4()
    other_id = uuid4()
    nodes = [
        SimpleNamespace(id=film_id, tool="launch_film"),
        SimpleNamespace(id=other_id, tool="write_post"),
    ]
    assert film_wiring_guard(
        ops=[{"op": "edit_prompt", "node": str(film_id), "prompt": "new"}],
        pre_nodes=nodes,
    ) is not None
    assert film_wiring_guard(
        ops=[{"op": "edit_prompt", "node": str(other_id), "prompt": "new"}],
        pre_nodes=nodes,
    ) is None
    assert film_wiring_guard(tasks=[{"tool": "launch_film", "params": {}}]) is not None
    assert film_wiring_guard(tasks=[SimpleNamespace(tool="launch_film")]) is not None
    assert film_wiring_guard(tasks=[{"tool": "write_post", "params": {}}]) is None


@pytest.mark.asyncio
async def test_generic_chat_run_dispatcher_backstops_a_bare_film_run(monkeypatch):
    from app.chat.service import _create_run_from_tasks

    async def _create_never(*args, **kwargs):
        raise AssertionError("create_run was reached for a bare chat Film run")

    monkeypatch.setattr("app.pipeline.orchestrator.create_run", _create_never)
    project = SimpleNamespace(id=uuid4(), language="en")
    with pytest.raises(ValueError, match="versioned Start"):
        await _create_run_from_tasks(
            _StubDB(), project, [SimpleNamespace(tool="launch_film")], "remake"
        )


@pytest.mark.asyncio
async def test_edit_graph_preserves_the_current_production_intent(monkeypatch):
    from app.models.schemas import EditGraphArgs

    turn = _chat_turn(SimpleNamespace(id=uuid4(), pending_brief={}))
    captured = {}

    async def _capture(proposal, prose, **kwargs):
        captured["proposal"] = proposal
        captured["prose"] = prose
        return "sentinel"

    monkeypatch.setattr(turn, "_run_wiring_proposal", _capture)
    result = await turn._edit_graph(
        EditGraphArgs.model_validate({"ops": [], "production_intent": True}),
        "make the current revision",
    )
    assert result == "sentinel"
    assert captured["proposal"].production_intent is True
    assert captured["prose"] == "make the current revision"


@pytest.mark.asyncio
async def test_no_progress_finish_closes_both_paths_without_a_run(monkeypatch):
    from app.agents.tool_loop import LoopResult

    for make_turn, module in (
        (_chat_turn, "app.chat.propose_turn"),
        (_plan_turn, "app.chat.plan_turn"),
    ):
        for version_saved in (False, True):
            project = SimpleNamespace(id=uuid4(), pending_brief={})
            turn = make_turn(project)
            turn._designed_this_turn = 2 if version_saved else None
            turn.outcome = None
            if make_turn is _plan_turn:
                turn.settled_pending = None

            async def _resolved():
                return None

            monkeypatch.setattr(turn, "_resolve_deferred", _resolved)

            async def _create(db, conversation_id, role, content, **kwargs):
                return SimpleNamespace(
                    id=uuid4(), role=role, content=content, question=None
                )

            monkeypatch.setattr(f"{module}._create_message", _create)
            outcome = await turn.finish(
                LoopResult(
                    prose="",
                    tool_name=None,
                    params=None,
                    iterations=2,
                    no_progress_tool="design_storyboard",
                )
            )
            message, run_id = outcome[0], outcome[1]
            assert run_id is None
            assert "停止重复尝试" in message.content
            assert "没有开始" in message.content
            if version_saved:
                assert "最近保存的分镜版本" in message.content
            else:
                assert "没有保存新的分镜" in message.content
            assert project.pending_brief == {}


def test_change_set_presentation_lists_only_changes_one_based():
    from app.models.schemas import (
        FilmChangeMoved,
        FilmChangeMusic,
        FilmChangeRemoved,
        FilmChangeRetimed,
        FilmChangeSet,
    )

    change_set = FilmChangeSet(
        moved=[FilmChangeMoved(scene_id="s3", from_index=2, to_index=4)],
        edited=[],
        added=[],
        removed=[FilmChangeRemoved(scene_id="s7", scene_type="divider")],
        retimed=[FilmChangeRetimed(scene_id="s5", seconds_before=9.0, seconds_after=6.5)],
        music=FilmChangeMusic(mood_before=None, mood_after="upbeat", retime="recut"),
        voiceover=None,
    )
    text = change_set_presentation(change_set, _board())
    assert "moved 3 → 5" in text
    assert "scene [s7] (divider): removed" in text
    assert "9s → 6.5s" in text
    assert 'music: none → "upbeat" — re-cut' in text
    assert "New totals: 14 scenes · 81s." in text


def test_repair_echo_steers_per_code():
    from app.tools.film.edits import FilmEditError

    assert "re-read" in film_edit_repair_echo(FilmEditError("base_mismatch", "x"))
    assert "changes nothing" in film_edit_repair_echo(FilmEditError("unchanged", "x"))
    assert "adjust the ops" in film_edit_repair_echo(
        FilmEditError("validation_failed", "- CONSTRAINT_VIOLATION: y")
    )
    structural = film_edit_repair_echo(FilmEditError("unknown_scene", "no scene s99"))
    assert "unknown_scene" in structural and "no scene s99" in structural
    # 旁白存在律 (音频三态): the content-gap echo names the authoring move
    # and explicitly never reads as a synthesis/voice failure.
    gap = film_edit_repair_echo(FilmEditError("voiceover_needs_narration", "x"))
    assert "update_scene" in gap and "never a synthesis or voice problem" in gap


# ---------------------------------------------------------------------------
# 7. Schema 层互斥与读容忍
# ---------------------------------------------------------------------------


def test_edits_args_discipline():
    # base_ref mandatory with edits
    with pytest.raises(Exception, match="base_ref"):
        _edit_args(edits=[{"op": "set_voiceover", "enabled": False}])
    # design params / specific_instruction / material_urls never mix
    with pytest.raises(Exception, match="never mix"):
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref="x",
            specific_instruction="再短一点",
        )
    with pytest.raises(Exception, match="never mix"):
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref="x",
            music_mood="calm",
        )
    for design_param in ({"voiceover": False}, {"aspect": "9:16"}):
        with pytest.raises(Exception, match="never mix"):
            _edit_args(
                edits=[{"op": "set_voiceover", "enabled": False}],
                base_ref="x",
                **design_param,
            )
    # review_hold is the legal companion; null tolerance on both new keys
    ok = _edit_args(
        edits=[{"op": "set_voiceover", "enabled": False}],
        base_ref="x",
        review_hold=True,
    )
    assert ok.review_hold is True
    # set_voiceover rides both directions (音频三态 — re-opening synthesizes
    # the board's own lines, zero redesign).
    reopen = _edit_args(edits=[{"op": "set_voiceover", "enabled": True}], base_ref="x")
    assert reopen.edits[0].enabled is True
    tolerated = DesignStoryboardArgs.model_validate({"edits": None, "base_ref": None})
    assert tolerated.edits is None and tolerated.base_ref is None


# ---------------------------------------------------------------------------
# 8. get_output_spec film 分支 (最小基准读取座)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_output_spec_film_branch_mints_the_base_ref(monkeypatch):
    from app.chat.perception import executes as ex

    board = _board()
    base = _provenance_base(board, _PARAMS, version=2)
    output = SimpleNamespace(
        id=uuid4(), project_id="p1", type="film", language="en",
        status="completed", render_spec=None, payload=None,
    )
    project = SimpleNamespace(id="p1")

    class _DB:
        async def get(self, model, key):
            return output

    async def _resolve(db, project, *, output_id=None):
        return base

    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _async_pages([_page()]))
    monkeypatch.setattr("app.agents.contexts.output_one_liner", lambda o: None)

    text = await ex.get_output_spec(
        _DB(), project, ex.GetOutputSpecParams(output_id=output.id)
    )
    assert "Storyboard version: 2" in text
    assert f"base_ref: {_base_ref(board, _PARAMS, version=2)}" in text
    # R3 事实表: a never-executed base reads its PLANNED timeline (the one
    # frame seat, labeled planned — never as executed); authored seconds and
    # the timeline duration (frames ÷ fps) are two separate columns.
    frames = execution_frames(board, None)
    assert "Timeline: planned" in text
    assert (
        f'[s1] words · authored 4s · planned {frames[0] / 30:g}s '
        f'({frames[0]}f) · at 0–{round(frames[0] / 30, 1):g}s · shows: '
        '"Ship faster" (dark) · silent'
    ) in text
    assert (
        f'[s2] hero · authored 5s · planned {frames[1] / 30:g}s ({frames[1]}f) '
        f'· at {round(frames[0] / 30, 1):g}–'
        f'{round((frames[0] + frames[1]) / 30, 1):g}s '
        '· shows: word: "Ship faster" · sub: "Acme turns hours of release '
        'work into minutes." · narration: "Meet Acme."'
    ) in text
    # 取景/视图引用: the ui scene's view + camera text ride the scene line.
    assert '[s3] ui · authored 9s' in text and 'view: page 0 shot 0 "(top)"' in text
    # 配乐事实两分 (7886d879): params 行是「选择」（unset ≠ off），Music 行是
    # 该版本冻结记录里的事实——此 base 的快照无床，如实说设计期没解析到床。
    assert "music unset (not off" in text
    assert "- Music: no bed in this version's frozen execution record" in text
    assert "aspect 16:9" in text


# ---------------------------------------------------------------------------
# 9. 能力门控 (settings.film_edits_enabled — 默认关, 测试显式开)
# ---------------------------------------------------------------------------


def test_wire_spec_prunes_the_edit_slice_when_gated_off(monkeypatch):
    """声明面门控: gate OFF ⇒ wire schema 无 edits/base_ref, $defs 垃圾回收
    (op 词表不外泄), 描述无 TARGETED EDITS 段; gate ON 全量恢复."""
    from app.agents.tool_loop import tool_spec
    from app.chat.turn_tools import _DESIGN_STORYBOARD_TOOL

    on = tool_spec(_DESIGN_STORYBOARD_TOOL)["function"]
    assert "edits" in on["parameters"]["properties"]
    assert "base_ref" in on["parameters"]["properties"]
    assert "TARGETED EDITS" in on["description"]
    # update_element (下批 A4 声明面): the composite element edit's
    # vocabulary rides the same gated slice — addressing, kind-applicability,
    # presence semantics, the no-asset-swap law.
    assert "update_element" in on["description"]
    assert "scene_id + element_id" in on["description"]
    assert "keep_audio" in on["description"]
    edits_field = on["parameters"]["properties"]["edits"]
    assert "update_element" in str(edits_field)
    # 画幅诚实文案: 不再导向重设计, 而是诚实「暂不支持」
    assert "no aspect change" not in on["description"]
    assert "never offer a redesign as the workaround" in on["description"]

    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    off = tool_spec(_DESIGN_STORYBOARD_TOOL)["function"]
    props = off["parameters"].get("properties", {})
    assert "edits" not in props and "base_ref" not in props
    assert "TARGETED EDITS" not in off["description"]
    assert "update_element" not in off["description"]
    assert "base_ref" not in off["description"]
    assert not off["parameters"].get("$defs")  # op models never leak
    # The compose capability stands either way.
    assert "Design the film's storyboard" in off["description"]
    monkeypatch.setattr("app.config.settings.film_edits_enabled", True)
    assert "edits" in tool_spec(_DESIGN_STORYBOARD_TOOL)["function"]["parameters"]["properties"]


def test_wire_spec_states_patch_contract_and_live_copy_bounds(monkeypatch):
    """The model sees the patch-only fields and the validator's own copy
    bounds BEFORE its first call; no second numeric table may drift in."""
    from app.agents.tool_loop import tool_spec
    from app.chat.turn_tools import _DESIGN_STORYBOARD_TOOL
    from app.tools.film import storyboard as sb

    def descriptions() -> tuple[str, str]:
        parameters = tool_spec(_DESIGN_STORYBOARD_TOOL)["function"]["parameters"]
        return (
            parameters["properties"]["edits"]["description"],
            parameters["$defs"]["FilmEditUpdateScene"]["properties"][
                "copy_slots"
            ]["description"],
        )

    patch, copy = descriptions()
    for field in (
        "focus", "language", "voiceover", "music_mood", "aspect",
        "specific_instruction", "material_urls", "text", "verbatim",
        "target_seconds", "scene_count", "group_chars",
    ):
        assert field in patch
    assert "review_hold and pending_disposition" in patch
    assert '"op":"set_voiceover","enabled":false' in patch
    assert '"op":"update_scene"' in patch
    assert "complete grammatical sentences" in copy
    assert "never truncate, drop or rewrite" in copy
    assert (
        f"lines: 1..{sb._LIST_CAPS['words.lines']} entries, each "
        f"≤{sb.TEXT_CAPS[('words', 'lines')]} characters"
    ) in copy
    assert (
        f"default/medium={sb.film_text_line_cap(None, seat='words')} units"
    ) in copy

    # Change the SOURCE, not an expected literal in a duplicated table: the
    # very next wire render must project both new values.
    monkeypatch.setitem(sb.TEXT_CAPS, ("words", "lines"), 31)
    monkeypatch.setattr(sb, "_TEXT_DISPLAY_CAP", 32)
    _, changed = descriptions()
    assert "lines: 1..4 entries, each ≤31 characters" in changed
    assert "default/medium=32 units" in changed


def test_prompt_law_prunes_the_edit_path_when_gated_off(monkeypatch):
    """prompt 面门控: 两个系统 prompt 的编辑法条随门控收放; compose 法不动.
    下批 A4: update_element 词表 (_website_film) 与组合创建段
    (_text_film 的 MEDIA COMPOSITION + list_project_media 发现律) 同一道门."""
    from app.chat.prompts import chat_intent_system, intent_router_system

    assert "base_ref" in intent_router_system()  # autouse gate ON
    on_router = intent_router_system()
    on_chat = chat_intent_system()
    for text in (on_router, on_chat):
        assert "update_element" in text
        assert "MEDIA COMPOSITION" in text
        assert "list_project_media" in text
        assert "keep_audio" in text

    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    off_router = intent_router_system()
    off_chat = chat_intent_system()
    for text in (off_router, off_chat):
        assert "base_ref" not in text
        assert "A TARGETED change" not in text
        assert "An edited version carries NO new hold" not in text
        assert "update_element" not in text
        assert "MEDIA COMPOSITION" not in text
        assert "list_project_media" not in text
        # compose law untouched
        assert "design_storyboard" in text
        assert "specific_instruction" in text

    monkeypatch.setattr("app.config.settings.film_edits_enabled", True)
    on_chat = chat_intent_system()
    assert "A TARGETED change" in on_chat and "base_ref" in on_chat


@pytest.mark.asyncio
async def test_gate_off_execution_refuses_edits_on_both_paths(monkeypatch):
    """执行面门控 (双路): gate OFF ⇒ 直接带 edits 的调用被诚实拒绝 ——
    无版本、无 marker、pending 字节不动; 拒绝文案不教导能力细节."""
    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)

    # chat path
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)
    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "does not accept edits" in result
    assert project.pending_brief == pending_before
    assert guards.begin_calls == [] and guards.cleared == []

    # plan path (mirror)
    project2 = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    pturn = _plan_turn(project2)
    result2 = await pturn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result2, str) and "does not accept edits" in result2
    assert project2.pending_brief == pending_before


def test_media_discovery_read_rides_the_same_gate(monkeypatch):
    """素材发现读的门控 (下批 A1): list_project_media 与编辑/组合出生同一道
    deployment gate. The loop's tool lists are built ONCE at import (the gate
    reads at process start), so membership itself is environment-set; gated
    here: the helper is deterministic in BOTH gate states, and the two read
    lists wire the read through the SAME gated seat (both carry it or
    neither does — never one list drifting)."""
    from app.chat.turn_tools import (
        CHAT_READ_TOOLS,
        PLAN_READ_TOOLS,
        _film_composite_read_tools,
    )

    # autouse gate ON: the helper yields the read.
    assert [t.name for t in _film_composite_read_tools()] == ["list_project_media"]
    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    assert _film_composite_read_tools() == []

    # Both lists ride the one helper — same treatment either way.
    plan_names = [t.name for t in PLAN_READ_TOOLS]
    chat_names = [t.name for t in CHAT_READ_TOOLS]
    assert ("list_project_media" in plan_names) == (
        "list_project_media" in chat_names
    )


def _compose_world(monkeypatch, guards, *, marker_draft="draft-test"):
    """The compose beat's stub seats: begin/clear recorded, the drafting seat
    returns a prebuilt board, no revision base exists, the committed-marker
    read answers the given holder."""
    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "begin_film_draft", guards.begin)
    monkeypatch.setattr(sb_mod, "clear_film_draft_marker", guards.clear)

    async def _prepared(db, project, **kwargs):
        return DockStoryboard(
            presentation="fact sheet",
            storyboard=_board().model_dump(mode="json"),
            fingerprint="fp-compose",
            reused=False,
            execution=None,
        )

    async def _no_base(db, project, **kwargs):
        return None

    async def _marker(project_id):
        return {"draft_id": marker_draft, "base_version": None}

    monkeypatch.setattr(sb_mod, "prepare_dock_storyboard", _prepared)
    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _no_base)
    monkeypatch.setattr(sb_mod, "read_committed_film_marker", _marker)


@pytest.mark.asyncio
async def test_compose_shape_pin_presence_reaches_both_design_paths(monkeypatch):
    """Wire-level proof for the redraft pin: omission inherits all three
    constraints; explicit null removes them from the synthetic launch task.
    The text source itself still inherits in both cases."""
    from app.agents.tool_loop import ToolObservation

    source_params = {
        "text": "用户原文",
        "verbatim": True,
        "target_seconds": 42.4,
        "scene_count": 11,
        "group_chars": [1, 3],
        "voiceover": False,
    }
    for make_turn in (_chat_turn, _plan_turn):
        for clear in (False, True):
            project = SimpleNamespace(id=uuid4(), pending_brief={})
            turn = make_turn(project, text="调整当前文字片")
            _compose_world(monkeypatch, _GuardStubs())
            base = _provenance_base(_text_board(), source_params, version=2)

            async def _base(db, project, **kwargs):
                return base

            async def _marker(project_id):
                return {"draft_id": "draft-test", "base_version": 2}

            captured = {}

            async def _prepared(db, project, **kwargs):
                captured.update(kwargs)
                return DockStoryboard(
                    presentation="fact sheet",
                    storyboard=_text_board().model_dump(mode="json"),
                    fingerprint="fp-compose",
                    reused=False,
                    execution=None,
                )

            import app.tools.film.storyboard as sb_mod

            monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _base)
            monkeypatch.setattr(sb_mod, "read_committed_film_marker", _marker)
            monkeypatch.setattr(sb_mod, "prepare_dock_storyboard", _prepared)
            raw = {"specific_instruction": "调整当前分镜"}
            if clear:
                raw.update(target_seconds=None, scene_count=None, group_chars=None)
            result = await turn._design_storyboard(_edit_args(**raw), "")
            assert isinstance(result, ToolObservation), result
            params = captured["tasks"][0]["params"]
            assert params["text"] == "用户原文"
            if clear:
                assert all(
                    key not in params
                    for key in ("target_seconds", "scene_count", "group_chars")
                )
            else:
                assert params["target_seconds"] == 42.4
                assert params["scene_count"] == 11
                assert params["group_chars"] == [1, 3]


@pytest.mark.asyncio
async def test_compose_observation_mints_base_ref_only_when_gated_on(monkeypatch):
    """读取面门控 (compose 观察): gate OFF ⇒ 观察不铸造/不邀请 base_ref;
    ON ⇒ 铸造行在位. compose 本体行为两态一致 (版本落库)."""
    from app.agents.tool_loop import ToolObservation

    project = SimpleNamespace(id=uuid4(), pending_brief=None)
    turn = _chat_turn(project, text="做一支官网短片")
    _compose_world(monkeypatch, _GuardStubs())
    on = await turn._design_storyboard(_edit_args(focus="product story"), "")
    assert isinstance(on, ToolObservation)
    assert "base_ref" in on.text
    assert PendingPlan.model_validate(project.pending_brief).film_storyboard_version == 1

    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    project2 = SimpleNamespace(id=uuid4(), pending_brief=None)
    turn2 = _chat_turn(project2, text="做一支官网短片")
    off = await turn2._design_storyboard(_edit_args(focus="product story"), "")
    assert isinstance(off, ToolObservation)
    assert "base_ref" not in off.text
    assert PendingPlan.model_validate(project2.pending_brief).film_storyboard_version == 1


@pytest.mark.asyncio
async def test_get_output_spec_omits_base_ref_when_gated_off(monkeypatch):
    """读取面门控 (get_output_spec): gate OFF ⇒ 无 base_ref 行, 无候选视图
    清单 (编辑模型的视图菜单不外泄), 版本/逐场事实仍在 (读不承诺未开放的
    编辑协议)."""
    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    from app.chat.perception import executes as ex

    board = _board()
    base = _provenance_base(board, _PARAMS, version=2)
    output = SimpleNamespace(
        id=uuid4(), project_id="p1", type="film", language="en",
        status="completed", render_spec=None, payload=None,
    )
    project = SimpleNamespace(id="p1")

    class _DB:
        async def get(self, model, key):
            return output

    async def _resolve(db, project, *, output_id=None):
        return base

    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _async_pages([_page()]))
    monkeypatch.setattr("app.agents.contexts.output_one_liner", lambda o: None)

    text = await ex.get_output_spec(
        _DB(), project, ex.GetOutputSpecParams(output_id=output.id)
    )
    assert "base_ref" not in text
    assert "Candidate views" not in text
    assert "Storyboard version: 2" in text
    frames = execution_frames(board, None)
    assert (
        f'[s1] words · authored 4s · planned {frames[0] / 30:g}s '
        f'({frames[0]}f) · at 0–{round(frames[0] / 30, 1):g}s · shows: '
        '"Ship faster" (dark) · silent'
    ) in text


# ---------------------------------------------------------------------------
# 10. patch 观察文本去冲突 (双路) — 下一步由授权状态决定, 非固定追问
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_observation_never_demands_an_unconditional_question(monkeypatch):
    """去冲突 (chat 路): 不再有「then ONE direct question — whether to
    start」的无条件追问; 下一步按 standing hold / 制作意图 / 确认设置分岔."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=True)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "update_scene", "scene_id": "s5",
                    "narration": "A tighter chapter walk."}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    assert "then ONE direct question" not in result.text
    assert "The next step keys on the CURRENT request" in result.text
    # The hold fork: this base carries a standing hold → the observation
    # says so and names the hold's release seat.
    assert "review hold ON" in result.text
    assert "the one question whether to remake this version" in result.text
    assert "propose_tasks" in result.text


@pytest.mark.asyncio
async def test_patch_observation_plan_path_same_deconfliction(monkeypatch):
    """去冲突 (plan 路镜像): 同法, 提案动词为 present_plan."""
    from app.chat.plan_turn import PlanTurn

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))

    turn = _plan_turn(project)
    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    assert "then ONE direct question" not in result.text
    assert "The next step keys on the CURRENT request" in result.text
    assert "review hold off" in result.text
    assert "present_plan" in result.text


# ---------------------------------------------------------------------------
# 11. superseded 释放自己的 marker (双路 × patch/compose + 真函数条件)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_patch_superseded_releases_its_own_marker(monkeypatch):
    """plan 路镜像: 并发回防丢弃前清本 draft marker."""
    from app.chat.plan_turn import PlanTurn

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))

    turn = _plan_turn(project, text="删掉第十场")

    guards = _GuardStubs(
        marker_base_version=2,
        committed=_pending_with_film(_board(), _PARAMS, version=3),
    )
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "remove_scene", "scene_id": "s10"}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str) and "discarded" in result
    assert project.pending_brief == pending_before
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_compose_superseded_releases_its_own_marker_both_paths(monkeypatch):
    """同形漏洞同法 (compose 座, 双路): 发布回防丢弃前清本 draft marker —
    marker 已被别的 draft 接管时清理函数自身 no-op (下一测试锁条件)."""
    from app.agents.tool_loop import ToolObservation  # noqa: F401

    # chat path compose
    project = SimpleNamespace(id=uuid4(), pending_brief=None)
    turn = _chat_turn(project, text="做一支官网短片")
    guards = _GuardStubs()
    _compose_world(monkeypatch, guards, marker_draft="other-draft")
    result = await turn._design_storyboard(_edit_args(focus="x"), "")
    assert isinstance(result, str) and "discarded" in result
    assert guards.cleared == ["draft-test"]
    assert project.pending_brief is None

    # plan path compose
    project2 = SimpleNamespace(id=uuid4(), pending_brief=None)
    pturn = _plan_turn(project2, text="做一支官网短片")
    guards2 = _GuardStubs()
    _compose_world(monkeypatch, guards2, marker_draft="other-draft")
    result2 = await pturn._design_storyboard(_edit_args(focus="x"), "")
    assert isinstance(result2, str) and "discarded" in result2
    assert guards2.cleared == ["draft-test"]
    assert project2.pending_brief is None


@pytest.mark.asyncio
async def test_lock_contention_dbapierror_reads_as_honest_refusal(monkeypatch):
    """并发护栏的异常类回归 (2026-10-23 T3 崩溃取证): asyncpg 的
    LockNotAvailableError (SQLSTATE 55P03) 映射为普通 DBAPIError 而非
    OperationalError — begin/clear 两座必须把它读成设计好的诚实拒绝
    (begin=None / clear 吞没), 而不是让 'Internal server error' 上屏;
    非锁类 DBAPI 失败照常抛."""
    import app.models.database as db_mod
    from sqlalchemy.exc import DBAPIError
    from app.tools.film.storyboard import (
        _is_lock_contention,
        begin_film_draft,
        clear_film_draft_marker,
    )

    lock_err = DBAPIError("SELECT ... FOR UPDATE NOWAIT", {}, Exception())
    lock_err.orig = type("LockNotAvailableError", (Exception,), {})()
    # The REAL asyncpg wrap (live-dialect forensics 2026-10-23): orig is the
    # dialect's translated `Error` whose sqlstate carries 55P03 and whose
    # __cause__ is the driver error — neither the DBAPIError.sqlstate nor
    # orig's type name betrays the lock.
    dialect_err = type("Error", (Exception,), {})()
    dialect_err.sqlstate = "55P03"
    dialect_err.__cause__ = type("LockNotAvailableError", (Exception,), {})()
    wrapped_err = DBAPIError("SELECT ... FOR UPDATE NOWAIT", {}, Exception())
    wrapped_err.orig = dialect_err
    other_err = DBAPIError("SELECT 1", {}, Exception())
    assert _is_lock_contention(lock_err) is True
    assert _is_lock_contention(wrapped_err) is True
    assert _is_lock_contention(other_err) is False

    class _LockSession:
        def __init__(self, exc):
            self.exc = exc

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, model, key, with_for_update=None):
            raise self.exc

    project = SimpleNamespace(id=uuid4())

    async def _flush():
        return None

    # begin: contention → the structured "locked" refusal (the designed
    # refusal), never a crash.
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _LockSession(lock_err))
    db = SimpleNamespace(flush=_flush)
    refused = await begin_film_draft(db, project, base_version=None, user_message_id=None)
    assert refused.draft_id is None and refused.refusal == "locked"
    # clear: contention → swallowed (the row's owner decides), never a crash.
    db2 = SimpleNamespace(is_modified=lambda project: True)
    await clear_film_draft_marker(db2, project, draft_id="mine")
    # A non-lock DBAPI failure still raises from both seats.
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _LockSession(other_err))
    with pytest.raises(DBAPIError):
        await begin_film_draft(db, project, base_version=None, user_message_id=None)
    with pytest.raises(DBAPIError):
        await clear_film_draft_marker(db2, project, draft_id="mine")

    # OperationalError parity (the begin seat once mapped EVERY
    # OperationalError to contention): a lock-classified one reads as the
    # "locked" refusal, a non-lock one keeps its real category and raises
    # from BOTH seats.
    from sqlalchemy.exc import OperationalError

    op_lock = OperationalError("SELECT ... FOR UPDATE NOWAIT", {}, Exception())
    op_lock.orig = dialect_err
    op_other = OperationalError("SELECT 1", {}, Exception())
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _LockSession(op_lock))
    refused = await begin_film_draft(db, project, base_version=None, user_message_id=None)
    assert refused.draft_id is None and refused.refusal == "locked"
    await clear_film_draft_marker(db2, project, draft_id="mine")
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _LockSession(op_other))
    with pytest.raises(OperationalError):
        await begin_film_draft(db, project, base_version=None, user_message_id=None)
    with pytest.raises(OperationalError):
        await clear_film_draft_marker(db2, project, draft_id="mine")


# ---------------------------------------------------------------------------
# 11. 同回合纠正道 + 带条件授权守卫 (7276ef13 修复批 A): a same-turn
# correction drafts against THIS turn's standing version under the turn's
# own standing marker (never a second begin — the self-lock), the cap
# refuses honestly with the shortfall marked, and a lapsed-budget takeover
# discards without touching the foreign marker.
# ---------------------------------------------------------------------------


def _correction_turn(project, *, corrections=0, draft_id="draft-test"):
    """A ChatTurn whose FIRST design already published this turn (version 2
    stands in the in-memory pending; the turn's committed marker ids
    ``draft_id``)."""
    turn = _chat_turn(project, text="按逗号拆成八屏")
    turn._designed_this_turn = 2
    turn._design_draft_id = draft_id
    turn._design_corrections = corrections
    turn._design_shortfalls = []
    return turn


@pytest.mark.asyncio
async def test_same_turn_correction_designs_on_the_in_turn_version(monkeypatch):
    """7276ef13 ②: 同回合纠错不再被「一回合一次设计」闸挡下 — the
    correction drafts against THIS turn's just-published version (never a
    second begin: the turn's own committed marker still stands, so Start
    fails closed and any concurrent begin is refused throughout), and
    publishes as the next version with the in-turn version as its base."""
    from app.agents.tool_loop import ToolObservation

    v2 = _board()
    project = SimpleNamespace(
        id=uuid4(),
        pending_brief=dict(_pending_with_film(v2, _PARAMS, version=2)),
    )
    turn = _correction_turn(project)
    guards = _GuardStubs(marker_base_version=1)  # draft-1's OWN (pre-turn) base
    _compose_world(monkeypatch, guards)

    result = await turn._design_storyboard(
        _edit_args(specific_instruction="按逗号拆成更多屏"), ""
    )
    assert isinstance(result, ToolObservation), result
    assert guards.begin_calls == []  # never a second begin (the self-lock)
    assert guards.cleared == []  # a successful correction never clears the marker
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 3
    assert pending.film_base_version == 2  # built on the IN-TURN version
    assert turn._designed_this_turn == 3
    assert turn._design_corrections == 1
    assert turn._design_shortfalls == []  # nothing failed this turn


@pytest.mark.asyncio
async def test_same_turn_correction_cap_refuses_honestly_and_marks_shortfall(
    monkeypatch,
):
    """同回合纠正上限: the correction budget (=2) spent, a further design
    call this turn is refused at the dispatch seat — the standing version
    is named, the honest-presentation duty is stated (never present the
    standing version as if the change had landed), the shortfall rides the
    turn for the conditional-authorization guard, and neither a begin nor
    a draft ever runs. 两座 (chat/plan) 同一法律."""
    from app.chat.turn_tools import MAX_DESIGN_CORRECTIONS_PER_TURN

    for build in (_correction_turn, None):
        v2 = _board()
        project = SimpleNamespace(
            id=uuid4(),
            pending_brief=dict(_pending_with_film(v2, _PARAMS, version=2)),
        )
        if build is not None:
            turn = build(project, corrections=MAX_DESIGN_CORRECTIONS_PER_TURN)
        else:
            turn = _plan_turn(project, text="再改一次")
            turn._designed_this_turn = 2
            turn._design_draft_id = "draft-test"
            turn._design_corrections = MAX_DESIGN_CORRECTIONS_PER_TURN
        guards = _GuardStubs()
        _compose_world(monkeypatch, guards)
        result = await turn._design_storyboard(
            _edit_args(specific_instruction="再改一次"), ""
        )
        assert isinstance(result, str), type(turn).__name__
        assert "version 2" in result, result
        assert "did not land" in result, result
        # 台账记账: the refused call's signature joins the ledger (a
        # specific_instruction-only call signs as "compose").
        assert _ledger_keys(turn) == ["compose"]
        assert guards.begin_calls == []
        # The refused correction changed nothing.
        assert (
            PendingPlan.model_validate(project.pending_brief)
            .film_storyboard_version
            == 2
        )


@pytest.mark.asyncio
async def test_same_turn_correction_marker_takeover_discards_honestly(monkeypatch):
    """The correction publish guard: the committed marker no longer names
    THIS turn's draft (our budget lapsed and a takeover landed) → the
    correction draft discards honestly, the in-turn version stands, the
    shortfall is marked — and the foreign marker is never cleared."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _correction_turn(project)
    guards = _GuardStubs()
    _compose_world(monkeypatch, guards, marker_draft="other-draft")

    result = await turn._design_storyboard(
        _edit_args(specific_instruction="按逗号拆成更多屏"), ""
    )
    assert isinstance(result, str)
    assert "discarded" in result
    assert _ledger_keys(turn) == ["compose"]  # the discard joins the ledger
    assert guards.cleared == []  # a correction never touches the marker
    assert project.pending_brief == pending_before


@pytest.mark.asyncio
async def test_same_turn_correction_patch_builds_on_the_in_turn_version(monkeypatch):
    """编辑拍纠正: the patch's base is THIS turn's just-published version
    (still uncommitted), so the committed world legitimately reads PRE-turn
    — the correction publish guard checks only that the committed marker
    still names this turn's draft (the committed-identity half would
    discard every correction by construction)."""
    from app.agents.tool_loop import ToolObservation

    v2 = _board()
    project = SimpleNamespace(
        id=uuid4(),
        pending_brief=dict(_pending_with_film(v2, _PARAMS, version=2)),
    )
    turn = _correction_turn(project)
    # The committed world = the PRE-TURN version 1 + this turn's marker.
    guards = _GuardStubs(
        marker_base_version=1,
        committed=dict(_pending_with_film(_board(), _PARAMS, version=1)),
    )
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    assert guards.begin_calls == []  # the patch correction never re-begins
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 3
    assert pending.film_base_version == 2
    assert pending.film_storyboard_params.get("voiceover") is False
    assert turn._design_corrections == 1


@pytest.mark.asyncio
async def test_verbatim_redraft_restating_drifted_copy_carries_the_drift_note(
    monkeypatch,
):
    """抄录漂移注记上线 (7276ef13 v3): a verbatim redraft that RE-PASTES a
    drifted copy publishes (a deliberate copy edit stays legal) but the
    observation carries the honest COPY DRIFT note; an identical re-paste
    carries none."""
    from app.agents.tool_loop import ToolObservation

    base_text = "如果觉得身边的一切都太不如意，那就去见喜欢的人，做喜欢的事，买喜欢的东西"
    base = _provenance_base(
        _board(), {**_PARAMS, "text": base_text, "verbatim": True}, version=2
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    async def _marker(project_id):
        # The compose publish guard reads the committed marker naming THIS
        # draft on ITS base (version 2 — the redraft's resolved base).
        return {"draft_id": "draft-test", "base_version": 2}

    for restated, expect in (
        (base_text.replace("买喜欢的东西", "买喜欢的事"), True),
        (base_text, False),
    ):
        project = SimpleNamespace(id=uuid4(), pending_brief=None)
        turn = _chat_turn(project, text="重新剪一版")
        guards = _GuardStubs()
        _compose_world(monkeypatch, guards)
        import app.tools.film.storyboard as sb_mod

        monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
        monkeypatch.setattr(sb_mod, "read_committed_film_marker", _marker)
        result = await turn._design_storyboard(
            _edit_args(text=restated, verbatim=True), ""
        )
        assert isinstance(result, ToolObservation), result
        assert ("COPY DRIFT" in result.text) is expect
        if expect:
            assert "买喜欢的东西" in result.text and "买喜欢的事" in result.text


# ---------------------------------------------------------------------------
# 11b. 定点收尾① — 签名台账: EVERY failed design exit joins the ledger
# (keyed by design_call_signature); a COMPOSE success clears all, a PATCH
# success clears only its OWN matching signature — an unrelated successful
# change never clears a failure it did not resolve. ② — 原文继承守卫:
# unproven drift sets the copy_drift hold (the note informs, never
# green-lights); user-pasted copy is proven and proceeds.
# ---------------------------------------------------------------------------


def test_design_call_signature_keys_repair_retry_vs_unrelated_change():
    """签名律 (定点收尾①): the signature is mechanical — op names + target
    handles in EXECUTION order (2026-10-23 拍板: 执行序即语义——同一幕先改
    深底再改浅底与反过来结果不同), VALUES-FREE. A repair retry (same op +
    handles, only the offending value changed) signs IDENTICALLY to its
    failure; an unrelated change signs differently and never clears it;
    every compose (no edits) is one family key."""
    from app.chat.turn_tools import design_call_signature

    failed = _edit_args(
        edits=[{"op": "update_element", "scene_id": "s2", "element_id": "e1",
                "source_start": 20.0, "source_end": 28.0}],
        base_ref="x",
    )
    retry = _edit_args(
        edits=[{"op": "update_element", "scene_id": "s2", "element_id": "e1",
                "source_start": 12.0, "source_end": 20.0}],
        base_ref="y",
    )
    unrelated = _edit_args(
        edits=[{"op": "update_element", "scene_id": "s2", "element_id": "e2",
                "lines": ["下周三上线"]}],
        base_ref="x",
    )
    assert design_call_signature(failed) == design_call_signature(retry)
    assert design_call_signature(failed) != design_call_signature(unrelated)
    # 复审①的洞: same op + same scene, DIFFERENT field — 同一幕换背景永不
    # 配对同一幕的动画时序失败.
    timing = _edit_args(
        edits=[{"op": "update_scene", "scene_id": "s2", "enter_interval": 0.9}],
        base_ref="x",
    )
    background = _edit_args(
        edits=[{"op": "update_scene", "scene_id": "s2", "dark": True}],
        base_ref="x",
    )
    assert design_call_signature(timing) != design_call_signature(background)
    # The target-VALUE joins only where the value IS the identity: a
    # reorder's arrangement, set_music's mood, set_voiceover's on/off.
    reorder_a = _edit_args(
        edits=[{"op": "reorder_scenes", "order": ["s2", "s1"]}], base_ref="x"
    )
    reorder_b = _edit_args(
        edits=[{"op": "reorder_scenes", "order": ["s1", "s2"]}], base_ref="x"
    )
    assert design_call_signature(reorder_a) != design_call_signature(reorder_b)
    mood_on = _edit_args(edits=[{"op": "set_music", "mood": "calm"}], base_ref="x")
    mood_off = _edit_args(edits=[{"op": "set_music", "mood": "off"}], base_ref="x")
    assert design_call_signature(mood_on) != design_call_signature(mood_off)
    # Compose = one family key (no edits at all).
    assert design_call_signature(_edit_args(text="文案")) == "compose"
    assert design_call_signature(_edit_args(specific_instruction="改")) == "compose"


def test_design_call_record_only_exact_equivalence_auto_clears():
    """复审再收紧 (「同字段不同值」洞): the ledger record carries the
    requested TARGET VALUES — the mechanical key is necessary but never
    sufficient. Only a byte-equivalent retry (same key AND same values)
    pairs with its failure for auto-clearing; a swapped-in value, a
    dropped field, or an added field never pairs. 「已经呈现」≠ 用户接受."""
    from app.chat.turn_tools import design_call_record

    asked = _edit_args(
        edits=[{"op": "update_scene", "scene_id": "s2",
                "enter": "words", "enter_hold_until": 99.0}],
        base_ref="x",
    )
    same = _edit_args(
        edits=[{"op": "update_scene", "scene_id": "s2",
                "enter": "words", "enter_hold_until": 99.0}],
        base_ref="y",  # base_ref never enters the record (read protocol)
    )
    other_value = _edit_args(
        edits=[{"op": "update_scene", "scene_id": "s2",
                "enter": "words", "enter_hold_until": 4.0}],
        base_ref="x",
    )
    dropped_field = _edit_args(
        edits=[{"op": "update_scene", "scene_id": "s2",
                "enter": "words"}],
        base_ref="x",
    )
    added_field = _edit_args(
        edits=[{"op": "update_scene", "scene_id": "s2",
                "enter": "words", "enter_hold_until": 99.0, "dark": True}],
        base_ref="x",
    )
    assert design_call_record(asked) == design_call_record(same)
    for variant in (other_value, dropped_field, added_field):
        assert design_call_record(asked) != design_call_record(variant)
    # Op order inside one batch IS the record (2026-10-23 拍板: 执行序即
    # 语义——同一幕先改深底再改浅底，与反过来的结果不同); only each op
    # object's INTERNAL field order is normalized away.
    reordered = _edit_args(
        edits=[
            {"op": "update_element", "scene_id": "s2", "element_id": "e2",
             "lines": ["a"]},
            {"op": "update_element", "scene_id": "s2", "element_id": "e1",
             "source_start": 1.0},
        ],
        base_ref="x",
    )
    swapped = _edit_args(
        edits=list(reversed(reordered.edits)), base_ref="x"
    )
    assert design_call_record(reordered) != design_call_record(swapped)


@pytest.mark.asyncio
async def test_patch_failure_then_unrelated_patch_success_keeps_the_hold(
    monkeypatch,
):
    """失败后仅完成其他修改 (定点收尾①): a failed patch joins the ledger; a
    LATER unrelated successful patch (a different element's change that
    never claimed to resolve the failure) leaves the hold standing — the
    dock's unmet_condition conjunct still blocks the auto start (零新
    run)."""
    board = _composite_text_board()
    params = dict(_TEXT_PARAMS)
    project = SimpleNamespace(
        id=uuid4(),
        pending_brief=dict(_pending_with_film(board, params, version=1)),
    )
    turn = _chat_turn(project, text="素材往后挪，再把第二章文案改一下")

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    _media_stub(monkeypatch, edits_mod, _composite_media(duration=25.0))

    # ① The out-of-range edit fails (the REAL validator) — a repair echo,
    # nothing lands, and the failure's signature joins the ledger.
    failed = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_element", "scene_id": "s2", "element_id": "e1",
                 "source_start": 20.0, "source_end": 28.0},
            ],
            base_ref=_base_ref(board, params, version=1),
        ),
        "",
    )
    assert isinstance(failed, str)
    assert _ledger_keys(turn) == [
        "patch:update_element:s2:e1[source_end,source_start]"
    ]
    assert project.pending_brief["film_storyboard_version"] == 1

    # ② An UNRELATED change (the text element's copy) lands — its
    # matching-signature clear removes nothing it did not resolve.
    from app.agents.tool_loop import ToolObservation

    landed = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_element", "scene_id": "s2", "element_id": "e2",
                 "lines": ["下周三上线，", "记得来看"]},
            ],
            base_ref=_base_ref(board, params, version=1),
        ),
        "",
    )
    assert isinstance(landed, ToolObservation), landed
    assert project.pending_brief["film_storyboard_version"] == 2
    # The unresolved failure's hold STANDS (the success never claimed it).
    assert _ledger_keys(turn) == [
        "patch:update_element:s2:e1[source_end,source_start]"
    ]


@pytest.mark.asyncio
async def test_patch_failure_then_matching_retry_clears_the_hold(monkeypatch):
    """等价重试销账 (定点收尾①, 复审再收紧; 失败座 2026-10-24 换位): the ONE
    auto-clearing path — the failure is the publish SUPERSEDE (a foreign
    draft's marker took the row mid-patch; no value was ever judged), and
    the retry is BYTE-EQUIVALENT (same key AND same requested target
    values). Its landing clears the record. (A retry that swaps in a
    DIFFERENT value never auto-clears — the same-field-different-value
    regression below. A BEGIN refusal is no longer this law's failure
    seat: it latches the design entry for the turn — see
    test_begin_refusal_latches_the_entry_for_the_turn.)"""
    board = _composite_text_board()
    params = dict(_TEXT_PARAMS)
    project = SimpleNamespace(
        id=uuid4(),
        pending_brief=dict(_pending_with_film(board, params, version=1)),
    )
    turn = _chat_turn(project, text="素材往后挪一点")

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    _media_stub(monkeypatch, edits_mod, _composite_media(duration=25.0))

    # The first publish reads a FOREIGN marker (a newer draft took the row
    # mid-patch) → the draft discards; the retry's marker matches again.
    guards.marker_draft_id = "foreign-takeover"

    ops = [
        {"op": "update_element", "scene_id": "s2", "element_id": "e1",
         "source_start": 12.0, "source_end": 20.0},
    ]
    failed = await turn._design_storyboard(
        _edit_args(edits=ops, base_ref=_base_ref(board, params, version=1)),
        "",
    )
    assert isinstance(failed, str) and "discarded" in failed
    assert _ledger_keys(turn) == [
        "patch:update_element:s2:e1[source_end,source_start]"
    ]
    guards.marker_draft_id = "draft-test"

    from app.agents.tool_loop import ToolObservation

    # The EXACTLY EQUIVALENT retry (same op, handles, fields AND values).
    retried = await turn._design_storyboard(
        _edit_args(edits=ops, base_ref=_base_ref(board, params, version=1)),
        "",
    )
    assert isinstance(retried, ToolObservation), retried
    assert project.pending_brief["film_storyboard_version"] == 2
    assert turn._design_shortfalls == []  # the equivalent retry resolves it


@pytest.mark.asyncio
async def test_begin_refusal_latches_the_entry_for_the_turn(monkeypatch):
    """入口锁存 (2026-10-24 d02bf85a 事故法 — the self-lock storm's law):
    a refused FIRST begin latches the design entry for the rest of the
    turn. The refusal feedback carries the facts + the closed-entry law;
    the SAME-turn repeat never touches begin again — it returns the
    deterministic TerminalRefusal (the loop ends, the ledger keeps the
    record — the hold is this turn's unmet condition, and the user's NEXT
    message re-enters). Both compose and patch seats, both turn paths."""
    import app.tools.film.storyboard as sb_mod
    from app.agents.tool_loop import TerminalRefusal
    from app.pipeline.lifecycle import confirmation_need
    from app.tools.film.storyboard import FilmDraftBegin

    for make_turn in (_chat_turn, _plan_turn):  # chat 路 + plan 路同一法律
        # -- compose seat --
        project = SimpleNamespace(id=uuid4(), pending_brief=None)
        turn = make_turn(project, text="逐字稿成片")
        guards = _GuardStubs()
        _compose_world(monkeypatch, guards)
        calls = {"n": 0}
        real_begin = guards.begin

        async def _refuse(db, project, *, base_version, user_message_id):
            calls["n"] += 1
            return FilmDraftBegin(refusal="locked")

        monkeypatch.setattr(sb_mod, "begin_film_draft", _refuse)

        n0 = calls["n"]
        refused = await turn._design_storyboard(
            _edit_args(text="第一句，第二句。", verbatim=True), ""
        )
        assert isinstance(refused, str), type(turn).__name__
        assert "design entry is CLOSED" in refused
        assert "unknown" in refused  # the locked holder is never narrated
        assert turn._design_begin_refusal == "locked"
        assert _ledger_keys(turn) == ["compose"]

        repeated = await turn._design_storyboard(
            _edit_args(text="第一句，第二句。", verbatim=True), ""
        )
        assert isinstance(repeated, TerminalRefusal), type(turn).__name__
        assert calls["n"] == n0 + 1  # the repeat never re-hit the row
        assert project.pending_brief is None  # nothing drafted
        assert _ledger_keys(turn) == ["compose"]  # deduped record stands
        need = confirmation_need(
            execution="auto", credits="auto",
            quote_high=120, unquotable=False, always_confirm_above=10000,
            production_intent=True,
            unmet_condition=bool(turn._design_shortfalls),
        )
        assert need.requires_confirmation and need.reason == "unmet_condition"

        # -- patch seat --
        board = _composite_text_board()
        params = dict(_TEXT_PARAMS)
        project2 = SimpleNamespace(
            id=uuid4(),
            pending_brief=dict(_pending_with_film(board, params, version=1)),
        )
        turn2 = make_turn(project2, text="素材往后挪一点")
        guards2 = _GuardStubs(marker_base_version=1)
        _patch_world(monkeypatch, guards2, project=project2)
        _kill_switch(monkeypatch)
        import app.tools.film.edits as edits_mod

        _media_stub(monkeypatch, edits_mod, _composite_media(duration=25.0))

        async def _refuse_in_flight(db, project, *, base_version, user_message_id):
            calls["n"] += 1
            return FilmDraftBegin(refusal="in_flight")

        monkeypatch.setattr(sb_mod, "begin_film_draft", _refuse_in_flight)
        ops = [
            {"op": "update_element", "scene_id": "s2", "element_id": "e1",
             "source_start": 12.0, "source_end": 20.0},
        ]
        n1 = calls["n"]
        refused2 = await turn2._design_storyboard(
            _edit_args(edits=ops, base_ref=_base_ref(board, params, version=1)),
            "",
        )
        assert isinstance(refused2, str), type(turn2).__name__
        assert "in flight" in refused2  # a live marker MAY narrate a design
        assert turn2._design_begin_refusal == "in_flight"
        assert _ledger_keys(turn2) == [
            "patch:update_element:s2:e1[source_end,source_start]"
        ]

        repeated2 = await turn2._design_storyboard(
            _edit_args(edits=ops, base_ref=_base_ref(board, params, version=1)),
            "",
        )
        assert isinstance(repeated2, TerminalRefusal), type(turn2).__name__
        assert calls["n"] == n1 + 1  # the repeat never re-hit the row
        assert project2.pending_brief["film_storyboard_version"] == 1


@pytest.mark.asyncio
async def test_same_scene_different_field_success_never_clears_the_failure(
    monkeypatch,
):
    """复审①的洞 + 再收紧 (双路覆盖): 同一幕的动画时序修改失败 → 同一幕换
    背景成功 — a different FIELD on the SAME scene signs differently, so
    the background success never clears the timing failure; 随后模型改用
    其他时间值成功（同字段不同值）同样不销账 — the dock's unmet_condition
    hold keeps the auto start blocked throughout (零新 run), until the
    user's OWN later explicit start (a conscious acceptance — the gate's
    docked_this_turn conjunct scopes the hold)."""
    from app.pipeline.lifecycle import confirmation_need

    for make_turn in (_chat_turn, None):  # chat 路 + plan 路同一法律
        board = _text_board()
        params = dict(_TEXT_PARAMS)
        project = SimpleNamespace(
            id=uuid4(),
            pending_brief=dict(_pending_with_film(board, params, version=1)),
        )
        if make_turn is not None:
            turn = make_turn(project, text="第二幕文字动画再快点")
        else:
            turn = _plan_turn(project, text="第二幕文字动画再快点")
        guards = _GuardStubs(marker_base_version=1)
        _patch_world(monkeypatch, guards, project=project)
        _kill_switch(monkeypatch)

        failed_sig = "patch:update_scene:s2:[enter,enter_hold_until]"
        # ① The timing edit overflows the 5s scene window (REAL validator).
        failed = await turn._design_storyboard(
            _edit_args(
                edits=[{"op": "update_scene", "scene_id": "s2",
                        "enter": "words", "enter_hold_until": 99.0}],
                base_ref=_base_ref(board, params, version=1),
            ),
            "",
        )
        assert isinstance(failed, str), type(turn).__name__
        assert _ledger_keys(turn) == [failed_sig]

        # ② Same scene, different field (the background polarity — s2
        # stands dark, so this LANDS) — and the unresolved timing failure's
        # hold STANDS.
        from app.agents.tool_loop import ToolObservation

        landed = await turn._design_storyboard(
            _edit_args(
                edits=[{"op": "update_scene", "scene_id": "s2", "dark": False}],
                base_ref=_base_ref(board, params, version=1),
            ),
            "",
        )
        assert isinstance(landed, ToolObservation), type(turn).__name__
        assert _ledger_keys(turn) == [failed_sig]
        # 保护仍在 → 自动制作被阻止 (the REAL law on the turn's ledger).
        need = confirmation_need(
            execution="auto", credits="auto",
            quote_high=120, unquotable=False, always_confirm_above=10000,
            production_intent=True,
            unmet_condition=bool(turn._design_shortfalls),
        )
        assert need.requires_confirmation and need.reason == "unmet_condition"

        # ③ 复审再收紧 (用户点名回归): same op + same FIELDS but a
        # DIFFERENT target value (99.0 → 4.0) LANDS — the requested timing
        # never landed, so the hold STILL STANDS and the auto start stays
        # blocked. 「已经呈现」≠ 用户接受.
        v2 = PendingPlan.model_validate(project.pending_brief)
        guards.marker_base_version = 2
        retried = await turn._design_storyboard(
            _edit_args(
                edits=[{"op": "update_scene", "scene_id": "s2",
                        "enter": "words", "enter_hold_until": 4.0}],
                base_ref=_base_ref(
                    FilmStoryboard.model_validate(v2.film_storyboard),
                    dict(v2.film_storyboard_params),
                    version=2,
                ),
            ),
            "",
        )
        assert isinstance(retried, ToolObservation), type(turn).__name__
        assert PendingPlan.model_validate(
            project.pending_brief
        ).film_storyboard_version == 3
        assert _ledger_keys(turn) == [failed_sig]  # 值变了 ≠ 修复
        need2 = confirmation_need(
            execution="auto", credits="auto",
            quote_high=120, unquotable=False, always_confirm_above=10000,
            production_intent=True,
            unmet_condition=bool(turn._design_shortfalls),
        )
        assert need2.requires_confirmation

        # ④ 用户明确接受当前方案后可启动: a LATER-turn explicit Start (the
        # user saw the standing version and chose) is legal — the gate's
        # docked_this_turn conjunct scopes the hold (the acceptance path
        # rides the existing confirmation mechanism, no ledger verdict).
        from app.pipeline.lifecycle import (
            LifecycleFacts,
            compute_lifecycle,
            evaluate_start_gate,
        )

        stamp = compute_lifecycle(
            LifecycleFacts(
                has_pending_plan=True,
                plan_tasks=({"tool": "launch_film", "params": {}},),
                plan_prose="Plan: one film.",
                estimate_total=(10, 20),
                required_inputs=(),
            )
        )
        assert (
            evaluate_start_gate(
                has_pending_plan=True,
                effective_tasks_nonempty=True,
                stamp=stamp,
                confirmation=need2,
                docked_this_turn=True,
            )
            is not None
        )
        assert (
            evaluate_start_gate(
                has_pending_plan=True,
                effective_tasks_nonempty=True,
                stamp=stamp,
                confirmation=need2,
                docked_this_turn=False,  # the user's own later beat
            )
            is None
        )


@pytest.mark.asyncio
async def test_compose_success_never_clears_an_unresolved_failure(monkeypatch):
    """复审① — 删除「重稿成功无条件清账」: a compose failure (the publish
    SUPERSEDE — a foreign draft's marker took the row mid-design; the
    begin-refusal failure seat retired with the 2026-10-24 入口锁存) followed
    by a SUCCESSFUL redraft keeps the ledger standing: 重稿成功不证明原请求落实
    (the incident's own shape). The dock's unmet_condition hold survives —
    the auto start stays blocked until the user sees the standing version
    and chooses."""
    import app.tools.film.storyboard as sb_mod
    from app.pipeline.lifecycle import confirmation_need

    project = SimpleNamespace(id=uuid4(), pending_brief=None)
    turn = _chat_turn(project, text="逐字稿成片，改完开工")
    guards = _GuardStubs()

    # The first publish reads a FOREIGN marker (a newer draft took the row
    # mid-design) → the draft discards; the retry's marker matches again.
    marker_holder = {"draft_id": "foreign-takeover", "base_version": None}

    async def _marker(project_id):
        return dict(marker_holder)

    _compose_world(monkeypatch, guards)
    monkeypatch.setattr(sb_mod, "read_committed_film_marker", _marker)

    refused = await turn._design_storyboard(_edit_args(text="第一句，第二句。", verbatim=True), "")
    assert isinstance(refused, str) and "discarded" in refused
    assert _ledger_keys(turn) == ["compose"]
    marker_holder["draft_id"] = "draft-test"

    from app.agents.tool_loop import ToolObservation

    landed = await turn._design_storyboard(_edit_args(text="第一句，第二句。", verbatim=True), "")
    assert isinstance(landed, ToolObservation), landed
    assert project.pending_brief["film_storyboard_version"] == 1
    # 重稿成功 ≠ 销账: the earlier refusal's record STANDS.
    assert _ledger_keys(turn) == ["compose"]
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=10000,
        production_intent=True,
        unmet_condition=bool(turn._design_shortfalls),
    )
    assert need.requires_confirmation and need.reason == "unmet_condition"


@pytest.mark.asyncio
async def test_layout_request_with_model_added_sentence_holds_the_auto_start(
    monkeypatch,
):
    """布局请求中模型误加一句 (定点收尾② — 事故形态): a LAYOUT-ONLY request
    (the user never pasted any copy this turn) whose redraft re-states the
    board text WITH an added sentence publishes with the honest COPY DRIFT
    note AND sets the copy_drift hold — the note informs, but never
    green-lights the auto start by itself. The pinned source text is the
    version's own (原文继承): the drift is measured against the BASE
    version's pinned copy, never the model's re-transcription."""
    from app.agents.tool_loop import ToolObservation

    base_text = "如果觉得身边的一切都太不如意，那就去见喜欢的人，做喜欢的事，买喜欢的东西"
    base = _provenance_base(
        _board(), {**_PARAMS, "text": base_text, "verbatim": True}, version=2
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    async def _marker(project_id):
        return {"draft_id": "draft-test", "base_version": 2}

    drifted = base_text + "，顺便加一句模型自作主张的话"
    project = SimpleNamespace(id=uuid4(), pending_brief=None)
    # 布局请求: the user's words carry NO copy — the drift is unproven.
    turn = _chat_turn(project, text="只调整排版布局，文案别动")
    guards = _GuardStubs()
    _compose_world(monkeypatch, guards)
    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    monkeypatch.setattr(sb_mod, "read_committed_film_marker", _marker)
    result = await turn._design_storyboard(_edit_args(text=drifted, verbatim=True), "")
    assert isinstance(result, ToolObservation), result
    assert "COPY DRIFT" in result.text  # the honest note still rides
    assert turn._design_shortfalls == []  # nothing FAILED — copy_drift, not unmet_condition

    # 保护在场 = 版本封套上的世界真值 (never a turn-local flag): the
    # published version carries the unaccepted-drift state…
    from app.tools.film.storyboard import film_text_drift_held

    assert film_text_drift_held(project.pending_brief) is True
    # …and that state, fed to the REAL confirmation law, BLOCKS the
    # same-turn auto start (零新 run) — 保护仍在 → 自动制作被阻止 (the gate
    # conjunct half is law-tested in test_lifecycle_pure's copy_drift
    # precedence test: docked_this_turn=True → start.needs_confirm).
    from app.pipeline.lifecycle import confirmation_need

    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=10000,
        production_intent=True,
        copy_drift=film_text_drift_held(project.pending_brief),
    )
    assert need.requires_confirmation and need.reason == "copy_drift"

    # A→B→继承 B 洞 (复审②): a SAME-TURN follow-up that only adjusts layout
    # (omits text — the pin inherits the drifted B) must NOT wash the hold:
    # the new version still carries the unaccepted-drift state against the
    # LAST ACCEPTED baseline (A), and the gate still blocks.
    drifted_v3 = dict(project.pending_brief)
    follow_up = await turn._design_storyboard(
        _edit_args(specific_instruction="再调一下布局"), ""
    )
    assert isinstance(follow_up, ToolObservation), follow_up
    assert PendingPlan.model_validate(
        project.pending_brief
    ).film_storyboard_version == 4  # the correction landed as a new version
    assert film_text_drift_held(project.pending_brief) is True  # 保护仍在
    # 跨回合: a REBUILT turn over the same standing version reads the same
    # world truth (the dock seat's copy_drift never depends on turn state).
    fresh_turn = _chat_turn(project, text="继续")
    assert film_text_drift_held(fresh_turn.project.pending_brief) is True
    assert drifted_v3["film_text_drift"]  # the drifted version itself carried it


@pytest.mark.asyncio
async def test_user_pasted_copy_edit_is_proven_and_proceeds(monkeypatch):
    """明确改文字的正例 (定点收尾②): the user pastes the new copy THEMSELVES
    this turn — the restated text is provably theirs
    (``text_drift_user_proven`` — whitespace-insensitive substring), so the
    drift note rides but NO hold sets: a deliberate copy edit stays legal
    and never blocks the auto start."""
    from app.agents.tool_loop import ToolObservation

    base_text = "如果觉得身边的一切都太不如意，那就去见喜欢的人，做喜欢的事，买喜欢的东西"
    base = _provenance_base(
        _board(), {**_PARAMS, "text": base_text, "verbatim": True}, version=2
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    async def _marker(project_id):
        return {"draft_id": "draft-test", "base_version": 2}

    new_copy = base_text.replace("买喜欢的东西", "买让自己安心的东西")
    project = SimpleNamespace(id=uuid4(), pending_brief=None)
    # The user pastes the new copy in their own message (whitespace and a
    # framing prefix around it — the proven check is substring-based).
    turn = _chat_turn(project, text=f"文案换成这句：\n{new_copy}\n就按这个来")
    guards = _GuardStubs()
    _compose_world(monkeypatch, guards)
    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    monkeypatch.setattr(sb_mod, "read_committed_film_marker", _marker)
    result = await turn._design_storyboard(
        _edit_args(text=new_copy, verbatim=True), ""
    )
    assert isinstance(result, ToolObservation), result
    assert "COPY DRIFT" in result.text  # drifted from the BASE — the note rides
    # …but the user proved it: no drift state on the version, no hold, and
    # the auto fast path stays free (正常成功旅程仍可直接开工).
    from app.pipeline.lifecycle import confirmation_need
    from app.tools.film.storyboard import film_text_drift_held

    assert film_text_drift_held(project.pending_brief) is False
    assert not confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=10000,
        production_intent=True,
        copy_drift=film_text_drift_held(project.pending_brief),
    ).requires_confirmation



@pytest.mark.asyncio
async def test_clear_film_draft_marker_only_clears_its_own_draft(monkeypatch):
    """真函数条件 (stub 侧会话): marker 属于本 draft ⇒ 清除并提交; 属于别的
    draft ⇒ 行不动、不提交."""
    import app.models.database as db_mod
    from app.tools.film.storyboard import clear_film_draft_marker

    class _Session:
        def __init__(self, row):
            self.row = row
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, model, key, with_for_update=None):
            return self.row

        async def commit(self):
            self.commits += 1

    db = SimpleNamespace(is_modified=lambda project: True)  # skip refresh leg
    project = SimpleNamespace(id=uuid4())

    own = SimpleNamespace(
        pending_brief={"film_draft_inflight": {"draft_id": "mine"}}
    )
    session = _Session(own)
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: session)
    await clear_film_draft_marker(db, project, draft_id="mine")
    assert "film_draft_inflight" not in own.pending_brief
    assert session.commits == 1

    other = SimpleNamespace(
        pending_brief={"film_draft_inflight": {"draft_id": "other"}}
    )
    session2 = _Session(other)
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: session2)
    await clear_film_draft_marker(db, project, draft_id="mine")
    assert other.pending_brief["film_draft_inflight"] == {"draft_id": "other"}
    assert session2.commits == 0

# ---------------------------------------------------------------------------
# 12. keep_cut 执行语义 — 编辑 → 持久化 → 执行 spec 的帧数链
#    (keep_cut = 消费 base 版本的已执行/已呈现时间轴, 永不回裸分配帧)
# ---------------------------------------------------------------------------

# Two DIFFERENT beds whose grids snap the fixture board's boundaries
# differently: off-grid by +0.1s (old) / -0.05s (new) at 30fps — a re-snap
# onto the new grid WOULD move the cut (the contrast legs prove it).
_OLD_BEATS = [0.1 + float(i) for i in range(120)]
_NEW_BEATS = [0.95 + float(i) for i in range(120)]


def _track(mood: str, beats: list[float], bpm: float = 60.0):
    return SimpleNamespace(
        id=uuid4(), mood=mood, title=mood.title(),
        file_path=f"music/{mood}.mp3", meta={"bpm": bpm, "beats": beats},
    )


def test_execution_frames_is_the_one_allocate_snap_formula():
    """帧公式一座 (执行/呈现同骑): allocate → beat snap. keep_cut 不走此座 —
    冻结切点是 base 版本自身的时间轴 (见 run 级测试)."""
    from app.tools.film.storyboard import (
        allocate_frames,
        execution_frames,
        snap_frames_to_beats,
    )

    board = _board()
    allocated = allocate_frames(board)
    snapped = snap_frames_to_beats(board, allocated, _OLD_BEATS)
    assert snapped != allocated  # the grid WOULD move the cut
    assert execution_frames(board, _OLD_BEATS) == snapped
    assert execution_frames(board, None) == allocated


def test_valid_kept_cut_and_spec_scene_frames_shapes():
    """冻结切点的 fail-closed 校验 + spec 帧读取座 (纯)."""
    from app.tools.film.storyboard import (
        allocate_frames,
        spec_scene_frames,
        valid_kept_cut,
    )

    board = _board()
    good = allocate_frames(board)
    assert valid_kept_cut(board, good) is True
    assert valid_kept_cut(board, None) is False
    assert valid_kept_cut(board, good[:-1]) is False  # 场数不齐
    assert valid_kept_cut(board, [0] + good[1:]) is False  # 低于结构下限
    assert valid_kept_cut(board, [True] * len(good)) is False  # bool ≠ int
    assert valid_kept_cut(board, [10**9] + good[1:]) is False  # 超渲染帽

    spec = {"scenes": [{"frames": 90}, {"frames": 270}]}
    assert spec_scene_frames(spec) == [90, 270]
    assert spec_scene_frames({}) is None
    assert spec_scene_frames({"scenes": [{"frames": 0}]}) is None
    assert spec_scene_frames({"scenes": [{"frames": 90}, {"noframes": 1}]}) is None


def test_film_music_retime_of_projection_shapes():
    """Start 投影的纯函数半: change_set.music.retime → run.context 值."""
    from app.tools.film.edits import film_music_retime_of

    assert film_music_retime_of(None) is None
    assert film_music_retime_of(SimpleNamespace()) is None
    assert (
        film_music_retime_of(SimpleNamespace(film_change_set=None)) is None
    )
    assert (
        film_music_retime_of(SimpleNamespace(film_change_set={"music": None}))
        is None
    )
    kept = SimpleNamespace(
        film_change_set={
            "music": {"mood_before": None, "mood_after": "upbeat",
                      "retime": "keep_cut"}
        }
    )
    assert film_music_retime_of(kept) == "keep_cut"
    recut = SimpleNamespace(
        film_change_set={"music": {"mood_before": "calm",
                                   "mood_after": "calm", "retime": "recut"}}
    )
    assert film_music_retime_of(recut) == "recut"
    garbage = SimpleNamespace(film_change_set={"music": {"retime": "bogus"}})
    assert film_music_retime_of(garbage) is None


class _RunDB:
    """LaunchFilm.run 的 DB stand-in: 先清旧产物的 select 回空, db.get 回
    指定 track, add 记录 Output."""

    def __init__(self, track):
        self.track = track
        self.added = []

    async def execute(self, *args, **kwargs):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    async def get(self, model, key):
        return self.track

    async def flush(self):
        return None

    def add(self, obj):
        self.added.append(obj)


def _stub_run_peripherals(monkeypatch, pages):
    """run() 外设 stub 一座: pages/计量/呈现字段/渲染认领/汇总."""
    import app.tools.film.storyboard as sb_mod

    async def _pages(db, project):
        return pages

    async def _noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _pages)
    monkeypatch.setattr(sb_mod, "record_media_usage", _noop_async)
    monkeypatch.setattr(sb_mod, "set_spec_field", _noop_async)
    monkeypatch.setattr(sb_mod, "pend_outputs_for_render", _noop_async)
    monkeypatch.setattr(sb_mod, "fill_summary", _noop_async)
    return sb_mod


async def _run_film(board, track, ctx_extra: dict, slot_extra: dict | None = None):
    """真 LaunchFilm.run (stub 外设) → 产出 spec 的逐场 frames."""
    from app.tools.film.storyboard import LaunchFilm

    pages = [_page()]
    db = _RunDB(track)
    node = SimpleNamespace(
        id=uuid4(),
        spec={"slot": {"type": "film", "voiceover": False, **(slot_extra or {})}},
    )
    project = SimpleNamespace(id=uuid4(), language="en")
    ctx = {
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(pages=pages, track=track),
        **ctx_extra,
    }
    run = SimpleNamespace(id=uuid4(), context=ctx)
    ids = await LaunchFilm().run(db, run, node, project)
    assert len(ids) == 1
    return db.added[0]


@pytest.mark.asyncio
async def test_keep_cut_run_consumes_the_executed_base_cut(monkeypatch):
    """用户复现形状的钉死: 原片按旧床网格渲染 (首/末幕被 snap 移动),
    keep_cut 换新音乐后逐幕帧数与原 spec 一致 —— 不是裸分配帧, 也不是
    新床网格的重卡点."""
    from app.tools.film.storyboard import allocate_frames

    board = _board()
    old_track = _track("calm", _OLD_BEATS)
    _stub_run_peripherals(monkeypatch, [_page()])

    # 1) 原片实跑: spec_A 的逐场帧 = 旧床卡点时间轴 (首/末幕被移动).
    base_output = await _run_film(board, old_track, {})
    spec_a_frames = [s["frames"] for s in base_output.render_spec["scenes"]]
    assert spec_a_frames != allocate_frames(board)  # snap 确实移动了切点
    spec_a_onsets = [
        s.get("lead_frames") for s in base_output.render_spec["scenes"]
    ]

    # 2) 编辑: set_music(upbeat, keep_cut) —— base 命名空间携带已执行切点
    #    (resolve 座从原 run 的 spec 读出, 这里直接给真值).
    base = _provenance_base(board, _PARAMS, version=1, cut_state="spec")
    base.film_cut_frames = spec_a_frames
    base.film_cut_reveal_onsets = spec_a_onsets
    pending_before = _pending_with_film(board, _PARAMS, version=3)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project, mentions=[SimpleNamespace(type="output", id=uuid4())])

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, resolve_base=None, project=project)

    import app.tools.film.edits as edits_mod

    async def _resolve(db, project, *, output_id=None):
        return base

    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    _kill_switch(monkeypatch)

    new_track = _track("upbeat", _NEW_BEATS, bpm=63.0)

    async def _named_track(db, project, mood):
        assert mood == "upbeat"
        return new_track, new_track.meta["beats"]

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _named_track)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "keep_cut"}],
            base_ref=_base_ref(board, _PARAMS, version=1, cut=film_base_cut(base)),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_change_set["music"]["retime"] == "keep_cut"
    # 信封: 冻结切点 = base 的已执行时间轴 (spec_A), 不是裸分配; 冻结场内
    # 切点 (reveal 落字拍) 同信封 —— 冻结时间轴的另一半.
    assert pending.film_kept_frames == spec_a_frames
    assert pending.film_kept_reveal_onsets == spec_a_onsets

    # 3) 新版本实跑 (Start stamping 的投影): 逐场帧 == spec_A; 新床网格在场
    #    (音乐确实换了) 但永不重卡切点 —— 场内落字拍也不压新网格.
    from app.tools.film.edits import film_music_retime_of

    assert film_music_retime_of(pending) == "keep_cut"
    new_output = await _run_film(
        board,
        new_track,
        {
            "film_music_retime": film_music_retime_of(pending),
            "film_kept_frames": pending.film_kept_frames,
            "film_kept_reveal_onsets": pending.film_kept_reveal_onsets,
        },
    )
    spec_b_frames = [s["frames"] for s in new_output.render_spec["scenes"]]
    assert spec_b_frames == spec_a_frames
    # 问题 5 回归: reveal 的落字拍也与原片逐帧一致 —— keep_cut 保场内文字
    # 出现时间, 不只是场长.
    assert [
        s.get("lead_frames") for s in new_output.render_spec["scenes"]
    ] == spec_a_onsets
    # 对照: 新床网格若重卡会移动切点 (分支有效性).
    from app.tools.film.storyboard import execution_frames

    assert execution_frames(board, _NEW_BEATS) != spec_a_frames


@pytest.mark.asyncio
async def test_music_off_run_consumes_no_bed(monkeypatch):
    """闸 21 执行面: 明确关闭的版本在 run 期走短路——快照无 track_id 时的
    resolve 回落永不碰 persona/曲库 (off 短路), 不硬失败、不落 calm 默认;
    spec 无 music 键, 帧按无网格分配 (execution_frames 的 beats=None 道)."""
    board = _board()
    _stub_run_peripherals(monkeypatch, [_page()])

    import app.tools.film.storyboard as sb_mod

    async def _chain_must_not_run(*args, **kwargs):
        raise AssertionError("the mood chain fired on the explicit OFF")

    # resolve_film_music itself stays REAL (the law under test); its chain
    # rungs trip the assertion if OFF ever falls through to them.
    monkeypatch.setattr(sb_mod, "resolve_persona", _chain_must_not_run)

    output = await _run_film(board, None, {}, slot_extra={"music_mood": "off"})
    assert "music" not in output.render_spec
    assert [
        s["frames"] for s in output.render_spec["scenes"]
    ] == execution_frames(board, None)  # allocated, never snapped to a grid


@pytest.mark.asyncio
async def test_keep_cut_draft_base_consumes_the_presented_timeline(monkeypatch):
    """未执行草稿 base: keep_cut 消费其已呈现计划时间轴 (base 板按 base 床
    网格 snap 的呈现值), 同样不是裸分配帧."""
    from app.tools.film.storyboard import execution_frames

    board = _board()
    old_track = _track("calm", _OLD_BEATS)
    # base = live pending v2, 快照带旧床网格 (呈现事实表按它 snap 过).
    presented = execution_frames(board, _OLD_BEATS)
    pending_before = _pending_with_film(
        board, _PARAMS, version=2, hold=False, track=old_track
    )
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    new_track = _track("upbeat", _NEW_BEATS, bpm=63.0)

    async def _named_track(db, project, mood):
        return new_track, new_track.meta["beats"]

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _named_track)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "keep_cut"}],
            base_ref=_base_ref(board, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_kept_frames == presented
    # 草稿冻结的场内切点 = 呈现时间轴的落字拍 (同一 onset 座, base 床网格).
    from app.tools.film.storyboard import draft_reveal_onsets

    presented_onsets = draft_reveal_onsets(
        board, presented, {"bpm": 60.0, "beats": _OLD_BEATS}
    )
    assert pending.film_kept_reveal_onsets == presented_onsets

    _stub_run_peripherals(monkeypatch, [_page()])
    new_output = await _run_film(
        board,
        new_track,
        {
            "film_music_retime": "keep_cut",
            "film_kept_frames": pending.film_kept_frames,
            "film_kept_reveal_onsets": pending.film_kept_reveal_onsets,
        },
    )
    assert [s["frames"] for s in new_output.render_spec["scenes"]] == presented
    # 场内落字拍同样冻结在呈现值 (永不压新床网格).
    assert [
        s.get("lead_frames") for s in new_output.render_spec["scenes"]
    ] == presented_onsets


@pytest.mark.asyncio
async def test_keep_cut_rejects_a_timeline_changing_batch(monkeypatch):
    """keep_cut 兼容律: 同批移动/删场/改秒 ⇒ keep_cut_incompatible 修复回声
    (指向 recut 或拆批), 零版本落库, marker 清."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_scene", "scene_id": "s5", "seconds": 6.0},
                {"op": "set_music", "mood": "upbeat", "retime": "keep_cut"},
            ],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "keep_cut_incompatible" in result and "recut" in result
    assert project.pending_brief == pending_before
    assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_run_fails_closed_when_the_kept_cut_is_missing(monkeypatch):
    """fail-closed: keep_cut 指令在场但冻结切点缺失/损坏 ⇒ 诚实失败,
    永不静默重卡."""
    board = _board()
    track = _track("upbeat", _NEW_BEATS)
    _stub_run_peripherals(monkeypatch, [_page()])

    with pytest.raises(ValueError, match="kept cut is missing"):
        await _run_film(board, track, {"film_music_retime": "keep_cut"})
    with pytest.raises(ValueError, match="kept cut is missing"):
        await _run_film(
            board,
            track,
            {
                "film_music_retime": "keep_cut",
                "film_kept_frames": [1, 2, 3],  # 场数不齐
            },
        )


@pytest.mark.asyncio
async def test_keep_cut_freezes_the_cut_against_narration_flex(monkeypatch):
    """旁白适配不得重新改变切点: keep_cut 下 flex 救援一旦要移动帧 ⇒
    诚实失败 (指引缩短台词或允许 recut), 永不交付被挪动过的「保持节奏」."""
    import app.tools.film.narration as narration_mod

    board = _board()
    track = _track("calm", _OLD_BEATS)
    sb_mod = _stub_run_peripherals(monkeypatch, [_page()])

    async def _no_persona(db, project):
        return None

    monkeypatch.setattr(sb_mod, "resolve_persona", _no_persona)

    kept = None

    async def _flexing_synthesis(**kwargs):
        # The flex rescue WANTS to move the cut (steal from silent scenes).
        nonlocal kept
        kept = kwargs["frames"]
        moved = list(kwargs["frames"])
        moved[0] += 12
        moved[7] -= 12
        return {}, moved, [{"scene": 0, "gained_s": 0.4}]

    monkeypatch.setattr(
        narration_mod, "synthesize_film_narration", _flexing_synthesis
    )

    from app.tools.film.storyboard import draft_reveal_onsets, execution_frames

    kept_frames = execution_frames(board, _OLD_BEATS)
    kept_onsets = draft_reveal_onsets(
        board, kept_frames, {"bpm": 60.0, "beats": _OLD_BEATS}
    )

    with pytest.raises(ValueError, match="outruns the kept cut"):
        await _run_film_with_voiceover(
            board,
            track,
            {
                "film_music_retime": "keep_cut",
                "film_kept_frames": kept_frames,
                "film_kept_reveal_onsets": kept_onsets,
            },
        )
    assert kept == kept_frames  # synthesis received the frozen cut verbatim

    # 继承腿: 冻结切点作为版本状态继承下来 (无 keep_cut 指令键) —— flex 冻结
    # 同门, 不因本轮没提音乐而放行.
    with pytest.raises(ValueError, match="outruns the kept cut"):
        await _run_film_with_voiceover(
            board,
            track,
            {
                "film_kept_frames": kept_frames,
                "film_kept_reveal_onsets": kept_onsets,
            },
        )


async def _run_film_with_voiceover(board, track, ctx_extra: dict):
    """_run_film 的配音变体 (slot voiceover 缺省 = on)."""
    from app.tools.film.storyboard import LaunchFilm

    pages = [_page()]
    db = _RunDB(track)
    node = SimpleNamespace(id=uuid4(), spec={"slot": {"type": "film"}})
    project = SimpleNamespace(id=uuid4(), language="en")
    ctx = {
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(pages=pages, track=track),
        **ctx_extra,
    }
    run = SimpleNamespace(id=uuid4(), context=ctx)
    await LaunchFilm().run(db, run, node, project)
    return db.added[0] if db.added else None


@pytest.mark.asyncio
async def test_edit_presentation_law_and_observation_speak_one_fork(monkeypatch):
    """最终组装一致性 (收尾项 3 的 prompt 半): gate-on 系统 prompt 的编辑拍
    呈现法与 patch 观察文本同一授权分岔 —— 两侧都不再要求无条件「同一问」."""
    from app.chat.prompts import chat_intent_system

    prompt = chat_intent_system()  # autouse gate ON
    assert "then the same ONE question" not in prompt
    assert "After an EDIT call" in prompt
    assert "Review hold off" in prompt and "review hold on" in prompt
    assert "COMPLETE CURRENT scene table" in prompt
    assert "ordinary modification calls answer" in prompt

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)
    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    obs = result.text
    assert "then ONE direct question" not in obs
    assert "keyed by the standing authorization" not in obs
    assert "FULL CURRENT SAVED BOARD" in obs
    assert "no new film has been produced" in obs
    # One fork, two seats: both key the next step on current intent + hold.
    assert "Review hold off" in obs and "review hold on" in obs
    assert "ordinary modification ends with" in obs


# ---------------------------------------------------------------------------
# 13. 冻结时间轴 = 版本状态 — 跨版继承 (问题 1) + 已执行基准不可读的结构化
#    拒绝 (问题 2, 真 resolve 座)
# ---------------------------------------------------------------------------


def _run_ctx(board, params, *, version=1, track=None) -> dict:
    """A run.context-shaped provenance stamp (真 resolve 座的输入行)."""
    return {
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_fingerprint": f"fp-v{version}",
        "film_storyboard_version": version,
        "film_storyboard_params": params,
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(
            pages=[_page()], track=track
        ),
        "film_created_via": "compose",
        "film_base_version": None,
    }


class _SeqDB:
    """Turn session stand-in for the REAL resolve seat: execute() answers
    queued result shims in call order (auth select → resolve selects)."""

    def __init__(self, results):
        self._results = list(results)

    async def execute(self, *args, **kwargs):
        return self._results.pop(0)

    async def flush(self):
        return None

    async def refresh(self, *args):
        return None


def _scalar(val):
    return SimpleNamespace(scalar_one_or_none=lambda: val)


def _row_or_none(val):
    return SimpleNamespace(one_or_none=lambda: val)


def _rows(rows):
    return SimpleNamespace(all=lambda: rows)


@pytest.mark.asyncio
async def test_frozen_cut_inherits_across_timeline_preserving_edits(monkeypatch):
    """问题 1 必验 (复现形状): 原片实跑 (旧床网格移动首/末幕切点)
    → set_music(upbeat, keep_cut) → set_voiceover(false) (本轮不提音乐)
    → 新 run 的逐场帧仍 == 原 spec。冻结切点是版本状态, 按实际变化失效 —
    不因本轮没有 set_music 而丢失, 也不回新床网格静默重卡."""
    from app.tools.film.edits import film_music_retime_of
    from app.tools.film.storyboard import allocate_frames, execution_frames

    board = _board()
    old_track = _track("calm", _OLD_BEATS)
    _stub_run_peripherals(monkeypatch, [_page()])

    # 1) 原片实跑: spec_A 逐场帧 = 旧床卡点时间轴 (snap 确实移动了切点).
    base_output = await _run_film(board, old_track, {})
    spec_a_frames = [s["frames"] for s in base_output.render_spec["scenes"]]
    assert spec_a_frames != allocate_frames(board)
    spec_a_onsets = [
        s.get("lead_frames") for s in base_output.render_spec["scenes"]
    ]

    # 2) 第一刀 (pin 道): set_music(upbeat, keep_cut) on the EXECUTED base.
    base = _provenance_base(board, _PARAMS, version=1, cut_state="spec")
    base.film_cut_frames = spec_a_frames
    base.film_cut_reveal_onsets = spec_a_onsets
    pending_before = _pending_with_film(board, _PARAMS, version=3)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(
        project, mentions=[SimpleNamespace(type="output", id=uuid4())]
    )

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, resolve_base=None, project=project)

    import app.tools.film.edits as edits_mod
    import app.tools.film.storyboard as sb_mod

    async def _resolve(db, project, *, output_id=None):
        return base

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    _kill_switch(monkeypatch)

    new_track = _track("upbeat", _NEW_BEATS, bpm=63.0)

    async def _named_track(db, project, mood):
        assert mood == "upbeat"
        return new_track, new_track.meta["beats"]

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _named_track)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "keep_cut"}],
            base_ref=_base_ref(board, _PARAMS, version=1, cut=film_base_cut(base)),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    v2 = PendingPlan.model_validate(project.pending_brief)
    assert v2.film_change_set["music"]["retime"] == "keep_cut"
    assert v2.film_kept_frames == spec_a_frames
    assert v2.film_kept_reveal_onsets == spec_a_onsets

    # 3) 第二刀 (live pending 道, 无 pin 无音乐 op): set_voiceover(false) —
    #    冻结切点作为版本状态继承, 不得清空.
    turn2 = _chat_turn(project)
    guards2 = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards2, project=project)
    _kill_switch(monkeypatch)

    result2 = await turn2._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(
                FilmStoryboard.model_validate(v2.film_storyboard),
                v2.film_storyboard_params,
                version=2,
                cut=film_base_cut(v2),
            ),
        ),
        "",
    )
    assert isinstance(result2, ToolObservation), result2
    v3 = PendingPlan.model_validate(project.pending_brief)
    assert v3.film_storyboard_version == 3
    assert v3.film_change_set["music"] is None
    assert v3.film_change_set["voiceover"] is False
    # 继承断点 = 本条断言: 第二轮没有 set_music, 冻结切点仍在 (场内落字
    # 拍同信封 —— 冻结时间轴的两半都不因本轮没提音乐而丢失).
    assert v3.film_kept_frames == spec_a_frames
    assert v3.film_kept_reveal_onsets == spec_a_onsets
    assert v3.film_cut_state == "kept"

    # 4) 新版本实跑 (Start stamping 投影): 无 retime 指令键, 冻结帧在场 ⇒
    #    run 消费冻结切点; voiceover off ⇒ 无旁白 flex. 逐场帧 == 原片.
    assert film_music_retime_of(v3) is None
    final_output = await _run_film(
        board,
        new_track,
        {
            "film_music_retime": film_music_retime_of(v3),
            "film_kept_frames": v3.film_kept_frames,
            "film_kept_reveal_onsets": v3.film_kept_reveal_onsets,
        },
    )
    spec_c_frames = [s["frames"] for s in final_output.render_spec["scenes"]]
    assert spec_c_frames == spec_a_frames
    # 场内落字拍也跨两刀逐帧一致 (问题 5 回归的链式形态).
    assert [
        s.get("lead_frames") for s in final_output.render_spec["scenes"]
    ] == spec_a_onsets
    # 对照: 若回缺省按新床网格重卡, 切点必移动 (分支有效性).
    assert execution_frames(board, _NEW_BEATS) != spec_a_frames


@pytest.mark.asyncio
async def test_recut_re_establishes_the_cut_on_the_new_grid(monkeypatch):
    """recut 对照腿 (失效按实际变化): 存活 recut 指令 ⇒ 冻结切点合法丢弃,
    新 run 按新床网格重 snap —— 切点移动, 旧帧不被盲目沿用."""
    from app.tools.film.storyboard import execution_frames

    board = _board()
    old_track = _track("calm", _OLD_BEATS)
    _stub_run_peripherals(monkeypatch, [_page()])
    base_output = await _run_film(board, old_track, {})
    spec_a_frames = [s["frames"] for s in base_output.render_spec["scenes"]]

    base = _provenance_base(board, _PARAMS, version=1, cut_state="spec")
    base.film_cut_frames = spec_a_frames
    pending_before = _pending_with_film(board, _PARAMS, version=3)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(
        project, mentions=[SimpleNamespace(type="output", id=uuid4())]
    )
    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, resolve_base=None, project=project)

    import app.tools.film.edits as edits_mod
    import app.tools.film.storyboard as sb_mod

    async def _resolve(db, project, *, output_id=None):
        return base

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    _kill_switch(monkeypatch)

    new_track = _track("upbeat", _NEW_BEATS, bpm=63.0)

    async def _named_track(db, project, mood):
        return new_track, new_track.meta["beats"]

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _named_track)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "recut"}],
            base_ref=_base_ref(board, _PARAMS, version=1, cut=film_base_cut(base)),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    v2 = PendingPlan.model_validate(project.pending_brief)
    assert v2.film_change_set["music"]["retime"] == "recut"
    # recut ⇒ 无冻结帧落库 (旧帧不沿用; 场内落字拍同律丢弃).
    assert v2.film_kept_frames is None
    assert v2.film_kept_reveal_onsets is None

    new_output = await _run_film(
        board,
        new_track,
        {
            "film_music_retime": "recut",
            "film_kept_frames": v2.film_kept_frames,
        },
    )
    recut_frames = [s["frames"] for s in new_output.render_spec["scenes"]]
    assert recut_frames == execution_frames(board, _NEW_BEATS)
    assert recut_frames != spec_a_frames


@pytest.mark.asyncio
async def test_unreadable_executed_spec_rejects_timeline_keeping_edits(
    monkeypatch,
):
    """问题 2 必验 (pin 道, 真 resolve 座): 已执行作品的 spec 缺失/损坏 ⇒
    恢复出的 base 带 cut_state="unreadable"; 保时间轴的 patch (keep_cut 换
    音乐 / 纯关旁白) 结构化拒绝 base_cut_unreadable, 不发布新版本, 原状态
    不变 —— 永不把损坏的冻结时间轴当普通草稿缺省静默重算."""
    _kill_switch(monkeypatch)
    for broken_spec in (None, {"scenes": [{"frames": 90}, {"noframes": 1}]}):
        for ops in (
            [{"op": "set_music", "mood": "upbeat", "retime": "keep_cut"}],
            [{"op": "set_voiceover", "enabled": False}],
        ):
            board = _board()
            project = SimpleNamespace(id=uuid4(), pending_brief={})
            turn = _chat_turn(
                project, mentions=[SimpleNamespace(type="output", id=uuid4())]
            )
            turn.db = _SeqDB(
                [
                    _scalar(uuid4()),  # authorizing message
                    _row_or_none((_run_ctx(board, _PARAMS), broken_spec)),
                ]
            )
            guards = _GuardStubs(marker_base_version=1)
            _patch_world(monkeypatch, guards, project=project)  # resolve NOT stubbed — 真座

            result = await turn._design_storyboard(
                _edit_args(
                edits=ops,
                base_ref=_base_ref(
                    board, _PARAMS, version=1, cut=("unreadable", None, None)
                ),
            ),
                "",
            )
            assert isinstance(result, str), (broken_spec, ops, result)
            assert "base_cut_unreadable" in result
            assert "recut" in result
            # 零版本落库 + 原状态不变 + 本 draft marker 清.
            assert project.pending_brief == {}
            assert turn._presentation_pending is None
            assert guards.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_provenance_base_cut_state_distinguishes_draft_from_unreadable(
    monkeypatch,
):
    """问题 2 (provenance 道, 真 resolve 座): 无 pin 无 live pending ⇒ 最新
    film run 恢复。

    - run 无 film output 行 ⇒ "draft": keep_cut 合法冻结其已呈现计划时间轴
      (base 板按 base 床网格 snap) —— 草稿缺省不被误判为损坏;
    - run 有 output 但 spec 损坏 ⇒ "unreadable": keep_cut 结构化拒绝,
      零版本落库."""
    import app.tools.film.edits as edits_mod

    board = _board()
    old_track = _track("calm", _OLD_BEATS)
    ctx = _run_ctx(board, _PARAMS, version=4, track=old_track)
    new_track = _track("upbeat", _NEW_BEATS, bpm=63.0)

    async def _named_track(db, project, mood):
        return new_track, new_track.meta["beats"]

    monkeypatch.setattr(edits_mod, "resolve_named_film_track", _named_track)

    from app.agents.tool_loop import ToolObservation

    # 腿 1: run 无 output ⇒ draft ⇒ keep_cut 冻结呈现时间轴 (成功发布).
    project = SimpleNamespace(id=uuid4(), pending_brief={})
    turn = _chat_turn(project)
    turn.db = _SeqDB(
        [
            _scalar(uuid4()),
            _rows([(ctx, uuid4())]),  # recent runs
            _row_or_none(None),  # no film output row
        ]
    )
    guards = _GuardStubs(marker_base_version=4)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "keep_cut"}],
            base_ref=_base_ref(board, _PARAMS, version=4),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    from app.tools.film.storyboard import draft_reveal_onsets, execution_frames

    presented = execution_frames(board, _OLD_BEATS)
    assert pending.film_kept_frames == presented
    assert pending.film_kept_reveal_onsets == draft_reveal_onsets(
        board, presented, {"bpm": 60.0, "beats": _OLD_BEATS}
    )
    assert pending.film_storyboard_version == 5

    # 腿 2: run 的 output spec 损坏 ⇒ unreadable ⇒ 结构化拒绝, 原状态不变.
    project2 = SimpleNamespace(id=uuid4(), pending_brief={})
    turn2 = _chat_turn(project2)
    turn2.db = _SeqDB(
        [
            _scalar(uuid4()),
            _rows([(ctx, uuid4())]),
            _row_or_none(({"scenes": [{"frames": 90}, {"noframes": 1}]},)),
        ]
    )
    guards2 = _GuardStubs(marker_base_version=4)
    _patch_world(monkeypatch, guards2, project=project2)
    _kill_switch(monkeypatch)

    result2 = await turn2._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "keep_cut"}],
            base_ref=_base_ref(
                board, _PARAMS, version=4, cut=("unreadable", None, None)
            ),
        ),
        "",
    )
    assert isinstance(result2, str)
    assert "base_cut_unreadable" in result2
    assert project2.pending_brief == {}
    assert guards2.cleared == ["draft-test"]


@pytest.mark.asyncio
async def test_frozen_version_recovers_from_run_context_before_any_output(
    monkeypatch,
):
    """复审 P2 复现形状: 冻结版本 Start 后 run 在 Output 创建前失败 —
    provenance 恢复不得丢 run.context 已持久化的冻结切点 (无 Output ≠
    普通草稿)。恢复 → 保时间轴编辑 (关旁白) → 执行 spec 逐场帧 == 原片."""
    from app.tools.film.storyboard import allocate_frames, execution_frames

    board = _board()
    old_track = _track("calm", _OLD_BEATS)
    _stub_run_peripherals(monkeypatch, [_page()])

    # 1) 原片实跑 → spec_A 逐场帧 (旧床 snap 确实移动了切点).
    base_output = await _run_film(board, old_track, {})
    spec_a_frames = [s["frames"] for s in base_output.render_spec["scenes"]]
    assert spec_a_frames != allocate_frames(board)

    # 2) keep_cut 版本 v2 被 Start: run.context 钉入冻结切点 + retime 指令
    #    (service.py stamping 形状), 但 run 在 Output 创建前失败 —
    #    pending 已被 Start 清空, 恢复只剩 provenance 道.
    v2_params = {**_PARAMS, "music_mood": "upbeat"}
    new_track = _track("upbeat", _NEW_BEATS, bpm=63.0)
    crashed_ctx = {
        **_run_ctx(board, v2_params, version=2, track=new_track),
        "film_music_retime": "keep_cut",
        "film_kept_frames": spec_a_frames,
        "film_kept_reveal_onsets": [
            s.get("lead_frames") for s in base_output.render_spec["scenes"]
        ],
    }
    project = SimpleNamespace(id=uuid4(), pending_brief={})
    turn = _chat_turn(project)
    turn.db = _SeqDB(
        [
            _scalar(uuid4()),
            _rows([(crashed_ctx, uuid4())]),  # recent runs
            _row_or_none(None),  # Output 尚未创建
        ]
    )
    guards = _GuardStubs(marker_base_version=2)
    _patch_world(monkeypatch, guards, project=project)  # resolve NOT stubbed — 真座
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    # 3) 保时间轴编辑 (关旁白): 恢复出的冻结切点继承进 v3 —— 不断链.
    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(
                board, v2_params, version=2,
                cut=("kept", spec_a_frames, crashed_ctx["film_kept_reveal_onsets"]),
            ),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    v3 = PendingPlan.model_validate(project.pending_brief)
    assert v3.film_storyboard_version == 3
    assert v3.film_kept_frames == spec_a_frames
    assert v3.film_kept_reveal_onsets == [
        s.get("lead_frames") for s in base_output.render_spec["scenes"]
    ]

    # 4) v3 实跑 (voiceover off): 逐场帧 == 原片; 新床网格若重卡必移动
    #    (对照).
    final_output = await _run_film(
        board,
        new_track,
        {
            "film_kept_frames": v3.film_kept_frames,
            "film_kept_reveal_onsets": v3.film_kept_reveal_onsets,
        },
    )
    assert [
        s["frames"] for s in final_output.render_spec["scenes"]
    ] == spec_a_frames
    assert [
        s.get("lead_frames") for s in final_output.render_spec["scenes"]
    ] == [
        s.get("lead_frames") for s in base_output.render_spec["scenes"]
    ]
    assert execution_frames(board, _NEW_BEATS) != spec_a_frames


@pytest.mark.asyncio
async def test_corrupt_frozen_state_in_run_context_never_degrades_to_draft(
    monkeypatch,
):
    """provenance 恢复 (真座): run.context 的冻结状态损坏 / keep_cut 指令
    无帧 ⇒ "unreadable" —— 保时间轴编辑结构化拒绝, 永不静默退回普通草稿
    按呈现时间轴重算; 零版本落库, 原状态不变."""
    from app.tools.film.storyboard import resolve_film_revision_base

    board = _board()
    track = _track("calm", _OLD_BEATS)
    bad_contexts = [
        # 冻结帧损坏 (场数不齐)
        {
            **_run_ctx(board, _PARAMS, version=2, track=track),
            "film_music_retime": "keep_cut",
            "film_kept_frames": [1, 2, 3],
        },
        # keep_cut 指令在场但帧缺失 (半写信封)
        {
            **_run_ctx(board, _PARAMS, version=2, track=track),
            "film_music_retime": "keep_cut",
        },
        # 帧在场、无指令键、但低于结构下限
        {
            **_run_ctx(board, _PARAMS, version=2, track=track),
            "film_kept_frames": [0] * 14,
        },
    ]
    _kill_switch(monkeypatch)
    for ctx in bad_contexts:
        # 恢复面直证: state unreadable, 无切点帧.
        probe = SimpleNamespace(id=uuid4(), pending_brief={})
        probe_db = _SeqDB([_rows([(ctx, uuid4())]), _row_or_none(None)])
        base = await resolve_film_revision_base(probe_db, probe)
        assert base is not None
        assert base.film_cut_state == "unreadable"
        assert base.film_cut_frames is None

        # patch 面: 保时间轴编辑 (关旁白) 结构化拒绝, 不发布新版本.
        project = SimpleNamespace(id=uuid4(), pending_brief={})
        turn = _chat_turn(project)
        turn.db = _SeqDB(
            [
                _scalar(uuid4()),
                _rows([(ctx, uuid4())]),
                _row_or_none(None),
            ]
        )
        guards = _GuardStubs(marker_base_version=2)
        _patch_world(monkeypatch, guards, project=project)

        result = await turn._design_storyboard(
            _edit_args(
                edits=[{"op": "set_voiceover", "enabled": False}],
                base_ref=_base_ref(
                    board, _PARAMS, version=2, cut=("unreadable", None, None)
                ),
            ),
            "",
        )
        assert isinstance(result, str), result
        assert "base_cut_unreadable" in result
        assert "recut" in result
        assert project.pending_brief == {}
        assert guards.cleared == ["draft-test"]


# ---------------------------------------------------------------------------
# Text-source film patch chain (素材源分派 — 文字片走完整编辑链)
# ---------------------------------------------------------------------------

_TEXT_COPY = (
    "好的内容，不该只出现一次。\n"
    "一场分享，可以长成文章、短片和讨论。\n"
    "你把专业讲好，助手负责送到更多人面前。"
)

_TEXT_PARAMS = {
    "text": _TEXT_COPY,
    "verbatim": True,
    "target_seconds": 14.0,
    "voiceover": False,
    "aspect": "9:16",
}


def _text_board() -> FilmStoryboard:
    return FilmStoryboard.model_validate(
        {
            "name": None,
            "language": "zh",
            "scenes": [
                {"type": "words", "seconds": 4.0, "dark": False,
                 "lines": ["好的内容，不该只出现一次。"]},
                {"type": "words", "seconds": 5.0, "dark": True,
                 "lines": ["一场分享，可以长成文章、短片和讨论。"]},
                {"type": "words", "seconds": 5.0, "dark": False,
                 "lines": ["你把专业讲好，助手负责送到更多人面前。"]},
            ],
        }
    )


@pytest.mark.asyncio
async def test_text_film_patch_chain_never_consults_pages(monkeypatch):
    """文字片编辑链 (素材源分派): a text film's patch grounds on its own
    pinned copy — the page seat is NEVER consulted (no capture exists or is
    needed), the real text-mode validator runs, an explicit copy edit
    re-declares the version's corpus pin, motion/enter/seconds land, and
    the published version's snapshot carries no pages."""
    board = _text_board()
    pending_before = _pending_with_film(board, _TEXT_PARAMS, version=1)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project, text="第二幕换个说法，慢推，逐字出现")

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    async def _no_pages(db, project):
        raise AssertionError("load_storyboard_pages on a text film patch")

    monkeypatch.setattr(edits_mod, "load_storyboard_pages", _no_pages)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {
                    "op": "update_scene",
                    "scene_id": "s2",
                    "copy_slots": {"lines": ["一次分享，也能持续长出新的讨论。"]},
                    "motion": "push",
                    "enter": "words",
                    "seconds": 6.0,
                }
            ],
            base_ref=_base_ref(board, _TEXT_PARAMS, version=1),
        ),
        "",
    )
    from app.agents.tool_loop import ToolObservation

    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 2
    assert pending.film_created_via == "patch"
    new_board = FilmStoryboard.model_validate(pending.film_storyboard)
    scene = new_board.scenes[1]
    assert scene.lines == ["一次分享，也能持续长出新的讨论。"]
    assert scene.motion == "push" and scene.enter == "words"
    assert scene.seconds == 6.0
    # The corpus pin followed the explicit copy edit (新文案不再撞旧原稿校验);
    # untouched scenes' words carry over byte-identical.
    new_text = pending.film_storyboard_params["text"]
    assert "一次分享，也能持续长出新的讨论。" in new_text
    assert "一场分享" not in new_text
    assert "好的内容，不该只出现一次。" in new_text
    assert "你把专业讲好，助手负责送到更多人面前。" in new_text
    # The change set reports the REAL delta (retime lands in retimed, never
    # a silent whole-film re-layout).
    change_set = pending.film_change_set
    assert change_set["edited"] == [
        {"scene_id": "s2", "fields": ["enter", "lines", "motion"], "notes": []}
    ]
    assert change_set["retimed"] == [
        {"scene_id": "s2", "seconds_before": 5.0, "seconds_after": 6.0}
    ]
    # The new version's execution snapshot carries NO pages (text source).
    assert pending.film_storyboard_execution["pages"] == []
    # Fingerprint parity: the approval dock recomputes THIS key off the
    # version's params (synced text included) + the frozen birth narrative →
    # reuse, never redraft.
    assert pending.film_storyboard_fingerprint == storyboard_fingerprint(
        [{"tool": "launch_film", "params": pending.film_storyboard_params}],
        pending.prompt,
    )
    # The presentation shows the computed change lines + the next base_ref.
    assert "PATCH of version 1" in result.text
    next_ref = _base_ref(new_board, dict(pending.film_storyboard_params), version=2)
    assert next_ref in result.text


@pytest.mark.asyncio
async def test_text_film_patch_fast_pace_is_the_users_choice(monkeypatch):
    """逐幕时间 = 用户法律 (2026-10-22 拍板 — 估计 = 建议非边界): an explicit
    seconds patch below the reading-time estimate is the user's faster-pace
    choice — it LANDS (never a gate, never a silent re-layout); the REAL
    refusal that remains is a non-positive window (a zero scene renders
    nothing)."""
    board = _text_board()
    pending_before = _pending_with_film(board, _TEXT_PARAMS, version=1)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project, text="第三幕压到 1 秒")

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "update_scene", "scene_id": "s3", "seconds": 1.0}],
            base_ref=_base_ref(board, _TEXT_PARAMS, version=1),
        ),
        "",
    )
    # 1s for a ~5s-read line: the explicit faster pace LANDS.
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 2
    new_board = FilmStoryboard.model_validate(pending.film_storyboard)
    assert new_board.scenes[2].seconds == 1.0

    # The REAL duration refusal: a zero window is illegal data — the edit
    # layer's own positivity check names it (never the reading estimate).
    # The follow-up edit rides the NEXT turn (同回合唯一设计闸: a same-turn
    # second design is refused at the dispatch seat), so a fresh turn
    # carries it against the v2 world the first patch left.
    turn2 = _chat_turn(project, text="第三幕压到 0 秒")
    result = await turn2._design_storyboard(
        _edit_args(
            edits=[{"op": "update_scene", "scene_id": "s3", "seconds": 0.0}],
            base_ref=_base_ref(
                new_board, dict(pending.film_storyboard_params), version=2
            ),
        ),
        "",
    )
    assert isinstance(result, str)
    assert "invalid_field" in result
    assert "positive" in result


# ---------------------------------------------------------------------------
# Text-film compile→run journey (plan→step 参数投影契约 + 执行契约护栏)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_film_compiled_slot_carries_the_text_source_to_run(monkeypatch):
    """参数投影契约全链: the REAL compiler's launch_film slot carries
    text/verbatim/target_seconds/scene_count alongside voiceover/music/
    aspect; the REAL LaunchFilm.run then consumes THAT compiled slot (never
    a hand-built one) — the text path never consults the page seat, never
    re-designs (the confirmed board is consumed), voiceover off = zero
    synthesis, music off = no bed."""
    from app.pipeline.orchestrator import TaskSpec, _compile_task_list

    params = {
        "text": _TEXT_COPY,
        "verbatim": True,
        "target_seconds": 14.0,
        "voiceover": False,
        "music_mood": "off",
        "aspect": "9:16",
        "language": "zh",
    }
    task = TaskSpec(
        tasks=[{"tool": "launch_film", "params": params}],
        target_language="zh",
    )
    nodes = _compile_task_list(task)
    film_nodes = [n for n in nodes if n.kind == "launch_film"]
    assert len(film_nodes) == 1
    slot = film_nodes[0].spec["slot"]
    # The projection carries the text source WHOLE (exclude_none keeps a
    # web film's slot byte-clean of these keys — the web legs below).
    assert slot["text"] == _TEXT_COPY
    assert slot["verbatim"] is True
    assert slot["target_seconds"] == 14.0
    assert slot["voiceover"] is False
    assert slot["music_mood"] == "off"
    assert slot["aspect"] == "9:16"

    board = _text_board()
    _stub_run_peripherals(monkeypatch, [])

    import app.tools.film.storyboard as sb_mod

    async def _no_pages(db, project):
        raise AssertionError("load_storyboard_pages on a text-film run")

    async def _no_orchestration(*args, **kwargs):
        raise AssertionError("the director ran on a confirmed text version")

    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _no_pages)
    monkeypatch.setattr(sb_mod, "orchestrate_storyboard", _no_orchestration)
    monkeypatch.setattr(sb_mod.film_text_director, "call", _no_orchestration)

    node = SimpleNamespace(id=uuid4(), spec=film_nodes[0].spec)
    ctx = {
        "instruction": "用这段文字做一支短片",
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(pages=[], track=None),
        "film_storyboard_params": params,
    }
    from app.tools.film.storyboard import LaunchFilm

    run = SimpleNamespace(id=uuid4(), context=ctx)
    db = _RunDB(None)
    project = SimpleNamespace(id=uuid4(), language="zh")
    ids = await LaunchFilm().run(db, run, node, project)
    assert len(ids) == 1
    output = db.added[0]
    assert "music" not in output.render_spec  # music off: no bed
    assert len(output.render_spec["scenes"]) == len(board.scenes)


@pytest.mark.asyncio
async def test_text_film_run_with_a_lost_text_source_fails_the_contract(
    monkeypatch,
):
    """执行契约护栏: a run whose version PINNED a text source but whose
    compiled slot lost it (the pre-fix projection's persisted shape) fails
    honestly as a broken plan→step handoff — NEVER as a web capture
    failure, NEVER pointing the user at a link. The page seat is not
    consulted (the guard fires first)."""
    from app.pipeline.orchestrator import TaskSpec, _compile_task_list

    params = {
        "text": _TEXT_COPY,
        "verbatim": True,
        "voiceover": False,
        "music_mood": "off",
        "aspect": "9:16",
    }
    task = TaskSpec(tasks=[{"tool": "launch_film", "params": params}])
    nodes = _compile_task_list(task)
    film_spec = [n for n in nodes if n.kind == "launch_film"][0].spec
    # Replay the pre-fix damage: the persisted step whose slot lost the
    # text source keys.
    damaged = {
        **film_spec,
        "slot": {
            k: v
            for k, v in film_spec["slot"].items()
            if k not in ("text", "verbatim", "target_seconds", "scene_count")
        },
    }
    assert "text" not in damaged["slot"]

    board = _text_board()
    _stub_run_peripherals(monkeypatch, [])

    import app.tools.film.storyboard as sb_mod

    async def _no_pages(db, project):
        raise AssertionError("the guard must fire before the page seat")

    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _no_pages)

    node = SimpleNamespace(id=uuid4(), spec=damaged)
    ctx = {
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(pages=[], track=None),
        # The confirmed version's params still pin the text source — THAT
        # mismatch is what makes this a broken execution contract.
        "film_storyboard_params": params,
    }
    from app.tools.film.storyboard import LaunchFilm

    run = SimpleNamespace(id=uuid4(), context=ctx)
    with pytest.raises(ValueError) as exc_info:
        await LaunchFilm().run(
            _RunDB(None), run, node, SimpleNamespace(id=uuid4(), language="zh")
        )
    message = str(exc_info.value)
    assert "TEXT film" in message
    assert "never reached the production step" in message
    assert "capture" not in message and "link" not in message.lower()


@pytest.mark.asyncio
async def test_web_film_slot_stays_byte_clean_of_text_keys():
    """网页片回归: a web launch_film task's compiled slot carries NO text
    keys (exclude_none drops them) — the projection extension never leaks
    text-source fields onto the web chain."""
    from app.pipeline.orchestrator import TaskSpec, _compile_task_list

    task = TaskSpec(
        tasks=[
            {
                "tool": "launch_film",
                "params": {"voiceover": True, "music_mood": "calm",
                           "aspect": "16:9", "focus": "product"},
            }
        ]
    )
    nodes = _compile_task_list(task)
    slot = [n for n in nodes if n.kind == "launch_film"][0].spec["slot"]
    assert slot["voiceover"] is True and slot["music_mood"] == "calm"
    assert slot["aspect"] == "16:9" and slot["focus"] == "product"
    for key in ("text", "verbatim", "target_seconds", "scene_count"):
        assert key not in slot


# ---------------------------------------------------------------------------
# Batch B: timing survives the confirmed board → run → render_spec chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_consumes_prepared_board_timing_into_the_render_spec(monkeypatch):
    """编译链证明 (Batch B): timing 是分镜内容, 不骑 launch slot 白名单 —
    真 LaunchFilm.run 消费确认的 prepared_storyboard, render_spec 逐场携带
    set 的时序字段 (explicit zero 在内), null 键不进 spec; 未设置的场保持
    legacy 形态. 编译白名单不丢字段, 因为字段根本不经由它."""
    board = _board()
    raw = board.model_dump(mode="json")
    raw["scenes"][0].update(
        {"enter": "words", "enter_start": 0.3, "enter_interval": 0.12,
         "enter_duration": 0.25}
    )
    raw["scenes"][7].update({"enter": "words", "enter_start": 0.0})
    board = FilmStoryboard.model_validate(raw)

    _stub_run_peripherals(monkeypatch, [_page()])
    output = await _run_film(board, _track("calm", _OLD_BEATS), {})
    scenes = output.render_spec["scenes"]
    assert scenes[0]["enter"] == "words"
    assert scenes[0]["enter_start"] == 0.3
    assert scenes[0]["enter_interval"] == 0.12
    assert scenes[0]["enter_duration"] == 0.25
    assert "enter_hold_until" not in scenes[0]  # null stays out
    assert scenes[7]["enter_start"] == 0.0  # explicit zero survives
    # Untouched words scenes keep the legacy byte-shape.
    assert "enter_start" not in scenes[8] and "enter" not in scenes[8]


# ---------------------------------------------------------------------------
# Batch B: Start stamping → compile → executor — the timing's full journey
# ---------------------------------------------------------------------------


class _StartDB:
    """answer_question Start 链的会话 stand-in: get 按模型分派到夹具行,
    execute 回空结果集 (项目行锁 / 素材唤醒 update / 活动 run 检查都用不
    到结果), add 收集落库对象 (run + steps), commit/refresh 空转."""

    def __init__(self, *, message, conversation, project, user):
        from app.models.tables import Conversation, Message, Project, User

        self._rows = {
            Message: message,
            Conversation: conversation,
            Project: project,
            User: user,
        }
        self.added: list = []

    async def get(self, model, key, with_for_update=False):
        return self._rows.get(model)

    async def execute(self, *args, **kwargs):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: []),
            scalar_one_or_none=lambda: None,
        )

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


@pytest.mark.asyncio
async def test_start_stamping_carries_confirmed_timing_into_the_render_spec(
    monkeypatch,
):
    """Start 全链 (Batch B 补环): 确认版分镜携带时序参数 → 真
    answer_question(kind="start") 的 stamping 块把它钉进 run.context → 真
    create_run / compile_graph 编译 → 真 LaunchFilm.run 消费那条
    run.context 与编译出的 step → render_spec 逐场携带时序.

    被验证环节全真 (stamping / 编译 / 执行器), 只有正交外设 stub: 生命周期
    采集 (有独立门禁测试)、草稿图投影、计费扣划、图填充、页座. 永不手造
    run.context —— context 由生产代码产出."""
    import app.chat.service as chat_service
    import app.pipeline.exploration_store as exploration_store
    import app.pipeline.graph_fill as graph_fill
    import app.pipeline.lifecycle as lifecycle
    import app.pipeline.orchestrator as orchestrator
    from app.chat.service import answer_question
    from app.models.schemas import InferredIntent, PendingPlan, StartAnswerRequest
    from app.models.tables import WorkflowRun, WorkflowStep

    # 确认版分镜: 第二幕带用户参数例的时序.
    raw = _text_board().model_dump(mode="json")
    raw["scenes"][1].update(
        {"enter": "words", "enter_start": 0.3, "enter_interval": 0.12,
         "enter_duration": 0.25}
    )
    board = FilmStoryboard.model_validate(raw)
    params = {**_TEXT_PARAMS, "music_mood": "off"}  # 无音乐无配音腿
    intent = InferredIntent.model_validate(
        {
            "action": "draft",
            "name": "文字片",
            "tasks": [{"tool": "launch_film", "params": params}],
        }
    )
    pending = PendingPlan(
        prompt="用这段文字做一支短片",
        intent=intent,
        film_storyboard=board.model_dump(mode="json"),
        film_storyboard_fingerprint="fp-v1",
        film_storyboard_version=1,
        film_storyboard_params=params,
        film_storyboard_content_digest=storyboard_content_digest(board),
        film_storyboard_execution=build_film_execution_snapshot(
            pages=[], track=None
        ),
        film_review_hold=False,
        film_draft_token="tok-b",
        film_design_authorized_by="u1",
    ).model_dump(mode="json")

    uid, cid, pid = uuid4(), uuid4(), uuid4()
    message = SimpleNamespace(
        id=uuid4(),
        conversation_id=cid,
        question={
            "kind": "task_book",
            "question": "确认开始制作吗？",
            "film_draft_token": "tok-b",
            "film_storyboard_version": 1,
        },
        answer=None,
        workflow_run_id=None,
    )
    conversation = SimpleNamespace(id=cid, user_id=uid, project_id=pid)
    project = SimpleNamespace(
        id=pid, user_id=uid, pending_brief=pending, status=None,
        language="zh",
    )
    user = SimpleNamespace(id=uid, settings={})
    db = _StartDB(
        message=message, conversation=conversation, project=project, user=user
    )

    async def _noop_async(*args, **kwargs):
        return None

    async def _false_async(*args, **kwargs):
        return False

    async def _zero_async(*args, **kwargs):
        return 0

    async def _facts_async(*args, **kwargs):
        return {}

    async def _lifecycle_stamp(*args, **kwargs):
        return lifecycle.LifecycleStamp(
            state="ready",
            material_ready=True,
            plan_ready=True,
            confirmation_scope_ready=True,
            charge_semantics_ready=True,
            no_active_conflicting_run=True,
            confirmation_ready=True,
        )

    # Orthogonal peripherals only — the stamping block, the compiler and the
    # executor under test stay real.
    monkeypatch.setattr(lifecycle, "project_lifecycle", _lifecycle_stamp)
    monkeypatch.setattr(graph_fill, "stamp_draft_graph", _noop_async)
    monkeypatch.setattr(exploration_store, "mark_compiled", _noop_async)
    monkeypatch.setattr(chat_service, "get_config", _noop_async)
    monkeypatch.setattr(orchestrator, "has_active_run", _false_async)
    monkeypatch.setattr(orchestrator, "_check_birthplace_requires", _noop_async)
    monkeypatch.setattr(orchestrator, "_needs_stills_alignment", _false_async)
    monkeypatch.setattr(orchestrator, "_materialize_profile", _noop_async)
    monkeypatch.setattr(orchestrator, "_estimate_facts", _facts_async)
    monkeypatch.setattr(orchestrator, "stamp_run_graph", _noop_async)
    monkeypatch.setattr(orchestrator, "credits_for_cost", _zero_async)
    monkeypatch.setattr(orchestrator, "check_hold", _noop_async)
    monkeypatch.setattr(orchestrator, "hold_run", _noop_async)

    answered, follow_up = await answer_question(
        db, uid, message.id, StartAnswerRequest(kind="start")
    )
    assert follow_up is None

    # ① stamping: run.context 由生产代码钉入, 确认版的时序逐字节在场.
    run = next(o for o in db.added if isinstance(o, WorkflowRun))
    stamped = run.context.get("prepared_storyboard")
    assert stamped is not None, "Start stamping dropped the confirmed board"
    stamped_scene = stamped["scenes"][1]
    assert stamped_scene["enter_start"] == 0.3
    assert stamped_scene["enter_interval"] == 0.12
    assert stamped_scene["enter_duration"] == 0.25
    # ② 编译: launch_film slot 不携带时序键 (时序是分镜内容, 不是 launch
    # 参数) — 它骑 stamped board, 不经 slot 白名单.
    step = next(
        o for o in db.added
        if isinstance(o, WorkflowStep) and o.kind == "launch_film"
    )
    slot = step.spec["slot"]
    assert slot["text"] == params["text"]
    for key in ("enter_start", "enter_interval", "enter_duration"):
        assert key not in slot
    assert project.pending_brief is None  # confirmed: the pending copy dropped

    # ③ 执行器: 真 LaunchFilm.run 消费那条 run.context + 编译出的 step.
    _stub_run_peripherals(monkeypatch, [])
    import app.tools.film.storyboard as sb_mod

    async def _no_pages(db, project):
        raise AssertionError("load_storyboard_pages on a text-film run")

    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _no_pages)
    from app.tools.film.storyboard import LaunchFilm

    run.id = run.id or uuid4()  # the fake flush never fires the id default
    run_db = _RunDB(None)
    ids = await LaunchFilm().run(
        run_db,
        run,
        step,
        SimpleNamespace(id=pid, language="zh", persona_id=None, user_id=uid),
    )
    assert len(ids) == 1
    spec_scene = run_db.added[0].render_spec["scenes"][1]
    assert spec_scene["enter"] == "words"
    assert spec_scene["enter_start"] == 0.3
    assert spec_scene["enter_interval"] == 0.12
    assert spec_scene["enter_duration"] == 0.25
    assert "enter_hold_until" not in spec_scene  # null stays out
    # 未设时序的场保持 legacy 形态.
    assert "enter_start" not in run_db.added[0].render_spec["scenes"][0]


@pytest.mark.asyncio
async def test_start_stamping_carries_composite_elements_into_the_render_spec(
    monkeypatch,
):
    """复审②: composite 元素经真实确认版 stamping → 编译 → run 消费到
    render_spec 的全旅程 (ADR-140). 复用 Start 链 harness; 被验证环节全真
    (answer_question 的 stamping 块 / create_run 编译 / LaunchFilm.run),
    只有正交外设 stub (生命周期采集 / 图投影 / 计费 / 页座 / 素材行读取).
    永不手造 run.context —— context 由生产代码产出."""
    import app.chat.service as chat_service
    import app.pipeline.exploration_store as exploration_store
    import app.pipeline.graph_fill as graph_fill
    import app.pipeline.lifecycle as lifecycle
    import app.pipeline.orchestrator as orchestrator
    from app.chat.service import answer_question
    from app.models.schemas import InferredIntent, PendingPlan, StartAnswerRequest
    from app.models.tables import WorkflowRun, WorkflowStep
    from app.tools.film.edits import ensure_scene_ids

    # 确认版分镜: 一个 composite 幕 (右半视频段 + 左半独立时序文字),
    # 身份句柄经出生座铸好 (e1/e2).
    board = ensure_scene_ids(_composite_text_board())
    params = {**_TEXT_PARAMS, "music_mood": "off"}  # 无音乐无配音腿
    media = _composite_media()
    intent = InferredIntent.model_validate(
        {
            "action": "draft",
            "name": "组合片",
            "tasks": [{"tool": "launch_film", "params": params}],
        }
    )
    pending = PendingPlan(
        prompt="用我的素材片段做一支短片",
        intent=intent,
        film_storyboard=board.model_dump(mode="json"),
        film_storyboard_fingerprint="fp-c1",
        film_storyboard_version=1,
        film_storyboard_params=params,
        film_storyboard_content_digest=storyboard_content_digest(board),
        # The design-time snapshot's media pins ride the version — the run's
        # drift gate compares against THESE.
        film_storyboard_execution=build_film_execution_snapshot(
            pages=[], track=None, media=media
        ),
        film_review_hold=False,
        film_draft_token="tok-c1",
        film_design_authorized_by="u1",
    ).model_dump(mode="json")

    uid, cid, pid = uuid4(), uuid4(), uuid4()
    message = SimpleNamespace(
        id=uuid4(),
        conversation_id=cid,
        question={
            "kind": "task_book",
            "question": "确认开始制作吗？",
            "film_draft_token": "tok-c1",
            "film_storyboard_version": 1,
        },
        answer=None,
        workflow_run_id=None,
    )
    conversation = SimpleNamespace(id=cid, user_id=uid, project_id=pid)
    project = SimpleNamespace(
        id=pid, user_id=uid, pending_brief=pending, status=None,
        language="zh",
    )
    user = SimpleNamespace(id=uid, settings={})
    db = _StartDB(
        message=message, conversation=conversation, project=project, user=user
    )

    async def _noop_async(*args, **kwargs):
        return None

    async def _false_async(*args, **kwargs):
        return False

    async def _zero_async(*args, **kwargs):
        return 0

    async def _facts_async(*args, **kwargs):
        return {}

    async def _lifecycle_stamp(*args, **kwargs):
        return lifecycle.LifecycleStamp(
            state="ready",
            material_ready=True,
            plan_ready=True,
            confirmation_scope_ready=True,
            charge_semantics_ready=True,
            no_active_conflicting_run=True,
            confirmation_ready=True,
        )

    # Orthogonal peripherals only — the stamping block, the compiler and the
    # executor under test stay real.
    monkeypatch.setattr(lifecycle, "project_lifecycle", _lifecycle_stamp)
    monkeypatch.setattr(graph_fill, "stamp_draft_graph", _noop_async)
    monkeypatch.setattr(exploration_store, "mark_compiled", _noop_async)
    monkeypatch.setattr(chat_service, "get_config", _noop_async)
    monkeypatch.setattr(orchestrator, "has_active_run", _false_async)
    monkeypatch.setattr(orchestrator, "_check_birthplace_requires", _noop_async)
    monkeypatch.setattr(orchestrator, "_needs_stills_alignment", _false_async)
    monkeypatch.setattr(orchestrator, "_materialize_profile", _noop_async)
    monkeypatch.setattr(orchestrator, "_estimate_facts", _facts_async)
    monkeypatch.setattr(orchestrator, "stamp_run_graph", _noop_async)
    monkeypatch.setattr(orchestrator, "credits_for_cost", _zero_async)
    monkeypatch.setattr(orchestrator, "check_hold", _noop_async)
    monkeypatch.setattr(orchestrator, "hold_run", _noop_async)

    answered, follow_up = await answer_question(
        db, uid, message.id, StartAnswerRequest(kind="start")
    )
    assert follow_up is None

    # ① stamping: run.context 由生产代码钉入, composite 元素逐字段在场
    #    (身份句柄 / 源区间 / 摆放 / 时间窗), 执行快照的 media 钉随行.
    run = next(o for o in db.added if isinstance(o, WorkflowRun))
    stamped = run.context.get("prepared_storyboard")
    assert stamped is not None, "Start stamping dropped the confirmed board"
    stamped_scene = next(s for s in stamped["scenes"] if s["type"] == "composite")
    assert [e["element_id"] for e in stamped_scene["elements"]] == ["e1", "e2"]
    svideo = stamped_scene["elements"][0]
    assert svideo["source_start"] == 10.0 and svideo["source_end"] == 18.0
    assert svideo["rect"] == {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}
    stext = stamped_scene["elements"][1]
    assert stext["lines"] == ["一场分享", "持续被看见"]
    assert stext["at"] == 1.0 and stext["until"] == 7.0
    media_pins = run.context["film_execution"].get("media")
    assert media_pins == [
        {"asset_id": _COMPOSITE_ASSET_ID, "key": "u/demo/video.mp4"}
    ]
    # ② 编译: launch_film slot 不携带元素键 (元素是分镜内容, 不是 launch
    #    参数) — 它骑 stamped board, 不经 slot 白名单.
    step = next(
        o for o in db.added
        if isinstance(o, WorkflowStep) and o.kind == "launch_film"
    )
    slot = step.spec["slot"]
    assert slot["text"] == params["text"]
    for key in ("elements", "source_start", "source_end", "rect", "at", "until"):
        assert key not in slot
    assert project.pending_brief is None  # confirmed: the pending copy dropped

    # ③ 执行器: 真 LaunchFilm.run 消费那条 run.context + 编译出的 step;
    #    素材行读取 (load_storyboard_media) 是正交外设, stub 出同一 media
    #    宇宙 (钉的 id+key 一致 → 漂移闸通过).
    _stub_run_peripherals(monkeypatch, [])
    import app.tools.film.storyboard as sb_mod

    async def _no_pages(db, project):
        raise AssertionError("load_storyboard_pages on a text-film run")

    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _no_pages)
    _media_stub(monkeypatch, sb_mod, media)
    from app.tools.film.storyboard import LaunchFilm

    run.id = run.id or uuid4()  # the fake flush never fires the id default
    run_db = _RunDB(None)
    ids = await LaunchFilm().run(
        run_db,
        run,
        step,
        SimpleNamespace(id=pid, language="zh", persona_id=None, user_id=uid),
    )
    assert len(ids) == 1
    spec = run_db.added[0].render_spec
    spec_scene = next(s for s in spec["scenes"] if s["type"] == "composite")
    assert spec_scene["frames"] == 240
    rvideo = spec_scene["elements"][0]
    assert rvideo["kind"] == "video" and rvideo["id"] == "e1"
    # 素材身份在编译座解算: id → 存储 key (模型/版本永不写 URL).
    assert rvideo["src"] == "u/demo/video.mp4"
    assert rvideo["source_start"] == 10.0 and rvideo["source_end"] == 18.0
    assert rvideo["rect"] == {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}
    assert rvideo["keep_audio"] is False
    rtext = spec_scene["elements"][1]
    assert rtext["kind"] == "text" and rtext["id"] == "e2"
    assert rtext["lines"] == ["一场分享", "持续被看见"]
    assert rtext["at"] == 1.0 and rtext["until"] == 7.0
    assert rtext["enter"] == "words" and rtext["enter_interval"] == 0.3
    # 呈现稿 digest = run context digest = render spec digest (一处真值).
    assert spec["provenance"]["storyboard_digest"] == storyboard_content_digest(
        board
    )


@pytest.mark.asyncio
async def test_pinned_read_threads_that_outputs_own_landed_bed():
    """配乐事实座 (事故 7886d879, 真 resolve 座): 钉读旧 Output 时 base 携带
    该 Output 自己交付 spec 里的床 — 钉恒胜, 永不借当前草稿的计划; 钉读的
    交付无床时如实 None (cut_state="spec" 区分「spec 无床」与「草稿根本
    没有 spec_music」)."""
    from app.tools.film.storyboard import resolve_film_revision_base

    board = _board()
    track = _track("calm", _OLD_BEATS)
    ctx = _run_ctx(board, _PARAMS, version=2, track=track)
    scenes = [{"frames": 96}, {"frames": 270}, {"frames": 150}]
    project = SimpleNamespace(id=uuid4(), pending_brief={})

    spec = {
        "scenes": scenes,
        "music": {"url": f"music/{track.id}.mp3", "gain_db": -20.0, "bpm": 60.0},
    }
    db = _SeqDB([_row_or_none((ctx, spec))])
    base = await resolve_film_revision_base(db, project, output_id=uuid4())
    assert base is not None
    assert base.film_cut_state == "spec"
    assert base.film_render_spec_music == spec["music"]

    # 钉读一个无床的交付: spec_music 如实 None, 不是草稿计划的替身.
    db = _SeqDB([_row_or_none((ctx, {"scenes": scenes}))])
    base = await resolve_film_revision_base(db, project, output_id=uuid4())
    assert base is not None
    assert base.film_cut_state == "spec"
    assert base.film_render_spec_music is None


@pytest.mark.asyncio
async def test_run_fallback_read_threads_the_delivered_bed():
    """配乐事实座 run 回退支路 (真座, 交付回合 get_output_spec 的读取路径):
    最新 film run 的交付 Output 有床 ⇒ base 携带该 spec 的 music 块; 无床
    ⇒ None (由 cut_state="spec" 与草稿区分)."""
    from app.tools.film.storyboard import resolve_film_revision_base

    board = _board()
    track = _track("calm", _OLD_BEATS)
    ctx = _run_ctx(board, _PARAMS, version=2, track=track)
    spec = {
        "scenes": [{"frames": 96}, {"frames": 270}, {"frames": 150}],
        "music": {"url": f"music/{track.id}.mp3", "gain_db": -20.0, "bpm": 60.0},
    }
    project = SimpleNamespace(id=uuid4(), pending_brief={})
    db = _SeqDB([_rows([(ctx, uuid4())]), _row_or_none((spec,))])
    base = await resolve_film_revision_base(db, project)
    assert base is not None
    assert base.film_cut_state == "spec"
    assert base.film_render_spec_music == spec["music"]

    db = _SeqDB(
        [_rows([(ctx, uuid4())]), _row_or_none(({"scenes": spec["scenes"]},))]
    )
    base = await resolve_film_revision_base(db, project)
    assert base is not None
    assert base.film_cut_state == "spec"
    assert base.film_render_spec_music is None


# ---------------------------------------------------------------------------
# Composite scenes (ADR-140) — the media composition closed loop on the REAL
# wiring: chat edit turn → patch beat → version publish; confirmed version →
# LaunchFilm.run → render spec. All external seats stubbed, the composition
# core real.
# ---------------------------------------------------------------------------

_COMPOSITE_ASSET_ID = "11111111-1111-1111-1111-111111111111"


def _composite_text_board() -> FilmStoryboard:
    """A text-source film carrying one composite scene (a video segment on
    the right + an independently timed text element on the left)."""
    return FilmStoryboard.model_validate(
        {
            "name": None,
            "language": "zh",
            "scenes": [
                {"type": "words", "seconds": 4.0, "dark": False,
                 "lines": ["好的内容，不该只出现一次。"]},
                {
                    "type": "composite",
                    "seconds": 8.0,
                    "elements": [
                        {"kind": "video", "asset": _COMPOSITE_ASSET_ID,
                         "source_start": 10.0, "source_end": 18.0, "at": 0.0,
                         "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}},
                        {"kind": "text", "lines": ["一场分享", "持续被看见"],
                         "at": 1.0, "until": 7.0,
                         "rect": {"x": 0.05, "y": 0.3, "w": 0.4, "h": 0.4},
                         "enter": "words", "enter_interval": 0.3},
                    ],
                },
                {"type": "words", "seconds": 5.0, "dark": False,
                 "lines": ["你把专业讲好，助手负责送到更多人面前。"]},
            ],
        }
    )


def _composite_media(*, duration: float | None = 25.0, key: str = "u/demo/video.mp4"):
    from app.tools.film.storyboard import StoryboardMedia, StoryboardMediaAsset

    return StoryboardMedia(
        assets={
            _COMPOSITE_ASSET_ID: StoryboardMediaAsset(
                id=_COMPOSITE_ASSET_ID, key=key, kind="video",
                title="Demo clip", duration_seconds=duration,
                width=1920, height=1080,
            )
        }
    )


def _media_stub(monkeypatch, mod, media, calls: list | None = None):
    async def _load(db, project, board, *, probe_duration=False):
        if calls is not None:
            calls.append(probe_duration)
        return media

    monkeypatch.setattr(mod, "load_storyboard_media", _load)


@pytest.mark.asyncio
async def test_composite_patch_chain_update_element(monkeypatch):
    """结构化编辑闭环: update_element ops on a composite scene ride the REAL
    patch beat — presence semantics, per-element change set, media pins in
    the new version's snapshot, the write seat's duration probing."""
    board = _composite_text_board()
    params = dict(_TEXT_PARAMS)
    pending_before = _pending_with_film(board, params, version=1)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project, text="左边文字从第 2 秒再开始，逐字间隔放慢一点")

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    probe_calls: list[bool] = []
    _media_stub(monkeypatch, edits_mod, _composite_media(), probe_calls)

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_element", "scene_id": "s2", "element_id": "e2",
                 "at": 2.0, "enter_interval": 0.5},
            ],
            base_ref=_base_ref(board, params, version=1),
        ),
        "",
    )
    from app.agents.tool_loop import ToolObservation

    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    assert pending.film_storyboard_version == 2
    assert pending.film_created_via == "patch"
    new_board = FilmStoryboard.model_validate(pending.film_storyboard)
    old_scene = next(s for s in board.scenes if s.type == "composite")
    new_scene = next(s for s in new_board.scenes if s.type == "composite")
    el = new_scene.elements[1]
    assert el.at == 2.0 and el.enter_interval == 0.5
    # 未修改内容保持: the video element and the other scenes byte-identical
    # (element_id excluded — the birth-assigned identity handle is never
    # content, the digest law's own exclusion).
    def _content(el: dict) -> dict:
        return {k: v for k, v in el.items() if k != "element_id"}

    assert _content(old_scene.elements[0].model_dump(mode="json")) == _content(
        new_scene.elements[0].model_dump(mode="json")
    )
    assert new_board.scenes[0].lines == board.scenes[0].lines
    assert new_board.scenes[2].lines == board.scenes[2].lines
    # The system-computed change set reads per element.
    assert pending.film_change_set["edited"] == [
        {"scene_id": "s2",
         "fields": ["elements.e2.at", "elements.e2.enter_interval"],
         "notes": []}
    ]
    # The new version's execution snapshot carries the media identity pin.
    assert pending.film_storyboard_execution["media"] == [
        {"asset_id": _COMPOSITE_ASSET_ID, "key": "u/demo/video.mp4"}
    ]
    # The patch beat is a WRITE seat: unknown durations probe (flag on).
    assert probe_calls == [True]
    # The presentation shows the element NOW line.
    assert "[e2] now: on screen 2s–7s" in result.text


@pytest.mark.asyncio
async def test_one_sentence_multi_change_rides_one_atomic_edits_batch(
    monkeypatch,
):
    """同回合唯一设计闸的配套能力证 (2026-10-23 收尾拍板③): 闸把同回合第二
    次设计拒在 dispatch 座, 因此一句话里的多个修改必须能放进**一个** edits
    批次一次落全 — 文案 + 入场时机 + 视频位置三处变化骑同一批次出生一个
    版本; 混入任一非法 op = 整批原子拒, 旧版本字节不动, 回声逐条点名违规
    (部分完成永不宣称全部完成)."""
    board = _composite_text_board()
    params = dict(_TEXT_PARAMS)
    pending_before = _pending_with_film(board, params, version=1)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(
        project, text="左侧文字改成「下周三上线，记得来看」，从第 2 秒再出现；视频挪到左半边"
    )

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    _media_stub(monkeypatch, edits_mod, _composite_media())

    from app.agents.tool_loop import ToolObservation

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_element", "scene_id": "s2", "element_id": "e2",
                 "lines": ["下周三上线，", "记得来看"], "at": 2.0},
                {"op": "update_element", "scene_id": "s2", "element_id": "e1",
                 "rect": {"x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0}},
            ],
            base_ref=_base_ref(board, params, version=1),
        ),
        "",
    )
    assert isinstance(result, ToolObservation), result
    pending = PendingPlan.model_validate(project.pending_brief)
    # ONE batch → ONE version, all three changes landed.
    assert pending.film_storyboard_version == 2
    assert len(guards.begin_calls) == 1
    new_board = FilmStoryboard.model_validate(pending.film_storyboard)
    scene = next(s for s in new_board.scenes if s.type == "composite")
    video, text = scene.elements[0], scene.elements[1]
    assert text.lines == ["下周三上线，", "记得来看"]
    assert text.at == 2.0
    assert video.rect.x == 0.0
    # 逐字片的文字源随板走 (编辑后语料重声明, _sync_text_source 一座).
    assert "下周三上线" in (pending.film_storyboard_params or {}).get("text", "")
    # change_set 逐元素点名三处变化.
    edited = pending.film_change_set["edited"]
    fields = {f for e in edited for f in e["fields"]}
    assert {"elements.e2.lines", "elements.e2.at", "elements.e1.rect"} <= fields

    # 部分完成 = 整批原子拒: 一个合法 op + 一个越界 op 同批 → 零落笔,
    # v2 字节不动, 修复回声点名违规 (真实校验器, 非 stub).
    v2_brief = dict(project.pending_brief)
    turn2 = _chat_turn(project, text="文字再快一点，视频源窗挪到第 24 到 30 秒")
    result2 = await turn2._design_storyboard(
        _edit_args(
            edits=[
                {"op": "update_element", "scene_id": "s2", "element_id": "e2",
                 "enter_interval": 0.8},
                {"op": "update_element", "scene_id": "s2", "element_id": "e1",
                 "source_start": 24.0, "source_end": 30.0},
            ],
            base_ref=_base_ref(
                new_board,
                dict(pending.film_storyboard_params),
                version=2,
            ),
        ),
        "",
    )
    assert isinstance(result2, str), result2  # repair echo, not a version
    assert "source" in result2 or "30" in result2
    assert project.pending_brief == v2_brief  # nothing landed, not even the valid op


@pytest.mark.asyncio
async def test_composite_patch_media_gate_rejects_out_of_range_edit(
    monkeypatch,
):
    """错误边界: an edit moving the source window past the probed duration
    rejects as validation_failed — the version stands untouched."""
    board = _composite_text_board()
    params = dict(_TEXT_PARAMS)
    pending_before = _pending_with_film(board, params, version=1)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project, text="素材往后挪到第 20 秒开始")

    guards = _GuardStubs(marker_base_version=1)
    _patch_world(monkeypatch, guards, project=project)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    _media_stub(monkeypatch, edits_mod, _composite_media(duration=25.0))

    result = await turn._design_storyboard(
        _edit_args(
            edits=[
                # 20 + 8 = 28s > the asset's 25s — a concrete conflict.
                {"op": "update_element", "scene_id": "s2", "element_id": "e1",
                 "source_start": 20.0, "source_end": 28.0},
            ],
            base_ref=_base_ref(board, params, version=1),
        ),
        "",
    )
    from app.agents.tool_loop import ToolObservation

    # The repair echo is plain model-facing text (never a dock, never a
    # published version) and names the concrete conflict verbatim.
    assert isinstance(result, str) and not isinstance(result, ToolObservation)
    assert "runs 25" in result
    # The live version stands byte-identical (v1, nothing published).
    assert project.pending_brief["film_storyboard_version"] == 1


@pytest.mark.asyncio
async def test_composite_run_chain_builds_the_render_spec(monkeypatch):
    """编译+执行闭环: a confirmed composite version runs the REAL
    LaunchFilm.run — the spec's composite scene resolves asset id → storage
    key, windows land on snapped frames, no audio promised."""
    from app.pipeline.orchestrator import TaskSpec, _compile_task_list

    board = _composite_text_board()
    params = {
        "text": _TEXT_COPY,
        "verbatim": True,
        "voiceover": False,
        "music_mood": "off",
        "aspect": "16:9",
    }
    task = TaskSpec(tasks=[{"tool": "launch_film", "params": params}])
    film_spec = [n for n in _compile_task_list(task) if n.kind == "launch_film"][0].spec

    media = _composite_media()
    _stub_run_peripherals(monkeypatch, [])

    import app.tools.film.storyboard as sb_mod

    probe_calls: list[bool] = []
    _media_stub(monkeypatch, sb_mod, media, probe_calls)

    async def _no_orchestration(*args, **kwargs):
        raise AssertionError("the director ran on a confirmed composite version")

    monkeypatch.setattr(sb_mod, "orchestrate_storyboard", _no_orchestration)
    monkeypatch.setattr(sb_mod.film_text_director, "call", _no_orchestration)

    node = SimpleNamespace(id=uuid4(), spec=film_spec)
    ctx = {
        "instruction": "用这段文字和素材做一支短片",
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(
            pages=[], track=None, media=media
        ),
        "film_storyboard_params": params,
    }
    from app.tools.film.storyboard import LaunchFilm

    run = SimpleNamespace(id=uuid4(), context=ctx)
    db = _RunDB(None)
    ids = await LaunchFilm().run(
        db, run, node, SimpleNamespace(id=uuid4(), language="zh")
    )
    assert len(ids) == 1
    spec = db.added[0].render_spec
    scene = next(s for s in spec["scenes"] if s["type"] == "composite")
    assert scene["frames"] == 240  # 8s @30fps
    video, text = scene["elements"]
    assert video["src"] == "u/demo/video.mp4"
    assert video["source_start"] == 10.0 and video["source_end"] == 18.0
    assert video["keep_audio"] is False
    assert text["lines"] == ["一场分享", "持续被看见"]
    assert text["enter"] == "words" and text["enter_interval"] == 0.3
    assert "enter_start" not in text  # null stays out of the spec
    # No narration, no bed, no original sound → no audio promised anywhere.
    assert "music" not in spec
    assert all("audio" not in s for s in spec["scenes"])
    assert probe_calls and probe_calls[0] is True  # the run seat probes


@pytest.mark.asyncio
async def test_composite_run_media_drift_fails_honestly(monkeypatch):
    """快照漂移: the pinned media key changed since the design beat (asset
    replaced) — the run fails honestly, never silently re-resolves."""
    from app.pipeline.orchestrator import TaskSpec, _compile_task_list

    board = _composite_text_board()
    params = {
        "text": _TEXT_COPY,
        "verbatim": True,
        "voiceover": False,
        "music_mood": "off",
        "aspect": "16:9",
    }
    task = TaskSpec(tasks=[{"tool": "launch_film", "params": params}])
    film_spec = [n for n in _compile_task_list(task) if n.kind == "launch_film"][0].spec

    stamped_media = _composite_media(key="u/demo/original.mp4")
    current_media = _composite_media(key="u/demo/replaced.mp4")
    _stub_run_peripherals(monkeypatch, [])

    import app.tools.film.storyboard as sb_mod

    _media_stub(monkeypatch, sb_mod, current_media)

    node = SimpleNamespace(id=uuid4(), spec=film_spec)
    ctx = {
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(
            pages=[], track=None, media=stamped_media
        ),
        "film_storyboard_params": params,
    }
    from app.tools.film.storyboard import LaunchFilm

    run = SimpleNamespace(id=uuid4(), context=ctx)
    with pytest.raises(ValueError) as exc_info:
        await LaunchFilm().run(
            _RunDB(None), run, node, SimpleNamespace(id=uuid4(), language="zh")
        )
    assert "drifted" in str(exc_info.value)


@pytest.mark.asyncio
async def test_composite_run_probed_duration_gates_honestly(monkeypatch):
    """两闸门律: the design seat saw an UNKNOWN duration (no rejection); the
    run seat probes the truth (5s) and the 18s source window fails the
    re-validation honestly — never a clamp, never a guess."""
    from app.pipeline.orchestrator import TaskSpec, _compile_task_list

    board = _composite_text_board()
    params = {
        "text": _TEXT_COPY,
        "verbatim": True,
        "voiceover": False,
        "music_mood": "off",
        "aspect": "16:9",
    }
    task = TaskSpec(tasks=[{"tool": "launch_film", "params": params}])
    film_spec = [n for n in _compile_task_list(task) if n.kind == "launch_film"][0].spec

    # Design-time stamp: duration unknown (dormant asset) — identity pinned.
    stamped_media = _composite_media(duration=None)
    # Run-time truth: the probe found 5s — source_end 18 overshoots.
    probed_media = _composite_media(duration=5.0)
    _stub_run_peripherals(monkeypatch, [])

    import app.tools.film.storyboard as sb_mod

    _media_stub(monkeypatch, sb_mod, probed_media)

    node = SimpleNamespace(id=uuid4(), spec=film_spec)
    ctx = {
        "prepared_storyboard": board.model_dump(mode="json"),
        "film_storyboard_content_digest": storyboard_content_digest(board),
        "film_execution": build_film_execution_snapshot(
            pages=[], track=None, media=stamped_media
        ),
        "film_storyboard_params": params,
    }
    from app.tools.film.storyboard import LaunchFilm

    run = SimpleNamespace(id=uuid4(), context=ctx)
    with pytest.raises(ValueError) as exc_info:
        await LaunchFilm().run(
            _RunDB(None), run, node, SimpleNamespace(id=uuid4(), language="zh")
        )
    # The honest refusal asks for a redesign (the validator named the
    # overshoot upstream of it) — never a trimmed window.
    assert "redesign" in str(exc_info.value)
