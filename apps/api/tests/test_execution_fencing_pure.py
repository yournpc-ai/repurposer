"""Execution fencing pure tests (ADR-079, R1 B2 — I-EXEC-01 / I-EXEC-02).

No DB, no LLM, no HTTP. ``_StubSession`` drives ``execute_step`` with a
rowcount=0 fencing write (authority lost: reaped, then re-claimed by a live
worker) and records every lifecycle call — the fenced discipline is that a
stale execution's world writes are ALL zero: no capture, no graph sync, no
cascade, no mirror, no run write. The deliberate exception is the
finally-block's ``maybe_finalize_run`` (row lock + terminal early-return =
idempotent), which must STILL fire.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import WorkflowStatus
from app.models.tables import Project, WorkflowRun, WorkflowStep
from app.pipeline import orchestrator
from app.pipeline.errors import TransientNodeError
from app.pipeline.orchestrator import (
    QualityBounce,
    Suspend,
    _foreign_execution,
    execute_step,
)

_NODE_ID = uuid4()
_RUN_ID = uuid4()
_PROJECT_ID = uuid4()
_MINE = uuid4()


# ---- stubs -----------------------------------------------------------------


class _StubExec:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _StubSession:
    """AsyncSession stand-in for the fenced paths: serves ``db.get`` off a
    seed map, answers every statement with a fixed rowcount (0 = the fencing
    write misses — the zombie loses), and records lifecycle calls. WHERE
    clauses are never evaluated — the tests seed precisely so the answer is
    already determined."""

    def __init__(self, seed: dict, rowcount: int):
        self._seed = seed
        self._rowcount = rowcount
        self.executed: list = []
        self.gets: list = []
        self.refreshed: list = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, row_id):
        self.gets.append(model)
        return self._seed.get(model)

    async def execute(self, stmt, *args, **kwargs):
        self.executed.append(stmt)
        return _StubExec(self._rowcount)

    async def refresh(self, obj):
        self.refreshed.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _SessionFactory:
    """``AsyncSessionLocal`` replacement — hands out seeded stubs in call
    order and keeps them for inspection."""

    def __init__(self, seed: dict, rowcount: int = 0):
        self._seed = seed
        self._rowcount = rowcount
        self.sessions: list[_StubSession] = []

    def __call__(self):
        session = _StubSession(self._seed, self._rowcount)
        self.sessions.append(session)
        return session


class _FakeBound:
    """metering.bind_workflow_step stand-in: context manager + ledger."""

    def __init__(self):
        self.accrued: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeNode:
    """NODE_KINDS entry: runs to a result or raises the staged exception."""

    kind = "fake_kind"
    runtime_fanout = False
    retries = 2

    def __init__(self, behavior):
        self._behavior = behavior
        self.run_calls = 0

    async def run(self, db, run, node, project):
        self.run_calls += 1
        if isinstance(self._behavior, BaseException):
            raise self._behavior
        return self._behavior


class _World:
    """The monkeypatched execute_step environment + its side-effect records."""

    def __init__(self, monkeypatch, fake_node, *, rowcount: int, node_status="running", token=_MINE):
        self.captured: list = []
        self.synced: list = []
        self.cascaded: list = []
        self.rescued: list = []
        self.finalized: list = []

        node = SimpleNamespace(
            id=_NODE_ID,
            run_id=_RUN_ID,
            kind="fake_kind",
            status=node_status,
            claim_token=token,
            attempt=1,
            cost=None,
            spec={},
        )
        run = SimpleNamespace(
            id=_RUN_ID,
            project_id=_PROJECT_ID,
            status=WorkflowStatus.RUNNING,
            context={"ui_language": "en"},
        )
        project = SimpleNamespace(id=_PROJECT_ID, user_id=uuid4(), language="en")
        seed = {WorkflowStep: node, WorkflowRun: run, Project: project}
        self.node = node
        self.factory = _SessionFactory(seed, rowcount=rowcount)

        monkeypatch.setattr(orchestrator, "AsyncSessionLocal", self.factory)
        monkeypatch.setitem(orchestrator.NODE_KINDS, "fake_kind", fake_node)
        monkeypatch.setattr(orchestrator, "bind_workflow_step", lambda _id: _FakeBound())

        async def _capture(db, *, user_id, node):
            self.captured.append(node)

        async def _sync(db, step):
            self.synced.append(step)

        async def _cascade(db, failed_node, *, reason=None):
            self.cascaded.append(failed_node)

        async def _rescue(db, node, project):
            self.rescued.append(node)

        async def _finalize(run_id):
            self.finalized.append(run_id)

        monkeypatch.setattr(orchestrator, "capture_step", _capture)
        monkeypatch.setattr(orchestrator, "sync_graph_node_for_step", _sync)
        monkeypatch.setattr(orchestrator, "_cascade_skip", _cascade)
        monkeypatch.setattr(orchestrator, "modifier_target_clips", _rescue)
        monkeypatch.setattr(orchestrator, "maybe_finalize_run", _finalize)


# ---- entry defense (the token capture decision) ----------------------------


def test_foreign_execution_decision() -> None:
    # running + NULL token = foreign row (pre-migration in-flight / claim-less
    # flip) → refuse. Everything else is executable: running+token is the
    # normal claimed path, pending is the mint path.
    assert _foreign_execution("running", None) is True
    assert _foreign_execution("running", uuid4()) is False
    assert _foreign_execution("pending", None) is False
    assert _foreign_execution("pending", uuid4()) is False


@pytest.mark.asyncio
async def test_foreign_row_refused_before_execution(monkeypatch) -> None:
    fake = _FakeNode([uuid4()])
    world = _World(monkeypatch, fake, rowcount=0, token=None)
    await execute_step(_NODE_ID)
    # Never executes, never opens the executor session — one entry session
    # only, and no tail writes at all.
    assert fake.run_calls == 0
    assert len(world.factory.sessions) == 1
    assert world.captured == [] and world.synced == [] and world.cascaded == []


@pytest.mark.asyncio
async def test_pending_mint_race_lost_stands_down(monkeypatch) -> None:
    fake = _FakeNode([uuid4()])
    world = _World(monkeypatch, fake, rowcount=0, node_status="pending", token=None)
    await execute_step(_NODE_ID)
    # The guarded mint missed (a racing claim won) → rollback, no execution.
    assert fake.run_calls == 0
    assert world.factory.sessions[0].rollbacks == 1
    assert world.captured == [] and world.synced == []


# ---- fenced tails: rowcount=0 → zero side effects --------------------------


@pytest.mark.asyncio
async def test_fenced_success_tail_zero_side_effects(monkeypatch) -> None:
    fake = _FakeNode([uuid4()])
    world = _World(monkeypatch, fake, rowcount=0)
    await execute_step(_NODE_ID)
    assert fake.run_calls == 1
    executor_session = world.factory.sessions[1]
    # Exactly ONE write attempted (the fencing UPDATE), then rollback — the
    # executor's staged writes die with the session.
    assert len(executor_session.executed) == 1
    assert executor_session.rollbacks == 1
    assert executor_session.commits == 0
    # I-EXEC-02: no capture (the double-billing hole), no graph sync.
    assert world.captured == []
    assert world.synced == []
    # Deliberate exception: maybe_finalize_run still runs (idempotent).
    assert world.finalized == [_RUN_ID]


@pytest.mark.asyncio
async def test_fenced_failure_tail_no_sync_no_rescue_no_cascade(monkeypatch) -> None:
    fake = _FakeNode(ValueError("boom"))
    world = _World(monkeypatch, fake, rowcount=0)
    await execute_step(_NODE_ID)
    tail_session = world.factory.sessions[2]
    assert len(tail_session.executed) == 1
    assert tail_session.rollbacks == 1
    assert tail_session.commits == 0
    assert world.synced == []
    assert world.rescued == []
    assert world.cascaded == []
    assert world.finalized == [_RUN_ID]


@pytest.mark.asyncio
async def test_fenced_retry_requeue_zero_side_effects(monkeypatch) -> None:
    # attempt 1 within budget 2 → the retry branch; fenced there too.
    fake = _FakeNode(TransientNodeError("flaky"))
    world = _World(monkeypatch, fake, rowcount=0)
    await execute_step(_NODE_ID)
    tail_session = world.factory.sessions[2]
    assert len(tail_session.executed) == 1
    assert tail_session.rollbacks == 1
    assert tail_session.commits == 0
    assert world.synced == [] and world.cascaded == []


@pytest.mark.asyncio
async def test_fenced_suspend_tail_never_writes_the_run(monkeypatch) -> None:
    fake = _FakeNode(Suspend({"options": []}))
    world = _World(monkeypatch, fake, rowcount=0)
    await execute_step(_NODE_ID)
    tail_session = world.factory.sessions[2]
    # The fencing write is the ONLY statement — no WorkflowRun update
    # follows a missed park (the COMPLETED → WAITING_HUMAN resurrection
    # path dies here), no sync, no commit.
    assert len(tail_session.executed) == 1
    assert tail_session.rollbacks == 1
    assert tail_session.commits == 0
    assert tail_session.gets == [WorkflowStep]
    assert world.synced == []


@pytest.mark.asyncio
async def test_fenced_quality_bounce_zero_side_effects(monkeypatch) -> None:
    fake = _FakeNode(QualityBounce(executor_id=uuid4(), feedback="fix it"))
    world = _World(monkeypatch, fake, rowcount=0)
    await execute_step(_NODE_ID)
    tail_session = world.factory.sessions[2]
    # Fenced BEFORE the executor row is even fetched — no resets, no sync.
    assert len(tail_session.executed) == 1
    assert tail_session.rollbacks == 1
    assert tail_session.commits == 0
    assert tail_session.gets == [WorkflowStep]
    assert world.synced == []


# ---- authority held: the happy path still bills AFTER the guarded write ----


@pytest.mark.asyncio
async def test_authority_held_success_tail_captures_and_commits(monkeypatch) -> None:
    fake = _FakeNode([uuid4()])
    world = _World(monkeypatch, fake, rowcount=1)
    await execute_step(_NODE_ID)
    executor_session = world.factory.sessions[1]
    # Guarded write landed → refresh, capture, sync, one commit — the
    # capture is reachable ONLY with authority held.
    assert executor_session.rollbacks == 0
    assert executor_session.commits == 1
    assert len(executor_session.refreshed) == 1
    assert len(world.captured) == 1
    assert len(world.synced) == 1
    assert world.finalized == [_RUN_ID]
