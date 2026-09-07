"""Run bridge (ADR-057 K4) — a wiring ``run`` op's resolved subgraph back
to the chain the ONLY birthplace (orchestrator.create_run) compiles.

The wiring layer mutates the persistent graph (edit_prompt / add_node …);
EXECUTION stays where it has always been: this module translates each
affected node back into its chain entry (tool + params), deterministically,
and the task list rides the unchanged compile/billing path. Zero bypass —
the LLM never assembles this, and no second execution channel opens.

A node's executable identity is stamped at fill time (``spec.tool``) and
its structured params live in ``spec.params`` (the slot vocabulary for
writers / the transform params for translate·dub). Internal compile-only
kinds (materialize_source — never a registered tool) translate to nothing:
their products feed the subgraph's consumers through the compile's
existing "act on existing clips" wiring (mode②, unchanged).
"""

from __future__ import annotations

from app.models.schemas import TaskItem
from app.models.tables import GraphNode

# spec.params keys that ride back into the task entry verbatim (the
# transform/processor vocabulary; the writers' executable params are the
# slot itself and unpack separately).
_PARAM_KEYS = (
    "target_language",
    "bilingual",
    "fork",
    "aspect",
    "mood",
    "count",
    "focus",
    "language",
    "tone_override",
    "query",
    "scope",
)


def task_for_graph_node(node: GraphNode) -> TaskItem | None:
    """One graph node → its chain entry. None = not executable (asset /
    document / internal compile-only kind / a node predating the tool
    stamp). The node's CURRENT spec is the program — an edit_prompt that
    landed before the run is what gets re-filled."""
    if node.kind in ("asset", "document"):
        return None
    spec = node.spec or {}
    tool = spec.get("tool")
    if not isinstance(tool, str) or not tool:
        return None
    params = dict(spec.get("params") or {})
    slot = params.pop("slot", None)
    task_params = (
        {k: v for k, v in slot.items() if k != "type" and v is not None}
        if isinstance(slot, dict)
        else {}
    )
    for key in _PARAM_KEYS:
        if params.get(key) is not None and key not in task_params:
            task_params[key] = params[key]
    return TaskItem(tool=tool, params=task_params)


def tasks_for_graph_nodes(nodes: list[GraphNode]) -> list[TaskItem]:
    """The subgraph's chain (the caller passes the nodes in the wiring
    delta's order — the settled layout's x order IS depth order, so
    producers precede their consumers). Internal kinds drop out; a subgraph
    that translates to nothing rejects at the caller (never a vacuous
    run)."""
    return [
        task
        for node in nodes
        if (task := task_for_graph_node(node)) is not None
    ]
