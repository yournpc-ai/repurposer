"""Pure-function tests for the graph write layer (ADR-057 wiring door).

Scope discipline (same as test_intent_layer_pure.py — why this suite exists
and what it must never become): covers ONLY deterministic adjudication — no
database, no LLM, no HTTP; the session is an in-memory stub serving the two
graph tables. If a behavior needs a real transaction or an LLM to verify, it
belongs to a manual e2e run (the chat_scenarios wiring assertions), not here.

Covered:
- apply_wiring_ops happy path: add_node (+after shorthand edges), port-law
  edge-type derivation, born states (asset done / others draft), 定居取景
  layout (existing frames never move), GraphDelta contents, two-stage flush
  (nodes strictly before edges — ADR-059)
- disconnect (ADR-062 边对账律的写门手势): severs exactly one typed triple,
  missing triple rejected, a same-batch newborn edge drops without a DELETE,
  and a disconnect-led batch frees the cycle check for a topology flip
- op schema-shape rejection (pydantic) and every domain rejection: dangling
  reference / self-loop / incompatible ports / cycle / duplicate edge /
  edit_prompt on wrong kind / edit_prompt while running / unknown nodes
- edit_prompt semantics: done → stale, draft stays draft, prompt written
- delete_node: edges die structurally with it
- run op: explicit seeds ∪ downstream closure (DAG topology order — I-PFA-04
  / C-2, NEVER layout.x: reversed-frame regressions, canvas-hidden modifier
  ordering, deterministic same-rank tiebreak), default
  seeds = the batch's affected set
- batch atomicity: a failing op kills the batch BEFORE the flush — never a
  half-applied graph (the caller's transaction rolls back)
- sync_graph_node_for_step's 版本累积: a re-fill's landed products JOIN the
  node's existing output_ids (the pager's version lineage), never a cleared
  slate; the v3 text back-writes — a writer node's spec.text reads its
  latest Output's content, a research node's spec.text renders the brief
- stamp_transcript_node (转写稿 document): born done with the text edge,
  idempotent, refreshes on reprocess, skips text-less assets
- _stamp_graph_core 三族化 (ADR-072/076 批 C2b): research collapses to ONE
  text×generator node (no agent, no brief doc — a re-dock without research
  sweeps it); translate/dub stamp the two-station pair (asm video×editor +
  `{fill_key}#doc` table×manual companion, doc_node_id linkage, the new
  edge law transcript→doc / doc→asm / asset→asm — never transcript→asm);
  materialize_source folds into its nearest downstream family (no node of
  its own, its step id rides the host's step_ids, and a run containing one
  makes EVERY clip root eat the assets — 评审修正 P0-C); the sync mirrors
  the doc station's state + renders the cue text
- _fill_key_for_step idempotency fingerprints (graph_fill): producer slot /
  translate·dub transform / bare-kind shapes — a re-run of the same slot
  finds its node, a new slot grows one
- settle_frames_with_edges (the door's frame settle — 布局一开始就定好):
  chains grow right one column per depth (parents-first passes), siblings
  stack inside their shared column, settled history never moves; pinned-id
  adds wire same-batch connects (born with full edge knowledge) and id
  collisions are rejected
- 词表 v3 门层 (ADR-076, C2a→C4): the v3 birth vocabulary (medium five +
  server-internal asset/document; legacy generator/processor/agent dead at
  the schema boundary since C4), v3 port table (text accepts ctx — the
  task-book→writer ctx edge lands), legacy rows still derive into v3 nodes,
  EditPromptOp's transition gate (tool presence or legacy type-value
  fallback — tool-less documents rejected), task_for_graph_node's execution-truth skip
  (P0-B)
- _read_face (C4 读面 legacy 映射): asset→媒介×manual / document→text×manual
  / legacy generator·processor·agent 按 spec.tool 落 (writer 卡 spec.text
  从最新 output 合成) / modifier·materialize 过渡词 / 新行直传
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.schemas import AssetType
from app.models.tables import Asset, GraphEdge, GraphNode, Output, Project, WorkflowRun, WorkflowStep
from app.pipeline import graph_fill
from app.pipeline.graph_fill import (
    _fill_key_for_step,
    _split_station_estimate,
    _stamp_graph_core,
    stamp_transcript_node,
    sync_graph_node_for_step,
)
from app.pipeline.graph_store import WiringRejected, apply_wiring_ops, settle_frames_with_edges

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
    rejected batch must die BEFORE any flush. The C2b tests also seed the
    Asset / Output tables (the stamp's §1+§3 asset reads, the writer-text
    back-write). Stub limitation: a COLUMN select (e.g.
    ``select(Output.workflow_step_id)``) returns the whole row objects — the
    mode② producer walk therefore always reads empty here; tests that need
    existing producers monkeypatch ``graph_fill._existing_clip_producer_nodes``."""

    def __init__(self, nodes=(), edges=(), steps=(), assets=(), outputs=()):
        self.project = Project(id=_PROJECT_ID)
        self.nodes = list(nodes)
        self.edges = list(edges)
        self.steps = list(steps)
        self.assets = list(assets)
        self.outputs = list(outputs)
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
        elif entity is Asset:
            rows = self.assets
        elif entity is Output:
            rows = self.outputs
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


def _node(node_type, *, state="draft", spec=None, layout=None):
    return GraphNode(
        id=uuid4(),
        project_id=_PROJECT_ID,
        type=node_type,
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
        # two ends' ports (a video asset → a video node = the video flow).
        [{"op": "add_node", "type": "video", "spec": {"prompt": "p"}, "after": [asset.id]}],
    )
    assert len(delta.affected) == 1
    newborn = next(n for n in db.added if isinstance(n, GraphNode) and n.id == delta.affected[0])
    assert newborn.state == "draft"  # 图先展示后运行 — zero consumption until a run
    edge = next(e for e in db.added if isinstance(e, GraphEdge))
    assert (edge.from_node, edge.to_node, edge.edge_type) == (asset.id, newborn.id, "video")
    # 定居取景 (统一摆位律): x = depth × pitch (the parent's generation 0 →
    # the child lands one pitch right; pitch = the widest class 400 + 64
    # since the 2026-09-13 分档加宽批); a fresh column's first node RISES
    # above its parent (2026-09-09); existing frames never move
    # (append-only 保序律).
    assert newborn.layout["x"] == 464
    assert newborn.layout["y"] == -88
    assert asset.layout == {"x": 0, "y": 0, "w": 280, "h": 260}
    # TWO flushes (ADR-059 分裂 flush 律): nodes strictly before edges — the
    # UOW never orders bare-FK inserts, so the door stages them.
    assert db.flush_count == 2


