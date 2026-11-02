"""Pure journey coverage for the generic Composition temporal edit algebra.

No DB, LLM, HTTP or rendering: Chat-shaped revision DTOs compile to the same
write-door operation used by legacy temporal ops. The 88-second work fixture
covers the website/native/music journey's structural invariants, not pixels.
"""
from __future__ import annotations

import copy
from fractions import Fraction
from uuid import UUID

import pytest

from app.editing.edits import TemporalEdit, apply_ops
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    CompositionContent,
    EditTarget,
    GeneratedImageOutput,
    GeneratorObject,
    ImageObject,
    Keyframe,
    LayoutBox,
    Scene,
    SourceBinding,
    SpeechObject,
    TextObject,
    TextStyle,
    TimeRange,
    Track,
    Transition,
    VideoObject,
    WebObject,
)
from app.editing.service import translate_revision
from app.editing.temporal import (
    TemporalCapabilityError,
    TemporalEditError,
    timeline_duration,
)
from app.editing.timing import SOURCE_TIMEBASE, quantize_ticks
from app.editing.validators import validate_content
from app.models.schemas import ReviseVideoArgs
from test_editing_edits_pure import (
    AUDIO_DIGEST,
    AUDIO_SNAPSHOT,
    IMG_DIGEST,
    IMG_SNAPSHOT,
    SNAPSHOT_FACTS,
    valid_content,
)

COMP_ID = UUID("55555555-5555-5555-5555-555555555555")
VER_ID = UUID("66666666-6666-6666-6666-666666666666")
WEB_SNAPSHOT = UUID("77777777-7777-7777-7777-777777777777")
WEB_DIGEST = "c" * 64


def _args(edit: dict) -> ReviseVideoArgs:
    return ReviseVideoArgs.model_validate({
        "base_ref": {
            "composition_id": str(COMP_ID),
            "composition_version_id": str(VER_ID),
            "content_digest": "d" * 64,
        },
        "edits": [edit],
    })


def _clip(content: CompositionContent, clip_id: str) -> Clip:
    return next(c for t in content.timeline.tracks for c in t.clips if c.clip_id == clip_id)


def _two_scene_content() -> tuple[CompositionContent, dict]:
    content = valid_content()
    second_scene = content.scenes[0].model_copy(deep=True)
    second_scene.scene_id = "scn_next"
    second_scene.range = TimeRange(start=4 * SOURCE_TIMEBASE, end=8 * SOURCE_TIMEBASE)
    content.scenes.append(second_scene)
    for source_id, target_id, object_id, animation_id, start in (
        ("clp_bg", "clp_bg_next", "obj_bg_next", None, 4),
        ("clp_title", "clp_title_next", "obj_title_next", "anm_fade_next", 5),
    ):
        clip = _clip(content, source_id).model_copy(deep=True)
        clip.clip_id = target_id
        clip.object.object_id = object_id
        clip.scene_id = "scn_next"
        clip.range = TimeRange(
            start=start * SOURCE_TIMEBASE,
            end=8 * SOURCE_TIMEBASE,
        )
        for animation in clip.animations:
            animation.animation_id = animation_id or animation.animation_id
            animation.target_object_id = object_id
        track = next(t for t in content.timeline.tracks if any(c.clip_id == source_id for c in t.clips))
        track.clips.append(clip)
    music = _clip(content, "clp_bed")
    music.range = TimeRange(start=0, end=8 * SOURCE_TIMEBASE)
    assert music.source is not None
    music.source.source_range = TimeRange(start=0, end=8 * SOURCE_TIMEBASE)
    facts = copy.deepcopy(SNAPSHOT_FACTS)
    facts[AUDIO_SNAPSHOT]["duration_ticks"] = 8 * SOURCE_TIMEBASE
    validate_content(content, facts)
    return content, facts


