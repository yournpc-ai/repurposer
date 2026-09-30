"""Render ownership (ADR-096 §1) — compile-static owner + writer barrier.

The terminal law: every output's render owner is a COMPILE-TIME fact — the
compile-last writer of its render_spec (usually the assembly station when no
morph follows). The runtime never arbitrates ownership: it only executes and
verifies.

Three mechanical pieces carry it:

- :func:`writer_steps_for_output` — the pure fold naming one output's writer
  steps from the run's compiled step list (birth step + every non-fork
  in-place morph whose scope covers the row). Seq-ordered; the last entry is
  the render owner. Statically enumerable because the compiled topology is
  fixed at ``create_run``.
- ``outputs.render_barrier`` — the fold's stamp on the output row, written
  by :func:`pend_outputs_for_render` (the ONE render-request seat) at every
  run-scoped pend. The render claim gate
  (``jobs.claim_pending_render``) fires only when every barrier step is done
  — the parallel-writers race (the black-card incident, ADR-096 Context) is
  structurally dead: a render always reads the full final spec.
- :func:`repair_render_barriers` — the named failure-repair path: a failed
  or cascade-skipped writer can never let a partial spec render as an
  apparently-complete product, so its step stays in the barrier (blocking
  the render) until this seat prunes it and rebirths the mirror — the
  product then honestly renders the surviving writers' spec with the failed
  node red on the canvas.

The render mirror step (ADR-074② 台账律: every pend carries a mirror so the
run's finalization sees it) is born here too, parented on the writer set —
the failure cascade skips it when any writer fails, which IS the owner
block.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import RenderStatus
from app.models.tables import Output, Project, WorkflowRun, WorkflowStep

logger = structlog.get_logger()

# Modifier kinds that rewrite a clip's render_spec IN PLACE (their fork
# variants derive new rows and never appear in another row's writer set).
INPLACE_MORPH_KINDS = (
    "translate_clip",
    "dub_clip",
    "remove_filler",
    "add_music",
    "reframe_clip",
)

# Clip-birthing kinds (the assembly stations). A morph with one of these in
# its inputs targets THAT producer's output_refs; a morph without any falls
# back to the project's pre-existing clips (the existing profile).
CLIPS_PRODUCER_KINDS = ("select_clips", "materialize_source", "cut_segments")

# Step statuses whose writers must be pruned out of a render barrier by the
# repair seat: a failed writer's spec writes rolled back, and a cascade-
# skipped writer never wrote — neither may block the survivors' render.
CLOSED_STEP_STATUSES = ("failed", "skipped")


@dataclass(frozen=True)
class StepView:
    """The fold's read-only step facts (adapter over WorkflowStep rows; pure
    tests construct these directly)."""

    id: str
    kind: str
    seq: int
    inputs: tuple[str, ...]
    fork: bool
    target_output_id: str | None


def step_view_of(step: WorkflowStep) -> StepView:
    spec = step.spec or {}
    return StepView(
        id=str(step.id),
        kind=step.kind,
        seq=int(step.seq),
        inputs=tuple(str(i) for i in (step.inputs or [])),
        fork=bool(spec.get("fork")),
        target_output_id=str(spec["target_output_id"]) if spec.get("target_output_id") else None,
    )


def writer_steps_for_output(
    steps: Iterable[StepView],
    *,
    birth_step_id: str | None,
    output_id: str,
) -> list[str]:
    """One output's compile-static writer set, seq-ordered (last = owner).

    Run-born row (its birth step sits in THIS run's compiled steps): the
    birth step plus every non-fork in-place morph holding the birth step in
    its inputs. Target-scoped morphs never cover run-born rows (the row was
    unborn when the scope was pinned) and fork morphs derive their own rows
    (they are the birth step of their derived rows, never a writer of the
    base row).

    Pre-existing row (a legacy/earlier-run row the current run's morphs act
    on): every non-fork in-place morph whose scope can cover it — an
    existing-profile morph (no clips producer in its inputs) targets the
    project's pre-existing clips, so it covers every such row; a
    target-scoped morph covers exactly its named row. Morphs wired off a
    clips producer target only that producer's run-born rows and never
    cover pre-existing ones.

    Over-inclusion is deliberate and safe: a morph that ends up SKIPPING the
    row still completes, lifting its barrier slot. Under-inclusion is the
    only real error (an early render reading a partial spec) — the fold
    always errs wide.
    """
    by_id = {s.id: s for s in steps}
    morphs = [
        s for s in by_id.values() if s.kind in INPLACE_MORPH_KINDS and not s.fork
    ]
    writers: set[str] = set()
    if birth_step_id is not None and birth_step_id in by_id:
        writers.add(birth_step_id)
        for m in morphs:
            if m.target_output_id:
                continue
            if birth_step_id in m.inputs:
                writers.add(m.id)
    else:
        for m in morphs:
            if m.target_output_id:
                if m.target_output_id == output_id:
                    writers.add(m.id)
                continue
            has_producer = any(
                (up := by_id.get(up_id)) is not None and up.kind in CLIPS_PRODUCER_KINDS
                for up_id in m.inputs
            )
            if not has_producer:
                writers.add(m.id)
    return sorted(writers, key=lambda sid: by_id[sid].seq)


def prune_writer_barrier(
    barrier: Iterable[str], closed_step_ids: Iterable[str]
) -> list[str]:
    """The repair fold: drop closed (failed/skipped) writers from a barrier.

    Order preserved; the survivors' completion is what the pruned render
    waits on. A barrier that empties lifts immediately (every writer the
    chain could still hear from is already settled)."""
    closed = set(closed_step_ids)
    return [sid for sid in barrier if sid not in closed]


async def render_step_label(db: AsyncSession, run: WorkflowRun) -> str | None:
    """The runtime-born render step's builder-written task name (same label()
    source as compile-time nodes), localized to the run's pinned UI locale."""
    from app.pipeline.graph import NODE_KINDS  # deferred: import cycle
    from app.pipeline.step_display import ui_lang_of

    project = await db.get(Project, run.project_id)
    render_cls = NODE_KINDS.get("render")
    if project is None or render_cls is None:
        return None
    return render_cls.label(None, ui_lang_of(run, project))