@pytest.mark.asyncio
async def test_asset_node_is_born_done():
    db = _StubDb()
    await apply_wiring_ops(
        db, _PROJECT_ID, [{"op": "add_node", "type": "asset", "spec": {"asset_type": "audio"}}]
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
async def test_disconnect_severs_one_typed_flow():
    a, b, c = _node("asset", state="done", spec={"asset_type": "video"}), _node("generator"), _node("generator")
    stale = _edge(b.id, c.id, "video")
    keep = _edge(a.id, c.id, "video")
    db = _StubDb(nodes=[a, b, c], edges=[stale, keep])
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [{"op": "disconnect", "from_node": b.id, "to_node": c.id, "edge_type": "video"}],
    )
    # The stale chain edge is DELETEd (a persisted row), the fan-out edge
    # survives untouched, and a re-read sees exactly the surviving edge.
    assert db.deleted == [stale]
    assert [(e.from_node, e.to_node) for e in db.edges] == [(a.id, c.id)]


@pytest.mark.asyncio
async def test_disconnect_frees_the_cycle_check_for_a_topology_flip():
    # 边对账序 (ADR-062): disconnects lead the stamp's batch, so the connect
    # of a flipped direction (old B→A stale, new A→B wanted) is checked
    # against the POST-retraction set — never rejected as a phantom cycle.
    a, b = _node("generator"), _node("generator")
    db = _StubDb(nodes=[a, b], edges=[_edge(b.id, a.id, "video")])
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [
            {"op": "disconnect", "from_node": b.id, "to_node": a.id, "edge_type": "video"},
            {"op": "connect", "from_node": a.id, "to_node": b.id, "edge_type": "video"},
        ],
    )
    assert [(e.from_node, e.to_node) for e in db.edges] == [(a.id, b.id)]


@pytest.mark.asyncio
async def test_disconnect_missing_edge_rejected():
    a, b = _node("generator"), _node("generator")
    db = _StubDb(nodes=[a, b], edges=[_edge(a.id, b.id, "video")])
    # Wrong type on an existing pair is still a miss (the triple is the key).
    with pytest.raises(WiringRejected, match="disconnect"):
        await apply_wiring_ops(
            db, _PROJECT_ID, [{"op": "disconnect", "from_node": a.id, "to_node": b.id, "edge_type": "text"}]
        )
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_disconnect_a_same_batch_newborn_edge_just_drops_it():
    a = _node("asset", state="done", spec={"asset_type": "video"})
    newborn_id = uuid4()
    db = _StubDb(nodes=[a])
    # A birth-then-sever within one batch: the after-edge never lands, and
    # no DELETE hits the database (the row was never persisted — the door
    # must not db.delete a transient object).
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [
            {"op": "add_node", "id": newborn_id, "type": "video", "spec": {"prompt": "p"}, "after": [a.id]},
            {"op": "disconnect", "from_node": a.id, "to_node": newborn_id, "edge_type": "video"},
        ],
    )
    assert db.edges == []
    assert db.deleted == []


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
async def test_run_op_closes_over_downstream_in_topology_order():
    a = _node("generator", layout={"x": 0, "y": 0, "w": 280, "h": 260})
    b = _node("processor", layout={"x": 376, "y": 0, "w": 280, "h": 260})
    c = _node("generator", layout={"x": 752, "y": 0, "w": 280, "h": 260})
    island = _node("generator", layout={"x": 0, "y": 400, "w": 280, "h": 260})
    edges = [_edge(a.id, b.id, "video"), _edge(b.id, c.id, "video")]
    db = _StubDb(nodes=[a, b, c, island], edges=edges)
    delta = await apply_wiring_ops(db, _PROJECT_ID, [{"op": "run", "nodes": [a.id]}])
    assert delta.run_nodes == [a.id, b.id, c.id]  # the island stays out


@pytest.mark.asyncio
async def test_run_op_orders_by_topology_never_layout_x():
    """The C-2 regression (I-PFA-04, 合同 §7 C-2): frames that contradict
    the topology (a 436-pitch legacy project / a late-born intermediate
    node) must NOT leak into execution — producers precede consumers even
    when layout.x says the opposite. Visual coordinates hold no execution
    authority."""
    producer = _node("generator", layout={"x": 928, "y": 0, "w": 280, "h": 260})
    middle = _node("processor", layout={"x": 464, "y": 0, "w": 280, "h": 260})
    consumer = _node("generator", layout={"x": 0, "y": 0, "w": 280, "h": 260})
    edges = [_edge(producer.id, middle.id, "video"), _edge(middle.id, consumer.id, "video")]
    db = _StubDb(nodes=[producer, middle, consumer], edges=edges)
    delta = await apply_wiring_ops(db, _PROJECT_ID, [{"op": "run", "nodes": [producer.id]}])
    # layout.x says consumer(0) < middle(464) < producer(928); the DAG says
    # producer → middle → consumer. The DAG wins.
    assert delta.run_nodes == [producer.id, middle.id, consumer.id]


@pytest.mark.asyncio
async def test_run_op_ranks_canvas_hidden_modifier_between_producer_and_consumer():
    """The visibility gate is a CANVAS law (I-PFA-01), never an execution
    filter: a morph modifier (reframe_clip — read-face hidden, B4-lite) is
    an executable step and must order between its producer and consumer."""
    producer = _node("generator", layout={"x": 0, "y": 0, "w": 280, "h": 260})
    mod = _node(
        "processor", spec={"tool": "reframe_clip"}, layout={"x": 464, "y": 0, "w": 280, "h": 260}
    )
    consumer = _node("generator", layout={"x": 928, "y": 0, "w": 280, "h": 260})
    edges = [_edge(producer.id, mod.id, "video"), _edge(mod.id, consumer.id, "video")]
    db = _StubDb(nodes=[producer, mod, consumer], edges=edges)
    delta = await apply_wiring_ops(db, _PROJECT_ID, [{"op": "run", "nodes": [producer.id]}])
    assert delta.run_nodes == [producer.id, mod.id, consumer.id]


@pytest.mark.asyncio
async def test_run_op_double_kill_shared_fixture():
    """错帧双杀 (shared malicious fixture, 用户点名): the same corrupted
    frames feed BOTH consumers — execution orders A→B→C here while (mirror
    suite web-side, layout.test.ts) the Canvas projects 0/464/928. If this
    pair ever diverges, one of the two consumers re-derived topology."""
    a = _node("generator", layout={"x": 928, "y": 0, "w": 280, "h": 260})
    b = _node("processor", layout={"x": 100, "y": 0, "w": 280, "h": 260})
    c = _node("generator", layout={"x": 464, "y": 0, "w": 280, "h": 260})
    edges = [_edge(a.id, b.id, "video"), _edge(b.id, c.id, "video")]
    db = _StubDb(nodes=[a, b, c], edges=edges)
    delta = await apply_wiring_ops(db, _PROJECT_ID, [{"op": "run", "nodes": [a.id]}])
    # layout.x says b(100) < c(464) < a(928); the DAG says a → b → c.
    assert delta.run_nodes == [a.id, b.id, c.id]


