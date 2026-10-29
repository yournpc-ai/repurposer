"""Pure narration preparation, revision and video-spec handoff tests.

No DB, provider call, network or audio decoder: external effects are explicit
in-memory fakes. The locked behavior is the paid-call boundary and the
immutable-version → fixed-media → ordinary audio/text-spec journey.
"""
from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

import pytest

from app.editing.schemas import (
    CaptionDerivation,
    Clip,
    CompositionContent,
    SpeechObject,
    TimeRange,
    Track,
    speech_text_digest,
)
from app.editing.service import translate_revision
from app.editing.video_spec import compile_video_spec
from app.editing.validators import validate_content
from app.models.schemas import ReviseVideoArgs
from app.providers.voice import T2AResult, _parse_subtitle_cues
from app.tools.video import narration, narration_store
from app.tools.video.params import NarrationPolicy
from app.tools.video.production import _render_capture_units
from test_editing_edits_pure import SNAPSHOT_FACTS, valid_content

COMP_ID = UUID("77777777-7777-7777-7777-777777777777")
VER_ID = UUID("88888888-8888-8888-8888-888888888888")
EXECUTION_ID = str(uuid4())
USER_ID = uuid4()


def narrated_content(text: str = "第一句。第二句。") -> CompositionContent:
    content = valid_content()
    speech = SpeechObject(
        kind="speech",
        object_id="obj_speech",
        text=text,
        voice_id="presenter_male",
        language="zh",
    )
    content.timeline.tracks.append(Track(
        track_id="trk_dialogue", kind="audio", role="dialogue", order=1,
        clips=[Clip(
            clip_id="clp_speech", range=TimeRange(start=0, end=360000),
            scene_id="scn_open", source=None, object=speech, animations=[],
        )],
    ))
    title = next(c for t in content.timeline.tracks for c in t.clips if c.clip_id == "clp_title")
    caption = title.model_copy(deep=True, update={
        "clip_id": "clp_caption",
        "range": TimeRange(start=0, end=360000),
        "animations": [],
    })
    caption.object = title.object.model_copy(deep=True, update={
        "object_id": "obj_caption",
        "text": text,
        "caption": CaptionDerivation(
            speech_object_id=speech.object_id,
            source_text_digest=speech_text_digest(text),
            alignment="minimax-t2a-v2-sentence-v1",
        ),
    })
    content.timeline.tracks.append(Track(
        track_id="trk_caption", kind="visual", role="caption", order=2,
        clips=[caption],
    ))
    content.scenes[0].speech_clip_ids = ["clp_speech"]
    validate_content(content, SNAPSHOT_FACTS)
    return content


def _cues(text: str, duration_s: float) -> list[dict]:
    return [{
        "text": text,
        "text_begin": 0,
        "text_end": len(text),
        "time_begin": 0,
        "time_end": int(duration_s * 1000),
    }]


def _original(content: CompositionContent, duration_s: float = 2.0) -> dict:
    speech = next(
        c.object for t in content.timeline.tracks for c in t.clips
        if isinstance(c.object, SpeechObject)
    )
    normalized = " ".join(speech.text.split())
    cues = _cues(normalized, duration_s)
    return {
        "content_hash": "a" * 64,
        "normalized_text": normalized,
        "media": {"storage_key": "narration/original.mp3", "digest": "b" * 64, "mime_type": "audio/mpeg"},
        "duration_s": duration_s,
        "cues": cues,
        "alignment": narration.NARRATION_ALIGNMENT,
        "alignment_digest": narration.narration_alignment_digest(normalized, cues),
        "usage_characters": len(normalized),
        "trace_id": "trace-original",
        "speed": 1.0,
        "cache_hit": True,
    }


def _revision(content: CompositionContent, *edits: dict) -> CompositionContent:
    from app.editing.edits import apply_ops

    args = ReviseVideoArgs.model_validate({
        "base_ref": {
            "composition_id": str(COMP_ID),
            "composition_version_id": str(VER_ID),
            "content_digest": "c" * 64,
        },
        "edits": list(edits),
    })
    return apply_ops(content, translate_revision(content, args), {})


