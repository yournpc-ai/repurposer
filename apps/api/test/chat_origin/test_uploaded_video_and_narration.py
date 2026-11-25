"""Layer 1A Chat-Origin: uploaded video semantic selection, independent captions, and narration preparation."""

from __future__ import annotations
import pytest

from uuid import UUID, uuid4


from types import SimpleNamespace


import pytest


from app.editing.alignment import NarrationPayload, NarrationSentence, NarrationWord


from app.editing.edits import AddClip, AddTrack, BindSource, apply_ops


from app.editing.revisions import AddNarrationOp


from app.editing.revisions import SetTextOp, expand_revision_op, set_text_ops


from app.editing.schemas import (
    AudioObject,
    Clip,
    CompositionContent,
    Scene,
    TimeRange,
    Track,
    Transform,
    VideoObject,
)


from app.editing.source_selection import (
    SourceSelectionAnswer,
    resolve_selection,
    source_sentences,
)


from app.editing.timing import SOURCE_TIMEBASE


from app.editing.validators import validate_content


from app.editing.video_spec import compile_video_spec


from app.tools.video.design import CompositionSceneAuthoring, _expand_scene_authoring


VIDEO_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


AUDIO_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


VIDEO_DIGEST = "c" * 64


AUDIO_DIGEST = "d" * 64


COMPOSITION_ID = UUID("33333333-3333-3333-3333-333333333333")


VERSION_ID = UUID("44444444-4444-4444-4444-444444444444")


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


WORDS = [
    word("Welcome.", 0, 4),
    word("Today we discuss the product.", 6, 10),
    word("Pricing is the next topic.", 12, 18),
    word("Annual plans ", 18, 21),
    word("include support.", 22, 25),
    word("That closes the pricing answer.", 27, 31),
    word("Thank you.", 33, 36),
]


FACT = {
    "kind": "video",
    "digest": VIDEO_DIGEST,
    "duration_ticks": 40 * SOURCE_TIMEBASE,
    "storage_key": "snapshots/upload.mp4",
    "meta": {
        "words": WORDS,
        "media": {"width": 1920, "height": 1080, "has_audio": True},
    },
}


FACTS = {
    VIDEO_ID: FACT,
    AUDIO_ID: {
        "kind": "audio",
        "digest": AUDIO_DIGEST,
        "duration_ticks": 13 * SOURCE_TIMEBASE,
        "storage_key": "snapshots/narration.wav",
        "meta": {},
    },
}


def initial_content():
    return CompositionContent(
        settings={"width": 1080, "height": 1920},
        scenes=[Scene(
            scene_id="scn_pricing",
            range=TimeRange(start=0, end=40 * SOURCE_TIMEBASE),
            intent="Explain the pricing choice",
        )],
        timeline={"tracks": [
            {"track_id": "trk_main", "kind": "visual", "role": "main", "order": 0, "clips": []},
        ]},
    )


async def expanded_content():
    scene = CompositionSceneAuthoring(
        scene_id="scn_pricing",
        snapshot_id=VIDEO_ID,
        source_query="the pricing argument; include the previous sentence too",
        captions_asr=True,
        source_fit="cover",
        source_transform=Transform(x=12),
        source_gain_db=-18,
    )

    async def select(*, query, sentences):
        assert query and sentences
        return SourceSelectionAnswer(sentence_ids=["asr_0003", "asr_0004", "asr_0005"])

    from unittest.mock import patch

    with patch("app.tools.video.agents.source_selector.call", new=select):
        expanded = await _expand_scene_authoring(
            initial_content().model_dump(mode="json"),
            scene,
            FACTS,
        )
        return CompositionContent.model_validate(expanded)


def clip_by_id(content, clip_id):
    return next(
        clip
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.clip_id == clip_id
    )