@pytest.mark.asyncio
async def test_run_op_same_rank_tiebreak_is_deterministic_never_layout():
    """Same-rank nodes are parallel by definition — their relative order is
    semantically free but must be deterministic (id str, never layout)."""
    x = _node("generator", layout={"x": 0, "y": 500, "w": 280, "h": 260})
    y = _node("processor", layout={"x": 0, "y": 0, "w": 280, "h": 260})
    src = _node("asset", state="done", spec={"asset_type": "video"})
    edges = [_edge(src.id, x.id, "video"), _edge(src.id, y.id, "video")]
    db = _StubDb(nodes=[src, x, y], edges=edges)
    delta = await apply_wiring_ops(db, _PROJECT_ID, [{"op": "run", "nodes": [src.id]}])
    same_rank = sorted([str(x.id), str(y.id)])
    assert [str(n) for n in delta.run_nodes] == [str(src.id)] + same_rank  # rank 0 first, then id order


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
    assert doc.type == "document"
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


# ---- research 单节点塌缩 (批 C2b — agent 族与 brief 文档退役) ---------------


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
async def test_research_collapses_to_one_text_node_and_sweeps_without_it():
    """词表 v3 塌缩律: the bounded loop IS one node (text×generator, the
    query as its program) — no agent node, no research_brief document, the
    writer wires from the research node itself, and a re-docked chain
    without research orphan-sweeps it."""
    project = Project(id=_PROJECT_ID)
    db = _StubDb()
    await _stamp_graph_core(
        db, project, _research_chain(), run=None, ui_language="en", draft=True, book_text="b"
    )
    research_node = next(n for n in db.nodes if (n.spec or {}).get("tool") == "research")
    assert research_node.type == "text"
    assert research_node.spec["prototype"] == "generator"
    assert research_node.spec["fill_key"] == "research"
    assert research_node.spec["prompt"] == "grid storage"  # query 即程序
    assert research_node.state == "draft"  # the preview's promise
    # 无 agent、无 brief 文档 — the agent family and the brief role retired.
    assert not [n for n in db.nodes if n.type == "agent"]
    assert not [n for n in db.nodes if (n.spec or {}).get("role") == "research_brief"]
    # the writer wires from the RESEARCH node (the execution truth, text flow)
    writer = next(n for n in db.nodes if (n.spec or {}).get("tool") == "write_post")
    assert writer.type == "text"
    assert any(
        str(e.from_node) == str(research_node.id)
        and str(e.to_node) == str(writer.id)
        and e.edge_type == "text"
        for e in db.edges
    )
    # a re-docked chain WITHOUT research orphan-sweeps the research node
    db2 = _StubDb(nodes=list(db.nodes), edges=list(db.edges))
    post_only = [_research_chain()[1]]
    await _stamp_graph_core(
        db2, project, post_only, run=None, ui_language="en", draft=True, book_text="b"
    )
    assert not [n for n in db2.nodes if (n.spec or {}).get("tool") == "research"]


@pytest.mark.asyncio
async def test_research_node_run_fill_and_sync_renders_the_brief():
    """Run fill births the single research node (draft — the newborn law;
    sync queues it as the steps execute); the sync renders the loop's
    closing brief straight onto its own spec.text (brief 文档镜像随塌缩退役)."""
    project = Project(id=_PROJECT_ID)
    run = WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, context={})
    steps = _research_chain()
    db = _StubDb(steps=steps)
    await _stamp_graph_core(
        db, project, steps, run=run, ui_language="en", draft=False, book_text=None
    )
    research_node = next(n for n in db.nodes if (n.spec or {}).get("tool") == "research")
    assert research_node.state == "draft"  # the newborn law — sync queues it
    # the loop closes: the brief lands on the research step's spec, the sync
    # mirrors the node's terminal + renders the text onto the node itself
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
    assert research_node.state == "done"
    assert "Storage is the bottleneck." in research_node.spec["text"]
    assert "• Fact one" in research_node.spec["text"]


# ---- 两站拆分 stamp (批 C2b, ADR-072) -----------------------------------------


def _translate_chain(with_materialize=False):
    steps = []
    if with_materialize:
        materialize = WorkflowStep(
            id=uuid4(), kind="materialize_source", seq=1, spec={}, estimate=None
        )
        materialize.inputs = []
        steps.append(materialize)
    translate = WorkflowStep(
        id=uuid4(),
        kind="translate_clip",
        seq=2 if with_materialize else 1,
        spec={"target_language": "fr"},
        estimate=None,
    )
    translate.inputs = [str(steps[0].id)] if with_materialize else []
    steps.append(translate)
    return steps


@pytest.mark.asyncio
async def test_two_station_stamp_asm_and_doc_companion():
    """ADR-072 两站拆分: a translate run stamps the asm station (video×editor,
    the executor) plus its `{fill_key}#doc` companion (table×manual — the
    persistent editable cue artifact's home), linked by spec.doc_node_id.
    The companion carries NO tool / prompt / step_ids / output_ids — it is
    not an execution unit. The new edge law: 文流经 doc 站中转 (transcript→
    doc→asm), the media flow feeds the asm direct (asset→asm), and the old
    transcript→asm direct edge is never stamped."""
    project = Project(id=_PROJECT_ID)
    run = WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, context={})
    steps = _translate_chain()
    asset = _asset(transcript="hello world")
    db = _StubDb(steps=steps, assets=[asset])
    await _stamp_graph_core(
        db, project, steps, run=run, ui_language="en", draft=False, book_text=None
    )
    asm = next(n for n in db.nodes if n.type == "video")
    doc = next(n for n in db.nodes if n.type == "table")
    transcript_doc = next(
        n for n in db.nodes if n.type == "document" and (n.spec or {}).get("role") == "transcript"
    )
    asset_node = next(n for n in db.nodes if n.type == "asset")
    key = "translate_clip#fr#False#False"
    # asm 站: the executor's identity (词表 v3 媒介×原型 + tool + 双站链接)
    assert asm.spec["fill_key"] == key
    assert asm.spec["tool"] == "translate_clip"
    assert asm.spec["prototype"] == "editor"
    assert asm.spec["doc_node_id"] == str(doc.id)
    assert asm.spec["step_ids"] == [str(steps[-1].id)]
    # 出生律 (pre-C2b 照旧): a newborn family node leaves the stamp at DRAFT
    # even in run mode — sync re-aggregates it to queued/running/done as
    # the steps execute (only REUSED nodes re-queue at stamp time).
    assert asm.state == "draft"
    # doc 站: table×manual, role = the doc_station declaration — no tool /
    # prompt / step_ids / output_ids (the cue artifact is its whole content)
    assert doc.spec["fill_key"] == f"{key}#doc"
    assert doc.spec["role"] == "translation"
    assert doc.spec["prototype"] == "manual"
    assert doc.spec["frame_class"] == "text"  # 340×560 reservation
    assert "tool" not in doc.spec
    assert "prompt" not in doc.spec
    assert "step_ids" not in doc.spec
    assert "output_ids" not in doc.spec
    assert doc.state == "queued"  # §6b — run 模式与 asm 同排
    # 边派生新规: exactly the four edges, transcript→asm 永不存在
    triples = {(str(e.from_node), str(e.to_node), e.edge_type) for e in db.edges}
    assert triples == {
        (str(asset_node.id), str(transcript_doc.id), "text"),
        (str(transcript_doc.id), str(doc.id), "text"),
        (str(doc.id), str(asm.id), "text"),
        (str(asset_node.id), str(asm.id), "video"),
    }


