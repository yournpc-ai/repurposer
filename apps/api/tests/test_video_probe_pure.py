"""Probe-gate expectations for the video family (ADR-145; the gate itself is
the shared render_probe seat — MG D4 放行闸③, one gate, family dispatch).

Fixtures are PyAV-encoded in-memory MP4s (never a real render), same posture
as test_render_probe_pure.py. Locks: expectation reads the spec's own
quantized facts (frames / width / height / rational fps), the audio-stream
expectation follows the presence of audio clips, and every mismatch code
bites.
"""

from __future__ import annotations

from pathlib import Path

from app.pipeline.render_probe import (
    PROBE_AUDIO_MISSING,
    PROBE_DURATION_MISMATCH,
    PROBE_RESOLUTION_MISMATCH,
    probe_expectation_for,
    probe_rendered_video,
)
from test_render_probe_pure import _encode_mp4


def _spec(*, frames: int = 120, audio: bool = True) -> dict:
    tracks = [
        {
            "track_id": "trk_main",
            "kind": "visual",
            "role": "main",
            "order": 0,
            "clips": [],
        }
    ]
    if audio:
        tracks.append(
            {
                "track_id": "trk_music",
                "kind": "audio",
                "role": "music",
                "order": 0,
                "clips": [{"clip_id": "clp_bed"}],
            }
        )
    return {
        "family": "video",
        "fps": {"num": 30, "den": 1},
        "width": 1920,
        "height": 1080,
        "duration_frames": frames,
        "tracks": tracks,
    }


def test_expectation_reads_spec_facts():
    expect = probe_expectation_for(_spec())
    assert expect.codec == "h264"
    assert (expect.width, expect.height) == (1920, 1080)
    assert expect.frames == 120
    assert expect.fps == 30.0
    assert expect.audio is True


def test_silent_cut_asserts_no_audio():
    assert probe_expectation_for(_spec(audio=False)).audio is None


def test_unmuted_video_object_promises_original_audio_without_an_audio_track():
    spec = _spec(audio=False)
    spec["tracks"][0]["clips"] = [{
        "clip_id": "clp_video",
        "object": {"kind": "video", "muted": False},
    }]
    assert probe_expectation_for(spec).audio is True
    spec["tracks"][0]["clips"][0]["object"]["muted"] = True
    assert probe_expectation_for(spec).audio is None


def test_fractional_fps_expectation():
    expect = probe_expectation_for({**_spec(), "fps": {"num": 30000, "den": 1001}})
    assert abs(expect.fps - 29.970) < 0.001


def test_passing_render(tmp_path: Path):
    path = _encode_mp4(tmp_path / "ok.mp4", frames=120, audio=True)
    assert probe_rendered_video(path, probe_expectation_for(_spec())) == []


def test_duration_mismatch_bites(tmp_path: Path):
    path = _encode_mp4(tmp_path / "short.mp4", frames=60, audio=True)
    codes = {v.code for v in probe_rendered_video(path, probe_expectation_for(_spec()))}
    assert PROBE_DURATION_MISMATCH in codes


def test_resolution_mismatch_bites(tmp_path: Path):
    path = _encode_mp4(tmp_path / "small.mp4", width=1280, height=720, frames=120, audio=True)
    codes = {v.code for v in probe_rendered_video(path, probe_expectation_for(_spec()))}
    assert PROBE_RESOLUTION_MISMATCH in codes


def test_promised_audio_missing_bites(tmp_path: Path):
    path = _encode_mp4(tmp_path / "silent.mp4", frames=120, audio=False)
    codes = {v.code for v in probe_rendered_video(path, probe_expectation_for(_spec()))}
    assert PROBE_AUDIO_MISSING in codes
