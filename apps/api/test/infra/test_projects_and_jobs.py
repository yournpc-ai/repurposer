"""Layer 1B infra contracts: project/job deletion locks, project listing, asset claims, skill store."""

from __future__ import annotations

import asyncio
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select, text

from app.dependencies import get_current_user_required, get_db
from app.models.schemas import AssetType
from app.models.tables import Asset, Conversation, CreditTransaction, MediaJob, Message, Output, Project, SourceSnapshot, Wallet
from app.pipeline import export_jobs, media_jobs
from test.support.db_helpers import _create, _project, _snapshots, _user, client_for, seed_project_with_receipt as seed, snapshot_db_state as state


projects = import_module("app.pipeline.routes.projects")



@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["unknown", "failed", "cancelled", "succeeded", "unreleased"])
async def test_delete_checks_job_and_ledger_before_removing_any_project(database, cleanup_calls, outcome):
    uid, pid, receipt_id = await seed(database)
    second = await _project(database, uid)
    async with database() as db:
        project, receipt = await db.get(Project, pid), await db.get(Message, receipt_id)
        await media_jobs.enqueue_media(db, project, receipt, {}, 7)
        await db.flush()
        job = await db.scalar(select(MediaJob).where(MediaJob.receipt_id == receipt_id))
        if outcome == "unknown":
            receipt.intent = {**receipt.intent, "provider_started": True}
            await db.flush()
            await media_jobs.cancel_media(db, project, job.id)
            assert job.status == "unknown"
        elif outcome == "unreleased":
            job.status = "failed"
            receipt.intent = {**receipt.intent, "media_result": {"status": "failed", "charged_credits": 0, "reserved_credits": 0}}
        elif outcome == "cancelled":
            await media_jobs.cancel_media(db, project, job.id)
        else:
            if outcome == "succeeded":
                receipt.intent = {**receipt.intent, "media_result": {"status": "available"}}
            await media_jobs._terminal(db, job, receipt, project, outcome, charged=4 if outcome == "succeeded" else 0,
                                       error="Test provider failure" if outcome == "failed" else None)
        await db.commit()
    before = await state(database)
    async with client_for(database, uid) as client:
        response = await client.post("/projects/bulk-delete", json={"ids": [str(second), str(pid)]})
    unlink, prefix = cleanup_calls
    after = await state(database)
    if outcome in {"unknown", "unreleased"}:
        assert response.status_code == 409, response.text
        assert after == before
        unlink.assert_not_awaited()
        prefix.assert_not_awaited()
    else:
        assert response.status_code == 204, response.text
        assert not any(after[k] for k in ("projects", "assets", "media_jobs", "outputs", "conversations", "messages"))
        assert after["credit_transactions"] == before["credit_transactions"]
        assert after["wallets"] == before["wallets"]
        assert after["source_snapshots"][0]["storage_key"] == before["source_snapshots"][0]["storage_key"]
        unlink.assert_awaited_once_with("synthetic/video.mp4")
        assert prefix.await_count == 2


