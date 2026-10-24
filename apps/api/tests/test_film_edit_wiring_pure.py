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
6. **呈现契约** — the observation carries ONLY the system-computed change
   lines + the next version's base_ref; the patched version's fingerprint
   recomputes equal at the approval dock (reuse, never a redraft).
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


def _base_ref(board: FilmStoryboard, params: dict, *, version: int) -> str:
    return film_version_identity_digest(board, params, version=version)


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


class _GuardStubs:
    """Recording stubs for the marker machinery (patched onto
    app.tools.film.storyboard)."""

    def __init__(self, *, live_version=None, marker_base_version=None):
        self.begin_calls: list[dict] = []
        self.cleared: list[str] = []
        self.live_version = live_version
        self.marker_base_version = marker_base_version

    async def begin(self, db, project, *, base_version, user_message_id):
        self.begin_calls.append({"base_version": base_version})
        return "draft-test"

    async def clear(self, db, project, *, draft_id):
        self.cleared.append(draft_id)

    async def read_state(self, project_id):
        return (
            {"draft_id": "draft-test", "base_version": self.marker_base_version},
            self.live_version,
        )


def _patch_world(monkeypatch, guards: _GuardStubs, *, resolve_base=None):
    """Wire the stub seats: marker machinery + revision-base resolution +
    the patch beat's DB dependencies (pages present, silent snapshot music).
    """
    import app.tools.film.edits as edits_mod
    import app.tools.film.storyboard as sb_mod

    monkeypatch.setattr(sb_mod, "begin_film_draft", guards.begin)
    monkeypatch.setattr(sb_mod, "clear_film_draft_marker", guards.clear)
    monkeypatch.setattr(sb_mod, "read_committed_film_state", guards.read_state)
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
    _patch_world(monkeypatch, guards)

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
        live_version=3, marker_base_version=1  # committed world still holds v3
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    _patch_world(monkeypatch, guards, resolve_base=_resolve)
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
        {"scene_id": "s5", "fields": ["narration"]}
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
    # The observation presents ONLY the change lines + the next base_ref.
    assert "PATCH of version 1" in result.text
    assert "edited — fields: narration" in result.text
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

    guards = _GuardStubs(live_version=3, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    _patch_world(monkeypatch, guards)

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
        live_version=2,  # 本 patch 的 begin 之后, committed pending 推进到 v2
        marker_base_version=1,
    )

    async def _resolve(db, project, *, output_id=None):
        return base

    _patch_world(monkeypatch, guards, resolve_base=_resolve)
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
async def test_happy_path_on_the_live_pending_with_zero_director_calls(
    monkeypatch,
):
    """闸 2 + 版本信封: live pending v2 → patch → v3, envelope 落库,
    hold 延续 base 的 standing hold (编辑拍永不代释放), 全部导演座炸毁仍成功."""
    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=True)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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

    _patch_world(monkeypatch, _GuardStubs(), resolve_base=_resolve_none)
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
    _kill_switch(monkeypatch)

    import app.tools.film.edits as edits_mod

    track = SimpleNamespace(
        id=uuid4(), mood="upbeat",
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


# ---------------------------------------------------------------------------
# 3. PlanTurn parity — the plan path's patch branch rides the same seats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_turn_patch_branch_lands_the_version(monkeypatch):
    from app.chat.plan_turn import PlanTurn

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))

    turn = PlanTurn.__new__(PlanTurn)
    turn.db = _StubDB()
    turn.user_id = uuid4()
    turn.conversation_id = uuid4()
    turn.project = project
    turn.request = SimpleNamespace(mentions=[], persona_id=None)
    turn.text = "换掉配乐"
    turn.on_phase = None
    turn.on_activity = None
    turn.on_candidates = None
    turn.on_row_append = None
    turn._presentation_pending = None
    turn.stored = None
    turn.mention_exemplar_id = None

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    # review_hold is the legal companion; null tolerance on both new keys
    ok = _edit_args(
        edits=[{"op": "set_voiceover", "enabled": False}],
        base_ref="x",
        review_hold=True,
    )
    assert ok.review_hold is True
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
        f'({frames[0]}f) · shows: "Ship faster" (dark) · silent'
    ) in text
    assert (
        f'[s2] hero · authored 5s · planned {frames[1] / 30:g}s ({frames[1]}f) '
        '· shows: word: "Ship faster" · sub: "Acme turns hours of release '
        'work into minutes." · narration: "Meet Acme."'
    ) in text
    # 取景/视图引用: the ui scene's view + camera text ride the scene line.
    assert '[s3] ui · authored 9s' in text and 'view: page 0 shot 0 "(top)"' in text
    assert 'music mood "none"' in text
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
    # 画幅诚实文案: 不再导向重设计, 而是诚实「暂不支持」
    assert "no aspect change" not in on["description"]
    assert "never offer a redesign as the workaround" in on["description"]

    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    off = tool_spec(_DESIGN_STORYBOARD_TOOL)["function"]
    props = off["parameters"].get("properties", {})
    assert "edits" not in props and "base_ref" not in props
    assert "TARGETED EDITS" not in off["description"]
    assert "base_ref" not in off["description"]
    assert not off["parameters"].get("$defs")  # op models never leak
    # The compose capability stands either way.
    assert "Design the website film's storyboard" in off["description"]
    monkeypatch.setattr("app.config.settings.film_edits_enabled", True)
    assert "edits" in tool_spec(_DESIGN_STORYBOARD_TOOL)["function"]["parameters"]["properties"]


