"""exploration_compile — the two turn paths' shared exploration-compile
orchestration (iter-3 S2, R12/R14 双门).

The plan path (iter-2 ③/⑤) and the chat path (iter-3 S2, R6 parity) run the
SAME discovery-chain landing law: journey resolution from the named selects
(one call plans one journey) → the pre-flight compile over in-memory preview
rows (an uncompilable package rejects back into the loop with ZERO writes —
an uncompilable plan never reaches the canvas or the dock) → the transform
backstop → the exploration door's own birth (its validation re-runs as the
authority). What differs between the paths is only the DOCK seat below the
compile (plan path: the brief machinery + stored-prompt freeze; chat path:
``_dock_plan_as_question``) — the compile law itself lives here ONCE, so the
two loops can never drift on it.

The error strings this module returns ARE the loop echo (the rejection is
the repair signal, never a crash) — keep their wording stable; both paths
hand them to the model verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import GraphNode, Project
from app.pipeline.exploration_store import (
    KIND_SELECT,
    STATE_DRAFT,
    STATE_READY,
    ContentPlanSpec,
    ExplorationRejected,
    plan_completeness_issues,
    propose_plans,
    read_journey_evidence,
    read_journey_plans,
)
from app.pipeline.product_graph import EXPLORATION_NODE_TYPE
from app.pipeline.scope_compile import (
    ScopeCompileRejected,
    compile_scope,
)
from app.tools import ToolRejected

if TYPE_CHECKING:
    from app.chat.exploration_tools import PlanItem


@dataclass
class PlanPreview:
    """The pre-flight compile's in-memory stand-in for a Content Plan row
    (R14 双门): the compile passes BEFORE the door births anything, so the
    duck-typed fields (id / state / spec) mirror what ``compile_scope``
    reads off a real row. (Born in plan_turn.py iter-2 ③; re-homed here in
    iter-3 S2 when the chat path grew the same seat.)"""

    id: str
    state: str
    spec: dict


@dataclass
class CompiledPackage:
    """The exploration package's compiled form, ready for either dock seat:
    the journey it rides, the evidence rows the compile dereferenced, the
    door-born (or journey-wide re-read) plan rows, the compiled chain, and
    the plan→task map keyed on the REAL plan row ids (the snapshot's R20
    router substrate — for a fresh birth the pre-flight map is re-keyed from
    the preview ids onto the born rows, the door births in compile order)."""

    journey_id: UUID
    selects: list[Any]
    candidate_sets: list[Any]
    plans: list[Any]
    tasks: list[Any]
    plan_task_map: dict[str, list[int]] = field(default_factory=dict)


async def compile_plans_package(
    db: AsyncSession,
    project: Project,
    plan_items: list[PlanItem],
    *,
    persona_id: UUID | None,
) -> CompiledPackage | str:
    """propose_plans's double door (R14): pre-flight compile → birth.

    Returns the CompiledPackage on success; on any rejection returns the
    loop-echo string with zero writes (pre-flight) or the door's own
    rejection (the birth attempt — the door's savepoint keeps it atomic).
    """
    # Journey resolution: the items carry select ids and the journey rides
    # structurally from them (one call plans one journey — the door's own
    # law, mirrored here so the pre-flight has its evidence).
    select_ids = [UUID(str(p.select_id)) for p in plan_items]
    rows = list(
        (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.project_id == project.id,
                    GraphNode.type == EXPLORATION_NODE_TYPE,
                    GraphNode.id.in_(select_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {str(n.id): n for n in rows}
    journey_ids: set[str] = set()
    for sid in select_ids:
        row = by_id.get(str(sid))
        if row is None or (row.spec or {}).get("exploration_kind") != KIND_SELECT:
            return (
                f"select: node {sid} is not one of this project's "
                "selects — re-read the propose_selects observation."
            )
        journey_ids.add(str(row.journey_id))
    if len(journey_ids) > 1:
        return (
            "propose_plans: one call plans one journey — the selects "
            "span two. Split the call."
        )
    journey_id = UUID(journey_ids.pop())
    selects, candidate_sets = await read_journey_evidence(
        db, UUID(str(project.id)), journey_id
    )

    # The pre-flight compile (R12 编译移出 LLM): in-memory previews of the
    # rows the door WOULD birth (same completeness self-check, same states)
    # — a rejection here writes nothing.
    previews: list[PlanPreview] = []
    for i, p in enumerate(plan_items):
        issues = plan_completeness_issues(p.outputs)
        payload = ContentPlanSpec(
            select_id=str(p.select_id),
            title=p.title.strip(),
            outputs=p.outputs,
            persona_id=str(persona_id) if persona_id else None,
        ).model_dump()
        if issues:
            payload["issues"] = issues
        previews.append(
            PlanPreview(
                # Per-ITEM uniqueness (one call may plan the same select
                # twice — the door allows it): a bare preview:{select_id}
                # key would collide in the pre-flight map and cross-wire
                # the re-key below (S2 pure-test find, 2026-09-23).
                id=f"preview:{i}:{p.select_id}",
                state=STATE_DRAFT if issues else STATE_READY,
                spec=payload,
            )
        )
    compiled = await _compile_and_check(db, project, previews, selects, candidate_sets)
    if isinstance(compiled, str):
        return compiled

    # Pre-flight passed — the door births the rows (its validation re-runs
    # as the authority; a door rejection rides back as the echo).
    try:
        born = await propose_plans(
            db,
            project,
            plans=[p.model_dump() for p in plan_items],
            persona_id=persona_id,
        )
    except ExplorationRejected as e:
        return f"The door rejected the proposal: {e}"

    # R20 修订路由器基材 (iter-3 E1/E2): re-key the pre-flight map (preview
    # ids) onto the born rows — the door births in the same order the
    # previews compiled (the compile is deterministic), so the ranges
    # transfer verbatim.
    plan_task_map = {
        str(born_row.id): compiled.plan_task_map[preview.id]
        for preview, born_row in zip(previews, born, strict=True)
        if preview.id in compiled.plan_task_map
    }
    return CompiledPackage(
        journey_id=journey_id,
        selects=selects,
        candidate_sets=candidate_sets,
        plans=list(born),
        tasks=compiled.tasks,
        plan_task_map=plan_task_map,
    )


async def recompile_journey_package(
    db: AsyncSession,
    project: Project,
    journey_id: UUID,
) -> CompiledPackage | str:
    """revise_plan's whole-journey recompile (决策包可编辑律): a revise
    targets one plan, but the decision package re-compiles with EVERY plan
    of the journey — real rows straight off the canvas (no previews; the
    rows already carry the door's state), same compiler, same transform
    backstop. The map reads ``compile_scope``'s own keys (real row ids)."""
    selects, candidate_sets = await read_journey_evidence(
        db, UUID(str(project.id)), journey_id
    )
    plans = await read_journey_plans(db, UUID(str(project.id)), journey_id)
    compiled = await _compile_and_check(db, project, plans, selects, candidate_sets)
    if isinstance(compiled, str):
        return compiled
    return CompiledPackage(
        journey_id=journey_id,
        selects=selects,
        candidate_sets=candidate_sets,
        plans=plans,
        tasks=compiled.tasks,
        plan_task_map=dict(compiled.plan_task_map),
    )


async def _compile_and_check(
    db: AsyncSession,
    project: Project,
    plans: list[Any],
    selects: list[Any],
    candidate_sets: list[Any],
):
    """The shared compile + backstop pair: ``compile_scope`` (R12) then the
    same-language / transform-target adjudication (the router-drafted
    dock's own backstop rides too — 同源语言护栏 etc.). Returns the
    CompiledScope, or the loop-echo string on rejection."""
    from app.pipeline.derivative_dispatch import (  # deferred: pipeline weight
        project_source_language,
    )
    from app.pipeline.morph import check_transform_targets
    from app.ui_locale import current_ui_language

    try:
        scope = compile_scope(
            plans,
            selects,
            candidate_sets,
            source_language=await project_source_language(db, project),
            default_language=project.language or current_ui_language() or "en",
        )
    except ScopeCompileRejected as e:
        return str(e)
    try:
        await check_transform_targets(
            db,
            project,
            scope.tasks,
            zh=(current_ui_language() or "").startswith("zh"),
        )
    except (ToolRejected, ValueError) as e:
        return str(e)
    return scope


__all__ = [
    "CompiledPackage",
    "PlanPreview",
    "compile_plans_package",
    "recompile_journey_package",
]