@pytest.mark.asyncio
async def test_semantic_middle_selection_captions_fixed_layout_and_dialogue_spec():
    content = await expanded_content()
    source = clip_by_id(content, "clp_scn_pricing_source")
    assert source.range.duration == 13 * SOURCE_TIMEBASE
    assert source.source.source_range == TimeRange(
        start=12 * SOURCE_TIMEBASE,
        end=25 * SOURCE_TIMEBASE,
    )
    assert isinstance(source.object, VideoObject)
    assert source.object.fit == "cover"
    assert source.object.transform.x == 12
    assert source.object.gain_db == -18
    assert source.object.muted is False

    captions = [
        clip
        for track in content.timeline.tracks
        if track.role == "caption"
        for clip in track.clips
    ]
    assert len(captions) == 3
    assert all(clip.object.style.background is None for clip in captions)
    assert [clip.range.duration for clip in captions] == [
        6 * SOURCE_TIMEBASE,
        3 * SOURCE_TIMEBASE,
        3 * SOURCE_TIMEBASE,
    ]
    assert captions[0].object.caption.source_range == TimeRange(
        start=12 * SOURCE_TIMEBASE,
        end=18 * SOURCE_TIMEBASE,
    )
    assert captions[1].object.caption.source_range == TimeRange(
        start=18 * SOURCE_TIMEBASE,
        end=21 * SOURCE_TIMEBASE,
    )
    assert captions[2].object.caption.source_range == TimeRange(
        start=22 * SOURCE_TIMEBASE,
        end=25 * SOURCE_TIMEBASE,
    )
    assert captions[1].object.text + " " + captions[2].object.text == "Annual plans include support."

    dub_clip = Clip(
        clip_id="clp_dub",
        range=TimeRange(start=0, end=13 * SOURCE_TIMEBASE),
        scene_id="scn_pricing",
        source={
            "snapshot_id": AUDIO_ID,
            "snapshot_digest": AUDIO_DIGEST,
            "source_range": {"start": 0, "end": 13 * SOURCE_TIMEBASE},
        },
        object=AudioObject(kind="audio", object_id="obj_dub", gain_db=-3),
        animations=[],
    )
    content = apply_ops(content, [
        BindSource(op="bind_source", snapshot_id=AUDIO_ID),
        AddTrack(
            op="add_track",
            track=Track(
                track_id="trk_dialogue",
                kind="audio",
                role="dialogue",
                order=0,
                clips=[],
            ),
        ),
        AddClip(op="add_clip", track_id="trk_dialogue", clip=dub_clip),
    ], {VIDEO_ID: VIDEO_DIGEST, AUDIO_ID: AUDIO_DIGEST})
    validate_content(content, FACTS)
    spec = compile_video_spec(
        content,
        FACTS,
        composition_id=COMPOSITION_ID,
        version_id=VERSION_ID,
        content_digest="e" * 64,
    )
    assert (spec["width"], spec["height"]) == (1080, 1920)
    compiled = {
        clip["clip_id"]: clip
        for track in spec["tracks"]
        for clip in track["clips"]
    }
    assert compiled[source.clip_id]["source"]["start_frame"] == 360
    assert compiled[source.clip_id]["source"]["end_frame"] == 750
    assert compiled["clp_dub"]["object"] == {
        "kind": "audio",
        "object_id": "obj_dub",
        "gain_db": -3.0,
    }
    assert compiled["clp_dub"]["source"]["end_frame"] == 390
    assert len([clip for clip in compiled if clip.startswith("clp_caption_")]) == 3


@pytest.mark.asyncio
async def test_hand_edited_caption_becomes_independent_without_changing_source_window():
    content = await expanded_content()
    content = apply_ops(content, set_text_ops(
        content,
        SetTextOp(
            op="set_text",
            clip_id="clp_caption_scn_pricing_asr_0003",
            text="Pricing made simple.",
        ),
    ), {VIDEO_ID: VIDEO_DIGEST})
    validate_content(content, FACTS)
    edited = clip_by_id(content, "clp_caption_scn_pricing_asr_0003")
    assert edited.object.text == "Pricing made simple."
    assert edited.object.caption.state == "independent"
    assert edited.object.caption.source_range == TimeRange(
        start=12 * SOURCE_TIMEBASE,
        end=18 * SOURCE_TIMEBASE,
    )
    source = clip_by_id(content, "clp_scn_pricing_source")
    assert source.source.source_range.duration == 13 * SOURCE_TIMEBASE
    assert source.range.duration == 13 * SOURCE_TIMEBASE


def test_selection_rejects_disconnected_and_unknown_sentences():
    sentences = source_sentences(WORDS, duration_ticks=FACT["duration_ticks"])
    with pytest.raises(ValueError, match="contiguous"):
        resolve_selection(
            sentences,
            SourceSelectionAnswer(sentence_ids=["asr_0002", "asr_0005"]),
        )
    with pytest.raises(ValueError, match="unknown"):
        resolve_selection(
            sentences,
            SourceSelectionAnswer(sentence_ids=["not-a-sentence"]),
        )


def test_word_axis_preserves_zero_duration_token_text_with_real_sentence_bounds():
    sentences = source_sentences([
        word("Annual", 10, 11),
        word(" plans.", 11, 12),
        word(" We", 12.06, 12.06),
        word(" include", 12.08, 13),
        word(" support.", 13, 14),
    ], duration_ticks=FACT["duration_ticks"])
    assert len(sentences) == 2
    assert sentences[0].start == 10
    assert sentences[0].end == 12
    assert sentences[1].start == 12.06
    assert sentences[1].end == 14
    assert sentences[1].text == "We include support."

    with pytest.raises(ValueError, match="no usable"):
        source_sentences([word("Silent.", 1, 1)], duration_ticks=FACT["duration_ticks"])
    with pytest.raises(ValueError, match="non-monotonic"):
        source_sentences([word("First", 3, 4), word("Backwards", 2, 5)], duration_ticks=FACT["duration_ticks"])