@pytest.mark.asyncio
async def test_materialize_folds_into_the_translate_family(monkeypatch):
    """materialize 折叠 (ADR-072 ⑦): no node of its own — its step id rides
    the host family's step_ids, the host's tool identity stays the
    consumer's (translate), and 评审修正 P0-C: a run CONTAINING a
    materialize makes every clip root eat the raw assets even when the
    project has existing clips (otherwise the whole-source chain mis-wires
    to the old producer — 画布撒谎)."""
    fake_producer = uuid4()

    async def _existing_producers(db, project_id):
        return [fake_producer]

    monkeypatch.setattr(graph_fill, "_existing_clip_producer_nodes", _existing_producers)
    project = Project(id=_PROJECT_ID)
    run = WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, context={})
    materialize, translate = _translate_chain(with_materialize=True)
    db = _StubDb(steps=[materialize, translate], assets=[_asset()])
    await _stamp_graph_core(
        db, project, [materialize, translate], run=run, ui_language="en", draft=False, book_text=None
    )
    video_nodes = [n for n in db.nodes if n.type == "video"]
    assert len(video_nodes) == 1  # the folded materialize grows no twin
    asm = video_nodes[0]
    assert asm.spec["fill_key"] == "translate_clip#fr#False#False"
    assert asm.spec["tool"] == "translate_clip"  # never "materialize_source"
    assert asm.spec["prompt"]  # P0-A: the translate head keeps its prompt
    assert not [n for n in db.nodes if (n.spec or {}).get("fill_key") == "materialize_source"]
    # the folded step's id rides the host family's step_ids (seq order)…
    assert asm.spec["step_ids"] == [str(materialize.id), str(translate.id)]
    # …and §6 back-points BOTH steps to the host node
    assert materialize.spec["graph_node_id"] == str(asm.id)
    assert translate.spec["graph_node_id"] == str(asm.id)
    # P0-C: the host root eats the raw assets — never the old producer
    asset_node = next(n for n in db.nodes if n.type == "asset")
    assert any(
        str(e.from_node) == str(asset_node.id) and str(e.to_node) == str(asm.id)
        and e.edge_type == "video"
        for e in db.edges
    )
    assert not [e for e in db.edges if str(e.from_node) == str(fake_producer)]


# ---- 两站估价归位 (批 A4/C3, 评审修正 P0-D) ----------------------------------


def test_station_estimate_split_shapes():
    """token 段归 doc / units 段归 asm / None 直传: translate 的纯 token
    报价 → doc 全量 + asm None (「估价随运行」); dub 的混合体 → token 段
    + units 段 (voice_clones 是配音产物的声纹单位)."""
    token_only = {"prompt_tokens": [100, 200], "completion_tokens": [50, 80], "units": {}}
    doc, asm = _split_station_estimate(token_only)
    assert doc == token_only
    assert asm is None
    hybrid = {
        "prompt_tokens": [10, 20],
        "completion_tokens": [30, 40],
        "units": {"tts_chars": 500.0, "voice_clones": 1.0},
    }
    doc, asm = _split_station_estimate(hybrid)
    assert doc == {"prompt_tokens": [10, 20], "completion_tokens": [30, 40], "units": {}}
    assert asm == {
        "prompt_tokens": [0, 0],
        "completion_tokens": [0, 0],
        "units": {"tts_chars": 500.0, "voice_clones": 1.0},
    }
    assert _split_station_estimate(None) == (None, None)


def test_station_split_folds_back_to_the_step_level_fold():
    """hold 不变性 (铁律): step.estimate 零改动 — 两站拆分后的两段 fold 回
    原整份 (draft 确认拍总额不破, §3.5.5-6; voice_clones min-1 钳制同律)."""
    from app.pipeline.graph import fold_estimates

    translate_est = {"prompt_tokens": [100, 200], "completion_tokens": [50, 80], "units": {}}
    dub_est = {
        "prompt_tokens": [10, 20],
        "completion_tokens": [30, 40],
        "units": {"tts_chars": 500.0, "voice_clones": 1.0},
    }
    whole = fold_estimates([translate_est, dub_est])
    parts = []
    for est in (translate_est, dub_est):
        parts.extend(_split_station_estimate(est))
    assert fold_estimates(parts) == whole


