"""Pure tests for the rendered-artifact probe gate (MG D4 — 放行闸③ /
禁止事项 10: 禁无文件校验的成功态 — the load-bearing guard that no render
settles COMPLETED without a file check).

No database, no LLM, no HTTP, NO REAL RENDER — fixtures are tiny MP4s encoded
in-memory by PyAV (a few blank frames; the render service is never involved).
The suite locks: the family dispatch (film = strict expectations read from the
spec's own frames; clip = minimal readability), every failure code's trigger,
the ±1-frame duration tolerance, and the audio-stream expectation (a spec
promising music or narration must render a container WITH an audio stream).
"""

from __future__ import annotations

from pathlib import Path

from app.pipeline.render_probe import (
    FILM_FPS,
    PROBE_AUDIO_MISSING,
    PROBE_CODEC_MISMATCH,
    PROBE_DURATION_MISMATCH,
    PROBE_OUTPUT_MISSING,
    PROBE_RESOLUTION_MISMATCH,
    PROBE_UNREADABLE,
    ProbeExpectation,
    probe_expectation_for,
    probe_rendered_sidecar,
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
    audio: bool = False,
) -> Path:
    """Encode a blank-video MP4 fixture. Real bytes through the real decoder
    stack — the honest stand-in for a render (never a render-service call).
    ``audio=True`` adds a silent AAC track (zero-dependency: planes filled
    with NUL bytes, no numpy)."""
    import av

    container = av.open(str(path), "w")
    stream = container.add_stream(codec, rate=fps)
    stream.width, stream.height = width, height
    stream.pix_fmt = "yuv420p"
    # Both streams must EXIST before the first mux — a stream added after
    # muxing started keeps a zero time_base and its packets fail to rebase.
    astream = container.add_stream("aac", rate=44100) if audio else None
    for _ in range(frames):
        frame = av.VideoFrame(width, height, "yuv420p")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    if astream is not None:
        remaining = int(frames / fps * 44100)
        pts = 0  # samples — PyAV cannot rebase a pts-less packet to zero time
        while remaining > 0:
            n = min(1024, remaining)
            aframe = av.AudioFrame(format="fltp", layout="mono", samples=n)
            aframe.sample_rate = 44100
            aframe.pts = pts
            pts += n
            for plane in aframe.planes:
                plane.update(b"\x00" * plane.buffer_size)
            for packet in astream.encode(aframe):
                # AAC encoder priming: the first packet(s) carry a negative
                # pts (encoder delay) which mp4 cannot mux — drop them; the
                # probe only needs a present, decodable audio stream.
                if packet.pts is None or packet.pts < 0:
                    continue
                container.mux(packet)
            remaining -= n
        for packet in astream.encode():
            if packet.pts is None or packet.pts < 0:
                continue
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


# ---- the audio-stream expectation (Batch 2) ---------------------------------
# The spec's own promises decide: a music bed or any per-scene narration
# ``audio`` key means the rendered container MUST carry an audio stream; a
# silent cut (neither) asserts nothing about audio.


def test_music_or_narration_in_spec_expects_audio() -> None:
    spec = _film_spec([FILM_FPS])
    assert probe_expectation_for(spec).audio is None  # silent cut: unasserted
    with_music = {**spec, "music": {"url": "music/x.mp3", "gain_db": -20.0}}
    assert probe_expectation_for(with_music).audio is True
    with_narration = _film_spec([FILM_FPS])
    with_narration["scenes"][0]["audio"] = "user/out/narr-0.mp3"
    assert probe_expectation_for(with_narration).audio is True


def test_expected_audio_stream_missing_is_rejected(tmp_path: Path) -> None:
    silent = _encode_mp4(tmp_path / "silent.mp4", frames=FILM_FPS)
    expect = probe_expectation_for({**_film_spec([FILM_FPS]), "music": {"url": "m.mp3"}})
    violations = probe_rendered_video(silent, expect)
    assert PROBE_AUDIO_MISSING in _codes(violations)


def test_expected_audio_stream_present_passes(tmp_path: Path) -> None:
    sounded = _encode_mp4(tmp_path / "sounded.mp4", frames=FILM_FPS, audio=True)
    expect = probe_expectation_for({**_film_spec([FILM_FPS]), "music": {"url": "m.mp3"}})
    assert probe_rendered_video(sounded, expect) == []


def test_silent_cut_never_asserts_audio(tmp_path: Path) -> None:
    # A spec promising neither music nor narration: the audio check stays out
    # either way (a silent film is a legal film).
    silent = _encode_mp4(tmp_path / "silent.mp4", frames=FILM_FPS)
    sounded = _encode_mp4(tmp_path / "sounded.mp4", frames=FILM_FPS, audio=True)
    expect = probe_expectation_for(_film_spec([FILM_FPS]))
    assert probe_rendered_video(silent, expect) == []
    assert probe_rendered_video(sounded, expect) == []


# ---- clip family (minimal checks, same seat) ----------------------------------


def test_clip_artifact_passes_with_minimal_expectation(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "clip.mp4", width=1080, height=1920, frames=45)
    assert probe_rendered_video(video, probe_expectation_for({})) == []


def test_clip_family_still_rejects_garbage(tmp_path: Path) -> None:
    garbage = tmp_path / "clip.mp4"
    garbage.write_bytes(b"not a video at all" * 16)
    assert PROBE_UNREADABLE in _codes(probe_rendered_video(garbage, ProbeExpectation()))


# ---- the caption sidecar (clip family companion) ------------------------------
# The law: existence always; the non-empty bar applies iff the caption track
# carries cues (the render service writes captionTrackToSrt([]) == "" — an
# empty srt is a VALID artifact for a captionless clip, never a gate failure).


def test_sidecar_present_and_nonzero_passes(tmp_path: Path) -> None:
    srt = tmp_path / "clip.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    assert probe_rendered_sidecar(srt, allow_empty=False) == []


def test_sidecar_missing_is_rejected_either_way(tmp_path: Path) -> None:
    assert _codes(probe_rendered_sidecar(None, allow_empty=True)) == {PROBE_OUTPUT_MISSING}
    assert _codes(probe_rendered_sidecar(tmp_path / "nope.srt", allow_empty=False)) == {
        PROBE_OUTPUT_MISSING
    }


def test_sidecar_empty_with_cues_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.srt"
    empty.write_bytes(b"")
    assert _codes(probe_rendered_sidecar(empty, allow_empty=False)) == {
        PROBE_OUTPUT_MISSING
    }


def test_sidecar_empty_without_cues_is_a_valid_artifact(tmp_path: Path) -> None:
    # captionTrackToSrt([]) == "" — a captionless clip's zero-byte srt is legal.
    empty = tmp_path / "empty.srt"
    empty.write_bytes(b"")
    assert probe_rendered_sidecar(empty, allow_empty=True) == []
