"""Pure tests for revise_selects — the pick-swap verb (iter-3 S4, ADR-089
§6 修订分类 / N-58, contract §4 S4).

Gated here (no DB / no LLM / no HTTP — the _StubDb pattern, seeds precise):

- **The door branch** (``exploration_store.revise_selects``): the swap lands
  IN PLACE (state → ``revised`` — the Select family's first revised writer),
  the birth ``idem`` SURVIVES (a revision never re-mints identity,
  revise_plan 同律), bounds re-validate against the SAME candidate set, the
  verdict/reason restatement is REQUIRED (R3 — the judgment attribute moves
  with the pick), a settled (compiled/superseded) select is closed, one call
  revises ONE journey, an identical restatement is a replay no-op, and
  unknown / wrong-kind ids reject.
- **select_revision_phase**: the three money states (pre_dock / docked /
  post_run) over the riding plans' states — the turn paths adjudicate on
  this pure seat, never re-derive it.
- **ReviseSelectsArgs** (tool boundary): the restatement fields are
  required, extra="forbid" stays the drift alarm, pending_disposition rides
  as the dual-path envelope seat, and a numeric-STRING member_index absorbs
  (顺形律 — pydantic lax coercion, never a rejection).
- **The post-run mechanics at door+compile level**: swap → mark_compiled →
  supersede-继任 → ``compile_plan_rows_package`` over the successor — the
  mini package's cut_segments re-derives the NEW member's range (the swap
  moves the SOURCE, never the deliverables).
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.chat.exploration_compile import CompiledPackage, compile_plan_rows_package
from app.chat.exploration_tools import ReviseSelectItem, ReviseSelectsArgs
from app.models.tables import Asset, GraphNode, Journey, Project
from app.pipeline.exploration_store import (
    CandidateMember,
    ExplorationRejected,
    mark_compiled,
    propose_candidates,
    propose_plans,
    propose_selects,
    revise_selects,
    select_revision_phase,
    supersede_plan,
)

_PROJECT_ID = uuid4()
_ASSET_ID = uuid4()

_WORDS = [
    {"word": "Pricing", "start": 0.0, "end": 0.5},
    {"word": "is", "start": 0.5, "end": 0.7},
    {"word": "hard.", "start": 0.7, "end": 1.0},
    {"word": "Fundraising", "start": 2.0, "end": 2.6},
    {"word": "is", "start": 2.6, "end": 2.8},
    {"word": "art.", "start": 2.8, "end": 3.2},
]
_MEMBERS = [
    {"start": 0.0, "end": 1.0, "excerpt": "Pricing is hard.", "speaker": "host"},
    {"start": 2.0, "end": 3.2, "excerpt": "Fundraising is art.", "speaker": "host"},
]


def _asset() -> Asset:
    return Asset(
        id=_ASSET_ID,
        user_id=uuid4(),
        project_id=_PROJECT_ID,
        type="video",
        duration_seconds=60,
        meta={"words": _WORDS, "language": "en"},
    )


# ---- the stub db (test_exploration_compile_pure pattern, verbatim) ------------


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _StubDb:
    """Serves GraphNode / Journey / Asset off lists; JSON-path criteria stay
    unevaluated (the pattern's documented limitation — seeds are precise).
    Plain-column eq filters: project_id / type / goal_text / journey_id."""

    def __init__(self, nodes=(), assets=(), journeys=()):
        self.project = Project(id=_PROJECT_ID, language=None)
        self.nodes = list(nodes)
        self.assets = list(assets)
        self.journeys = list(journeys)
        self.added: list = []

    async def get(self, model, row_id):
        if model is Asset:
            return next((a for a in self.assets if str(a.id) == str(row_id)), None)
        if model is Journey:
            return next((j for j in self.journeys if str(j.id) == str(row_id)), None)
        return None

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        rows = {
            GraphNode: self.nodes,
            Journey: self.journeys,
            Asset: self.assets,
        }.get(entity, [])
        for crit in getattr(stmt, "_where_criteria", []):
            left = getattr(crit, "left", None)
            col = getattr(left, "name", None)
            value = getattr(getattr(crit, "right", None), "value", None)
            op_name = getattr(getattr(crit, "operator", None), "__name__", "")
            if (
                col in ("project_id", "type", "goal_text", "journey_id")
                and value is not None
                and op_name == "eq"
            ):
                rows = [r for r in rows if str(getattr(r, col, None)) == str(value)]
        return _StubResult(list(rows))

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, GraphNode):
            self.nodes.append(obj)
        elif isinstance(obj, Journey):
            self.journeys.append(obj)

    async def flush(self):
        pass


# ---- seeds (the door births the rows — spec shapes stay exact) -------------------


async def _seed_chain(db: _StubDb, *, goal="goal") -> tuple[GraphNode, GraphNode]:
    """A candidate set with TWO members + one select on member 0."""
    cset = await propose_candidates(
        db,
        db.project,
        asset_id=_ASSET_ID,
        topic="pricing",
        members=[CandidateMember(**m) for m in _MEMBERS],
        goal_text=goal,
    )
    sel = (
        await propose_selects(
            db,
            db.project,
            candidate_set_id=cset.id,
            selects=[{"member_index": 0, "verdict": "v0", "reason": "r0"}],
        )
    )[0]
    return cset, sel


# ---- the door branch --------------------------------------------------------------


@pytest.mark.asyncio
class TestReviseSelectsDoor:
    async def test_swap_lands_in_place_revised(self) -> None:
        db = _StubDb(assets=[_asset()])
        _cset, sel = await _seed_chain(db)
        birth_idem = sel.spec["idem"]
        revised = await revise_selects(
            db,
            db.project,
            selects=[
                {
                    "select_id": str(sel.id),
                    "member_index": 1,
                    "verdict": "v1",
                    "reason": "r1",
                }
            ],
        )
        assert revised == [sel]  # the SAME row
        assert sel.state == "revised"  # the family's first revised writer
        assert sel.spec["member_index"] == 1
        assert sel.spec["verdict"] == "v1"
        assert sel.spec["reason"] == "r1"
        assert sel.spec["idem"] == birth_idem  # identity never re-mints
        assert len(db.nodes) == 2  # zero new rows (cset + select only)

    async def test_replay_is_a_noop(self) -> None:
        db = _StubDb(assets=[_asset()])
        _cset, sel = await _seed_chain(db)
        args = {
            "select_id": str(sel.id),
            "member_index": 1,
            "verdict": "v1",
            "reason": "r1",
        }
        await revise_selects(db, db.project, selects=[args])
        again = await revise_selects(db, db.project, selects=[args])
        assert again == [sel]
        assert sel.state == "revised"  # unchanged, no double-write

    async def test_bounds_revalidate_against_the_same_set(self) -> None:
        db = _StubDb(assets=[_asset()])
        _cset, sel = await _seed_chain(db)
        with pytest.raises(ExplorationRejected, match="outside the candidate"):
            await revise_selects(
                db,
                db.project,
                selects=[
                    {
                        "select_id": str(sel.id),
                        "member_index": 2,  # the set has 2 members (0..1)
                        "verdict": "v",
                        "reason": "r",
                    }
                ],
            )
        assert sel.spec["member_index"] == 0  # untouched
        assert sel.state == "ready"

    async def test_verdict_and_reason_restatement_required(self) -> None:
        db = _StubDb(assets=[_asset()])
        _cset, sel = await _seed_chain(db)
        for missing in ({"verdict": "", "reason": "r"}, {"verdict": "v", "reason": "  "}):
            with pytest.raises(ExplorationRejected, match="verdict and reason"):
                await revise_selects(
                    db,
                    db.project,
                    selects=[{"select_id": str(sel.id), "member_index": 1, **missing}],
                )
        assert sel.state == "ready"

    async def test_settled_select_is_closed(self) -> None:
        db = _StubDb(assets=[_asset()])
        _cset, sel = await _seed_chain(db)
        for settled in ("compiled", "superseded"):
            sel.state = settled
            with pytest.raises(ExplorationRejected, match="never revised"):
                await revise_selects(
                    db,
                    db.project,
                    selects=[
                        {
                            "select_id": str(sel.id),
                            "member_index": 1,
                            "verdict": "v",
                            "reason": "r",
                        }
                    ],
                )
            sel.state = "ready"

    async def test_one_call_one_journey(self) -> None:
        db = _StubDb(assets=[_asset()])
        _cset, sel_a = await _seed_chain(db, goal="goal A")
        _cset_b, sel_b = await _seed_chain(db, goal="goal B")
        assert str(sel_a.journey_id) != str(sel_b.journey_id)
        with pytest.raises(ExplorationRejected, match="one journey"):
            await revise_selects(
                db,
                db.project,
                selects=[
                    {"select_id": str(sel_a.id), "member_index": 1, "verdict": "v", "reason": "r"},
                    {"select_id": str(sel_b.id), "member_index": 1, "verdict": "v", "reason": "r"},
                ],
            )

    async def test_unknown_and_wrong_kind_ids_reject(self) -> None:
        db = _StubDb(assets=[_asset()])
        cset, sel = await _seed_chain(db)
        for bad_id, match in ((str(uuid4()), "not found"), (str(cset.id), "is a candidate_set")):
            with pytest.raises(ExplorationRejected, match=match):
                await revise_selects(
                    db,
                    db.project,
                    selects=[
                        {"select_id": bad_id, "member_index": 1, "verdict": "v", "reason": "r"}
                    ],
                )
        assert sel.state == "ready"

    async def test_empty_call_rejects(self) -> None:
        db = _StubDb(assets=[_asset()])
        with pytest.raises(ExplorationRejected, match="no selects"):
            await revise_selects(db, db.project, selects=[])


# ---- the money-state discriminator (pure seat) -------------------------------------


class TestSelectRevisionPhase:
    def test_spectrum(self) -> None:
        assert select_revision_phase([]) == "pre_dock"
        assert select_revision_phase(["ready"]) == "docked"
        assert select_revision_phase(["ready", "revised", "draft"]) == "docked"
        assert select_revision_phase(["compiled"]) == "post_run"
        # A superseded row's successor rides the SAME select — a re-revision
        # before the mini package confirms still resolves post_run here and
        # the successor (live) is what compiles.
        assert select_revision_phase(["superseded", "revised"]) == "post_run"


# ---- the tool boundary (args shape) --------------------------------------------------


class TestReviseSelectsArgs:
    def test_restatement_fields_required(self) -> None:
        sel_id = str(uuid4())
        for missing in ("member_index", "verdict", "reason"):
            item = {
                "select_id": sel_id,
                "member_index": 1,
                "verdict": "v",
                "reason": "r",
            }
            item.pop(missing)
            with pytest.raises(ValidationError):
                ReviseSelectsArgs.model_validate({"selects": [item]})

    def test_numeric_string_member_index_absorbs(self) -> None:
        """顺形律: a provider dialect emitting "1" for the index coerces in
        lax mode — never a rejected iteration."""
        item = ReviseSelectItem.model_validate(
            {
                "select_id": str(uuid4()),
                "member_index": "1",
                "verdict": "v",
                "reason": "r",
            }
        )
        assert item.member_index == 1

    def test_pending_disposition_seat(self) -> None:
        item = {
            "select_id": str(uuid4()),
            "member_index": 1,
            "verdict": "v",
            "reason": "r",
        }
        assert (
            ReviseSelectsArgs.model_validate({"selects": [item]}).pending_disposition
            == "none"
        )
        assert (
            ReviseSelectsArgs.model_validate(
                {"selects": [item], "pending_disposition": "skip"}
            ).pending_disposition
            == "skip"
        )
        with pytest.raises(ValidationError):
            ReviseSelectsArgs.model_validate(
                {"selects": [item], "pending_disposition": "maybe"}
            )

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ReviseSelectsArgs.model_validate(
                {
                    "selects": [
                        {
                            "select_id": str(uuid4()),
                            "member_index": 1,
                            "verdict": "v",
                            "reason": "r",
                        }
                    ],
                    "member_index": 2,  # top-level drift key
                }
            )


# ---- the post-run mechanics at door+compile level -------------------------------------


@pytest.mark.asyncio
class TestPostRunMiniPackage:
    async def test_swap_supersede_mini_compile_rederives_the_range(self) -> None:
        """The S4 post-run chain end-to-end at the deterministic level:
        the select swaps (member 0 → 1), the riding compiled plan supersedes
        (spec carried over verbatim), and the successor's mini compile
        re-derives the NEW member's range — the swap moves the SOURCE."""
        db = _StubDb(assets=[_asset()])
        _cset, sel = await _seed_chain(db)
        plan = (
            await propose_plans(
                db,
                db.project,
                plans=[
                    {
                        "select_id": str(sel.id),
                        "title": "Pricing clip",
                        "outputs": [{"kind": "clip"}],
                    }
                ],
            )
        )[0]
        journey_id = plan.journey_id
        await mark_compiled(db, db.project, plan_ids=[plan.id])
        assert plan.state == "compiled"

        await revise_selects(
            db,
            db.project,
            selects=[
                {
                    "select_id": str(sel.id),
                    "member_index": 1,
                    "verdict": "the fundraising framing",
                    "reason": "stronger hook",
                }
            ],
        )
        assert sel.state == "revised"

        successor = await supersede_plan(db, db.project, plan_id=plan.id)
        assert plan.state == "superseded"
        assert successor.state == "revised"
        assert successor.id != plan.id
        assert successor.spec["select_id"] == str(sel.id)  # carry-over verbatim
        assert successor.spec["outputs"] == plan.spec["outputs"]

        package = await compile_plan_rows_package(
            db, db.project, journey_id, [successor]
        )
        assert isinstance(package, CompiledPackage)
        assert [t.tool for t in package.tasks] == ["cut_segments"]
        seg = package.tasks[0].params["segments"][0]
        assert (seg["start"], seg["end"]) == (2.0, 3.2)  # the NEW member's range
        assert set(package.plan_task_map) == {str(successor.id)}
