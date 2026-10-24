"""7276ef13 定点收尾③ — 真实隔离 PostgreSQL 的 marker 协议验证.

The pure wiring suites stub the marker seats; this file runs the CORE
transaction machinery — begin / clear / the committed publish reads — against
a disposable real Postgres database (``_isolated_database`` — the composite
lifecycle suite's same pattern). Only the LLM seat (``prepare_dock_storyboard``)
and the patch beat's auxiliaries (pages / snapshot track) are stubbed.

Covered law:
- 首稿 → 同回合纠正 → 提交: the correction publishes on the in-turn version
  with NO second begin (the self-lock stays theoretical), the committed row
  lands the LATEST candidate, and the turn commit retires the marker (the
  new pending carries none — 无 marker 残留).
- 失败分支: a drafting failure runs the REAL begin + REAL clear — the
  committed row stands byte-identical, no marker leaks.
- 过期分支: a lapsed-budget marker fails BOTH publish guards closed
  (compose AND patch — the liveness halves are consistent), the old
  committed state is never overwritten.
- 接管分支: a foreign marker discards our draft and is never touched by
  our clear; the committed pending stands.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = pytest.mark.asyncio


async def _isolated_database():
    """A disposable database on the configured Postgres server (the
    composite lifecycle suite's same seat — jsonb + row locks speak real
    SQL, SQLite cannot stand in). Returns (engine, admin_engine, db_name)."""
    from app.config import settings
    from app.models.database import Base
    from app.models import tables  # noqa: F401 — register every table

    url = settings.database_url
    if not url.startswith("postgresql"):
        pytest.skip("configured database is not Postgres")
    server = url.rsplit("/", 1)[0]
    name = f"rep_itest_{uuid4().hex[:12]}"
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception:
        await admin.dispose()
        pytest.skip("local Postgres unreachable or CREATE DATABASE denied")
    engine = create_async_engine(f"{server}/{name}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, admin, name


def _text_board():
    from app.models.schemas import FilmStoryboard
    from app.tools.film.edits import ensure_scene_ids

    return ensure_scene_ids(
        FilmStoryboard.model_validate(
            {
                "name": None,
                "language": "zh",
                "scenes": [
                    {"type": "words", "seconds": 4.0, "dark": False,
                     "lines": ["好的内容，不该只出现一次。"]},
                    {"type": "words", "seconds": 5.0, "dark": True,
                     "lines": ["一场分享，可以长成文章、短片和讨论。"]},
                ],
            }
        )
    )


_TEXT_PARAMS = {
    "text": "好的内容，不该只出现一次。\n一场分享，可以长成文章、短片和讨论。",
    "verbatim": True,
    "voiceover": False,
    "music_mood": "off",
    "aspect": "9:16",
    "language": "zh",
}


def _dock(board, *, reused=False):
    from app.tools.film.storyboard import DockStoryboard

    return DockStoryboard(
        presentation="fact sheet",
        storyboard=board.model_dump(mode="json"),
        fingerprint="fp-itest",
        reused=reused,
        execution=None,
    )


def _v1_pending() -> dict:
    """A committed version-1 PendingPlan envelope (film_design_state's real
    construction — no LLM seat involved)."""
    from app.models.schemas import PendingPlan
    from app.tools.film.storyboard import film_design_state

    version_state = film_design_state(
        None,
        film=_dock(_text_board()),
        design_params=dict(_TEXT_PARAMS),
        review_hold=True,
        authorized_by=None,
    )
    assert version_state["film_storyboard_version"] == 1
    return PendingPlan(prompt="逐字稿成片", **version_state).model_dump(mode="json")


def _plan_turn(db, project, *, text):
    """A PlanTurn mid-turn stand-in over the REAL session (the pure suites'
    `_plan_turn` harness shape — every turn-state field initialized)."""
    from app.chat.plan_turn import PlanTurn

    turn = PlanTurn.__new__(PlanTurn)
    turn.db = db
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


def _stub_director(monkeypatch, board=None):
    """The LLM seat's only stub: the drafting call returns a prebuilt
    board. Everything transactional stays REAL."""
    import app.tools.film.storyboard as sb_mod

    async def _prepared(db, project, **kwargs):
        return _dock(board or _text_board())

    monkeypatch.setattr(sb_mod, "prepare_dock_storyboard", _prepared)


def _spy_begin(monkeypatch):
    """Wrap the REAL begin (never replace it) — the call count proves the
    correction never re-begins while the real lock/write protocol runs."""
    import app.tools.film.storyboard as sb_mod

    real_begin = sb_mod.begin_film_draft
    calls: list[dict] = []

    async def _spy(*args, **kwargs):
        calls.append(kwargs)
        return await real_begin(*args, **kwargs)

    monkeypatch.setattr(sb_mod, "begin_film_draft", _spy)
    return calls



def _version_state(pend: dict) -> dict:
    """「旧状态不被覆盖」的断言口径: compare the VERSIONED world (board /
    params / lineage) — the two keys the marker protocol LEGITIMATELY moves
    are excluded and asserted separately: ``film_draft_inflight`` (retired =
    absent or None) and ``film_draft_token`` (begin's documented
    supersession — 旧确认作废 at every begin)."""
    return {
        k: v
        for k, v in pend.items()
        if k not in ("film_draft_inflight", "film_draft_token")
    }


async def _committed_pending(factory, project_id):
    async with factory() as session:
        return (
            await session.execute(
                text("SELECT pending_brief FROM projects WHERE id = :pid"),
                {"pid": project_id},
            )
        ).scalar_one()


async def _rewrite_committed_marker(factory, project_id, mutate):
    """Directly rewrite the COMMITTED row's in-flight marker (a staleness /
    takeover the test injects outside the turn — the world moving under an
    in-flight draft)."""
    from app.models.tables import Project

    async with factory() as session:
        row = await session.get(Project, project_id, with_for_update=True)
        pend = dict(row.pending_brief)
        pend["film_draft_inflight"] = mutate(
            dict(pend.get("film_draft_inflight") or {})
        )
        row.pending_brief = pend
        await session.commit()


async def test_first_draft_same_turn_correction_commit_isolated_db(
    monkeypatch,
):
    """首稿 → 同回合纠正 → 提交: the correction drafts against the IN-TURN
    version under the turn's OWN standing committed marker (no second
    begin — the self-lock never fires), and the turn's commit lands the
    LATEST candidate with the marker retired (无残留) and the lineage
    intact (v2 on base v1)."""
    from app.agents.tool_loop import ToolObservation
    from app.models.tables import Project, User

    engine, admin, db_name = await _isolated_database()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.database as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)
    _stub_director(monkeypatch)
    begin_calls = _spy_begin(monkeypatch)

    try:
        async with factory() as db:
            user = User(email=f"itest-{uuid4().hex[:8]}@example.com", name="itest")
            db.add(user)
            await db.flush()
            project = Project(user_id=user.id, title="itest", language="zh")
            db.add(project)
            await db.commit()
            project_id = project.id

            turn = _plan_turn(db, project, text="逐字稿成片")
            first = await turn._design_storyboard(
                _args(text=_TEXT_PARAMS["text"], verbatim=True), ""
            )
            assert isinstance(first, ToolObservation), first
            assert len(begin_calls) == 1  # the first design's REAL begin

            correction = await turn._design_storyboard(
                _args(specific_instruction="拆成更多屏"), ""
            )
            assert isinstance(correction, ToolObservation), correction
            assert len(begin_calls) == 1  # never a second begin (self-lock avoided)
            assert turn._design_corrections == 1

            # The commit publishes the LATEST candidate (the correction's v2).
            await db.commit()

        committed = await _committed_pending(factory, project_id)
        assert committed["film_storyboard_version"] == 2
        assert committed["film_base_version"] == 1
        # 无 marker 残留: the turn commit's new pending carries no LIVE
        # in-flight marker (retired = absent or None).
        assert not committed.get("film_draft_inflight")
        assert turn._design_shortfalls == []
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


async def test_drafting_failure_clears_the_marker_and_preserves_committed(
    monkeypatch,
):
    """失败分支: the REAL begin commits the marker, the drafting seat fails,
    the REAL clear removes ONLY this draft's marker — the committed pending
    stands byte-identical (旧状态不被覆盖) and no marker leaks."""
    import app.tools.film.storyboard as sb_mod
    from app.models.tables import Project, User

    engine, admin, db_name = await _isolated_database()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.database as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)

    async def _boom(db, project, **kwargs):
        raise RuntimeError("director down")

    monkeypatch.setattr(sb_mod, "prepare_dock_storyboard", _boom)

    try:
        async with factory() as db:
            user = User(email=f"itest-{uuid4().hex[:8]}@example.com", name="itest")
            db.add(user)
            await db.flush()
            project = Project(
                user_id=user.id, title="itest", language="zh",
                pending_brief=_v1_pending(),
            )
            db.add(project)
            await db.commit()
            project_id = project.id
            before = await _committed_pending(factory, project_id)

            turn = _plan_turn(db, project, text="重出一版")
            with pytest.raises(RuntimeError):
                await turn._design_storyboard(_args(specific_instruction="重出"), "")
            # The failure joined the ledger (the turn never docks over it
            # silently) even though the exception ends the beat.
            assert _ledger_keys(turn) == ["compose"]
            await db.rollback()

        committed = await _committed_pending(factory, project_id)
        # 旧版本状态不被覆盖; marker 无残留; the old confirmation token
        # stays voided (begin's documented supersession — the failed draft
        # never silently RESURRECTS the old Start authorization).
        assert not committed.get("film_draft_inflight")
        assert committed.get("film_draft_token") is None
        assert _version_state(committed) == _version_state(before)
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


async def test_stale_marker_discards_the_compose_publish_isolated_db(
    monkeypatch,
):
    """过期分支 (compose): our own marker's budget lapsed mid-draft → the
    publish guard fails CLOSED (the liveness half), the draft discards, the
    committed v1 pending stands byte-identical, and the discard releases
    its OWN (stale) marker."""
    from app.models.tables import Project, User
    from app.tools.film.storyboard import _DOCK_DRAFT_BUDGET_S

    engine, admin, db_name = await _isolated_database()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.database as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)
    _stub_director(monkeypatch)

    try:
        async with factory() as db:
            user = User(email=f"itest-{uuid4().hex[:8]}@example.com", name="itest")
            db.add(user)
            await db.flush()
            project = Project(
                user_id=user.id, title="itest", language="zh",
                pending_brief=_v1_pending(),
            )
            db.add(project)
            await db.commit()
            project_id = project.id
            before = await _committed_pending(factory, project_id)

            turn = _plan_turn(db, project, text="重出一版")
            # Begin for real (committed marker), then age the marker past
            # the design budget — the world the publish guard will read.
            import app.tools.film.storyboard as sb_mod

            real_begin = sb_mod.begin_film_draft

            async def _begin_then_age(*args, **kwargs):
                draft_id = await real_begin(*args, **kwargs)
                await _rewrite_committed_marker(
                    factory,
                    project_id,
                    lambda m: {**m, "started_at": time.time()
                               - (_DOCK_DRAFT_BUDGET_S + 10.0)},
                )
                return draft_id

            monkeypatch.setattr(sb_mod, "begin_film_draft", _begin_then_age)

            result = await turn._design_storyboard(
                _args(specific_instruction="重出"), ""
            )
            assert isinstance(result, str) and "discarded" in result
            assert _ledger_keys(turn) == ["compose"]
            await db.rollback()

        committed = await _committed_pending(factory, project_id)
        assert committed["film_storyboard_version"] == 1
        assert not committed.get("film_draft_inflight")  # own stale marker released
        # The versioned world stands byte-identical; the token stayed
        # voided from our begin.
        assert committed.get("film_draft_token") is None
        assert _version_state(committed) == _version_state(before)
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


async def test_takeover_marker_discards_and_is_never_touched_isolated_db(
    monkeypatch,
):
    """接管分支: a FOREIGN live marker (a newer design's begin landed over
    our stale one) discards our publish; our clear is draft-scoped and
    NEVER touches the takeover's marker; the committed pending stands."""
    from app.models.tables import Project, User

    engine, admin, db_name = await _isolated_database()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.database as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)
    _stub_director(monkeypatch)

    try:
        async with factory() as db:
            user = User(email=f"itest-{uuid4().hex[:8]}@example.com", name="itest")
            db.add(user)
            await db.flush()
            project = Project(
                user_id=user.id, title="itest", language="zh",
                pending_brief=_v1_pending(),
            )
            db.add(project)
            await db.commit()
            project_id = project.id
            before = await _committed_pending(factory, project_id)

            turn = _plan_turn(db, project, text="重出一版")
            import app.tools.film.storyboard as sb_mod

            real_begin = sb_mod.begin_film_draft

            async def _begin_then_takeover(*args, **kwargs):
                draft_id = await real_begin(*args, **kwargs)
                await _rewrite_committed_marker(
                    factory,
                    project_id,
                    lambda m: {**m, "draft_id": "foreign-takeover"},
                )
                return draft_id

            monkeypatch.setattr(sb_mod, "begin_film_draft", _begin_then_takeover)

            result = await turn._design_storyboard(
                _args(specific_instruction="重出"), ""
            )
            assert isinstance(result, str) and "discarded" in result
            assert _ledger_keys(turn) == ["compose"]
            await db.rollback()

        committed = await _committed_pending(factory, project_id)
        # The takeover's marker is UNTOUCHED (our clear never lifts a
        # foreign draft's marker) and the pending otherwise stands.
        assert committed["film_draft_inflight"]["draft_id"] == "foreign-takeover"
        assert committed.get("film_draft_token") is None
        assert _version_state(committed) == _version_state(before)
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


