"""Run execution authority pure tests (R1 B3 — I-EXEC-03 / I-EXEC-04).

No DB, no LLM, no HTTP. A queued-result stub session drives the ONE
arbitration seat (``resume_waiting_interrupt``); ``has_active_run`` and the
graph back-write are monkeypatched recorders. The matrix: waiting node
present/absent × authority free/held. The blocked branch (再挂) must write
ZERO state — node stays waiting, no spec.answer, run untouched — so a parked
run never becomes the project's second {PENDING, RUNNING} owner, and the
settled answer survives on the message row for the next authority-freeing
beat (finalize handoff / sweep retry).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.schemas import WorkflowStatus
from app.models.tables import WorkflowRun, WorkflowStep
from app.pipeline import orchestrator
from app.pipeline.orchestrator import (
    _resume_authority_decision,
    resume_waiting_interrupt,
)

_ANSWER = {"kind": "option", "option_id": "a", "text": "Focus: Pricing"}


# ---- stubs -----------------------------------------------------------------


class _QueueResult:
    """Serves both result idioms the seat consumes."""

    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row

    def first(self):
        return self._row


class _StubSession:
    """AsyncSession stand-in: answers ``db.execute`` from a queue (the seat's
    statement order is deterministic: ① waiting-node select, ② project row
    lock) and records every statement so tests can prove the lock was taken.
    """

    def __init__(self, results: list):
        self._results = list(results)
        self.statements: list = []

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        return self._results.pop(0)


@pytest.fixture
def authority(monkeypatch):
    """Monkeypatched recorders: has_active_run (verdict + exclusion witness)
    and the graph back-write (must NEVER fire on a blocked park)."""
    calls = {"active": [], "synced": []}

    async def fake_has_active_run(db, project_id, *, exclude_run_id=None):
        calls["active"].append(
            {"project_id": project_id, "exclude_run_id": exclude_run_id}
        )
        return fake_has_active_run.verdict

    fake_has_active_run.verdict = False

    async def fake_sync(db, node):
        calls["synced"].append(node.id)

    monkeypatch.setattr(orchestrator, "has_active_run", fake_has_active_run)
    monkeypatch.setattr(orchestrator, "sync_graph_node_for_step", fake_sync)
    calls["set_verdict"] = lambda v: setattr(fake_has_active_run, "verdict", v)
    return calls


def _parked_run() -> WorkflowRun:
    run = WorkflowRun(
        project_id=uuid4(),
        status=WorkflowStatus.WAITING_HUMAN,
        context={},
    )
    run.id = uuid4()
    return run


def _waiting_node(run: WorkflowRun) -> WorkflowStep:
    node = WorkflowStep(
        run_id=run.id,
        kind="interrupt",
        status="waiting",
        seq=1,
        started_at=datetime.now(UTC),
        spec={"suspend_payload": {"question_message_id": str(uuid4())}},
    )
    node.id = uuid4()
    node.claim_token = None
    return node


# ---- the pure decision matrix ----------------------------------------------


def test_decision_no_waiting_node_is_idle():
    assert _resume_authority_decision(node_present=False, authority_free=True) == "idle"
    assert _resume_authority_decision(node_present=False, authority_free=False) == "idle"


def test_decision_authority_free_resumes():
    assert (
        _resume_authority_decision(node_present=True, authority_free=True)
        == "resumed"
    )


def test_decision_authority_held_blocks():
    assert (
        _resume_authority_decision(node_present=True, authority_free=False)
        == "blocked"
    )


# ---- the seat, driven ------------------------------------------------------


@pytest.mark.asyncio
async def test_seat_no_waiting_node_is_idle(authority):
    run = _parked_run()
    db = _StubSession([_QueueResult(None)])
    outcome = await resume_waiting_interrupt(db, run, _ANSWER)
    assert outcome == "idle"
    # Idempotent no-op: the arbitration (lock + re-check) never fires.
    assert len(db.statements) == 1
    assert authority["active"] == []
    assert run.status == WorkflowStatus.WAITING_HUMAN


@pytest.mark.asyncio
async def test_seat_authority_free_resumes(authority):
    run = _parked_run()
    node = _waiting_node(run)
    db = _StubSession([_QueueResult(node), _QueueResult(None)])
    authority["set_verdict"](False)

    outcome = await resume_waiting_interrupt(db, run, _ANSWER)

    assert outcome == "resumed"
    # The project row lock was taken BEFORE the re-check (statements ① node
    # select ② lock — the re-check rides the monkeypatched predicate).
    assert len(db.statements) == 2
    # The resuming run never counts ITSELF as the blocker.
    assert authority["active"] == [
        {"project_id": run.project_id, "exclude_run_id": run.id}
    ]
    assert node.spec["answer"] == _ANSWER
    assert node.status == "pending"
    assert node.started_at is None
    assert node.claim_token is None
    assert run.status == WorkflowStatus.RUNNING
    assert authority["synced"] == [node.id]


@pytest.mark.asyncio
async def test_seat_authority_held_blocks_with_zero_writes(authority):
    run = _parked_run()
    node = _waiting_node(run)
    original_spec = dict(node.spec)
    db = _StubSession([_QueueResult(node), _QueueResult(None)])
    authority["set_verdict"](True)

    outcome = await resume_waiting_interrupt(db, run, _ANSWER)

    assert outcome == "blocked"
    # Arbitration DID run under the lock (I-EXEC-04: atomic re-check)…
    assert len(db.statements) == 2
    assert authority["active"] == [
        {"project_id": run.project_id, "exclude_run_id": run.id}
    ]
    # …but the park wrote ZERO state: the node keeps waiting with its spec
    # untouched (the answer lives on the settled message row), the run keeps
    # WAITING_HUMAN, and the graph back-write never fires.
    assert node.status == "waiting"
    assert node.spec == original_spec
    assert "answer" not in node.spec
    assert node.started_at is not None
    assert run.status == WorkflowStatus.WAITING_HUMAN
    assert authority["synced"] == []
