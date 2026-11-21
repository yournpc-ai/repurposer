import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from app.chat import editor_media, service
from app.models.schemas import ChatTurnStopRequest
from app.models.tables import CreditTransaction, ExportJob, Message, Output, Project, Wallet
from app.pipeline import export_jobs
from test.core.test_compositions import _create, _snapshots
from test.core.test_project_job_deletion import cleanup_calls, client_for, seed, state


@pytest_asyncio.fixture
async def export(database, monkeypatch):
    owner, pid, rid = await seed(database)
    await _snapshots(database, owner)
    comp, version, _ = await _create(database, owner, pid)
    monkeypatch.setattr(export_jobs.settings, "public_test_export_versions", frozenset({version.id}))
    monkeypatch.setattr(export_jobs, "AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    ref = {"composition_id": str(comp.id), "composition_version_id": str(version.id),
           "content_digest": version.content_digest}
    spec = {"family": "video", "provenance": ref, "width": 320, "height": 180,
            "duration_frames": 30, "fps": {"num": 30, "den": 1}}
    async with database() as db:
        receipt = await db.get(Message, rid)
        opening = Message(conversation_id=receipt.conversation_id, role="user", content="Export this version",
                          seq=2, turn_state="in_flight")
        db.add(opening)
        await db.flush()
        receipt.seq, receipt.turn_id = 3, opening.id
        receipt.intent = {**receipt.intent, "tool": "export_video",
                          "export_preview": {**ref, "model_media": True, "mp4_sha256": "a" * 64}}
        await export_jobs.enqueue_export(db, await db.get(Project, pid), receipt, spec, 8)
        await db.commit()
        return SimpleNamespace(owner=owner, pid=pid, turn=opening.id, rid=rid,
                               job=UUID(receipt.intent["export_job"]), key=receipt.intent["export_location"])


@pytest.fixture
def renderer(monkeypatch):
    # Pause on each side of the single physical PUT. Only the Renderer and storage are doubles.
    prepared, upload, stored = asyncio.Event(), asyncio.Event(), asyncio.Event()
    allow_prepare, allow_put, allow_reply = asyncio.Event(), asyncio.Event(), asyncio.Event()
    objects, puts = set(), []
    upload_ids = {}
    wire = SimpleNamespace(prepared=prepared, upload=upload, stored=stored, allow_prepare=allow_prepare,
                           allow_put=allow_put, allow_reply=allow_reply, objects=objects, puts=puts, upload_ids=upload_ids)

    async def probe(key):
        return key in objects

    async def remove(key):
        objects.discard(key)

    async def post(url, *, json):
        if url.endswith("/prepare-export"):
            prepared.set()
            await allow_prepare.wait()
            return httpx.Response(200, json={"ready": True, "single_put": True, "upload_identity": True}, request=httpx.Request("POST", url))
        assert url.endswith("/upload")
        upload.set()
        await allow_put.wait()
        key = json["outputs"]["video"]["key"]
        puts.append(key)
        objects.add(key)
        upload_ids[key] = json["outputs"]["video"]["upload_id"]
        stored.set()
        await allow_reply.wait()
        return httpx.Response(200, json={"video": key}, request=httpx.Request("POST", url))

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return SimpleNamespace(post=post)

        async def __aexit__(self, *args):
            pass

    async def head(key):
        return {"Metadata": {"export-upload": upload_ids.get(key)}} if key in objects else None

    monkeypatch.setattr(export_jobs, "object_head", head)
    wire.remove = AsyncMock(side_effect=remove)
    monkeypatch.setattr(export_jobs, "httpx", SimpleNamespace(AsyncClient=Client))
    monkeypatch.setattr(export_jobs, "exists", probe)
    monkeypatch.setattr(export_jobs, "delete_file", wire.remove)
    monkeypatch.setattr(export_jobs, "presign_upload", AsyncMock(return_value="https://fixture.invalid/put"))
    monkeypatch.setattr(export_jobs, "_probe_artifacts", AsyncMock(return_value=([], "a" * 64)))
    return wire


async def claim(database):
    async with database() as db:
        return await export_jobs.claim_export(db)


async def stop(database, export):
    async with database() as db:
        assert await service.stop_turn_at_visible_frontier(db, export.turn, ChatTurnStopRequest()) == "cancelled"


