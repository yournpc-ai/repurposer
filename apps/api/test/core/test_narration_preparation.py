import hashlib
import io
import json
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import numpy as np
import pytest

from app.chat.video_turn_seats import align_recording_seat
from app.models.schemas import AssetType, AlignRecordingArgs
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

    read = await align_recording_seat(
        project=project,
        args=AlignRecordingArgs(
            text="Exact narration",
            audio_asset_id=asset.id,
        ),
        mentions=[],
    )
    assert read.ok
    facts = json.loads(read.text)
    assert facts["alignment_id"] == str(alignment_id) and facts["status"] == "ALIGNED"


@pytest.mark.asyncio
async def test_existing_upload_still_requires_explicit_mention(database, monkeypatch):
    project, asset = await _project(database, generated=False)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    read = await align_recording_seat(
        project=project,
        args=AlignRecordingArgs(
            text="Exact narration",
            audio_asset_id=asset.id,
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
async def test_measured_score_has_one_playable_receipt_across_cache_worker_and_history(database, monkeypatch):
    from importlib import import_module

    from app.chat.service import _create_message
    from app.editing.schemas import speech_text_digest
    from app.editing.timing import SOURCE_TIMEBASE as ticks
    from app.models.schemas import ChatMessageResponse, canonical_json_hash
    from app.models.tables import Conversation, Message, WorkflowRun
    from app.providers import storage
    from app.tools.music.score import ScoreSpecDraft
    from app.tools.video import music_preparation as music
    from app.chat.editor_media import settle_media_receipt
    from app.models.schemas import WorkflowStatus
    from app.tools.video.narration_draft import reproject_narration_timing
    from test.core.test_narration_timing import spoken_draft

    project, _ = await _project(database, generated=True)
    files = {}
    monkeypatch.setattr(storage, "read", AsyncMock(side_effect=files.__getitem__))
    monkeypatch.setattr(storage, "exists", AsyncMock(side_effect=files.__contains__))
    monkeypatch.setattr(storage, "save", AsyncMock(side_effect=lambda key, data, **kw: files.update({key: data})))
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(music, "AsyncSessionLocal", database)

    ids = ["intro", "end"]
    draft = spoken_draft(ids)
    draft["content"]["scenes"][-1]["range"]["end"] = 15 * ticks
    draft["design"].update(user_constraints={"target_seconds": 15}, narrations=[{
        "scene_id": sid, "text_digest": speech_text_digest(sid), "alignment": {"status": "READY"},
        "source_duration_ticks": ticks, "source_timebase": ticks,
        "cues": [{"source_range": {"start": 0, "end": ticks}}],
    } for sid in ids])
    reproject_narration_timing(draft)
    from app.tools.music.score import build_score_spec
    score = build_score_spec(ScoreSpecDraft.model_validate({
        "bpm": {"num": 96}, "sections": [{"scene_id": sid, "intent": "build"} for sid in ids],
        "instruments": [{"instrument_id": "lead", "kind": "pad"}], "seed": 42,
        "events": [{"scene_id": sid, "instrument_id": "lead", "start_beat": "0",
                    "duration_beats": "4", "midi": 60} for sid in ids],
    }), draft)
    result = await music.prepare_programmatic_music(project=project, name="Evidence", score=score, execution_id="test")
    cached = await music.cached_music_preparation(owner_id=project.user_id, project_id=project.id, score=score)
    assert cached["snapshot"] == result["snapshot"] and cached["cache_hit"]
    reference = {"draft_id": "storyboard", "draft_digest": canonical_json_hash(draft)}
    request = {"draft_ref": reference, "name": "Evidence"}
    async with database() as db:
        conversation = Conversation(user_id=project.user_id, project_id=project.id, ui_language="en", context={
            "schema_version": 1, "items": [{"executed_arguments": draft, "candidate": {
                "target_tool": "design_video", "candidate_id": reference["draft_id"],
                "candidate_digest": reference["draft_digest"],
            }}],
        })
        run = WorkflowRun(project_id=project.id)
        db.add_all([conversation, run])
        await db.commit()
        opening = await _create_message(db, conversation.id, "user", "帮我做一支宣传片")
        receipt = await _create_message(db, conversation.id, "assistant", "", turn_id=opening.id,
                                        intent={"editor_media": str(uuid4())}, workflow_run_id=run.id)
        run.status = WorkflowStatus.COMPLETED
        run.context = {"music_preparation": {"request": request, "result": result}}
        await db.commit()
        first = await settle_media_receipt(db, project, run)
        assert (await settle_media_receipt(db, project, run)).id == first.id
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

def test_mixed_mp4_with_trailing_index_has_measured_loudness(tmp_path):
    import subprocess
    from imageio_ffmpeg import get_ffmpeg_exe

    path = tmp_path / "mixed.mp4"
    subprocess.run(
        [get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
         "-c:a", "aac", str(path)],
        input=_tone_wav(), check=True, capture_output=True,
    )
    data = path.read_bytes()
    assert data.index(b"mdat") < data.index(b"moov")
    measured = analyze_audio_bytes(data, snapshot_id=str(uuid4())).media_facts["loudness"]
    assert measured["integrated_lufs"] == pytest.approx(-15, abs=1)
    assert measured["true_peak_dbtp"] == pytest.approx(-12, abs=2)
