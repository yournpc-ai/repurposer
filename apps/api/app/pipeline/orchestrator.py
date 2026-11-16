"""RunPlan orchestrator: materialize the plan graph, walk it, settle runs.

Topology is code-determined — the LLM never shapes the graph (ADR-028, task
brief §9). Every WorkflowRun is born here (``create_run``); the worker claims
ready nodes (``jobs.claim_ready_node``) and executes them through
``execute_step``.

Run-level semantics preserved from the retired run_generation:
- the verdict (2026-09-13 ADR-074②, the pre-fork rule retired): ANY failed
  non-fanout step fails the run — a partial failure (products landed) drops
  the project to REVIEW, a total one to DRAFT;
- run COMPLETED flips the project to REVIEW;
- render nodes HOLD a run open (ADR-074② 同日三轮翻案: they mirror the
  render chain, D2 — and the run's end waits for the last render, so the
  receipt / closing line never lands mid-render).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AnswerPayload,
    AssetType,
    IntentSlot,
    ProjectStatus,
    PlanEstimate,
    RenderStatus,
    TaskItem,
    WorkflowStatus,
)
from app.models.tables import Asset, AssetStatus, CreditTransaction, Message, Output, WorkflowStep, Project, WorkflowRun
from app.metering import bind_workflow_step, merge_accrued_cost
# Graph fill/back-write (ADR-057 K2) — top-level is cycle-free: graph_fill's
# module-level chain (graph / graph_store / outputs / billing) never points
# back here; its own import of THIS module stays function-level inside
# stamp_draft_graph.
from app.pipeline.errors import TransientNodeError, user_error_line, user_line
from app.pipeline.run_review import output_is_delivered
from app.pipeline.render_ownership import (
    reconcile_orphaned_renders,
    repair_render_barriers,
)
from app.pipeline.step_display import ui_lang_of
from app.pipeline.graph import (
    NODE_KINDS,
    fold_estimates,
    node_for,
)
# Graph fill/back-write (ADR-057 K2) — top-level is cycle-free: graph_fill's
# module-level chain (graph / graph_store / outputs / billing) never points
# back here; its own import of THIS module stays function-level inside
# stamp_draft_graph.
from app.pipeline.step_context import _estimate_facts
from app.pipeline.trigger_events import (
    TRIGGER_RUN_COMPLETED,
    TRIGGER_RUN_FAILED,
    fire_trigger,
    run_trigger_ref,
)
from app.platform.billing import (
    capture_step,
    check_hold,
    credits_for_cost,
    estimate_usd_range,
    hold_run,
    release_run,
)
from app.tools import TOOL_REGISTRY, strip_null_params, validate_task_list

logger = structlog.get_logger()

_TARGETED_DERIVATIVE_SCOPES = frozenset()


class Suspend(Exception):
    """挂起: a thin interrupt node parks itself for a human answer (期 4).

    The interrupt runner raises it after docking the question; execute_step's
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


class QualityBounce(Exception):
    """质检打回 (产物质量线期 3, ADR-047 节点内有界环): the verify node's
    bounded-loop transport.

    The verify runner raises it after recording the round's snapshot; the
    execute_step catch branch resets BOTH the verify node and its upstream
    executor to ``pending`` with the structured feedback riding the
    executor's ``spec.feedback`` (its runner pops it into the agent call's
    repair echo). No failure, no cascade — the claim loop re-runs executor →
    verify, bounded by the verify node's attempt budget (≤ 2 bounces)."""

    def __init__(self, executor_id: UUID, feedback: str) -> None:
        super().__init__("quality bounce")
        self.executor_id = executor_id
        self.feedback = feedback


class TaskSpec(BaseModel):
    """The confirmed plan: normalized generation intent (计划).

    Mirrors Chat dispatch; stored verbatim on run.context.
    The only request grammar is the tool chain (``tasks``, ADR-043) —
    outputs are the compiled graph's derived projection, never declared.
    Targeted scopes (hook/clip/derivative/render) carry no chain — they
    re-run one node family off ``target_id``.
    """

    target_language: str = "en"
    instruction: str | None = None
    tone_settings: dict | None = None
    # The confirmed persona choice, pinned into run.context at plan
    # confirmation (the composer persona block → chat first message → pending
    # intent chain). None = resolve per the default-persona chain.
    persona_id: str | None = None
    scope: str = "full"
    operation: str = "regenerate"
    target_id: UUID | None = None
    tasks: list[TaskItem] | None = None
    # The UI locale the run was launched under (Accept-Language, pinned at
    # the birthplace): display-layer strings (step summaries, ask chrome)
    # follow it, never the material's language. None on legacy rows → the
    # display layer falls back to project/source language.
    ui_language: str | None = None
    # The run's display name (ADR-058 — LLM 建图时命名): a compact noun
    # phrase written by the proposing agent at birth, stored verbatim on
    # run.context; the dock's receipt title and completion line read it.
    # None on typed/legacy paths → the display layer falls back to the
    # chain-derived label. Display copy NEVER derives from frozen params.
    name: str | None = None
    # 资产角色 pins (ADR-078 判词④): settled by CODE from the role question's
    # answer / an @-mention (chat layer), never by the LLM. ``source`` = the
    # user's own material the run works on; ``exemplar`` = the reference
    # video whose craft the run reverse-compiles — it keys the decompiler's
    # compile-time injection. Stored verbatim on run.context; roles are
    # reversible between runs (the next plan may swap them).
    source_asset_id: str | None = None
    exemplar_asset_id: str | None = None
    # Server-resolved Chat turn authorizing saved-version production.
    video_authorized_by: UUID | None = None


def first_task_language(tasks: list[TaskItem] | None) -> str | None:
    """The chain's first language param — the spec-level fallback.

    Language is a per-task param now (``target_language`` on clip
    transforms, ``language`` on the writers); the spec-level field only
    feeds defaults for nodes a task didn't pin.
    """
    for task in tasks or []:
        params = task.params or {}
        lang = params.get("target_language") or params.get("language")
        if isinstance(lang, str) and lang:
            return lang
    return None


class _NodeSpec:
    """Lowering record; ``inputs`` are indices into the lowered list."""
    __slots__ = ("kind", "seq", "inputs", "spec")

    def __init__(self, kind: str, seq: int, inputs: list[int] | None = None, spec: dict | None = None) -> None:
        self.kind = kind
        self.seq = seq
        self.inputs = inputs or []
        self.spec = spec or {}


