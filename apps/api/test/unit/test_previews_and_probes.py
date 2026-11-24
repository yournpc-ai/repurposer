"""Layer 0 pure contracts: bounded scrub previews, rendered-artifact probe gate, and output signal checks."""

from __future__ import annotations
import pytest

from copy import deepcopy


from types import SimpleNamespace


from uuid import UUID


import pytest


from test.support.composition_fixtures import FOUR_S_TICKS, SNAPSHOT_FACTS, valid_content


from app.editing.schemas import (
    CaptionDerivation,
    GeneratedImageOutput,
    GeneratorObject,
    LayoutBox,
    ProgramOutput,
    VideoObject,
    WebObject,
)


from app.models.schemas import VideoObjectScrubTarget, VideoSegmentScrubTarget


from app.tools.video.preview import (
    ScrubTargetError,
    compile_video_scrub,
    project_video_scrub,
    revision_scrub_affected,
    source_geometry,
)


COMP_ID = UUID("33333333-3333-3333-3333-333333333333")


VER_ID = UUID("44444444-4444-4444-4444-444444444444")


OBJECT_TARGET = VideoObjectScrubTarget(object_id="obj_title")


def compile_preview(content=None, generator_media=None, target=OBJECT_TARGET):
    content = content or valid_content()
    return compile_video_scrub(
        content,
        SNAPSHOT_FACTS,
        composition_id=COMP_ID,
        version_id=VER_ID,
        content_digest="c" * 64,
        target=target,
        generator_media=generator_media or {},
    )


def test_object_scrub_compiles_only_that_object_with_exact_provenance():
    result = compile_preview()
    assert result["status"] == "ready"
    spec = result["video_spec"]
    assert spec["provenance"] == {
        "composition_id": str(COMP_ID),
        "composition_version_id": str(VER_ID),
        "content_digest": "c" * 64,
    }
    clips = [clip for track in spec["tracks"] for clip in track["clips"]]
    assert [clip["clip_id"] for clip in clips] == ["clp_title"]
    assert clips[0]["start_frame"] == 0
    assert spec["duration_frames"] == 90
    assert result["scope"]["isolated_object"] is True
    assert result["scope"]["target"] == {"kind": "object", "object_id": "obj_title"}


def test_segment_scrub_rebases_time_and_preserves_frame_sampled_animation():
    result = compile_preview(target=VideoSegmentScrubTarget(
        clip_id="clp_title", start_seconds=1.5, end_seconds=2.5,
    ))
    assert result["status"] == "ready"
    spec = result["video_spec"]
    assert spec["duration_frames"] == 30
    clips = [clip for track in spec["tracks"] for clip in track["clips"]]
    assert {clip["clip_id"] for clip in clips} == {"clp_bg", "clp_title", "clp_bed"}
    assert all(clip["start_frame"] == 0 for clip in clips)
    title = next(clip for clip in clips if clip["clip_id"] == "clp_title")
    assert all(keyframe["at"] >= 0 for animation in title["animations"] for keyframe in animation["keyframes"])
    audio = next(clip for clip in clips if clip["clip_id"] == "clp_bed")
    assert audio["source"]["start_frame"] == 45
    assert audio["source"]["end_frame"] == 75
    assert result["scope"]["source_range_seconds"] == {"start": 1.5, "end": 2.5}


def test_full_timeline_segment_is_refused_even_when_explicitly_requested():
    with pytest.raises(ScrubTargetError, match="cannot contain the complete video"):
        project_video_scrub(valid_content(), VideoSegmentScrubTarget(
            scene_id="scn_open", start_seconds=0, end_seconds=4,
        ))


def test_revision_scrub_must_intersect_the_server_computed_delta():
    read = {
        "storyboard": {
            "scenes": [{
                "scene_id": "scn_open",
                "clips": [
                    {"clip_id": "clp_title", "object_id": "obj_title"},
                    {"clip_id": "clp_other", "object_id": "obj_other"},
                ],
            }],
            "unassigned_clips": [],
        },
        "change_set": {
            "clips": {"added": [], "updated": [{"clip_id": "clp_title"}]},
            "scenes": {"added": [], "moved": []},
        },
    }
    assert revision_scrub_affected(read, OBJECT_TARGET)
    assert revision_scrub_affected(read, VideoSegmentScrubTarget(
        scene_id="scn_open", start_seconds=1, end_seconds=2,
    ))
    assert not revision_scrub_affected(read, VideoObjectScrubTarget(object_id="obj_other"))
    assert not revision_scrub_affected(read, VideoSegmentScrubTarget(
        clip_id="clp_other", start_seconds=1, end_seconds=2,
    ))


