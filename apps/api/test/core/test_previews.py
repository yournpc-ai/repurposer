"""Bounded pre-production Scrub previews: local scopes, never a full film."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest

from test.core.fixtures import FOUR_S_TICKS, SNAPSHOT_FACTS, valid_content
from app.agents.working_drafts import record_working_draft_review, working_draft_review_facts
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


def review_evidence(content, *, start=0.0, end=8.0, scene_ids=None, digest="d"):
    from app.models.schemas import canonical_json_hash

    reviewed_scenes = scene_ids or ["scn_open", "scn_second"]
    return {
        "draft_ref": {"draft_id": "cnd_test", "draft_digest": digest * 64},
        "content_digest": canonical_json_hash(content.model_dump(mode="json")),
        "scope": {
            "source_range_seconds": {"start": start, "end": end},
            "scene_ids": reviewed_scenes,
            "clip_ids": [
                clip.clip_id for track in content.timeline.tracks for clip in track.clips
                if clip.scene_id in reviewed_scenes
            ],
        },
        "observation": {"mode": "continuous_mp4", "media_digest": digest * 64},
    }


def judge_unjudged(arguments, *, verdict="pass", clip_ids=None, resolves_issue_ids=()):
    from app.agents.working_drafts import record_working_draft_judgment, working_draft_review_facts

    for evidence_id in working_draft_review_facts(arguments)["unjudged_evidence_ids"]:
        arguments = record_working_draft_judgment(arguments, {
            "evidence_id": evidence_id,
            "verdict": verdict,
            "observed": "Visible target Scene content",
            "summary": "checked",
            "clip_ids": clip_ids or [],
            "resolves_issue_ids": list(resolves_issue_ids),
        })
    return arguments






def test_second_scene_edit_invalidates_only_affected_review_ranges_then_rechecks():
    from app.agents.working_drafts import (
        assert_working_draft_review_ready,
        record_working_draft_review,
        review_state_after_edit,
        working_draft_review_facts,
    )

    content = two_scene_content()
    arguments = {"content": content.model_dump(mode="json"), "design": {}}
    arguments = record_working_draft_review(
        arguments, review_evidence(content, end=4, scene_ids=["scn_open"]),
    )
    arguments = judge_unjudged(arguments)
    arguments = record_working_draft_review(arguments, review_evidence(content))
    assert working_draft_review_facts(arguments)["save_ready"] is False
    arguments = judge_unjudged(arguments)
    assert working_draft_review_facts(arguments)["save_ready"] is True

    revised = deepcopy(content)
    first_before = [clip for track in revised.timeline.tracks for clip in track.clips if clip.scene_id == "scn_open"]
    second_title = next(
        clip for track in revised.timeline.tracks for clip in track.clips
        if clip.clip_id == "clp_title_second"
    )
    second_title.object.text = "Value / Defend"
    review = review_state_after_edit(arguments, revised.model_dump(mode="json"))
    revised_arguments = {
        "content": revised.model_dump(mode="json"), "design": {}, "review": review,
    }
    facts = working_draft_review_facts(revised_arguments)
    assert facts["reviewed_ranges_seconds"] == [{"start": 0.0, "end": 5.0}]
    assert facts["invalidated_ranges_seconds"] == [{"start": 5.0, "end": 8.0}]
    assert facts["current_scene_id"] == "scn_second"
    assert facts["next_review_target"] == {
        "scene_id": "scn_second",
        "include_previous_scene": True,
        "start_seconds": 5.0,
        "end_seconds": 8.0,
        "recheck": True,
    }
    assert facts["save_ready"] is False
    with pytest.raises(ValueError, match="sequential review is incomplete"):
        assert_working_draft_review_ready(revised_arguments)
    first_after = [clip for track in revised.timeline.tracks for clip in track.clips if clip.scene_id == "scn_open"]
    assert first_after == first_before
    assert revised.sources == content.sources
    assert revised.timeline.transitions == content.timeline.transitions

    rechecked = record_working_draft_review(
        revised_arguments, review_evidence(revised, digest="f"),
    )
    rechecked = judge_unjudged(rechecked)
    assert working_draft_review_facts(rechecked)["save_ready"] is True
    assert_working_draft_review_ready(rechecked)


def test_overlapping_new_clip_invalidates_evidence_and_empty_segments_stay_empty():
    from app.agents.working_drafts import review_state_after_edit, working_draft_review_facts

    content = two_scene_content()
    arguments = {"content": content.model_dump(mode="json"), "design": {}}
    arguments = record_working_draft_review(arguments, review_evidence(content))
    review = arguments["review"]
    review["reviews"][0]["valid_segments"] = []
    assert working_draft_review_facts(arguments)["reviewed_ranges_seconds"] == []

    arguments = {"content": content.model_dump(mode="json"), "design": {}}
    arguments = record_working_draft_review(arguments, review_evidence(content))
    revised = deepcopy(content)
    overlay = deepcopy(revised.timeline.tracks[1].clips[0])
    overlay.clip_id = "clp_overlap"
    overlay.object.object_id = "obj_overlap"
    revised.timeline.tracks[1].clips.append(overlay)
    updated = review_state_after_edit(arguments, revised.model_dump(mode="json"))
    facts = working_draft_review_facts({
        "content": revised.model_dump(mode="json"), "design": {}, "review": updated,
    })
    assert facts["invalidated_ranges_seconds"] == [{"start": 1.0, "end": 4.0}]
    assert facts["save_ready"] is False


def test_open_issue_requires_a_targeted_recheck_and_pass_before_save():
    from app.agents.working_drafts import assert_working_draft_review_ready, record_working_draft_review

    content = two_scene_content()
    content.timeline.tracks[1].clips[0].object.text = "核对中文证据"
    arguments = {"content": content.model_dump(mode="json"), "design": {}}
    arguments = record_working_draft_review(arguments, review_evidence(content))
    arguments = judge_unjudged(arguments, verdict="issue", clip_ids=["clp_title_second"])
    facts = working_draft_review_facts(arguments)
    assert facts["open_issues"][0]["clip_ids"] == ["clp_title_second"]
    with pytest.raises(ValueError, match="open_issues"):
        assert_working_draft_review_ready(arguments)

    arguments = record_working_draft_review(arguments, review_evidence(content, digest="f"))
    arguments = judge_unjudged(arguments, resolves_issue_ids=[facts["open_issues"][0]["issue_id"]])
    assert working_draft_review_facts(arguments)["save_ready"] is True
    assert_working_draft_review_ready(arguments)












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
    facts = sampled_frame_facts(frames)
    assert facts[0]["pixel_difference_from_previous_bbox_px"] is None
    assert facts[1]["pixel_difference_from_previous_bbox_px"] == []
    assert facts[2]["pixel_difference_from_previous_bbox_px"] == [0, 0, 16, 18]
    assert [fact["seconds"] for fact in facts] == [0.0, 1.0, 1.966667]
    assert len({fact["jpeg_sha256"] for fact in facts}) == 2
