"""RunPlan orchestrator: materialize the plan graph, walk it, settle runs.

Topology is code-determined — the LLM never shapes the graph (ADR-028, task
brief §9). Every WorkflowRun is born here (``create_run``); the worker claims
ready nodes (``jobs.claim_ready_node``) and executes them through
``execute_step``; ``execute_run_inline`` is the same walk for the demo seed
(single executor, no SKIP LOCKED needed).

Run-level semantics preserved from the retired run_generation:
- "all failed or nothing" — a run only fails when every generation node
  failed/was skipped (partial failures still complete the run);
- run COMPLETED flips the project to REVIEW;
- render nodes never hold a run open (they mirror the render chain, D2).
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetType, ProjectStatus, TaskItem, WorkflowStatus
from app.models.tables import Asset, Output, WorkflowStep, Project, Speaker, WorkflowRun
from app.metering import bind_workflow_step
from app.pipeline.node_runners import KNOWN_OUTPUTS, STEP_RUNNERS
from app.pipeline.registry import (
    SkillEntry,
    generation_node_kinds,
    validate_task_list,
)

logger = structlog.get_logger()

GENERATION_NODE_KINDS = generation_node_kinds()

_OUTPUT_TO_NODE_KIND: dict[str, str] = {
    "clips": "clips_pipeline",
    "post": "post_gen",
    "quotes": "quotes_gen",
    "carousel": "carousel_gen",
    "article": "article_gen",
}

_TARGETED_DERIVATIVE_SCOPES = {"derivative", "post", "quotes", "carousel", "article"}


class TaskSpec(BaseModel):
    """The task book: normalized generation intent (任务书).

    Mirrors GenerateRequest/chat dispatch; stored verbatim on run.context.
    ``tasks`` is the LLM-proposed task list (CHAT_ARCH §3) — when present,
    compile_graph runs mode② and the fixed topologies below are bypassed.
    """

    outputs: list[str] = ["clips"]
    clip_count: int = 5
    target_language: str = "en"
    instruction: str | None = None
    tone_settings: dict | None = None
    brand_template_id: str | None = None
    scope: str = "full"
    operation: str = "regenerate"
    target_id: UUID | None = None
    tasks: list[TaskItem] | None = None


class _NodeSpec:
    """Lowering record; ``inputs`` are indices into the lowered list."""

    __slots__ = ("kind", "seq", "inputs", "spec")

    def __init__(self, kind: str, seq: int, inputs: list[int] | None = None, spec: dict | None = None) -> None:
        self.kind = kind
        self.seq = seq
        self.inputs = inputs or []
        self.spec = spec or {}


def compile_graph(task: TaskSpec, target_type: str | None = None) -> list[_NodeSpec]:
    """Lower a task book into a fixed node topology (pure, code-determined).

    Mode② (task list): ``task.tasks`` is materialized via ``_compile_task_list``.
    Mode① (fixed topology):
    Full run:   preprocess → persona_bootstrap ↘
                       → director_understand → director_plan
                -> {clips_pipeline | post_gen | quotes_gen | carousel_gen | article_gen}
                (persona_bootstrap and director_understand both hang off
                preprocess — they are independent and can run in parallel)
    Targeted:   hook/clip -> [script];
                derivative -> [director_understand -> director_plan -> X_gen];
                render -> [render].
    """
    if task.tasks:
        return _compile_task_list(task)

    scope = task.scope or "full"

    if scope == "full":
        outputs = [o for o in task.outputs if o in KNOWN_OUTPUTS] or ["clips"]
        nodes = [
            _NodeSpec("preprocess", 1),
            _NodeSpec("persona_bootstrap", 2, inputs=[0]),
            _NodeSpec("director_understand", 3, inputs=[0]),
            _NodeSpec("director_plan", 4, inputs=[1, 2]),
        ]
        # Deterministic order keeps the step list stable across runs.
        for seq, output in enumerate(
            ("clips", "post", "quotes", "carousel", "article"), start=10
        ):
            if output in outputs:
                nodes.append(
                    _NodeSpec(_OUTPUT_TO_NODE_KIND[output], seq, inputs=[3])
                )
        return nodes

    if scope in ("hook", "clip"):
        return [
            _NodeSpec(
                "script",
                1,
                spec={
                    "scope": scope,
                    "target_id": str(task.target_id) if task.target_id else None,
                    "instruction": task.instruction,
                    "operation": task.operation,
                },
            )
        ]

    if scope in _TARGETED_DERIVATIVE_SCOPES:
        if not target_type:
            raise ValueError(f"Cannot lower scope={scope} without a target type")
        return [
            _NodeSpec("director_understand", 1),
            _NodeSpec("director_plan", 2, inputs=[0], spec={"target_type": target_type}),
            _NodeSpec(
                _OUTPUT_TO_NODE_KIND[target_type],
                3,
                inputs=[1],
                spec={
                    "target_id": str(task.target_id) if task.target_id else None,
                    "target_language": task.target_language,
                    "target_type": target_type,
                },
            ),
        ]

    if scope == "render":
        return [
            _NodeSpec(
                "render",
                1,
                spec={"target_id": str(task.target_id) if task.target_id else None},
            )
        ]

    raise ValueError(f"Targeted scope not implemented: {scope}")


_SKILL_TO_OUTPUT: dict[str, str] = {
    "select_clips": "clips",
    "write_post": "post",
    "write_quotes": "quotes",
    "write_carousel": "carousel",
    "write_article": "article",
}


def _compile_task_list(task: TaskSpec) -> list[_NodeSpec]:
    """Mode②: materialize an LLM-proposed task list into a standard graph.

    Pure, code-determined (CHAT_ARCH §5): the registry adjudicates existence
    and params; topology is derived here — generation skills that need a
    director share one deduped prelude (preprocess → persona_bootstrap ∥
    director_understand → director_plan); modifier skills (needs_director=
    False, e.g. remove_filler / add_music) hang off the clips node when one
    exists, else get empty inputs (= act on the project's existing clips).
    Modifiers are chained in proposal order so two of them never edit the same
    render_spec concurrently. Defaults come from the params schemas, never
    from the LLM.
    """
    entries = validate_task_list(task.tasks or [])  # raises SkillRejected
    nodes: list[_NodeSpec] = []

    if any(entry.needs_director for entry in entries):
        nodes.extend(
            [
                _NodeSpec("preprocess", 1),
                _NodeSpec("persona_bootstrap", 2, inputs=[0]),
                _NodeSpec("director_understand", 3, inputs=[0]),
                _NodeSpec("director_plan", 4, inputs=[1, 2]),
            ]
        )
    director_idx = 3 if nodes else None

    seq = 10
    skill_node_idx: dict[str, int] = {}
    modifiers: list[tuple[TaskItem, SkillEntry]] = []
    for item, entry in zip(task.tasks or [], entries, strict=True):
        params = entry.params_model.model_validate(item.params or {}) if entry.params_model else None
        if not entry.needs_director and not entry.produces_outputs:
            modifiers.append((item, entry))
            continue
        if entry.name == "revise_script":
            assert params is not None
            spec = {
                "scope": params.scope,
                "target_id": params.target_output_id
                or (str(task.target_id) if task.target_id else None),
                "instruction": params.instruction or task.instruction,
                "operation": "revise",
            }
        elif entry.node_kind == "clips_pipeline":
            spec = {"target_language": task.target_language}
        else:
            spec = {
                "target_id": str(task.target_id) if task.target_id else None,
                "target_language": task.target_language,
                "target_type": _SKILL_TO_OUTPUT[entry.name],
            }
        inputs = [director_idx] if director_idx is not None else []
        skill_node_idx[entry.name] = len(nodes)
        nodes.append(_NodeSpec(entry.node_kind, seq, inputs=inputs, spec=spec))
        seq += 1

    # Modifiers run after the nodes named in their `after` constraints (when
    # present in this graph) and after the previous modifier — never in
    # parallel with each other. No edges at all = act on existing clips.
    prev_modifier_idx: int | None = None
    for item, entry in modifiers:
        params = entry.params_model.model_validate(item.params or {}) if entry.params_model else None
        inputs = [skill_node_idx[name] for name in entry.after if name in skill_node_idx]
        if prev_modifier_idx is not None:
            inputs.append(prev_modifier_idx)
        prev_modifier_idx = len(nodes)
        spec = params.model_dump(mode="json") if params else {}
        nodes.append(_NodeSpec(entry.node_kind, seq, inputs=inputs, spec=spec))
        seq += 1

    return nodes


def derive_context_fields(tasks: list[TaskItem]) -> dict:
    """Backfill the mode① context fields (outputs / clip_count) from a task
    list, so run.context consumers always see the same shape."""
    outputs: list[str] = []
    clip_count: int | None = None
    for item in tasks:
        output = _SKILL_TO_OUTPUT.get(item.skill)
        if output and output not in outputs:
            outputs.append(output)
        if item.skill == "select_clips" and (item.params or {}).get("count"):
            clip_count = int(item.params["count"])
    fields: dict = {"outputs": outputs}
    if clip_count is not None:
        fields["clip_count"] = clip_count
    return fields


async def _validate_requires(
    db: AsyncSession, project: Project, entries: list[SkillEntry]
) -> None:
    """Birthplace rejection: every input a task list's skills declare must
    exist on the project before the run is created (CHAT_ARCH §5)."""
    needs: set[str] = set()
    for entry in entries:
        needs.update(entry.requires)
    for req in sorted(needs):
        missing = False
        if req == "media":
            result = await db.execute(
                select(Asset.id)
                .where(
                    Asset.project_id == project.id,
                    Asset.type.in_(
                        [AssetType.VIDEO, AssetType.AUDIO, AssetType.IMAGE, AssetType.SLIDES]
                    ),
                    Asset.file_url.isnot(None),
                )
                .limit(1)
            )
            missing = result.scalar_one_or_none() is None
        elif req == "transcript":
            result = await db.execute(
                select(Asset.id)
                .where(
                    Asset.project_id == project.id,
                    or_(
                        Asset.transcript.isnot(None),
                        Asset.meta["words"].isnot(None),
                    ),
                )
                .limit(1)
            )
            missing = result.scalar_one_or_none() is None
        elif req == "speaker_photo":
            speaker = (
                await db.get(Speaker, project.speaker_id) if project.speaker_id else None
            )
            missing = speaker is None or not speaker.avatar_url
        elif req == "voiceprint":
            if not project.speaker_id:
                missing = True
            else:
                result = await db.execute(
                    select(Asset.id)
                    .where(
                        Asset.speaker_id == project.speaker_id,
                        Asset.type == AssetType.VOICE_SAMPLE,
                    )
                    .limit(1)
                )
                missing = result.scalar_one_or_none() is None
        if missing:
            raise ValueError(f"Missing required input: {req}")


async def create_run(
    db: AsyncSession,
    project: Project,
    task: TaskSpec,
) -> WorkflowRun:
    """Create a run and materialize its plan graph. THE ONLY WorkflowRun birthplace."""
    target_type: str | None = None
    if task.scope in _TARGETED_DERIVATIVE_SCOPES and task.target_id is not None:
        target = await db.get(Output, task.target_id)
        if target is None or target.project_id != project.id:
            raise ValueError("Target output not found")
        if target.type not in _OUTPUT_TO_NODE_KIND or target.type == "clips":
            raise ValueError(f"Target output type {target.type} is not regenerable")
        target_type = target.type

    if task.tasks:
        entries = validate_task_list(task.tasks)  # raises SkillRejected
        await _validate_requires(db, project, entries)

    run = WorkflowRun(
        project_id=project.id,
        status=WorkflowStatus.PENDING,
        context=task.model_dump(mode="json"),
        progress=0,
    )
    db.add(run)
    await db.flush()

    node_specs = compile_graph(task, target_type)
    nodes: list[WorkflowStep] = []
    for ns in node_specs:
        node = WorkflowStep(
            run_id=run.id,
            kind=ns.kind,
            status="pending",
            seq=ns.seq,
            spec=ns.spec,
        )
        db.add(node)
        nodes.append(node)
    await db.flush()  # assign ids
    # Resolve input indices to node ids.
    for node, ns in zip(nodes, node_specs, strict=True):
        node.inputs = [str(nodes[i].id) for i in ns.inputs]
    await db.commit()
    logger.info(
        "run_materialized",
        run_id=str(run.id),
        nodes=len(node_specs),
        scope=task.scope,
    )
    return run


async def execute_step(node_id: UUID) -> None:
    """Execute one claimed node; settle terminal state + downstream + the run.

    Never raises — failures land on the node row (and cascade-skip downstream).
    """
    run_id: UUID | None = None
    try:
        async with AsyncSessionLocal() as db:
            node = await db.get(WorkflowStep, node_id)
            if node is None or node.status not in ("pending", "running"):
                return
            run_id = node.run_id
            if node.status == "pending":
                node.status = "running"
                node.started_at = datetime.now(UTC)
                node.attempt = (node.attempt or 0) + 1
            run = await db.get(WorkflowRun, node.run_id)
            if run is not None and run.status == WorkflowStatus.PENDING:
                run.status = WorkflowStatus.RUNNING
            await db.commit()

        try:
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                run = await db.get(WorkflowRun, node.run_id)
                project = await db.get(Project, run.project_id)
                runner = STEP_RUNNERS[node.kind]
                with bind_workflow_step(node.id):
                    output_ids = await runner(db, run, node, project)
                node.output_refs = [str(oid) for oid in (output_ids or [])]
                if node.kind == "render":
                    # The render chain owns this node's terminal state (D2):
                    # back to pending so the render-status claim mirror moves it.
                    node.status = "pending"
                    node.finished_at = None
                else:
                    node.status = "done"
                    node.finished_at = datetime.now(UTC)
                await db.commit()
                logger.info("workflow_step_done", node_id=str(node_id), kind=node.kind)
        except Exception as e:  # noqa: BLE001 — record any failure on the node
            logger.error("workflow_step_failed", node_id=str(node_id), error=str(e))
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                node.status = "failed"
                node.error = str(e)[:2000]
                node.finished_at = datetime.now(UTC)
                await db.commit()
                await _cascade_skip(db, node)
                await db.commit()
    finally:
        if run_id is not None:
            await maybe_finalize_run(run_id)


async def _cascade_skip(db: AsyncSession, failed_node: WorkflowStep) -> None:
    """Transitively mark downstream pending nodes as skipped."""
    frontier = [failed_node.id]
    while frontier:
        current = frontier.pop()
        result = await db.execute(
            select(WorkflowStep).where(
                WorkflowStep.run_id == failed_node.run_id,
                WorkflowStep.status.in_(["pending", "running"]),
                WorkflowStep.inputs.contains([str(current)]),
            )
        )
        for child in result.scalars():
            child.status = "skipped"
            child.error = f"upstream node {current} failed"
            child.finished_at = datetime.now(UTC)
            frontier.append(child.id)


async def maybe_finalize_run(run_id: UUID) -> None:
    """Settle a run once no non-render node is active.

    Render nodes are excluded from the active/failure tally (they mirror the
    render chain and never hold a run open — same semantics as the retired
    orchestration, where renders continued after the run completed).
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(
            WorkflowRun, run_id, with_for_update=True
        )
        if run is None or run.status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
        ):
            return

        nodes = list(
            (await db.execute(select(WorkflowStep).where(WorkflowStep.run_id == run_id)))
            .scalars()
            .all()
        )
        total = len(nodes)
        settled = sum(1 for n in nodes if n.status in ("done", "failed", "skipped"))
        run.progress = int(settled / total * 100) if total else 100

        active = [
            n
            for n in nodes
            if n.status in ("pending", "running") and n.kind != "render"
        ]
        if active:
            await db.commit()
            return

        gen_nodes = [n for n in nodes if n.kind in GENERATION_NODE_KINDS]
        any_failed = any(n.status == "failed" for n in nodes)
        gen_failed_like = [n for n in gen_nodes if n.status in ("failed", "skipped")]

        if any_failed and (not gen_nodes or len(gen_failed_like) == len(gen_nodes)):
            first_error = next((n.error for n in nodes if n.status == "failed"), None)
            run.status = WorkflowStatus.FAILED
            run.error = first_error or "All outputs failed"
        else:
            run.status = WorkflowStatus.COMPLETED
            run.error = None
            project = await db.get(Project, run.project_id)
            if project is not None:
                project.status = ProjectStatus.REVIEW
                project.updated_at = datetime.now(UTC)
        run.progress = 100
        await db.commit()
        logger.info(
            "run_finalized",
            run_id=str(run_id),
            status=run.status.value,
            nodes=total,
        )


