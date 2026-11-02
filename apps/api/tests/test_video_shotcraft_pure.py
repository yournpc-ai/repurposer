"""Fixed blur-slide adaptation through the native editing and compile contracts."""
from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.editing.edits import apply_ops
from app.editing.schemas import CompositionContent
from app.editing.service import translate_revision
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec
from app.models.schemas import ReviseVideoArgs
from app.skills.external import SkillCapabilityReport, SkillDraft, SkillSource
from app.skills.video_shotcraft import (
    VIDEO_SHOTCRAFT_REVISION,
    BlurSlidePalette,
    SkillAdaptationError,
    instantiate_blur_demote_sequence,
    instantiate_blur_slide,
    instantiate_title_demote,
)


def _draft() -> SkillDraft:
    return SkillDraft(
        name="video-shotcraft",
        description="Pinned shot evidence",
        instructions="Use the pinned blur-slide method.",
        references=[
            SkillSource(
                path="references/shots/typography/blur-slide.md",
                role="reference",
                digest="feb73479174b0ff073a6d774c6ed3bd250591439fbd750e1167c2f39b27a05d4",
                text="pinned shot card",
            ),
            SkillSource(
                path="demos/typography/blur-slide/BlurSlide.tsx",
                role="implementation",
                digest="4e7227b050b4f9fdd0c8762f308aaf2a152f8c476fa3e11efe84b3a23cc43a91",
                text="pinned implementation",
            ),
            SkillSource(
                path="references/shots/typography/title-demote-to-label.md",
                role="reference",
                digest="4e01c04c76d9f6a3f1b18e9c75ac1502cb1aefe1ac08ef47426b8628ea9fa08f",
                text="pinned demote shot card",
            ),
            SkillSource(
                path="demos/typography/title-demote-to-label/TitleDemoteToLabel.tsx",
                role="implementation",
                digest="5448cdf76c9eb57ebc4de46ae0f2e9bd399275e9600181afb26fe5dfbf0eeff5",
                text="pinned demote implementation",
            ),
        ],
        source_hash="a" * 64,
        source_revision=VIDEO_SHOTCRAFT_REVISION,
        capability_report=SkillCapabilityReport(),
    )


def _instantiate():
    return instantiate_blur_slide(
        _draft(),
        title_lines=("Make every idea", "move clearly"),
        subtitle="Your existing material shaped into the content you name",
    )


def test_blur_slide_core_uses_shared_word_progress_and_native_edits():
    instantiated = _instantiate()
    candidate = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        instantiated.ops,
        {},
    )
    validate_content(candidate, {})

    clips = [clip for track in candidate.timeline.tracks for clip in track.clips]
    assert len(clips) == 3
    title_a = next(clip for clip in clips if clip.clip_id == "clp_blur_title_a")
    channels = {animation.property: animation for animation in title_a.animations}
    assert set(channels) == {"opacity", "transform.position", "filter.blur"}
    for animation in channels.values():
        assert animation.text_part is not None
        assert animation.text_part.stagger == 12000
        assert [keyframe.at for keyframe in animation.keyframes] == [30000, 96000]
        assert animation.keyframes[0].easing.params == (0.22, 1.0, 0.36, 1.0)

    title_b = next(clip for clip in clips if clip.clip_id == "clp_blur_title_b")
    tracking = next(
        animation for animation in title_b.animations
        if animation.property == "text.letter_spacing"
    )
    assert [keyframe.value for keyframe in tracking.keyframes] == [0.03, -0.025]
    assert [keyframe.at for keyframe in tracking.keyframes] == [90000, 180000]
    assert instantiated.skill_provenance["scope"] == "word-reveal-core"


def test_blur_slide_compiles_expanded_text_part_properties_and_real_hold():
    candidate = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        _instantiate().ops,
        {},
    )
    validate_content(candidate, {})
    spec = compile_video_spec(
        candidate,
        {},
        composition_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("00000000-0000-0000-0000-000000000002"),
        content_digest="d" * 64,
    )

    clips = {clip["clip_id"]: clip for track in spec["tracks"] for clip in track["clips"]}
    title_a = clips["clp_blur_title_a"]
    assert title_a["object"]["style"]["letter_spacing"] == -0.035
    assert len([a for a in title_a["animations"] if a["property"] == "filter.blur"]) == 3
    assert all(a["target_text_part_id"] for a in title_a["animations"])
    subtitle_blur = [
        animation for animation in clips["clp_blur_subtitle"]["animations"]
        if animation["property"] == "filter.blur"
    ]
    assert len(subtitle_blur) == 9
    assert max(
        keyframe["at"] for animation in subtitle_blur for keyframe in animation["keyframes"]
    ) == 73  # 34 + 20 + 8×2.4 = 73.2 source frames, quantized to frame 73