@pytest.mark.asyncio
async def test_two_station_estimate_seats_and_requote_on_reuse():
    """两站各归其座: stamp 时 doc 站揣 token 段 (capture-0 账面 — units 恒
    {}), asm 站揣 units 段或 None; reuse 重盖章时 doc 的 estimate 同步重报
    (与 asm 的 estimate 刷新同律)."""
    project = Project(id=_PROJECT_ID)
    run = WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, context={})
    # translate: 纯 token 报价 → doc 全量, asm None.
    translate = WorkflowStep(
        id=uuid4(),
        kind="translate_clip",
        seq=1,
        spec={"target_language": "fr"},
        estimate={"prompt_tokens": [100, 200], "completion_tokens": [50, 80], "units": {}},
    )
    translate.inputs = []
    db = _StubDb(steps=[translate], assets=[_asset()])
    await _stamp_graph_core(
        db, project, [translate], run=run, ui_language="en", draft=False, book_text=None
    )
    asm = next(n for n in db.nodes if n.type == "video")
    doc = next(n for n in db.nodes if n.type == "table")
    assert doc.spec["estimate"] == translate.estimate
    assert doc.spec["estimate"]["units"] == {}  # capture-0 账面结构
    assert asm.spec["estimate"] is None  # 「估价随运行」(ADR-063 诚实面)
    # dub: 混合体 → doc = token 段, asm = units 段 (voice_clones 归 asm).
    dub = WorkflowStep(
        id=uuid4(),
        kind="dub_clip",
        seq=2,
        spec={"target_language": "de"},
        estimate={
            "prompt_tokens": [10, 20],
            "completion_tokens": [30, 40],
            "units": {"tts_chars": 500.0, "voice_clones": 1.0},
        },
    )
    dub.inputs = [str(translate.id)]
    db2 = _StubDb(nodes=list(db.nodes), edges=list(db.edges), steps=[dub], assets=[])
    await _stamp_graph_core(
        db2, project, [dub], run=run, ui_language="en", draft=False, book_text=None
    )
    dub_asm = next(
        n for n in db2.nodes
        if n.type == "video" and (n.spec or {}).get("tool") == "dub_clip"
    )
    dub_doc = next(
        n for n in db2.nodes
        if n.type == "table" and (n.spec or {}).get("role") == "dub_script"
    )
    assert dub_doc.spec["estimate"] == {
        "prompt_tokens": [10, 20], "completion_tokens": [30, 40], "units": {}
    }
    assert dub_asm.spec["estimate"] == {
        "prompt_tokens": [0, 0], "completion_tokens": [0, 0],
        "units": {"tts_chars": 500.0, "voice_clones": 1.0},
    }
    # reuse 重报: 同 fill_key 再盖章 — doc 的 estimate 随新编译重报 (token
    # 段刷新; 账面结构恒 capture-0), asm 复用分支同样揣拆分后的 units 段.
    dub_v2 = WorkflowStep(
        id=uuid4(),
        kind="dub_clip",
        seq=2,
        spec={"target_language": "de"},
        estimate={
            "prompt_tokens": [12, 22],
            "completion_tokens": [32, 42],
            "units": {"tts_chars": 600.0, "voice_clones": 1.0},
        },
    )
    dub_v2.inputs = []
    db3 = _StubDb(
        nodes=list(db2.nodes), edges=list(db2.edges), steps=[dub_v2], assets=[]
    )
    await _stamp_graph_core(
        db3, project, [dub_v2], run=run, ui_language="en", draft=False, book_text=None
    )
    assert dub_doc.spec["estimate"] == {
        "prompt_tokens": [12, 22], "completion_tokens": [32, 42], "units": {}
    }
    assert dub_asm.spec["estimate"] == {
        "prompt_tokens": [0, 0], "completion_tokens": [0, 0],
        "units": {"tts_chars": 600.0, "voice_clones": 1.0},
    }


# ---- sync back-write: v3 文本回写 + 两站双站镜像 (批 C2b) ---------------------


@pytest.mark.asyncio
async def test_sync_back_writes_writer_text_from_the_latest_output():
    """writer 升 text 型: the landed product's content back-writes the node's
    spec.text — the 全文卡 reads the node's own words (the version lineage
    still accumulates alongside)."""
    out_id = uuid4()
    step = WorkflowStep(
        id=uuid4(), kind="write_post", status="done", spec={}, output_refs=[out_id]
    )
    node = _node("text", state="running", spec={"tool": "write_post", "step_ids": [str(step.id)]})
    step.spec["graph_node_id"] = str(node.id)
    out = Output(
        id=out_id,
        project_id=_PROJECT_ID,
        workflow_step_id=step.id,
        type="post",
        payload={"content": "Bonjour le monde"},
    )
    db = _StubDb(nodes=[node], steps=[step], outputs=[out])
    await sync_graph_node_for_step(db, step)
    assert node.state == "done"
    assert node.spec["text"] == "Bonjour le monde"
    assert node.spec["output_ids"] == [str(out_id)]


@pytest.mark.asyncio
async def test_sync_mirrors_the_doc_station_and_renders_the_cue_text():
    """两站双站镜像 (ADR-072): the doc station tracks its asm's state in
    lockstep and renders the translation artifact's cue rows as `start–end
    text` lines. 迁移期读回退: a legacy row carrying the artifact on the ASM
    still renders (迁移边界零重买翻译)."""
    step = WorkflowStep(id=uuid4(), kind="translate_clip", status="done", spec={}, output_refs=[])
    artifact = {
        "clips": {
            "out1": {
                "source_hash": "h",
                "rows": [
                    {"start": 0, "end": 2, "text": "Bonjour"},
                    {"start": 65, "end": 67.5, "text": "le monde"},
                ],
            }
        }
    }
    doc = _node(
        "table",
        state="queued",
        spec={
            "fill_key": "translate_clip#fr#False#False#doc",
            "role": "translation",
            "translation": artifact,
        },
    )
    asm = _node(
        "video",
        state="running",
        spec={"tool": "translate_clip", "doc_node_id": str(doc.id), "step_ids": [str(step.id)]},
    )
    step.spec["graph_node_id"] = str(asm.id)
    db = _StubDb(nodes=[asm, doc], steps=[step])
    await sync_graph_node_for_step(db, step)
    assert asm.state == "done"
    assert doc.state == "done"  # lockstep with its asm
    assert doc.spec["text"] == "0:00–0:02 Bonjour\n1:05–1:07 le monde"
    # 迁移期读回退: the artifact living on the ASM (a pre-v3 row) renders the
    # same face — the doc's own (empty) artifact never shadows it.
    doc2 = _node(
        "table",
        state="queued",
        spec={"fill_key": "translate_clip#de#False#False#doc", "role": "translation"},
    )
    asm2 = _node(
        "video",
        state="running",
        spec={
            "tool": "translate_clip",
            "doc_node_id": str(doc2.id),
            "step_ids": [str(step.id)],
            "translation": artifact,
        },
    )
    db2 = _StubDb(nodes=[asm2, doc2], steps=[step])
    step.spec = {**step.spec, "graph_node_id": str(asm2.id)}
    await sync_graph_node_for_step(db2, step)
    assert doc2.spec["text"] == "0:00–0:02 Bonjour\n1:05–1:07 le monde"


# ---- task book face (全文卡律 判词④: prose birth + 双面 back-write 律) ------


def _post_chain():
    plan = WorkflowStep(
        id=uuid4(),
        kind="plan",
        seq=1,
        spec={"task_book": {"slots": [{"type": "post"}], "target_language": "en"}},
        estimate=None,
    )
    post = WorkflowStep(
        id=uuid4(),
        kind="write_post",
        seq=2,
        spec={"slot": {"type": "post"}, "slot_index": 0},
        estimate=None,
    )
    post.inputs = [str(plan.id)]
    plan.inputs = []
    return [plan, post]


def _book_node(db):
    return next(
        n for n in db.nodes if n.type == "document" and (n.spec or {}).get("role") == "task_book"
    )


