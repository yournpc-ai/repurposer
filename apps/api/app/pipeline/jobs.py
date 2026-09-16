"""Postgres-backed job queue primitives.

The database *is* the queue: pending work lives as rows (``Asset`` rows awaiting
processing, ``workflow_steps`` awaiting execution, ``outputs`` awaiting render).
Workers claim a row with ``SELECT ... FOR UPDATE SKIP LOCKED``, which lets
multiple workers run concurrently without ever grabbing the same row.
No Redis/broker required.

The claim helpers atomically flip a row out of its pending state before
returning it, so a claimed row is invisible to other workers' claim queries.
``reap_stale`` recovers rows orphaned by a crashed worker (left mid-flight in a
running state): at startup with no threshold (the historical full sweep), and
from every tick with an age threshold (nodes only — see the docstring).

To scale horizontally later, only the claim mechanism here changes (e.g. swap
to arq/Celery + Redis); callers stay the same.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import CursorResult, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.schemas import AssetStatus, RenderStatus
from app.models.tables import Asset, Output, Project, WorkflowStep
from app.pipeline.errors import user_line
from app.pipeline.graph import runtime_fanout_kinds
from app.ui_locale import display_language

logger = structlog.get_logger()


def _attempt_cap_decision(attempt: int, cap: int) -> Literal["claim", "terminal"]:
    """The poison-pill boundary (R1 B4a), pure so the matrix is test-covered:
    ``attempt == cap`` is still claimable (one last execution — total
    executions = cap + 1, matching the NodeBase.retries magnitude), and
    ``attempt > cap`` settles the FAILED terminal instead of re-entering the
    crash loop."""
    return "terminal" if attempt > cap else "claim"


def reset_asset_processing(asset: Asset) -> None:
    """THE manual-reprocess reset seat (R1 B4a — 复位+清零一体): status,
    counter, and error move as ONE write-set. A status-only flip would hand
    the claim loop a row whose counter is still over the cap — it would
    terminally fail again on the next tick (假重开)."""
    asset.processing_status = AssetStatus.PENDING
    asset.processing_error = None
    asset.attempt = 0


def reset_output_render(output: Output) -> None:
    """Same one-seat reset for renders (R1 B4a): status + token + error +
    counter. The manual render endpoint calls this; intent-driven re-pends
    (morph / verify / undo-redo / tool re-render) reset the counter at their
    own seats — new intent = new budget; only the crash reap keeps counting.
    """
    output.render_status = RenderStatus.PENDING
    output.render_claim_token = None
    output.render_error = None
    output.render_attempt = 0


def _runtime_fanout_sql() -> str:
    """Fan-out kinds (render, D2) as a SQL literal list — node-declared
    (`runtime_fanout`), consumed kernel-wide. Built lazily: this module is
    imported before the registry door opens, so a module-level constant would
    freeze an empty set. Values are code constants, never user input."""
    return ", ".join(f"'{k}'" for k in sorted(runtime_fanout_kinds()))


async def claim_pending_asset(db: AsyncSession) -> UUID | None:
    """Atomically claim one pending asset, flipping it to PROCESSING.

    Returns the claimed asset id, or None if no asset is pending. Uses
    ``FOR UPDATE SKIP LOCKED`` so concurrent workers never claim the same row.

    Poison-pill guard (R1 B4a): the claim counts the row (``attempt + 1``);
    a head row already over ``settings.asset_max_attempts`` settles FAILED
    with the honest localized line instead of re-entering the crash loop,
    and the loop moves to the next row.
    """
    while True:
        row = (
            await db.execute(
                select(Asset)
                .where(Asset.processing_status == AssetStatus.PENDING)
                .order_by(Asset.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        if _attempt_cap_decision(row.attempt, settings.asset_max_attempts) == "terminal":
            project = (
                await db.get(Project, row.project_id)
                if row.project_id is not None
                else None
            )
            lang = display_language(None, project.language if project else None)
            await db.execute(
                update(Asset)
                .where(Asset.id == row.id)
                .values(
                    processing_status=AssetStatus.FAILED,
                    processing_error=user_line("processing_gave_up", lang),
                )
            )
            await db.commit()
            logger.warning(
                "asset_attempt_cap_terminal",
                asset_id=str(row.id),
                attempt=row.attempt,
            )
            continue

        asset_id = await db.scalar(
            update(Asset)
            .where(Asset.id == row.id)
            .values(
                processing_status=AssetStatus.PROCESSING,
                processing_error=None,
                attempt=Asset.attempt + 1,
            )
            .returning(Asset.id)
        )
        await db.commit()
        return asset_id


async def claim_ready_node(db: AsyncSession) -> UUID | None:
    """Atomically claim one ready workflow step, flipping it to ``running``.

    A node is ready when it is pending and every upstream node (its ``inputs``
    edge list) is done. Render nodes are excluded — they are claimed through
    ``outputs.render_status`` (D2: the render chain owns their lifecycle).
    Runs whose project still has assets being processed are gated off, exactly
    like the retired run-level claim.

    Single UPDATE...RETURNING statement, so the claim is atomic under
    concurrent workers. Also flips the owning run PENDING -> RUNNING.
    The claim mints the row's fencing token (``claim_token``, ADR-079) —
    ``execute_step``'s terminal writes predicate on it.
    """
    node_id = (
        await db.execute(
            text(
                f"""
                UPDATE workflow_steps pn
                SET status = 'running',
                    started_at = now(),
                    attempt = attempt + 1,
                    claim_token = gen_random_uuid(),
                    updated_at = now()
                WHERE pn.id = (
                    SELECT pn2.id
                    FROM workflow_steps pn2
                    JOIN workflow_runs r ON r.id = pn2.run_id
                    WHERE pn2.status = 'pending'
                      AND pn2.kind NOT IN ({_runtime_fanout_sql()})
                      AND NOT EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements_text(pn2.inputs) AS up(id)
                        JOIN workflow_steps upn ON upn.id = up.id::uuid
                        WHERE upn.status <> 'done'
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM assets a
                        WHERE a.project_id = r.project_id
                          AND a.processing_status IN ('PENDING', 'PROCESSING')
                      )
                    ORDER BY pn2.seq, pn2.created_at
                    LIMIT 1
                    FOR UPDATE OF pn2 SKIP LOCKED
                )
                RETURNING pn.id
                """
            )
        )
    ).scalar_one_or_none()
    if node_id is None:
        return None

    await db.execute(
        text(
            "UPDATE workflow_runs SET status = 'RUNNING', updated_at = now() "
            "WHERE id = (SELECT run_id FROM workflow_steps WHERE id = :nid) "
            "AND status = 'PENDING'"
        ),
        {"nid": node_id},
    )
    # Graph back-write (ADR-057 K2) at the CLAIM seat: this UPDATE flips the
    # step pending → running before execute_step's session ever loads it, so
    # the orchestrator's own start-sync (its `status == "pending"` branch)
    # is unreachable for every worker-claimed step — the owning graph node
    # sat "queued" through the entire run (2026-09-13 走查实拍: 画布无 wipe、
    # 无边上 packet,节点显示 Queued 而步骤已跑 3 分钟+). Re-aggregate the
    # family here so the node flips to running atomically with the claim.
    # The sync is flush-only; this commit carries claim + flip together.
    step = await db.get(WorkflowStep, node_id)
    if step is not None:
        from app.pipeline.graph_fill import (  # deferred: registry-door order
            sync_graph_node_for_step,
        )

        await sync_graph_node_for_step(db, step)
    await db.commit()
    return node_id


async def claim_pending_render(db: AsyncSession) -> UUID | None:
    """Atomically claim one clip output awaiting render, flipping it to RENDERING.

    The claim mints the row's fencing token (``render_claim_token``, ADR-079)
    — the render chain's terminal writes predicate on it — and counts the row
    (``render_attempt + 1``, R1 B4a). A head row already over
    ``settings.render_max_attempts`` settles FAILED with the honest localized
    line — AND mirrors its fan-out node failed + finalizes the owning run, or
    the node would sit pending forever and the run would never settle — then
    the loop moves to the next row.
    """
    while True:
        row = (
            await db.execute(
                select(Output)
                .where(Output.type == "clip")
                .where(Output.render_status == RenderStatus.PENDING)
                .order_by(Output.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        if _attempt_cap_decision(row.render_attempt, settings.render_max_attempts) == "terminal":
            project = await db.get(Project, row.project_id)
            lang = display_language(None, project.language if project else None)
            line = user_line("render_gave_up", lang)
            await db.execute(
                update(Output)
                .where(Output.id == row.id)
                .values(render_status=RenderStatus.FAILED, render_error=line)
            )
            await db.commit()
            logger.warning(
                "render_attempt_cap_terminal",
                output_id=str(row.id),
                attempt=row.render_attempt,
            )
            from app.pipeline.rendering import (  # deferred: own sessions
                _finalize_owning_run,
                _mirror_render_node,
            )

            await _mirror_render_node(row.id, "failed", line)
            await _finalize_owning_run(row.id)
            continue

        output_id = await db.scalar(
            update(Output)
            .where(Output.id == row.id)
            .values(
                render_status=RenderStatus.RENDERING,
                render_error=None,
                render_claim_token=func.gen_random_uuid(),
                render_attempt=Output.render_attempt + 1,
            )
            .returning(Output.id)
        )
        # Mirror the fan-out node (if any) to running.
        await db.execute(
            text(
                f"UPDATE workflow_steps SET status = 'running', started_at = now(), "
                "updated_at = now() "
                f"WHERE kind IN ({_runtime_fanout_sql()}) AND status = 'pending' "
                "AND spec->>'output_id' = :oid"
            ),
            {"oid": str(output_id)},
        )
        await db.commit()
        return output_id


# Age threshold for the periodic (per-tick) node reap, in seconds
# (chat-flow-sequencing D2): healthy LLM nodes finish ≤ ~180s (the provider
# client bounds every call at 120–180s), so 900s is a wide lane — a node
# older than this is orphaned by a dead event loop, not working.
STALE_NODE_REAP_SECONDS = 900.0


async def reap_stale(db: AsyncSession) -> None:
    """Startup full sweep: reset rows orphaned by a crashed worker.

    Every in-flight row is a crash leftover — the single-worker dev
    assumption. That assumption has a documented hazard: a stale ORPHAN
    worker process (same dev box, days-old code) can still hold rows it
    will never finish; the startup sweep of the LIVE worker then resets
    those rows to pending, which is the wanted rescue — but under that
    same single-instance assumption a startup sweep on a second live
    worker would reset its healthy in-flight rows too. Age-based reaping
    (``reap_stale_nodes_older_than``, the worker's every-tick sweep) is
    immune to that, which is one reason the periodic sweep exists.

    Poison-pill termination (R1 B4a — the old TODO, resolved): an orphaned
    row whose claim count is already over the cap does NOT re-pend — it
    settles FAILED with the honest localized line, ending the crash loop.
    The reap never resets the counter: that count IS the loop being bounded
    (only intent-driven re-pends and the manual reset seats zero it).
    """
    capped_assets = (
        (
            await db.execute(
                select(Asset).where(
                    Asset.processing_status == AssetStatus.PROCESSING,
                    Asset.attempt > settings.asset_max_attempts,
                )
            )
        )
        .scalars()
        .all()
    )
    for asset in capped_assets:
        project = (
            await db.get(Project, asset.project_id)
            if asset.project_id is not None
            else None
        )
        lang = display_language(None, project.language if project else None)
        asset.processing_status = AssetStatus.FAILED
        asset.processing_error = user_line("processing_gave_up", lang)
        logger.warning(
            "asset_attempt_cap_terminal",
            seat="reap",
            asset_id=str(asset.id),
            attempt=asset.attempt,
        )
    # (output id, localized line) — the node mirror + owning-run finalize
    # ride their own sessions AFTER this reap commits.
    capped_renders: list[tuple[UUID, str]] = []
    for output in (
        (
            await db.execute(
                select(Output).where(
                    Output.render_status == RenderStatus.RENDERING,
                    Output.render_attempt > settings.render_max_attempts,
                )
            )
        )
        .scalars()
        .all()
    ):
        project = await db.get(Project, output.project_id)
        lang = display_language(None, project.language if project else None)
        line = user_line("render_gave_up", lang)
        output.render_status = RenderStatus.FAILED
        output.render_error = line
        capped_renders.append((output.id, line))
        logger.warning(
            "render_attempt_cap_terminal",
            seat="reap",
            output_id=str(output.id),
            attempt=output.render_attempt,
        )
    if capped_assets or capped_renders:
        await db.flush()

    assets = await db.execute(
        update(Asset)
        .where(Asset.processing_status == AssetStatus.PROCESSING)
        .values(processing_status=AssetStatus.PENDING)
    )
    nodes = await db.execute(
        update(WorkflowStep)
        .where(WorkflowStep.status == "running")
        .values(status="pending", claim_token=None)
    )
    renders = await db.execute(
        update(Output)
        .where(Output.render_status == RenderStatus.RENDERING)
        .values(render_status=RenderStatus.PENDING, render_claim_token=None)
    )
    await db.commit()
    if capped_renders:
        # The capped render's fan-out node must mirror failed and its owning
        # run must finalize — a pending-forever node would hang the run.
        from app.pipeline.rendering import (  # deferred: own sessions
            _finalize_owning_run,
            _mirror_render_node,
        )

        for output_id, line in capped_renders:
            await _mirror_render_node(output_id, "failed", line)
            await _finalize_owning_run(output_id)
    asset_count = assets.rowcount if isinstance(assets, CursorResult) else 0
    node_count = nodes.rowcount if isinstance(nodes, CursorResult) else 0
    render_count = renders.rowcount if isinstance(renders, CursorResult) else 0
    if asset_count or node_count or render_count:
        logger.info(
            "reaped_stale_jobs",
            assets=asset_count,
            nodes=node_count,
            renders=render_count,
        )


async def reap_stale_nodes_older_than(db: AsyncSession, older_than_seconds: float) -> None:
    """Periodic age-based sweep (the worker's every tick): NODES ONLY, and
    only ones in ``running`` longer than the threshold (``started_at <
    now() - threshold``). Assets and renders stay startup-sweep-only on
    purpose: rendering already carries its own 900s httpx fence, and ASR of
    a long video legitimately outlives any threshold we can confidently
    set — reaping those mid-work would loop the reprocessing, not rescue
    it. Split out of ``reap_stale`` (2026-09-05 减法批): the threshold was
    a ``None`` sentinel switching WHICH tables get touched — a mode switch
    dressed as a filter, now two honestly-named operations.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
    nodes = await db.execute(
        update(WorkflowStep)
        .where(WorkflowStep.status == "running")
        .where(WorkflowStep.started_at < cutoff)
        .values(status="pending", claim_token=None)
    )
    await db.commit()
    node_count = nodes.rowcount if isinstance(nodes, CursorResult) else 0
    if node_count:
        logger.info(
            "reaped_stale_nodes",
            nodes=node_count,
            older_than_seconds=older_than_seconds,
        )