async def _load_step_views(db: AsyncSession, run_id: UUID) -> list[StepView]:
    steps = list(
        (
            await db.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    return [step_view_of(s) for s in steps]


async def pend_outputs_for_render(
    db: AsyncSession,
    run: WorkflowRun,
    outputs: Iterable[Output],
    *,
    barriers: dict[UUID, list[str]] | None = None,
) -> None:
    """The ONE render-request seat (ADR-096 §1): pend + barrier stamp + mirror.

    For every output: supersede still-pending sibling mirrors (ANY run — one
    live render request per output), flip ``render_status`` to PENDING with
    the claim token NULLed and the attempt budget reset (intent re-pend = new
    budget, R1 B4a), stamp ``render_barrier`` with the compile-static writer
    set (or the caller's explicit override — the failure-repair/reconcile
    seats pass pruned sets), and birth ONE render mirror step whose inputs
    are the barrier (the last writer owns the render; the failure cascade
    skips the mirror when any writer fails — the owner block).

    ``run`` is the run the mirrors belong to AND whose compiled steps feed
    the fold — for a post-run edit it is the output's BIRTH run (a terminal
    run's barrier steps are all done, so the render fires immediately).
    """
    outputs = list(outputs)
    if not outputs:
        return
    views = await _load_step_views(db, run.id)
    computed: dict[UUID, list[str]] = {}
    for o in outputs:
        if barriers is not None:
            computed[o.id] = list(barriers.get(o.id) or [])
        else:
            computed[o.id] = writer_steps_for_output(
                views,
                birth_step_id=str(o.workflow_step_id) if o.workflow_step_id else None,
                output_id=str(o.id),
            )
    id_strs = [str(o.id) for o in outputs]
    await db.execute(
        delete(WorkflowStep).where(
            WorkflowStep.kind == "render",
            WorkflowStep.status == "pending",
            WorkflowStep.spec["output_id"].astext.in_(id_strs),
        )
    )
    for o in outputs:
        await db.execute(
            update(Output)
            .where(Output.id == o.id)
            .values(
                render_status=RenderStatus.PENDING,
                render_claim_token=None,
                render_error=None,
                render_attempt=0,
                render_barrier=computed[o.id],
            )
        )
    max_seq = int(
        (
            await db.execute(
                select(func.max(WorkflowStep.seq)).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        or 0
    )
    label = await render_step_label(db, run)
    for idx, o in enumerate(outputs, start=1):
        db.add(
            WorkflowStep(
                run_id=run.id,
                kind="render",
                status="pending",
                seq=max_seq + idx,
                inputs=computed[o.id],
                spec={"output_id": str(o.id), **({"summary": label} if label else {})},
            )
        )
    await db.flush()


async def repair_render_barriers(db: AsyncSession, run: WorkflowRun) -> int:
    """The named failure-repair path (ADR-096 §1): prune closed writers.

    After a step failure (and its downstream cascade-skip), any PENDING
    output whose render barrier still names a failed/skipped step of this
    run would wait forever — the failed writer's spec writes rolled back, so
    the surviving writers' spec is the honest deliverable. Restamp those
    rows with the pruned barrier and rebirth their mirrors (the cascade
    skipped the old ones — they stay as the ledger of the blocked attempt).
    Idempotent: a barrier with no closed steps is left untouched. Returns
    the healed-row count.
    """
    statuses = dict(
        (
            await db.execute(
                select(WorkflowStep.id, WorkflowStep.status).where(
                    WorkflowStep.run_id == run.id,
                    WorkflowStep.status.in_(CLOSED_STEP_STATUSES),
                )
            )
        ).all()
    )
    closed = {str(sid) for sid in statuses}
    if not closed:
        return 0
    rows = list(
        (
            await db.execute(
                select(Output).where(
                    Output.render_status == RenderStatus.PENDING,
                    Output.render_barrier.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    heal: dict[UUID, list[str]] = {}
    healed_outputs: list[Output] = []
    for o in rows:
        barrier = [str(s) for s in (o.render_barrier or [])]
        if not closed & set(barrier):
            continue
        pruned = prune_writer_barrier(barrier, closed)
        heal[o.id] = pruned
        healed_outputs.append(o)
    if not healed_outputs:
        return 0
    await pend_outputs_for_render(db, run, healed_outputs, barriers=heal)
    logger.info(
        "render_barriers_repaired", run_id=str(run.id), count=len(healed_outputs)
    )
    return len(healed_outputs)


def needs_render_reconcile(
    *,
    has_render_spec: bool,
    render_status: str | None,
    archived: bool,
    has_pending_render_step: bool,
) -> bool:
    """The finalize-reconcile predicate (ADR-096 §4): an output born in the
    run is render-orphaned when it carries a render contract, the render was
    never requested (render_status NULL), it is not archived (the claim gate
    never picks archived rows — re-pending one would pend a render no worker
    ever claims, holding the run open forever), and no pending render step
    (any run) still owns its render."""
    return (
        has_render_spec
        and render_status is None
        and not archived
        and not has_pending_render_step
    )


async def reconcile_orphaned_renders(db: AsyncSession, run: WorkflowRun) -> list[UUID]:
    """Run-finalize reconcile (ADR-096 §4, the readiness law's second seat):
    re-pend THIS run's render-orphaned outputs through the one pend seat.

    A repair mechanism, never a normal-path dependency: morph runners and
    the failure repair own their re-pends; this scans only what fell through
    (a crash window, a pre-terminal-law legacy hole). Idempotent by
    predicate — the first pass flips rows to PENDING, so a repeat finalize
    matches nothing. Scope is this run's born outputs only — a blanket sweep
    of historical projects would mass-resurrect old renders (billing blast).

    The barrier is the pruned writer set (at finalize every step is settled;
    failed/skipped writers must not block the rescue render).
    """
    birth_steps = select(WorkflowStep.id).where(WorkflowStep.run_id == run.id)
    rows = list(
        (
            await db.execute(
                select(Output).where(
                    Output.workflow_step_id.in_(birth_steps),
                    Output.render_spec.isnot(None),
                    Output.render_status.is_(None),
                    Output.archived_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    pending_rendered = set(
        (
            await db.execute(
                select(WorkflowStep.spec["output_id"].astext).where(
                    WorkflowStep.kind == "render",
                    WorkflowStep.status == "pending",
                    WorkflowStep.spec["output_id"].astext.in_(
                        [str(o.id) for o in rows]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    orphans = [
        o
        for o in rows
        if needs_render_reconcile(
            has_render_spec=True,
            render_status=None,
            archived=False,
            has_pending_render_step=str(o.id) in pending_rendered,
        )
    ]
    if not orphans:
        return []
    views = await _load_step_views(db, run.id)
    closed = {
        str(sid)
        for (sid, _st) in (
            await db.execute(
                select(WorkflowStep.id, WorkflowStep.status).where(
                    WorkflowStep.run_id == run.id,
                    WorkflowStep.status.in_(CLOSED_STEP_STATUSES),
                )
            ).all()
        )
    }
    barriers: dict[UUID, list[str]] = {}
    for o in orphans:
        barrier = writer_steps_for_output(
            views,
            birth_step_id=str(o.workflow_step_id) if o.workflow_step_id else None,
            output_id=str(o.id),
        )
        barriers[o.id] = prune_writer_barrier(barrier, closed)
    await pend_outputs_for_render(db, run, orphans, barriers=barriers)
    healed = [o.id for o in orphans]
    logger.info(
        "render_orphans_reconciled", run_id=str(run.id), count=len(healed)
    )
    return healed