@pytest.mark.asyncio
async def test_draft_book_born_with_full_prose_and_confirm_sized_frame():
    project = Project(id=_PROJECT_ID)
    db = _StubDb()
    prose = "Four caption versions off your full demo video — EN, ZH, FR, ES."
    await _stamp_graph_core(
        db, project, _post_chain(), run=None, ui_language="en", draft=True, book_text=prose
    )
    book = _book_node(db)
    assert book.spec["text"] == prose  # the LLM's own plan restatement, never a condensation
    # 全文卡律 frame (server mirror of layout.ts documentTextHeight): 66
    # Latin chars → ceil(66/67) = 1 line → 26 + 16 + 18 + 16 + 88 (the
    # dock-time confirm allowance) = 164 → the DOCUMENT_MIN_H floor (280,
    # 2026-09-13 增大批) binds; the lane is the widened 340 (was 260).
    assert book.layout["h"] == 280
    assert book.layout["w"] == 340


@pytest.mark.asyncio
async def test_draft_restamp_refreshes_the_prose_but_run_fill_never_rewrites_it():
    project = Project(id=_PROJECT_ID)
    run = WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, context={})
    steps = _post_chain()
    db = _StubDb(steps=steps)
    await _stamp_graph_core(
        db, project, steps, run=None, ui_language="en", draft=True, book_text="old prose"
    )
    # A revised chain re-docks: the dock owns the DRAFT face — refresh.
    await _stamp_graph_core(
        db, project, steps, run=None, ui_language="en", draft=True, book_text="new prose"
    )
    assert _book_node(db).spec["text"] == "new prose"
    # Start's run fill (the deterministic composition is available here —
    # "1 post · English") must NOT overwrite the docked promise.
    await _stamp_graph_core(
        db, project, steps, run=run, ui_language="en", draft=False, book_text=None
    )
    assert _book_node(db).spec["text"] == "new prose"


@pytest.mark.asyncio
async def test_run_born_book_fills_an_empty_face_with_composition_or_run_name():
    project = Project(id=_PROJECT_ID)
    run = WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, context={})
    db = _StubDb(steps=_post_chain())
    await _stamp_graph_core(
        db, project, _post_chain(), run=run, ui_language="en", draft=False, book_text=None
    )
    assert _book_node(db).spec["text"] == "1 post · English"
    # A transform chain carries no output slots — the deterministic
    # composition is blind (None); the run's LLM-given name is the face.
    plan, post = _post_chain()
    plan.spec = {"task_book": {"slots": [], "target_language": "en"}}
    named_run = WorkflowRun(
        id=uuid4(), project_id=_PROJECT_ID, context={"name": "Multilingual caption versions"}
    )
    db2 = _StubDb(steps=[plan, post])
    await _stamp_graph_core(
        db2, project, [plan, post], run=named_run, ui_language="en", draft=False, book_text=None
    )
    assert _book_node(db2).spec["text"] == "Multilingual caption versions"


def test_document_frame_full_text_math_cjk_latin_empty():
    from app.pipeline.graph_store import _document_frame

    # 2026-09-13 增大批: the 340-wide lane, 43 CJK / 67 Latin chars per line
    # (the 308px column), floor 280 / cap 560 (one law with layout.ts).
    # CJK 100 chars → ceil(100/43) = 3 lines → 26 + 16 + 54 + 16 = 112 →
    # the floor binds.
    assert _document_frame({"text": "字" * 100}) == (340, 280)
    # Latin 200 chars → ceil(200/67) = 3 lines — the same floor.
    assert _document_frame({"text": "a" * 200}) == (340, 280)
    # Above the floor the math speaks: CJK 1000 → ceil(1000/43) = 24 lines
    # → 26 + 16 + 432 + 16 = 490; Latin 2000 → ceil(2000/67) = 30 lines →
    # 598 → the 560 cap binds.
    assert _document_frame({"text": "字" * 1000}) == (340, 490)
    assert _document_frame({"text": "a" * 2000}) == (340, 560)
    # Empty text → the floor again; the task_book role adds the confirm
    # allowance (+88) — visible once the text's own need clears the floor:
    # Latin 600 → ceil(600/67) = 9 lines → 26 + 16 + 162 + 16 = 220 + 88.
    assert _document_frame({"text": ""}) == (340, 280)
    assert _document_frame({"text": "a" * 600, "role": "task_book"}) == (340, 308)


# ---- settle_frames_with_edges (the door's frame settle, 2026-09-08) ---------


@pytest.mark.asyncio
async def test_add_node_pinned_id_wires_same_batch_born_with_edge_knowledge():
    """The stamper's seat: a pinned id lets the SAME batch's connect op
    reference the newborn — the door's settle sees the final edge set and
    the chain is born left→right, never stacked at x=0 and repaired
    (2026-09-08 用户拍板: 布局一开始就定好)."""
    book_id = uuid4()
    writer_id = uuid4()
    db = _StubDb()
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [
            {"op": "add_node", "id": book_id, "type": "document",
             "spec": {"role": "task_book", "text": "1 LinkedIn post · English"}},
            {"op": "add_node", "id": writer_id, "type": "text",
             "spec": {"fill_key": "write_post#post#0", "frame_class": "text"}},
            {"op": "connect", "from_node": book_id, "to_node": writer_id, "edge_type": "ctx"},
        ],
    )
    book = next(n for n in db.nodes if n.id == book_id)
    writer = next(n for n in db.nodes if n.id == writer_id)
    assert (book.layout["x"], book.layout["y"]) == (0, 0)
    assert writer.layout["x"] == 464
    # A fresh column's first node rises above its parent (2026-09-09).
    assert writer.layout["y"] == -88


@pytest.mark.asyncio
async def test_add_node_pinned_id_collision_rejected():
    existing = _node("generator")
    db = _StubDb(nodes=[existing])
    with pytest.raises(WiringRejected, match="already exists"):
        await apply_wiring_ops(
            db,
            _PROJECT_ID,
            [{"op": "add_node", "id": existing.id, "type": "text", "spec": {}}],
        )


def test_settle_frames_chain_grows_right_not_down():
    """The fill's two-batch case: nodes born as x=0 islands (stacked), edges
    landed after — the re-settle walks parents-first and the chain reads
    left → right, one column per depth."""
    book = _node("document", spec={"role": "task_book"},
                 layout={"x": 0, "y": 0, "w": 260, "h": 200})
    writer = _node("generator", spec={"fill_key": "write_post#post#0", "frame_class": "text"},
                   layout={"x": 0, "y": 224, "w": 340, "h": 440})
    verify_free_second = _node("generator", spec={"fill_key": "write_post#post#1", "frame_class": "text"},
                               layout={"x": 0, "y": 688, "w": 340, "h": 440})
    edges = [
        _edge(book.id, writer.id, "ctx"),
        _edge(book.id, verify_free_second.id, "ctx"),
    ]
    settle_frames_with_edges([book, writer, verify_free_second], [], edges)
    # The book has no parents — it stays at the origin island.
    assert (book.layout["x"], book.layout["y"]) == (0, 0)
    # Children settle one depth-pitch right (464 since the 2026-09-13 分档
    # 加宽批: the widest class 400 + GAP_MAIN 64): the first RISES above
    # the book (2026-09-09), the second stacks INSIDE the shared column
    # (same depth) under its sibling (cross gap).
    assert writer.layout["x"] == 464
    assert writer.layout["y"] == -88
    assert verify_free_second.layout["x"] == 464
    # The sibling stack's gap derives from the frame-class RESERVATION
    # (text = 560 since 2026-09-10 卡高内容驱动, was 440), never from the
    # node's provisional layout h — the fixture's 440 is deliberately stale
    # to prove the reservation drives.
    assert verify_free_second.layout["y"] == -88 + 560 + 16


