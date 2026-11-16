"""Persistent asset and manual-Canvas CRUD.

Graph nodes and edges are user material, not a projection of Runs or Outputs.
Composition authoring and production stay in Chat; this module never starts a Run.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Asset, GraphEdge, GraphNode


class WiringRejected(ValueError):
    pass


_OFFERS = {
    "text": frozenset({"text"}),
    "table": frozenset({"text"}),
    "image": frozenset({"text"}),
    "video": frozenset({"video", "audio", "text"}),
    "audio": frozenset({"audio", "text"}),
    "document": frozenset({"text"}),
}
_ASSET_OFFERS = {
    "video": frozenset({"video", "audio", "text"}),
    "audio": frozenset({"audio", "text"}),
    "image": frozenset({"video", "text"}),
    "slides": frozenset({"video", "text"}),
}
_ACCEPTS = {
    "text": frozenset({"text"}),
    "table": frozenset({"text"}),
    "image": frozenset({"text"}),
    "video": frozenset({"video", "audio", "text"}),
    "audio": frozenset({"audio", "text"}),
}


def _offers(node: GraphNode) -> frozenset[str]:
    if node.type == "asset":
        return _ASSET_OFFERS.get(str((node.spec or {}).get("asset_type")), frozenset({"text"}))
    return _OFFERS.get(node.type, frozenset())


def _accepts(node: GraphNode) -> frozenset[str]:
    if node.type == "asset":
        return frozenset()
    return _ACCEPTS.get(node.type, frozenset())


class WiringDelta:
    def __init__(self, affected: list[UUID]):
        self.affected = affected
        self.run_nodes: list[UUID] = []


async def apply_wiring_ops(
    db: AsyncSession,
    project_id: UUID,
    raw_ops: list[dict[str, Any]],
    *,
    allow_settled_delete: bool = False,
) -> WiringDelta:
    """Validate a whole batch, then apply asset/manual-node changes atomically."""
    rows = list((await db.scalars(select(GraphNode).where(GraphNode.project_id == project_id))).all())
    nodes = {row.id: row for row in rows}
    affected: list[UUID] = []

    async def apply_connection(op: dict[str, Any]) -> None:
        source_id = UUID(str(op.get("from_node")))
        target_id = UUID(str(op.get("to_node")))
        if op["op"] == "disconnect":
            existing = await db.scalar(select(GraphEdge).where(
                GraphEdge.project_id == project_id,
                GraphEdge.from_node == source_id,
                GraphEdge.to_node == target_id,
            ))
            if existing is not None:
                await db.delete(existing)
            return
        source = nodes.get(source_id)
        target = nodes.get(target_id)
        if source is None or target is None or source.id == target.id:
            raise WiringRejected("A connection needs two different existing nodes")
        existing = await db.scalar(select(GraphEdge).where(
            GraphEdge.project_id == project_id,
            GraphEdge.from_node == source.id,
            GraphEdge.to_node == target.id,
        ))
        if existing is not None:
            return
        edge_type = op.get("edge_type")
        if edge_type is None:
            common = _offers(source) & _accepts(target)
            edge_type = next((kind for kind in ("video", "audio", "text") if kind in common), None)
        if edge_type not in {"video", "audio", "text"}:
            raise WiringRejected("These nodes have no compatible media connection")
        if edge_type not in _offers(source) or edge_type not in _accepts(target):
            raise WiringRejected("The connection is incompatible with these nodes")
        existing_edges = list((await db.scalars(select(GraphEdge).where(
            GraphEdge.project_id == project_id,
        ))).all())
        adjacency: dict[UUID, list[UUID]] = {}
        for edge in existing_edges:
            adjacency.setdefault(edge.from_node, []).append(edge.to_node)
        seen: set[UUID] = set()
        frontier = [target.id]
        while frontier:
            current = frontier.pop()
            if current == source.id:
                raise WiringRejected("A connection cannot form a cycle")
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(adjacency.get(current, []))
        db.add(GraphEdge(
            project_id=project_id, from_node=source.id, to_node=target.id,
            edge_type=edge_type, from_port=op.get("from_port"), to_port=op.get("to_port"),
        ))

    for op in raw_ops:
        kind = op.get("op")
        if kind == "add_node":
            node_type = op.get("type")
            spec = op.get("spec") or {}
            if node_type != "asset" and spec.get("prototype") != "manual":
                raise WiringRejected("Graph accepts only assets and manual nodes")
            node_id = UUID(str(op["id"])) if op.get("id") else None
            if node_id is not None and node_id in nodes:
                raise WiringRejected("Graph node already exists")
            node = GraphNode(
                id=node_id,
                project_id=project_id,
                type=node_type,
                spec=spec,
                state="done" if node_type == "asset" else "draft",
                layout=op.get("layout") or {},
            )
            db.add(node)
            await db.flush()
            nodes[node.id] = node
            affected.append(node.id)
            for parent in op.get("after") or []:
                await apply_connection({
                    "op": "connect", "from_node": str(parent), "to_node": str(node.id), "edge_type": None,
                })
        elif kind == "edit_prompt":
            node = nodes.get(UUID(str(op.get("node"))))
            if node is None or (node.spec or {}).get("prototype") != "manual":
                raise WiringRejected("Only a manual node has editable text")
            node.spec = {**(node.spec or {}), "prompt": str(op.get("prompt") or "")}
            affected.append(node.id)
        elif kind in {"connect", "disconnect"}:
            await apply_connection(op)
        elif kind == "delete_node":
            node = nodes.pop(UUID(str(op.get("node"))), None)
            if node is None:
                raise WiringRejected("Graph node not found")
            if node.type != "asset" and (node.spec or {}).get("prototype") != "manual":
                raise WiringRejected("Only assets and manual nodes can be deleted")
            await db.delete(node)
            affected.append(node.id)
        else:
            raise WiringRejected(f"Unsupported Graph operation: {kind}")

    await db.flush()
    return WiringDelta(affected)


async def stamp_asset_node(db: AsyncSession, project_id: UUID, asset: Asset) -> GraphNode:
    existing = await db.scalar(select(GraphNode).where(
        GraphNode.project_id == project_id,
        GraphNode.type == "asset",
        GraphNode.spec["asset_id"].as_string() == str(asset.id),
    ))
    if existing is not None:
        return existing
    delta = await apply_wiring_ops(db, project_id, [{
        "op": "add_node", "type": "asset",
        "spec": {
            "asset_id": str(asset.id),
            "asset_type": str(asset.type.value if hasattr(asset.type, "value") else asset.type),
            "title": asset.title,
        },
    }])
    node = await db.get(GraphNode, delta.affected[0])
    assert node is not None
    return node


async def remove_asset_node(db: AsyncSession, project_id: UUID, asset_id: UUID) -> None:
    rows = list((await db.scalars(select(GraphNode).where(
        GraphNode.project_id == project_id,
        GraphNode.type == "asset",
        GraphNode.spec["asset_id"].as_string() == str(asset_id),
    ))).all())
    for row in rows:
        await db.delete(row)
    await db.flush()


def wiring_catalog_lines() -> str:
    return (
        "- add_node: add a manual media node\n"
        "- connect / disconnect: connect compatible media nodes\n"
        "- edit_prompt: edit a manual node's text\n"
        "- delete_node: delete a manual node"
    )


async def edit_manual_graph(db: AsyncSession, project, raw_ops: list[dict[str, Any]]) -> str | None:
    """Chat-facing validation for the existing asset/manual-node write door."""
    from app.models.tables import Project as ProjectTable

    if project is None:
        return "manual Graph CRUD needs a project"
    assert isinstance(project, ProjectTable)
    rows = list((await db.scalars(select(GraphNode).where(GraphNode.project_id == project.id))).all())
    nodes = {node.id: node for node in rows}
    for op in raw_ops:
        kind = op.get("op")
        if kind == "add_node" and op.get("id") is not None:
            nodes[UUID(str(op["id"]))] = GraphNode(type=op["type"], spec=op["spec"])
        if kind == "edit_prompt":
            try:
                node = nodes.get(UUID(str(op.get("node"))))
            except ValueError:
                return "edit_prompt has an invalid Graph node id"
            if node is None or (node.spec or {}).get("prototype") != "manual":
                return "edit_prompt is available only on a manual Graph node"
        for key in ("node", "from_node", "to_node"):
            node_id = op.get(key)
            if node_id is None:
                continue
            try:
                node = nodes.get(UUID(str(node_id)))
            except ValueError:
                return f"{kind} has an invalid Graph node id"
            if node is not None and node.type != "asset" and (node.spec or {}).get("prototype") != "manual":
                return "Graph CRUD accepts only assets and manual nodes; task nodes are retired"
    try:
        await apply_wiring_ops(db, project.id, raw_ops)
    except WiringRejected as exc:
        return str(exc)
    return None
