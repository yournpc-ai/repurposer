"""Uploaded video and narration — chat origin contracts."""
from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import AssetType
from app.models.tables import Asset, Project, User
from test.support.chat_http import tool_result

pytestmark = pytest.mark.chat_origin


async def _project(database, *, generated):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="narration-owner")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Narration source")
        db.add(project)
        await db.flush()
        asset = Asset(
            id=uuid4(),
            user_id=user.id,
            project_id=project.id,
            type=AssetType.AUDIO,
            file_url="sources/narration.mp3",
            meta={"origin": {"video_narration_hash": "a" * 64}} if generated else {},
        )
        db.add(asset)
        await db.commit()
        return project, asset


@pytest.mark.asyncio
async def test_generated_narration_reuses_owned_source_without_mention(database, monkeypatch):
    project, asset = await _project(database, generated=True)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    snapshot = SimpleNamespace(id=uuid4())
    alignment_id = uuid4()

    async def fake_snapshot(_db, actual, *, owner_id):
        assert actual.id == asset.id
        assert owner_id == project.user_id
        return snapshot

    async def fake_request(*, owner_id, audio_snapshot_id, text):
        assert owner_id == project.user_id
        assert audio_snapshot_id == snapshot.id
        assert text == "Exact narration"
        return {"alignment_id": str(alignment_id)}

    async def fake_wait(*, owner_id, alignment_id):
        return {"alignment_id": str(alignment_id), "status": "READY"}

    monkeypatch.setattr("app.tools.video.preparation.snapshot_audio_asset", fake_snapshot)
    monkeypatch.setattr("app.tools.video.alignment_store.request_alignment", fake_request)
    monkeypatch.setattr("app.tools.video.alignment_store.wait_for_alignment", fake_wait)

    read, _ = await tool_result(
        database, monkeypatch, project.user_id, project.id, "Align my recording to Exact narration.",
        "align_recording", {"text": "Exact narration", "audio_asset_id": str(asset.id)},
        operation="app.chat.video_turn_seats.align_recording_seat",
    )
    assert read.ok
    facts = json.loads(read.text)
    assert facts["alignment_id"] == str(alignment_id) and facts["status"] == "READY"


@pytest.mark.asyncio
async def test_existing_upload_still_requires_explicit_mention(database, monkeypatch):
    project, asset = await _project(database, generated=False)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    read, _ = await tool_result(
        database, monkeypatch, project.user_id, project.id, "Align my recording to Exact narration.",
        "align_recording", {"text": "Exact narration", "audio_asset_id": str(asset.id)},
        operation="app.chat.video_turn_seats.align_recording_seat",
    )
    assert isinstance(read, str)
    assert "requires the user's explicit @asset reference" in read