async def assert_result(database, export, status):
    async with database() as db:
        job = await db.get(ExportJob, export.job)
        receipt = await db.get(Message, export.rid)
        result = receipt.intent["media_result"]
        assert job.status == status
        assert result["status"] == ("available" if status == "succeeded" else status)
        assert (await db.get(Message, export.turn)).turn_state == "cancelled"
        assert result["reserved_credits"] == 0
        success = status == "succeeded"
        assert result["charged_credits"] == (8 if success else 0)
        assert (await db.get(Output, export.job) is not None) == success
        assert (await db.get(Wallet, export.owner)).balance == (92 if success else 100)
        entries = list(await db.execute(select(CreditTransaction.kind, CreditTransaction.amount)))
        assert sorted(entries) == sorted([("hold", -8), ("release", 8)] + ([("capture", -8)] if success else []))
        assert await editor_media.continue_media_turn(db, await db.get(Project, export.pid), receipt) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["preparation", "before_put", "after_put", "after_output"])
async def test_stop_and_export_commit_order(database, export, renderer, cleanup_calls, boundary):
    first, second = await asyncio.gather(claim(database), claim(database))
    assert bool(first) != bool(second)
    identity = first or second
    task = asyncio.create_task(export_jobs.execute_export(*identity))
    try:
        await asyncio.wait_for(renderer.prepared.wait(), 5)
        if boundary != "preparation":
            renderer.allow_prepare.set()
            await asyncio.wait_for(renderer.upload.wait(), 5)
        if boundary in {"after_put", "after_output"}:
            renderer.allow_put.set()
            await asyncio.wait_for(renderer.stored.wait(), 5)
        if boundary == "after_output":
            renderer.allow_reply.set()
            await task
        await stop(database, export)
        await stop(database, export)
        if boundary in {"before_put", "after_put"}:
            before = await state(database)
            async with client_for(database, export.owner) as client:
                assert (await client.delete(f"/projects/{export.pid}")).status_code == 409
            assert before == await state(database)
            async with database() as db:
                result = (await db.get(Message, export.rid)).intent["media_result"]
                assert result["stop_requested"] and result["status"] == "provider_unknown"
                assert result["reserved_credits"] == 8 and result["charged_credits"] is None
                assert await db.get(Output, export.job) is None
    finally:
        renderer.allow_prepare.set()
        renderer.allow_put.set()
        renderer.allow_reply.set()
        await asyncio.wait_for(task, 5)
    success = boundary == "after_output"
    await export_jobs.execute_export(*identity)
    await assert_result(database, export, "succeeded" if success else "cancelled")
    assert renderer.puts == ([] if boundary == "preparation" else [export.key])
    assert renderer.objects == ({export.key} if success else set())
    assert renderer.remove.await_count == int(boundary in {"before_put", "after_put"})
    async with client_for(database, export.owner) as client:
        assert (await client.delete(f"/projects/{export.pid}")).status_code == 204


async def expire(database, job_id):
    async with database() as db:
        await db.execute(update(ExportJob).where(ExportJob.id == job_id).values(lease_until=func.now()))
        await db.commit()


