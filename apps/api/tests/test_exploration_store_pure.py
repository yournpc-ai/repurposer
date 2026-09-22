"""Pure tests for the exploration write door (app/pipeline/exploration_store.py).

ADR-088 §2/§4 + I-EXPLORE-01, gated here:

- **Evidence validation** (the door's teeth): start < end, end inside the
  timeline, excerpt verbatim inside its OWN range (normalized containment —
  punctuation retypes pass, paraphrases fail); no timeline → honest reject.
- **Spec shapes**: CandidateSet / Select / ContentPlan serialize into
  graph_nodes.spec with prototype/kind/journey attribution; R7 pointer (no
  source copy); R3 verdict+reason required.
- **Completeness self-check** (拍 5a): clean → ready; issues → draft with
  the issues stamped (never silent).
- **Idempotency**: identical call returns the existing artifact — no twin
  node, no twin journey (the goal IS the journey's identity).
- **The lane**: deterministic frames (x = −464, tail + gap stacking).
- **The door's DB half** rides the _StubDb pattern (test_graph_wiring_pure
  sibling): JSON-path filters stay unevaluated — replay tests seed
  precisely.
"""

import pytest
from uuid import uuid4

from app.models.tables import Asset, GraphNode, Journey, Project
from app.pipeline.exploration_store import (
    CandidateMember,
    ContentPlanSpec,
    ExplorationRejected,
    SelectSpec,
    exploration_lane_frame,
    member_issues,
    normalize_evidence,
    plan_completeness_issues,
    PlanOutput,
    propose_candidates,
    propose_plans,
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


def _asset(with_words: bool = True) -> Asset:
    return Asset(
        id=_ASSET_ID,
        user_id=uuid4(),
        project_id=_PROJECT_ID,
        type="video",
        duration_seconds=60,
        meta={"words": _WORDS} if with_words else {},
    )


def _members(**over):
    base = dict(start=0.0, end=1.0, excerpt="Pricing is hard.")
    base.update(over)
    return [CandidateMember(**base)]


# ---- the stub db (test_graph_wiring_pure pattern + Journey) ---------------------


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
    """Serves GraphNode / Asset / Journey off lists; JSON-path criteria stay
    unevaluated (the pattern's documented limitation — replay tests seed
    precisely)."""

    def __init__(self, nodes=(), assets=(), journeys=()):
        self.project = Project(id=_PROJECT_ID)
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
        }.get(entity, [])
        # plain-column eq only (project_id / type / goal_text) — JSON-path
        # criteria fall through unevaluated by design
        for crit in getattr(stmt, "_where_criteria", []):
            left = getattr(crit, "left", None)
            col = getattr(left, "name", None)
            value = getattr(getattr(crit, "right", None), "value", None)
            op_name = getattr(getattr(crit, "operator", None), "__name__", "")
            if col in ("project_id", "type", "goal_text") and value is not None and op_name == "eq":
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


# ---- normalize_evidence / member_issues / completeness ---------------------------


class TestNormalizeEvidence:
    def test_punctuation_and_case_retypes_pass(self) -> None:
        assert normalize_evidence("Pricing is hard.") == normalize_evidence("pricing is hard")
        assert normalize_evidence("定价难。") == normalize_evidence("定价难")

    def test_paraphrase_fails(self) -> None:
        assert normalize_evidence("Pricing is easy") != normalize_evidence("Pricing is hard")


class TestMemberIssues:
    def test_verbatim_member_passes(self) -> None:
        assert member_issues(_members(), duration_s=60, words=_WORDS) == []

    def test_start_not_before_end(self) -> None:
        issues = member_issues(_members(start=1.0, end=1.0), duration_s=60, words=_WORDS)
        assert any("start" in i for i in issues)

    def test_beyond_timeline(self) -> None:
        issues = member_issues(_members(end=99.0), duration_s=60, words=_WORDS)
        assert any("timeline" in i for i in issues)

    def test_excerpt_outside_own_range(self) -> None:
        # "Fundraising is art." is verbatim speech — but not inside [0,1]
        issues = member_issues(_members(excerpt="Fundraising is art."), duration_s=60, words=_WORDS)
        assert any("not verbatim speech inside its own range" in i for i in issues)

    def test_paraphrase_rejected(self) -> None:
        issues = member_issues(_members(excerpt="Pricing is really hard"), duration_s=60, words=_WORDS)
        assert issues

    def test_empty_members(self) -> None:
        assert member_issues([], duration_s=60, words=_WORDS) == ["candidate set carries no members"]


class TestPlanCompleteness:
    def test_empty_outputs(self) -> None:
        assert plan_completeness_issues([]) == ["content plan names no outputs"]

    def test_duplicate_kind_language(self) -> None:
        outputs = [
            PlanOutput(kind="clip", language="fr"),
            PlanOutput(kind="clip", language="fr"),
        ]
        assert plan_completeness_issues(outputs)

    def test_language_variants_are_distinct(self) -> None:
        outputs = [
            PlanOutput(kind="clip", language="fr"),
            PlanOutput(kind="clip", language=None),
            PlanOutput(kind="post", language="fr"),
        ]
        assert plan_completeness_issues(outputs) == []


