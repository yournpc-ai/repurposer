import hashlib
import io
import json
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
import pytest

from app.chat.video_turn_seats import prepare_narration_seat
from app.models.schemas import AssetType, PrepareNarrationArgs
from app.models.tables import Asset, Project, User
from app.pipeline.errors import user_error_line
from app.tools.video.media_analysis import LoudnessAnalysisError, analyze_audio_bytes, read_report


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
        return {"alignment_id": str(alignment_id), "status": "ALIGNED"}

    monkeypatch.setattr("app.tools.video.preparation.snapshot_audio_asset", fake_snapshot)
    monkeypatch.setattr("app.tools.video.alignment_store.request_alignment", fake_request)
    monkeypatch.setattr("app.tools.video.alignment_store.wait_for_alignment", fake_wait)

    read = await prepare_narration_seat(
        project=project,
        args=PrepareNarrationArgs(
            text="Exact narration",
            audio_asset_id=asset.id,
            language="en",
        ),
        mentions=[],
    )
    assert read.ok
    facts = json.loads(read.text)
    assert facts["alignment_id"] == str(alignment_id) and facts["status"] == "ALIGNED"
    assert facts["cache"] == "hit" and facts["scene_id"] is None


@pytest.mark.asyncio
async def test_existing_upload_still_requires_explicit_mention(database, monkeypatch):
    project, asset = await _project(database, generated=False)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    read = await prepare_narration_seat(
        project=project,
        args=PrepareNarrationArgs(
            text="Exact narration",
            audio_asset_id=asset.id,
            language="en",
        ),
        mentions=[],
    )
    assert isinstance(read, str)
    assert "requires the user's explicit @asset reference" in read


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
    from app.tools.video.audio_playback import playback_item, record_prepared_audio
    from app.chat.service import _create_message
    from app.models.schemas import ChatMessageResponse
    from app.models.tables import Conversation
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
        conversation = Conversation(user_id=project.user_id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
        opening = await _create_message(db, conversation.id, "user", "Make a promo")
        journey = {"opening_id": str(opening.id)}
        request = {"scene_id": "opening", "draft_ref": {"draft_id": "draft"}}
        receipt = await record_prepared_audio(db, project, conversation.id, journey, "narration", result, request)
        assert receipt.blocks == []
        assert receipt.intent["media_journey"]["state"] == "active"
        assert receipt.intent["prepared_audio"]["duration_seconds"] == 1.0
        repeated = await record_prepared_audio(db, project, conversation.id, journey, "narration", result, request)
        assert repeated.id == receipt.id
        # Previously persisted players are read as measurements in both transports.
        archived = ChatMessageResponse.model_validate(receipt).model_dump()
        archived["blocks"] = [{"kind": "audio_playback", "items": [item]}]
        archived["intent"] = {"media_journey": journey}
        wire = ChatMessageResponse.model_validate(archived)
        assert wire.blocks == [] and wire.intent["prepared_audio"]["role"] == "narration"
        assert ChatMessageResponse.model_validate({**archived, "intent": {}}).blocks == archived["blocks"]
    assert item["duration_seconds"] == 1.0
    assert max(item["peaks"]) == pytest.approx(0.25, abs=0.001)
    report = await read_report(snapshot.meta["analysis_ref"])
    loudness = report["media_facts"]["loudness"]
    assert loudness["integrated_lufs"] == pytest.approx(-15.05, abs=0.3)
    assert loudness["true_peak_dbtp"] == pytest.approx(-12.04, abs=0.2)


def test_loudness_failure_reports_the_audio_stage(monkeypatch, tmp_path):
    from app.chat.trigger_turn import _run_failed_fallback_speech

    monkeypatch.setenv("IMAGEIO_FFMPEG_EXE", str(tmp_path / "unavailable"))
    with pytest.raises(LoudnessAnalysisError) as exc:
        analyze_audio_bytes(_tone_wav(), snapshot_id=str(uuid4()))
    reason = user_error_line(exc.value, "zh")
    assert "响度与真峰值校验失败" in reason
    assert _run_failed_fallback_speech(
        [f"FAILED STEP: prepare_narration — {reason}"], "zh", managed_media=True,
    ) == reason