def compile_graph(task: TaskSpec) -> list[_NodeSpec]:
    """Compile the one authorized action into the existing DAG kernel."""
    entries = validate_task_list(task.tasks or [])
    if len(entries) != 1:
        raise ValueError("One saved Composition production takes exactly one task")
    entry = entries[0]
    params = entry.params_model.model_validate(strip_null_params(task.tasks[0].params))
    values = params.model_dump(mode="json", exclude_none=True)
    if entry.name == "produce_video":
        values.update({
            "target_id": str(task.target_id) if task.target_id else None,
            "target_language": task.target_language,
            "target_type": "video",
            "slot": {"type": "video"},
            "slot_index": 0,
        })
    return [_NodeSpec(entry.name, 10, inputs=[], spec=values)]


async def derive_plan_preview(
    db: AsyncSession, project: Project, tasks: list[TaskItem]
) -> list[dict]:
    entries = validate_task_list(tasks)
    return [{"type": "video" if entry.name == "produce_video" else "audio", "count": 1}
            for entry in entries]


async def derive_task_estimates(
    db: AsyncSession, project: Project, tasks: list[TaskItem]
) -> PlanEstimate | None:
    """The dock payload's credits quotation (BILLING §7): the plan's total
    [low, high] plus a per-task MARGINAL range.

    Per-task = the prefix-compile difference (compile the chain up to task i,
    subtract the credits of the chain up to i−1): the shared prelude
    (understand/plan/…) lands on the first task that needs it and cancels
    out of every later delta, so Σ per_task ≡ total exactly — the dock's
    numbers can never drift from the run's own fold (三面同源). A task adding
    no quoted cost (an unquotable fan-out, e.g. a dub whose targets don't
    exist at compile) gets None and settles at capture. Mirrors
    derive_plan_preview's compile (same profile, same graph the dock
    previews); raises ToolRejected / ValueError — the caller degrades to a
    quote-less dock exactly like a preview-less one.
    """
    if not tasks:
        return None
    spec = TaskSpec(tasks=list(tasks))
    facts = await _estimate_facts(db, project)
    from app.tools.video.production import video_quote_facts
    facts.update(await video_quote_facts(db, project, tasks))

    async def prefix_credits(prefix: list[TaskItem]) -> list[int]:
        node_specs = compile_graph(TaskSpec(tasks=list(prefix)))
        fold = fold_estimates(
            NODE_KINDS[ns.kind].estimate(
                {
                    **facts,
                    "spec": ns.spec,
                    "input_kinds": [node_specs[i].kind for i in ns.inputs],
                }
            )
            for ns in node_specs
        )
        usd_low, usd_high = estimate_usd_range(fold)
        return [
            await credits_for_cost(db, usd_low),
            await credits_for_cost(db, usd_high),
        ]

    per_task: list[list[int] | None] = []
    prev = [0, 0]
    total = [0, 0]
    for i in range(1, len(tasks) + 1):
        current = await prefix_credits(tasks[:i])
        delta = [current[0] - prev[0], current[1] - prev[1]]
        per_task.append(None if delta == [0, 0] else delta)
        prev = current
        total = current
    if total == [0, 0]:
        return None
    return PlanEstimate(total=total, per_task=per_task)


# Birthplace rejection copy for the clips-media gate — fired by the ∀-check
# when a clips slot's MEDIA requirement fails (the knowledge is the node's;
# only this user-facing way-out copy lives here).
CLIPS_NEED_MEDIA = (
    "Clips need a video, audio, or image source. Upload one or deselect clips."
)


# Birthplace rejection copy for the active-run guard (create_run).
RUN_ALREADY_ACTIVE = (
    "This project already has a run in progress — wait for it to finish."
)


class RunAlreadyActiveError(ValueError):
    """Birthplace rejection: the project already has a PENDING/RUNNING run.

    Subclasses ValueError so every existing birthplace translation (request
    handlers' 422, chat dispatch's degrade) keeps working untouched; the
    chat surface catches it first for its own plain-language line."""


async def has_active_run(
    db: AsyncSession, project_id, *, exclude_run_id: UUID | None = None
) -> bool:
    """The active-run predicate (PENDING/RUNNING — WAITING_HUMAN is parked,
    not executing). Shared by create_run's guard and the plan surface's
    late-turn zombie-dock check; callers needing serialization take the
    project row lock first. ``exclude_run_id`` (the resume arbitration seat,
    R1 B3) keeps a resuming run from counting ITSELF as the blocker — a
    RUNNING run holding a waiting node must not dead-lock its own resume."""
    clauses = [
        WorkflowRun.project_id == project_id,
        WorkflowRun.status.in_([WorkflowStatus.PENDING, WorkflowStatus.RUNNING]),
    ]
    if exclude_run_id is not None:
        clauses.append(WorkflowRun.id != exclude_run_id)
    row = (
        await db.execute(select(WorkflowRun.id).where(*clauses).limit(1))
    ).first()
    return row is not None


# The resume arbitration seat's verdict (I-EXEC-03/04, R1 B3): callers speak
# plainly off it — a blocked park is NOT a resume, and "idle" (no waiting
# node) is the idempotent no-op.
ResumeOutcome = Literal["resumed", "blocked", "idle"]


def _resume_authority_decision(
    node_present: bool, authority_free: bool
) -> ResumeOutcome:
    """The pure decision layer of the resume arbitration seat (DB-free,
    matrix-tested): no waiting node → idle; the project's {PENDING, RUNNING}
    single-owner law (I-EXEC-03) decides resume vs. 再挂 (blocked — the
    answer stays settled on the message row, the node stays parked, a later
    authority-freeing beat retries)."""
    if not node_present:
        return "idle"
    return "resumed" if authority_free else "blocked"