def test_word_axis_rejects_overflow():
    with pytest.raises(ValueError, match="exceeds"):
        source_sentences([word("Beyond.", 39, 41)], duration_ticks=FACT["duration_ticks"])


@pytest.mark.asyncio
async def test_ready_narration_audio_and_caption_provenance():
    content = await expanded_content()
    payload = NarrationPayload(
        source_timebase=SOURCE_TIMEBASE,
        duration_ticks=13 * SOURCE_TIMEBASE,
        sentences=[
            NarrationSentence(
                sentence_id="s0001",
                text="Annual plans",
                text_start=0,
                text_end=12,
                start_tick=0,
                end_tick=5 * SOURCE_TIMEBASE,
                match=1.0,
                status="aligned",
                words=[NarrationWord(
                    word_id="w000001",
                    text="Annual plans",
                    text_start=0,
                    text_end=12,
                    start_tick=0,
                    end_tick=5 * SOURCE_TIMEBASE,
                    timing="anchored",
                )],
            ),
            NarrationSentence(
                sentence_id="s0002",
                text="include support.",
                text_start=13,
                text_end=29,
                start_tick=5 * SOURCE_TIMEBASE,
                end_tick=13 * SOURCE_TIMEBASE,
                match=1.0,
                status="aligned",
                words=[NarrationWord(
                    word_id="w000002",
                    text="include support.",
                    text_start=13,
                    text_end=29,
                    start_tick=5 * SOURCE_TIMEBASE,
                    end_tick=13 * SOURCE_TIMEBASE,
                    timing="anchored",
                )],
            ),
        ],
    )
    alignment_id = uuid4()
    alignment = SimpleNamespace(
        id=alignment_id,
        audio_snapshot_id=AUDIO_ID,
        audio_digest=AUDIO_DIGEST,
        status="READY",
        content_digest="f" * 64,
        algorithm="minimax-t2a-v2-sentence-v1",
        payload=payload.model_dump(mode="json"),
    )
    from app.editing.revisions import AddNarrationOp

    content = apply_ops(content, expand_revision_op(
        AddNarrationOp(
            op="add_narration",
            source_id=AUDIO_ID,
            alignment_id=alignment_id,
            scene_id="scn_pricing",
        ),
        content,
        facts=FACTS,
        narration_alignment=alignment,
    ), {VIDEO_ID: VIDEO_DIGEST, AUDIO_ID: AUDIO_DIGEST})
    validate_content(content, FACTS)

    narration_captions = [
        clip
        for track in content.timeline.tracks
        if track.track_id == "trk_narration_caption_scn_pricing"
        for clip in track.clips
    ]
    assert len(narration_captions) == 2
    assert narration_captions[0].object.caption.narration_alignment_id == alignment_id
    assert narration_captions[0].object.caption.narration_content_digest == "f" * 64

    dialogue = clip_by_id(content, "clp_dialogue_scn_pricing")
    assert dialogue.range.duration == 13 * SOURCE_TIMEBASE
    assert dialogue.source.source_range.duration == 13 * SOURCE_TIMEBASE
    assert narration_captions[1].range.start == 5 * SOURCE_TIMEBASE
    assert narration_captions[1].range.end == 13 * SOURCE_TIMEBASE
    spec = compile_video_spec(
        content,
        FACTS,
        composition_id=COMPOSITION_ID,
        version_id=VERSION_ID,
        content_digest="e" * 64,
    )
    compiled = next(
        clip for track in spec["tracks"] for clip in track["clips"]
        if clip["clip_id"] == "clp_dialogue_scn_pricing"
    )
    assert compiled["source"]["end_frame"] == 390


# --- Narration ownership & loudness measurement ---

import hashlib


import io


import json


import wave


from types import SimpleNamespace


from unittest.mock import AsyncMock


from uuid import UUID, uuid4


import numpy as np


import pytest


from app.editing.timing import SOURCE_TIMEBASE


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
        return {"alignment_id": str(alignment_id), "status": "READY"}

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
    assert facts["alignment_id"] == str(alignment_id) and facts["status"] == "READY"


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
async def test_measured_score_has_playable_receipt_across_cache_and_history(database, monkeypatch):
    from importlib import import_module

    from app.chat.service import _create_message
    from app.models.schemas import ChatMessageResponse
    from app.models.tables import Conversation, Message
    from app.providers import storage
    from app.tools.video import music_preparation as music
    from app.chat.editor_media import _record_audio
    from app.tools.music.score import GenerateMusicArgs, instrumental_score

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


def test_loudness_failure_reports_the_audio_stage(monkeypatch, tmp_path):

    monkeypatch.setenv("IMAGEIO_FFMPEG_EXE", str(tmp_path / "unavailable"))
    with pytest.raises(LoudnessAnalysisError) as exc:
        analyze_audio_bytes(_tone_wav(), snapshot_id=str(uuid4()))
    reason = user_error_line(exc.value, "zh")
    assert "响度与真峰值校验失败" in reason


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

