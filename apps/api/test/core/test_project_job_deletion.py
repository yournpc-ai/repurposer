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
from test.core.test_compositions import _create, _project, _snapshots, _user


projects = import_module("app.pipeline.routes.projects")


def client_for(database, uid):
    app = FastAPI()
    app.include_router(projects.router, prefix="/projects")
    app.include_router(import_module("app.pipeline.routes.outputs").router, prefix="/outputs")

    async def session():
        async with database() as db:
            yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=uid)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def seed(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    async with database() as db:
        conversation = Conversation(project_id=pid, user_id=uid)
        asset = Asset(project_id=pid, user_id=uid, type=AssetType.VIDEO, file_url="synthetic/video.mp4")
        db.add_all([conversation, asset, Wallet(user_id=uid, balance=100), Output(project_id=pid, type="video")])
        await db.flush()
        db.add(SourceSnapshot(owner_id=uid, asset_id=asset.id, origin_project_id=pid, kind="video",
                              storage_key="snapshots/synthetic.mp4", digest="a" * 64))
        receipt = Message(conversation_id=conversation.id, role="assistant", content="", seq=1, intent={
            "tool": "generate_music", "editor_media": str(uuid4()),
        })
        db.add(receipt)
        await db.commit()
        return uid, pid, receipt.id


async def state(database):
    # Every column, including receipt payloads, wallet version, foreign keys and timestamps.
    async with database() as db:
        return {table: list(await db.scalars(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")))
                for table in ("projects", "assets", "source_snapshots", "outputs", "media_jobs",
                              "export_jobs", "conversations", "messages", "wallets", "credit_transactions")}


@pytest.fixture
def cleanup_calls(monkeypatch):
    unlink, prefix = AsyncMock(), AsyncMock()
    monkeypatch.setattr(projects, "delete_file", unlink)
    monkeypatch.setattr(projects, "delete_project_files", prefix)
    return unlink, prefix


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
    monkeypatch.setattr(export_jobs.settings, "public_test_export_versions", frozenset({version.id}))
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
    from app.providers.storage import public_test_export_root

    uid, pid, _ = await seed(database)
    unlink = AsyncMock()
    monkeypatch.setattr(import_module("app.pipeline.routes.outputs"), "delete_file", unlink)
    async with database() as db:
        output = await db.scalar(select(Output).where(Output.project_id == pid))
        key = f"{public_test_export_root()}{uid}/{pid}/{output.id}.mp4"
        output.files = {"video": key}
        snapshot = await db.scalar(select(SourceSnapshot).where(SourceSnapshot.origin_project_id == pid))
        snapshot.storage_key = key
        await db.commit()
        async with client_for(database, uid) as client:
            assert (await client.delete(f"/outputs/{output.id}")).status_code == 204
        unlink.assert_not_awaited()
        await db.refresh(snapshot)
        assert snapshot.storage_key == key
