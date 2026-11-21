"""Native MP4 exports. PostgreSQL owns claims, the immutable object key survives claim loss."""

import asyncio
import copy
import logging
from datetime import timedelta
from math import gcd
from uuid import UUID, uuid4

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import func, select, text, update

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Composition, CompositionVersion, ExportJob, Message, Output, Project
from app.pipeline.rendering import _absolutize, _probe_artifacts
from app.platform.billing import hold_export, settle_export
from app.providers.storage import (
    exists,
    presign_upload,
    private_export_key,
    private_export_root,
    verify_private_export_storage,
)

LEASE = timedelta(seconds=45)
MAX_ATTEMPTS = 3
log = logging.getLogger(__name__)


async def enqueue_export(db, project, receipt, spec, credits):
    try:
        await verify_private_export_storage()
    except (ValueError, ClientError, BotoCoreError):
        error = (
            "私有成片存储尚未就绪，未预占费用。"
            if (project.language or "").startswith("zh")
            else "Private export storage is unavailable. No credits were reserved."
        )
        receipt.content = error
        receipt.intent = {
            **receipt.intent,
            "media_result": {
                "role": "export",
                "status": "failed",
                "code": "private_storage_unavailable",
                "error": error,
            },
        }
        return
    owner = project.user_id
    ref = spec["provenance"]
    preview = receipt.intent["export_preview"]
    prior = (
        await db.execute(
            select(Output, ExportJob.receipt_id)
            .join(ExportJob, Output.id == ExportJob.id)
            .where(
                Output.project_id == project.id,
                Output.composition_version_id == UUID(ref["composition_version_id"]),
                Output.files["video"].as_string().startswith(private_export_root()),
                ExportJob.status == "succeeded",
                ExportJob.render_spec == spec,
            )
            .order_by(ExportJob.created_at.desc())
            .limit(1)
        )
    ).first()
    if prior:
        output, receipt_id = prior
        failures, digest = await _probe_artifacts(spec, output.files["video"])
        if failures or digest != output.files.get("video_sha256"):
            raise ValueError("The saved MP4 no longer matches its verified bytes.")
    composition = await db.scalar(
        select(Composition)
        .where(
            Composition.id == UUID(ref["composition_id"]),
            Composition.origin_project_id == project.id,
            Composition.owner_id == owner,
        )
        .with_for_update()
    )
    if (
        composition is None
        or str(composition.current_version_id) != ref["composition_version_id"]
        or not preview.get("model_media")
        or not preview.get("mp4_sha256")
        or any(preview.get(k) != v for k, v in ref.items())
    ):
        raise ValueError("Export authorization does not match the observed version.")
    if prior:
        original = await db.get(Message, receipt_id)
        receipt.intent = {**receipt.intent, "media_result": original.intent["media_result"]}
        receipt.content = original.content
        return
    if await db.scalar(
        select(ExportJob.id)
        .where(
            ExportJob.project_id == project.id,
            ExportJob.version_id == composition.current_version_id,
            ExportJob.status.in_(("running", "queued")),
        )
        .limit(1)
    ):
        raise ValueError("This version is already being exported.")
    # Serialize admissions, including parallel openings. No DB lock spans the rendering request.
    await db.execute(text("select pg_advisory_xact_lock(66062001)"))
    owned = select(Project.id).where(Project.user_id == owner)
    active = select(ExportJob.id).where(ExportJob.status.in_(("queued", "running")))
    if (
        await db.scalar(select(func.count()).select_from(active.subquery())) >= 32
        or await db.scalar(
            select(func.count()).select_from(
                active.where(ExportJob.project_id.in_(owned)).subquery()
            )
        )
        >= 4
    ):
        raise ValueError("The export queue is full. Try again after an export finishes.")
    identity = UUID(receipt.intent["editor_media"])
    job = ExportJob(
        id=identity,
        receipt_id=receipt.id,
        project_id=project.id,
        version_id=composition.current_version_id,
        authorized_credits=credits,
        render_spec=spec,
        status="queued",
        attempt=0,
    )
    await hold_export(db, user_id=owner, export_id=identity, credits=credits)
    db.add(job)
    receipt.content = (
        "正在排队导出 MP4。" if (project.language or "").startswith("zh") else "MP4 export queued."
    )
    receipt.intent = {**receipt.intent, "export_job": str(identity)}


