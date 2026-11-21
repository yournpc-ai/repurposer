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
    monkeypatch.setattr("app.pipeline.node_runners.warm_understanding", AsyncMock())
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
