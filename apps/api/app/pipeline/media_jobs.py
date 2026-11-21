"""Execution of individual authorized native media requests."""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update

from app.editing.schemas import SpeechObject
from app.pipeline import job_lease
from app.models.database import AsyncSessionLocal
from app.models.schemas import PlanEstimate
from app.models.tables import MediaJob, Message, Project, VideoNarration
from app.platform.project_context import lock_project_for_job
from app.platform.billing import credits_for_cost, estimate_usd_range, hold_media, settle_media
from app.tools.video.narration import narration_billable_upper_bound, prepare_original_narration
from app.tools.video.narration_store import NarrationOutcomeUnknown
from app.tools.video.params import narration_original_policy

LEASE = timedelta(seconds=45)
MAX_ATTEMPTS = 3
KINDS = ("generate_voice", "generate_music", "generate_image")


async def media_quote(db, kind, params, *, project):
    units = {}
    if kind == "generate_voice":
        from app.tools.video.narration import (
            narration_original_request_key,
            narration_original_quote_characters,
        )

        aligning = await db.scalar(
            select(VideoNarration.id).where(
                VideoNarration.user_id == project.user_id,
                VideoNarration.content_hash == narration_original_request_key(**params),
                VideoNarration.status == "aligning",
                VideoNarration.audio_digest.is_not(None),
                VideoNarration.storage_key.is_not(None),
            )
        )
        if aligning is None:
            units["tts_chars"] = await narration_original_quote_characters(
                user_id=project.user_id, **params
            )
    elif kind == "generate_image":
        from app.tools.video.visual_assets import cached_visual_asset

        spec = _image_spec(params, project)
        cached = await cached_visual_asset(
            owner_id=project.user_id, project_id=project.id, spec=spec
        )
        if cached is None:
            units = {"images": 1} if spec.source.kind == "minimax_image" else {}
            bounds = estimate_usd_range(
                {"prompt_tokens": [0, 8192], "completion_tokens": [0, 2048], "units": units}
            )
            prices = [await credits_for_cost(db, usd) for usd in bounds]
            return PlanEstimate(total=prices, per_task=[prices])
    elif kind != "generate_music":
        raise ValueError("Unsupported media request")
    credits = await _unit_credits(db, units)
    return PlanEstimate(total=[credits, credits], per_task=[[credits, credits]])