async def _finish(db, job, project, status, error=None, files=None):
    receipt = await db.get(Message, job.receipt_id, with_for_update=True)
    spec = job.render_spec
    ref = spec["provenance"]
    success = status == "succeeded"
    if success:
        version = await db.get(CompositionVersion, job.version_id)
        composition = await db.get(Composition, version.composition_id)
        seconds = spec["duration_frames"] * spec["fps"]["den"] / spec["fps"]["num"]
        divisor = gcd(spec["width"], spec["height"])
        payload = {
            "composition_digest": ref["content_digest"],
            "name": composition.name,
            "duration_seconds": seconds,
            "duration": seconds,
            "aspect": f"{spec['width'] // divisor}:{spec['height'] // divisor}",
        }
        db.add(
            Output(
                id=job.id,
                project_id=project.id,
                composition_id=composition.id,
                composition_version_id=version.id,
                work_id=composition.id,
                type="video",
                language=(version.skill_provenance or {}).get("language"),
                provenance="generated",
                payload=payload,
                render_spec=spec,
                files=files,
                render_status=RenderStatus.COMPLETED,
            )
        )
        facts = {
            "status": "available",
            "role": "export",
            **ref,
            "output_id": str(job.id),
            "duration_seconds": seconds,
            "review_pending": True,
        }
    else:
        facts = {"status": status, "role": "export", **ref, "error": error}
    await settle_export(
        db,
        user_id=project.user_id,
        export_id=job.id,
        reserved=job.authorized_credits,
        charged=job.authorized_credits if success else 0,
    )
    receipt.intent = {**receipt.intent, "media_result": facts}
    zh = (project.language or "").startswith("zh")
    receipt.content = (
        ("正式 MP4 已导出，待审片。" if zh else "MP4 export complete. Review pending.")
        if success
        else error
    )
    job.status, job.claim_token, job.lease_until = status, None, None


