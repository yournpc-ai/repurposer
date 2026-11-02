"""Pure deterministic Output signal checks; no DB, LLM, HTTP or renderer."""
from __future__ import annotations

import io
import math
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw
from test_render_probe_pure import _encode_mp4

from app.tools.video.output_checks import (
    FrameSample,
    inspect_frame_samples,
    inspect_output_audio,
)


def _spec(*, audio: bool) -> dict:
    return {
        "family": "video",
        "fps": {"num": 30, "den": 1},
        "duration_frames": 30,
        "tracks": [{"kind": "audio", "clips": [{"clip_id": "aud"}]}] if audio else [],
    }


def _jpeg(*, flat: bool) -> bytes:
    image = Image.new("RGB", (32, 32), "white")
    if not flat:
        ImageDraw.Draw(image).rectangle((4, 4, 27, 27), fill="black")
    out = io.BytesIO()
    image.save(out, "JPEG")
    return out.getvalue()


def _wav(*, amplitude: float, seconds: float = 1.0) -> bytes:
    rate = 22050
    count = int(rate * seconds)
    t = np.arange(count, dtype=np.float64) / rate
    pcm = np.round(np.sin(2 * math.pi * 440 * t) * amplitude * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm.tobytes())
    return out.getvalue()


def test_flat_and_repeated_samples_are_candidates_not_delivery_failures():
    blank = _jpeg(flat=True)
    inspection = inspect_frame_samples([
        FrameSample(0, 0.0, blank),
        FrameSample(30, 1.0, _jpeg(flat=False)),
        FrameSample(60, 2.0, blank),
    ])

    assert inspection.sampled_frames == 3
    assert [item.frame for item in inspection.flat_frame_candidates] == [0, 60]
    assert len(inspection.repeated_frame_groups) == 1
    assert inspection.repeated_frame_groups[0].times_seconds == [0.0, 2.0]


def test_expected_audio_stream_is_not_confused_with_audible_audio():
    audio, issues = inspect_output_audio(_wav(amplitude=0.0), _spec(audio=True))

    assert audio.present is True and audio.decode_ok is True
    assert audio.scope == "full_stream"
    assert audio.integrated_lufs is None
    assert {issue.code for issue in issues} == {"AUDIO_SILENT"}


def test_silent_delivery_without_an_audio_requirement_is_legal():
    audio, issues = inspect_output_audio(_wav(amplitude=0.0), _spec(audio=False))

    assert audio.expected is False and audio.present is True
    assert issues == []


def test_missing_expected_audio_is_a_deterministic_issue(tmp_path: Path):
    video = _encode_mp4(tmp_path / "missing.mp4", frames=30, audio=False).read_bytes()
    audio, issues = inspect_output_audio(video, _spec(audio=True))

    assert audio.present is False and audio.decode_ok is False
    assert [issue.code for issue in issues] == ["AUDIO_MISSING"]


def test_full_stream_tone_has_real_rms_and_peak_measurements():
    audio, issues = inspect_output_audio(_wav(amplitude=0.25), _spec(audio=True))

    assert audio.present is True and audio.decode_ok is True
    assert audio.samples == 22050
    assert audio.duration_seconds == 1.0
    assert audio.rms_dbfs == pytest.approx(-15.05, abs=0.15)
    assert audio.peak_dbfs == pytest.approx(-12.04, abs=0.15)
    assert issues == []


def test_quiet_and_clipping_signals_have_distinct_issue_codes():
    _, quiet_issues = inspect_output_audio(_wav(amplitude=0.0001), _spec(audio=True))
    _, clipped_issues = inspect_output_audio(_wav(amplitude=1.0), _spec(audio=True))

    assert [issue.code for issue in quiet_issues] == ["AUDIO_QUIET"]
    assert [issue.code for issue in clipped_issues] == ["AUDIO_CLIPPED"]


def test_unreadable_media_does_not_invent_audio_absence():
    audio, issues = inspect_output_audio(b"not a media container", _spec(audio=True))

    assert audio.present is None and audio.decode_ok is False
    assert [issue.code for issue in issues] == ["AUDIO_DECODE_FAILED"]