class TestLaneFrames:
    def test_first_node_at_lane_top(self) -> None:
        frame = exploration_lane_frame("candidate_set", [])
        assert frame == {"x": -464, "y": 0, "w": 340, "h": 96}

    def test_stacking_below_tail(self) -> None:
        first = GraphNode(
            id=uuid4(), project_id=_PROJECT_ID, type="exploration",
            state="ready", spec={}, layout={"x": -464, "y": 0, "w": 340, "h": 96},
        )
        frame = exploration_lane_frame("select", [first])
        assert frame["x"] == -464
        assert frame["y"] == 96 + 16
        assert (frame["w"], frame["h"]) == (320, 140)


# ---- the door ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestProposeCandidates:
    async def test_happy_path_mints_journey_and_born_ready(self) -> None:
        db = _StubDb(assets=[_asset()])
        node = await propose_candidates(
            db, db.project,
            asset_id=_ASSET_ID, topic="pricing",
            members=_members(), goal_text="把定价最好的回答做成 3 条短视频",
        )
        assert node.state == "ready"
        assert node.type == "exploration"
        assert node.journey_id is not None
        spec = node.spec
        assert spec["prototype"] == "exploration"
        assert spec["exploration_kind"] == "candidate_set"
        assert spec["topic"] == "pricing"
        assert len(spec["members"]) == 1
        assert node.layout["x"] == -464
        assert len(db.journeys) == 1
        assert db.journeys[0].goal_text.startswith("把定价")

    async def test_no_words_is_an_honest_reject(self) -> None:
        db = _StubDb(assets=[_asset(with_words=False)])
        with pytest.raises(ExplorationRejected, match="no timeline"):
            await propose_candidates(
                db, db.project,
                asset_id=_ASSET_ID, topic="pricing",
                members=_members(), goal_text="goal",
            )

    async def test_evidence_reject(self) -> None:
        db = _StubDb(assets=[_asset()])
        with pytest.raises(ExplorationRejected, match="candidate evidence rejected"):
            await propose_candidates(
                db, db.project,
                asset_id=_ASSET_ID, topic="pricing",
                members=_members(excerpt="a paraphrase never spoken"),
                goal_text="goal",
            )

    async def test_replay_returns_existing_no_twin_journey(self) -> None:
        db = _StubDb(assets=[_asset()])
        first = await propose_candidates(
            db, db.project,
            asset_id=_ASSET_ID, topic="pricing",
            members=_members(), goal_text="same goal",
        )
        again = await propose_candidates(
            db, db.project,
            asset_id=_ASSET_ID, topic="pricing",
            members=_members(), goal_text="same goal",
        )
        assert str(again.id) == str(first.id)
        assert len(db.journeys) == 1

    async def test_explicit_journey_adopted(self) -> None:
        journey = Journey(id=uuid4(), project_id=_PROJECT_ID, goal_text="g")
        db = _StubDb(assets=[_asset()], journeys=[journey])
        node = await propose_candidates(
            db, db.project,
            asset_id=_ASSET_ID, topic="pricing",
            members=_members(), journey_id=journey.id,
        )
        assert str(node.journey_id) == str(journey.id)
        assert len(db.journeys) == 1


@pytest.mark.asyncio
class TestProposeSelects:
    async def _seed_set(self, db: _StubDb) -> GraphNode:
        return await propose_candidates(
            db, db.project,
            asset_id=_ASSET_ID, topic="pricing",
            members=[
                CandidateMember(start=0.0, end=1.0, excerpt="Pricing is hard."),
                CandidateMember(start=2.0, end=3.2, excerpt="Fundraising is art."),
            ],
            goal_text="goal",
        )

    async def test_happy_path_inherits_journey(self) -> None:
        db = _StubDb(assets=[_asset()])
        cset = await self._seed_set(db)
        born = await propose_selects(
            db, db.project,
            candidate_set_id=cset.id,
            selects=[{"member_index": 0, "verdict": "最完整回答", "reason": "直接给出定价三步法"}],
        )
        assert len(born) == 1
        spec = SelectSpec.model_validate(born[0].spec)
        assert spec.member_index == 0
        assert spec.candidate_set_id == str(cset.id)
        # R7: a pointer, never a copy — the spec carries NO excerpt text
        assert "excerpt" not in born[0].spec
        assert str(born[0].journey_id) == str(cset.journey_id)

    async def test_member_index_out_of_range(self) -> None:
        db = _StubDb(assets=[_asset()])
        cset = await self._seed_set(db)
        with pytest.raises(ExplorationRejected, match="outside the candidate"):
            await propose_selects(
                db, db.project,
                candidate_set_id=cset.id,
                selects=[{"member_index": 9, "verdict": "v", "reason": "r"}],
            )

    async def test_verdict_and_reason_required(self) -> None:
        db = _StubDb(assets=[_asset()])
        cset = await self._seed_set(db)
        with pytest.raises(ExplorationRejected, match="verdict and reason"):
            await propose_selects(
                db, db.project,
                candidate_set_id=cset.id,
                selects=[{"member_index": 0, "verdict": "", "reason": "r"}],
            )

    async def test_rejects_a_non_candidate_set(self) -> None:
        db = _StubDb(assets=[_asset()])
        cset = await self._seed_set(db)
        sel = (
            await propose_selects(
                db, db.project,
                candidate_set_id=cset.id,
                selects=[{"member_index": 0, "verdict": "v", "reason": "r"}],
            )
        )[0]
        with pytest.raises(ExplorationRejected, match="candidate_set"):
            await propose_selects(
                db, db.project,
                candidate_set_id=sel.id,
                selects=[{"member_index": 0, "verdict": "v", "reason": "r"}],
            )