def test_prompt_law_prunes_the_edit_path_when_gated_off(monkeypatch):
    """prompt 面门控: 两个系统 prompt 的编辑法条随门控收放; compose 法不动."""
    from app.chat.prompts import chat_intent_system, intent_router_system

    assert "base_ref" in intent_router_system()  # autouse gate ON

    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    off_router = intent_router_system()
    off_chat = chat_intent_system()
    for text in (off_router, off_chat):
        assert "base_ref" not in text
        assert "A TARGETED change" not in text
        assert "An edited version carries NO new hold" not in text
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
    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    from app.chat.plan_turn import PlanTurn

    project2 = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    pturn = PlanTurn.__new__(PlanTurn)
    pturn.db = _StubDB()
    pturn.user_id = uuid4()
    pturn.conversation_id = uuid4()
    pturn.project = project2
    pturn.request = SimpleNamespace(mentions=[], persona_id=None)
    pturn.text = "换掉配乐"
    pturn.on_phase = None
    pturn.on_activity = None
    pturn.on_candidates = None
    pturn.on_row_append = None
    pturn._presentation_pending = None
    pturn.stored = None
    pturn.mention_exemplar_id = None
    result2 = await pturn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(v2, _PARAMS, version=2),
        ),
        "",
    )
    assert isinstance(result2, str) and "does not accept edits" in result2
    assert project2.pending_brief == pending_before


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
        f'({frames[0]}f) · shows: "Ship faster" (dark) · silent'
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    assert "keyed by the standing authorization" in result.text
    # The hold fork: this base carries a standing hold → the observation
    # says so and names the hold's release seat.
    assert "review hold ON" in result.text
    assert "the ONE production question" in result.text
    assert "propose_tasks" in result.text


