import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, update

from app.distribution import core, publishing
from app.distribution.adapters import linkedin
from app.models.schemas import ChannelPlatform, PublicationState
from app.models.tables import ChannelAccount, Notification, Output, Publication
from test.core.test_project_job_deletion import client_for, cleanup_calls, seed


async def scheduled(database, video):
    uid, pid, _ = await seed(database)
    async with database() as db:
        out = await db.scalar(select(Output).where(Output.project_id == pid))
        channel = ChannelAccount(user_id=uid, platform=ChannelPlatform.LINKEDIN,
                                 platform_user_id="test-member", display_name="Test",
                                 credentials_enc=core.encrypt_credentials({"access_token": "fixture"}))
        db.add(channel)
        await db.flush()
        pub = await core.create_publication(db, user_id=uid, project_id=pid, output_id=out.id,
                                            channel_account_id=channel.id, client_key="first-publication")
        if video:
            pub.platform_job_id = "urn:li:video:fixture"
        await db.commit()
        return uid, pid, out.id, channel.id, pub.id


async def claim(database):
    async with database() as db:
        return await publishing.claim_due_publication(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("video", [False, True], ids=["text-begin", "video-poll"])
@pytest.mark.parametrize("outcome", ["late_ack", "verified_post", "verified_absence"])
async def test_post_response_loss_blocks_repost_and_deletion(database, monkeypatch, cleanup_calls, video, outcome):
    uid, pid, oid, cid, pub_id = await scheduled(database, video)
    monkeypatch.setattr(publishing, "AsyncSessionLocal", database)
    reached, finish = asyncio.Event(), asyncio.Event()
    requests = []

    async def platform(request):
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"status": "AVAILABLE"})
        assert request.url.path == "/rest/posts"
        reached.set()
        await finish.wait()
        if outcome == "late_ack":
            return httpx.Response(201, headers={"x-restli-id": "urn:li:share:1"})
        raise httpx.ReadTimeout("platform reply unavailable", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(platform))
    monkeypatch.setattr(linkedin, "httpx", SimpleNamespace(AsyncClient=lambda **kwargs: client))
    a, b = await asyncio.gather(claim(database), claim(database))
    assert bool(a) != bool(b)
    job = a or b
    writer = asyncio.create_task(publishing.process_publication(*job))
    try:
        await asyncio.wait_for(reached.wait(), 5)
        async with database() as db:
            pub = await db.get(Publication, pub_id)
            assert pub.dispatch_started_at and pub.claim_token == job[1]
            with pytest.raises(core.DistributionError, match="publication_outcome_pending"):
                await core.cancel_publication(db, pub_id, uid)
            await db.rollback()
            await db.execute(update(Publication).where(Publication.id == pub_id).values(due_at=func.now()))
            await db.commit()
        assert await claim(database) is None
        assert await claim(database) is None
        async with database() as db:
            pub = await db.get(Publication, pub_id)
            assert pub.state == PublicationState.UNKNOWN and pub.due_at is None
            with pytest.raises(core.DistributionError):
                await core.retry_publication(db, pub_id, uid)
            with pytest.raises(core.DistributionError, match="publication_outcome_pending"):
                await core.create_publication(db, user_id=uid, project_id=pid, output_id=oid,
                                              channel_account_id=cid, client_key="new-click")
        async with client_for(database, uid) as api:
            assert (await api.delete(f"/projects/{pid}")).status_code == 409
        for cleanup in cleanup_calls:
            cleanup.assert_not_awaited()
    finally:
        finish.set()
        await asyncio.wait_for(writer, 5)
    if outcome != "late_ack":
        post_id = "urn:li:share:1" if outcome == "verified_post" else None
        assert await publishing.reconcile_publication(pub_id, evidence="platform-case:fixture-123", post_id=post_id)
        assert not await publishing.reconcile_publication(pub_id, evidence="replay", post_id=post_id)
    await publishing.process_publication(*job)
    assert await claim(database) is None
    assert requests.count(("POST", "/rest/posts")) == 1
    async with database() as db:
        pub = await db.get(Publication, pub_id)
        assert pub.state == (PublicationState.FAILED if outcome == "verified_absence" else PublicationState.PUBLISHED)
        assert not pub.claim_token and not pub.dispatch_started_at
        notes = list(await db.scalars(select(Notification.type).where(Notification.user_id == uid)))
        assert sorted(notes) == sorted(["publish_unknown", "publish_failed" if outcome == "verified_absence" else "publish_succeeded"])
        if outcome != "late_ack":
            assert pub.reconciliation["evidence"] == "platform-case:fixture-123"
    async with client_for(database, uid) as api:
        assert (await api.delete(f"/projects/{pid}")).status_code == 204