def test_unrelated_pending_media_does_not_block_an_isolated_object():
    content = valid_content()
    clip = content.timeline.tracks[0].clips[0]
    clip.object = GeneratorObject(
        kind="generator",
        object_id="obj_paid_image",
        producer="image-generation",
        prompt="A fixed product background",
        provider="minimax",
        model="image-01",
        output=GeneratedImageOutput(),
        layout=clip.object.layout,
    )
    clip.source = None
    assert compile_preview(content)["status"] == "ready"


def test_targeted_unpaid_generated_image_is_pending_not_a_partial_spec():
    content = valid_content()
    clip = content.timeline.tracks[0].clips[0]
    clip.object = GeneratorObject(
        kind="generator",
        object_id="obj_paid_image",
        producer="image-generation",
        prompt="A fixed product background",
        provider="minimax",
        model="image-01",
        output=GeneratedImageOutput(),
        layout=clip.object.layout,
    )
    clip.source = None
    result = compile_preview(content, target=VideoObjectScrubTarget(object_id="obj_paid_image"))
    assert result["status"] == "pending_media"
    assert result["pending"] == [{
        "clip_id": clip.clip_id,
        "object_id": "obj_paid_image",
        "kind": "image-generation",
    }]
    assert "video_spec" not in result


def test_source_aligned_derived_caption_compiles_without_hidden_media_work():
    content = valid_content()
    title = content.timeline.tracks[1].clips[0]
    title.object.caption = CaptionDerivation(
        speech_object_id="obj_source_speech",
        source_text_digest="d" * 64,
        alignment="faster-whisper-script-v1",
    )
    result = compile_preview(content)
    assert result["status"] == "ready"
    assert any(
        clip["clip_id"] == title.clip_id
        for track in result["video_spec"]["tracks"]
        for clip in track["clips"]
    )


def test_missing_fixed_generator_media_fails_closed():
    content = valid_content()
    clip = content.timeline.tracks[0].clips[0]
    generator = GeneratorObject(
        kind="generator",
        object_id="obj_fixed_program",
        producer="draw-2d",
        code="function render(ctx) { return []; }",
        output=ProgramOutput(
            width=640, height=360, fps=15, duration_frames=30, background="#000000"
        ),
        layout=clip.object.layout,
    )
    clip.object = generator
    clip.source = None
    result = compile_preview(
        content,
        {generator.object_id: {"program_digest": "0" * 64}},
        target=VideoObjectScrubTarget(object_id=generator.object_id),
    )
    assert result["status"] == "unavailable"
    assert result["reason"] == "fixed_generator_media_unavailable"
    assert result["clip_ids"] == [clip.clip_id]


def two_scene_content():
    content = deepcopy(valid_content())
    second_scene = deepcopy(content.scenes[0])
    second_scene.scene_id = "scn_second"
    second_scene.range.start = FOUR_S_TICKS
    second_scene.range.end = FOUR_S_TICKS * 2
    content.scenes.append(second_scene)
    for track in content.timeline.tracks:
        if track.kind != "visual":
            continue
        additions = []
        for original in track.clips:
            clip = original.model_copy(deep=True)
            clip.clip_id += "_second"
            clip.scene_id = "scn_second"
            clip.range.start += FOUR_S_TICKS
            clip.range.end += FOUR_S_TICKS
            clip.object.object_id += "_second"
            for animation in clip.animations:
                animation.target_object_id = clip.object.object_id
            additions.append(clip)
        track.clips.extend(additions)
    return content


def test_saved_preview_compiles_one_scene_and_the_immediate_join():
    content = two_scene_content()
    _, first_scope = project_video_scrub(content, VideoSegmentScrubTarget(
        scene_id="scn_open", start_seconds=0, end_seconds=4,
    ))
    assert first_scope["clip_ids"] == ["clp_bed", "clp_bg", "clp_title"]
    result = compile_video_scrub(
        content,
        SNAPSHOT_FACTS,
        composition_id=COMP_ID,
        version_id=VER_ID,
        content_digest="c" * 64,
        target=VideoSegmentScrubTarget(scene_id="scn_second", start_seconds=0, end_seconds=8),
        generator_media={},
        allow_outside_target=True,
        allow_complete=True,
    )
    assert result["status"] == "ready"
    assert result["video_spec"]["duration_frames"] == 240
    assert result["scope"]["clip_ids"] == [
        "clp_bed", "clp_bg", "clp_bg_second", "clp_title", "clp_title_second",
    ]
    with pytest.raises(ScrubTargetError, match="window must stay inside"):
        project_video_scrub(content, VideoSegmentScrubTarget(
            scene_id="scn_open", start_seconds=0, end_seconds=5,
        ))