@pytest.mark.asyncio
async def test_project_lock_orders_delete_and_paid_admission(database, cleanup_calls):
    uid, pid, receipt_id = await seed(database)
    async with client_for(database, uid) as client, database() as admission, database() as deletion:
        project = await admission.get(Project, pid)
        receipt = await admission.get(Message, receipt_id)
        # Delete takes the lock first. Admission has already read its project/receipt.
        await deletion.scalar(select(Project.id).where(Project.id == pid).with_for_update())
        with pytest.raises(ValueError, match="unavailable"):
            await media_jobs.enqueue_media(admission, project, receipt, {}, 7)
        await admission.rollback()
        await deletion.rollback()
        # Admission takes the lock first and holds it across reserve + Job insert.
        await media_jobs.enqueue_media(admission, await admission.get(Project, pid),
                                      await admission.get(Message, receipt_id), {}, 7)
        backend = await admission.scalar(text("select pg_backend_pid()"))
        deleting = asyncio.create_task(client.delete(f"/projects/{pid}"))
        async with asyncio.timeout(5):
            while not await deletion.scalar(text(
                "select exists(select 1 from pg_locks where not granted and :pid = any(pg_blocking_pids(pid)))"
            ), {"pid": backend}):
                await asyncio.sleep(0.01)
        await admission.commit()
        assert (await deleting).status_code == 409
    snapshot = await state(database)
    assert len(snapshot["media_jobs"]) == len(snapshot["credit_transactions"]) == 1
    assert snapshot["wallets"][0]["balance"] == 93
    for operation in cleanup_calls:
        operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_blocks_delete_until_reservation_is_released(database, cleanup_calls, monkeypatch):
    uid, pid, receipt_id = await seed(database)
    await _snapshots(database, uid)
    comp, version, _ = await _create(database, uid, pid)
    ref = {"composition_id": str(comp.id), "composition_version_id": str(version.id), "content_digest": version.content_digest}
    async with database() as db:
        receipt = await db.get(Message, receipt_id)
        receipt.intent = {**receipt.intent, "tool": "export_video", "export_preview": {**ref, "model_media": True, "mp4_sha256": "a"*64}}
        project = await db.get(Project, pid)
        await export_jobs.enqueue_export(db, project, receipt, {"provenance": ref}, 8)
        await db.commit()
        async with client_for(database, uid) as client:
            before = await state(database)
            assert (await client.delete(f"/projects/{pid}")).status_code == 409
            assert await state(database) == before
            for operation in cleanup_calls:
                operation.assert_not_awaited()
            await export_jobs.cancel_export(db, project, receipt.intent["export_job"])
            await db.commit()
            assert (await client.delete(f"/projects/{pid}")).status_code == 204
    async with database() as db:
        assert (await db.get(Wallet, uid)).balance == 100
        assert sorted(await db.scalars(select(CreditTransaction.amount))) == [-8, 8]


@pytest.mark.asyncio
async def test_media_stop_reads_committed_provider_start_before_releasing_hold(database, monkeypatch):
    uid, pid, rid = await seed(database)
    monkeypatch.setattr(media_jobs, "AsyncSessionLocal", database)
    async with database() as db:
        await media_jobs.enqueue_media(db, await db.get(Project, pid), await db.get(Message, rid), {}, 7)
        await db.commit()
    async with database() as worker, database() as stopping:
        job_id, token = await media_jobs.claim_media(worker, "generate_music")
        receipt = await stopping.get(Message, rid)
        assert "provider_started" not in receipt.intent
        await media_jobs._start_provider(job_id, token)
        await media_jobs.cancel_media(stopping, await stopping.get(Project, pid), job_id)
        await stopping.commit()
        assert receipt.intent["media_result"]["status"] == "provider_unknown"
        assert (await stopping.get(Wallet, uid)).balance == 93


@pytest.mark.asyncio
async def test_delete_output_keeps_snapshot_owned_bytes(database, monkeypatch):
    from app.providers.storage import export_root

    uid, pid, _ = await seed(database)
    unlink = AsyncMock()
    monkeypatch.setattr(import_module("app.pipeline.routes.outputs"), "delete_file", unlink)
    async with database() as db:
        output = await db.scalar(select(Output).where(Output.project_id == pid))
        key = f"{export_root()}{uid}/{pid}/{output.id}.mp4"
        output.files = {"video": key}
        snapshot = await db.scalar(select(SourceSnapshot).where(SourceSnapshot.origin_project_id == pid))
        snapshot.storage_key = key
        await db.commit()
        async with client_for(database, uid) as client:
            assert (await client.delete(f"/outputs/{output.id}")).status_code == 204
        unlink.assert_not_awaited()
        await db.refresh(snapshot)
        assert snapshot.storage_key == key


# --- Project list fractional duration ---
from uuid import uuid4

import pytest

from app.models.tables import Conversation, Message, Output, Project, User
from app.pipeline.routes.projects import list_projects




