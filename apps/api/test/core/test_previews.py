"""Bounded pre-production Scrub previews: local scopes, never a full film."""
from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest

from test.core.fixtures import FOUR_S_TICKS, SNAPSHOT_FACTS, valid_content
from app.agents.working_drafts import record_working_draft_review, working_draft_review_facts
from app.editing.schemas import (
    CaptionDerivation,
    GeneratedImageOutput,
    GeneratorObject,
    ProgramOutput,
    WebObject,
)
from app.models.schemas import VideoObjectScrubTarget, VideoSegmentScrubTarget
from app.tools.video.preview import (
    ScrubTargetError,
    compile_video_scrub,
    project_video_scrub,
    revision_scrub_affected,
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


def test_draft_review_compiles_one_scene_and_the_immediate_join():
    from app.tools.video.preview import VideoDraftReviewTarget, project_working_draft_review

    content = two_scene_content()
    _, first_scope = project_working_draft_review(content, VideoDraftReviewTarget(
        scene_id="scn_open", start_seconds=0, end_seconds=4,
    ))
    assert first_scope["scene_ids"] == ["scn_open"]
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
    with pytest.raises(ScrubTargetError, match="first Scene has no previous"):
        project_working_draft_review(content, VideoDraftReviewTarget(
            scene_id="scn_open", include_previous_scene=True, start_seconds=0, end_seconds=4,
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
    from app.tools.video.preview import WorkingDraftReviewJudgment

    for evidence_id in working_draft_review_facts(arguments)["unjudged_evidence_ids"]:
        arguments = record_working_draft_judgment(arguments, WorkingDraftReviewJudgment(
            evidence_id=evidence_id,
            verdict=verdict,
            observed="Visible target Scene content",
            summary="checked",
            clip_ids=clip_ids or [],
            resolves_issue_ids=list(resolves_issue_ids),
        ))
    return arguments


@pytest.mark.parametrize("retry_verdict", ["pass", "uncertain"])
def test_unconfirmed_preview_requires_one_same_window_retry_before_saving(retry_verdict):
    from app.agents.working_drafts import (
        assert_working_draft_review_ready, record_working_draft_judgment, working_draft_review_facts,
    )
    from app.tools.video.preview import VideoDraftReviewTarget, project_working_draft_review

    content = two_scene_content()
    target = VideoDraftReviewTarget(
        scene_id="scn_second", include_previous_scene=True, start_seconds=2.5, end_seconds=8,
    )
    _, scope = project_working_draft_review(content, target)
    evidence = review_evidence(content, start=2.5)
    evidence["scope"] = scope
    evidence["observation"]["representative_frame"] = {"scene_id": "scn_second", "output_seconds": 7.75}
    initial = {"content": content.model_dump(mode="json"), "design": {}}
    first = record_working_draft_review(initial, review_evidence(content, end=4, scene_ids=["scn_open"]))
    first = judge_unjudged(first)
    first = record_working_draft_review(first, evidence)
    original_id = working_draft_review_facts(first)["unjudged_evidence_ids"][0]
    with pytest.raises(ValueError, match="record what is visible"):
        record_working_draft_judgment(first, {"evidence_id": original_id, "verdict": "pass"})
    first = judge_unjudged(first, verdict="uncertain")
    facts = working_draft_review_facts(first)
    assert facts["next_review_target"] == {**target.model_dump(), "confirmation_retry": True}
    with pytest.raises(ValueError, match="sequential review is incomplete"):
        assert_working_draft_review_ready(first)

    retry = {**evidence, "observation": {**evidence["observation"], "confirmation_retry": True}}
    retried = record_working_draft_review(first, retry)
    assert working_draft_review_facts(retried)["unjudged_evidence_ids"][0] != original_id
    judged = judge_unjudged(retried, verdict=retry_verdict)
    facts = working_draft_review_facts(judged)
    if retry_verdict == "pass":
        assert_working_draft_review_ready(judged)
    else:
        assert facts["confirmation_blocked"] and facts["next_review_target"] is None
        with pytest.raises(ValueError, match="sequential review is incomplete"):
            assert_working_draft_review_ready(judged)


def test_optional_second_scene_preview_does_not_require_first_scene_review():
    from app.agents.working_drafts import assert_working_draft_review_ready, working_draft_review_facts
    from app.tools.video.preview import ReviewWorkingDraftArgs, project_working_draft_review

    content = two_scene_content()
    draft = {"content": content.model_dump(mode="json"), "design": {}}
    assert_working_draft_review_ready(draft)
    args = ReviewWorkingDraftArgs(
        draft_ref={"draft_id": "cnd_test", "draft_digest": "d" * 64}, scene_id="scn_second",
    )
    args.bind_working_draft(draft)
    _, scope = project_working_draft_review(content, args._review_target)
    assert scope["source_range_seconds"] == {"start": 4.0, "end": 8.0}
    assert scope["scene_ids"] == ["scn_second"]
    evidence = review_evidence(content, start=4)
    evidence["scope"] = scope
    reviewed = record_working_draft_review(args._working_draft, evidence)
    with pytest.raises(ValueError, match="sequential review is incomplete"):
        assert_working_draft_review_ready(reviewed)
    reviewed = judge_unjudged(reviewed)
    assert working_draft_review_facts(reviewed)["next_review_target"] is None
    assert_working_draft_review_ready(reviewed)


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


def test_sequential_review_activity_follows_real_start_evidence_recheck_and_save():
    from app.agents.tool_loop import ReadAccepted, ReadExecuting
    from app.agents.working_drafts import record_working_draft_review, review_state_after_edit
    from app.chat.activity import ActivityProjector
    from app.chat.activity_receipts import VideoDraftReviewReceipt
    from app.chat.turn_tools import _design_video_tool, _review_working_draft_tool
    from app.models.schemas import VideoDraftRef
    from app.tools.video.design import CompositionDesignVideoArgs
    from app.tools.video.preview import ReviewWorkingDraftArgs, VideoDraftReviewTarget

    content = two_scene_content()
    arguments = {"content": content.model_dump(mode="json"), "design": {}}
    projector = ActivityProjector([_design_video_tool(), _review_working_draft_tool()])

    def review_args(_target, state):
        args = ReviewWorkingDraftArgs(
            draft_ref=VideoDraftRef(draft_id="cnd_test", draft_digest="d" * 64),
        )
        args.bind_working_draft(state)
        return args

    def receipt(scene_ids):
        return VideoDraftReviewReceipt(
            draft_digest="d" * 64,
            content_digest="c" * 64,
            media_digest="e" * 64,
            source_range_seconds={"start": 0.0, "end": 4.0 if scene_ids == ["scn_open"] else 8.0},
            scene_ids=scene_ids,
            continuous=True,
        )

    def accept(name, params, *, ok=True, evidence=None):
        return [
            *projector.name_known(name),
            *projector.feed_event(ReadExecuting(tool_name=name, params=params)),
            *projector.feed_event(ReadAccepted(tool_name=name, ok=ok, receipt=evidence)),
        ]

    frames = accept("review_working_draft", review_args(
        VideoDraftReviewTarget(scene_id="scn_open", start_seconds=0, end_seconds=4), arguments,
    ), evidence=receipt(["scn_open"]))
    arguments = record_working_draft_review(
        arguments, review_evidence(content, end=4, scene_ids=["scn_open"]),
    )
    arguments = judge_unjudged(arguments)
    frames += accept("review_working_draft", review_args(
        VideoDraftReviewTarget(
            scene_id="scn_second", include_previous_scene=True, start_seconds=2.5, end_seconds=8,
        ), arguments,
    ), evidence=receipt(["scn_open", "scn_second"]))
    arguments = record_working_draft_review(arguments, review_evidence(content))
    arguments = judge_unjudged(arguments)

    revised = deepcopy(content)
    revised.timeline.tracks[1].clips[1].object.text = "Value / Defend"
    arguments = {
        "content": revised.model_dump(mode="json"),
        "design": {},
        "review": review_state_after_edit(arguments, revised.model_dump(mode="json")),
    }
    design = CompositionDesignVideoArgs(
        draft_ref=VideoDraftRef(draft_id="cnd_test", draft_digest="d" * 64), save=False,
    )
    frames += accept("design_video", design)
    frames += accept("review_working_draft", review_args(
        VideoDraftReviewTarget(
            scene_id="scn_second", include_previous_scene=True, start_seconds=0, end_seconds=8,
        ), arguments,
    ), evidence=receipt(["scn_open", "scn_second"]))
    save = CompositionDesignVideoArgs(
        draft_ref=VideoDraftRef(draft_id="cnd_test", draft_digest="f" * 64), save=True,
    )
    frames += accept("design_video", save)

    assert [(frame.status, frame.key) for frame in frames] == [
        ("active", "chat.activity.videoDraftScene"),
        ("completed", "chat.activity.videoDraftSceneDone"),
        ("active", "chat.activity.videoDraftJoin"),
        ("completed", "chat.activity.videoDraftJoinDone"),
        ("active", "chat.activity.videoDesign"),
        ("completed", "chat.activity.videoDesignDone"),
        ("active", "chat.activity.videoDraftRecheck"),
        ("completed", "chat.activity.videoDraftRecheckDone"),
        ("active", "chat.activity.videoSave"),
        ("completed", "chat.activity.videoSaveDone"),
    ]
    assert [frames[index].count for index in (0, 2, 6, 7)] == [1, 2, 2, 2]

    failed = accept("review_working_draft", review_args(
        VideoDraftReviewTarget(scene_id="scn_open", start_seconds=0, end_seconds=4), arguments,
    ), ok=False)
    assert [frame.status for frame in failed] == ["active", "failed"]
    assert failed[-1].receipt is None


@pytest.mark.asyncio
async def test_draft_preview_names_missing_web_source_before_renderer(monkeypatch):
    from app.editing.validators import ContentValidationError
    from app.models.schemas import VideoDraftRef
    from app.tools.video.preview import (
        ReviewWorkingDraftArgs,
        VideoDraftReviewTarget,
        prepare_working_draft_review,
    )

    content = two_scene_content()
    clip = content.timeline.tracks[0].clips[0]
    clip.object = WebObject(
        kind="web",
        object_id="obj_web",
        view_id="view-3",
        layout=clip.object.layout,
    )
    clip.source = None
    args = ReviewWorkingDraftArgs(
        draft_ref=VideoDraftRef(draft_id="cnd_test", draft_digest="d" * 64),
    )
    args.bind_working_draft({"content": content.model_dump(mode="json"), "design": {}})
    from unittest.mock import AsyncMock

    owner_id = UUID(int=0)
    monkeypatch.setattr(
        "app.tools.video.preview.snapshot_facts",
        AsyncMock(return_value={
            snapshot_id: {**facts, "owner_id": owner_id}
            for snapshot_id, facts in SNAPSHOT_FACTS.items()
        }),
    )
    with pytest.raises(ContentValidationError, match="web objects require a source"):
        await prepare_working_draft_review(None, owner_id=owner_id, args=args)


def test_high_level_web_focus_recomputes_only_the_target_clip_camera():
    from app.tools.video.design import CompositionDesignVideoArgs, _apply_focus_write
    from test.core.fixtures import IMG_SNAPSHOT

    content = valid_content()
    clip = content.timeline.tracks[0].clips[0]
    clip.object = WebObject(
        kind="web", object_id="obj_web", view_id="view-value", layout=clip.object.layout,
    )
    facts = {
        **SNAPSHOT_FACTS,
        IMG_SNAPSHOT: {
            **SNAPSHOT_FACTS[IMG_SNAPSHOT],
            "kind": "web",
            "meta": {"views": [{
                "view_id": "view-value", "width": 1200, "height": 800,
                "storage_key": "test/view-value.png", "digest": "a" * 64,
                "elements": [{"id": "value", "x": 0.75, "y": 0.5, "w": 0.2, "h": 0.1}],
            }]},
        },
    }
    before = content.model_dump(mode="json")
    args = CompositionDesignVideoArgs(focus_clip_id=clip.clip_id, focus_element_id="value")
    title = before["timeline"]["tracks"][1]["clips"][0]
    with pytest.raises(ValueError, match="web framing repair changes only its target Clip"):
        CompositionDesignVideoArgs(
            focus_clip_id=clip.clip_id,
            focus_element_id="value",
            clips=[{"track_id": before["timeline"]["tracks"][1]["track_id"], "clip": title}],
        )
    updated = _apply_focus_write(before, args, facts)
    target = next(
        item for track in updated["timeline"]["tracks"] for item in track["clips"]
        if item["clip_id"] == clip.clip_id
    )
    other = next(
        item for track in updated["timeline"]["tracks"] for item in track["clips"]
        if item["clip_id"] != clip.clip_id
    )
    assert {animation["property"] for animation in target["animations"]} == {
        "transform.scale", "transform.position",
    }
    assert target["object"] == before["timeline"]["tracks"][0]["clips"][0]["object"]
    assert other == before["timeline"]["tracks"][1]["clips"][0]


def test_repeat_preview_request_before_judgment_does_not_open_fake_activity():
    from app.agents.tool_loop import ReadExecuting
    from app.chat.activity import ActivityProjector
    from app.chat.turn_tools import _design_video_tool, _review_working_draft_tool
    from app.models.schemas import VideoDraftRef
    from app.tools.video.preview import ReviewWorkingDraftArgs

    content = two_scene_content()
    arguments = {"content": content.model_dump(mode="json"), "design": {}}
    arguments = record_working_draft_review(
        arguments, review_evidence(content, end=4, scene_ids=["scn_open"]),
    )
    args = ReviewWorkingDraftArgs(
        draft_ref=VideoDraftRef(draft_id="cnd_test", draft_digest="d" * 64),
    )
    args.bind_working_draft(arguments)
    projector = ActivityProjector([_design_video_tool(), _review_working_draft_tool()])
    assert projector.name_known("review_working_draft") == []
    assert projector.feed_event(ReadExecuting(
        tool_name="review_working_draft", params=args,
    )) == []


def test_valid_focus_repair_enters_review_and_save_waits_for_pass():
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.working_drafts import assert_working_draft_review_ready, working_draft_arguments
    from app.chat.prompts import assemble_video_round
    from app.models.schemas import canonical_json_hash
    from app.tools.video.design import CompositionDesignVideoArgs, _apply_focus_write
    from test.core.fixtures import IMG_SNAPSHOT

    content = valid_content()
    clip = content.timeline.tracks[0].clips[0]
    clip.object = WebObject(
        kind="web", object_id="obj_web", view_id="view-value", layout=clip.object.layout,
    )
    view = {
        "view_id": "view-value", "width": 1200, "height": 800,
        "storage_key": "test/view-value.png", "digest": "a" * 64,
        "elements": [{"id": "value", "x": 0.75, "y": 0.5, "w": 0.2, "h": 0.1}],
    }
    facts = {
        **SNAPSHOT_FACTS,
        IMG_SNAPSHOT: {**SNAPSHOT_FACTS[IMG_SNAPSHOT], "kind": "web", "meta": {"views": [view]}},
    }
    before = content.model_dump(mode="json")
    reviewed = record_working_draft_review({"content": before, "design": {}}, review_evidence(content))
    reviewed = judge_unjudged(reviewed, verdict="issue", clip_ids=[clip.clip_id])
    issue_id = working_draft_review_facts(reviewed)["open_issues"][0]["issue_id"]
    args = CompositionDesignVideoArgs(focus_clip_id=clip.clip_id, focus_element_id="value")
    updated = _apply_focus_write(before, args, facts)
    assert canonical_json_hash(updated) != canonical_json_hash(before)
    revised = working_draft_arguments(args, updated, base=reviewed)
    facts_after = working_draft_review_facts(revised)
    assert facts_after["invalidated_ranges_seconds"] == [{"start": 0.0, "end": 4.0}]
    with pytest.raises(ValueError, match="sequential review is incomplete"):
        assert_working_draft_review_ready(revised)

    draft = CandidateRecord.create(
        tool_name="design_video", arguments=revised, errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="repair",
    )
    source = {"kind": "snapshot", "snapshot_id": str(IMG_SNAPSHOT), "views": [{
        **view, "targets": [{"id": "value"}],
    }]}
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    import json

    assembled = assemble_video_round({
        "tools": intent_router.tools,
        "drafts": (draft,), "snapshot": ContextSnapshot("source", resources=(("snapshot", source),)),
        "mode": "plan", "user_text": "Repair the target",
    })
    assert assembled.stage == "draft_review"
    assert "design_video" not in {tool.name for tool in assembled.tools}
    dynamic = json.loads(assembled.context.split("当前视频轮次（目标和状态由服务端提供）：\n", 1)[1])
    assert dynamic["draft"]["next_review_target"]["scene_id"] == "scn_open"

    from app.editing.schemas import CompositionContent

    rechecked = record_working_draft_review(
        revised, review_evidence(CompositionContent.model_validate(updated), digest="f"),
    )
    rechecked = judge_unjudged(rechecked, resolves_issue_ids=[issue_id])
    assert working_draft_review_facts(rechecked)["save_ready"] is True
    assert_working_draft_review_ready(rechecked)


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
