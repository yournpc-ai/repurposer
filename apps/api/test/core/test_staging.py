"""Staging cleanup must never become a user-work queue blocker."""
import asyncio
from typing import cast
from uuid import uuid4

import pytest

from app.pipeline import staging
import app.worker as worker

pytestmark = pytest.mark.asyncio


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
