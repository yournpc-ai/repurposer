"""Graph store (ADR-057) — the wiring layer, the graph's ONLY write door.

The project graph is a persistent, mutable product object (two tables,
``graph_nodes`` / ``graph_edges``, owner = Pipeline, MODULE_ARCH §4). Every
mutation — chat-built drafts, prompt edits, deletions, run fills — lands
here as a batch of wiring ops; the canvas reads the graph directly (zero
projection). 能力完备、手势缺席: the op set is complete enough to express
anything chat wiring needs (manual wiring capability MUST exist for chat
wiring to rest on), but no UI ever exposes manual gestures.

Ops (the registry below): ``add_node`` / ``connect`` / ``edit_prompt`` /
``delete_node`` / ``run``. Initial generation, revision and new builds are
the SAME op set — the "revision loop" as a separate concept is retired;
there is one graph being edited continuously. Islands are legal (the graph
is a forest, not a single connected DAG).

Adjudication mirrors compile_graph's posture: validate EVERY op first (op
type / reference existence / port-type compatibility / no cycle), land the
batch in one flush (the caller commits — create_run precedent), or reject
the whole batch (WiringRejected). Execution is NOT here: a ``run`` op only
resolves its target subgraph into the returned delta — the run itself is
born at the only birthplace (orchestrator.create_run), zero bypass.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import GraphEdge, GraphNode, Project


class WiringRejected(ValueError):
    """A wiring op failed adjudication (unknown op / dangling reference /
    incompatible ports / a cycle). Same family as ToolRejected — request
    handlers translate to 422, chat degrades to a plain-language reply."""


# ---- op schemas (the wiring registry) --------------------------------------


class AddNodeOp(BaseModel):
    """Place a node. ``spec`` is the node's program (prompt / params /
    asset_id / text — well-formed shapes are the producer's knowledge, K2's
    migration mapping); ``after`` wires its birth edges (connect's shorthand).
    ``id`` pins the newborn's identity — the server-side stamper's seat: its
    SAME-batch connect ops reference the pinned id, so frames are born with
    full edge knowledge (布局一开始就定好, 2026-09-08 用户拍板 — never an
    island guess repaired by a second pass). Chat proposals never carry one."""

    op: Literal["add_node"]
    kind: Literal["asset", "document", "generator", "processor", "agent"]
    spec: dict[str, Any] = Field(default_factory=dict)
    after: list[UUID] = Field(default_factory=list)
    id: UUID | None = None


class ConnectOp(BaseModel):
    """Wire one typed flow. ``edge_type`` None derives from the two ends'
    port offers (ctx = the reference/context flow)."""

    op: Literal["connect"]
    from_node: UUID
    to_node: UUID
    edge_type: Literal["video", "audio", "text", "ctx"] | None = None
    from_port: str | None = None
    to_port: str | None = None


class EditPromptOp(BaseModel):
    """Rewrite a generator/agent node's prompt — the card-face direct edit
    AND the chat-pointed revision are this one op. A done node goes stale
    (its product predates the new program); a running node rejects (it is
    executing the old program — the revision reruns it)."""

    op: Literal["edit_prompt"]
    node: UUID
    prompt: str


class DeleteNodeOp(BaseModel):
    """Remove a node; its edges die with it structurally. Products
    (outputs rows) are NOT touched — they have their own lifecycle
    (DELETE /outputs/{id})."""

    op: Literal["delete_node"]
    node: UUID


class DisconnectOp(BaseModel):
    """Sever one typed flow. The stamp reconciliation's seat (2026-09-10
    边对账律, ADR-062): the compiled topology owns every edge among its own
    members — an edge the compile no longer emits is retracted through this
    op, never left lingering next to the new set (the run-fill's grow-only
    law covers nodes/history, never a stale topology claim). A compiler-
    internal gesture: the prompt catalog never lists it, chat proposals
    never emit it."""

    op: Literal["disconnect"]
    from_node: UUID
    to_node: UUID
    edge_type: Literal["video", "audio", "text", "ctx"]


class RunOp(BaseModel):
    """Fill nodes (an execution event, not a graph write). ``nodes`` None =
    the batch's affected subgraph; the resolved set always closes over
    downstream (a node rerun refills what feeds off it). Execution itself
    stays at orchestrator.create_run — this op only resolves the target."""

    op: Literal["run"]
    nodes: list[UUID] | None = None


WiringOp = Annotated[
    AddNodeOp | ConnectOp | DisconnectOp | EditPromptOp | DeleteNodeOp | RunOp,
    Field(discriminator="op"),
]

WIRING_OPS: dict[str, type[BaseModel]] = {
    "add_node": AddNodeOp,
    "connect": ConnectOp,
    "disconnect": DisconnectOp,
    "edit_prompt": EditPromptOp,
    "delete_node": DeleteNodeOp,
    "run": RunOp,
}

_OPS_ADAPTER: TypeAdapter[Any] = TypeAdapter(list[WiringOp])


def wiring_catalog_lines() -> str:
    """The registry's self-projection as prompt lines (注册表条目扰动 =
    prompt 扰动纪律: entries stay terse + the gate enumerations ride along).
    The chat intent surfaces consume this verbatim — K4 wires it in."""
    return "\n".join(
        [
            "- add_node: place a node (kind: asset|document|generator|processor|agent; "
            "spec: the node's program — prompt/params; after: upstream node ids to wire from)",
            "- connect: wire a typed flow between two nodes "
            "(edge_type: video|audio|text|ctx — ctx = the reference/context flow)",
            "- edit_prompt: rewrite a generator/agent node's prompt",
            "- delete_node: remove a node (its edges go with it)",
            "- run: fill nodes with products (nodes optional — default = the "
            "affected subgraph; always closes over downstream)",
        ]
    )


# ---- ports (the port law's data half) ---------------------------------------

# kind → (offers, accepts). An edge's type must be offered by its source and
# accepted by its target; ctx is the universal context flow (never the only
# choice when a concrete type is shared — the derivation prefers it last).
_NODE_PORTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "asset": (frozenset(), frozenset()),  # per asset type — see _offers/_accepts
    "document": (frozenset({"text", "ctx"}), frozenset({"text"})),
    "generator": (
        frozenset({"video", "audio", "text"}),
        frozenset({"video", "audio", "text", "ctx"}),
    ),
    "processor": (
        frozenset({"video"}),
        frozenset({"video", "audio", "text", "ctx"}),
    ),
    "agent": (frozenset({"text"}), frozenset({"text", "ctx"})),
}

# An asset's out-ports by its asset type (the three-flow source: a video
# offers video + audio + the transcript text).
_ASSET_OFFERS: dict[str, frozenset[str]] = {
    "video": frozenset({"video", "audio", "text"}),
    "audio": frozenset({"audio", "text"}),
    "image": frozenset({"video", "text"}),
    "slides": frozenset({"video", "text"}),
}


def _offers(node: GraphNode) -> frozenset[str]:
    if node.kind == "asset":
        return _ASSET_OFFERS.get(
            str((node.spec or {}).get("asset_type") or ""), frozenset({"text"})
        )
    return _NODE_PORTS.get(node.kind, (frozenset(), frozenset()))[0]


def _accepts(node: GraphNode) -> frozenset[str]:
    return _NODE_PORTS.get(node.kind, (frozenset(), frozenset()))[1]


def _derive_edge_type(from_node: GraphNode, to_node: GraphNode) -> str:
    """The shared concrete type, ctx last — never an invented flow."""
    common = _offers(from_node) & _accepts(to_node)
    for candidate in ("video", "audio", "text"):
        if candidate in common:
            return candidate
    if "ctx" in common or "ctx" in _accepts(to_node):
        return "ctx"
    raise WiringRejected(
        f"No compatible port between {from_node.kind} and {to_node.kind}"
    )


# ---- layout (画布定居取景: assigned once, append-only) ----------------------

# Canvas frames per SIZE CLASS (w, h) — the graph surface's reserved boxes.
# Heights reserve the class's MAX content height (the frontend renders
# content-driven heights inside the reservation, so a column never overlaps
# and a node fills into its reservation as products land): clip = the 9:16
# product card's full anatomy (caption 26 + thumb 498 + program 88 + bar
# 44); text = the 12-line text card's (caption 26 + body 282 + program 88 +
# bar 44). A node's class comes from spec.frame_class (the fill stamps it
# from the family's product vocabulary); an unstamped generator/processor/
# agent reserves the clip maximum — safe by construction.
_GAP_MAIN = 96
_GAP_CROSS = 24
# A fresh column's first node RISES above its topmost parent (2026-09-09
# 走查拍板, FLORA 同典): out-ports ride the parent's top-RIGHT (~54px from
# its top: outBase 40 + half the 28px anchor), in-ports the child's
# bottom-LEFT (~204px from its top at the draft anatomy: 26+120+88+44 −
# inBase 60 − half the anchor), so a top-aligned child forces every edge
# into a steep S across the gap. Lifting the child by the port-geometry
# delta + a breath of slack (204 − 54 − 24) lets the line arc gently.
_FRESH_COLUMN_RISE = 126
_FRAME_CLASS: dict[str, tuple[int, int]] = {
    "asset": (280, 260),
    "document": (260, 200),
    # 440 → 560 (2026-09-10 用户拍板——内容长度驱动卡高): the taller text
    # reservation derives an 18-line preview cap (was 12) client-side; the
    # cap is computed FROM each node's own reservation, so nodes born under
    # 440 keep their 12-line guarantee — append-only 保序律 covers size law
    # changes without migration.
    "text": (340, 560),
    "clip": (280, 660),
}
_KIND_FRAME_CLASS = {"asset": "asset", "document": "document"}

# The task-book document's role tag (graph_fill's stamps set it; the frame
# law reads it for the dock-time confirm allowance). One home here — the
# graph's role vocabulary is the door's business, never a magic string per
# call site.
_TASK_BOOK_ROLE = "task_book"

# 全文卡律 (2026-09-10 判词④——进了卡面的必须原文全文，无摘要无浓缩): the
# document card never truncates, so a text-bearing document's frame is BORN
# at the text's full height (documents know their text at birth — the
# transcript lands with ASR, the book's plan summary with the dock). The
# line math is ONE law with the client's shared measurement
# (apps/web/src/components/flow/layout.ts — the text card's chars-per-line
# table, scaled proportionally to the document's narrower text width); two
# mirrors cross-referenced, never a third copy (判词②).
_DOCUMENT_LINE_PX = 18  # text-xs leading-relaxed (same as the text card)
_DOCUMENT_CAPTION_PX = 26  # NodeCaption band (= PRODUCT_LABEL_PX)
# The task_book's dock-time confirm anatomy (price + balance + the Start
# button): resident while the book is unconfirmed, so the frame reserves it
# from birth; post-Start the card simply fills less of its reservation
# (cards fill INTO frames, never the reverse).
_DOCUMENT_CONFIRM_PX = 88
_CJK_RE = re.compile(r"[一-龥぀-ゟ゠-ヿ]")


def _document_frame(spec: dict[str, Any]) -> tuple[int, int]:
    w, _ = _FRAME_CLASS["document"]
    text = str(spec.get("text") or "")
    # The text card's table is 44 CJK / 68 Latin chars per 312px of text
    # width; the document's column is 228px — the same proportion (one law).
    cjk = bool(_CJK_RE.search(text))
    chars_per_line = 32 if cjk else 50
    lines = max(1, math.ceil(len(text) / chars_per_line)) if text else 1
    h = _DOCUMENT_CAPTION_PX + 16 + lines * _DOCUMENT_LINE_PX + 16
    if spec.get("role") == _TASK_BOOK_ROLE:
        h += _DOCUMENT_CONFIRM_PX
    return w, h

# 统一摆位律 (2026-09-09 拍板): ONE frame law owns every newborn's frame
# (_assign_layout), and columns are DEPTH-pitched — x = depth × _PITCH,
# never derived from a parent's right edge (mixed frame widths made
# parent-right columns ragged: same-column nodes of different widths hand
# their children different starts, and same-depth siblings drift into
# horizontal overlap). Depth = the topological generation (max parent
# depth + 1, islands 0), so a child always lands strictly right of EVERY
# parent by ≥ _GAP_MAIN. A node's column IS its depth — the frame's x is a
# rendering of it, never the source of truth. Frames of projects born
# before this law are replayed once by migration (see
# migrations/versions/e7a9c1d35b28_depth_pitch_frames.py).
_PITCH = max(w for w, _ in _FRAME_CLASS.values()) + _GAP_MAIN  # 340 + 96


def _frame_of(kind: str, spec: dict[str, Any]) -> tuple[int, int]:
    cls = _KIND_FRAME_CLASS.get(kind) or str(spec.get("frame_class") or "") or "clip"
    if cls == "document":
        return _document_frame(spec)
    return _FRAME_CLASS.get(cls, _FRAME_CLASS["clip"])


def _assign_layout(
    kind: str,
    spec: dict[str, Any],
    depth: int,
    parents: list[GraphNode],
    column: list[GraphNode],
) -> dict[str, int]:
    """THE one frame law (统一摆位律) — every newborn's settled frame comes
    from this function and nowhere else:
      x = depth × _PITCH                  (depth-pitched columns, never ragged)
      y = ① the column's tail + _GAP_CROSS  (siblings stack in place)
          ② a fresh column → the topmost parent's y − _FRESH_COLUMN_RISE
             (the port-geometry delta — the out→in arc stays gentle)
          ③ an island → 0
    Existing frames NEVER move — the graph only grows, it never jolts
    (append-only 保序律)."""
    w, h = _frame_of(kind, spec)
    if column:
        y = (
            max(
                int((n.layout or {}).get("y", 0)) + int((n.layout or {}).get("h", h))
                for n in column
            )
            + _GAP_CROSS
        )
    elif parents:
        y = min(int((p.layout or {}).get("y", 0)) for p in parents) - _FRESH_COLUMN_RISE
    else:
        y = 0
    return {"x": depth * _PITCH, "y": y, "w": w, "h": h}


def settle_frames_with_edges(
    newborns: list[GraphNode],
    placed: list[GraphNode],
    edges: list[GraphEdge],
) -> None:
    """The door's frame settle (画布定居取景): every newborn's frame is
    assigned ONCE — by _assign_layout, the one frame law — parents-first
    over the batch's FINAL edge set (a node is born with full edge
    knowledge, never an island guess repaired later; 2026-09-08 用户拍板:
    布局一开始就定好). ``placed`` = the settled history — existing frames
    NEVER move (append-only 保序律); the newborns' provisional add-time
    values are replaced before the flush, so no provisional frame is ever
    persisted."""
    by_id = {UUID(str(n.id)): n for n in [*placed, *newborns]}

    def parents_of(node_id: UUID) -> list[GraphNode]:
        return [
            by_id[UUID(str(e.from_node))]
            for e in edges
            if UUID(str(e.to_node)) == node_id and UUID(str(e.from_node)) in by_id
        ]

    # Depth = the topological generation (max parent depth + 1, islands 0),
    # memoized over the FINAL edge set — settled history derives it the same
    # way (a node's column IS its depth; the frame's x merely renders it).
    # The cycle guard only keeps a poisoned world from looping forever — the
    # wiring adjudication rejects cycles before this ever runs.
    depth_memo: dict[UUID, int] = {}

    def depth_of(node_id: UUID, trail: set[UUID]) -> int:
        memo = depth_memo.get(node_id)
        if memo is not None:
            return memo
        if node_id in trail:
            return 0
        trail.add(node_id)
        ups = parents_of(node_id)
        d = 0 if not ups else max(depth_of(UUID(str(p.id)), trail) for p in ups) + 1
        depth_memo[node_id] = d
        return d

    def frame_of(node: GraphNode) -> None:
        nid = UUID(str(node.id))
        depth = depth_of(nid, set())
        parents = parents_of(nid)
        column = [n for n in working if depth_of(UUID(str(n.id)), set()) == depth]
        node.layout = _assign_layout(node.kind, node.spec or {}, depth, parents, column)

    settled = {UUID(str(n.id)) for n in placed}
    working = list(placed)
    pending = list(newborns)
    # Parents-first passes: a newborn whose parent is also a newborn waits
    # for the pass that settles it (a chain settles one link per pass).
    # Structurally cycle-free (the wiring adjudication rejects cycles); the
    # fallback below settles whatever remains rather than loop forever.
    while pending:
        progressed = False
        for node in list(pending):
            nid = UUID(str(node.id))
            if any(UUID(str(p.id)) not in settled for p in parents_of(nid)):
                continue
            frame_of(node)
            working.append(node)
            settled.add(nid)
            pending.remove(node)
            progressed = True
        if not progressed:
            for node in pending:
                frame_of(node)
                working.append(node)
            break


# ---- the delta ---------------------------------------------------------------


class GraphDelta(BaseModel):
    """What a wiring batch changed. ``affected`` = nodes touched (added /
    prompt-edited / deleted). ``run_nodes`` = a run op's resolved target
    subgraph (seeds ∪ downstream, deterministic order); None = the batch
    carried no run op."""

    affected: list[UUID] = Field(default_factory=list)
    run_nodes: list[UUID] | None = None


# ---- the write door ------------------------------------------------------------


async def apply_wiring_ops(
    db: AsyncSession,
    project_id: UUID,
    ops: list[dict[str, Any] | BaseModel],
) -> GraphDelta:
    """Validate and land one batch of wiring ops. THE graph's only write.

    Flush-only — the caller commits (the batch commits atomically with the
    turn that caused it, create_run precedent). Raises WiringRejected; the
    whole batch dies together, never a half-applied graph.
    """
    parsed: list[BaseModel] = _OPS_ADAPTER.validate_python(ops)
    project = await db.get(Project, project_id)
    if project is None:
        raise WiringRejected(f"Project not found: {project_id}")

    nodes: dict[UUID, GraphNode] = {
        UUID(str(n.id)): n
        for n in (
            await db.execute(
                select(GraphNode).where(GraphNode.project_id == project_id)
            )
        )
        .scalars()
        .all()
    }
    edges: list[GraphEdge] = list(
        (
            await db.execute(
                select(GraphEdge).where(GraphEdge.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    # Persistent-at-load edges (disconnect needs the distinction: a pre-
    # existing row takes a real DELETE, a same-batch newborn just drops out
    # of the working list before it ever lands).
    persisted_edge_ids = {id(e) for e in edges}

    def children_of(node_id: UUID) -> list[UUID]:
        return [UUID(str(e.to_node)) for e in edges if UUID(str(e.from_node)) == node_id]

    def reaches(start: UUID, target: UUID) -> bool:
        """Downstream reachability over the working edge set (cycle checks
        and run-subgraph closure share this one walk)."""
        seen: set[UUID] = set()
        frontier = [start]
        while frontier:
            cur = frontier.pop()
            if cur == target:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            frontier.extend(children_of(cur))
        return False

    def add_edge(
        from_id: UUID,
        to_id: UUID,
        edge_type: str | None,
        from_port: str | None,
        to_port: str | None,
    ) -> None:
        from_node = nodes.get(from_id)
        to_node = nodes.get(to_id)
        if from_node is None or to_node is None:
            raise WiringRejected(f"connect: dangling reference {from_id} → {to_id}")
        if from_id == to_id:
            raise WiringRejected("connect: a node cannot feed itself")
        etype = edge_type or _derive_edge_type(from_node, to_node)
        if etype not in _offers(from_node):
            raise WiringRejected(
                f"connect: {from_node.kind} does not offer {etype}"
            )
        if etype not in _accepts(to_node):
            raise WiringRejected(f"connect: {to_node.kind} does not accept {etype}")
        if reaches(to_id, from_id):
            raise WiringRejected("connect: the edge would close a cycle")
        if any(
            UUID(str(e.from_node)) == from_id
            and UUID(str(e.to_node)) == to_id
            and e.edge_type == etype
            for e in edges
        ):
            raise WiringRejected(f"connect: duplicate {etype} edge {from_id} → {to_id}")
        edges.append(
            GraphEdge(
                id=uuid4(),
                project_id=project_id,
                from_node=from_id,
                from_port=from_port or f"out:{etype}",
                to_node=to_id,
                to_port=to_port or f"in:{etype}",
                edge_type=etype,
            )
        )

    delta = GraphDelta()
    pending_delete: list[UUID] = []
    newborn_ids: list[UUID] = []  # op order — the post-loop layout pass

    for op in parsed:
        if isinstance(op, AddNodeOp):
            if op.id is not None and op.id in nodes:
                raise WiringRejected(f"add_node: id {op.id} already exists")
            parents = []
            for parent_id in op.after:
                parent = nodes.get(parent_id)
                if parent is None:
                    raise WiringRejected(f"add_node: unknown upstream {parent_id}")
                parents.append(parent)
            pw, ph = _frame_of(op.kind, dict(op.spec))
            node = GraphNode(
                # Explicit ids: the working map wires after-edges off them
                # BEFORE the flush (the column default only fires at INSERT).
                # A stamper-pinned id (op.id) lets the SAME batch's connect
                # ops reference the newborn — frames born with full edge
                # knowledge.
                id=op.id or uuid4(),
                project_id=project_id,
                kind=op.kind,
                # Assets are inputs, not execution units — their content is
                # self-evident at birth (processing status lives on the
                # asset row itself). Everything else is born a draft
                # (图先展示后运行 — zero consumption until a run fills it).
                state="done" if op.kind == "asset" else "draft",
                spec=dict(op.spec),
                # Provisional frame (a placeholder — the door's settle
                # replaces it with the frame law's output before the flush,
                # so no provisional value is ever persisted). Pitch-monotone
                # (right of every parent, risen with them) so the run op's
                # layout-ordered subgraph reads the same before and after
                # the settle.
                layout={
                    "x": (
                        max(int((p.layout or {}).get("x", 0)) for p in parents) + _PITCH
                        if parents
                        else 0
                    ),
                    "y": (
                        min(int((p.layout or {}).get("y", 0)) for p in parents)
                        - _FRESH_COLUMN_RISE
                        if parents
                        else 0
                    ),
                    "w": pw,
                    "h": ph,
                },
            )
            nodes[UUID(str(node.id))] = node
            newborn_ids.append(UUID(str(node.id)))
            delta.affected.append(UUID(str(node.id)))
            for parent_id in op.after:
                add_edge(parent_id, UUID(str(node.id)), None, None, None)
        elif isinstance(op, ConnectOp):
            add_edge(op.from_node, op.to_node, op.edge_type, op.from_port, op.to_port)
        elif isinstance(op, DisconnectOp):
            match = next(
                (
                    e
                    for e in edges
                    if UUID(str(e.from_node)) == op.from_node
                    and UUID(str(e.to_node)) == op.to_node
                    and e.edge_type == op.edge_type
                ),
                None,
            )
            if match is None:
                raise WiringRejected(
                    f"disconnect: no {op.edge_type} edge {op.from_node} → {op.to_node}"
                )
            edges.remove(match)
            if id(match) in persisted_edge_ids:
                await db.delete(match)
        elif isinstance(op, EditPromptOp):
            node = nodes.get(op.node)
            if node is None:
                raise WiringRejected(f"edit_prompt: unknown node {op.node}")
            if node.kind not in ("generator", "agent"):
                raise WiringRejected(
                    f"edit_prompt: a {node.kind} node has no prompt to edit"
                )
            if node.state in ("queued", "running"):
                raise WiringRejected(
                    "edit_prompt: the node is running its program — let it "
                    "finish, then revise"
                )
            node.spec = {**(node.spec or {}), "prompt": op.prompt}
            if node.state == "done":
                # The product now predates the program — stale until the
                # revision reruns it (原型 C: stale = factsbar 可重跑徽章).
                node.state = "stale"
            delta.affected.append(op.node)
        elif isinstance(op, DeleteNodeOp):
            node = nodes.get(op.node)
            if node is None:
                raise WiringRejected(f"delete_node: unknown node {op.node}")
            pending_delete.append(op.node)
            delta.affected.append(op.node)
            nodes.pop(op.node)
            edges[:] = [
                e
                for e in edges
                if UUID(str(e.from_node)) != op.node and UUID(str(e.to_node)) != op.node
            ]
        elif isinstance(op, RunOp):
            seeds = op.nodes if op.nodes is not None else list(delta.affected)
            for seed in seeds:
                if seed not in nodes:
                    raise WiringRejected(f"run: unknown node {seed}")
            resolved: set[UUID] = set()
            for seed in seeds:
                resolved.add(seed)
                # Close over downstream — a node rerun refills what feeds
                # off it (修订 = edit_prompt + run({node} ∪ downstream)).
                resolved |= {n for n in nodes if reaches(seed, n)}
            delta.run_nodes = sorted(
                resolved,
                key=lambda n: (
                    int((nodes[n].layout or {}).get("x", 0)),
                    int((nodes[n].layout or {}).get("y", 0)),
                ),
            )

    # Settle the newborns' frames with FULL edge knowledge (画布定居取景):
    # parents-first over the batch's FINAL edge set (the add-time column
    # guess was a placeholder — the real parents are the batch's edges).
    # Each frame is assigned ONCE here, before the flush — born right, never
    # repaired later; existing frames NEVER move (append-only 保序律).
    placed = [n for n in nodes.values() if UUID(str(n.id)) not in set(newborn_ids)]
    settle_frames_with_edges([nodes[nid] for nid in newborn_ids], placed, edges)

    # Land the batch: deletions (edges cascade structurally), then the new
    # rows, then the edited rows (ORM-tracked already). TWO flushes, nodes
    # strictly before edges (2026-09-09 取证): the UOW only orders inter-
    # table inserts through relationship()s and these tables have none — a
    # single mixed flush let the edge INSERT precede the node's (SQLA
    # 2.0.51, vacuum-reproduced) and FK-violated at random (轮盘赌, born at
    # K1). The explicit stage boundary makes the order structural — never
    # merge the flushes back.
    for node_id in pending_delete:
        row = await db.get(GraphNode, node_id)
        if row is not None:
            await db.delete(row)
    for node in nodes.values():
        db.add(node)
    await db.flush()
    for edge in edges:
        db.add(edge)
    await db.flush()
    return delta


__all__ = [
    "AddNodeOp",
    "ConnectOp",
    "DeleteNodeOp",
    "DisconnectOp",
    "EditPromptOp",
    "GraphDelta",
    "RunOp",
    "WIRING_OPS",
    "WiringOp",
    "WiringRejected",
    "apply_wiring_ops",
    "settle_frames_with_edges",
    "wiring_catalog_lines",
]