def test_manual_caption_survives_narration_revision_until_explicit_sync():
    base = narrated_content()
    edited = _revision(base, {"op": "update_text", "clip_id": "clp_caption", "text": "人工字幕"})
    revised = _revision(edited, {"op": "update_speech", "clip_id": "clp_speech", "text": "新的旁白。"})
    caption = next(c for t in revised.timeline.tracks for c in t.clips if c.clip_id == "clp_caption")
    speech = next(c for t in revised.timeline.tracks for c in t.clips if c.clip_id == "clp_speech")
    assert caption.object.text == "人工字幕"
    assert caption.object.caption.state == "independent"
    assert speech.object.text == "新的旁白。"
    validate_content(revised, SNAPSHOT_FACTS)

    synced = _revision(revised, {"op": "sync_captions", "clip_id": "clp_speech"})
    caption = next(c for t in synced.timeline.tracks for c in t.clips if c.clip_id == "clp_caption")
    assert caption.object.text == "新的旁白。"
    assert caption.object.caption.state == "derived"
    assert caption.object.caption.source_text_digest == speech_text_digest("新的旁白。")
    # Neither revision mutates the earlier immutable candidate.
    original_caption = next(c for t in base.timeline.tracks for c in t.clips if c.clip_id == "clp_caption")
    assert original_caption.object.text == "第一句。第二句。"


def test_speech_compiles_to_audio_and_actual_sentence_text_clips_only():
    content = narrated_content()
    before = content.model_dump(mode="json")
    original = _original(content)
    media = {
        "obj_speech": {
            "request": {
                "speech_object_id": "obj_speech",
                "text_digest": speech_text_digest("第一句。第二句。"),
                "provider": "minimax",
                "model": "speech-2.6-hd",
                "voice_id": "presenter_male",
                "language": "zh",
                "gain_db": 0.0,
                "window_ticks": 360000,
            },
            "media": original["media"],
            "duration_s": 2.0,
            "normalized_text": original["normalized_text"],
            "cues": original["cues"],
        },
    }
    spec = compile_video_spec(
        content, SNAPSHOT_FACTS, composition_id=COMP_ID, version_id=VER_ID,
        content_digest="c" * 64, speech_media=media,
    )
    clips = {c["clip_id"]: c for t in spec["tracks"] for c in t["clips"]}
    assert clips["clp_speech"]["object"]["kind"] == "audio"
    assert clips["clp_speech"]["start_frame"] == 0
    assert clips["clp_speech"]["end_frame"] == 60
    assert clips["clp_speech"]["source"]["end_frame"] == 60
    assert clips["clp_caption:cue:0"]["object"] == {
        **clips["clp_caption:cue:0"]["object"],
        "kind": "text",
        "text": "第一句。第二句。",
    }
    assert clips["clp_caption:cue:0"]["end_frame"] == 60
    assert "clp_caption" not in clips
    assert '"kind": "speech"' not in json.dumps(spec)
    assert content.model_dump(mode="json") == before


def test_fractional_millisecond_cues_keep_precision_until_frame_quantization():
    content = narrated_content("甲乙")
    original = _original(content)
    original["cues"] = [
        {"text": "甲", "text_begin": 0, "text_end": 1, "time_begin": 33.9, "time_end": 1000.1},
        {"text": "乙", "text_begin": 1, "text_end": 2, "time_begin": 1000.1, "time_end": 2000},
    ]
    media = {
        "obj_speech": {
            "request": {
                "speech_object_id": "obj_speech",
                "text_digest": speech_text_digest("甲乙"),
                "provider": "minimax",
                "model": "speech-2.6-hd",
                "voice_id": "presenter_male",
                "language": "zh",
                "gain_db": 0.0,
                "window_ticks": 360000,
            },
            "media": original["media"],
            "duration_s": original["duration_s"],
            "normalized_text": original["normalized_text"],
            "cues": original["cues"],
        },
    }
    spec = compile_video_spec(
        content, SNAPSHOT_FACTS, composition_id=COMP_ID, version_id=VER_ID,
        content_digest="c" * 64, speech_media=media,
    )
    clips = {c["clip_id"]: c for t in spec["tracks"] for c in t["clips"]}
    first = clips["clp_caption:cue:0"]
    second = clips["clp_caption:cue:1"]
    assert (first["start_frame"], first["end_frame"]) == (1, 31)
    assert (second["start_frame"], second["end_frame"]) == (31, 60)
    assert [first["object"]["text"], second["object"]["text"]] == ["甲", "乙"]