def test_saved_playback_preserves_empty_time_and_transition_boundaries():
    from app.editing.schemas import Transition
    from app.models.schemas import VideoRangeScrubTarget

    content = valid_content()
    main_track = content.timeline.tracks[0]
    content.timeline.tracks = [main_track]
    left = main_track.clips[0]
    right = left.model_copy(deep=True)
    right.clip_id, right.object.object_id = "right", "right-image"
    left.range.end, right.range.start = 90000, 270000
    main_track.clips.append(right)

    def play(start, end):
        result = compile_preview(content, target=VideoRangeScrubTarget(start_seconds=start, end_seconds=end))
        assert result["status"] == "ready"
        return result["video_spec"]

    assert play(0, 4)["duration_frames"] == 120
    gap = play(1, 3)
    assert gap["duration_frames"] == 60 and gap["tracks"][0]["clips"] == []
    tail_gap = play(0.5, 2)
    assert tail_gap["duration_frames"] == 45 and tail_gap["tracks"][0]["clips"][0]["end_frame"] == 15
    right.range.start = left.range.end
    content.timeline.transitions = [Transition(transition_id="dissolve", from_clip_id=left.clip_id,
                                               to_clip_id=right.clip_id, duration=36000)]
    with pytest.raises(ScrubTargetError, match="complete transition"):
        play(1, 2)