@pytest.mark.asyncio
async def test_sigkill_after_platform_received_post(database, monkeypatch):
    import os
    import sys

    uid, _, _, _, pub_id = await scheduled(database, False)
    monkeypatch.setattr(publishing, "AsyncSessionLocal", database)
    received = asyncio.Event()
    calls = []

    async def platform(reader, writer):
        headers = await reader.readuntil(b"\r\n\r\n")
        calls.append(headers.splitlines()[0])
        received.set()
        try:
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(platform, "127.0.0.1", 0)
    env = dict(os.environ, DATABASE_URL=database.kw["bind"].url.render_as_string(hide_password=False),
               FIXTURE_PORT=str(server.sockets[0].getsockname()[1]), NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
    code = """
import os, asyncio
from app.models.database import AsyncSessionLocal
from app.distribution import publishing
from app.distribution.adapters import linkedin
linkedin._API = 'http://127.0.0.1:' + os.environ['FIXTURE_PORT']
async def run():
    async with AsyncSessionLocal() as db:
        identity = await publishing.claim_due_publication(db)
    await publishing.process_publication(*identity)
asyncio.run(run())
"""
    async with server:
        child = await asyncio.create_subprocess_exec(sys.executable, "-c", code, env=env)
        try:
            await asyncio.wait_for(received.wait(), 20)
        finally:
            if child.returncode is None:
                child.kill()
            await child.wait()
    assert child.returncode == -9
    async with database() as db:
        await db.execute(update(Publication).where(Publication.id == pub_id).values(due_at=func.now()))
        await db.commit()
    assert await asyncio.gather(claim(database), claim(database)) == [None, None]
    async with database() as db:
        pub = await db.get(Publication, pub_id)
        assert pub.state == PublicationState.UNKNOWN and pub.dispatch_started_at
        assert pub.platform_job_id is None
        assert await db.scalar(select(Notification.type).where(Notification.user_id == uid)) == "publish_unknown"
    assert calls == [b"POST /rest/posts HTTP/1.1"]


@pytest.mark.asyncio
async def test_tiktok_polls_known_id_without_a_second_publish(database, monkeypatch):
    from app.distribution.adapters import tiktok

    uid, pid, _, cid, pub_id = await scheduled(database, False)
    async with database() as db:
        (await db.get(ChannelAccount, cid)).platform = ChannelPlatform.TIKTOK
        pub = await db.get(Publication, pub_id)
        pub.payload = {**pub.payload, "media": {"video": "https://test.invalid/synthetic.mp4"}}
        await db.commit()
    monkeypatch.setattr(publishing, "AsyncSessionLocal", database)
    requests = []

    async def platform(req):
        import json

        path = req.url.path
        requests.append(path)
        if path.endswith("/creator_info/query/"):
            data = {"privacy_level_options": ["SELF_ONLY"]}
        elif path.endswith("/video/init/"):
            async with database() as db:
                assert (await db.get(Publication, pub_id)).dispatch_started_at is not None
            data = {"publish_id": "test-platform-job"}
        else:
            assert json.loads(req.content) == {"publish_id": "test-platform-job"}
            data = {"status": "PUBLISH_COMPLETE", "share_id": "test-post"}
        return httpx.Response(200, json={"data": data})

    monkeypatch.setattr(tiktok, "httpx", SimpleNamespace(AsyncClient=lambda **_: httpx.AsyncClient(
        transport=httpx.MockTransport(platform))))
    await publishing.process_publication(*(await claim(database)))
    async with database() as db:
        pub = await db.get(Publication, pub_id)
        assert pub.platform_job_id == "test-platform-job" and pub.dispatch_started_at is None
        with pytest.raises(core.DistributionError, match="publication_outcome_pending"):
            await core.cancel_publication(db, pub_id, uid)
        pub.due_at = func.now()
        await db.commit()
    await publishing.process_publication(*(await claim(database)))
    async with database() as db:
        pub = await db.get(Publication, pub_id)
        assert pub.state == PublicationState.PUBLISHED and pub.platform_post_id == "test-post"
        assert list(await db.scalars(select(Notification.type))) == ["publish_succeeded"]
    assert [path.rsplit("/", 2)[-2] for path in requests] == ["query", "init", "fetch"]