async def execute_run_inline(run_id: UUID) -> None:
    """Walk a run's graph in-process (demo seed). Same runners as the worker.

    Render nodes are skipped here just like in the node claim — the worker
    renders them in the background via outputs.render_status.
    """
    while True:
        async with AsyncSessionLocal() as db:
            node_id = (
                await db.execute(
                    text(
                        """
                        SELECT pn.id FROM workflow_steps pn
                        WHERE pn.run_id = :rid
                          AND pn.status = 'pending'
                          AND pn.kind <> 'render'
                          AND NOT EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(pn.inputs) AS up(id)
                            JOIN workflow_steps upn ON upn.id = up.id::uuid
                            WHERE upn.status <> 'done'
                          )
                        ORDER BY pn.seq
                        LIMIT 1
                        """
                    ),
                    {"rid": run_id},
                )
            ).scalar_one_or_none()
        if node_id is None:
            break
        await execute_step(node_id)
    await maybe_finalize_run(run_id)


async def finalize_stuck_runs() -> None:
    """Finalize RUNNING runs whose nodes are all settled (crash recovery)."""
    async with AsyncSessionLocal() as db:
        run_ids = (
            await db.execute(
                text(
                    """
                    SELECT r.id FROM workflow_runs r
                    WHERE r.status = 'RUNNING'
                      AND NOT EXISTS (
                        SELECT 1 FROM workflow_steps pn
                        WHERE pn.run_id = r.id
                          AND pn.status IN ('pending', 'running')
                          AND pn.kind <> 'render'
                      )
                    """
                )
            )
        ).scalars().all()
    for rid in run_ids:
        await maybe_finalize_run(rid)
