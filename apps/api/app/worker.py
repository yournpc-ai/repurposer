"""Poll and execute the independent background domains used by Studio."""

import asyncio

import structlog

from app.config import settings
from app.distribution import (
    claim_due_publication,
    process_publication,
    reap_stale_publications,
)
from app.models.database import AsyncSessionLocal, require_current_schema
from app.pipeline.asset_processing import claim_pending_asset, process_asset
from app.pipeline.export_jobs import claim_export, execute_export
from app.pipeline.media_jobs import KINDS, claim_media, execute_media
from app.pipeline.staging import reap_stale_staging_uploads
from app.platform.notifications import deliver_due_alert
from app.platform.payment_webhooks import (
    claim_payment_alert,
    flag_stale_webhook_events,
    process_payment_alert,
)
from app.tools.video.alignment_store import (
    claim_pending_alignment,
    process_narration_alignment,
    reap_stale_alignments,
)

logger = structlog.get_logger()


# Staging GC (Batch A, I-PFA-08): S3 listing is not free, so the reaper runs
# on a slow cadence. It is a background task, never inline in the claim loop:
# storage cleanup must not delay user-requested asset or export work.
_STAGING_REAP_INTERVAL_SECONDS = 3600
_last_staging_reap = 0.0
_staging_reap_task: asyncio.Task[None] | None = None

_job_resume_task: asyncio.Task | None = None
_media_tasks: set[asyncio.Task] = set()
_asset_task: asyncio.Task | None = None
_running_render_tasks: set[asyncio.Task] = set()


async def _run_staging_reap() -> None:
    """Retrieve every background failure instead of leaking task exceptions."""
    try:
        await reap_stale_staging_uploads()
    except Exception as e:  # noqa: BLE001 — cleanup retries on the next cadence
        logger.warning("staging_reap_failed", error=str(e))


def _schedule_staging_reap(now: float) -> bool:
    """Start at most one cleanup task without making the claim loop await it."""
    global _last_staging_reap, _staging_reap_task  # noqa: PLW0603
    if now - _last_staging_reap < _STAGING_REAP_INTERVAL_SECONDS:
        return False
    if _staging_reap_task is not None and not _staging_reap_task.done():
        return False
    _last_staging_reap = now
    _staging_reap_task = asyncio.create_task(_run_staging_reap())
    return True


async def _tick() -> bool:
    """Claim and run units of work. Returns True if anything was processed."""
    did_work = False

    # Publications first (DISTRIBUTION.md §6): a scheduled publish is a time
    # promise to the user and must not queue behind asset processing or rendering.
    # The table is usually empty, so the check is nearly free.
    async with AsyncSessionLocal() as db:
        publication = await claim_due_publication(db)
    if publication is not None:
        did_work = True
        await process_publication(*publication)

    # Payment alerts are an outbox claim source: the API persists failures,
    # while this worker owns the external email call and its bounded retries.
    async with AsyncSessionLocal() as db:
        if await flag_stale_webhook_events(db):
            did_work = True
        payment_alert = await claim_payment_alert(db)
    if payment_alert is not None:
        did_work = True
        await process_payment_alert(payment_alert)

    if settings.resend_api_key:
        async with AsyncSessionLocal() as db:
            if await deliver_due_alert(db):
                did_work = True

    global _asset_task
    if _asset_task is None or _asset_task.done():
        if _asset_task is not None and _asset_task.exception():
            logger.error("asset_task_interrupted", error=str(_asset_task.exception()))
        _asset_task = None
        async with AsyncSessionLocal() as db:
            asset = await claim_pending_asset(db)
        if asset:
            did_work = True
            _asset_task = asyncio.create_task(process_asset(*asset))

    # Deterministic final-audio/script alignment is the fifth claim source.
    # ALIGNED waits for Agent semantics and READY is immutable; neither is
    # claimed again. Expired PROCESSING leases recover to PENDING only.
    async with AsyncSessionLocal() as db:
        await reap_stale_alignments(db)
        alignment_claim = await claim_pending_alignment(db)
    if alignment_claim is not None:
        did_work = True
        await process_narration_alignment(*alignment_claim)

    for kind in KINDS:
        async with AsyncSessionLocal() as db:
            claim = await claim_media(db, kind)
        if claim:
            did_work = True
            task = asyncio.create_task(execute_media(*claim))
            _media_tasks.add(task)
            task.add_done_callback(_media_tasks.discard)

    while len(_running_render_tasks) < settings.render_concurrency:
        async with AsyncSessionLocal() as db:
            export = await claim_export(db)
        if export is None:
            break
        did_work = True
        task = asyncio.create_task(execute_export(*export))
        _running_render_tasks.add(task)
        task.add_done_callback(_running_render_tasks.discard)

    global _job_resume_task
    if _job_resume_task is None or _job_resume_task.done():
        if _job_resume_task is not None and _job_resume_task.exception():
            logger.warning("job_receipt_continuation_interrupted")
        from app.chat.editor_recovery import resume_job_receipts
        _job_resume_task = asyncio.create_task(resume_job_receipts())

    # Staging GC is scheduled only after every claim source has had its turn.
    # A slow storage sweep remains isolated from all subsequent ticks.
    _schedule_staging_reap(asyncio.get_running_loop().time())

    return did_work


async def run_worker() -> None:
    """Worker entrypoint: recover orphaned jobs, then poll forever."""
    from app.providers.llm import get_llm_client

    await require_current_schema()
    llm = get_llm_client()
    logger.info(
        "worker_starting",
        poll_interval=settings.worker_poll_interval,
        llm_provider=llm.provider,
        llm_model=llm.model,
    )
    if not settings.payment_alert_recipient_list:
        logger.warning("payment_alerts_not_configured")
    async with AsyncSessionLocal() as db:
        # Warm the configs cache before any claim: the pricing seams
        # (price_units → peek_config) read it synchronously, and this
        # process has no reconcile seat — read-only prime, race-safe.
        from app.platform.configs import warm_config_cache

        await warm_config_cache(db)
        await reap_stale_publications(db)
        await reap_stale_alignments(db)
    while True:
        try:
            did_work = await _tick()
        except Exception as e:  # noqa: BLE001 — keep the loop alive on any error
            logger.error("worker_tick_failed", error=str(e))
            did_work = False
        if not did_work:
            await asyncio.sleep(settings.worker_poll_interval)


def main() -> None:
    """Synchronous entrypoint for ``python -m app.worker``."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("worker_stopped")


if __name__ == "__main__":
    main()
