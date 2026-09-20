"""Deterministic Scope Classifier (ADR-087 §4, Phase 4 Batch 1).

The Confirmation Doctrine's adjudication seat (Frozen Rule 7 — 范围包含性由
Application Command 层代码裁决，不是 LLM 自决): given a requested paid
execution, decide whether it is provably INSIDE the user's already-approved
scope (``continuation`` → may run autonomously, Rule 5), provably OUTSIDE it
(``expansion`` → Confirmation Dock, Rule 6), or provable neither way
(``unproven`` → Confirmation Dock — the safety default; UNPROVEN →
CONTINUATION is forbidden, Rule 10 / D4).

Approved scope has two persisted canonical sources (Batch 1 preflight,
2026-09-20 用户确认 ① — no second approved-scope data model is built):

- **graph-scoped**: the project's run-born nodes — ``graph_nodes.state !=
  "draft"`` (the run fill never deletes; ``draft`` = the unconfirmed plan
  preview, born with zero consumption). Identity = ``spec.fill_key``,
  executability = ``spec.tool``, paid-ness = the registry's
  ``produces_outputs`` declaration.
- **chain-scoped**: historical ``workflow_runs.context`` — the TaskSpec
  verbatim snapshot stored at the sole birthplace ``create_run``.

Two pure cores with **zero op semantics** (2026-09-20 用户裁定 — the
extensibility guardrail): this module owns NO op vocabulary. The wiring door
(``graph_store.apply_wiring_ops``) is the sole owner of op application
semantics (cascades / validation / closure resolution); the classifier
compares PLAIN GRAPH FACTS gathered before and after the door (the D4
resulting-scope 分类律: the judged object is the RESULTING paid execution
scope, never the operation name — an ``if "delete_node" in ops`` verdict is
structurally impossible here). New op types / node families / tools flow
through the door and the registries without touching this module; the
unknown-tool path is locked by a contract test.

- ``classify_graph_scope`` — graph entries (edit_graph / future gestures).
  Verdict rules per paid closure member (tool-carrying nodes the door's
  RunOp resolved): not in the pre-op graph or still ``draft`` → executing
  it is NEW paid work (``expansion``); approved member whose transitive
  upstream strictly GREW → it now executes on a configuration no approval
  covered (``expansion``); upstream shrank or swapped → the D4-interim
  deletion-semantics case, provable neither way (``unproven``); upstream
  unchanged → inside approved scope. Registry-unknown tools (a legacy
  ``spec.tool`` NODE_KINDS no longer declares) can prove nothing →
  ``unproven``. Registry-internal members (``produces_outputs=False``,
  e.g. research — their cost folds into the family estimate, preflight §8)
  ride as notes only and never flip the verdict alone (B2 复议点, in-册).
- ``classify_chain_against_history`` — chain entries (typed /generate,
  verbatim retry, D2). The requested chain + spec-level work fields must
  EQUAL a historical confirmed chain after canonicalization (recursive
  null-strip — the proposal convention is "null = take the default" — with
  mapping keys canonicalized; the task ORDER is preserved — it is the
  execution order). Client claims ("this is a retry") are never proof
  (Rule 9); only equality against a server-persisted chain is. Strictness
  is deliberate: a false negative docks a legitimate retry (safe), a false
  positive would run unapproved paid work (never).

Gatherers (``load_graph_facts`` / ``load_historical_chains``) read
pipeline-owned tables only, so DB access stays in this Application Command
layer and the cores never see a session (the lifecycle.py 纯核+装配器
pattern).

Batch 1 is ADDITIVE: nothing here is wired into propose_tasks /
apply_wiring_ops / _create_run_from_tasks / /generate / answer_question —
B2 (edit_graph) and B5 (/generate) do the switches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import GraphEdge, GraphNode, WorkflowRun
from app.pipeline.graph import NODE_KINDS

ScopeDecision = Literal["continuation", "expansion", "unproven"]

CONTINUATION: ScopeDecision = "continuation"
EXPANSION: ScopeDecision = "expansion"
UNPROVEN: ScopeDecision = "unproven"


@dataclass(frozen=True)
class NodeFact:
    """One graph node as a plain fact (gathered by the Application Command
    layer — the cores never see an ORM row)."""

    id: str
    type: str
    state: str  # draft | queued | running | done | failed | skipped | stale
    fill_key: str | None  # spec.fill_key — the persisted identity
    tool: str | None  # spec.tool — the executable identity
    produces_outputs: bool | None  # registry declaration, gatherer-resolved
    # (None = the tool is unknown to the current registry — proves nothing)


@dataclass(frozen=True)
class EdgeFact:
    """One graph edge as a plain fact. Upstream computation walks every
    typed flow — any edge carries execution input, regardless of type."""

    from_node: str
    to_node: str
    edge_type: str


@dataclass(frozen=True)
class ChainFacts:
    """One task chain as plain facts: the ordered tasks plus the spec-level
    work fields (persona / caption mode / role pins / language ...). Display
    and execution-governance fields (``name`` / ``autonomy`` /
    ``ui_language``) are excluded at normalization — they are not the work.
    """

    tasks: tuple[Mapping[str, Any], ...]
    spec: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScopeVerdict:
    """The deterministic adjudication. ``reasons`` are machine-readable
    fact ids (``new_paid_node:<fill_key>`` / ``draft_node_executed:<id>`` /
    ``closure_inputs_expanded:<fill_key>`` / ``closure_inputs_reduced:<id>``
    / ``unclassified_tool_member:<tool>@<id>`` / ``exact_retry`` /
    ``no_exact_retry`` ...) in the door-resolved closure order — B6's
    machine-readable blockers and future UI explanations read them.
    """

    decision: ScopeDecision
    reasons: tuple[str, ...] = ()


# ---- graph-scoped classification -------------------------------------------------


def classify_graph_scope(
    *,
    pre_nodes: tuple[NodeFact, ...],
    pre_edges: tuple[EdgeFact, ...],
    post_nodes: tuple[NodeFact, ...],
    post_edges: tuple[EdgeFact, ...],
    run_node_ids: tuple[str, ...] | None,
) -> ScopeVerdict:
    """Adjudicate the requested run closure against the run-born graph.

    ``run_node_ids`` is the closure the wiring door resolved for the run op
    (post-op working graph, topo order); ``None``/empty = no paid execution
    requested (a pure structural edit is free — trivially continuation).
    """
    if not run_node_ids:
        return ScopeVerdict(CONTINUATION, ("no_paid_execution",))

    pre_by_id = {n.id: n for n in pre_nodes}
    post_by_id = {n.id: n for n in post_nodes}
    pre_rev = _reverse_adjacency(pre_edges)
    post_rev = _reverse_adjacency(post_edges)

    expansion: list[str] = []
    unproven: list[str] = []
    notes: list[str] = []

    for node_id in run_node_ids:
        member = post_by_id.get(node_id)
        if member is None:
            unproven.append(f"closure_member_unknown:{node_id}")
            continue
        if member.tool is None:
            continue  # not executable — never part of the paid scope
        key = member.fill_key or node_id
        prior = pre_by_id.get(node_id)
        approved = prior is not None and prior.state != "draft"
        if not approved:
            # Born draft by the door in this batch, or still an unconfirmed
            # draft: executing it is NEW paid work (Rule 6), never an
            # approved continuation (Rule 10 — a draft edit is not a bypass).
            if member.produces_outputs is True:
                tag = "new_paid_node" if prior is None else "draft_node_executed"
                expansion.append(f"{tag}:{key}")
            elif member.produces_outputs is None:
                unproven.append(f"unclassified_tool_member:{member.tool}@{node_id}")
            else:
                notes.append(f"internal_tool_member:{member.tool}@{node_id}")
            continue
        # Approved member: does it now execute on an input set no approval
        # covered? (connect re-wires it; delete starves it.)
        upstream_before = _reach(pre_rev, node_id)
        upstream_after = _reach(post_rev, node_id)
        if upstream_before == upstream_after:
            continue
        if member.produces_outputs is None:
            unproven.append(f"unclassified_tool_member:{member.tool}@{node_id}")
            continue
        if member.produces_outputs is False:
            # Registry-internal members never flip the verdict alone
            # (preflight §8, in-册 — B2 复议点), but the note keeps the
            # altered configuration visible.
            notes.append(f"internal_tool_inputs_changed:{key}")
            continue
        added = upstream_after - upstream_before
        removed = upstream_before - upstream_after
        if added and not removed:
            expansion.append(f"closure_inputs_expanded:{key}")
        else:
            unproven.append(f"closure_inputs_reduced:{key}")

    if expansion:
        return ScopeVerdict(EXPANSION, tuple(expansion + unproven + notes))
    if unproven:
        return ScopeVerdict(UNPROVEN, tuple(unproven + notes))
    return ScopeVerdict(CONTINUATION, tuple(notes))


def _reverse_adjacency(edges: tuple[EdgeFact, ...]) -> dict[str, set[str]]:
    rev: dict[str, set[str]] = {}
    for e in edges:
        rev.setdefault(e.to_node, set()).add(e.from_node)
    return rev


def _reach(rev: dict[str, set[str]], node_id: str) -> frozenset[str]:
    """The transitive upstream set: every node that can reach ``node_id``."""
    seen: set[str] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        for parent in rev.get(current, ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return frozenset(seen)


# ---- chain-scoped classification --------------------------------------------------

# Spec-level fields that ARE the work. Display (name / ui_language) and
# execution governance (autonomy) are deliberately absent — they never
# change what the paid execution produces.
SPEC_WORK_FIELDS = frozenset(
    {
        "target_language",
        "instruction",
        "tone_settings",
        "persona_id",
        "scope",
        "operation",
        "target_id",
        "caption_mode",
        "source_asset_id",
        "exemplar_asset_id",
    }
)


def classify_chain_against_history(
    *,
    requested: ChainFacts,
    historical: tuple[ChainFacts, ...],
) -> ScopeVerdict:
    """Prove an exact retry: the requested chain must EQUAL a server-
    persisted confirmed chain (D2). No match → ``unproven`` → Confirmation
    Dock — never guessed into continuation (Rule 10)."""
    wanted = _normalize_chain(requested)
    for entry in historical:
        if _normalize_chain(entry) == wanted:
            return ScopeVerdict(CONTINUATION, ("exact_retry",))
    return ScopeVerdict(UNPROVEN, ("no_exact_retry",))


def _normalize_chain(facts: ChainFacts) -> tuple:
    """The canonical comparison form: spec work-fields projection (mapping
    key order erased, explicit nulls stripped) + the task list in ORDER."""
    spec_projection = {k: v for k, v in facts.spec.items() if k in SPEC_WORK_FIELDS}
    return (
        _canonicalize(spec_projection),
        tuple(_canonicalize(dict(t)) for t in facts.tasks),
    )


def _canonicalize(value: Any) -> Any:
    """Hashable canonical form: mappings → sorted (key, value) tuples with
    None values dropped ("null = take the default"); sequences → tuples
    (order preserved — task order is execution order); UUIDs → str."""
    if isinstance(value, Mapping):
        return tuple(
            sorted((str(k), _canonicalize(v)) for k, v in value.items() if v is not None)
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonicalize(v) for v in value)
    if isinstance(value, UUID):
        return str(value)
    return value


# ---- gatherers (the Application Command layer's fact loading) ---------------------


async def load_graph_facts(
    db: AsyncSession, project_id: UUID
) -> tuple[tuple[NodeFact, ...], tuple[EdgeFact, ...]]:
    """Load the project's persistent graph as plain facts. Read-only; the
    caller (B2's edit_graph switch) snapshots before the door and again
    after it (the same session's autoflush serves the post-op state)."""
    node_rows = (
        (await db.execute(select(GraphNode).where(GraphNode.project_id == project_id)))
        .scalars()
        .all()
    )
    edge_rows = (
        (await db.execute(select(GraphEdge).where(GraphEdge.project_id == project_id)))
        .scalars()
        .all()
    )
    nodes = tuple(
        NodeFact(
            id=str(n.id),
            type=str(n.type),
            state=str(n.state),
            fill_key=(n.spec or {}).get("fill_key"),
            tool=(n.spec or {}).get("tool"),
            produces_outputs=_registry_produces_outputs((n.spec or {}).get("tool")),
        )
        for n in node_rows
    )
    edges = tuple(
        EdgeFact(
            from_node=str(e.from_node),
            to_node=str(e.to_node),
            edge_type=str(e.edge_type),
        )
        for e in edge_rows
    )
    return nodes, edges


async def load_historical_chains(db: AsyncSession, project_id: UUID) -> tuple[ChainFacts, ...]:
    """Load every historical confirmed chain of the project (run.context —
    the TaskSpec snapshot stored at the sole birthplace). Rows that cannot
    prove anything (legacy context without a task list) are skipped: they
    never serve as approval proof, and skipping them only ever steers
    toward the dock."""
    rows = (
        (
            await db.execute(
                select(WorkflowRun.context).where(WorkflowRun.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    chains: list[ChainFacts] = []
    for ctx in rows:
        if not isinstance(ctx, dict):
            continue
        tasks = ctx.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            continue
        if not all(isinstance(t, dict) and (t.get("tool") or t.get("kind")) for t in tasks):
            continue
        chains.append(ChainFacts(tasks=tuple(tasks), spec=ctx))
    return tuple(chains)


def _registry_produces_outputs(tool: Any) -> bool | None:
    """Resolve the paid-output declaration from the node registry. A tool
    the current registry no longer knows (legacy spec.tool) proves nothing
    → None → the classifier's ``unproven`` path."""
    if not isinstance(tool, str) or not tool:
        return None
    node_cls = NODE_KINDS.get(tool)
    return None if node_cls is None else bool(node_cls.produces_outputs)
