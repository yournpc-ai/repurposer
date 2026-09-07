"""Pure-function tests for the graph write layer (ADR-057 wiring door).

Scope discipline (same as test_intent_layer_pure.py — why this suite exists
and what it must never become): covers ONLY deterministic adjudication — no
database, no LLM, no HTTP; the session is an in-memory stub serving the two
graph tables. If a behavior needs a real transaction or an LLM to verify, it
belongs to a manual e2e run (the chat_scenarios wiring assertions), not here.

Covered:
- apply_wiring_ops happy path: add_node (+after shorthand edges), port-law
  edge-type derivation, born states (asset done / others draft), 定居取景
  layout (existing frames never move), GraphDelta contents, single flush
- op schema-shape rejection (pydantic) and every domain rejection: dangling
  reference / self-loop / incompatible ports / cycle / duplicate edge /
  edit_prompt on wrong kind / edit_prompt while running / unknown nodes
- edit_prompt semantics: done → stale, draft stays draft, prompt written
- delete_node: edges die structurally with it
- run op: explicit seeds ∪ downstream closure (layout order), default
  seeds = the batch's affected set
- batch atomicity: a failing op kills the batch BEFORE the flush — never a
  half-applied graph (the caller's transaction rolls back)
- sync_graph_node_for_step's 版本累积: a re-fill's landed products JOIN the
  node's existing output_ids (the pager's version lineage), never a cleared
  slate; the research agent's brief document mirrors its terminal + text
- stamp_transcript_node (转写稿 document): born done with the text edge,
  idempotent, refreshes on reprocess, skips text-less assets
- _stamp_graph_core's research-brief document: born with its agent (draft /
  queued), derivation edge, orphan-swept when the chain drops research
- _fill_key_for_step idempotency fingerprints (graph_fill): producer slot /
  translate·dub transform / bare-kind shapes — a re-run of the same slot
  finds its node, a new slot grows one
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.schemas import AssetType
from app.models.tables import Asset, GraphEdge, GraphNode, Project, WorkflowRun, WorkflowStep
from app.pipeline.graph_fill import (
    _fill_key_for_step,
    _stamp_graph_core,
    stamp_transcript_node,
    sync_graph_node_for_step,
)
from app.pipeline.graph_store import WiringRejected, apply_wiring_ops

_PROJECT_ID = uuid4()


# ---- in-memory session stub (the two graph tables + a Project row) --------


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        # Stub limitation: WHERE clauses are NOT evaluated — the tests seed
        # precisely so the full list already is the answer.
        return self._rows[0] if self._rows else None


class _StubDb:
    """AsyncSession stand-in: serves GraphNode/GraphEdge selects off lists,
    records writes. ``flush_count`` is the batch-atomicity witness — a
    rejected batch must die BEFORE any flush."""

    def __init__(self, nodes=(), edges=(), steps=()):
        self.project = Project(id=_PROJECT_ID)
        self.nodes = list(nodes)
        self.edges = list(edges)
        self.steps = list(steps)
        self.added: list = []
        self.deleted: list = []
        self.flush_count = 0

    async def get(self, model, row_id):
        if model is Project:
            return self.project if str(row_id) == str(self.project.id) else None
        if model is GraphNode:
            return next((n for n in self.nodes if str(n.id) == str(row_id)), None)
        if model is WorkflowStep:
            return next((s for s in self.steps if str(s.id) == str(row_id)), None)
        return None

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is GraphNode:
            rows = self.nodes
        elif entity is GraphEdge:
            rows = self.edges
        elif entity is WorkflowStep:
            rows = self.steps
        else:
            return _StubResult([])
        return _StubResult(self._apply_where(list(rows), stmt))

    @staticmethod
    def _apply_where(rows, stmt):
        """The stub's mini-WHERE: evaluates simple ``col == v`` / ``col IN (...)`
        criteria on plain columns (id / kind / type / status / project_id).
        Anything fancier (JSON-path filters) stays unevaluated — the tests
        seed precisely for those."""
        for crit in getattr(stmt, "_where_criteria", []):
            left = getattr(crit, "left", None)
            op_name = getattr(getattr(crit, "operator", None), "__name__", "")
            value = getattr(getattr(crit, "right", None), "value", None)
            col = getattr(left, "name", None)
            if col is None or value is None:
                continue
            if op_name == "eq":
                rows = [r for r in rows if str(getattr(r, col, None)) == str(value)]
            elif op_name == "in_op":
                values = {str(v) for v in value}
                rows = [r for r in rows if str(getattr(r, col, None)) in values]
        return rows

    def _register(self, obj):
        """Read-after-write: a landed row is visible to the next select
        (deduped — the door re-adds the whole working set at landing)."""
        bucket = self.nodes if isinstance(obj, GraphNode) else self.edges if isinstance(obj, GraphEdge) else None
        if bucket is not None and all(str(r.id) != str(obj.id) for r in bucket):
            bucket.append(obj)

    def add(self, obj):
        self.added.append(obj)
        self._register(obj)

    async def delete(self, obj):
        self.deleted.append(obj)
        if isinstance(obj, GraphNode):
            self.nodes = [n for n in self.nodes if str(n.id) != str(obj.id)]
            # the FK cascade's stub form: the node's edges die with it
            self.edges = [
                e
                for e in self.edges
                if str(e.from_node) != str(obj.id) and str(e.to_node) != str(obj.id)
            ]
        elif isinstance(obj, GraphEdge):
            self.edges = [e for e in self.edges if str(e.id) != str(obj.id)]

    async def flush(self):
        self.flush_count += 1


def _node(kind, *, state="draft", spec=None, layout=None):
    return GraphNode(
        id=uuid4(),
        project_id=_PROJECT_ID,
        kind=kind,
        state=state,
        spec=spec or {},
        layout=dict(layout or {"x": 0, "y": 0, "w": 280, "h": 260}),
    )


def _edge(from_id, to_id, edge_type):
    return GraphEdge(
        id=uuid4(),
        project_id=_PROJECT_ID,
        from_node=from_id,
        from_port=f"out:{edge_type}",
        to_node=to_id,
        to_port=f"in:{edge_type}",
        edge_type=edge_type,
    )


# ---- happy path -------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_node_with_after_derives_edge_state_layout():
    asset = _node("asset", state="done", spec={"asset_type": "video"})
    db = _StubDb(nodes=[asset])
    delta = await apply_wiring_ops(
        db,
        _PROJECT_ID,
        # ``after`` is connect's shorthand — the edge's type derives off the
        # two ends' ports (a video asset → a generator = the video flow).
        [{"op": "add_node", "kind": "generator", "spec": {"prompt": "p"}, "after": [asset.id]}],
    )
    assert len(delta.affected) == 1
    newborn = next(n for n in db.added if isinstance(n, GraphNode) and n.id == delta.affected[0])
    assert newborn.state == "draft"  # 图先展示后运行 — zero consumption until a run
    edge = next(e for e in db.added if isinstance(e, GraphEdge))
    assert (edge.from_node, edge.to_node, edge.edge_type) == (asset.id, newborn.id, "video")
    # 定居取景: x = the parent's right edge + the main gap; existing frames
    # never move (append-only 保序律).
    assert newborn.layout["x"] == 280 + 96
    assert newborn.layout["y"] == 0
    assert asset.layout == {"x": 0, "y": 0, "w": 280, "h": 260}
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_asset_node_is_born_done():
    db = _StubDb()
    await apply_wiring_ops(
        db, _PROJECT_ID, [{"op": "add_node", "kind": "asset", "spec": {"asset_type": "audio"}}]
    )
    assert db.added[0].state == "done"  # an input, not an execution unit


@pytest.mark.asyncio
async def test_connect_derivation_prefers_concrete_and_ctx_is_never_invented():
    doc = _node("document", spec={"role": "task_book"})
    gen = _node("generator")
    db = _StubDb(nodes=[doc, gen])
    # document offers text+ctx — the derivation prefers the concrete flow.
    await apply_wiring_ops(db, _PROJECT_ID, [{"op": "connect", "from_node": doc.id, "to_node": gen.id}])
    assert db.added[-1].edge_type == "text"
    # ctx lands only when named explicitly.
    gen2 = _node("generator")
    db.nodes.append(gen2)
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [{"op": "connect", "from_node": doc.id, "to_node": gen2.id, "edge_type": "ctx"}],
    )
    assert db.added[-1].edge_type == "ctx"


@pytest.mark.asyncio
async def test_same_pair_allows_distinct_edge_types():
    asset = _node("asset", state="done", spec={"asset_type": "video"})
    gen = _node("generator")
    db = _StubDb(nodes=[asset, gen], edges=[_edge(asset.id, gen.id, "video")])
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [{"op": "connect", "from_node": asset.id, "to_node": gen.id, "edge_type": "text"}],
    )
    assert db.added[-1].edge_type == "text"


# ---- rejections (op schema + every domain gate) -----------------------------


@pytest.mark.asyncio
async def test_unknown_op_shape_rejected_at_the_schema_boundary():
    db = _StubDb()
    with pytest.raises(ValidationError):
        await apply_wiring_ops(db, _PROJECT_ID, [{"op": "rewire_everything"}])
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_connect_dangling_reference_rejected():
    a = _node("generator")
    with pytest.raises(WiringRejected, match="dangling"):
        await apply_wiring_ops(
            _StubDb(nodes=[a]), _PROJECT_ID, [{"op": "connect", "from_node": uuid4(), "to_node": a.id}]
        )


@pytest.mark.asyncio
async def test_connect_self_loop_rejected():
    a = _node("generator")
    with pytest.raises(WiringRejected, match="itself"):
        await apply_wiring_ops(
            _StubDb(nodes=[a]), _PROJECT_ID, [{"op": "connect", "from_node": a.id, "to_node": a.id}]
        )


@pytest.mark.asyncio
async def test_connect_incompatible_ports_rejected():
    src = _node("generator")
    dst = _node("asset", state="done", spec={"asset_type": "video"})  # accepts nothing
    with pytest.raises(WiringRejected, match="No compatible port"):
        await apply_wiring_ops(
            _StubDb(nodes=[src, dst]),
            _PROJECT_ID,
            [{"op": "connect", "from_node": src.id, "to_node": dst.id}],
        )


@pytest.mark.asyncio
async def test_connect_cycle_rejected():
    a, b = _node("generator"), _node("generator")
    db = _StubDb(nodes=[a, b], edges=[_edge(a.id, b.id, "video")])
    with pytest.raises(WiringRejected, match="cycle"):
        await apply_wiring_ops(db, _PROJECT_ID, [{"op": "connect", "from_node": b.id, "to_node": a.id}])
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_connect_duplicate_edge_rejected():
    a, b = _node("generator"), _node("generator")
    db = _StubDb(nodes=[a, b], edges=[_edge(a.id, b.id, "video")])
    with pytest.raises(WiringRejected, match="duplicate"):
        await apply_wiring_ops(
            db, _PROJECT_ID, [{"op": "connect", "from_node": a.id, "to_node": b.id, "edge_type": "video"}]
        )


@pytest.mark.asyncio
async def test_edit_prompt_done_goes_stale_and_writes_the_program():
    done = _node("generator", state="done", spec={"prompt": "old"})
    db = _StubDb(nodes=[done])
    delta = await apply_wiring_ops(
        db, _PROJECT_ID, [{"op": "edit_prompt", "node": done.id, "prompt": "new program"}]
    )
    assert done.spec["prompt"] == "new program"
    assert done.state == "stale"  # the product now predates the program
    assert delta.affected == [done.id]


@pytest.mark.asyncio
async def test_edit_prompt_on_a_draft_stays_a_draft():
    draft = _node("generator", state="draft")
    await apply_wiring_ops(
        _StubDb(nodes=[draft]), _PROJECT_ID, [{"op": "edit_prompt", "node": draft.id, "prompt": "x"}]
    )
    assert draft.state == "draft"  # the preview's program revised before any run


@pytest.mark.asyncio
async def test_edit_prompt_rejections():
    proc = _node("processor")
    with pytest.raises(WiringRejected, match="no prompt"):
        await apply_wiring_ops(
            _StubDb(nodes=[proc]), _PROJECT_ID, [{"op": "edit_prompt", "node": proc.id, "prompt": "x"}]
        )
    running = _node("generator", state="running")
    with pytest.raises(WiringRejected, match="running"):
        await apply_wiring_ops(
            _StubDb(nodes=[running]),
            _PROJECT_ID,
            [{"op": "edit_prompt", "node": running.id, "prompt": "x"}],
        )
    with pytest.raises(WiringRejected, match="unknown node"):
        await apply_wiring_ops(
            _StubDb(), _PROJECT_ID, [{"op": "edit_prompt", "node": uuid4(), "prompt": "x"}]
        )


@pytest.mark.asyncio
async def test_delete_node_takes_its_edges_structurally():
    a = _node("asset", state="done", spec={"asset_type": "video"})
    b = _node("generator")
    db = _StubDb(nodes=[a, b], edges=[_edge(a.id, b.id, "video")])
    delta = await apply_wiring_ops(db, _PROJECT_ID, [{"op": "delete_node", "node": a.id}])
    assert delta.affected == [a.id]
    assert [type(d) for d in db.deleted] == [GraphNode]
    # the edge died with it in the working set — a follow-up batch wiring
    # from the deleted node dangles
    with pytest.raises(WiringRejected, match="dangling"):
        await apply_wiring_ops(
            _StubDb(nodes=[b]), _PROJECT_ID, [{"op": "connect", "from_node": a.id, "to_node": b.id}]
        )


@pytest.mark.asyncio
async def test_run_op_closes_over_downstream_in_layout_order():
    a = _node("generator", layout={"x": 0, "y": 0, "w": 280, "h": 260})
    b = _node("processor", layout={"x": 376, "y": 0, "w": 280, "h": 260})
    c = _node("generator", layout={"x": 752, "y": 0, "w": 280, "h": 260})
    island = _node("generator", layout={"x": 0, "y": 400, "w": 280, "h": 260})
    edges = [_edge(a.id, b.id, "video"), _edge(b.id, c.id, "video")]
    db = _StubDb(nodes=[a, b, c, island], edges=edges)
    delta = await apply_wiring_ops(db, _PROJECT_ID, [{"op": "run", "nodes": [a.id]}])
    assert delta.run_nodes == [a.id, b.id, c.id]  # the island stays out


@pytest.mark.asyncio
async def test_run_op_default_seeds_are_the_batchs_affected_set():
    a = _node("generator", state="stale", layout={"x": 0, "y": 0, "w": 280, "h": 260})
    b = _node("processor", layout={"x": 376, "y": 0, "w": 280, "h": 260})
    db = _StubDb(nodes=[a, b], edges=[_edge(a.id, b.id, "video")])
    # the edit_prompt → run pair (the chat revision's one form)
    delta = await apply_wiring_ops(
        db, _PROJECT_ID, [{"op": "edit_prompt", "node": a.id, "prompt": "p"}, {"op": "run"}]
    )
    assert delta.run_nodes == [a.id, b.id]


@pytest.mark.asyncio
async def test_run_op_unknown_seed_rejected():
    with pytest.raises(WiringRejected, match="unknown node"):
        await apply_wiring_ops(_StubDb(), _PROJECT_ID, [{"op": "run", "nodes": [uuid4()]}])


@pytest.mark.asyncio
async def test_a_failing_op_kills_the_batch_before_any_flush():
    good = _node("generator")
    db = _StubDb(nodes=[good])
    with pytest.raises(WiringRejected):
        await apply_wiring_ops(
            db,
            _PROJECT_ID,
            [
                {"op": "edit_prompt", "node": good.id, "prompt": "x"},
                {"op": "connect", "from_node": good.id, "to_node": uuid4()},
            ],
        )
    assert db.flush_count == 0  # never a half-applied graph — the caller rolls back


# ---- sync back-write: 版本累积 (the pager's version lineage) ----------------


@pytest.mark.asyncio
async def test_sync_back_write_accumulates_versions():
    old_id, new_id = uuid4(), uuid4()
    node = _node("generator", state="done", spec={"output_ids": [str(old_id)]})
    step = WorkflowStep(
        id=uuid4(),
        kind="write_post",
        status="done",
        spec={"graph_node_id": str(node.id)},
        output_refs=[new_id],
    )
    node.spec["step_ids"] = [str(step.id)]
    db = _StubDb(nodes=[node], steps=[step])
    await sync_graph_node_for_step(db, step)
    # the re-fill's product JOINS the lineage — the card pages old ∪ new
    assert node.spec["output_ids"] == [str(old_id), str(new_id)]
    # idempotent: the same terminal re-synced adds nothing twice
    await sync_graph_node_for_step(db, step)
    assert node.spec["output_ids"] == [str(old_id), str(new_id)]


# ---- fill-key idempotency fingerprints (graph_fill) --------------------------


def test_fill_key_producer_slot_shape():
    post0 = WorkflowStep(kind="write_post", spec={"slot": {"type": "post"}, "slot_index": 0})
    post0_again = WorkflowStep(kind="write_post", spec={"slot": {"type": "post"}, "slot_index": 0})
    # a re-run of the same slot finds its node
    assert _fill_key_for_step(post0) == _fill_key_for_step(post0_again) == "write_post#post#0"
    post1 = WorkflowStep(kind="write_post", spec={"slot": {"type": "post"}, "slot_index": 1})
    assert _fill_key_for_step(post1) != _fill_key_for_step(post0)  # a new slot grows one
    clips = WorkflowStep(kind="select_clips", spec={"slot": {"type": "clips"}, "slot_index": 0})
    assert _fill_key_for_step(clips) == "select_clips#clips#0"


def test_fill_key_translate_dub_shape():
    de = WorkflowStep(kind="translate_clip", spec={"target_language": "de", "fork": True})
    fr = WorkflowStep(kind="translate_clip", spec={"target_language": "fr", "fork": True})
    assert _fill_key_for_step(de) == "translate_clip#de#False#True"
    assert _fill_key_for_step(de) != _fill_key_for_step(fr)  # each language its own node


def test_fill_key_bare_kind_for_deterministic_steps():
    assert _fill_key_for_step(WorkflowStep(kind="remove_filler", spec={})) == "remove_filler"
    assert _fill_key_for_step(WorkflowStep(kind="research", spec={"query": "q"})) == "research"


# ---- 转写稿 document (stamp_transcript_node) ---------------------------------


def _asset(**kw):
    return Asset(
        id=uuid4(),
        project_id=_PROJECT_ID,
        type=kw.pop("type", AssetType.VIDEO),
        **kw,
    )


@pytest.mark.asyncio
async def test_transcript_node_skips_textless_assets():
    db = _StubDb()
    assert await stamp_transcript_node(db, _PROJECT_ID, _asset()) is None
    assert db.added == []


@pytest.mark.asyncio
async def test_transcript_node_born_done_with_text_edge_and_idempotent():
    asset = _asset(transcript="the quick brown fox")
    db = _StubDb()
    doc = await stamp_transcript_node(db, _PROJECT_ID, asset)
    assert doc is not None
    assert doc.state == "done"  # an artifact, not an execution unit
    assert doc.kind == "document"
    assert doc.spec["role"] == "transcript"
    assert doc.spec["text"] == "the quick brown fox"
    edge = next(e for e in db.edges if e.to_node == doc.id)
    assert edge.edge_type == "text"
    # idempotent: a second stamp finds the same card — no twin, no second
    # edge (re-seeded stub: the doc-check's filtered select returns it).
    db2 = _StubDb(nodes=[doc], edges=list(db.edges))
    again = await stamp_transcript_node(db2, _PROJECT_ID, asset)
    assert str(again.id) == str(doc.id)
    assert db2.added == []


@pytest.mark.asyncio
async def test_transcript_node_text_refreshes_on_reprocess():
    asset = _asset(transcript="v1")
    db = _StubDb()
    doc = await stamp_transcript_node(db, _PROJECT_ID, asset)
    asset.transcript = "v2 — reprocessed"
    again = await stamp_transcript_node(_StubDb(nodes=[doc]), _PROJECT_ID, asset)
    assert str(again.id) == str(doc.id)
    assert again.spec["text"] == "v2 — reprocessed"


# ---- research brief document (_stamp_graph_core + sync mirror) ---------------


def _research_chain():
    research = WorkflowStep(
        id=uuid4(), kind="research", seq=1, spec={"query": "grid storage"}, estimate=None
    )
    post = WorkflowStep(
        id=uuid4(),
        kind="write_post",
        seq=2,
        spec={"slot": {"type": "post"}, "slot_index": 0},
        estimate=None,
    )
    post.inputs = [str(research.id)]
    research.inputs = []
    return [research, post]


@pytest.mark.asyncio
async def test_research_brief_doc_born_with_agent_and_swept_without_it():
    project = Project(id=_PROJECT_ID)
    db = _StubDb()
    await _stamp_graph_core(
        db, project, _research_chain(), run=None, ui_language="en", draft=True, book_text="b"
    )
    agent = next(n for n in db.nodes if n.kind == "agent")
    doc = next(
        n for n in db.nodes if n.kind == "document" and (n.spec or {}).get("role") == "research_brief"
    )
    assert doc.state == "draft"  # the preview's promise
    assert (agent.spec or {}).get("brief_doc_id") == str(doc.id)
    edge = next(e for e in db.edges if str(e.to_node) == str(doc.id))
    assert (str(edge.from_node), edge.edge_type) == (str(agent.id), "text")
    # the writer still wires from the AGENT (the execution truth — leaf face)
    writer = next(n for n in db.nodes if n.kind == "generator")
    assert any(
        str(e.from_node) == str(agent.id) and str(e.to_node) == str(writer.id) for e in db.edges
    )
    # a re-docked chain WITHOUT research orphan-sweeps the brief doc
    db2 = _StubDb(nodes=list(db.nodes), edges=list(db.edges))
    post_only = [_research_chain()[1]]
    await _stamp_graph_core(
        db2, project, post_only, run=None, ui_language="en", draft=True, book_text="b"
    )
    assert not [
        n for n in db2.nodes if n.kind == "document" and (n.spec or {}).get("role") == "research_brief"
    ]


@pytest.mark.asyncio
async def test_research_brief_doc_queued_in_run_mode_and_mirrored_at_sync():
    project = Project(id=_PROJECT_ID)
    run = WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, context={})
    steps = _research_chain()
    db = _StubDb(steps=steps)
    await _stamp_graph_core(
        db, project, steps, run=run, ui_language="en", draft=False, book_text=None
    )
    doc = next(
        n for n in db.nodes if n.kind == "document" and (n.spec or {}).get("role") == "research_brief"
    )
    assert doc.state == "queued"
    # the loop closes: the brief lands on the research step's spec, the sync
    # mirrors the agent's terminal + renders the text onto the doc
    research = steps[0]
    research.status = "done"
    research.spec = {
        **(research.spec or {}),
        "research_brief": {
            "summary": "Storage is the bottleneck.",
            "key_facts": ["Fact one", "Fact two"],
            "sources": [{"title": "t", "url": "u"}],
            "caveat": None,
        },
    }
    await sync_graph_node_for_step(db, research)
    assert doc.state == "done"
    assert "Storage is the bottleneck." in doc.spec["text"]
    assert "• Fact one" in doc.spec["text"]