def test_blur_slide_rejects_unpinned_source_and_non_strict_copy():
    changed = _draft().model_copy(update={"source_revision": "deadbeef"})
    with pytest.raises(SkillAdaptationError, match="pinned"):
        instantiate_blur_slide(
            changed,
            title_lines=("Make every idea", "move clearly"),
            subtitle="Your existing material shaped into the content you name",
        )
    changed_source = _draft()
    changed_source.references[0].digest = "0" * 64
    with pytest.raises(SkillAdaptationError, match="source evidence"):
        instantiate_blur_slide(
            changed_source,
            title_lines=("Make every idea", "move clearly"),
            subtitle="Your existing material shaped into the content you name",
        )
    with pytest.raises(SkillAdaptationError, match="exactly 3 words"):
        instantiate_blur_slide(
            _draft(),
            title_lines=("Too short", "move clearly"),
            subtitle="Your existing material shaped into the content you name",
        )
    with pytest.raises(SkillAdaptationError, match="without attached punctuation"):
        instantiate_blur_slide(
            _draft(),
            title_lines=("Make every idea", "move clearly."),
            subtitle="Your existing material shaped into the content you name",
        )
    with pytest.raises(ValidationError, match="color|background|string_pattern_mismatch"):
        BlurSlidePalette(background="not-a-color")


def test_second_product_content_reuses_method_not_previous_copy_or_colors():
    original = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        _instantiate().ops,
        {},
    )
    reused = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        instantiate_blur_slide(
            _draft(),
            title_lines=("Grow your audience", "share boldly"),
            subtitle="Turn your hard earned expertise into stories worth following",
            palette=BlurSlidePalette(
                background="#101418",
                title="#F5F3EE",
                subtitle="#C7D0D8",
            ),
        ).ops,
        {},
    )
    validate_content(reused, {})

    assert original.settings.background == "#F7F6F2"
    assert reused.settings.background == "#101418"
    reused_clips = {
        clip.clip_id: clip for track in reused.timeline.tracks for clip in track.clips
    }
    assert reused_clips["clp_blur_title_a"].object.text == "Grow your audience"
    assert reused_clips["clp_blur_title_b"].object.text == "share boldly"
    assert reused_clips["clp_blur_subtitle"].object.style.color == "#C7D0D8"

    def timing_signatures(content: CompositionContent) -> dict[str, list]:
        return {
            clip.clip_id: [
                (
                    animation.property,
                    animation.text_part.stagger if animation.text_part else None,
                    [(key.at, key.value, key.easing) for key in animation.keyframes],
                )
                for animation in clip.animations
            ]
            for track in content.timeline.tracks
            for clip in track.clips
        }

    assert timing_signatures(reused) == timing_signatures(original)


def test_native_revision_changes_copy_and_palette_without_moving_untouched_method():
    base = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        _instantiate().ops,
        {},
    )
    args = ReviseVideoArgs.model_validate({
        "base_ref": {
            "composition_id": "00000000-0000-0000-0000-000000000001",
            "composition_version_id": "00000000-0000-0000-0000-000000000002",
            "content_digest": "d" * 64,
        },
        "edits": [
            {
                "op": "update_text",
                "clip_id": "clp_blur_title_a",
                "text": "Turn every insight",
                "color": "#F5F3EE",
            },
            {
                "op": "update_text",
                "clip_id": "clp_blur_title_b",
                "color": "#F5F3EE",
            },
            {
                "op": "update_text",
                "clip_id": "clp_blur_subtitle",
                "text": "Your research and expertise shaped into content people remember",
                "color": "#C7D0D8",
            },
            {"op": "set_background", "color": "#101418"},
        ],
    })
    revised = apply_ops(base, translate_revision(base, args), {})
    validate_content(revised, {})

    base_clips = {
        clip.clip_id: clip for track in base.timeline.tracks for clip in track.clips
    }
    revised_clips = {
        clip.clip_id: clip for track in revised.timeline.tracks for clip in track.clips
    }
    assert revised_clips["clp_blur_title_a"].object.text == "Turn every insight"
    assert revised_clips["clp_blur_title_b"].object.text == "move clearly"
    assert revised_clips["clp_blur_subtitle"].object.style.color == "#C7D0D8"
    assert revised.settings.background == "#101418"
    assert revised.scenes == base.scenes
    assert revised_clips["clp_blur_title_b"].animations == base_clips["clp_blur_title_b"].animations
    for clip_id in ("clp_blur_title_a", "clp_blur_subtitle"):
        before = base_clips[clip_id]
        after = revised_clips[clip_id]
        assert after.range == before.range
        assert [a.property for a in after.animations] == [a.property for a in before.animations]
        assert [
            [(key.at, key.value, key.easing) for key in animation.keyframes]
            for animation in after.animations
        ] == [
            [(key.at, key.value, key.easing) for key in animation.keyframes]
            for animation in before.animations
        ]
        assert {
            part_id
            for animation in after.animations
            if animation.text_part
            for part_id in animation.text_part.part_ids
        }.isdisjoint({
            part_id
            for animation in before.animations
            if animation.text_part
            for part_id in animation.text_part.part_ids
        })


