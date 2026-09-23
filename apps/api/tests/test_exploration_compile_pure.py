"""Pure tests for the shared exploration-compile seat
(app/chat/exploration_compile.py, iter-3 S2 — R12/R14 双门一条法律).

Gated here:

- **Journey resolution** (compile_plans_package): an unknown select id →
  the loop-echo string; selects spanning two journeys → the one-call-one-
  journey echo; a single journey passes through.
- **The double door**: the pre-flight compile over in-memory previews
  (``preview:{select_id}`` ids, draft/ready states off the completeness
  self-check) rejects with ZERO writes — the door never runs; a clean
  package births through the door and the pre-flight map re-keys from the
  preview ids onto the born rows in birth order (zip law).
- **recompile_journey_package**: real rows compile straight (no previews),
  the map keys ARE the real row ids.
- **pending_disposition** (iter-3 S2 envelope seat): default / legal /
  illegal values on ProposePlansArgs / RevisePlanArgs.

The DB half rides the _StubDb pattern (test_exploration_store_pure
sibling): GraphNode / Journey / Asset list-served, JSON-path criteria stay
unevaluated — seeds are precise. The compile surface uses simple chains
(writer-only / clip-without-language): check_transform_targets passes
trivially with no transform tasks, and project_source_language reads the
stubbed Asset's meta.language. ``current_ui_language()`` has no request
context here → None → default_language falls back to "en" (expected).
"""

import pytest
from uuid import uuid4