def test_settle_frames_parent_chain_one_link_per_pass():
    """A → B → C: C must wait for B's settled frame (parents-first passes),
    landing one column further right — never computed off B's provisional
    island frame."""
    a = _node("document", layout={"x": 0, "y": 0, "w": 260, "h": 200})
    b = _node("generator", spec={"frame_class": "text"}, layout={"x": 0, "y": 224, "w": 340, "h": 440})
    c = _node("processor", spec={"frame_class": "clip"}, layout={"x": 0, "y": 688, "w": 280, "h": 660})
    edges = [_edge(a.id, b.id, "ctx"), _edge(b.id, c.id, "text")]
    settle_frames_with_edges([a, b, c], [], edges)
    assert b.layout["x"] == 464
    assert c.layout["x"] == 2 * 464
    # The rise compounds link by link: b above a, c above b.
    assert c.layout["y"] == -176


def test_settle_frames_never_moves_settled_history():
    """Settled nodes are the re-settle's ground truth: a newborn parented by
    one settles right of ITS frame; the settled frame itself is untouched."""
    asset = _node("asset", state="done", spec={"asset_type": "video"},
                  layout={"x": 0, "y": 0, "w": 280, "h": 260})
    book = _node("document", layout={"x": 0, "y": 284, "w": 260, "h": 200})
    writer = _node("generator", spec={"frame_class": "text"},
                   layout={"x": 0, "y": 508, "w": 340, "h": 440})
    edges = [_edge(asset.id, book.id, "text"), _edge(book.id, writer.id, "ctx")]
    settle_frames_with_edges([book, writer], [asset], edges)
    assert asset.layout == {"x": 0, "y": 0, "w": 280, "h": 260}
    # The book rises above its settled parent; the settled frame is untouched.
    assert (book.layout["x"], book.layout["y"]) == (464, -88)
    assert writer.layout["x"] == 2 * 464


# ---- 词表 v3 门层 (ADR-076, C2a): 媒介五值 + legacy 容忍 ---------------------


@pytest.mark.asyncio
async def test_add_node_accepts_the_v3_medium_vocabulary():
    """The door's v3 birth vocabulary: the five medium values land as
    first-class nodes, and a legacy video asset's birth edges derive into
    them by the same port law (concrete-first)."""
    asset = _node("asset", state="done", spec={"asset_type": "video"})
    db = _StubDb(nodes=[asset])
    delta = await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [
            {"op": "add_node", "type": "video",
             "spec": {"tool": "translate_clip"}, "after": [asset.id]},
            {"op": "add_node", "type": "text",
             "spec": {"tool": "write_post"}, "after": [asset.id]},
        ],
    )
    assert len(delta.affected) == 2
    by_type = {n.type: n for n in db.added if isinstance(n, GraphNode)}
    edge_types = {
        str(e.to_node): e.edge_type for e in db.added if isinstance(e, GraphEdge)
    }
    # asset(video) offers {video,audio,text} — the concrete video flow wins
    # into the video node; the text node takes the concrete text flow.
    assert edge_types[str(by_type["video"].id)] == "video"
    assert edge_types[str(by_type["text"].id)] == "text"


@pytest.mark.asyncio
async def test_add_node_rejects_a_kind_outside_the_v3_vocabulary():
    """C4 门收窄: the birth vocabulary is the five media values + the two
    server-internal words (asset / document) — the legacy generator /
    processor / agent trio is dead at the schema boundary (their tolerance
    entries stay only in the port table for old-row edge derivation)."""
    for dead in ("hologram", "generator", "processor", "agent"):
        db = _StubDb()
        with pytest.raises(ValidationError):
            await apply_wiring_ops(db, _PROJECT_ID, [{"op": "add_node", "type": dead}])
        assert db.flush_count == 0


@pytest.mark.asyncio
async def test_legacy_rows_still_derive_into_v3_nodes():
    """legacy 读容忍: a legacy generator's out-flows derive into the new
    medium nodes by the unchanged port law (旧行连线仍要过门)."""
    gen = _node("generator")
    video = _node("video", spec={"tool": "translate_clip"})
    text = _node("text", spec={"tool": "write_post"})
    db = _StubDb(nodes=[gen, video, text])
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [
            {"op": "connect", "from_node": gen.id, "to_node": video.id},
            {"op": "connect", "from_node": gen.id, "to_node": text.id},
        ],
    )
    edge_types = {
        str(e.to_node): e.edge_type for e in db.added if isinstance(e, GraphEdge)
    }
    assert edge_types[str(video.id)] == "video"  # concrete-first
    assert edge_types[str(text.id)] == "text"


@pytest.mark.asyncio
async def test_task_book_ctx_edge_lands_on_a_v3_text_writer():
    """本批最高危交互点: 任务书→writer 的 ctx 边打到新 text 型 writer 节点
    —— text 的 accepts 缺 ctx 会令整 stamp 批 422. document offers
    {text,ctx}: the explicit ctx edge lands; the unnamed derivation still
    prefers the concrete text flow."""
    book = _node("document", spec={"role": "task_book"})
    writer = _node("text", spec={"tool": "write_post"})
    db = _StubDb(nodes=[book, writer])
    await apply_wiring_ops(
        db,
        _PROJECT_ID,
        [{"op": "connect", "from_node": book.id, "to_node": writer.id, "edge_type": "ctx"}],
    )
    assert db.added[-1].edge_type == "ctx"
    writer2 = _node("text", spec={"tool": "write_article"})
    db.nodes.append(writer2)
    await apply_wiring_ops(
        db, _PROJECT_ID, [{"op": "connect", "from_node": book.id, "to_node": writer2.id}]
    )
    assert db.added[-1].edge_type == "text"