def _sequence():
    return instantiate_blur_demote_sequence(
        _draft(),
        title_lines=("Make every idea", "move clearly"),
        subtitle="Your existing material shaped into the content you name",
        section_title="Shape",
        section_lines=(
            "Upload the material you already have",
            "Name the content you want",
            "Review and refine every version",
        ),
        palette=BlurSlidePalette(
            background="#101418",
            title="#F5F3EE",
            subtitle="#C7D0D8",
        ),
    )


def test_title_demote_has_one_shared_demotion_curve_and_overlapping_growth():
    candidate = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        instantiate_title_demote(
            _draft(),
            title="Shape",
            content_lines=(
                "Upload the material you already have",
                "Name the content you want",
                "Review and refine every version",
            ),
        ).ops,
        {},
    )
    validate_content(candidate, {})
    clips = {clip.clip_id: clip for track in candidate.timeline.tracks for clip in track.clips}
    title = clips["clp_demote_title"]
    channels = {
        animation.property: animation
        for animation in title.animations
        if animation.text_part is None
    }
    assert set(channels) == {"transform.scale", "transform.position"}
    for animation in channels.values():
        assert [key.at for key in animation.keyframes] == [108000, 186000]
        assert animation.keyframes[0].easing.params == (0.6, 0.0, 0.18, 1.0)
    assert channels["transform.scale"].keyframes[-1].value == 0.22
    entrance = next(a for a in title.animations if a.text_part is not None)
    assert entrance.text_part.kind == "grapheme"
    assert len(entrance.text_part.part_ids) == 5
    assert clips["clp_demote_content_0"].animations[0].keyframes[0].at == 144000
    assert clips["clp_demote_content_1"].animations[0].keyframes[0].at == 162000


def test_two_shot_sequence_offsets_ranges_but_not_clip_local_animation():
    instantiated = _sequence()
    candidate = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        instantiated.ops,
        {},
    )
    validate_content(candidate, {})
    assert [(scene.range.start, scene.range.end) for scene in candidate.scenes] == [
        (0, 360000),
        (360000, 696000),
    ]
    clips = {clip.clip_id: clip for track in candidate.timeline.tracks for clip in track.clips}
    demote = clips["clp_demote_title"]
    assert (demote.range.start, demote.range.end) == (360000, 696000)
    scale = next(a for a in demote.animations if a.property == "transform.scale")
    assert [key.at for key in scale.keyframes] == [108000, 186000]
    assert [shot["shot"] for shot in instantiated.skill_provenance["shots"]] == [
        "blur-slide",
        "title-demote-to-label",
    ]

    spec = compile_video_spec(
        candidate,
        {},
        composition_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("00000000-0000-0000-0000-000000000002"),
        content_digest="d" * 64,
    )
    assert spec["duration_frames"] == 232
    compiled_demote = next(
        clip for track in spec["tracks"] for clip in track["clips"]
        if clip["clip_id"] == "clp_demote_title"
    )
    assert compiled_demote["start_frame"] == 120
    assert compiled_demote["end_frame"] == 232


def test_title_demote_strict_mode_rejects_unsupported_copy_and_source_drift():
    with pytest.raises(SkillAdaptationError, match="exactly 1 words"):
        instantiate_title_demote(
            _draft(),
            title="Too many words",
            content_lines=("One", "Two", "Three"),
        )
    with pytest.raises(SkillAdaptationError, match="1–64"):
        instantiate_title_demote(
            _draft(),
            title="Shape",
            content_lines=("One", "", "Three"),
        )
    changed = _draft()
    changed.references[-1].digest = "0" * 64
    with pytest.raises(SkillAdaptationError, match="source evidence"):
        instantiate_title_demote(
            changed,
            title="Shape",
            content_lines=("One", "Two", "Three"),
        )