async def cancel_export(db, project, job_id):
    job = await db.scalar(
        select(ExportJob)
        .where(ExportJob.id == job_id, ExportJob.project_id == project.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job and job.status in {"queued", "running"}:
        await _finish(
            db,
            job,
            project,
            "cancelled",
            "MP4 导出已停止。"
            if (project.language or "").startswith("zh")
            else "MP4 export stopped.",
        )


async def claim_export(db):
    # Cap active renderers across worker processes. Expired claims have no authority.
    if not await db.scalar(text("select pg_try_advisory_xact_lock(66062001)")):
        return None
    running = (ExportJob.status == "running") & (ExportJob.lease_until > func.now())
    if (
        await db.scalar(select(func.count()).select_from(ExportJob).where(running))
        >= settings.render_concurrency
    ):
        return None
    owners = (
        select(Project.user_id).join(ExportJob, ExportJob.project_id == Project.id).where(running)
    )
    job = await db.scalar(
        select(ExportJob)
        .join(Project, Project.id == ExportJob.project_id)
        .where(
            Project.user_id.not_in(owners),
            (ExportJob.status == "queued")
            | ((ExportJob.status == "running") & (ExportJob.lease_until <= func.now())),
        )
        .order_by(ExportJob.created_at, ExportJob.id)
        .with_for_update(of=ExportJob, skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    if job.attempt >= MAX_ATTEMPTS:
        await _finish(
            db,
            job,
            await db.get(Project, job.project_id),
            "failed",
            "The export retry limit was reached.",
        )
        await db.commit()
        return None
    token = uuid4()
    job.status, job.claim_token, job.lease_until = "running", token, func.now() + LEASE
    job.attempt += 1
    await db.commit()
    return job.id, token


def _authority(job_id, token):
    return (
        ExportJob.id == job_id,
        ExportJob.status == "running",
        ExportJob.claim_token == token,
        ExportJob.lease_until > func.clock_timestamp(),
    )


async def _heartbeat(job_id, token):
    while True:
        await asyncio.sleep(LEASE.total_seconds() / 3)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(ExportJob)
                .where(*_authority(job_id, token))
                .values(lease_until=func.now() + LEASE)
            )
            await db.commit()
            if not result.rowcount:
                return


async def _announce(job_id, token, en, zh):
    """A progress receipt is projected only while its executor still owns the row."""
    async with AsyncSessionLocal() as db:
        job = await db.scalar(select(ExportJob).where(*_authority(job_id, token)).with_for_update())
        if not job:
            return False
        project = await db.get(Project, job.project_id)
        receipt = await db.get(Message, job.receipt_id)
        receipt.content = zh if (project.language or "").startswith("zh") else en
        await db.commit()
        return True


async def execute_export(job_id, token):
    beat = asyncio.create_task(_heartbeat(job_id, token))
    try:
        async with AsyncSessionLocal() as db:
            job = await db.scalar(select(ExportJob).where(*_authority(job_id, token)))
            if not job:
                return
            project = await db.get(Project, job.project_id)
            spec = _absolutize(copy.deepcopy(job.render_spec))
        try:
            key = private_export_key(project.user_id, project.id, job_id)
            await verify_private_export_storage()
            if not await exists(key):
                put_url = await presign_upload(
                    key,
                    content_type="video/mp4",
                    create_only=True,
                    ttl=max(3600, settings.render_timeout_seconds + 600),
                )
                payload = {
                    "spec": spec,
                    "render_id": str(job_id),
                    "outputs": {
                        "video": {
                            "key": key,
                            "put_url": put_url,
                            "content_type": "video/mp4",
                            "create_only": True,
                        }
                    },
                }
                async with httpx.AsyncClient(
                    timeout=settings.render_timeout_seconds, trust_env=False
                ) as client:
                    if not await _announce(job_id, token, "Rendering the MP4.", "正在渲染 MP4。"):
                        return
                    root = settings.render_url.removesuffix("/render")
                    response = await client.post(
                        root + "/prepare-export", json={"spec": spec, "render_id": str(job_id)}
                    )
                    response.raise_for_status()
                    if response.json().get("ready") is not True:
                        raise ValueError("Renderer did not confirm the artifact")
                    if not await _announce(
                        job_id, token, "Uploading the rendered MP4.", "正在上传成片。"
                    ):
                        return
                    try:
                        response = await client.post(root + "/upload", json=payload)
                        response.raise_for_status()
                        if response.json().get("video") != key:
                            raise ValueError("Unexpected renderer acknowledgement")
                    except httpx.HTTPError:
                        # An interrupted response or a competing conditional PUT can
                        # leave the exact immutable artifact ready for verification.
                        if not await exists(key):
                            raise
            if not await _announce(job_id, token, "Checking the uploaded MP4.", "正在校验成片。"):
                return
            violations, digest = await _probe_artifacts(spec, key)
            if violations or not digest:
                raise ValueError("MP4 integrity check failed")
            files = {"video": key, "video_sha256": digest}
        except Exception as exc:
            log.warning("Video export %s failed (%s)", job_id, type(exc).__name__)
            files = None
        async with AsyncSessionLocal() as db:
            job = await db.scalar(
                select(ExportJob).where(*_authority(job_id, token)).with_for_update()
            )
            if job:
                await _finish(
                    db,
                    job,
                    project,
                    "succeeded" if files else "failed",
                    None if files else "The renderer could not deliver a verified MP4.",
                    files,
                )
                await db.commit()
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)
