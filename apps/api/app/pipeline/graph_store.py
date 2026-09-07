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
    migration mapping); ``after`` wires its birth edges (connect's shorthand)."""

    op: Literal["add_node"]
    kind: Literal["asset", "document", "generator", "processor", "agent"]
    spec: dict[str, Any] = Field(default_factory=dict)
    after: list[UUID] = Field(default_factory=list)


class ConnectOp(BaseModel):
    """Wire one typed flow. ``edge_type`` None derives from the two ends'
    port offers (ctx = the dashed context flow)."""

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


class RunOp(BaseModel):
    """Fill nodes (an execution event, not a graph write). ``nodes`` None =
    the batch's affected subgraph; the resolved set always closes over
    downstream (a node rerun refills what feeds off it). Execution itself
    stays at orchestrator.create_run — this op only resolves the target."""

    op: Literal["run"]
    nodes: list[UUID] | None = None


WiringOp = Annotated[
    AddNodeOp | ConnectOp | EditPromptOp | DeleteNodeOp | RunOp,
    Field(discriminator="op"),
]

WIRING_OPS: dict[str, type[BaseModel]] = {
    "add_node": AddNodeOp,
    "connect": ConnectOp,
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
            "(edge_type: video|audio|text|ctx — ctx = context, the dashed line)",
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

# Canvas frames per kind (w, h) — the graph surface's own size facts (the
# recipe surface keeps its frontend layout; these two sleeves share the
# canvas's one size language and are calibrated together at K3).
_GAP_MAIN = 96
_GAP_CROSS = 24
_NODE_FRAME: dict[str, tuple[int, int]] = {
    "asset": (280, 228),
    "document": (260, 200),
    "generator": (280, 420),
    "processor": (280, 380),
    "agent": (280, 420),
}


def _assign_layout(
    kind: str, parents: list[GraphNode], existing: list[GraphNode]
) -> dict[str, int]:
    """The settled frame for a newborn node: x = right of its parents'
    rightmost edge (islands start a fresh column), y = appended under that
    column's current tail. Existing frames NEVER move — the graph only
    grows, it never jolts (append-only 保序律)."""
    w, h = _NODE_FRAME[kind]
    x = (
        max(int((p.layout or {}).get("x", 0)) + int((p.layout or {}).get("w", w))
            for p in parents)
        + _GAP_MAIN
        if parents
        else 0
    )
    column = [n for n in existing if int((n.layout or {}).get("x", 0)) == x]
    y = (
        max(
            int((n.layout or {}).get("y", 0)) + int((n.layout or {}).get("h", h))
            for n in column
        )
        + _GAP_CROSS
        if column
        else 0
    )
    return {"x": x, "y": y, "w": w, "h": h}


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

    for op in parsed:
        if isinstance(op, AddNodeOp):
            parents = []
            for parent_id in op.after:
                parent = nodes.get(parent_id)
                if parent is None:
                    raise WiringRejected(f"add_node: unknown upstream {parent_id}")
                parents.append(parent)
            node = GraphNode(
                # Explicit ids: the working map wires after-edges off them
                # BEFORE the flush (the column default only fires at INSERT).
                id=uuid4(),
                project_id=project_id,
                kind=op.kind,
                # Assets are inputs, not execution units — their content is
                # self-evident at birth (processing status lives on the
                # asset row itself). Everything else is born a draft
                # (图先展示后运行 — zero consumption until a run fills it).
                state="done" if op.kind == "asset" else "draft",
                spec=dict(op.spec),
                layout=_assign_layout(op.kind, parents, list(nodes.values())),
            )
            nodes[UUID(str(node.id))] = node
            delta.affected.append(UUID(str(node.id)))
            for parent_id in op.after:
                add_edge(parent_id, UUID(str(node.id)), None, None, None)
        elif isinstance(op, ConnectOp):
            add_edge(op.from_node, op.to_node, op.edge_type, op.from_port, op.to_port)
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

    # Land the batch: deletions (edges cascade structurally), then the new
    # rows, then the edited rows (ORM-tracked already).
    for node_id in pending_delete:
        row = await db.get(GraphNode, node_id)
        if row is not None:
            await db.delete(row)
    for node in nodes.values():
        db.add(node)
    for edge in edges:
        db.add(edge)
    await db.flush()
    return delta


__all__ = [
    "AddNodeOp",
    "ConnectOp",
    "DeleteNodeOp",
    "EditPromptOp",
    "GraphDelta",
    "RunOp",
    "WIRING_OPS",
    "WiringOp",
    "WiringRejected",
    "apply_wiring_ops",
    "wiring_catalog_lines",
]