async def test_stale_marker_discards_the_patch_publish_isolated_db(
    monkeypatch,
):
    """过期分支 (patch — compose/patch 活性检查一致性): the patch guard's
    liveness half fails closed on the same lapsed marker; the REAL
    ``prepare_film_patch`` built the patch (no LLM on this path by law),
    the old committed version stands, the stale marker is released."""
    import app.tools.film.edits as edits_mod
    from app.models.tables import Project, User
    from app.tools.film.storyboard import _DOCK_DRAFT_BUDGET_S

    engine, admin, db_name = await _isolated_database()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.database as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)

    # The patch beat's auxiliaries (never LLM): no pages on a text film, no
    # snapshot music.
    async def _no_pages(db, project):
        return []

    async def _no_track(db, project, params):
        return None

    monkeypatch.setattr(edits_mod, "load_storyboard_pages", _no_pages)
    monkeypatch.setattr(edits_mod, "film_snapshot_track", _no_track)

    try:
        async with factory() as db:
            user = User(email=f"itest-{uuid4().hex[:8]}@example.com", name="itest")
            db.add(user)
            await db.flush()
            project = Project(
                user_id=user.id, title="itest", language="zh",
                pending_brief=_v1_pending(),
            )
            db.add(project)
            await db.commit()
            project_id = project.id
            before = await _committed_pending(factory, project_id)

            turn = _plan_turn(db, project, text="第二幕改文案")
            import app.tools.film.storyboard as sb_mod

            real_begin = sb_mod.begin_film_draft

            async def _begin_then_age(*args, **kwargs):
                draft_id = await real_begin(*args, **kwargs)
                await _rewrite_committed_marker(
                    factory,
                    project_id,
                    lambda m: {**m, "started_at": time.time()
                               - (_DOCK_DRAFT_BUDGET_S + 10.0)},
                )
                return draft_id

            monkeypatch.setattr(sb_mod, "begin_film_draft", _begin_then_age)

            from app.tools.film.edits import (
                film_base_cut,
                film_version_identity_digest,
            )

            base_ref = film_version_identity_digest(
                _text_board(), dict(_TEXT_PARAMS), version=1,
                cut=film_base_cut(
                    SimpleNamespace(
                        film_storyboard_version=1,
                        film_kept_frames=None,
                        film_storyboard_execution=None,
                    )
                ),
            )
            result = await turn._design_storyboard(
                _args(
                    edits=[
                        {"op": "update_scene", "scene_id": "s2",
                         "copy_slots": {"lines": ["一场分享，持续被看见。"]}},
                    ],
                    base_ref=base_ref,
                ),
                "",
            )
            assert isinstance(result, str) and "discarded" in result
            assert _ledger_keys(turn) == ["patch:update_scene:s2:[copy_slots.lines]"]
            await db.rollback()

        committed = await _committed_pending(factory, project_id)
        assert committed["film_storyboard_version"] == 1
        assert "film_draft_inflight" not in committed
        assert committed.get("film_draft_token") is None
        assert _version_state(committed) == _version_state(before)
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()



def _ledger_keys(turn) -> list[str]:
    """The shortfall ledger's mechanical keys (entries are
    ``design_call_record`` dicts — {key, target})."""
    return [e["key"] for e in turn._design_shortfalls]


def _args(**kw):
    from app.models.schemas import DesignStoryboardArgs

    return DesignStoryboardArgs.model_validate(kw)