@pytest.mark.asyncio
async def test_quote_covers_the_bounded_remaining_passes_without_synthesis(monkeypatch):
    content = narrated_content()
    text = "第一句。第二句。"

    async def missing(user_id, speech):
        return None

    monkeypatch.setattr(narration_store, "peek_original", missing)
    upper_bound = narration.narration_billable_upper_bound(text)
    assert upper_bound == 16
    assert await narration.narration_quote_characters(content, user_id=USER_ID) == upper_bound * 2

    async def fitting(user_id, speech):
        return _original(content, duration_s=2.0)

    monkeypatch.setattr(narration_store, "peek_original", fitting)
    assert await narration.narration_quote_characters(content, user_id=USER_ID) == 0

    async def overlong(user_id, speech):
        original = _original(content, duration_s=5.0)
        original["usage_characters"] = 9  # Provider units, not Python len().
        return original

    monkeypatch.setattr(narration_store, "peek_original", overlong)
    assert await narration.narration_quote_characters(content, user_id=USER_ID) == upper_bound


def test_minimax_sentence_envelope_accepts_real_float_millisecond_times():
    cues = _parse_subtitle_cues([
        {
            "text": "先看问题。",
            "pronounce_text": "先看问题。",
            "time_begin": 0.0,
            "time_end": 956.5079365079366,
            "text_begin": 0,
            "text_end": 5,
            "pronounce_text_begin": 0,
            "pronounce_text_end": 5,
            "is_final_segment": True,
        },
    ], source_text="先看问题。")
    assert cues == [{
        "text": "先看问题。", "text_begin": 0, "text_end": 5,
        "time_begin": 0.0, "time_end": 956.5079365079366,
    }]


def test_render_mirror_never_rebills_produce_step_tts():
    payload = {
        "duration_seconds": 8.0,
        "speech_media": {
            "obj_speech": {"usage": {"tts_chars": 9}},
            "obj_other": {"usage": {"tts_chars": 9}},
        },
    }
    assert _render_capture_units(payload) == {"film_seconds": 8.0}