async def test_project_list_accepts_fractional_output_duration(database):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Fractional duration")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        db.add(Message(conversation_id=conversation.id, role="user", content="Make a video", seq=1))
        db.add(Output(
            project_id=project.id,
            type="video",
            files={"video": "clip.mp4"},
            payload={"duration": 23.433333333333334},
            render_spec={"aspect": "16:9"},
        ))
        await db.commit()

        rows = await list_projects(db=db, current_user=user)
        compact = await list_projects(db=db, current_user=user, include_thumbnail=False)
        assert [row.id for row in compact] == [project.id]
        assert compact[0].thumbnail_url is None

    assert len(rows) == 1
    assert rows[0].id == project.id
    assert rows[0].thumbnail_duration == 23
    assert rows[0].thumbnail_aspect == "16:9"


# --- Asset worker claims ---
import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, update

from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset, Project, User
from app.pipeline import asset_processing as assets


@pytest.mark.asyncio
async def test_two_workers_and_expired_processor_cannot_overwrite_successor(database, monkeypatch):
    async with database() as db:
        user = User(email="claim@example.test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Claims")
        db.add(project)
        await db.flush()
        asset = Asset(user_id=user.id, project_id=project.id, type=AssetType.TRANSCRIPT,
                      processing_requested_at=func.now())
        db.add(asset)
        await db.commit()
        aid = asset.id

    async def claim():
        async with database() as db:
            return await assets.claim_pending_asset(db)

    monkeypatch.setattr(assets, "AsyncSessionLocal", database)
    entered, release = asyncio.Event(), asyncio.Event()
    async def processor(asset, _):
        if asset.attempt == 1:
            entered.set()
            await release.wait()
            return assets.ProcessResult(extracted_text="stale")
        return assets.ProcessResult(extracted_text="verified")

    monkeypatch.setitem(assets.PROCESSORS, AssetType.TRANSCRIPT, [processor])
    activity = AsyncMock()
    monkeypatch.setattr(assets, "_record_reading_activity", activity)
    monkeypatch.setattr("app.pipeline.understanding.warm_understanding", AsyncMock())
    claims = await asyncio.gather(claim(), claim())
    assert sum(bool(c) for c in claims) == 1
    first = asyncio.create_task(assets.process_asset(*(claims[0] or claims[1])))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert await claim() is None
        async with database() as db:
            await db.execute(update(Asset).where(Asset.id == aid).values(lease_until=func.now()))
            await db.commit()
        successor = await claim()
        assert successor and successor not in claims
        await assets.process_asset(*successor)
    finally:
        release.set()
        await first
    async with database() as db:
        row = await db.get(Asset, aid)
        assert row.extracted_text == "verified" and row.processing_status == AssetStatus.COMPLETED
        assert row.claim_token is None and row.lease_until is None and row.attempt == 2
        assert "processing_stage" not in row.meta
        assert await db.scalar(select(Asset.id).where(Asset.processing_status == AssetStatus.PROCESSING)) is None
    activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_and_asset_worker_materialize_one_understanding(database, monkeypatch):
    from app.models.schemas import MaterialUnderstanding
    from app.models.tables import Output
    from app.pipeline import understanding

    async with database() as db:
        user = User(email="material@example.test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Same material")
        db.add(project)
        await db.flush()
        db.add(Asset(project_id=project.id, user_id=user.id, type=AssetType.TRANSCRIPT,
                     extracted_text="A single source", processing_status=AssetStatus.COMPLETED))
        await db.commit()

    entered, release = asyncio.Event(), asyncio.Event()
    async def analyze(*args):
        entered.set()
        await release.wait()
        return MaterialUnderstanding(core_thesis="A single source")
    provider = AsyncMock(side_effect=analyze)
    monkeypatch.setattr(understanding, "AsyncSessionLocal", database)
    monkeypatch.setattr(understanding, "_materialize_understanding", provider)
    first = asyncio.create_task(understanding.warm_understanding(project.id))
    await asyncio.wait_for(entered.wait(), 5)
    second = asyncio.create_task(understanding.warm_understanding(project.id))
    release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 5)
    provider.assert_awaited_once()
    async with database() as db:
        assert await db.scalar(select(func.count(Output.id)).where(Output.type == "material_understanding")) == 1


# --- Owner-scoped SkillVersion store ---


from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.database import Base
from app.models.schemas import ExternalSkillReference
from app.models.tables import SkillVersion, User
from app.skills.resolution import list_available_skills, resolve_chat_skill
from app.skills.external import SkillPolicy, build_skill_draft
from app.skills.store import SkillNotFoundError, get_skill_version, import_external_skill