def test_source_geometry_distinguishes_borders_from_actual_source_clipping():
    content = valid_content()
    content.settings.width, content.settings.height = 320, 180
    clip = content.timeline.tracks[0].clips[0]
    clip.object = VideoObject(
        kind="video", object_id="obj_video",
        layout=LayoutBox(x=0, y=0, width=320, height=180), fit="contain",
    )
    clip.animations = []

    facts = source_geometry(content, clip, 240, 216)
    assert facts["source_bounds_canvas_px"] == [60.0, 0.0, 260.0, 180.0]
    assert facts["source_visible_bounds_canvas_px"] == [60.0, 0.0, 260.0, 180.0]
    assert facts["source_clipped_px"] == {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
    assert facts["canvas_borders_px"] == {"left": 60.0, "top": 0.0, "right": 60.0, "bottom": 0.0}
    assert facts["whole_source_inside_canvas"] is True

    clip.object.transform.x, clip.object.transform.y, clip.object.transform.scale = -8.0, 18.0, 1.55
    facts = source_geometry(content, clip, 544, 960)
    assert facts["source_bounds_canvas_px"] == [72.95, -31.5, 231.05, 247.5]
    assert facts["source_visible_bounds_canvas_px"] == [72.95, 0.0, 231.05, 180.0]
    assert facts["source_clipped_px"] == {"left": 0.0, "top": 31.5, "right": 0.0, "bottom": 67.5}
    assert facts["canvas_borders_px"] == {"left": 72.95, "top": 0.0, "right": 88.95, "bottom": 0.0}
    assert facts["whole_source_inside_canvas"] is False


def test_face_geometry_reports_actual_face_and_context_clipping():
    from app.tools.video.preview import face_geometry

    content = valid_content()
    content.settings.width, content.settings.height = 320, 180
    clip = content.timeline.tracks[0].clips[0]
    clip.object = VideoObject(
        kind="video", object_id="obj_video",
        layout=LayoutBox(x=0, y=0, width=320, height=180), fit="contain",
    )
    clip.animations = []
    clip.object.transform.x, clip.object.transform.y, clip.object.transform.scale = -6.0, 20.0, 1.8
    geometry = {**source_geometry(content, clip, 544, 960), "source_pixels": [544, 960]}
    face = face_geometry((150, 0, 150, 220), 0.92, geometry)
    assert face["canvas_clipped_px"] == {"left": 0.0, "top": 52.0, "right": 0.0, "bottom": 0.0}
    assert face["face_fully_visible"] is False
    assert face["expanded_face_fully_visible"] is False
    assert face["confidence"] == 0.92

    clip.object.transform.x, clip.object.transform.y, clip.object.transform.scale = 0.0, 0.0, 1.0
    geometry = {**source_geometry(content, clip, 544, 960), "source_pixels": [544, 960]}
    face = face_geometry((150, 10, 150, 220), 0.92, geometry)
    assert face["face_fully_visible"] is True
    assert face["expanded_face_fully_visible"] is True


def test_preview_samples_include_motion_boundaries_without_unbounded_reads():
    from app.tools.video.preview import preview_sample_frames

    assert preview_sample_frames([(0, 60)]) == [0, 29, 59]
    assert len(preview_sample_frames([(0, 60), (60, 120)])) == 6
    assert preview_sample_frames([(0, 30), (30, 60), (60, 90)]) == [14, 44, 74]
    assert len(preview_sample_frames([(index * 30, (index + 1) * 30) for index in range(12)])) == 6


def test_sampled_frame_facts_distinguish_static_source_from_rendered_movement():
    import io
    from PIL import Image
    from app.tools.video.preview import sampled_frame_facts

    frames = []
    for x, seconds in [(0, 0.0), (0, 1.0), (3, 1.966667)]:
        encoded = io.BytesIO()
        image = Image.new("RGB", (32, 18), "white")
        image.paste((0, 0, 0), (x, 0, x + 8, 18))
        image.save(encoded, format="JPEG")
        frames.append((encoded.getvalue(), seconds))
    facts = sampled_frame_facts(frames, background="#000000")
    assert facts[0]["edges_matching_canvas_color_px"]["left"] == 8
    assert facts[2]["edges_matching_canvas_color_px"]["left"] == 0
    assert facts[0]["pixel_difference_from_previous_bbox_px"] is None
    assert facts[1]["pixel_difference_from_previous_bbox_px"] == []
    assert facts[2]["pixel_difference_from_previous_bbox_px"] == [0, 0, 16, 18]
    assert [fact["seconds"] for fact in facts] == [0.0, 1.0, 1.966667]
    assert len({fact["jpeg_sha256"] for fact in facts}) == 2


# --- Rendered-artifact probe gate ---

from pathlib import Path


from app.pipeline.render_probe import (
    DEFAULT_FPS,
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
    frames: int = DEFAULT_FPS,  # exactly 1.0s at the default fps
    fps: int = DEFAULT_FPS,
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
    if codec == "h264":
        stream.options = {"preset": "ultrafast", "tune": "zerolatency"}
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


def _video_spec(frames: list[int], *, audio: bool = False) -> dict:
    return {
        "family": "video",
        "duration_frames": sum(frames),
        "width": 1920,
        "height": 1080,
        "fps": {"num": DEFAULT_FPS, "den": 1},
        "tracks": [{"kind": "audio", "clips": [{"clip_id": "a"}]}] if audio else [],
    }


def _codes(violations) -> set[str]:
    return {v.code for v in violations}


def test_video_expectation_reads_frames_off_the_spec() -> None:
    expect = probe_expectation_for(_video_spec([90, 60]))  # 150 frames = 5.0s @30fps
    assert expect.codec == "h264"
    assert (expect.width, expect.height) == (1920, 1080)
    assert expect.frames == 150
    assert expect.fps == DEFAULT_FPS


def test_clip_family_gets_the_minimal_expectation() -> None:
    for clip_like in ({}, {"family": "clip"}, {"source": {"url": "k"}}):
        expect = probe_expectation_for(clip_like)
        assert expect == ProbeExpectation()


def test_video_spec_without_frames_degrades_the_duration_check() -> None:
    expect = probe_expectation_for({"family": "video", "tracks": []})
    assert expect.frames is None  # codec/resolution still asserted


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


def test_clean_video_artifact_passes(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "video.mp4", frames=2 * DEFAULT_FPS)  # 2.0s
    expect = probe_expectation_for(_video_spec([DEFAULT_FPS, DEFAULT_FPS]))
    assert probe_rendered_video(video, expect) == []


def test_wrong_codec_is_rejected(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "mpeg4.mp4", codec="mpeg4", frames=DEFAULT_FPS)
    expect = probe_expectation_for(_video_spec([DEFAULT_FPS]))
    assert PROBE_CODEC_MISMATCH in _codes(probe_rendered_video(video, expect))


def test_wrong_resolution_is_rejected(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "small.mp4", width=640, height=360, frames=DEFAULT_FPS)
    expect = probe_expectation_for(_video_spec([DEFAULT_FPS]))
    assert PROBE_RESOLUTION_MISMATCH in _codes(probe_rendered_video(video, expect))


def test_duration_drift_beyond_one_frame_is_rejected(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "long.mp4", frames=3 * DEFAULT_FPS)  # 3.0s
    expect = probe_expectation_for(_video_spec([2 * DEFAULT_FPS]))  # allocated 2.0s
    assert PROBE_DURATION_MISMATCH in _codes(probe_rendered_video(video, expect))


def test_duration_within_one_frame_passes(tmp_path: Path) -> None:
    # 61 frames ≈ 2.033s vs an allocated 2.0s — exactly the ±1-frame lane.
    video = _encode_mp4(tmp_path / "ok.mp4", frames=2 * DEFAULT_FPS + 1)
    expect = probe_expectation_for(_video_spec([2 * DEFAULT_FPS]))
    assert probe_rendered_video(video, expect) == []


def test_video_audio_track_sets_the_audio_expectation() -> None:
    assert probe_expectation_for(_video_spec([DEFAULT_FPS])).audio is None
    assert probe_expectation_for(_video_spec([DEFAULT_FPS], audio=True)).audio is True


def test_expected_audio_stream_missing_is_rejected(tmp_path: Path) -> None:
    silent = _encode_mp4(tmp_path / "silent.mp4", frames=DEFAULT_FPS)
    expect = probe_expectation_for(_video_spec([DEFAULT_FPS], audio=True))
    violations = probe_rendered_video(silent, expect)
    assert PROBE_AUDIO_MISSING in _codes(violations)


def test_expected_audio_stream_present_passes(tmp_path: Path) -> None:
    sounded = _encode_mp4(tmp_path / "sounded.mp4", frames=DEFAULT_FPS, audio=True)
    expect = probe_expectation_for(_video_spec([DEFAULT_FPS], audio=True))
    assert probe_rendered_video(sounded, expect) == []


def test_silent_cut_never_asserts_audio(tmp_path: Path) -> None:
    # A spec promising neither music nor narration: the audio check stays out
    # either way (a silent video is a legal video).
    silent = _encode_mp4(tmp_path / "silent.mp4", frames=DEFAULT_FPS)
    sounded = _encode_mp4(tmp_path / "sounded.mp4", frames=DEFAULT_FPS, audio=True)
    expect = probe_expectation_for(_video_spec([DEFAULT_FPS]))
    assert probe_rendered_video(silent, expect) == []
    assert probe_rendered_video(sounded, expect) == []


def test_clip_artifact_passes_with_minimal_expectation(tmp_path: Path) -> None:
    video = _encode_mp4(tmp_path / "clip.mp4", width=1080, height=1920, frames=45)
    assert probe_rendered_video(video, probe_expectation_for({})) == []


def test_clip_family_still_rejects_garbage(tmp_path: Path) -> None:
    garbage = tmp_path / "clip.mp4"
    garbage.write_bytes(b"not a video at all" * 16)
    assert PROBE_UNREADABLE in _codes(probe_rendered_video(garbage, ProbeExpectation()))


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


# --- Output audio/video signal checks ---

import io


import math


import wave


from pathlib import Path


import numpy as np


import pytest


from PIL import Image, ImageDraw


from test.support.media_helpers import encode_mp4 as _encode_mp4


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


def _wav(*, amplitude: float, seconds: float = 1.0, channels: int = 1) -> bytes:
    rate = 22050
    count = int(rate * seconds)
    t = np.arange(count, dtype=np.float64) / rate
    pcm = np.round(np.sin(2 * math.pi * 440 * t) * amplitude * 32767).astype("<i2")
    if channels > 1:
        pcm = np.repeat(pcm[:, None], channels, axis=1).reshape(-1)
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
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


def test_native_stereo_peak_does_not_invent_clipping_through_mono_downmix():
    # Correlated channels at 0.8 stay below full scale in the delivered file.
    # A 1/sqrt(2)-per-channel mono downmix would instead report about 1.13.
    audio, issues = inspect_output_audio(
        _wav(amplitude=0.8, channels=2), _spec(audio=True)
    )

    assert audio.samples == 22050
    assert audio.peak_dbfs == pytest.approx(-1.94, abs=0.15)
    assert audio.rms_dbfs == pytest.approx(-4.97, abs=0.15)
    assert audio.clipped_sample_ratio == 0.0
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