from app.models.tables import Asset, GraphNode, Journey, Project
from app.chat.exploration_compile import (
    CompiledPackage,
    compile_plans_package,
    recompile_journey_package,
)
from app.chat.exploration_tools import (
    PlanItem,
    ProposePlansArgs,
    RevisePlanArgs,
)
from app.pipeline.exploration_store import (
    CandidateMember,
    PlanOutput,
    propose_candidates,
    propose_selects,
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


def _asset() -> Asset:
    return Asset(
        id=_ASSET_ID,
        user_id=uuid4(),
        project_id=_PROJECT_ID,
        type="video",
        duration_seconds=60,
        meta={"words": _WORDS, "language": "en"},
    )


# ---- the stub db (test_exploration_store_pure pattern + Asset rows) -------------


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
    Adds ``journey_id`` to the eq-filterable plain columns (the journey
    reads filter on it) and Asset to the execute-served entities
    (project_source_language's list_assets)."""

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
        # plain-column eq only (project_id / type / goal_text / journey_id)
        # — JSON-path and in_ criteria fall through unevaluated by design
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


async def _seed_select(db: _StubDb, *, topic="pricing", goal="goal") -> GraphNode:
    cset = await propose_candidates(
        db,
        db.project,
        asset_id=_ASSET_ID,
        topic=topic,
        members=[CandidateMember(start=0.0, end=1.0, excerpt="Pricing is hard.")],
        goal_text=goal,
    )
    return (
        await propose_selects(
            db,
            db.project,
            candidate_set_id=cset.id,
            selects=[{"member_index": 0, "verdict": "v", "reason": "r"}],
        )
    )[0]


def _plan_item(select_id, outputs, title="") -> PlanItem:
    return PlanItem(
        select_id=select_id,
        title=title,
        outputs=[PlanOutput(**o) for o in outputs],
    )


# ---- journey resolution ------------------------------------------------------------


@pytest.mark.asyncio
class TestJourneyResolution:
    async def test_unknown_select_echoes(self) -> None:
        db = _StubDb(assets=[_asset()])
        await _seed_select(db)
        result = await compile_plans_package(
            db,
            db.project,
            [_plan_item(uuid4(), [{"kind": "post"}])],
            persona_id=None,
        )
        assert isinstance(result, str)
        assert "is not one of this project's selects" in result

    async def test_cross_journey_echoes(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel_a = await _seed_select(db)
        sel_b = await _seed_select(db, topic="fundraising", goal="another goal")
        result = await compile_plans_package(
            db,
            db.project,
            [
                _plan_item(sel_a.id, [{"kind": "post"}]),
                _plan_item(sel_b.id, [{"kind": "post"}]),
            ],
            persona_id=None,
        )
        assert isinstance(result, str)
        assert "one call plans one journey" in result

    async def test_single_journey_passes(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel = await _seed_select(db)
        package = await compile_plans_package(
            db,
            db.project,
            [_plan_item(sel.id, [{"kind": "post"}], title="定价帖")],
            persona_id=None,
        )
        assert isinstance(package, CompiledPackage)
        assert str(package.journey_id) == str(sel.journey_id)


# ---- the double door -----------------------------------------------------------------


@pytest.mark.asyncio
class TestCompilePlansPackage:
    async def test_writer_only_package_births_and_maps(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel = await _seed_select(db)
        nodes_before = len(db.nodes)
        package = await compile_plans_package(
            db,
            db.project,
            [
                _plan_item(
                    sel.id,
                    [{"kind": "post", "language": "fr"}, {"kind": "article"}],
                    title="A",
                ),
                _plan_item(sel.id, [{"kind": "quotes"}], title="B"),
            ],
            persona_id=None,
        )
        assert isinstance(package, CompiledPackage)
        # Two plans born ready, in the call's order.
        assert len(package.plans) == 2
        assert all(p.state == "ready" for p in package.plans)
        assert package.plans[0].spec["title"] == "A"
        # The compiled chain: 2 writer tasks for plan A + 1 for plan B.
        assert [t.tool for t in package.tasks] == [
            "write_post",
            "write_article",
            "write_quotes",
        ]
        # R20 substrate: the map re-keyed off the preview ids onto the born
        # rows, ranges transferred verbatim (birth order == compile order).
        born_ids = [str(p.id) for p in package.plans]
        assert set(package.plan_task_map) == set(born_ids)
        assert package.plan_task_map[born_ids[0]] == [0, 2]
        assert package.plan_task_map[born_ids[1]] == [2, 3]
        # The door wrote exactly the two plan rows (no twins, no edges).
        assert len(db.nodes) == nodes_before + 2

    async def test_clip_package_compiles_cut_segments(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel = await _seed_select(db)
        package = await compile_plans_package(
            db,
            db.project,
            [_plan_item(sel.id, [{"kind": "clip"}], title="定价短片")],
            persona_id=None,
        )
        assert isinstance(package, CompiledPackage)
        assert [t.tool for t in package.tasks] == ["cut_segments"]
        seg = package.tasks[0].params["segments"][0]
        assert (seg["start"], seg["end"]) == (0.0, 1.0)
        assert package.tasks[0].params["asset_id"] == str(_ASSET_ID)

    async def test_draft_gate_rejects_with_zero_writes(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel = await _seed_select(db)
        nodes_before = len(db.nodes)
        result = await compile_plans_package(
            db,
            db.project,
            # duplicate kind+language — the completeness self-check stamps
            # the plan draft, the pre-flight compile rejects it.
            [_plan_item(sel.id, [{"kind": "post"}, {"kind": "post"}])],
            persona_id=None,
        )
        assert isinstance(result, str)
        assert "still has open gaps" in result
        assert len(db.nodes) == nodes_before  # the door never ran

    async def test_preview_ids_are_preview_namespaced(self) -> None:
        """The pre-flight stand-ins are named preview:{select_id} — a leak of
        the preview id into the package would break the R20 map, so the
        package's keys must be the born rows' real ids (never 'preview:…')."""
        db = _StubDb(assets=[_asset()])
        sel = await _seed_select(db)
        package = await compile_plans_package(
            db,
            db.project,
            [_plan_item(sel.id, [{"kind": "post"}])],
            persona_id=None,
        )
        assert isinstance(package, CompiledPackage)
        assert all(
            not key.startswith("preview:") for key in package.plan_task_map
        )


@pytest.mark.asyncio
class TestRecompileJourneyPackage:
    async def test_real_rows_compile_with_real_id_keys(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel = await _seed_select(db)
        package = await compile_plans_package(
            db,
            db.project,
            [
                _plan_item(sel.id, [{"kind": "post"}], title="A"),
                _plan_item(sel.id, [{"kind": "article"}], title="B"),
            ],
            persona_id=None,
        )
        assert isinstance(package, CompiledPackage)

        recompiled = await recompile_journey_package(
            db, db.project, package.journey_id
        )
        assert isinstance(recompiled, CompiledPackage)
        assert [p.id for p in recompiled.plans] == [p.id for p in package.plans]
        assert [t.tool for t in recompiled.tasks] == ["write_post", "write_article"]
        # The map keys ARE the real row ids (no preview stand-ins here).
        born_ids = [str(p.id) for p in package.plans]
        assert set(recompiled.plan_task_map) == set(born_ids)
        assert recompiled.plan_task_map[born_ids[0]] == [0, 1]
        assert recompiled.plan_task_map[born_ids[1]] == [1, 2]


# ---- the envelope seat (pending_disposition) ----------------------------------------


class TestPendingDisposition:
    def test_defaults_to_none(self) -> None:
        sel = uuid4()
        args = ProposePlansArgs(
            plans=[{"select_id": str(sel), "outputs": [{"kind": "post"}]}]
        )
        assert args.pending_disposition == "none"
        revise = RevisePlanArgs(plan_id=uuid4(), outputs=[{"kind": "post"}])
        assert revise.pending_disposition == "none"

    def test_legal_values_accepted(self) -> None:
        for value in ("answer", "skip", "none"):
            args = ProposePlansArgs(
                plans=[{"select_id": str(uuid4()), "outputs": [{"kind": "post"}]}],
                pending_disposition=value,
            )
            assert args.pending_disposition == value
            revise = RevisePlanArgs(
                plan_id=uuid4(),
                outputs=[{"kind": "post"}],
                pending_disposition=value,
            )
            assert revise.pending_disposition == value

    def test_illegal_value_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProposePlansArgs(
                plans=[{"select_id": str(uuid4()), "outputs": [{"kind": "post"}]}],
                pending_disposition="maybe",
            )
        with pytest.raises(ValidationError):
            RevisePlanArgs(
                plan_id=uuid4(),
                outputs=[{"kind": "post"}],
                pending_disposition="maybe",
            )
