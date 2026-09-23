"""Pure tests for the Memory 三窄切 (iter-3 S6, ADR-088 §7 read 洞销账 /
E5 样例参数继承, contract §4 S6).

Gated here (no DB / no LLM / no HTTP — the _StubDb pattern, seeds precise):

- **output_fact / journey_summary_line**: the ONE wording of a plan output's
  spec fact and a journey digest line (two seats — the context block and the
  exemplar injection — share them; the extras ride in the pinned key order
  caption_mode → aspect, dub appended, unnamed variables never speak).
- **read_journey_summaries**: newest-first ordering, the cap, the
  exclude-the-work-in-flight law, plans grouped by journey, the newest
  plan's spec facts, and None-safe created_at ordering (stub sessions never
  fire column defaults).
- **get_artifact** (the perception family's artifact read): tenant law (a
  cross-project / non-exploration / unknown id reads as an honest miss,
  never a crash), the candidate collection's bounded member rendering, the
  pick's R7 dereference (the pointed section rides the read), the plan
  card's deliverables + open gaps, and the unknown-kind fallback.
- **GetArtifactParams**: the boundary model's shape.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.chat.perception.executes import GetArtifactParams, get_artifact
from app.models.tables import GraphNode, Journey, Project
from app.pipeline.exploration_store import (
    JourneySummary,
    journey_summary_line,
    output_fact,
    read_journey_summaries,
)
from app.pipeline.product_graph import EXPLORATION_NODE_TYPE

_PROJECT_ID = uuid4()


# ---- the stub db (test_revise_selects_pure pattern + GraphNode.get) --------


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _StubDb:
    """Serves GraphNode / Journey off lists; JSON-path criteria stay
    unevaluated. Plain-column eq filters: project_id / type / journey_id."""

    def __init__(self, nodes=(), journeys=()):
        self.project = Project(id=_PROJECT_ID, language=None)
        self.nodes = list(nodes)
        self.journeys = list(journeys)

    async def get(self, model, row_id):
        if model is GraphNode:
            return next((n for n in self.nodes if str(n.id) == str(row_id)), None)
        if model is Journey:
            return next((j for j in self.journeys if str(j.id) == str(row_id)), None)
        return None

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        rows = {
            GraphNode: self.nodes,
            Journey: self.journeys,
        }.get(entity, [])
        for crit in getattr(stmt, "_where_criteria", []):
            left = getattr(crit, "left", None)
            col = getattr(left, "name", None)
            value = getattr(getattr(crit, "right", None), "value", None)
            op_name = getattr(getattr(crit, "operator", None), "__name__", "")
            if (
                col in ("project_id", "type", "journey_id")
                and value is not None
                and op_name == "eq"
            ):
                rows = [r for r in rows if str(getattr(r, col, None)) == str(value)]
        return _StubResult(list(rows))


def _journey(*, goal="grow the channel", created=None, project_id=None) -> Journey:
    j = Journey(id=uuid4(), project_id=project_id or _PROJECT_ID, goal_text=goal)
    j.created_at = created
    return j


def _node(
    kind: str,
    *,
    journey_id,
    spec: dict,
    state="ready",
    created=None,
    project_id=None,
) -> GraphNode:
    n = GraphNode(
        id=uuid4(),
        project_id=project_id or _PROJECT_ID,
        type=EXPLORATION_NODE_TYPE,
        state=state,
        journey_id=journey_id,
        spec={"exploration_kind": kind, **spec},
    )
    n.created_at = created
    return n


def _plan(journey_id, outputs, *, created=None, title="Plan", issues=None):
    return _node(
        "content_plan",
        journey_id=journey_id,
        created=created,
        spec={
            "select_id": str(uuid4()),
            "title": title,
            "outputs": outputs,
            "issues": issues or [],
        },
    )


# ---- output_fact / journey_summary_line -------------------------------------


class TestOutputFact:
    def test_full_clip_fact_key_order(self) -> None:
        fact = output_fact(
            {
                "kind": "clip",
                "language": "fr",
                "caption_mode": "word_pop",
                "aspect": "9:16",
                "dub": True,
            }
        )
        # The pinned order: caption_mode → aspect, dub appended last.
        assert fact == "clip:fr(word_pop,9:16,dub)"

    def test_kind_and_language_only(self) -> None:
        assert output_fact({"kind": "post", "language": "en"}) == "post:en"

    def test_bare_kind(self) -> None:
        assert output_fact({"kind": "article"}) == "article"

    def test_unnamed_variables_never_speak(self) -> None:
        # caption_mode/dub absent → nothing invented (世界自证, not defaults).
        assert output_fact({"kind": "clip", "language": "en"}) == "clip:en"


class TestJourneySummaryLine:
    def test_line_with_facts(self) -> None:
        summary = JourneySummary(
            journey_id=uuid4(),
            goal="launch week clips",
            plan_count=2,
            output_count=3,
            spec_facts=("clip:fr(dub)", "post:en"),
        )
        assert journey_summary_line(summary) == (
            'goal "launch week clips": 2 plan(s), 3 output(s); '
            "last plan: clip:fr(dub), post:en"
        )

    def test_line_without_facts(self) -> None:
        summary = JourneySummary(
            journey_id=uuid4(), goal="g", plan_count=0, output_count=0
        )
        assert journey_summary_line(summary) == 'goal "g": 0 plan(s), 0 output(s)'

    def test_goal_truncated_at_80(self) -> None:
        summary = JourneySummary(
            journey_id=uuid4(), goal="x" * 200, plan_count=1, output_count=1
        )
        line = journey_summary_line(summary)
        assert '"%s"' % ("x" * 80) in line
        assert "x" * 81 not in line


# ---- read_journey_summaries -------------------------------------------------


@pytest.mark.asyncio
class TestReadJourneySummaries:
    async def test_newest_first_with_cap(self) -> None:
        old = _journey(goal="old", created=datetime(2026, 9, 1, tzinfo=UTC))
        mid = _journey(goal="mid", created=datetime(2026, 9, 10, tzinfo=UTC))
        new = _journey(goal="new", created=datetime(2026, 9, 20, tzinfo=UTC))
        db = _StubDb(journeys=[old, new, mid])  # insertion order ≠ sort order
        summaries = await read_journey_summaries(db, _PROJECT_ID, cap=2)
        assert [s.goal for s in summaries] == ["new", "mid"]  # cap bites

    async def test_exclude_the_work_in_flight(self) -> None:
        current = _journey(goal="current", created=datetime(2026, 9, 20, tzinfo=UTC))
        past = _journey(goal="past", created=datetime(2026, 9, 1, tzinfo=UTC))
        db = _StubDb(journeys=[current, past])
        summaries = await read_journey_summaries(
            db, _PROJECT_ID, cap=3, exclude_journey_id=current.id
        )
        assert [s.goal for s in summaries] == ["past"]

    async def test_plans_grouped_and_newest_plan_facts(self) -> None:
        j = _journey(goal="g", created=datetime(2026, 9, 20, tzinfo=UTC))
        other = _journey(goal="other", created=datetime(2026, 9, 19, tzinfo=UTC))
        older_plan = _plan(
            j.id,
            [{"kind": "clip", "language": "en"}],
            created=datetime(2026, 9, 20, 1, tzinfo=UTC),
        )
        newer_plan = _plan(
            j.id,
            [
                {"kind": "clip", "language": "fr", "dub": True},
                {"kind": "post", "language": "fr"},
            ],
            created=datetime(2026, 9, 20, 2, tzinfo=UTC),
        )
        other_plan = _plan(other.id, [{"kind": "quotes"}], created=None)
        db = _StubDb(
            journeys=[j, other],
            nodes=[newer_plan, other_plan, older_plan],
        )
        summaries = await read_journey_summaries(db, _PROJECT_ID)
        first = summaries[0]
        assert first.plan_count == 2
        assert first.output_count == 3  # aggregated over BOTH plans
        assert first.spec_facts == ("clip:fr(dub)", "post:fr")  # newest plan only
        assert summaries[1].spec_facts == ("quotes",)

    async def test_journey_without_plans(self) -> None:
        j = _journey(goal="empty", created=datetime(2026, 9, 20, tzinfo=UTC))
        db = _StubDb(journeys=[j])
        (summary,) = await read_journey_summaries(db, _PROJECT_ID)
        assert summary.plan_count == 0
        assert summary.output_count == 0
        assert summary.spec_facts == ()

    async def test_none_created_at_sorts_stable(self) -> None:
        # Stub sessions never fire column defaults — None keys must not crash
        # the ordering ("" sorts below any real timestamp: real rows first).
        a = _journey(goal="a", created=None)
        b = _journey(goal="b", created=datetime(2026, 9, 20, tzinfo=UTC))
        db = _StubDb(journeys=[a, b])
        summaries = await read_journey_summaries(db, _PROJECT_ID)
        assert [s.goal for s in summaries] == ["b", "a"]

    async def test_tenant_scoped(self) -> None:
        mine = _journey(goal="mine", created=None)
        theirs = _journey(goal="theirs", created=None, project_id=uuid4())
        db = _StubDb(journeys=[mine, theirs])
        summaries = await read_journey_summaries(db, _PROJECT_ID)
        assert [s.goal for s in summaries] == ["mine"]


# ---- get_artifact -----------------------------------------------------------


@pytest.mark.asyncio
class TestGetArtifact:
    async def test_unknown_id_is_an_honest_miss(self) -> None:
        db = _StubDb()
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=uuid4())
        )
        assert "No exploration artifact" in text

    async def test_cross_tenant_is_an_honest_miss(self) -> None:
        node = _node(
            "candidate_set",
            journey_id=uuid4(),
            project_id=uuid4(),  # another project's row
            spec={"topic": "t", "members": []},
        )
        db = _StubDb(nodes=[node])
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=node.id)
        )
        assert "No exploration artifact" in text

    async def test_non_exploration_node_is_an_honest_miss(self) -> None:
        node = GraphNode(
            id=uuid4(),
            project_id=_PROJECT_ID,
            type="video",
            state="done",
            spec={"summary": "clip"},
        )
        db = _StubDb(nodes=[node])
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=node.id)
        )
        assert "No exploration artifact" in text

    async def test_candidate_collection_renders_members_bounded(self) -> None:
        members = [
            {"start": i, "end": i + 1, "excerpt": f"line {i}", "speaker": "host"}
            for i in range(14)
        ]
        node = _node(
            "candidate_set",
            journey_id=uuid4(),
            spec={"topic": "pricing", "members": members},
        )
        db = _StubDb(nodes=[node])
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=node.id)
        )
        assert 'topic "pricing"' in text
        assert "14 section(s)" in text
        assert "11) " in text  # members 0..11 render
        assert "12) " not in text and "13) " not in text  # capped at 12
        assert "… (2 more sections)" in text
        assert "[0–1s] host: line 0" in text

    async def test_pick_dereferences_the_pointed_section(self) -> None:
        cset = _node(
            "candidate_set",
            journey_id=uuid4(),
            spec={
                "topic": "pricing",
                "members": [
                    {"start": 0.0, "end": 1.0, "excerpt": "zero", "speaker": "h"},
                    {"start": 2.0, "end": 3.2, "excerpt": "Fundraising is art.", "speaker": "h"},
                ],
            },
        )
        pick = _node(
            "select",
            journey_id=uuid4(),
            spec={
                "candidate_set_id": str(cset.id),
                "member_index": 1,
                "verdict": "the arc turn",
                "reason": "names the stakes",
            },
        )
        db = _StubDb(nodes=[cset, pick])
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=pick.id)
        )
        assert "member 1 of collection" in text
        assert "verdict: the arc turn" in text
        assert "reason: names the stakes" in text
        # R7: the pointed section rides the read — no second read needed.
        assert "[2.0–3.2s] Fundraising is art." in text

    async def test_pick_with_a_gone_collection_never_crashes(self) -> None:
        pick = _node(
            "select",
            journey_id=uuid4(),
            spec={
                "candidate_set_id": str(uuid4()),
                "member_index": 0,
                "verdict": "v",
                "reason": "r",
            },
        )
        db = _StubDb(nodes=[pick])
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=pick.id)
        )
        assert "verdict: v" in text
        assert "the section" not in text

    async def test_plan_card_renders_deliverables_and_gaps(self) -> None:
        plan = _plan(
            uuid4(),
            [
                {
                    "kind": "clip",
                    "language": "fr",
                    "dub": True,
                    "brief": "the pricing turn",
                },
                {"kind": "post", "language": "en"},
            ],
            title="Launch week",
            issues=["caption language undecided"],
        )
        db = _StubDb(nodes=[plan])
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=plan.id)
        )
        assert "Launch week" in text
        assert "2 output(s)" in text
        assert "clip:fr(dub) — the pricing turn" in text
        assert "post:en" in text
        assert "open gaps: caption language undecided" in text

    async def test_unknown_kind_falls_back(self) -> None:
        node = _node("mystery", journey_id=uuid4(), spec={})
        db = _StubDb(nodes=[node])
        text = await get_artifact(
            db, db.project, GetArtifactParams(artifact_id=node.id)
        )
        assert "unrecognized kind" in text


class TestGetArtifactParams:
    def test_artifact_id_required_and_coerced(self) -> None:
        with pytest.raises(Exception):
            GetArtifactParams()
        params = GetArtifactParams(artifact_id=str(uuid4()))
        assert params.artifact_id is not None