class _World:
    """In-memory effects for prepare_speech_media; no database or HTTP."""

    def __init__(self, monkeypatch, content, *, cached_duration=None, adapted_duration=3.0):
        self.content = content
        self.synth_calls = []
        self.metered = []
        self.cancelled = 0
        self.storage = {}
        self.durations = {b"original": 2.0, b"adapted": adapted_duration}
        self.pending = None
        self.cached = _original(content, cached_duration) if cached_duration is not None else None
        self.adapted_duration = adapted_duration
        monkeypatch.setattr(narration, "decode_duration_s", lambda data: self.durations[data])

        async def save(key, data, content_type=None):
            self.storage[key] = data

        async def exists(key):
            return key in self.storage

        async def read(key):
            return self.storage[key]

        from app.providers import storage, voice
        from app.tools.video import preparation
        from app import metering
        monkeypatch.setattr(storage, "save", save)
        monkeypatch.setattr(storage, "exists", exists)
        monkeypatch.setattr(storage, "read", read)

        def synthesize(text, voice_id, language, speed):
            self.synth_calls.append((text, voice_id, language, speed))
            audio = b"original" if speed == 1.0 else b"adapted"
            return T2AResult(audio, f"https://subtitles/{len(self.synth_calls)}", len(text), f"trace-{len(self.synth_calls)}")

        def subtitles(url, *, source_text):
            duration = self.durations[b"original" if url.endswith("/1") else b"adapted"]
            return _cues(source_text, duration)

        monkeypatch.setattr(voice, "synthesize_detailed", synthesize)
        monkeypatch.setattr(voice, "fetch_subtitle_cues", subtitles)

        async def resolve(user_id, speech, *, execution_id):
            if self.cached is not None:
                return {"state": "done", "original": self.cached}
            return {"state": "needs_audio", "normalized_text": " ".join(speech.text.split())}

        async def complete_audio(user_id, speech, **facts):
            self.storage["narration/original.mp3"] = facts["audio"]
            self.pending = {
                "media": {"storage_key": "narration/original.mp3", "digest": hashlib.sha256(facts["audio"]).hexdigest(), "mime_type": "audio/mpeg"},
                "duration_s": facts["duration_s"],
                "subtitle_file": facts["subtitle_file"],
                "usage_characters": facts["usage_characters"],
                "trace_id": facts["trace_id"],
            }
            return self.pending

        async def complete_alignment(user_id, speech, *, execution_id, cues):
            normalized = " ".join(speech.text.split())
            return {
                **self.pending,
                "normalized_text": normalized,
                "cues": cues,
                "alignment": narration.NARRATION_ALIGNMENT,
                "alignment_digest": narration.narration_alignment_digest(normalized, cues),
                "run_usage": self.pending["usage_characters"],
            }

        async def cancel(*args, **kwargs):
            self.cancelled += 1

        async def unknown(*args, **kwargs):
            raise AssertionError("this test did not submit an uncertain original")

        monkeypatch.setattr(narration_store, "resolve_original", resolve)
        monkeypatch.setattr(narration_store, "complete_audio", complete_audio)
        monkeypatch.setattr(narration_store, "complete_alignment", complete_alignment)
        monkeypatch.setattr(narration_store, "cancel_unsubmitted", cancel)
        monkeypatch.setattr(narration_store, "mark_outcome_unknown", unknown)

        async def store(data, suffix, mime):
            key = f"narration/adapted{suffix}"
            self.storage[key] = data
            return key, hashlib.sha256(data).hexdigest()

        async def meter(units):
            self.metered.append(units)

        monkeypatch.setattr(preparation, "store_source_bytes", store)
        monkeypatch.setattr(metering, "record_media_usage", meter)


@pytest.mark.asyncio
async def test_first_pass_fit_and_execution_resume_submit_one_original(monkeypatch):
    content = narrated_content()
    world = _World(monkeypatch, content)
    policy = NarrationPolicy(max_tts_characters=100)
    first = await narration.prepare_speech_media(
        content, user_id=USER_ID, execution_id=EXECUTION_ID, policy=policy,
    )
    assert len(world.synth_calls) == 1
    assert first["obj_speech"]["state"] == "done"
    assert first["obj_speech"]["speed"] == 1.0
    assert world.metered == [{"tts_chars": float(len("第一句。第二句。"))}]

    resumed = await narration.prepare_speech_media(
        content, user_id=USER_ID, execution_id=EXECUTION_ID, policy=policy,
    )
    assert resumed["obj_speech"]["media"] == first["obj_speech"]["media"]
    assert len(world.synth_calls) == 1
    assert len(world.metered) == 1


@pytest.mark.asyncio
async def test_fixed_original_reuse_across_runs_has_no_new_tts_charge(monkeypatch):
    content = narrated_content()
    world = _World(monkeypatch, content, cached_duration=2.0)
    # A resumed manifest verifies real bytes; provide the shared original.
    world.storage["narration/original.mp3"] = b"cached"
    original = world.cached
    original["media"]["digest"] = hashlib.sha256(b"cached").hexdigest()
    prepared = await narration.prepare_speech_media(
        content, user_id=USER_ID, execution_id=str(uuid4()),
        policy=NarrationPolicy(max_tts_characters=0),
    )
    assert prepared["obj_speech"]["cache_hit"] is True
    assert prepared["obj_speech"]["usage"]["tts_chars"] == 0
    assert world.synth_calls == [] and world.metered == []