@pytest.mark.asyncio
class TestProposePlans:
    async def _seed_select(self, db: _StubDb) -> GraphNode:
        cset = await propose_candidates(
            db, db.project,
            asset_id=_ASSET_ID, topic="pricing",
            members=_members(), goal_text="goal",
        )
        return (
            await propose_selects(
                db, db.project,
                candidate_set_id=cset.id,
                selects=[{"member_index": 0, "verdict": "v", "reason": "r"}],
            )
        )[0]

    async def test_clean_plan_born_ready(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel = await self._seed_select(db)
        born = await propose_plans(
            db, db.project,
            plans=[{
                "select_id": str(sel.id),
                "title": "定价三条",
                "outputs": [
                    {"kind": "clip", "language": None, "caption_mode": "bilingual"},
                    {"kind": "post", "language": "fr"},
                ],
            }],
            persona_id=None,
        )
        assert born[0].state == "ready"
        spec = ContentPlanSpec.model_validate(born[0].spec)
        assert spec.title == "定价三条"
        assert len(spec.outputs) == 2
        assert "issues" not in born[0].spec

    async def test_issues_stamp_draft_honestly(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel = await self._seed_select(db)
        born = await propose_plans(
            db, db.project,
            plans=[{
                "select_id": str(sel.id),
                "outputs": [
                    {"kind": "clip", "language": "fr"},
                    {"kind": "clip", "language": "fr"},
                ],
            }],
        )
        assert born[0].state == "draft"
        assert born[0].spec["issues"]

    async def test_cross_journey_rejected(self) -> None:
        db = _StubDb(assets=[_asset()])
        sel_a = await self._seed_select(db)
        # a second journey's select
        cset_b = await propose_candidates(
            db, db.project,
            asset_id=_ASSET_ID, topic="fundraising",
            members=[CandidateMember(start=2.0, end=3.2, excerpt="Fundraising is art.")],
            goal_text="another goal entirely",
        )
        sel_b = (
            await propose_selects(
                db, db.project,
                candidate_set_id=cset_b.id,
                selects=[{"member_index": 0, "verdict": "v", "reason": "r"}],
            )
        )[0]
        with pytest.raises(ExplorationRejected, match="one call plans one journey"):
            await propose_plans(
                db, db.project,
                plans=[
                    {"select_id": str(sel_a.id), "outputs": [{"kind": "clip"}]},
                    {"select_id": str(sel_b.id), "outputs": [{"kind": "clip"}]},
                ],
            )


# ---- I-EXPLORE-01 door halves (ADR-088 §4) -------------------------------------


@pytest.mark.asyncio
async def test_door_births_zero_edges_and_no_estimate_or_prompt():
    """探索写门的 I-EXPLORE-01 半边: a full chain (candidates → selects →
    plans) writes ONLY graph_nodes (+ the journey) — never a GraphEdge,
    and the born specs carry no execution fields (estimate / prompt / tool
    / output_ids) — quote-fold and program-gate inputs never exist on the
    family, by construction."""
    from app.models.tables import GraphEdge, Journey as J

    db = _StubDb(assets=[_asset()])
    cset = await propose_candidates(
        db, db.project,
        asset_id=_ASSET_ID, topic="pricing",
        members=_members(), goal_text="goal",
    )
    sel = (
        await propose_selects(
            db, db.project,
            candidate_set_id=cset.id,
            selects=[{"member_index": 0, "verdict": "v", "reason": "r"}],
        )
    )[0]
    await propose_plans(
        db, db.project,
        plans=[{"select_id": str(sel.id), "outputs": [{"kind": "clip"}]}],
    )
    assert not any(isinstance(o, GraphEdge) for o in db.added)
    exploration_nodes = [
        o for o in db.added
        if isinstance(o, GraphNode) and o.type == "exploration"
    ]
    assert len(exploration_nodes) == 3
    for n in exploration_nodes:
        assert not ({"estimate", "prompt", "tool", "output_ids"} & set(n.spec))


def test_born_spec_keys_are_exactly_the_declared_shape():
    """The spec shape IS the lock: the door constructs specs via
    model_dump — only declared fields exist (extra caller keys can never
    smuggle execution semantics into the family)."""
    spec = ContentPlanSpec(
        select_id="x", outputs=[PlanOutput(kind="clip")]
    ).model_dump()
    assert set(spec) == {
        "prototype", "exploration_kind", "select_id", "title",
        "outputs", "persona_id", "idem",
    }