async def _user(factory) -> UUID:
    async with factory() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.commit()
        return user.id


def _draft(
    extra: bytes = b"", *, policy: SkillPolicy | None = None,
    capabilities=(),
):
    return build_skill_draft(
        {
            "SKILL.md": (
                b"---\nname: external-method\ndescription: A reusable method.\n"
                b"---\nUse the method.\n"
            ),
            "references/method.md": b"Keep the declared structure." + extra,
        },
        declared_capabilities=capabilities,
        source_uri="https://example.invalid/skill",
        source_revision="rev-1",
        policy=policy or SkillPolicy(mode="strict", scene_count=1),
    )


async def test_skill_versions_round_trip_append_and_enforce_owner(database):
    owner_id = await _user(database)
    other_id = await _user(database)
    async with database() as db:
        first, replayed = await import_external_skill(db, owner_id=owner_id, draft=_draft())
        assert first.version == 1 and not replayed
        same, replayed = await import_external_skill(db, owner_id=owner_id, draft=_draft())
        assert same.id == first.id and replayed
        second, replayed = await import_external_skill(
            db, owner_id=owner_id, draft=_draft(b"\nAdaptive detail.")
        )
        assert second.version == 2 and not replayed
        third, replayed = await import_external_skill(
            db,
            owner_id=owner_id,
            draft=_draft(
                b"\nAdaptive detail.",
                policy=SkillPolicy(mode="adaptive", adaptation_bounds=["Keep one scene."]),
            ),
        )
        assert third.version == 3 and not replayed
        assert third.source_hash == second.source_hash
        assert third.version_digest != second.version_digest
        await db.commit()

    async with database() as db:
        loaded = await get_skill_version(db, owner_id=owner_id, skill_version_id=first.id)
        assert loaded.instructions == "Use the method."
        assert loaded.references[0]["text"] == "Keep the declared structure."
        assert loaded.policy["mode"] == "strict"
        assert loaded.policy["scene_count"] == 1
        unchanged = await get_skill_version(db, owner_id=owner_id, skill_version_id=second.id)
        assert unchanged.id != first.id
        with pytest.raises(SkillNotFoundError):
            await get_skill_version(db, owner_id=other_id, skill_version_id=first.id)

    async with database() as db:
        # Pre-digest rows replay by their complete persisted draft, without a
        # backfill that would violate the production immutability trigger.
        legacy = await db.get(SkillVersion, second.id)
        legacy.version_digest = None
        await db.commit()
        replay, replayed = await import_external_skill(
            db, owner_id=owner_id, draft=_draft(b"\nAdaptive detail.")
        )
        assert replay.id == second.id and replayed


async def test_skill_resolver_is_owner_scoped_and_version_exact(database):
    owner_id = await _user(database)
    other_id = await _user(database)
    async with database() as db:
        first, _ = await import_external_skill(
            db,
            owner_id=owner_id,
            draft=_draft(b"\nUse opacity.", capabilities={"animation:opacity"}),
        )
        second, _ = await import_external_skill(
            db,
            owner_id=owner_id,
            draft=_draft(b"\nVersion two. Use opacity.", capabilities={"animation:opacity"}),
        )
        undeclared, _ = await import_external_skill(db, owner_id=owner_id, draft=_draft())
        await db.commit()

    async with database() as db:
        reference = ExternalSkillReference(kind="external", skill_version_id=first.id)
        resolved = await resolve_chat_skill(
            db, owner_id=owner_id, reference=reference
        )
        assert resolved == reference
        options = await list_available_skills(db, owner_id=owner_id)
        external_ids = {
            option.reference.skill_version_id
            for option in options
            if isinstance(option.reference, ExternalSkillReference)
        }
        assert external_ids == {first.id, second.id, undeclared.id}
        method = next(option for option in options if option.reference == ExternalSkillReference(
            kind="external", skill_version_id=undeclared.id,
        ))
        assert method.capabilities == ["progressive_skill_package"]
        with pytest.raises(SkillNotFoundError):
            await resolve_chat_skill(
                db, owner_id=other_id, reference=reference
            )