async def create_run(
    db: AsyncSession,
    project: Project,
    task: TaskSpec,
    *,
    reuse_video_production: bool = False,
) -> WorkflowRun:
    """The only Run birthplace: authorize, compile, quote and reserve once.

    A repeated Start on the same presented production Dock reuses its original
    Run. Explicit regeneration through another authoring turn remains distinct.
    """
    if task.ui_language is None:
        from app.ui_locale import current_ui_language
        task.ui_language = current_ui_language()
    await db.execute(select(Project).where(Project.id == project.id).with_for_update())
    if reuse_video_production:
        from app.tools.video.production import existing_video_production
        existing = await existing_video_production(db, project, task.tasks or [])
        if existing is not None:
            return existing
    from app.models.tables import now_utc
    await db.execute(update(Asset).where(
        Asset.project_id == project.id,
        Asset.processing_status == AssetStatus.PENDING,
        Asset.processing_requested_at.is_(None),
    ).values(processing_requested_at=now_utc()))
    if await has_active_run(db, project.id):
        raise RunAlreadyActiveError(
            "这个项目已有生成在进行中——等它结束再开始新的。"
            if (task.ui_language or "").startswith("zh") else RUN_ALREADY_ACTIVE
        )
    from app.tools.video.production import pin_narration_preparation, pin_video_production
    video_context = await pin_video_production(db, project, task.tasks, task.video_authorized_by)
    narration_context = await pin_narration_preparation(project, task.tasks)
    for pin, role_word, must_be_video in (
        (task.exemplar_asset_id, "exemplar", True),
        (task.source_asset_id, "source", False),
    ):
        if not pin:
            continue
        try:
            pinned = await db.get(Asset, UUID(str(pin)))
        except ValueError:
            pinned = None
        if pinned is None or pinned.project_id != project.id or not pinned.file_url:
            raise ValueError(f"The pinned {role_word} asset is not available.")
        if must_be_video and pinned.type != AssetType.VIDEO:
            raise ValueError("The exemplar must be a video")
    validate_task_list(task.tasks or [])
    run = WorkflowRun(
        project_id=project.id,
        status=WorkflowStatus.PENDING,
        context={**task.model_dump(mode="json"), **video_context, **narration_context},
        progress=0,
    )
    db.add(run)
    await db.flush()
    node_specs = compile_graph(task)
    facts = await _estimate_facts(db, project)
    from app.tools.video.production import video_quote_facts
    facts.update(await video_quote_facts(db, project, task.tasks))
    nodes: list[WorkflowStep] = []
    for ns in node_specs:
        spec = dict(ns.spec or {})
        if ns.kind == "produce_video":
            spec["narration_policy"] = video_context["narration_policy"]
            spec["aspect"] = video_context["aspect"]
        else:
            spec["narration_policy"] = narration_context["narration_preparation"]["narration_policy"]
        label = NODE_KINDS[ns.kind].label(
            IntentSlot.model_validate(spec["slot"]) if isinstance(spec.get("slot"), dict) else None,
            task.ui_language or "en",
        )
        if label:
            spec.setdefault("summary", label)
        node = WorkflowStep(
            run_id=run.id, kind=ns.kind, status="pending", seq=ns.seq, spec=spec,
            estimate=NODE_KINDS[ns.kind].estimate({
                **facts, "spec": ns.spec,
                "input_kinds": [node_specs[i].kind for i in ns.inputs],
            }),
        )
        db.add(node)
        nodes.append(node)
    await db.flush()
    for node, ns in zip(nodes, node_specs, strict=True):
        node.inputs = [str(nodes[i].id) for i in ns.inputs]
    await db.flush()
    _, usd_high = estimate_usd_range(fold_estimates([n.estimate for n in nodes]))
    required = await credits_for_cost(db, usd_high)
    await check_hold(db, user_id=project.user_id, required=required)
    await hold_run(db, user_id=project.user_id, run_id=run.id, amount=required)
    logger.info("run_materialized", run_id=str(run.id), nodes=len(nodes), scope=task.scope, credits_held=required)
    return run


# Node execution fence (2026-09-04 chat-flow-sequencing D1): a node's
# executor.run gets at most this long, period — the D9 fuse bounds wedged
# DB sessions, this bounds a hung event loop (orphan worker claimed the node
# then died mid-call, provider connection dead-but-unclosed). The MiniMax
# client already carries 120–180s per-call timeouts, so every LLM chain
# inside a healthy node stays well under this; runtime_fanout render nodes
# return immediately (the render chain owns their lifecycle + carries its
# own 900s httpx fence), so nothing legitimate outlives it. A tripped fence
# walks the existing failure path: error lands on the node row + downstream
# cascade-skips, never silent.
NODE_EXECUTION_TIMEOUT_SECONDS = 600.0


def _foreign_execution(node_status: str | None, claim_token: UUID | None) -> bool:
    """Entry defense (ADR-079): a ``running`` row WITHOUT a claim token is
    foreign — an in-flight row from before the fencing migration (the deploy
    note kills its owning asyncio task with the worker restart) or a
    claim-less mirror flip. There is no identity to fence its terminal
    writes with, so the only safe move is to stand down; a live claim
    re-mints the token and re-executes legitimately."""
    return node_status == "running" and claim_token is None