@pytest.mark.asyncio
async def test_killed_worker_unknown_then_positive_storage_evidence(database, export, renderer, cleanup_calls):
    # A separate OS process uses the actual claim and dispatch transaction. Kill it after commit.
    env = os.environ.copy()
    env["DATABASE_URL"] = database.kw["bind"].url.render_as_string(hide_password=False)
    program = """
import asyncio
from app.models.database import AsyncSessionLocal
from app.pipeline.export_jobs import claim_export, _announce
async def main():
    async with AsyncSessionLocal() as db:
        job, token = await claim_export(db)
    assert await _announce(job, token, 'Upload', '上传', dispatch_upload=True)
    print(token, flush=True)
    await asyncio.Event().wait()
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", program, env=env,
                                                  stdout=asyncio.subprocess.PIPE)
    try:
        token = UUID((await asyncio.wait_for(process.stdout.readline(), 20)).decode().strip())
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
    assert process.returncode == -9
    await stop(database, export)
    for _ in range(export_jobs.MAX_ATTEMPTS):
        await expire(database, export.job)
        a, b = await asyncio.gather(claim(database), claim(database))
        assert bool(a) != bool(b)
        await export_jobs.execute_export(*(a or b))
    assert await claim(database) is None
    async with database() as db:
        assert (await db.get(ExportJob, export.job)).status == "unknown"
        assert (await db.get(Wallet, export.owner)).balance == 92
    async with client_for(database, export.owner) as client:
        assert (await client.delete(f"/projects/{export.pid}")).status_code == 409
    assert not await export_jobs.recheck_unknown_upload(export.job)
    await export_jobs._record_upload_observation(export.job, str(uuid4()), "stored")
    assert await claim(database) is None
    renderer.objects.add(export.key)
    renderer.upload_ids[export.key] = str(uuid4())
    assert not await export_jobs.recheck_unknown_upload(export.job)
    renderer.upload_ids[export.key] = str(token)
    assert await export_jobs.recheck_unknown_upload(export.job)
    identity = await claim(database)
    assert identity[1] != token
    await export_jobs.execute_export(export.job, token)
    await export_jobs.execute_export(*identity)
    await export_jobs._record_upload_observation(export.job, str(token), "stored")
    assert await claim(database) is None and not await export_jobs.recheck_unknown_upload(export.job)
    assert not renderer.puts and not renderer.objects
    renderer.remove.assert_awaited_once_with(export.key)
    await assert_result(database, export, "cancelled")


@pytest.mark.asyncio
async def test_late_original_response_after_claim_loss_cannot_deliver(database, export, renderer):
    renderer.allow_prepare.set()
    first = await claim(database)
    worker = asyncio.create_task(export_jobs.execute_export(*first))
    try:
        await asyncio.wait_for(renderer.upload.wait(), 5)
        await stop(database, export)
        for _ in range(export_jobs.MAX_ATTEMPTS):
            await expire(database, export.job)
            await export_jobs.execute_export(*(await claim(database)))
        assert await claim(database) is None
        async with database() as db:
            assert (await db.get(ExportJob, export.job)).status == "unknown"
        renderer.allow_put.set()
        renderer.allow_reply.set()
        await worker
        second = await claim(database)
        assert second[1] != first[1]
        await export_jobs.execute_export(*second)
        await assert_result(database, export, "cancelled")
        assert renderer.puts == [export.key] and not renderer.objects
    finally:
        renderer.allow_put.set()
        renderer.allow_reply.set()
        await asyncio.wait_for(worker, 5)


@pytest.mark.asyncio
async def test_cancel_refreshes_receipt_read_before_dispatch(database, export):
    job_id, token = await claim(database)
    async with database() as db:
        stale = await db.get(Message, export.rid)
        assert "upload_started_by" not in stale.intent
        assert await export_jobs._announce(job_id, token, "Uploading", "上传", dispatch_upload=True)
        await export_jobs.cancel_export(db, await db.get(Project, export.pid), job_id)
        await db.commit()
        assert stale.intent["upload_started_by"] == str(token)
        assert stale.intent["media_result"]["status"] == "provider_unknown"
        assert (await db.get(Wallet, export.owner)).balance == 92


@pytest.mark.asyncio
async def test_visible_export_pins_old_version_and_only_reports_reviewed_delivery(database, export, renderer):
    from app.chat.video_turn_seats import short_video_confirmation, stamp_video_presentation
    from app.editing.service import video_version_read
    from app.editing.store import apply_composition_edits
    from test.core.test_compositions import set_intent

    async with database() as db:
        project = await db.get(Project, export.pid)
        job = await db.get(ExportJob, export.job)
        base = job.render_spec["provenance"]
        tool = await db.get(Message, export.rid)
        cid = tool.conversation_id
        shown = Message(conversation_id=cid, role="assistant", content="Storyboard", seq=1)
        db.add(shown)
        await db.flush()
        read = await video_version_read(db, owner_id=export.owner, version_id=job.version_id)
        stamp_video_presentation(project, shown, read, production_requested=True)
        assert (await short_video_confirmation(db, project, cid, "Yes", None))["status"] == "queued"
        await db.commit()
    identity = await claim(database)
    async with database() as db:
        await apply_composition_edits(db, owner_id=export.owner, composition_id=UUID(base["composition_id"]),
                                      base_version_id=UUID(base["composition_version_id"]), ops=[set_intent("new head")])
    renderer.allow_prepare.set()
    renderer.allow_put.set()
    renderer.allow_reply.set()
    await export_jobs.execute_export(*identity)
    async with database() as db:
        project = await db.get(Project, export.pid)
        async def confirm():
            return await short_video_confirmation(db, project, cid, "Yes", None)

        read = await video_version_read(db, owner_id=export.owner, output_id=export.job)
        assert read["composition_version_id"] == base["composition_version_id"] and not read["is_current"]
        facts = await confirm()
        assert facts["export_job_id"] == str(export.job) and facts["status"] == "succeeded"
        assert facts["media_result"]["charged_credits"] == 8 and facts["output_refs"] == []
        delivered = Message(conversation_id=cid, turn_id=export.turn, seq=4, role="assistant",
                            content="Reviewed", intent={"output_refs": [str(export.job)], "reviewed_version": base})
        db.add(delivered)
        await db.flush()
        assert (await confirm())["delivery_message_id"] == str(delivered.id)
        unrelated = Message(conversation_id=cid, seq=5, role="user", content="Another topic")
        db.add(unrelated)
        await db.flush()
        db.add(Message(conversation_id=cid, seq=6, role="assistant", turn_id=unrelated.id, content="Which one?"))
        await db.flush()
        assert await confirm() is None
