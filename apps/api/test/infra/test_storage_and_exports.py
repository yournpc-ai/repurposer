"""Layer 1B infra contracts: local:// storage adapter, export URLs, and staging cleanup."""

from __future__ import annotations

import httpx
import pytest
from app.config import settings
from app.main import app
from app.providers import storage

# --- Export storage public URL & download filename ---
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Response

from app.providers import storage


@pytest.mark.parametrize("prefix", ["exports/", "public-test-exports/"])
def test_export_location_pins_public_bucket_and_output(monkeypatch, prefix):
    monkeypatch.setattr(storage.settings, "s3_bucket_name", "cuts")
    monkeypatch.setattr(storage.settings, "s3_public_url", "https://cuts.example")
    owner, project, output = uuid4(), uuid4(), uuid4()
    path = f"{prefix}{owner}/{project}/{output}.mp4"
    location = f"tos://cuts/{path}"
    assert storage._bucket(location) == "cuts"
    assert storage._normalize_key(location) == path
    assert storage.public_url(location) == f"https://cuts.example/{path}"
    assert storage.matches_export_location(location, owner, project, output)
    for identity in [(uuid4(), project, output), (owner, uuid4(), output), (owner, project, uuid4())]:
        assert not storage.matches_export_location(location, *identity)
    for other in [location.replace("tos://cuts/", "tos://other/"), location.replace(prefix, "other/")]:
        assert storage.public_url(other) is None
        with pytest.raises(ValueError):
            storage._bucket(other)


@pytest.mark.asyncio
async def test_output_plays_from_public_url_and_download_keeps_filename(monkeypatch):
    outputs = import_module("app.pipeline.routes.outputs")
    owner, project, oid = uuid4(), uuid4(), uuid4()
    location = f"{storage.export_root()}{owner}/{project}/{oid}.mp4"
    output = SimpleNamespace(id=oid, project_id=project, files={"video": location})
    monkeypatch.setattr(outputs, "get_output_for_user", AsyncMock(return_value=output))
    sign = AsyncMock(return_value="attachment-url")
    monkeypatch.setattr(outputs, "presign_download", sign)
    args = dict(output_id=oid, current_user=SimpleNamespace(id=owner), db=None, response=Response())
    assert await outputs.playback(**args) == {"url": storage.public_url(location), "expires_in": None}
    sign.assert_not_awaited()
    assert (await outputs.playback(**args, download=True))["url"] == "attachment-url"
    sign.assert_awaited_once_with(location, ttl=300, filename=f"{oid}.mp4")


# --- Staging cleanup bounded concurrency ---
"""Staging cleanup must never become a user-work queue blocker."""
import asyncio
from typing import cast
from uuid import uuid4

import pytest

from app.pipeline import staging
import app.worker as worker




class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return list(self.values)


class _Session:
    def __init__(self, values):
        self.values = values

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _query):
        return _Result(self.values)


async def test_staging_listing_has_bounded_concurrency(monkeypatch):
    user_ids = [uuid4() for _ in range(12)]
    monkeypatch.setattr(staging, "AsyncSessionLocal", lambda: _Session(user_ids))
    monkeypatch.setattr(staging, "_STAGING_LIST_CONCURRENCY", 4)

    active = 0
    maximum = 0
    listed = 0
    first_batch = asyncio.Event()
    release = asyncio.Event()

    async def list_objects(_prefix):
        nonlocal active, maximum, listed
        active += 1
        listed += 1
        maximum = max(maximum, active)
        if listed == 4:
            first_batch.set()
        await release.wait()
        active -= 1
        return []

    monkeypatch.setattr(staging, "list_objects_with_age", list_objects)
    task = asyncio.create_task(staging.reap_stale_staging_uploads())
    try:
        await asyncio.wait_for(first_batch.wait(), timeout=1)
        assert listed == 4
        assert maximum == 4
        release.set()
        assert await task == 0
        assert listed == len(user_ids)
    finally:
        release.set()
        await task


async def test_staging_schedule_does_not_wait_or_overlap(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def run_reap():
        started.set()
        await release.wait()

    monkeypatch.setattr(worker, "_run_staging_reap", run_reap)
    previous_last = worker._last_staging_reap
    previous_task = worker._staging_reap_task
    worker._last_staging_reap = 0.0
    worker._staging_reap_task = None
    task = None
    finished = False
    try:
        assert worker._schedule_staging_reap(worker._STAGING_REAP_INTERVAL_SECONDS + 1)
        task = cast(asyncio.Task[None], worker._staging_reap_task)
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not task.done()
        assert not worker._schedule_staging_reap(worker._STAGING_REAP_INTERVAL_SECONDS + 2)
        release.set()
        await task
        finished = True
    finally:
        release.set()
        if task is not None and not finished:
            await task
        worker._last_staging_reap = previous_last
        worker._staging_reap_task = previous_task


# --- Local storage adapter roundtrip & loopback route ---
@pytest.mark.asyncio
async def test_h5_local_storage_adapter_roundtrip_and_loopback_route(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    monkeypatch.setattr(settings, "s3_public_url", "http://testserver/_local_storage")

    key = "test-user/sfx/demo.wav"
    await storage.save(key, b"hello-local-audio", content_type="audio/wav")
    assert await storage.exists(key) is True
    assert await storage.size(key) == len(b"hello-local-audio")
    assert await storage.read(key) == b"hello-local-audio"
    assert key in await storage._list_keys("test-user/sfx/")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(f"/_local_storage/{key}")
        assert resp.status_code == 200
        assert resp.content == b"hello-local-audio"

        put_resp = await client.put("/_local_storage/test-user/put.txt", content=b"uploaded")
        assert put_resp.status_code == 200
        assert await storage.read("test-user/put.txt") == b"uploaded"

    await storage.delete(key)
    assert await storage.exists(key) is False

    # Disabled cleanly when s3_endpoint_url is https://
    monkeypatch.setattr(settings, "s3_endpoint_url", "https://tos-example.invalid")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/_local_storage/test-user/put.txt")
        assert resp.status_code == 404
