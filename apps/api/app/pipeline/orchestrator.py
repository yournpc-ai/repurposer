"""Cancellation and settlement of outstanding Run records."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AnswerPayload,
    ProjectStatus,
    RenderStatus,
    WorkflowStatus,
)
from app.models.tables import CreditTransaction, Message, Output, WorkflowStep, Project, WorkflowRun
# Graph fill/back-write (ADR-057 K2) — top-level is cycle-free: graph_fill's
# module-level chain (graph / graph_store / outputs / billing) never points
# back here; its own import of THIS module stays function-level inside
# stamp_draft_graph.
from app.pipeline.errors import user_line
from app.pipeline.run_review import output_is_delivered
from app.pipeline.render_ownership import (
    reconcile_orphaned_renders,
)
# Graph fill/back-write (ADR-057 K2) — top-level is cycle-free: graph_fill's
# module-level chain (graph / graph_store / outputs / billing) never points
# back here; its own import of THIS module stays function-level inside
# stamp_draft_graph.
from app.pipeline.trigger_events import (
    TRIGGER_RUN_COMPLETED,
    TRIGGER_RUN_FAILED,
    fire_trigger,
    run_trigger_ref,
)
from app.platform.billing import (
    release_run,
)

logger = structlog.get_logger()

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

    journey = (run.context or {}).get("media_journey")
    if journey:
        # The active plan and its Run were persisted together. Settle that
        # same transcript marker atomically with cancellation for live/replay.
        plan = await db.scalar(select(Message).where(
            Message.workflow_run_id == run.id,
            Message.intent["media_journey"]["opening_id"].as_string() == journey["opening_id"],
            Message.intent["media_journey"]["state"].as_string() == "active",
        ).order_by(Message.seq.desc()).limit(1))
        if plan is not None:
            plan.intent = {**plan.intent, "media_journey": {**journey, "state": "stopped"}}
        run.context = {**run.context, "media_continuation_finished": True}

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

        # Output-free preparation succeeds only on fixed media, exact report
        # references and settled actual usage, never on a fabricated Output.
        preparation_error = None
        if not failed_verdict:
            from app.tools.video.production.narration import (
                has_narration_preparation_scope,
                narration_preparation_facts,
            )
            from app.tools.video.production.visual_assets import (
                has_visual_asset_preparation_scope,
                visual_asset_preparation_fact,
            )
            from app.tools.video.music_preparation import (
                has_music_preparation_scope,
                music_preparation_fact,
            )

            try:
                if has_narration_preparation_scope(run):
                    await narration_preparation_facts(db, run, nodes)
                if has_visual_asset_preparation_scope(run):
                    await visual_asset_preparation_fact(db, run, nodes)
                if has_music_preparation_scope(run):
                    await music_preparation_fact(db, run, nodes)
            except ValueError as exc:
                preparation_error = str(exc)

        if failed_verdict or missing_delivery or preparation_error:
            run.status = WorkflowStatus.FAILED
            run.error = (
                (failed_verdict[0].error if failed_verdict else None)
                or preparation_error
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
