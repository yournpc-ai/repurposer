"""Pure tests for the rendered-artifact probe gate (MG D4 — 放行闸③ /
禁止事项 10: 禁无文件校验的成功态 — the load-bearing guard that no render
settles COMPLETED without a file check).

No database, no LLM, no HTTP, NO REAL RENDER — fixtures are tiny MP4s encoded
in-memory by PyAV (a few blank frames; the render service is never involved).
The suite locks: the family dispatch (film = strict expectations read from the
spec's own frames; clip = minimal readability), every failure code's trigger,
and the ±1-frame duration tolerance.
"""

from __future__ import annotations

from pathlib import Path

from app.pipeline.render_probe import (
    FILM_FPS,
    PROBE_CODEC_MISMATCH,
    PROBE_DURATION_MISMATCH,
    PROBE_OUTPUT_MISSING,
    PROBE_RESOLUTION_MISMATCH,
    PROBE_UNREADABLE,
    ProbeExpectation,
    probe_expectation_for,
    probe_rendered_text,
    probe_rendered_video,
)


def _encode_mp4(
    path: Path,
    *,
    codec: str = "h264",
    width: int = 1920,
    height: int = 1080,
    frames: int = FILM_FPS,  # exactly 1.0s at the fixed film fps
    fps: int = FILM_FPS,
) -> Path:
    """Encode a blank-video MP4 fixture. Real bytes through the real decoder
    stack — the honest stand-in for a render (never a render-service call)."""
    import av

    container = av.open(str(path), "w")
    stream = container.add_stream(codec, rate=fps)
    stream.width, stream.height = width, height
    stream.pix_fmt = "yuv420p"
    for _ in range(frames):
        frame = av.VideoFrame(width, height, "yuv420p")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


def _film_spec(frames: list[int]) -> dict:
    return {
        "family": "film",
        "theme": {"canvas": "#F7F6F2", "ink": "#141414"},
        "scenes": [{"type": "words", "frames": n, "dark": False, "lines": ["x"]} for n in frames],
    }


def _codes(violations) -> set[str]:
    return {v.code for v in violations}


# ---- the family dispatch (one seat, check items read only spec.family) ------


def test_film_expectation_reads_frames_off_the_spec() -> None:
    expect = probe_expectation_for(_film_spec([90, 60]))  # 150 frames = 5.0s @30fps
    assert expect.codec == "h264"
    assert (expect.width, expect.height) == (1920, 1080)
    assert expect.frames == 150
    assert expect.fps == FILM_FPS


def test_clip_family_gets_the_minimal_expectation() -> None:
    for clip_like in ({}, {"family": "clip"}, {"source": {"url": "k"}}):
        expect = probe_expectation_for(clip_like)
        assert expect == ProbeExpectation()


def test_film_spec_without_frames_degrades_the_duration_check() -> None:
    expect = probe_expectation_for({"family": "film", "scenes": [{"type": "words"}]})
    assert expect.frames is None  # codec/resolution still asserted


# ---- existence / readability (both families) ---------------------------------


def test_missing_file_is_not_a_success(tmp_path: Path) -> None:
    violations = probe_rendered_video(tmp_path / "nope.mp4", ProbeExpectation())
    assert _codes(violations) == {PROBE_OUTPUT_MISSING}


def test_none_path_is_not_a_success() -> None:
    assert _codes(probe_rendered_video(None, ProbeExpectation())) == {PROBE_OUTPUT_MISSING}


def test_zero_byte_file_is_not_a_success(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    assert _codes(probe_rendered_video(empty, ProbeExpectation())) == {PROBE_OUTPUT_MISSING}


def test_truncated_garbage_is_unreadable(tmp_path: Path) -> None:
    garbage = tmp_path / "cut.mp4"
    garbage.write_bytes(b"\x00\x00\x00\x1cftypmp42" + b"\xff" * 64)
    assert PROBE_UNREADABLE in _codes(probe_rendered_video(garbage, ProbeExpectation()))


# ---- film-family strict items -------------------------------------------------


def test_clean_film_artifact_passes(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "film.mp4", frames=2 * FILM_FPS)  # 2.0s
    expect = probe_expectation_for(_film_spec([FILM_FPS, FILM_FPS]))
    assert probe_rendered_video(video, expect) == []


def test_wrong_codec_is_rejected(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "mpeg4.mp4", codec="mpeg4", frames=FILM_FPS)
    expect = probe_expectation_for(_film_spec([FILM_FPS]))
    assert PROBE_CODEC_MISMATCH in _codes(probe_rendered_video(video, expect))


def test_wrong_resolution_is_rejected(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "small.mp4", width=640, height=360, frames=FILM_FPS)
    expect = probe_expectation_for(_film_spec([FILM_FPS]))
    assert PROBE_RESOLUTION_MISMATCH in _codes(probe_rendered_video(video, expect))


def test_duration_drift_beyond_one_frame_is_rejected(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "long.mp4", frames=3 * FILM_FPS)  # 3.0s
    expect = probe_expectation_for(_film_spec([2 * FILM_FPS]))  # allocated 2.0s
    assert PROBE_DURATION_MISMATCH in _codes(probe_rendered_video(video, expect))


def test_duration_within_one_frame_passes(tmp_path: Path) -> None:
    # 61 frames ≈ 2.033s vs an allocated 2.0s — exactly the ±1-frame lane.
    video = _encode_mp4(tmp_path / "ok.mp4", frames=2 * FILM_FPS + 1)
    expect = probe_expectation_for(_film_spec([2 * FILM_FPS]))
    assert probe_rendered_video(video, expect) == []


# ---- clip family (minimal checks, same seat) ----------------------------------


def test_clip_artifact_passes_with_minimal_expectation(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "clip.mp4", width=1080, height=1920, frames=45)
    assert probe_rendered_video(video, probe_expectation_for({})) == []


def test_clip_family_still_rejects_garbage(tmp_path: Path) -> None:
    garbage = tmp_path / "clip.mp4"
    garbage.write_bytes(b"not a video at all" * 16)
    assert PROBE_UNREADABLE in _codes(probe_rendered_video(garbage, ProbeExpectation()))


# ---- the caption sidecar (clip family companion) ------------------------------


def test_sidecar_present_and_nonzero_passes(tmp_path: Path) -> None:
    srt = tmp_path / "clip.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    assert probe_rendered_text(srt) == []


def test_sidecar_missing_or_empty_is_rejected(tmp_path: Path) -> None:
    assert _codes(probe_rendered_text(tmp_path / "nope.srt")) == {PROBE_OUTPUT_MISSING}
    empty = tmp_path / "empty.srt"
    empty.write_bytes(b"")
    assert _codes(probe_rendered_text(empty)) == {PROBE_OUTPUT_MISSING}