async def _fenced_step_write(
    db: AsyncSession, node_id: UUID, mine: UUID, **values
) -> bool:
    """The fencing write (ADR-079): every terminal/settle write carries the
    execution identity — ``WHERE id=:id AND claim_token=:mine``.

    rowcount=0 = authority lost (reaped, then re-claimed by a live worker,
    whose claim re-minted the token). The caller then rolls the session back
    — the executor's staged writes die with it — and stops: no capture, no
    graph sync, no cascade, no mirror, no run write (I-EXEC-01/02). The row
    lock the write takes also serializes us against the reaper: while this
    transaction is open the row cannot be reaped out from under us.
    """
    result = await db.execute(
        update(WorkflowStep)
        .where(WorkflowStep.id == node_id, WorkflowStep.claim_token == mine)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount > 0


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
            if _foreign_execution(node.status, node.claim_token):
                logger.warning(
                    "workflow_step_foreign_row_refused",
                    node_id=str(node_id),
                    kind=node.kind,
                )
                return
            mine: UUID
            if node.status == "pending":
                # Legacy direct-execution path (never worker-claimed): mint
                # our own token with a guarded flip — a racing claim wins the
                # row and we stand down instead of double-executing.
                mine = uuid4()
                minted = await db.execute(
                    update(WorkflowStep)
                    .where(
                        WorkflowStep.id == node_id,
                        WorkflowStep.status == "pending",
                    )
                    .values(
                        status="running",
                        started_at=datetime.now(UTC),
                        attempt=WorkflowStep.attempt + 1,
                        claim_token=mine,
                        updated_at=datetime.now(UTC),
                    )
                    .execution_options(synchronize_session=False)
                )
                if minted.rowcount == 0:
                    await db.rollback()
                    logger.info("workflow_step_claim_race_lost", node_id=str(node_id))
                    return
                await db.refresh(node)
                # Graph back-write (ADR-057 K2): the family's first running
                # step flips the owning graph node queued → running.
            else:
                mine = node.claim_token
            run = await db.get(WorkflowRun, node.run_id)
            if run is None or run.status == WorkflowStatus.CANCELLED:
                await db.rollback()
                return
            if run.status == WorkflowStatus.PENDING:
                run.status = WorkflowStatus.RUNNING
            await db.commit()

        accrued: dict = {}
        try:
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                run = await db.get(WorkflowRun, node.run_id)
                if (
                    run is None
                    or run.status == WorkflowStatus.CANCELLED
                    or node.claim_token != mine
                ):
                    return
                project = await db.get(Project, run.project_id)
                executor = NODE_KINDS[node.kind]
                bound = bind_workflow_step(node.id)
                # Same ledger object the runner's LLM/media calls accumulate
                # into — readable after the with-block AND on raise (D9).
                accrued = bound.accrued
                with bound:
                    try:
                        output_ids = await asyncio.wait_for(
                            executor.run(db, run, node, project),
                            timeout=NODE_EXECUTION_TIMEOUT_SECONDS,
                        )
                    except TimeoutError as exc:
                        # A bare wait_for TimeoutError carries no message —
                        # re-raise with the reason so the structlog failure
                        # event below says WHAT died (the user-facing line
                        # stays the generic honest one via user_error_line).
                        raise RuntimeError(
                            f"node execution timed out after "
                            f"{NODE_EXECUTION_TIMEOUT_SECONDS:.0f}s"
                        ) from exc
                # D9: metering no longer UPDATEs this row per LLM call from a
                # second session (that locked the row this session holds
                # uncommitted — an application-level self-deadlock under node
                # concurrency). One merge write bills the whole execution.
                new_cost = merge_accrued_cost(node.cost, accrued)
                fanout = NODE_KINDS[node.kind].runtime_fanout
                values: dict = {
                    "output_refs": [str(oid) for oid in (output_ids or [])],
                    "cost": new_cost,
                    "updated_at": datetime.now(UTC),
                }
                if fanout:
                    # The render chain owns this node's terminal state (D2):
                    # back to pending so the render-status claim mirror moves
                    # it. An authority-losing re-pend (ADR-079) — the token
                    # dies here; the render chain re-mints at its own claim.
                    values.update(
                        status="pending", finished_at=None, claim_token=None
                    )
                else:
                    values.update(
                        status="done",
                        finished_at=datetime.now(UTC),
                        # Clear any transient note from earlier attempts (W3) —
                        # a done node carries no error.
                        error=None,
                    )
                if not await _fenced_step_write(db, node_id, mine, **values):
                    # Fenced (I-EXEC-01/02): a live worker re-claimed this node
                    # while we executed. Roll back — the executor's staged
                    # writes die with the session — and stop: NO capture (the
                    # double-billing hole), no graph sync, no run write. The
                    # finally-block's maybe_finalize_run still runs (deliberate
                    # exception: row lock + terminal early-return make it
                    # idempotent, and cascade-NULLed nodes rely on it to close).
                    # kind captured pre-rollback: rollback expires every
                    # session object, and reading an expired attribute is
                    # implicit IO — MissingGreenlet under asyncio
                    # (expire_on_commit=False shields commits, never
                    # rollbacks). Same capture in every fenced tail below.
                    kind = node.kind
                    await db.rollback()
                    logger.warning(
                        "workflow_step_fenced",
                        node_id=str(node_id),
                        kind=kind,
                        tail="success",
                    )
                    return
                await db.refresh(node)
                if not fanout:
                    # Credits (ADR-055): settle the step's actual at the
                    # metering merge write — same session, same commit
                    # (ADR-050). Only the done branch: failed/skipped nodes
                    # never write a capture (失败不扣费), and runtime_fanout
                    # (render) settles in the render chain — its terminal
                    # state is D2-owned and render is priced $0 (PRICING).
                    # Only reachable with authority held (the fenced write
                    # above) — a stale execution NEVER captures.
                    await capture_step(db, user_id=project.user_id, node=node)
                # Graph back-write (ADR-057 K2): AFTER the status write above —
                # the owning graph node's state re-aggregates off its internal
                # step family (this step included), products back-write too.
                # Same session, same commit; no-op for steps outside the graph.
                await db.commit()
                logger.info("workflow_step_done", node_id=str(node_id), kind=node.kind)
        except Suspend as s:
            # Interrupt park (期 4): node → waiting with the derived options
            # in spec.suspend_payload, run → WAITING_HUMAN. The question was
            # already docked by the runner in its own session (committed
            # before raising), so nothing here rolls back. No cascade — the
            # downstream nodes simply stay pending behind the waiting one.
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                if node is None:
                    # Project deleted mid-flight (cleanup won the race) —
                    # nothing left to settle.
                    return
                parked = await _fenced_step_write(
                    db,
                    node_id,
                    mine,
                    status="waiting",
                    spec={**(node.spec or {}), "suspend_payload": s.payload},
                    cost=merge_accrued_cost(node.cost, accrued),
                    # Suspend park is authority-losing (ADR-079): the resume
                    # re-pend is re-claimed with a fresh token — this one dies.
                    claim_token=None,
                    updated_at=datetime.now(UTC),
                )
                if not parked:
                    # Fenced zombie Suspend: no park, and above all NO run
                    # write — the COMPLETED → WAITING_HUMAN resurrection path
                    # (race proof §3.4) dies here. The docked question message
                    # the runner already committed becomes an orphan (known
                    # residue, registered for a later sweep batch).
                    kind = node.kind  # pre-rollback (see tail="success")
                    await db.rollback()
                    logger.warning(
                        "workflow_step_fenced",
                        node_id=str(node_id),
                        kind=kind,
                        tail="suspend",
                    )
                    return
                await db.refresh(node)
                # Run write with expected-from-state (ADR-079): ONLY
                # RUNNING → WAITING_HUMAN may land — a terminal run can never
                # be resurrected, even when the node write raced a finalize.
                await db.execute(
                    update(WorkflowRun)
                    .where(
                        WorkflowRun.id == node.run_id,
                        WorkflowRun.status == WorkflowStatus.RUNNING,
                    )
                    .values(
                        status=WorkflowStatus.WAITING_HUMAN,
                        updated_at=datetime.now(UTC),
                    )
                    .execution_options(synchronize_session=False)
                )
                await db.commit()
                logger.info("workflow_step_waiting", node_id=str(node_id), kind=node.kind)
        except QualityBounce as q:
            # 质检打回 (期 3): the verify node judged this round failed within
            # its bounce budget. Reset BOTH nodes to pending — the executor
            # re-runs with the feedback popped into its agent call, the verify
            # re-checks the new round (its attempt counter is the loop's
            # bound). Done modifiers downstream of the executor reset with it:
            # the executor's idempotent re-run deletes the round-1 rows (their
            # morph writes die with them), so the modifiers re-apply to the
            # repaired round — never a silently unmorphed final product.
            # No cascade, no failure record, run stays open.
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                if node is None:
                    # Project deleted mid-flight — nothing left to reset.
                    return
                requeued = await _fenced_step_write(
                    db,
                    node_id,
                    mine,
                    status="pending",
                    finished_at=None,
                    # Bill the bounced verify attempt — its judge calls happened.
                    cost=merge_accrued_cost(node.cost, accrued),
                    # The bounce re-queue is authority-losing (ADR-079) — the
                    # next claim re-mints. Same for the executor + modifier
                    # resets below: any stale execution still holding their
                    # old token dies against the NULL.
                    claim_token=None,
                    updated_at=datetime.now(UTC),
                )
                if not requeued:
                    kind = node.kind  # pre-rollback (see tail="success")
                    await db.rollback()
                    logger.warning(
                        "workflow_step_fenced",
                        node_id=str(node_id),
                        kind=kind,
                        tail="quality_bounce",
                    )
                    return
                await db.refresh(node)
                executor = await db.get(WorkflowStep, q.executor_id)
                if executor is not None and executor.status == "done":
                    executor.status = "pending"
                    executor.finished_at = None
                    executor.error = None
                    executor.claim_token = None
                    executor.spec = {**(executor.spec or {}), "feedback": q.feedback}
                    siblings = list(
                        (
                            await db.execute(
                                select(WorkflowStep).where(
                                    WorkflowStep.run_id == node.run_id
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    by_id = {str(s.id): s for s in siblings}

                    def _depends_on(step: WorkflowStep, target: str) -> bool:
                        seen: set[str] = set()
                        frontier = [str(i) for i in (step.inputs or [])]
                        while frontier:
                            cur = frontier.pop()
                            if cur == target:
                                return True
                            if cur in seen:
                                continue
                            seen.add(cur)
                            up = by_id.get(cur)
                            if up is not None:
                                frontier.extend(str(i) for i in (up.inputs or []))
                        return False

                    for s in siblings:
                        cls = NODE_KINDS.get(s.kind)
                        if (
                            cls is not None
                            and not cls.needs_plan_prelude
                            and not cls.produces_outputs
                            and not cls.runtime_fanout
                            and s.status == "done"
                            and _depends_on(s, str(executor.id))
                        ):
                            s.status = "pending"
                            s.finished_at = None
                            s.error = None
                            s.claim_token = None
                await db.commit()
                logger.info(
                    "quality_bounce",
                    node_id=str(node_id),
                    executor_id=str(q.executor_id),
                )
        except Exception as e:  # noqa: BLE001 — record any failure on the node
            logger.error("workflow_step_failed", node_id=str(node_id), error=str(e))
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                if node is None:
                    # Project deleted mid-flight (cleanup won the race) —
                    # nothing left to fail.
                    return
                # Step-level retry (agent-loop-upgrade W3): a TransientNodeError
                # within the kind's retry budget resets the node to pending —
                # the worker's next tick is the backoff, downstream is NOT
                # cascade-skipped. Deterministic failures fail fast as before.
                # The budget lives on the node class (NodeBase.retries).
                executor = node_for(node.kind)
                budget = executor.retries if executor is not None else 0
                if isinstance(e, TransientNodeError) and (node.attempt or 0) <= budget:
                    requeued = await _fenced_step_write(
                        db,
                        node_id,
                        mine,
                        status="pending",
                        error=f"transient attempt {node.attempt}: {str(e)[:500]}",
                        finished_at=None,
                        cost=merge_accrued_cost(node.cost, accrued),
                        # The retry re-queue is authority-losing (ADR-079) —
                        # the next claim re-mints; this token dies.
                        claim_token=None,
                        updated_at=datetime.now(UTC),
                    )
                    if not requeued:
                        kind = node.kind  # pre-rollback (see tail="success")
                        await db.rollback()
                        logger.warning(
                            "workflow_step_fenced",
                            node_id=str(node_id),
                            kind=kind,
                            tail="retry",
                        )
                        return
                    await db.commit()
                    logger.info(
                        "workflow_step_retry",
                        node_id=str(node_id),
                        kind=node.kind,
                        attempt=node.attempt,
                    )
                    return
                # node.error is USER copy — the failed step row's tail. Bake the
                # localized line (errors.USER_ERROR_LINES, the run's pinned UI
                # locale — same bake-at-write discipline as step summaries);
                # the raw exception stays in the structlog event above, never
                # in the DB the UI reads.
                run = await db.get(WorkflowRun, node.run_id)
                project = await db.get(Project, run.project_id) if run else None
                failed = await _fenced_step_write(
                    db,
                    node_id,
                    mine,
                    status="failed",
                    error=(
                        user_error_line(e, ui_lang_of(run, project))
                        if run is not None
                        else user_error_line(e)
                    ),
                    finished_at=datetime.now(UTC),
                    # Bill the failed attempt — its LLM/media calls happened.
                    cost=merge_accrued_cost(node.cost, accrued),
                    updated_at=datetime.now(UTC),
                )
                if not failed:
                    # Fenced (I-EXEC-01/02): no sync, no rescue, no cascade —
                    # the live execution owns the node's world now.
                    kind = node.kind  # pre-rollback (see tail="success")
                    await db.rollback()
                    logger.warning(
                        "workflow_step_fenced",
                        node_id=str(node_id),
                        kind=kind,
                        tail="failure",
                    )
                    return
                await db.refresh(node)
                await db.commit()
                await _cascade_skip(db, node)
                await db.commit()
                # Render-barrier repair (ADR-096 §1): the failed step — and
                # every downstream morph the cascade just skipped — may sit in
                # the writer barrier of outputs this run already pended, and
                # a barrier naming a closed step blocks the render forever.
                # Prune the closed steps out of every PENDING output's
                # barrier and rebirth the mirrors, so each clip honestly
                # renders its surviving writers' spec with the failed node
                # red on the canvas. Best-effort: the repair must never mask
                # the failure.
                if run is not None:
                    try:
                        await repair_render_barriers(db, run)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        logger.warning(
                            "render_barrier_repair_failed",
                            node_id=str(node_id),
                            exc_info=True,
                        )
    finally:
        if run_id is not None:
            await maybe_finalize_run(run_id)


async def _cascade_skip(
    db: AsyncSession, failed_node: WorkflowStep, *, reason: str | None = None
) -> None:
    """Transitively mark downstream pending nodes as skipped.

    ``reason`` overrides the failure line — the interrupt bail cascade is a
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
            # ADR-079: a cascade-skipped RUNNING child may have a stale
            # executor still in flight — NULLing the token turns its terminal
            # write into a deterministic 0-row discard (not last-writer-wins).
            child.claim_token = None
            # Graph back-write (ADR-057 K2): a cascade-skipped child flips its
            # owning graph node's aggregate with it (no-op outside the graph).
            frontier.append(child.id)


async def resume_waiting_interrupt(
    db: AsyncSession, run: WorkflowRun, answer: dict
) -> ResumeOutcome:
    """answer = resume — under project-level execution-authority arbitration
    (I-EXEC-03/04, R1 B3). On a free authority: write the AnswerPayload dump
    into the waiting node's spec, flip it back to pending and the run back to
    RUNNING — the claim loop re-executes the node, whose spec.answer branch
    goes straight to done. The seat is the ``waiting`` status, any kind
    (direction interrupt, 期 3 verify escalation): each runner's own answer
    branch decides what the answer means.

    THE ONE arbitration seat: every resume channel (chat answer endpoint,
    chat autoResume, tool-loop disposition, expire sweep) funnels here, so
    the {PENDING, RUNNING} single-owner law is enforced at this second birth
    channel exactly like create_run's — project row lock (same pattern),
    then an atomic re-check. Lock order (D9): callers arrive holding at most
    a message row lock; the project lock is taken AFTER it here, and
    create_run never locks a message after its project lock — no cycle.

    Authority occupied → ``"blocked"``: zero state writes (the node stays
    waiting, the answer lives on the settled message row), and the caller
    speaks the parked line (再挂+明示). The next authority-freeing beat —
    the run-finalization handoff or the expire sweep's retry branch —
    re-attempts. Idempotent: no waiting node → ``"idle"``. Flush-only; the
    caller commits."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.status == "waiting",
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        return "idle"
    await db.execute(
        select(Project.id).where(Project.id == run.project_id).with_for_update()
    )
    decision = _resume_authority_decision(
        node_present=True,
        authority_free=not await has_active_run(
            db, run.project_id, exclude_run_id=run.id
        ),
    )
    if decision == "blocked":
        logger.info(
            "interrupt_resume_blocked", run_id=str(run.id), node_id=str(node.id)
        )
        return "blocked"
    node.spec = {**(node.spec or {}), "answer": answer}
    node.status = "pending"
    node.started_at = None
    # ADR-079: the resume re-pend is authority-losing — the next claim
    # re-mints (the park already NULLed; this is the explicit belt).
    node.claim_token = None
    if run.status == WorkflowStatus.WAITING_HUMAN:
        run.status = WorkflowStatus.RUNNING
    logger.info("interrupt_resumed", run_id=str(run.id), node_id=str(node.id))
    return "resumed"


async def _resume_parked_answered(db: AsyncSession, settled_run: WorkflowRun) -> None:
    """Authority handoff (I-EXEC-03/04, R1 B3): a terminal settle frees the
    project's execution authority — resume any same-project interrupt parked
    ANSWERED-but-blocked (再挂), with no user action. An unanswered park is
    the user's own pending decision, never auto-resumed here. Each candidate
    goes through the one arbitration seat (project row lock + atomic
    re-check), so at most one parked run takes the freed slot; the rest stay
    parked for the next handoff / sweep retry. Flush + one commit."""
    parked_runs = (
        (
            await db.execute(
                select(WorkflowRun).where(
                    WorkflowRun.project_id == settled_run.project_id,
                    WorkflowRun.status == WorkflowStatus.WAITING_HUMAN,
                    WorkflowRun.id != settled_run.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for parked in parked_runs:
        node = (
            await db.execute(
                select(WorkflowStep).where(
                    WorkflowStep.run_id == parked.id,
                    WorkflowStep.status == "waiting",
                )
            )
        ).scalar_one_or_none()
        if node is None:
            continue
        message_id = ((node.spec or {}).get("suspend_payload") or {}).get(
            "question_message_id"
        )
        if not message_id:
            continue
        message = await db.get(Message, UUID(str(message_id)))
        if message is None or message.answer is None:
            continue
        outcome = await resume_waiting_interrupt(db, parked, message.answer)
        if outcome == "resumed":
            logger.info(
                "authority_handoff_resumed",
                settled_run_id=str(settled_run.id),
                run_id=str(parked.id),
            )
    if parked_runs:
        await db.commit()


async def bail_waiting_interrupt(
    db: AsyncSession, run: WorkflowRun
) -> WorkflowStep | None:
    """Bail path (期 4): node done with ``spec.bailed`` + downstream cascade-
    skipped with the non-failure reason (#5). The run itself settles
    COMPLETED via maybe_finalize_run once the caller commits — the bailed
    node's summary line ("Bailed by user") is the user-abort note in
    the aggregated run summary. The seat is the ``waiting`` status, any kind
    (direction interrupt, 期 3 verify escalation). Idempotent like resume.
    Flush-only."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.run_id == run.id,
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
    logger.info("interrupt_bailed", run_id=str(run.id), node_id=str(node.id))
    return node


async def cancel_run(
    db: AsyncSession,
    run: WorkflowRun,
    project: Project,
) -> WorkflowRun:
    """Cancel an owned active Run using the existing step/render fences.

    The caller locks project then run. This transaction revokes every active
    claim and releases only the unconsumed hold; completed Outputs, previous
    deliveries and captures are deliberately left untouched. No completion or
    failure trigger is emitted for CANCELLED.
    """
    if run.status in {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }:
        return run

    nodes = list((
        await db.execute(
            select(WorkflowStep)
            .where(WorkflowStep.run_id == run.id)
            .with_for_update()
        )
    ).scalars().all())
    output_ids = {
        UUID(str(output_id))
        for node in nodes
        for output_id in [
            *(node.output_refs or []),
            *((node.spec or {}).get("output_id"),),
        ]
        if output_id
    }
    now = datetime.now(UTC)
    for node in nodes:
        if node.status in {"pending", "running", "waiting"}:
            node.status = "cancelled"
            node.claim_token = None
            node.finished_at = now
            node.updated_at = now

    outputs = list((
        await db.execute(select(Output).where(Output.id.in_(output_ids)).with_for_update())
    ).scalars().all()) if output_ids else []
    any_landed = any(output_is_delivered(output) for output in outputs)
    for output in outputs:
        if output.render_status in {RenderStatus.PENDING, RenderStatus.RENDERING}:
            output.render_status = RenderStatus.CANCELLED
            output.render_claim_token = None

    # A cancelled direction checkpoint must not rebuild as a pending dock on
    # refresh. It settles through the existing answer payload, not a new UI
    # control or message model.
    pending_questions = list((
        await db.execute(
            select(Message).where(
                Message.workflow_run_id == run.id,
                Message.role == "assistant",
                Message.question.is_not(None),
                Message.answer.is_(None),
            )
        )
    ).scalars().all())
    for message in pending_questions:
        message.answer = AnswerPayload(
            kind="bail", text="cancelled", answered_at=now
        ).model_dump(mode="json")

    run.status = WorkflowStatus.CANCELLED
    run.error = None
    run.updated_at = now
    settled = sum(
        node.status in {"done", "failed", "skipped", "cancelled"} for node in nodes
    )
    run.progress = int(settled / len(nodes) * 100) if nodes else 100
    project.status = ProjectStatus.REVIEW if any_landed else ProjectStatus.DRAFT
    project.updated_at = now
    await release_run(db, user_id=project.user_id, run_id=run.id)
    await db.commit()
    logger.info("run_cancelled", run_id=str(run.id), project_id=str(project.id))
    return run


async def _release_orphaned_hold(db: AsyncSession, run_id: UUID) -> None:
    """Settle a hold whose run (or project) row is already gone — orphan-hold
    recovery (BILLING §8 known boundary → 支付批前落地).

    The ledger is append-only and its hold rows carry the owner, so the
    remainder (release_run recomputes hold − releases from the ledger,
    clamped at 0) can be returned without any run/project row. Idempotent:
    the release idem key dedupes against a prior settlement. No hold row →
    nothing was ever frozen → nothing to do.
    """
    holder = (
        await db.execute(
            select(CreditTransaction.user_id)
            .where(
                CreditTransaction.kind == "hold",
                CreditTransaction.ref["run_id"].astext == str(run_id),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if holder is None:
        logger.warning("credits_release_skipped_no_hold", run_id=str(run_id))
        return
    await release_run(db, user_id=holder, run_id=run_id)
    await db.commit()


async def maybe_finalize_run(run_id: UUID) -> None:
    """Settle a run once no node is active — render fan-out included.

    Render nodes HOLD the run open (2026-09-13 ADR-074② 翻案): the run's end
    is the receipt / closing-line tombstone (ADR-073②), so it must wait for
    the last render — the retired orchestration's inheritance ("renders
    continue after the run completes") let「做好了」land mid-render. Render
    mirrors settle through the render chain (D2: ``outputs.render_status``
    owns their lifecycle), so ``render_output`` re-invokes this finalizer
    when a render lands. Failed renders fail the run; partial delivery is
    determined by usable outputs, not merely successful producer steps.
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(
            WorkflowRun, run_id, with_for_update=True
        )
        if run is None:
            # Orphan-hold recovery (BILLING §8): the run row was deleted
            # mid-flight (project deletion cascades it) while this finalize
            # raced behind it. The ledger outlives the run — settle the
            # hold's remainder from it instead of freezing it forever.
            await _release_orphaned_hold(db, run_id)
            return
        if run.status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
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
            # waiting counts as active: a interrupt parked for a human answer
            # must never let the run settle (期 4). Render fan-out steps count
            # too (ADR-074② 翻案 — the run ends when the last render lands).
            if n.status in ("pending", "running", "waiting")
        ]
        if active:
            await db.commit()
            return

        # Render-ownership reconcile (ADR-096 §4, 双职责之二): outputs this
        # run birthed whose render fell through every request seat (a crash
        # window, a pre-terminal-law legacy hole) are re-pended HERE, before
        # the verdict — the run stays open on the fresh render steps and
        # settles when they land (the render chain's _finalize_owning_run
        # re-invokes this finalizer). Idempotent by predicate; a repair
        # mechanism only — the normal paths (birth fan-out, morph touch,
        # failure repair) self-serve their pends.
        reconciled = await reconcile_orphaned_renders(db, run)
        if reconciled:
            await db.commit()
            return

        # Render/upload failures are delivery failures, including fan-out.
        failed_verdict = [n for n in nodes if n.status == "failed"]
        output_ids = {UUID(str(oid)) for n in nodes for oid in (n.output_refs or [])}
        outputs = list((await db.execute(
            select(Output).where(Output.id.in_(output_ids))
        )).scalars().all()) if output_ids else []
        delivered = [o for o in outputs if output_is_delivered(o)]
        any_landed = bool(delivered)
        # A completed producer with no usable rendered file must not receive
        # a green receipt, even when a render mirror is missing/corrupt.
        missing_delivery = len(delivered) < len(output_ids)
        project = await db.get(Project, run.project_id)

        # A narration-only Run succeeds on fixed audio + alignment + settled
        # usage, never on a fabricated Output. Other zero-Output Runs keep
        # the ordinary verdict unchanged.
        narration_error = None
        if not failed_verdict:
            from app.tools.video.production.narration import (
                has_narration_preparation_scope,
                narration_preparation_fact,
            )

            if has_narration_preparation_scope(run):
                try:
                    await narration_preparation_fact(db, run, nodes)
                except ValueError as exc:
                    narration_error = str(exc)

        if failed_verdict or missing_delivery or narration_error:
            run.status = WorkflowStatus.FAILED
            run.error = (
                (failed_verdict[0].error if failed_verdict else None)
                or narration_error
                or next((o.render_error for o in outputs if o.render_error), None)
                or user_line("delivery_missing", (project.language if project else None) or "en")
            )
            # Failed runs must NOT leave the project stuck in PROCESSING
            # (the frontend hides destructive ops while it's "live" — a run
            # that won't recover keeps the user from deleting or retrying,
            # and there's no auto-recovery path: the worker either restarts
            # and resumes the PENDING node, or it doesn't). A PARTIAL failure
            # (products landed — their cards are on the canvas) drops to
            # REVIEW so the results world opens on what landed; a total
            # failure drops back to DRAFT so the user can either retry (a new
            # message) or clean up (delete) — the failed run stays in the run
            # row for history.
            if project is not None and project.status == ProjectStatus.PROCESSING:
                project.status = (
                    ProjectStatus.REVIEW if any_landed else ProjectStatus.DRAFT
                )
                project.updated_at = datetime.now(UTC)
        else:
            run.status = WorkflowStatus.COMPLETED
            run.error = None
            if project is not None:
                project.status = ProjectStatus.REVIEW
                project.updated_at = datetime.now(UTC)
        run.progress = 100
        # Release the unconsumed reservation. Successful steps retain their
        # actual charges even when another step failed; failed steps have no
        # capture. A missing project settles from the ledger (its
        # hold rows carry the owner), never skipped (orphan hold, BILLING §8).
        if project is not None:
            await release_run(db, user_id=project.user_id, run_id=run.id)
        else:
            await _release_orphaned_hold(db, run_id)
        await db.commit()
        logger.info(
            "run_finalized",
            run_id=str(run_id),
            status=run.status.value,
            nodes=total,
        )
        # Authority handoff (R1 B3): the settle freed this project's execution
        # authority — a same-project interrupt parked answered-but-blocked
        # (再挂) resumes now, no user action. Best-effort: the expire sweep's
        # retry branch is the backstop if this fires mid-crash.
        try:
            await _resume_parked_answered(db, run)
        except Exception:  # noqa: BLE001 — finalization never dies on it
            logger.warning(
                "authority_handoff_failed", run_id=str(run_id), exc_info=True
            )
        # 触发回合 (T3, ADR-077 判词③): run 终态按判决分两族白名单事件——
        # 成功或有产物落地的部分失败 → run_completed 收官评审 (旅程一⑦,
        # fire gate = ADR-074② 判决真值);全灭 (FAILED 且零落地) →
        # run_failed 失败通报 (ADR-135: 收据自证不了失败原因,也给不出下
        # 一步——开口是唯一诚实面,沉默即失联)。两族互斥,按 run id 各自
        # 去重。This line runs once per terminal transition (an
        # already-terminal run early-returns above). Fire-and-forget —
        # finalization never waits on the agent's speech. (Seam:
        # app.pipeline.trigger_events, ADR-087 §6.)
        if project is not None and (
            run.status == WorkflowStatus.COMPLETED or any_landed
        ):
            fire_trigger(
                UUID(str(project.id)),
                TRIGGER_RUN_COMPLETED,
                run_trigger_ref(run_id, TRIGGER_RUN_COMPLETED, run.context),
            )
        elif project is not None and run.status == WorkflowStatus.FAILED:
            fire_trigger(
                UUID(str(project.id)),
                TRIGGER_RUN_FAILED,
                run_trigger_ref(run_id, TRIGGER_RUN_FAILED, run.context),
            )


async def expire_stale_interrupts(older_than: timedelta | None = None) -> int:
    """Auto-answer long-parked waiting nodes (direction interrupt, 期 3 verify
    escalation, 期 4 hook gate — any kind parks on the ``waiting`` seat) with
    their default option.

    Expiry semantics = the review tier degrades to best-judgment completion
    after the TTL (the leave-note promise: 离开不中断) — never a bail, never
    a permanent park. The answer carries the machine marker
    ``answer.text="expired"`` (same pattern as ``superseded``); the default
    option has no argument id, so plan injects no direction —
    exactly the auto-tier behavior. The message UPDATE is guarded by
    ``answer IS NULL``: a user answer racing the sweep always wins.

    Expire ≠ TTL resume (R1 B3): settling the answer and regaining execution
    authority are two acts. The resume attempt goes through the arbitration
    seat (``resume_waiting_interrupt``) — while another run holds the
    project's {PENDING, RUNNING} slot the expired node stays parked
    (answered-but-blocked), and every later sweep tick retries through the
    already-settled branch until the authority handoff lets it in. Returns
    the number of interrupts NEWLY expired (0 is the common, silent case;
    retries of already-settled parks don't count).
    """
    ttl = (
        older_than
        if older_than is not None
        else timedelta(seconds=settings.interrupt_expiry_seconds)
    )
    cutoff = datetime.now(UTC) - ttl
    expired = 0
    async with AsyncSessionLocal() as db:
        nodes = list(
            (
                await db.execute(
                    select(WorkflowStep).where(
                        # The waiting seat, ANY kind (direction interrupt, 期 3
                        # verify escalation, 期 4 hook gate) — a kind filter
                        # would park non-interrupt kinds past their TTL,
                        # breaking 离开不中断.
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
                    "interrupt_expiry_skipped_corrupt_payload", node_id=str(node.id)
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
            if settled_id is not None:
                expired += 1
                logger.info(
                    "interrupt_expired", node_id=str(node.id), run_id=str(node.run_id)
                )
                settled_answer = answer
            else:
                # Already settled — the user beat the sweep, OR a previous
                # tick settled the default but parked blocked (authority
                # held, R1 B3). Expire ≠ TTL resume: expiry settles the
                # answer, then the arbitration seat ATTEMPTS to regain
                # execution authority. Blocked → the node stays parked and
                # the next sweep tick retries through this same branch (the
                # settled answer is re-read from the message row — the
                # user's answer always wins, it is never re-settled).
                message = await db.get(Message, UUID(str(message_id)))
                if message is None or message.answer is None:
                    continue
                settled_answer = message.answer
            run = await db.get(WorkflowRun, node.run_id)
            if run is not None:
                await resume_waiting_interrupt(db, run, settled_answer)
            await db.commit()
    return expired


async def finalize_stuck_runs() -> None:
    """Finalize RUNNING runs whose nodes are all settled (crash recovery).

    Render steps hold the run open here too (ADR-074② 翻案): the startup
    reap just re-pended orphaned renders, so a crashed mid-render run must
    survive this sweep and settle when the re-run lands.

    Case law in raw SQL: workflow_runs.status is a native enum storing the
    enum NAME ('RUNNING' — same convention as jobs.py's run claim), while
    workflow_steps.status is a lowercase varchar. A lowercase 'running'
    here is a startup-killing parse error (one slipped in with a WIP edit
    on 2026-09-06 and no worker could boot until restored).
    """
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
                      )
                    """
                )
            )
        ).scalars().all()
    for rid in run_ids:
        await maybe_finalize_run(rid)


# ---- startup self-check (AGENT_ARCH §10) ------------------------------------


def assert_runners_registered() -> None:
    """Fail boot if either authorized task lost its concrete DAG executor."""
    for name, entry in TOOL_REGISTRY.items():
        if not entry.seat and name not in NODE_KINDS:
            raise RuntimeError(f"Tool '{name}': no node registered under that name")
    for kind in ("produce_video", "prepare_narration"):
        if kind not in NODE_KINDS:
            raise RuntimeError(f"Missing production executor: {kind}")