async def _unit_credits(db, units):
    usd = estimate_usd_range(
        {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": units}
    )[1]
    return await credits_for_cost(db, usd)


async def enqueue_media(db, project, receipt, params, credits):
    await lock_project_for_job(db, project)
    kind = receipt.intent["tool"]
    await db.execute(text("select pg_advisory_xact_lock(66063001)"))
    active = select(MediaJob.id).where(
        MediaJob.status.in_(("queued", "running")), MediaJob.kind == kind
    )
    owned = select(Project.id).where(Project.user_id == project.user_id)
    if (
        await db.scalar(select(func.count()).select_from(active.subquery())) >= 32
        or await db.scalar(
            select(func.count()).select_from(
                active.where(MediaJob.project_id.in_(owned)).subquery()
            )
        )
        >= 4
    ):
        raise ValueError("The media queue is full.")
    job_id = UUID(receipt.intent["editor_media"])
    await hold_media(db, user_id=project.user_id, job_id=job_id, credits=credits)
    db.add(
        MediaJob(
            id=job_id,
            receipt_id=receipt.id,
            project_id=project.id,
            kind=kind,
            authorized_credits=credits,
            request=params,
            status="queued",
            attempt=0,
        )
    )
    receipt.intent = {**receipt.intent, "media_job": str(job_id)}
    receipt.content = (
        "素材生成已排队。"
        if (project.language or "").startswith("zh")
        else "Media generation queued."
    )


def _authority(job_id, token):
    return job_lease.authority(MediaJob, job_id, token)


async def _fixed_voice_digest(db, job, project):
    return await db.scalar(
        select(VideoNarration.audio_digest).where(
            VideoNarration.synthesis_execution_id == str(job.id),
            VideoNarration.user_id == project.user_id,
            VideoNarration.status.in_(("done", "aligning")),
            VideoNarration.audio_digest.is_not(None),
        )
    )


async def _terminal(db, job, receipt, project, status, charged=0, error=None, *, fixed_digest=None):
    if status == "unknown" and job.kind == "generate_voice":
        fixed_digest = await _fixed_voice_digest(db, job, project)
        if fixed_digest:
            status = "failed"
            error = "The original recording is fixed. Media recovery and settlement are pending."
    keep_hold = (status == "unknown" or fixed_digest is not None) and receipt.intent.get(
        "provider_started", False
    )
    if not keep_hold:
        await settle_media(
            db,
            user_id=project.user_id,
            job_id=job.id,
            reserved=job.authorized_credits,
            charged=charged,
        )
    facts = (receipt.intent or {}).get("media_result", {})
    if error:
        receipt.content = error
        facts = {"status": "provider_unknown" if status == "unknown" else status, "error": error}
        if fixed_digest:
            facts.update(status="fixed_audio_pending_recovery", digest=fixed_digest)
    receipt.intent = {
        **receipt.intent,
        "media_result": {
            **facts,
            "charged_credits": None if keep_hold else charged,
            "reserved_credits": job.authorized_credits if keep_hold else 0,
        },
    }
    job.status, job.claim_token, job.lease_until = status, None, None


async def cancel_media(db, project, job_id):
    job = await db.scalar(
        select(MediaJob)
        .where(MediaJob.id == job_id, MediaJob.project_id == project.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if job and job.status in ("running", "queued"):
        receipt = await db.get(Message, job.receipt_id, with_for_update=True, populate_existing=True)
        uncertain = receipt.intent.get("provider_started")
        await _terminal(
            db,
            job,
            receipt,
            project,
            "unknown" if uncertain else "cancelled",
            error="Stopped. Provider settlement pending."
            if uncertain
            else "Media generation stopped.",
        )


async def claim_media(db, kind):
    if not await db.scalar(text("select pg_try_advisory_xact_lock(66063001)")):
        return None
    active = (
        select(Project.user_id)
        .join(MediaJob, MediaJob.project_id == Project.id)
        .where(
            MediaJob.kind == kind, MediaJob.status == "running", MediaJob.lease_until > func.now()
        )
    )
    if await db.scalar(select(func.count()).select_from(active.subquery())) >= 2:
        return None
    job = await db.scalar(
        select(MediaJob)
        .join(Project)
        .where(
            MediaJob.kind == kind,
            Project.user_id.not_in(active),
            (MediaJob.status == "queued")
            | ((MediaJob.status == "running") & (MediaJob.lease_until <= func.now())),
        )
        .order_by(MediaJob.created_at, MediaJob.id)
        .with_for_update(of=MediaJob, skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    receipt = await db.get(Message, job.receipt_id, with_for_update=True)
    project = await db.get(Project, job.project_id)
    if job.attempt >= MAX_ATTEMPTS:
        await _terminal(
            db,
            job,
            receipt,
            project,
            "unknown" if receipt.intent.get("provider_started") else "failed",
            error="Media generation reached the recovery limit.",
        )
        await db.commit()
        return None
    token = uuid4()
    job.status, job.claim_token, job.lease_until = "running", token, func.now() + LEASE
    job.attempt += 1
    zh = (project.language or "").startswith("zh")
    receipt.content = (
        ("正在生成旁白。" if zh else "Generating narration.")
        if kind == "generate_voice"
        else ("正在生成音乐。" if zh else "Generating music.")
    )
    if kind == "generate_image":
        receipt.content = "正在生成图片。" if zh else "Generating image."
    await db.commit()
    return job.id, token


async def _heartbeat(job_id, token):
    await job_lease.heartbeat(AsyncSessionLocal, MediaJob, job_id, token, LEASE)


async def _start_provider(job_id, token):
    async with AsyncSessionLocal() as db:
        owner = await db.scalar(
            select(MediaJob).where(*_authority(job_id, token)).with_for_update()
        )
        if not owner:
            raise ValueError("The media request has stopped.")
        receipt = await db.get(Message, owner.receipt_id, with_for_update=True)
        if receipt.intent.get("provider_started"):
            raise NarrationOutcomeUnknown("A provider request was already submitted.")
        if owner.kind == "generate_voice":
            changed = await db.execute(
                update(VideoNarration)
                .where(
                    VideoNarration.owner_token == f"{job_id}:original",
                    VideoNarration.status == "reserved",
                    VideoNarration.user_id
                    == select(Project.user_id)
                    .where(Project.id == owner.project_id)
                    .scalar_subquery(),
                    VideoNarration.synthesis_execution_id == str(job_id),
                )
                .values(status="synthesizing")
            )
            if changed.rowcount != 1:
                raise ValueError("The original recording reservation is unavailable.")
        receipt.intent = {**receipt.intent, "provider_started": True}
        await db.commit()


def _image_spec(params, project):
    from app.tools.video.visual_assets import SceneAssetSpec

    spec = SceneAssetSpec.model_validate(params["scene"])
    spec._generation_scope = (project.user_id, project.id)
    spec._review_basis = params["review_basis"]
    return spec


async def _image(job, project, token):
    from app.metering import collect_execution_cost
    from app.platform.billing import cost_usd
    from app.tools.video.visual_assets import cached_visual_asset, prepare_visual_asset

    spec = _image_spec(job.request, project)
    async with AsyncSessionLocal() as lock:
        await lock.execute(
            select(
                func.pg_advisory_xact_lock(
                    int.from_bytes(bytes.fromhex(spec.request_digest())[:8], "big", signed=True)
                )
            )
        )
        cached = await cached_visual_asset(
            owner_id=project.user_id, project_id=project.id, spec=spec
        )
        if cached:
            if (cached.get("execution") or {}).get("media_job_id") == str(job.id):
                cost = cached["execution"].get("metered_cost")
                if cost is None:
                    raise NarrationOutcomeUnknown("Image fixed before its usage receipt was saved.")
                return cached, await credits_for_cost(lock, cost_usd(cost))
            return cached, 0
        if not job.authorized_credits:
            raise ValueError("The quoted image cache is unavailable.")
        await _start_provider(job.id, token)
        with collect_execution_cost() as usage:
            image = await prepare_visual_asset(
                owner_id=project.user_id,
                project_id=project.id,
                spec=spec,
                draft_ref=None,
                execution_id=str(job.id),
                step_attempt=job.attempt,
                media_usage=usage.accrued,
            )
        return image, await credits_for_cost(lock, cost_usd(usage.accrued))


async def _voice(job, project, token):
    from app.tools.video.alignment_store import request_alignment
    from app.tools.video.preparation import snapshot_narration_original

    speech = SpeechObject(kind="speech", object_id="obj_prepare_narration", **job.request)
    limit = narration_billable_upper_bound(" ".join(speech.text.split()))
    original, _ = await prepare_original_narration(
        speech,
        user_id=project.user_id,
        execution_id=str(job.id),
        policy=narration_original_policy(limit if job.authorized_credits else 0),
        before_submit=lambda: _start_provider(job.id, token),
    )
    async with AsyncSessionLocal() as db:
        _, snapshot = await snapshot_narration_original(
            db, project, text=speech.text, original=original
        )
        await db.commit()
    alignment = await request_alignment(
        owner_id=project.user_id, audio_snapshot_id=snapshot.id, text=speech.text
    )
    generated = original.get("synthesis_execution_id") == str(job.id)
    return {
        "audio_snapshot_id": str(snapshot.id),
        "audio_digest": snapshot.digest,
        "alignment_id": alignment["alignment_id"],
        "cache_hit": not generated,
    }, {"tts_chars": original["usage_characters"] if generated else 0}


async def execute_media(job_id, token):
    from app.chat.editor_media import _record_audio, _record_image
    from app.tools.music.score import GenerateMusicArgs, instrumental_score
    from app.tools.video.music_preparation import prepare_programmatic_music

    beat = asyncio.create_task(_heartbeat(job_id, token))
    try:
        async with AsyncSessionLocal() as db:
            job = await db.scalar(select(MediaJob).where(*_authority(job_id, token)))
            if job is None:
                return
            project = await db.get(Project, job.project_id)
        try:
            async with asyncio.timeout(900):
                if job.kind == "generate_voice":
                    result, units = await _voice(job, project, token)
                elif job.kind == "generate_image":
                    result, image_credits = await _image(job, project, token)
                else:
                    args = GenerateMusicArgs.model_validate(job.request)
                    result = await prepare_programmatic_music(
                        project=project,
                        score=instrumental_score(args),
                        name=args.name,
                        execution_id=str(job.id),
                    )
                    units = {}
                async with AsyncSessionLocal() as db:
                    job = await db.scalar(
                        select(MediaJob).where(*_authority(job_id, token)).with_for_update()
                    )
                    if job:
                        receipt = await db.get(Message, job.receipt_id, with_for_update=True)
                        if job.kind == "generate_image":
                            await _record_image(db, project, receipt, result)
                            charged = min(job.authorized_credits, image_credits)
                        else:
                            await _record_audio(db, project, receipt, result, job.request)
                            charged = min(job.authorized_credits, await _unit_credits(db, units))
                        await _terminal(db, job, receipt, project, "succeeded", charged)
                        await db.commit()
        except Exception as exc:
            async with AsyncSessionLocal() as db:
                job = await db.scalar(
                    select(MediaJob).where(*_authority(job_id, token)).with_for_update()
                )
                if job:
                    receipt = await db.get(Message, job.receipt_id, with_for_update=True)
                    fixed = None
                    if job.kind == "generate_voice" and receipt.intent.get("provider_started"):
                        fixed = await _fixed_voice_digest(db, job, project)
                        if fixed and job.attempt < MAX_ATTEMPTS:
                            job.status, job.claim_token, job.lease_until = "queued", None, None
                            await db.commit()
                            return
                    uncertain = isinstance(exc, NarrationOutcomeUnknown) or receipt.intent.get(
                        "provider_started"
                    )
                    await _terminal(
                        db,
                        job,
                        receipt,
                        project,
                        "unknown" if uncertain and not fixed else "failed",
                        error=(
                            "The original recording is fixed. Media recovery and settlement are pending."
                            if fixed
                            else "The provider result needs reconciliation."
                            if uncertain
                            else "Media preparation failed."
                        ),
                        fixed_digest=fixed,
                    )
                    await db.commit()
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)