@pytest.mark.asyncio
async def test_patch_observation_plan_path_same_deconfliction(monkeypatch):
    """去冲突 (plan 路镜像): 同法, 提案动词为 present_plan."""
    from app.chat.plan_turn import PlanTurn

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))

    turn = PlanTurn.__new__(PlanTurn)
    turn.db = _StubDB()
    turn.user_id = uuid4()
    turn.conversation_id = uuid4()
    turn.project = project
    turn.request = SimpleNamespace(mentions=[], persona_id=None)
    turn.text = "换掉配乐"
    turn.on_phase = None
    turn.on_activity = None
    turn.on_candidates = None
    turn.on_row_append = None
    turn._presentation_pending = None
    turn.stored = None
    turn.mention_exemplar_id = None

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    assert "keyed by the standing authorization" in result.text
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

    turn = PlanTurn.__new__(PlanTurn)
    turn.db = _StubDB()
    turn.user_id = uuid4()
    turn.conversation_id = uuid4()
    turn.project = project
    turn.request = SimpleNamespace(mentions=[], persona_id=None)
    turn.text = "删掉第十场"
    turn.on_phase = None
    turn.on_activity = None
    turn.on_candidates = None
    turn.on_row_append = None
    turn._presentation_pending = None
    turn.stored = None
    turn.mention_exemplar_id = None

    guards = _GuardStubs(live_version=3, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    from app.chat.plan_turn import PlanTurn

    project2 = SimpleNamespace(id=uuid4(), pending_brief=None)
    pturn = PlanTurn.__new__(PlanTurn)
    pturn.db = _StubDB()
    pturn.user_id = uuid4()
    pturn.conversation_id = uuid4()
    pturn.project = project2
    pturn.request = SimpleNamespace(mentions=[], persona_id=None)
    pturn.text = "做一支官网短片"
    pturn.on_phase = None
    pturn.on_activity = None
    pturn.on_candidates = None
    pturn.on_row_append = None
    pturn._presentation_pending = None
    pturn.stored = None
    pturn.mention_exemplar_id = None
    guards2 = _GuardStubs()
    _compose_world(monkeypatch, guards2, marker_draft="other-draft")
    result2 = await pturn._design_storyboard(_edit_args(focus="x"), "")
    assert isinstance(result2, str) and "discarded" in result2
    assert guards2.cleared == ["draft-test"]
    assert project2.pending_brief is None


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


async def _run_film(board, track, ctx_extra: dict):
    """真 LaunchFilm.run (stub 外设) → 产出 spec 的逐场 frames."""
    from app.tools.film.storyboard import LaunchFilm

    pages = [_page()]
    db = _RunDB(track)
    node = SimpleNamespace(
        id=uuid4(), spec={"slot": {"type": "film", "voiceover": False}}
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

    guards = _GuardStubs(live_version=3, marker_base_version=1)
    _patch_world(monkeypatch, guards, resolve_base=None)

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
            base_ref=_base_ref(board, _PARAMS, version=1),
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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

    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    assert "review hold off" in prompt and "review hold on" in prompt

    v2 = _board()
    pending_before = _pending_with_film(v2, _PARAMS, version=2, hold=False)
    project = SimpleNamespace(id=uuid4(), pending_brief=dict(pending_before))
    turn = _chat_turn(project)
    guards = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards)
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
    assert "keyed by the standing authorization" in obs
    # One fork, two seats: both key the next step on review hold + intent.
    assert "review hold off" in obs and "review hold on" in obs


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

    guards = _GuardStubs(live_version=3, marker_base_version=1)
    _patch_world(monkeypatch, guards, resolve_base=None)

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
            base_ref=_base_ref(board, _PARAMS, version=1),
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
    guards2 = _GuardStubs(live_version=2, marker_base_version=2)
    _patch_world(monkeypatch, guards2)
    _kill_switch(monkeypatch)

    result2 = await turn2._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(
                FilmStoryboard.model_validate(v2.film_storyboard),
                v2.film_storyboard_params,
                version=2,
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
    guards = _GuardStubs(live_version=3, marker_base_version=1)
    _patch_world(monkeypatch, guards, resolve_base=None)

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
            base_ref=_base_ref(board, _PARAMS, version=1),
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
            guards = _GuardStubs(live_version=None, marker_base_version=1)
            _patch_world(monkeypatch, guards)  # resolve NOT stubbed — 真座

            result = await turn._design_storyboard(
                _edit_args(edits=ops, base_ref=_base_ref(board, _PARAMS, version=1)),
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
    guards = _GuardStubs(live_version=None, marker_base_version=4)
    _patch_world(monkeypatch, guards)
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
    guards2 = _GuardStubs(live_version=None, marker_base_version=4)
    _patch_world(monkeypatch, guards2)
    _kill_switch(monkeypatch)

    result2 = await turn2._design_storyboard(
        _edit_args(
            edits=[{"op": "set_music", "mood": "upbeat", "retime": "keep_cut"}],
            base_ref=_base_ref(board, _PARAMS, version=4),
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
    guards = _GuardStubs(live_version=None, marker_base_version=2)
    _patch_world(monkeypatch, guards)  # resolve NOT stubbed — 真座
    _kill_switch(monkeypatch)

    from app.agents.tool_loop import ToolObservation

    # 3) 保时间轴编辑 (关旁白): 恢复出的冻结切点继承进 v3 —— 不断链.
    result = await turn._design_storyboard(
        _edit_args(
            edits=[{"op": "set_voiceover", "enabled": False}],
            base_ref=_base_ref(board, v2_params, version=2),
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
        guards = _GuardStubs(live_version=None, marker_base_version=2)
        _patch_world(monkeypatch, guards)

        result = await turn._design_storyboard(
            _edit_args(
                edits=[{"op": "set_voiceover", "enabled": False}],
                base_ref=_base_ref(board, _PARAMS, version=2),
            ),
            "",
        )
        assert isinstance(result, str), result
        assert "base_cut_unreadable" in result
        assert "recut" in result
        assert project.pending_brief == {}
        assert guards.cleared == ["draft-test"]
