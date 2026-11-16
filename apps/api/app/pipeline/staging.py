"""Upload staging lifecycle (Product Flow Alignment Batch A, contract
``docs/tasks/product-flow-alignment.md`` §5, invariant I-PFA-08).

Staging objects live under ``{user_id}/uploads/staging/{session_id}/`` and
are uploaded *before* any project exists. Attach points an asset row at the
staging key as-is (zero server-side copy), so a referenced staging object is
indistinguishable from a project object for deletion purposes — the reaper
therefore skips any key referenced by an ``assets.file_url`` row.

State machine: ``created → uploading → uploaded → attached``; objects that
never reach ``attached`` within ``STAGING_TTL_SECONDS`` are expired and
reaped (including the "PUT succeeded, attach never called" window).
"""

import asyncio
import time

import structlog
from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.tables import Asset, User
from app.providers.storage import (
    delete_file,
    get_staging_upload_prefix,
    list_objects_with_age,
)

logger = structlog.get_logger()

# 24h: generous against any realistic compose→Generate gap; in-flight PUTs
# finish in minutes, so nothing young is ever at risk.
STAGING_TTL_SECONDS = 24 * 3600
# Listing is remote IO. Keep the owner-prefix isolation, but do not turn the
# user count into a serial storage-delay multiplier.
_STAGING_LIST_CONCURRENCY = 8


async def reap_stale_staging_uploads(ttl_seconds: int = STAGING_TTL_SECONDS) -> int:
    """Delete expired, unreferenced staging objects. Returns the delete count.

    Enumeration is per-user (bounded prefixes) — never a bucket-wide listing.
    Prefix reads use bounded concurrency; reference checks keep their own short
    DB sessions, so no transaction stays open across remote storage calls.
    Failures are logged and skipped: a missed object is retried next pass.
    """
    cutoff = time.time() - ttl_seconds
    async with AsyncSessionLocal() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())

    semaphore = asyncio.Semaphore(_STAGING_LIST_CONCURRENCY)

    async def list_for_user(user_id):
        async with semaphore:
            try:
                objects = await list_objects_with_age(get_staging_upload_prefix(user_id))
                return user_id, objects
            except Exception as e:  # noqa: BLE001 — storage hiccup ≠ worker failure
                logger.warning("staging_reap_list_failed", user_id=str(user_id), error=str(e))
                return user_id, None

    listings = await asyncio.gather(*(list_for_user(user_id) for user_id in user_ids))
    reaped = 0
    for _user_id, objects in listings:
        if objects is None:
            continue
        expired = [key for key, modified in objects if modified < cutoff]
        if not expired:
            continue
        async with AsyncSessionLocal() as db:
            referenced = set(
                (
                    await db.execute(select(Asset.file_url).where(Asset.file_url.in_(expired)))
                )
                .scalars()
                .all()
            )
        for key in expired:
            if key in referenced:
                continue
            try:
                await delete_file(key)
                reaped += 1
            except Exception as e:  # noqa: BLE001 — skip, retry next pass
                logger.warning("staging_reap_delete_failed", key=key, error=str(e))
    if reaped:
        logger.info("staging_reap_completed", reaped=reaped)
    return reaped
