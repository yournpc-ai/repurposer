"""RunPlan orchestrator: materialize the plan graph, walk it, settle runs.

Topology is code-determined — the LLM never shapes the graph (ADR-028, task
brief §9). Every WorkflowRun is born here (``create_run``); the worker claims
ready nodes (``jobs.claim_ready_node``) and executes them through
``execute_step``.

Run-level semantics preserved from the retired run_generation:
- "all failed or nothing" — a run only fails when every generation node
  failed/was skipped (partial failures still complete the run);
- run COMPLETED flips the project to REVIEW;
- render nodes never hold a run open (they mirror the render chain, D2).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AnswerPayload,
    AssetType,
    IntentSlot,
    ProjectStatus,
    SLOT_COUNT_LIMITS,
    TaskItem,
    WorkflowStatus,
)
from app.models.tables import Asset, Message, Output, WorkflowStep, Project, Speaker, WorkflowRun
from app.metering import bind_workflow_step
from app.pipeline.asset_processing import has_renderable_media
from app.pipeline.errors import TransientNodeError
from app.pipeline.node_runners import KNOWN_OUTPUTS, STEP_RUNNERS, slot_tag
from app.pipeline.registry import (
    SkillEntry,
    generation_node_kinds,
    retries_for_node_kind,
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


class Suspend(Exception):
    """挂起: a thin checkpoint node parks itself for a human answer (期 4).

    The checkpoint runner raises it after docking the question; execute_step's
    catch branch parks the node in ``waiting`` (options ride in
    ``spec.suspend_payload``) and the run in WAITING_HUMAN. Re-entry is
    queue-based, not call-stack resumption: the answer endpoint writes
    ``spec.answer``, flips the node back to pending and the run back to
    RUNNING, and the claim loop re-runs the runner from the top — whose
    answer branch goes straight to done.
    """

    def __init__(self, payload: dict) -> None:
        super().__init__("suspended")
        self.payload = payload


class TaskSpec(BaseModel):
    """The task book: normalized generation intent (任务书).

    Mirrors GenerateRequest/chat dispatch; stored verbatim on run.context.
    ``outputs`` is the slot list (IntentSlot, N-20 request layer) — one slot
    per requested output, same-type multi slots for multi-language/angle
    versions. ``tasks`` is the LLM-proposed task list (CHAT_ARCH §3) — when
    present, compile_graph runs mode② and the fixed topologies below are
    bypassed.
    """

    outputs: list[IntentSlot] = [IntentSlot(type="clips")]
    target_language: str = "en"
    instruction: str | None = None
    tone_settings: dict | None = None
    brand_template_id: str | None = None
    # 配音语言集 (RECIPES §4.1): task-book-level dub languages — full runs
    # fan out one fork-semantic dub node per language after the clips node.
    # Empty = no dubbing. Requires a clips slot (compile_graph raises).
    dub_languages: list[str] = []
    # Autonomy tier (intent-ask-primitive §2.7): stored verbatim on
    # run.context; the review tier inserts a direction checkpoint between
    # director_understand and director_plan on full runs (期 4).
    autonomy: str = "auto"
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


# Canonical slot order for the full-run fan-out: deterministic so the step
# list is stable across runs; same-type slots keep their request order.
_SLOT_ORDER = {"clips": 0, "post": 1, "quotes": 2, "carousel": 3, "article": 4}

_SLOT_TYPE_LABEL = {
    "clips": "Clips",
    "post": "Post",
    "quotes": "Quotes",
    "carousel": "Carousel",
    "article": "Article",
}


def ordered_slots(slots: list[IntentSlot]) -> list[IntentSlot]:
    """Canonical fan-out order (type order, then request order within type).

    Clips is a single aggregate slot — duplicate clips slots are dropped
    (first wins); the clips_pipeline runner's idempotent re-cut semantics
    assume one clips node per run.
    """
    ordered: list[IntentSlot] = []
    seen_clips = False
    for slot in sorted(
        enumerate(slots), key=lambda p: (_SLOT_ORDER.get(p[1].type, 99), p[0])
    ):
        s = slot[1]
        if s.type == "clips":
            if seen_clips:
                continue
            seen_clips = True
        ordered.append(s)
    return ordered


def slot_step_label(slot: IntentSlot) -> str | None:
    """Display label distinguishing same-kind sibling steps (per-slot fan-out).

    Preset as the step's spec.summary at materialization so two ``post_gen``
    nodes (e.g. English/German) read differently in the stepper before they
    run; the runner rewrites it with the quantified line + the same tag when
    done. ``None`` when the slot carries nothing distinguishing (the common
    case — the stepper then falls back to the kind copy as before).
    """
    tag = slot_tag(slot)
    if tag is None:
        return None
    return f"{_SLOT_TYPE_LABEL.get(slot.type, slot.type)} · {tag}"


def compile_graph(task: TaskSpec, target_type: str | None = None) -> list[_NodeSpec]:
    """Lower a task book into a fixed node topology (pure, code-determined).

    Mode② (task list): ``task.tasks`` is materialized via ``_compile_task_list``.
    Mode① (fixed topology):
    Full run:   preprocess → persona_bootstrap ↘
                       → director_understand → director_plan
                -> one executor node per task slot (per-slot fan-out: two post
                slots — e.g. en/de — produce two post_gen nodes, each carrying
                its own slot in spec)
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
        slots = ordered_slots([s for s in task.outputs if s.type in KNOWN_OUTPUTS])
        if not slots:
            slots = [IntentSlot(type="clips")]
        nodes = [
            _NodeSpec("preprocess", 1),
            _NodeSpec("persona_bootstrap", 2, inputs=[0]),
            _NodeSpec("director_understand", 3, inputs=[0]),
        ]
        if task.autonomy == "review":
            # Direction checkpoint (期 4, review tier only — the auto tier
            # never inserts one, #12; targeted runs don't either). It parks
            # the run for the user's direction pick between understanding
            # and planning; ``spec.for`` carries the use (N-19). Persona and
            # understanding ride its inputs so the plan node's old ordering
            # constraint survives transitively.
            nodes.append(
                _NodeSpec("checkpoint", 4, inputs=[1, 2], spec={"for": "direction"})
            )
            nodes.append(_NodeSpec("director_plan", 5, inputs=[3]))
        else:
            nodes.append(_NodeSpec("director_plan", 4, inputs=[1, 2]))
        plan_idx = len(nodes) - 1
        type_ordinals: dict[str, int] = {}
        clips_idx: int | None = None
        seq = 10
        for slot in slots:
            # slot_index = the slot's ordinal among its own type — the
            # executor picks its storyboard slot by it (director_plan aligns
            # storyboard slots to this same canonical order).
            slot_index = type_ordinals.get(slot.type, 0)
            type_ordinals[slot.type] = slot_index + 1
            spec: dict = {
                "slot": slot.model_dump(mode="json"),
                "slot_index": slot_index,
            }
            label = slot_step_label(slot)
            if label:
                spec["summary"] = label
            nodes.append(
                _NodeSpec(_OUTPUT_TO_NODE_KIND[slot.type], seq, inputs=[plan_idx], spec=spec)
            )
            if slot.type == "clips":
                clips_idx = len(nodes) - 1
            seq += 1
        # Dub fan-out (RECIPES §4.1): one dub node per requested language,
        # chained after the clips node. ``fork: true`` = derived-row
        # semantics (N-19: mechanism stays dub, use rides in the spec) —
        # each language becomes its own Output row instead of morphing the
        # source clips' specs. Per-language nodes light up the stepper one
        # by one, meter separately, and retry independently.
        if task.dub_languages:
            if clips_idx is None:
                raise ValueError("dub_languages requires a clips slot")
            for lang in dict.fromkeys(task.dub_languages):
                nodes.append(
                    _NodeSpec(
                        "dub",
                        seq,
                        inputs=[clips_idx],
                        spec={
                            "target_language": lang,
                            "fork": True,
                            "summary": f"Dub · {lang.upper()}",
                        },
                    )
                )
                seq += 1
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
    """Backfill the mode① context fields (slot list) from a task list, so
    run.context consumers always see the same shape. Slot type comes from the
    skill, count from its params (mode② task items carry no focus/language)."""
    slots: dict[str, IntentSlot] = {}
    for item in tasks:
        output = _SKILL_TO_OUTPUT.get(item.skill)
        if output is None or output in slots:
            continue
        count = (item.params or {}).get("count")
        slots[output] = IntentSlot(
            type=output,  # type: ignore[arg-type]
            count=int(count) if count is not None else None,
        )
    return {"outputs": [s.model_dump(mode="json") for s in slots.values()]}


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
            # Mirrors the consumption rule (platform/project_context.py):
            # documents land in extracted_text, ASR lands in transcript /
            # meta.words — any of the three satisfies a text input.
            result = await db.execute(
                select(Asset.id)
                .where(
                    Asset.project_id == project.id,
                    or_(
                        Asset.transcript.isnot(None),
                        Asset.extracted_text.isnot(None),
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


# Birthplace rejection message for the clips-media gate (A1: the gate lives
# here, not at the call sites — every run-creation path gets it for free).
CLIPS_NEED_MEDIA = (
    "Clips need a video, audio, or image source. Upload one or deselect clips."
)


async def create_run(
    db: AsyncSession,
    project: Project,
    task: TaskSpec,
) -> WorkflowRun:
    """Create a run and materialize its plan graph. THE ONLY WorkflowRun birthplace.

    Every entry constraint rejects here, once — targeted-scope validity,
    mode② skill required inputs, and the clips-media gate — so the entry
    points (/generate, the task_book start answer, chat dispatch) only
    assemble the TaskSpec. Raises ValueError; request handlers translate to
    422, chat dispatch degrades to an ask-back.

    Flush-only — the caller commits at the request boundary, so the run, the
    answer that started it, and the project state land in ONE transaction
    (the run only becomes claimable by the worker on commit).
    """
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

    # Slot sanity (C3): an out-of-bounds count is real money (count=999
    # quotes = 999 image generations). Post/article carry no count — one
    # slot = one output; same-type multi slots are how you ask for more.
    for slot in task.outputs:
        limits = SLOT_COUNT_LIMITS.get(slot.type)
        if limits and slot.count is not None and not limits[0] <= slot.count <= limits[1]:
            raise ValueError(
                f"{slot.type} count must be between {limits[0]} and {limits[1]} "
                f"(got {slot.count})"
            )

    # Clips need a renderable media source — reject at birth instead of
    # letting the run produce unrenderable clips. Unconditional: targeted
    # re-renders read the same source media, so no scope is exempt.
    if any(s.type == "clips" for s in task.outputs) and not await has_renderable_media(
        db, project.id
    ):
        raise ValueError(CLIPS_NEED_MEDIA)

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
    await db.flush()
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
                    # Clear any transient note from earlier attempts (W3) —
                    # a done node carries no error.
                    node.error = None
                await db.commit()
                logger.info("workflow_step_done", node_id=str(node_id), kind=node.kind)
        except Suspend as s:
            # Checkpoint park (期 4): node → waiting with the derived options
            # in spec.suspend_payload, run → WAITING_HUMAN. The question was
            # already docked by the runner in its own session (committed
            # before raising), so nothing here rolls back. No cascade — the
            # downstream nodes simply stay pending behind the waiting one.
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                node.status = "waiting"
                node.spec = {**(node.spec or {}), "suspend_payload": s.payload}
                run = await db.get(WorkflowRun, node.run_id)
                if run is not None:
                    run.status = WorkflowStatus.WAITING_HUMAN
                await db.commit()
                logger.info("workflow_step_waiting", node_id=str(node_id), kind=node.kind)
        except Exception as e:  # noqa: BLE001 — record any failure on the node
            logger.error("workflow_step_failed", node_id=str(node_id), error=str(e))
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                # Step-level retry (agent-loop-upgrade W3): a TransientNodeError
                # within the kind's retry budget resets the node to pending —
                # the worker's next tick is the backoff, downstream is NOT
                # cascade-skipped. Deterministic failures fail fast as before.
                budget = retries_for_node_kind(node.kind)
                if isinstance(e, TransientNodeError) and (node.attempt or 0) <= budget:
                    node.status = "pending"
                    node.error = f"transient attempt {node.attempt}: {str(e)[:500]}"
                    node.finished_at = None
                    await db.commit()
                    logger.info(
                        "workflow_step_retry",
                        node_id=str(node_id),
                        kind=node.kind,
                        attempt=node.attempt,
                    )
                    return
                node.status = "failed"
                node.error = str(e)[:2000]
                node.finished_at = datetime.now(UTC)
                await db.commit()
                await _cascade_skip(db, node)
                await db.commit()
    finally:
        if run_id is not None:
            await maybe_finalize_run(run_id)


async def _cascade_skip(
    db: AsyncSession, failed_node: WorkflowStep, *, reason: str | None = None
) -> None:
    """Transitively mark downstream pending nodes as skipped.

    ``reason`` overrides the failure line — the checkpoint bail cascade is a
    graceful exit (#5), so its skipped children read "user bailed", never
    "upstream failed".
    """
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
            child.error = reason or f"upstream node {current} failed"
            child.finished_at = datetime.now(UTC)
            frontier.append(child.id)


async def resume_waiting_checkpoint(
    db: AsyncSession, run: WorkflowRun, answer: dict
) -> WorkflowStep | None:
    """answer = resume: write the AnswerPayload dump into the waiting
    checkpoint's spec, flip the node back to pending and the run back to
    RUNNING — the claim loop re-executes the thin node, whose spec.answer
    branch goes straight to done. Idempotent: no waiting checkpoint → None
    (already resumed or bailed). Flush-only; the caller commits."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.kind == "checkpoint",
            WorkflowStep.status == "waiting",
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        return None
    node.spec = {**(node.spec or {}), "answer": answer}
    node.status = "pending"
    node.started_at = None
    if run.status == WorkflowStatus.WAITING_HUMAN:
        run.status = WorkflowStatus.RUNNING
    logger.info("checkpoint_resumed", run_id=str(run.id), node_id=str(node.id))
    return node


async def bail_waiting_checkpoint(
    db: AsyncSession, run: WorkflowRun
) -> WorkflowStep | None:
    """Bail path (期 4): node done with ``spec.bailed`` + downstream cascade-
    skipped with the non-failure reason (#5). The run itself settles
    COMPLETED via maybe_finalize_run once the caller commits — the bailed
    checkpoint's summary line ("Bailed by user") is the user-abort note in
    the aggregated run summary. Idempotent like resume. Flush-only."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.kind == "checkpoint",
            WorkflowStep.status == "waiting",
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        return None
    node.spec = {**(node.spec or {}), "bailed": True, "summary": "Bailed by user"}
    node.status = "done"
    node.finished_at = datetime.now(UTC)
    await _cascade_skip(db, node, reason="user bailed")
    logger.info("checkpoint_bailed", run_id=str(run.id), node_id=str(node.id))
    return node


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
            # waiting counts as active: a checkpoint parked for a human answer
            # must never let the run settle (期 4).
            if n.status in ("pending", "running", "waiting") and n.kind != "render"
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


async def expire_stale_checkpoints(older_than: timedelta | None = None) -> int:
    """Auto-answer long-parked checkpoints with their default option.

    Expiry semantics = the review tier degrades to best-judgment completion
    after the TTL (the leave-note promise: 离开不中断) — never a bail, never
    a permanent park. The answer carries the machine marker
    ``answer.text="expired"`` (same pattern as ``superseded``); the default
    option has no argument id, so director_plan injects no direction —
    exactly the auto-tier behavior. The message UPDATE is guarded by
    ``answer IS NULL``: a user answer racing the sweep always wins, and
    ``resume_waiting_checkpoint`` is itself idempotent. Returns the number
    of checkpoints expired (0 is the common, silent case).
    """
    ttl = (
        older_than
        if older_than is not None
        else timedelta(seconds=settings.checkpoint_expiry_seconds)
    )
    cutoff = datetime.now(UTC) - ttl
    expired = 0
    async with AsyncSessionLocal() as db:
        nodes = list(
            (
                await db.execute(
                    select(WorkflowStep).where(
                        WorkflowStep.kind == "checkpoint",
                        WorkflowStep.status == "waiting",
                        WorkflowStep.started_at < cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        for node in nodes:
            payload = (node.spec or {}).get("suspend_payload") or {}
            message_id = payload.get("question_message_id")
            default = next(
                (
                    o
                    for o in payload.get("options") or []
                    if o.get("argument_id") is None
                ),
                None,
            )
            if not message_id or default is None:
                logger.warning(
                    "checkpoint_expiry_skipped_corrupt_payload", node_id=str(node.id)
                )
                continue
            answer = AnswerPayload(
                kind="option",
                option_id=default["id"],
                text="expired",
                answered_at=datetime.now(UTC),
            ).model_dump(mode="json")
            settled_id = await db.scalar(
                update(Message)
                .where(Message.id == UUID(str(message_id)), Message.answer.is_(None))
                .values(answer=answer)
                .returning(Message.id)
            )
            if settled_id is None:
                continue  # the user answered between the scan and this write
            run = await db.get(WorkflowRun, node.run_id)
            if run is not None:
                await resume_waiting_checkpoint(db, run, answer)
            await db.commit()
            expired += 1
            logger.info(
                "checkpoint_expired", node_id=str(node.id), run_id=str(node.run_id)
            )
    return expired


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
                          AND pn.status IN ('pending', 'running', 'waiting')
                          AND pn.kind <> 'render'
                      )
                    """
                )
            )
        ).scalars().all()
    for rid in run_ids:
        await maybe_finalize_run(rid)