@pytest.mark.asyncio
async def test_edit_prompt_transition_gate_tool_presence():
    """ADR-076 过渡闸门 (批 B4 set_param 落地前 editor 修订不断粮): the
    executing body's presence (spec.tool) marks an editable program — the
    legacy two-kind fallback covers pre-v3 unstamped rows."""
    # 旧行带 tool 可编辑 (a tool-bearing processor — the widened gate).
    proc = _node("processor", state="done", spec={"tool": "translate_clip", "prompt": "old"})
    await apply_wiring_ops(
        _StubDb(nodes=[proc]), _PROJECT_ID,
        [{"op": "edit_prompt", "node": proc.id, "prompt": "new"}],
    )
    assert proc.spec["prompt"] == "new"
    assert proc.state == "stale"
    # 新 text 型 writer 可编辑.
    writer = _node("text", state="done", spec={"tool": "write_post", "prompt": "old"})
    await apply_wiring_ops(
        _StubDb(nodes=[writer]), _PROJECT_ID,
        [{"op": "edit_prompt", "node": writer.id, "prompt": "new"}],
    )
    assert writer.spec["prompt"] == "new"
    assert writer.state == "stale"
    # 无 tool 的文档恒拒 — v3 与 legacy 同律 (transcript / task book /
    # brief 的文字层直改是另一个 op 的事, 不归 edit_prompt).
    v3_doc = _node("text", spec={"role": "transcript"})
    with pytest.raises(WiringRejected, match="no prompt"):
        await apply_wiring_ops(
            _StubDb(nodes=[v3_doc]), _PROJECT_ID,
            [{"op": "edit_prompt", "node": v3_doc.id, "prompt": "x"}],
        )
    legacy_doc = _node("document", spec={"role": "task_book"})
    with pytest.raises(WiringRejected, match="no prompt"):
        await apply_wiring_ops(
            _StubDb(nodes=[legacy_doc]), _PROJECT_ID,
            [{"op": "edit_prompt", "node": legacy_doc.id, "prompt": "x"}],
        )


def test_task_for_graph_node_skips_by_the_execution_truth():
    """词表 v3 评审修正 P0-B: skip = asset or no spec.tool, never the card's
    kind — a writer upgraded to the text type keeps its run bridge (the
    graph/revise + chat revision run aimed at it never 422s)."""
    from app.pipeline.graph_revise import task_for_graph_node

    writer = _node("text", spec={"tool": "write_post", "params": {"slot": {"type": "post"}}})
    task = task_for_graph_node(writer)
    assert task is not None
    assert task.tool == "write_post"
    # A legacy row's bridge is exactly as before.
    legacy = _node("generator", spec={"tool": "write_post", "params": {"slot": {"type": "post"}}})
    assert task_for_graph_node(legacy) is not None
    # Tool-less nodes drop out whatever their kind — asset (an input),
    # legacy documents, and the v3 manual text doc all the same.
    assert task_for_graph_node(_node("asset", state="done")) is None
    assert task_for_graph_node(_node("document", spec={"role": "task_book"})) is None
    assert task_for_graph_node(_node("text", spec={"role": "transcript"})) is None



# ---- _read_face (C4 读面 legacy 映射) -----------------------------------------


def test_read_face_passes_v3_rows_through():
    from app.pipeline.routes.projects import _read_face

    spec = {"fill_key": "translate_clip#fr#False#False", "tool": "translate_clip",
            "prototype": "editor", "doc_node_id": "x"}
    assert _read_face("video", spec, []) == ("video", spec)
    table_spec = {"fill_key": "k#doc", "role": "translation", "prototype": "manual"}
    assert _read_face("table", table_spec, []) == ("table", table_spec)


def test_read_face_maps_assets_by_asset_type():
    from app.pipeline.routes.projects import _read_face

    kind, spec = _read_face("asset", {"asset_id": "a", "asset_type": "video"}, [])
    assert (kind, spec["prototype"]) == ("video", "manual")
    assert spec["asset_id"] == "a"  # the dossier join key rides along
    assert _read_face("asset", {"asset_type": "voice_sample"}, [])[0] == "audio"
    assert _read_face("asset", {"asset_type": "slides"}, [])[0] == "video"
    assert _read_face("asset", {"asset_type": "image"}, [])[0] == "image"
    assert _read_face("asset", {"asset_type": "transcript"}, [])[0] == "text"
    assert _read_face("asset", {}, [])[0] == "text"  # unknown → safest reading


def test_read_face_maps_documents_to_text_manual():
    from app.pipeline.routes.projects import _read_face

    kind, spec = _read_face("document", {"role": "transcript", "text": "t"}, [])
    assert (kind, spec["prototype"], spec["role"]) == ("text", "manual", "transcript")
    assert _read_face("document", {"role": "task_book"}, [])[0] == "text"
    assert _read_face("document", {}, [])[0] == "text"  # role-less → same


def test_read_face_maps_legacy_executors_by_tool_not_kind():
    from app.pipeline.routes.projects import _read_face

    # 键用 spec.tool 而非裸 kind — a reused legacy row's kind is stale.
    assert _read_face("generator", {"tool": "write_post"}, [])[0] == "text"
    assert _read_face("processor", {"tool": "write_article"}, [])[1]["prototype"] == "generator"
    assert _read_face("agent", {"tool": "research"}, [])[0] == "text"
    assert _read_face("generator", {"tool": "write_quotes"}, [])[0] == "image"
    assert _read_face("generator", {"tool": "write_carousel"}, [])[1]["prototype"] == "generator"
    assert _read_face("processor", {"tool": "select_clips"}, [])[0] == "video"
    assert _read_face("generator", {"tool": "translate_clip"}, [])[1]["prototype"] == "editor"
    assert _read_face("processor", {"tool": "dub_clip"}, [])[0] == "video"
    # 过渡词: modifier 随 B4 退役, materialize 随历史清理收 — spec 原样.
    mod_spec = {"tool": "remove_filler", "output_ids": []}
    assert _read_face("processor", mod_spec, []) == ("modifier", mod_spec)
    mat_spec = {"tool": "materialize_source"}
    assert _read_face("processor", mat_spec, []) == ("materialize", mat_spec)
    # 无 tool 回退 = text×manual (the full-text card is the safest reading).
    assert _read_face("generator", {}, []) == ("text", {"prototype": "manual"})


def test_read_face_synthesizes_writer_text_from_the_latest_output():
    from app.pipeline.routes.projects import _read_face

    out_old = Output(id=uuid4(), project_id=_PROJECT_ID, type="post",
                     payload={"content": "old"})
    out_new = Output(id=uuid4(), project_id=_PROJECT_ID, type="post",
                     payload={"content": "the latest words"})
    kind, spec = _read_face(
        "generator", {"tool": "write_post", "output_ids": ["x", "y"]}, [out_old, out_new]
    )
    assert kind == "text"
    assert spec["text"] == "the latest words"  # the 全文卡 face
    # An existing spec.text (a C2b+ row's sync back-write) is never clobbered.
    kind2, spec2 = _read_face(
        "generator", {"tool": "write_post", "text": "stamped"}, [out_new]
    )
    assert spec2["text"] == "stamped"
    # 非 writer 的 text×generator (research) 不合成.
    assert "text" not in _read_face("agent", {"tool": "research"}, [out_new])[1]