def test_clip_move_uses_generic_target_and_preserves_source_and_local_animation():
    base = valid_content()
    before = _clip(base, "clp_title")
    ops = translate_revision(base, _args({
        "op": "move",
        "target": {"kind": "clip", "id": "clp_title"},
        "start_seconds": 0.5,
    }))
    assert len(ops) == 1 and isinstance(ops[0], TemporalEdit)
    updated = apply_ops(base, ops, {})
    validate_content(updated, SNAPSHOT_FACTS)
    moved = _clip(updated, "clp_title")
    assert moved.range == TimeRange(start=SOURCE_TIMEBASE // 2, end=7 * SOURCE_TIMEBASE // 2)
    assert moved.source == before.source
    assert moved.animations == before.animations
    assert _clip(updated, "clp_bed") == _clip(base, "clp_bed")


def test_track_and_explicit_selection_resolve_stable_ids_not_time_intersection():
    base = valid_content()
    moved_track = apply_ops(base, translate_revision(base, _args({
        "op": "move", "target": {"kind": "track", "id": "trk_music"}, "start_seconds": 1,
    })), {})
    validate_content(moved_track, SNAPSHOT_FACTS)
    assert _clip(moved_track, "clp_bed").range.start == SOURCE_TIMEBASE
    assert _clip(moved_track, "clp_bg") == _clip(base, "clp_bg")

    moved_selection = apply_ops(base, translate_revision(base, _args({
        "op": "move",
        "target": {
            "kind": "selection", "scene_ids": ["scn_open"], "clip_ids": ["clp_bed"],
        },
        "start_seconds": 1,
    })), {})
    validate_content(moved_selection, SNAPSHOT_FACTS)
    assert moved_selection.scenes[0].range.start == SOURCE_TIMEBASE
    assert _clip(moved_selection, "clp_bed").range.start == SOURCE_TIMEBASE


def test_track_delete_removes_the_track_and_its_clips_only():
    base = valid_content()
    updated = apply_ops(base, [TemporalEdit(
        op="temporal_edit", action="delete", target=EditTarget(kind="track", id="trk_title"),
    )], {})
    validate_content(updated, SNAPSHOT_FACTS)
    assert [track.track_id for track in updated.timeline.tracks] == ["trk_main", "trk_music"]
    assert _clip(updated, "clp_bg") == _clip(base, "clp_bg")
    assert _clip(updated, "clp_bed") == _clip(base, "clp_bed")


def test_empty_track_delete_needs_no_fabricated_time_range():
    base = valid_content()
    expected = base.model_copy(deep=True)
    base.timeline.tracks.append(Track(
        track_id="trk_empty", kind="visual", role="title", order=3,
    ))
    validate_content(base, SNAPSHOT_FACTS)
    updated = apply_ops(base, [TemporalEdit(
        op="temporal_edit", action="delete", target=EditTarget(kind="track", id="trk_empty"),
    )], {})
    validate_content(updated, SNAPSHOT_FACTS)
    assert updated == expected


def test_scene_trim_ripples_structural_downstream_and_leaves_global_music():
    base, facts = _two_scene_content()
    updated = apply_ops(base, translate_revision(base, _args({
        "op": "trim",
        "target": {"kind": "scene", "id": "scn_open"},
        "start_seconds": 0,
        "end_seconds": 2,
        "ripple": "forward",
        "source_policy": "crop_1x",
    })), {})
    validate_content(updated, facts)
    scenes = {scene.scene_id: scene for scene in updated.scenes}
    assert scenes["scn_open"].range == TimeRange(start=0, end=2 * SOURCE_TIMEBASE)
    assert scenes["scn_next"].range == TimeRange(
        start=2 * SOURCE_TIMEBASE, end=6 * SOURCE_TIMEBASE
    )
    assert _clip(updated, "clp_bg_next").range == scenes["scn_next"].range
    assert _clip(updated, "clp_title_next").range == TimeRange(
        start=3 * SOURCE_TIMEBASE, end=6 * SOURCE_TIMEBASE
    )
    assert _clip(updated, "clp_bed") == _clip(base, "clp_bed")


def test_scene_delete_distinguishes_lift_and_ripple():
    base, facts = _two_scene_content()
    for mode, expected_start in (("lift", 4), ("ripple", 0)):
        updated = apply_ops(base, translate_revision(base, _args({
            "op": "delete", "target": {"kind": "scene", "id": "scn_open"}, "mode": mode,
        })), {})
        validate_content(updated, facts)
        assert [scene.scene_id for scene in updated.scenes] == ["scn_next"]
        assert _clip(updated, "clp_bg_next").range.start == expected_start * SOURCE_TIMEBASE
        assert all(clip.clip_id != "clp_bg" for track in updated.timeline.tracks for clip in track.clips)
        assert _clip(updated, "clp_bed") == _clip(base, "clp_bed")


def test_linked_group_follows_generic_clip_move_without_time_intersection_guesses():
    base = valid_content()
    title, music = _clip(base, "clp_title"), _clip(base, "clp_bed")
    title.linked_group_id = music.linked_group_id = "picture-and-sound"
    music.range = TimeRange(start=SOURCE_TIMEBASE, end=4 * SOURCE_TIMEBASE)
    assert music.source is not None
    music.source.source_range = TimeRange(start=SOURCE_TIMEBASE, end=4 * SOURCE_TIMEBASE)
    validate_content(base, SNAPSHOT_FACTS)
    updated = apply_ops(base, [TemporalEdit(
        op="temporal_edit", action="move", target=EditTarget(kind="clip", id="clp_title"), start=0,
    )], {})
    validate_content(updated, SNAPSHOT_FACTS)
    assert _clip(updated, "clp_title").range == TimeRange(start=0, end=3 * SOURCE_TIMEBASE)
    moved_music = _clip(updated, "clp_bed")
    assert moved_music.range == TimeRange(start=0, end=3 * SOURCE_TIMEBASE)
    assert moved_music.source is not None
    assert moved_music.source.source_range == TimeRange(
        start=SOURCE_TIMEBASE, end=4 * SOURCE_TIMEBASE
    )
    assert _clip(updated, "clp_bg") == _clip(base, "clp_bg")


def test_time_map_keeps_offset_rational_until_shared_quantizer_at_custom_timebase():
    base = valid_content()
    for scene in base.scenes:
        scene.range = TimeRange(
            start=quantize_ticks(Fraction(scene.range.start, SOURCE_TIMEBASE) * 1000),
            end=quantize_ticks(Fraction(scene.range.end, SOURCE_TIMEBASE) * 1000),
        )
    for track in base.timeline.tracks:
        for clip in track.clips:
            clip.range = TimeRange(
                start=quantize_ticks(Fraction(clip.range.start, SOURCE_TIMEBASE) * 1000),
                end=quantize_ticks(Fraction(clip.range.end, SOURCE_TIMEBASE) * 1000),
            )
            for animation in clip.animations:
                for keyframe in animation.keyframes:
                    keyframe.at = quantize_ticks(Fraction(keyframe.at, SOURCE_TIMEBASE) * 1000)
    base.settings.timebase = 1000
    base.settings.fps.num = 25
    title = _clip(base, "clp_title")
    title.range = TimeRange(start=1, end=title.range.end)
    title.animations[0].keyframes = [Keyframe(at=300, value=0.5)]
    validate_content(base, SNAPSHOT_FACTS)

    updated = apply_ops(base, translate_revision(base, _args({
        "op": "time_map", "target": {"kind": "timeline"},
        "scale": 0.5, "offset_seconds": 0.0005, "source_policy": "crop_1x",
    })), {})
    validate_content(updated, SNAPSHOT_FACTS)
    # Output t=1 maps through 0.5×1+0.5 to exactly 1; rounding b to 1 first
    # would incorrectly produce 2. Clip-local animation only scales: 300→150;
    # adding b would incorrectly produce 151.
    assert _clip(updated, "clp_title").range.start == 1
    assert _clip(updated, "clp_title").animations[0].keyframes[0].at == 150
    assert timeline_duration(updated) == 2001
    music = _clip(updated, "clp_bed")
    assert music.source is not None and music.source.source_range is not None
    assert music.range.duration == 2000
    assert music.source.source_range.duration == 2 * SOURCE_TIMEBASE


def _rich_88_second_content() -> tuple[CompositionContent, dict]:
    scene_ranges = [
        ("scn_open", 0, 8),
        ("scn_chapter_1", 8, 28),
        ("scn_chapter_2", 28, 48),
        ("scn_chapter_3", 48, 68),
        ("scn_chapter_4", 68, 80),
        ("scn_close", 80, 88),
    ]
    scenes = [
        Scene(
            scene_id=scene_id,
            range=TimeRange(start=start * SOURCE_TIMEBASE, end=end * SOURCE_TIMEBASE),
            intent=scene_id,
            visual_description=f"Visible direction for {scene_id}",
        )
        for scene_id, start, end in scene_ranges
    ]
    layout = LayoutBox(x=0, y=0, width=1920, height=1080)
    background = Track(track_id="trk_stills", kind="visual", role="main", order=0)
    for clip_id, object_id, start, end in (
        ("clp_still_a", "obj_still_a", 0, 4),
        ("clp_still_b", "obj_still_b", 4, 8),
    ):
        background.clips.append(Clip(
            clip_id=clip_id,
            range=TimeRange(start=start * SOURCE_TIMEBASE, end=end * SOURCE_TIMEBASE),
            scene_id="scn_open",
            source={
                "snapshot_id": IMG_SNAPSHOT,
                "snapshot_digest": IMG_DIGEST,
            },
            object=ImageObject(kind="image", object_id=object_id, layout=layout),
        ))

    web_track = Track(track_id="trk_web", kind="visual", role="main", order=1)
    title_track = Track(track_id="trk_title", kind="visual", role="title", order=2)
    for scene_id, start, end in scene_ranges:
        duration = (end - start) * SOURCE_TIMEBASE
        web_track.clips.append(Clip(
            clip_id=f"clp_web_{scene_id}",
            range=TimeRange(start=start * SOURCE_TIMEBASE, end=end * SOURCE_TIMEBASE),
            scene_id=scene_id,
            source={"snapshot_id": WEB_SNAPSHOT, "snapshot_digest": WEB_DIGEST},
            object=WebObject(
                kind="web", object_id=f"obj_web_{scene_id}", view_id="view-main", layout=layout,
            ),
            animations=[
                Animation(
                    animation_id=f"anm_scale_{scene_id}",
                    target_object_id=f"obj_web_{scene_id}",
                    property="transform.scale",
                    keyframes=[Keyframe(at=0, value=1.0), Keyframe(at=duration, value=1.2)],
                ),
                Animation(
                    animation_id=f"anm_camera_{scene_id}",
                    target_object_id=f"obj_web_{scene_id}",
                    property="transform.position",
                    keyframes=[
                        Keyframe(at=0, value=(0.0, 0.0)),
                        Keyframe(at=duration // 2, value=(120.0, -40.0)),
                        Keyframe(at=duration, value=(80.0, -20.0)),
                    ],
                ),
            ],
        ))
        title_track.clips.append(Clip(
            clip_id=f"clp_text_{scene_id}",
            range=TimeRange(start=start * SOURCE_TIMEBASE, end=end * SOURCE_TIMEBASE),
            scene_id=scene_id,
            object=TextObject(
                kind="text",
                object_id=f"obj_text_{scene_id}",
                text=f"Exact copy for {scene_id}",
                layout=LayoutBox(x=160, y=100, width=1600, height=160),
                style=TextStyle(font_size=72, color="#FFFFFF"),
            ),
            animations=[
                Animation(
                    animation_id=f"anm_blur_{scene_id}",
                    target_object_id=f"obj_text_{scene_id}",
                    property="filter.blur",
                    keyframes=[Keyframe(at=0, value=12.0), Keyframe(at=duration, value=0.0)],
                ),
                Animation(
                    animation_id=f"anm_spacing_{scene_id}",
                    target_object_id=f"obj_text_{scene_id}",
                    property="text.letter_spacing",
                    keyframes=[Keyframe(at=0, value=0.2), Keyframe(at=duration, value=0.0)],
                ),
            ],
        ))
    music = Clip(
        clip_id="clp_music",
        range=TimeRange(start=0, end=88 * SOURCE_TIMEBASE),
        scene_id=None,
        source={
            "snapshot_id": AUDIO_SNAPSHOT,
            "snapshot_digest": AUDIO_DIGEST,
            "source_range": {"start": 0, "end": 88 * SOURCE_TIMEBASE},
        },
        object=AudioObject(kind="audio", object_id="obj_music", gain_db=-18),
        animations=[Animation(
            animation_id="anm_music_gain",
            target_object_id="obj_music",
            property="audio.gain",
            keyframes=[
                Keyframe(at=0, value=0.8),
                Keyframe(at=88 * SOURCE_TIMEBASE, value=1.0),
            ],
        )],
    )
    content = CompositionContent(
        settings={"width": 1920, "height": 1080},
        sources=[
            SourceBinding(snapshot_id=IMG_SNAPSHOT, snapshot_digest=IMG_DIGEST),
            SourceBinding(snapshot_id=WEB_SNAPSHOT, snapshot_digest=WEB_DIGEST),
            SourceBinding(snapshot_id=AUDIO_SNAPSHOT, snapshot_digest=AUDIO_DIGEST),
        ],
        scenes=scenes,
        timeline={
            "tracks": [
                background,
                web_track,
                title_track,
                Track(track_id="trk_music", kind="audio", role="music", order=0, clips=[music]),
            ],
            "transitions": [Transition(
                transition_id="trn_open",
                from_clip_id="clp_still_a",
                to_clip_id="clp_still_b",
                duration=SOURCE_TIMEBASE,
            )],
        },
    )
    facts = {
        **copy.deepcopy(SNAPSHOT_FACTS),
        AUDIO_SNAPSHOT: {
            **SNAPSHOT_FACTS[AUDIO_SNAPSHOT],
            "duration_ticks": 88 * SOURCE_TIMEBASE,
        },
        WEB_SNAPSHOT: {
            "digest": WEB_DIGEST,
            "kind": "web",
            "duration_ticks": None,
            "meta": {"views": [{
                "view_id": "view-main", "storage_key": "scenario/view-main.png", "digest": "e" * 64,
            }]},
        },
    }
    validate_content(content, facts)
    assert timeline_duration(content) == 88 * SOURCE_TIMEBASE
    return content, facts


def test_timeline_time_map_preserves_88_second_work_content_in_one_revision():
    base, facts = _rich_88_second_content()
    scale = 30 / 88
    ops = translate_revision(base, _args({
        "op": "time_map",
        "target": {"kind": "timeline"},
        "scale": scale,
        "offset_seconds": 0,
        "source_policy": "crop_1x",
    }))
    assert len(ops) == 1 and ops[0].op == "temporal_edit"
    updated = apply_ops(base, ops, {})
    validate_content(updated, facts)
    assert timeline_duration(updated) == 30 * SOURCE_TIMEBASE
    assert [scene.scene_id for scene in updated.scenes] == [scene.scene_id for scene in base.scenes]
    assert updated.sources == base.sources
    assert updated.settings == base.settings
    assert updated.timeline.transitions[0].transition_id == "trn_open"
    assert updated.timeline.transitions[0].duration == quantize_ticks(
        Fraction(str(scale)) * SOURCE_TIMEBASE
    )

    before_clips = {clip.clip_id: clip for track in base.timeline.tracks for clip in track.clips}
    before_animations = {
        animation.animation_id: animation
        for clip in before_clips.values()
        for animation in clip.animations
    }
    for track in updated.timeline.tracks:
        for clip in track.clips:
            before = before_clips[clip.clip_id]
            assert clip.object == before.object
            assert clip.scene_id == before.scene_id
            assert clip.linked_group_id == before.linked_group_id
            for animation in clip.animations:
                previous = before_animations[animation.animation_id]
                assert [keyframe.value for keyframe in animation.keyframes] == [
                    keyframe.value for keyframe in previous.keyframes
                ]
                assert [keyframe.easing for keyframe in animation.keyframes] == [
                    keyframe.easing for keyframe in previous.keyframes
                ]
                assert [keyframe.at for keyframe in animation.keyframes] == [
                    quantize_ticks(
                        Fraction(str(scale)) * (before.range.start + keyframe.at)
                    ) - clip.range.start
                    for keyframe in previous.keyframes
                ]
    music = _clip(updated, "clp_music")
    assert music.source is not None and music.source.source_range is not None
    assert music.source.snapshot_id == AUDIO_SNAPSHOT
    assert music.source.snapshot_digest == AUDIO_DIGEST
    assert music.source.source_range == TimeRange(start=0, end=30 * SOURCE_TIMEBASE)
    assert music.object.gain_db == -18
    assert [scene.visual_description for scene in updated.scenes] == [
        scene.visual_description for scene in base.scenes
    ]


def test_time_map_requires_explicit_music_crop_policy_and_never_mutates_base():
    base, _ = _rich_88_second_content()
    before = base.model_dump(mode="json")
    op = TemporalEdit(
        op="temporal_edit", action="time_map", target=EditTarget(kind="timeline"), scale=0.5,
    )
    with pytest.raises(TemporalEditError, match="crop_1x"):
        apply_ops(base, [op], {})
    assert base.model_dump(mode="json") == before


def test_time_map_rejects_speech_generator_and_video_without_partial_candidate():
    speech_base = valid_content()
    speech_base.timeline.tracks.append(Track(
        track_id="trk_dialogue", kind="audio", role="dialogue", order=1,
        clips=[Clip(
            clip_id="clp_speech", range=TimeRange(start=0, end=4 * SOURCE_TIMEBASE),
            scene_id="scn_open",
            object=SpeechObject(
                kind="speech", object_id="obj_speech", text="Reviewed narration",
                voice_id="voice", language="en",
            ),
        )],
    ))
    speech_base.scenes[0].speech_clip_ids = ["clp_speech"]
    validate_content(speech_base, SNAPSHOT_FACTS)

    generator_base = valid_content()
    generator_base.timeline.tracks.append(Track(
        track_id="trk_generator", kind="visual", role="main", order=2,
        clips=[Clip(
            clip_id="clp_generator", range=TimeRange(start=0, end=4 * SOURCE_TIMEBASE),
            scene_id="scn_open",
            object=GeneratorObject(
                kind="generator", object_id="obj_generator", runtime="image-v1",
                prompt="A still background", provider="minimax", model="image-01",
                output=GeneratedImageOutput(), layout=LayoutBox(x=0, y=0, width=1920, height=1080),
            ),
        )],
    ))
    validate_content(generator_base, SNAPSHOT_FACTS)

    video_base = valid_content()
    video = _clip(video_base, "clp_bg")
    video.object = VideoObject(
        kind="video", object_id="obj_bg", layout=video.object.layout,
    )
    assert video.source is not None
    video.source.source_range = TimeRange(start=0, end=4 * SOURCE_TIMEBASE)
    video_facts = copy.deepcopy(SNAPSHOT_FACTS)
    video_facts[IMG_SNAPSHOT] = {
        **video_facts[IMG_SNAPSHOT], "kind": "video", "duration_ticks": 4 * SOURCE_TIMEBASE,
    }
    validate_content(video_base, video_facts)

    for base in (speech_base, generator_base, video_base):
        before = base.model_dump(mode="json")
        with pytest.raises(TemporalCapabilityError, match="time_map|reviewed"):
            apply_ops(base, [TemporalEdit(
                op="temporal_edit", action="time_map", target=EditTarget(kind="timeline"),
                scale=0.5, source_policy="crop_1x",
            )], {})
        assert base.model_dump(mode="json") == before


def test_invalid_target_and_cross_scene_link_conflict_leave_base_unchanged():
    base, _ = _two_scene_content()
    before = base.model_dump(mode="json")
    with pytest.raises(TemporalEditError, match="does not exist"):
        apply_ops(base, [TemporalEdit(
            op="temporal_edit", action="move",
            target=EditTarget(kind="clip", id="clp_missing"), start=0,
        )], {})
    assert base.model_dump(mode="json") == before

    _clip(base, "clp_bg").linked_group_id = "cross-scene"
    _clip(base, "clp_bg_next").linked_group_id = "cross-scene"
    before = base.model_dump(mode="json")
    with pytest.raises(TemporalEditError, match="crosses the targeted Scene boundary"):
        apply_ops(base, [TemporalEdit(
            op="temporal_edit", action="move",
            target=EditTarget(kind="scene", id="scn_open"), start=SOURCE_TIMEBASE,
        )], {})
    assert base.model_dump(mode="json") == before
