"""DAG edge reads (ADR-039 P1 split): loading upstream artifacts through the
``inputs`` edge list, storyboard/slot alignment, and coverage derivation.

Upstreams are matched by kind, never by position — the full-run prelude fans
out (persona_bootstrap ∥ director_understand), so input order is not a
stable contract.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    CoverageReport,
    IntentSlot,
    MaterialUnderstanding,
    Storyboard,
    StoryboardSlot,
)
from app.models.tables import Output, WorkflowStep


async def _upstream_by_kind(
    db: AsyncSession, node: WorkflowStep, kind: str
) -> WorkflowStep:
    """Find this node's direct upstream step of the given kind."""
    for upstream_id in node.inputs or []:
        upstream = await db.get(WorkflowStep, UUID(str(upstream_id)))
        if upstream is not None and upstream.kind == kind:
            return upstream
    raise ValueError(f"Node {node.id} ({node.kind}) has no upstream {kind} node")


async def _load_understanding(
    db: AsyncSession, node: WorkflowStep
) -> MaterialUnderstanding:
    """Load the MaterialUnderstanding from this node's upstream
    director_understand node (its output row may be a reused earlier one).

    The direction checkpoint (期 4) sits transparently between plan/executor
    nodes and the understand node — upstreams are matched by kind, so the
    search walks through checkpoint nodes' inputs one extra hop."""
    frontier = [str(i) for i in (node.inputs or [])]
    visited: set[str] = set()
    understand: WorkflowStep | None = None
    while frontier and understand is None:
        upstream = await db.get(WorkflowStep, UUID(frontier.pop()))
        if upstream is None or str(upstream.id) in visited:
            continue
        visited.add(str(upstream.id))
        if upstream.kind == "director_understand":
            understand = upstream
        elif upstream.kind == "checkpoint":
            frontier.extend(str(i) for i in (upstream.inputs or []))
    if understand is None:
        raise ValueError(f"Node {node.id} ({node.kind}) has no upstream director_understand node")
    if not understand.output_refs:
        raise ValueError("Upstream director_understand node has no output")
    row = await db.get(Output, UUID(str(understand.output_refs[0])))
    if row is None or row.type != "material_understanding":
        raise ValueError("material_understanding output not found")
    return MaterialUnderstanding.model_validate(row.payload)


async def _load_director_outputs(
    db: AsyncSession, node: WorkflowStep
) -> tuple[MaterialUnderstanding, Storyboard]:
    """Load both director artifacts for an executor node (two upstream hops):
    the storyboard from director_plan, the understanding from its upstream."""
    plan_node = await _upstream_by_kind(db, node, "director_plan")
    understanding = await _load_understanding(db, plan_node)
    if not plan_node.output_refs:
        raise ValueError("Upstream director_plan node has no storyboard output")
    row = await db.get(Output, UUID(str(plan_node.output_refs[0])))
    if row is None or row.type != "storyboard":
        raise ValueError("storyboard output not found")
    return understanding, Storyboard.model_validate(row.payload)


def _align_storyboard_slots(
    sb_slots: list[StoryboardSlot], intent_slots: list[IntentSlot]
) -> list[StoryboardSlot]:
    """Zip storyboard slots 1:1 onto the task slots (same type, in order).

    The task book's explicit fields (count/focus/tone_override) are binding —
    code enforces them here so the director's remaining freedom is exactly
    the vacancies: argument_ids / quote_candidates / cta (and focus when the
    slot left it open). Same-type multi slots keep the canonical order both
    sides share (executor nodes find their slot by that ordinal).
    """
    pool: dict[str, list[StoryboardSlot]] = {}
    for s in sb_slots:
        pool.setdefault(s.slot, []).append(s)
    aligned: list[StoryboardSlot] = []
    for islot in intent_slots:
        candidates = pool.get(islot.type, [])
        sb = candidates.pop(0) if candidates else StoryboardSlot(slot=islot.type)
        if islot.count is not None:
            sb.count = islot.count
        if islot.focus:
            sb.focus = islot.focus
        if islot.tone_override:
            sb.tone_override = islot.tone_override
        aligned.append(sb)
    return aligned


async def _checkpoint_direction(
    db: AsyncSession, node: WorkflowStep
) -> dict | None:
    """The direction checkpoint's answer as task-book input (期 4).

    Read off the plan node's checkpoint upstream (matched by kind, never by
    position): option → the chosen argument as a priority; freeform → the
    guidance text verbatim; the default option (no argument id) → None, the
    current behavior. Explicit slot focus stays binding — the priority order
    is slot.focus > checkpoint direction > director's own assignment (§2.5).
    """
    for upstream_id in node.inputs or []:
        upstream = await db.get(WorkflowStep, UUID(str(upstream_id)))
        if upstream is None or upstream.kind != "checkpoint":
            continue
        spec = upstream.spec or {}
        answer = spec.get("answer")
        if not answer:
            return None
        if answer.get("kind") == "freeform":
            text = answer.get("text")
            return {"text": text} if text else None
        if answer.get("kind") == "option":
            options = (spec.get("suspend_payload") or {}).get("options") or []
            by_id = {o.get("id"): o for o in options}
            chosen = by_id.get(answer.get("option_id")) or {}
            if not chosen.get("argument_id"):
                return None  # the default option = current behavior
            return {
                "argument_ids": [chosen["argument_id"]],
                "text": chosen.get("label"),
            }
        return None  # bail never reaches here — the plan node was skipped
    return None


def _compute_coverage(
    storyboard: Storyboard, understanding: MaterialUnderstanding
) -> CoverageReport:
    """Derive argument → slot accountability from valid argument_ids.

    Unknown ids (the LLM may invent them) are dropped in place first. The
    report is informational — never a gate (gating belongs to Phase 3 verify).
    """
    valid_ids = {a.id for a in understanding.key_arguments}
    assignments: dict[str, list[str]] = {}
    for slot in storyboard.slots:
        slot.argument_ids = [i for i in slot.argument_ids if i in valid_ids]
        for arg_id in slot.argument_ids:
            assignments.setdefault(arg_id, []).append(slot.slot)
    collisions = [
        f"{arg_id} → {', '.join(slots)}"
        for arg_id, slots in assignments.items()
        if len(slots) > 1
    ]
    unused = [a.id for a in understanding.key_arguments if a.id not in assignments]
    return CoverageReport(
        assignments=assignments, unused_arguments=unused, collisions=collisions
    )