@pytest.mark.asyncio
async def test_overlong_adaptation_is_a_paid_terminal_conflict_without_content_changes(monkeypatch):
    content = narrated_content("这是一句明显超过四秒固定镜头长度的旁白。")
    world = _World(monkeypatch, content, adapted_duration=4.2)
    world.durations[b"original"] = 5.0
    before = content.model_dump(mode="json")
    with pytest.raises(narration.NarrationFitError, match="fixed 4.000s window") as caught:
        await narration.prepare_speech_media(
            content, user_id=USER_ID, execution_id=EXECUTION_ID,
            policy=NarrationPolicy(max_tts_characters=100),
        )
    assert len(world.synth_calls) == 2
    assert world.synth_calls[1][3] <= 1.35
    assert "text and cut are unchanged" in str(caught.value)
    assert content.model_dump(mode="json") == before
    manifests = [json.loads(v) for k, v in world.storage.items() if k.endswith("clp_speech.json")]
    assert manifests[-1]["state"] == "conflict"
    assert len(world.metered) == 2


@pytest.mark.asyncio
async def test_budget_refusal_happens_before_the_provider_post(monkeypatch):
    content = narrated_content()
    world = _World(monkeypatch, content)
    with pytest.raises(narration.NarrationBudgetError):
        await narration.prepare_speech_media(
            content, user_id=USER_ID, execution_id=EXECUTION_ID,
            policy=NarrationPolicy(max_tts_characters=1),
        )
    assert world.synth_calls == [] and world.metered == []
    assert world.cancelled == 1


@pytest.mark.asyncio
async def test_submitted_adaptation_recovery_fails_closed_without_another_post(monkeypatch):
    content = narrated_content()
    world = _World(monkeypatch, content)
    clip = next(c for t in content.timeline.tracks for c in t.clips if c.clip_id == "clp_speech")
    policy = NarrationPolicy(max_tts_characters=100)
    key = narration._manifest_key(EXECUTION_ID, clip.clip_id)
    world.storage[key] = json.dumps({
        "execution_id": EXECUTION_ID,
        "state": "submitted",
        "request": narration._request(clip, policy),
    }).encode()
    with pytest.raises(narration_store.NarrationOutcomeUnknown):
        await narration.prepare_speech_media(
            content, user_id=USER_ID, execution_id=EXECUTION_ID, policy=policy,
        )
    assert world.synth_calls == []


@pytest.mark.asyncio
async def test_confirmed_original_audio_resumes_subtitles_without_tts(monkeypatch):
    content = narrated_content()
    world = _World(monkeypatch, content)

    async def needs_alignment(user_id, speech, *, execution_id):
        return {
            "state": "needs_alignment",
            "normalized_text": " ".join(speech.text.split()),
            "audio": {
                "media": {"storage_key": "narration/original.mp3", "digest": "b" * 64, "mime_type": "audio/mpeg"},
                "duration_s": 2.0,
                "subtitle_file": "https://subtitles/1",
                "usage_characters": len(speech.text),
                "trace_id": "trace-existing",
            },
        }

    world.pending = {
        "media": {"storage_key": "narration/original.mp3", "digest": "b" * 64, "mime_type": "audio/mpeg"},
        "duration_s": 2.0,
        "subtitle_file": "https://subtitles/1",
        "usage_characters": len("第一句。第二句。"),
        "trace_id": "trace-existing",
    }
    monkeypatch.setattr(narration_store, "resolve_original", needs_alignment)
    prepared = await narration.prepare_speech_media(
        content, user_id=USER_ID, execution_id=EXECUTION_ID,
        policy=NarrationPolicy(max_tts_characters=0),
    )
    assert prepared["obj_speech"]["state"] == "done"
    assert prepared["obj_speech"]["usage"]["tts_chars"] == len("第一句。第二句。")
    assert world.synth_calls == [] and world.metered == []
