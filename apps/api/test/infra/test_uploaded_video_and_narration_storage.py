"""Uploaded video and narration — infra contracts."""
from __future__ import annotations

import hashlib
import io
import wave
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import numpy as np
import pytest

from app.models.schemas import AssetType
from app.models.tables import Asset, Project, User
from app.tools.video.media_analysis import read_report

pytestmark = pytest.mark.infra


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


def _tone_wav():
    rate = 48000
    samples = 0.25 * 32767 * np.sin(2 * np.pi * 1000 * np.arange(rate) / rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setparams((1, 2, rate, rate, "NONE", "not compressed"))
        stream.writeframes(samples.astype("<i2").tobytes())
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_scene_audio_freezes_and_yields_measured_playback_without_system_ffmpeg(
    database, monkeypatch,
):
    from app.providers import storage
    from app.tools.video.audio_playback import playback_item
    from app.tools.video.preparation import snapshot_narration_original

    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    project, _ = await _project(database, generated=True)
    data = _tone_wav()
    digest = hashlib.sha256(data).hexdigest()
    files = {"voice.wav": data}

    async def save(key, data, **kwargs):
        files[key] = data

    monkeypatch.setattr(storage, "read", AsyncMock(side_effect=files.__getitem__))
    monkeypatch.setattr(storage, "exists", AsyncMock(side_effect=files.__contains__))
    monkeypatch.setattr(storage, "save", save)
    async with database() as db:
        _, snapshot = await snapshot_narration_original(
            db, project, text="One scene", scene_id="opening", original={
                "content_hash": "a" * 64, "duration_s": 1.0,
                "media": {"storage_key": "voice.wav", "digest": digest},
            },
        )
        await db.commit()
    async with database() as db:
        result = {"audio_snapshot_id": str(snapshot.id), "audio_digest": digest}
        item = await playback_item(db, project, "narration", result, {"scene_id": "opening"})
    assert item["duration_seconds"] == 1.0
    assert max(item["peaks"]) == pytest.approx(0.25, abs=0.001)
    report = await read_report(snapshot.meta["analysis_ref"])
    loudness = report["media_facts"]["loudness"]
    assert loudness["integrated_lufs"] == pytest.approx(-15.05, abs=0.3)
    assert loudness["true_peak_dbtp"] == pytest.approx(-12.04, abs=0.2)


@pytest.mark.asyncio
async def test_measured_score_has_playable_receipt_across_cache_and_history(database, monkeypatch):
    from importlib import import_module

    from app.chat.editor_media import _record_audio
    from app.chat.service import _create_message
    from app.models.schemas import ChatMessageResponse
    from app.models.tables import Conversation, Message
    from app.providers import storage
    from app.tools.music.score import GenerateMusicArgs, instrumental_score
    from app.tools.video import music_preparation as music

    project, _ = await _project(database, generated=True)
    files = {}
    monkeypatch.setattr(storage, "read", AsyncMock(side_effect=files.__getitem__))
    monkeypatch.setattr(storage, "exists", AsyncMock(side_effect=files.__contains__))
    monkeypatch.setattr(storage, "save", AsyncMock(side_effect=lambda key, data, **kw: files.update({key: data})))
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(music, "AsyncSessionLocal", database)

    score = instrumental_score(GenerateMusicArgs(style="ambient", duration_seconds=15))
    result = await music.prepare_programmatic_music(project=project, name="Evidence", score=score, execution_id="test")
    cached = await music.cached_music_preparation(owner_id=project.user_id, project_id=project.id, score=score)
    assert cached["snapshot"] == result["snapshot"] and cached["cache_hit"]
    request = {"name": "Evidence"}
    async with database() as db:
        conversation = Conversation(user_id=project.user_id, project_id=project.id, ui_language="en")
        db.add(conversation)
        await db.commit()
        opening = await _create_message(db, conversation.id, "user", "帮我做一支宣传片")
        receipt = await _create_message(db, conversation.id, "assistant", "", turn_id=opening.id,
                                        intent={"editor_media": str(uuid4())})
        first = await _record_audio(db, project, receipt, result, request)
        await db.commit()
    async with database() as db:
        row = await db.get(Message, receipt.id)
        wire = ChatMessageResponse.model_validate(row)
        assert wire.content == first.content
        assert wire.intent["media_result"]["status"] == "available"
        block, = wire.blocks
        item, = block["items"]
        assert block["kind"] == "audio_playback" and block["project_id"] == str(project.id)
        assert (item["role"], item["title"], item["duration_seconds"]) == ("music", "Evidence", 15)
        assert item["snapshot_id"] == result["snapshot"]["snapshot_id"]
        assert item["analysis_digest"] == result["analysis"]["report_digest"] and max(item["peaks"]) > 0
        signed = AsyncMock(return_value="https://storage.example.test/signed-score")
        assets_routes = import_module("app.pipeline.routes.assets")
        monkeypatch.setattr(assets_routes, "presign_download", signed)
        playback = await assets_routes.get_audio_playback(project.id, UUID(item["snapshot_id"]), db, await db.get(User, project.user_id))
        signed.assert_awaited_once_with(result["media"]["storage_key"])
        assert playback["digest"] == item["digest"] and playback["url"] == signed.return_value
