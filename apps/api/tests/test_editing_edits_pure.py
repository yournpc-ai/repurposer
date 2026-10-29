"""Pure op-apply / validation tests for the editing write door's inner half.

No DB: snapshot facts arrive as plain dicts, exactly the shape
``editing.store.snapshot_facts`` resolves. Locks the op vocabulary, patch
semantics (absent vs explicit null), the copy/remap law and the whole-
candidate validator's rejections (illegal references, time-domain law,
overlap, animation targets).
"""

from __future__ import annotations

import copy
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter

from app.editing.edits import EditError, Op, apply_ops, duplicate_clip
from app.editing.schemas import CompositionContent, TimeRange
from app.editing.timing import SOURCE_TIMEBASE
from app.editing.store import content_digest_of
from app.editing.validators import ContentValidationError, validate_content

ADAPT = TypeAdapter(Op)

IMG_SNAPSHOT = UUID("11111111-1111-1111-1111-111111111111")
IMG_DIGEST = "a" * 64
AUDIO_SNAPSHOT = UUID("22222222-2222-2222-2222-222222222222")
AUDIO_DIGEST = "b" * 64

FOUR_S_TICKS = 4 * SOURCE_TIMEBASE  # 4s at the version timebase (both 90000)

SNAPSHOT_FACTS = {
    IMG_SNAPSHOT: {
        "digest": IMG_DIGEST,
        "kind": "image",
        "duration_ticks": None,
        "owner_id": uuid4(),
        "storage_key": "snapshots/img.png",
    },
    AUDIO_SNAPSHOT: {
        "digest": AUDIO_DIGEST,
        "kind": "audio",
        "duration_ticks": FOUR_S_TICKS,
        "owner_id": uuid4(),
        "storage_key": "snapshots/audio.wav",
    },
}


def creation_ops() -> list[Op]:
    """A valid one-scene sample film: image + text over a fixed music bed."""
    ops = [
        {"op": "set_settings", "settings": {"width": 1920, "height": 1080}},
        {"op": "bind_source", "snapshot_id": str(IMG_SNAPSHOT)},
        {"op": "bind_source", "snapshot_id": str(AUDIO_SNAPSHOT)},
        {
            "op": "add_scene",
            "scene": {
                "scene_id": "scn_open",
                "range": {"start": 0, "end": FOUR_S_TICKS},
                "intent": "opening",
            },
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_main", "kind": "visual", "role": "main", "order": 0},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_title", "kind": "visual", "role": "title", "order": 1},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_music", "kind": "audio", "role": "music", "order": 0},
        },
        {
            "op": "add_clip",
            "track_id": "trk_main",
            "clip": {
                "clip_id": "clp_bg",
                "range": {"start": 0, "end": FOUR_S_TICKS},
                "scene_id": "scn_open",
                "source": {"snapshot_id": str(IMG_SNAPSHOT), "snapshot_digest": IMG_DIGEST},
                "object": {
                    "kind": "image",
                    "object_id": "obj_bg",
                    "layout": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                },
            },
        },
        {
            "op": "add_clip",
            "track_id": "trk_title",
            "clip": {
                "clip_id": "clp_title",
                "range": {"start": SOURCE_TIMEBASE, "end": FOUR_S_TICKS},
                "scene_id": "scn_open",
                "object": {
                    "kind": "text",
                    "object_id": "obj_title",
                    "text": "Hello",
                    "layout": {"x": 160, "y": 480, "width": 1600, "height": 120},
                    "style": {"font_size": 96, "color": "#FFFFFF"},
                },
                "animations": [
                    {
                        "animation_id": "anm_fade",
                        "target_object_id": "obj_title",
                        "property": "opacity",
                        "keyframes": [
                            {"at": 0, "value": 0},
                            {"at": 27000, "value": 1},
                        ],
                    }
                ],
            },
        },
        {
            "op": "add_clip",
            "track_id": "trk_music",
            "clip": {
                "clip_id": "clp_bed",
                "range": {"start": 0, "end": FOUR_S_TICKS},
                "source": {
                    "snapshot_id": str(AUDIO_SNAPSHOT),
                    "snapshot_digest": AUDIO_DIGEST,
                    "source_range": {"start": 0, "end": FOUR_S_TICKS},
                },
                "object": {"kind": "audio", "object_id": "obj_bed", "gain_db": -20},
            },
        },
    ]
    return [ADAPT.validate_python(o) for o in ops]


def valid_content() -> CompositionContent:
    content = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        creation_ops(),
        {sid: f["digest"] for sid, f in SNAPSHOT_FACTS.items()},
    )
    validate_content(content, SNAPSHOT_FACTS)
    return content


def test_chat_split_then_trim_preserves_curve_frames_and_linked_audio():
    from app.editing.schemas import Easing, Keyframe

    content = valid_content()
    title = _clip_of(content, "clp_title")
    music = next(c for t in content.timeline.tracks for c in t.clips if c.object.kind == "audio")
    title.linked_group_id = music.linked_group_id = "linked"
    music.range = TimeRange(start=SOURCE_TIMEBASE, end=FOUR_S_TICKS)
    music.source.source_range = TimeRange(start=SOURCE_TIMEBASE, end=FOUR_S_TICKS)
    title.animations[0].keyframes = [
        Keyframe(at=0, value=0, easing=Easing(kind="cubic_bezier", params=(0.42, 0, 0.58, 1))),
        Keyframe(at=3*SOURCE_TIMEBASE, value=1),
    ]
    result = apply_ops(content, [ADAPT.validate_python({
        "op": "split_clip", "clip_id": title.clip_id, "at": 2*SOURCE_TIMEBASE,
        "new_clip_id": "clp_right", "new_object_id": "obj_right",
    })], {})
    validate_content(result, SNAPSHOT_FACTS)
    right = _clip_of(result, "clp_right")
    assert right.animations[0].keyframes[0].value == pytest.approx(0.2317748, abs=1e-6)
    assert _clip_of(result, title.clip_id).animations[0].keyframes[-1].value == right.animations[0].keyframes[0].value
    linked_audio = next(c for t in result.timeline.tracks for c in t.clips
                        if c.object.kind == "audio" and c.linked_group_id == right.linked_group_id)
    assert linked_audio.source.source_range == TimeRange(start=2*SOURCE_TIMEBASE, end=FOUR_S_TICKS)
    kept = TimeRange(start=seconds_ticks(2.25), end=seconds_ticks(3.75))
    trimmed = apply_ops(result, [ADAPT.validate_python({
        "op": "trim_clip", "clip_id": right.clip_id, "range": kept.model_dump(),
    })], {})
    validate_content(trimmed, SNAPSHOT_FACTS)
    assert _clip_of(trimmed, linked_audio.clip_id).range == kept
    from app.editing.timing import ticks_to_frames
    audio_range = _clip_of(trimmed, linked_audio.clip_id).source.source_range
    assert (ticks_to_frames(audio_range.start, SOURCE_TIMEBASE, 30),
            ticks_to_frames(audio_range.end, SOURCE_TIMEBASE, 30)) == (68, 113)
    assert audio_range.duration == kept.duration
    assert _clip_of(trimmed, "clp_bg") == _clip_of(content, "clp_bg")


def seconds_ticks(value):
    from app.editing.timing import seconds_to_ticks
    return seconds_to_ticks(value)


def test_adjacent_media_crossfade_compiles_handles_and_frozen_grid_snap():
    from app.editing.temporal import snap_cut
    from app.editing.video_spec import compile_video_spec

    content = valid_content()
    content = apply_ops(content, [ADAPT.validate_python({
        "op": "split_clip", "clip_id": "clp_bg", "at": seconds_ticks(2),
        "new_clip_id": "clp_next", "new_object_id": "obj_next",
    })], {})
    a, b = _clip_of(content, "clp_bg"), _clip_of(content, "clp_next")
    music = next(c for t in content.timeline.tracks for c in t.clips if c.object.kind == "audio")
    for clip in snap_cut(content, a, b, music, {"meta": {"beat_grid": {"beats": [0.1, 1.1, 2.1, 3.1], "bpm": 60}}}, seconds_ticks(.2)):
        content = apply_ops(content, [ADAPT.validate_python({"op": "update_clip", "clip_id": clip.clip_id,
            "range": clip.range.model_dump(), "source": clip.source.model_dump(),
            "animations": [x.model_dump() for x in clip.animations]})], {})
    content = apply_ops(content, [ADAPT.validate_python({"op": "set_transition", "transition": {
        "transition_id": "trn_one", "from_clip_id": a.clip_id, "to_clip_id": b.clip_id,
        "duration": seconds_ticks(.4),
    }})], {})
    validate_content(content, SNAPSHOT_FACTS)
    spec = compile_video_spec(content, SNAPSHOT_FACTS, composition_id=uuid4(), version_id=uuid4(), content_digest="c"*64)
    assert spec["transitions"][0] == {"transition_id": "trn_one", "kind": "crossfade",
        "from_clip_id": "clp_bg", "to_clip_id": "clp_next", "start_frame": 57, "end_frame": 69, "cut_frame": 63}
    main = spec["tracks"][0]["clips"]
    assert (main[0]["end_frame"], main[1]["start_frame"], spec["duration_frames"]) == (69, 57, 120)


def test_sample_content_validates():
    content = valid_content()
    assert len(content.timeline.tracks) == 3
    assert content.scenes[0].scene_id == "scn_open"


def test_digest_stable_and_content_sensitive():
    a = content_digest_of(valid_content())
    assert a == content_digest_of(valid_content())
    changed = apply_ops(
        valid_content(),
        [ADAPT.validate_python({"op": "update_scene", "scene_id": "scn_open", "intent": "hook"})],
        {},
    )
    assert content_digest_of(changed) != a


def test_update_patch_absent_keeps_explicit_null_clears():
    content = valid_content()
    ops = [
        ADAPT.validate_python(
            {"op": "update_scene", "scene_id": "scn_open", "visual_description": "a skyline"}
        )
    ]
    updated = apply_ops(content, ops, {})
    assert updated.scenes[0].visual_description == "a skyline"
    assert updated.scenes[0].intent == "opening"  # absent key untouched
    cleared = apply_ops(
        updated,
        [ADAPT.validate_python({"op": "update_scene", "scene_id": "scn_open", "visual_description": None})],
        {},
    )
    assert cleared.scenes[0].visual_description is None


def test_move_scene_moves_owned_clips_and_preserves_source_and_local_animation():
    content = valid_content()
    before = content.model_dump()
    moved = apply_ops(content, [ADAPT.validate_python({
        "op": "move_scene", "scene_id": "scn_open", "start": 90000,
    })], {})
    validate_content(moved, SNAPSHOT_FACTS)
    assert moved.scenes[0].range.start == 90000
    for original_track, moved_track in zip(content.timeline.tracks, moved.timeline.tracks):
        for original, result in zip(original_track.clips, moved_track.clips):
            if original.scene_id == "scn_open":
                assert result.range.start == original.range.start + 90000
                assert result.range.end == original.range.end + 90000
                assert result.source == original.source
                assert result.animations == original.animations
            else:
                assert result == original  # global music stays at its original output time
    assert content.model_dump() == before
    with pytest.raises(EditError, match="use move_scene"):
        apply_ops(content, [ADAPT.validate_python({
            "op": "update_scene", "scene_id": "scn_open",
            "range": {"start": 90000, "end": FOUR_S_TICKS + 90000},
        })], {})


def test_remove_scene_removes_owned_content_and_keeps_global_music():
    content = valid_content()
    # A reference from another scene must not survive the removed content.
    other = content.scenes[0].model_copy(deep=True)
    other.scene_id = "scn_other"
    other.speech_clip_ids = ["clp_title"]
    content.scenes.append(other)
    removed = apply_ops(content, [ADAPT.validate_python({
        "op": "remove_scene", "scene_id": "scn_open",
    })], {})
    validate_content(removed, SNAPSHOT_FACTS)
    assert [scene.scene_id for scene in removed.scenes] == ["scn_other"]
    assert removed.scenes[0].speech_clip_ids == []
    assert [c.clip_id for t in removed.timeline.tracks for c in t.clips] == ["clp_bed"]
    assert removed.timeline.tracks[-1].clips == content.timeline.tracks[-1].clips
    assert len(content.timeline.tracks[0].clips) == 1  # input unchanged


def test_remove_track_requires_empty():
    with pytest.raises(EditError, match="remove them first"):
        apply_ops(valid_content(), [ADAPT.validate_python({"op": "remove_track", "track_id": "trk_main"})], {})


def test_remove_clip_detaches_scene_speech_refs():
    content = copy.deepcopy(valid_content())
    content.scenes[0].speech_clip_ids = ["clp_title"]
    updated = apply_ops(
        content, [ADAPT.validate_python({"op": "remove_clip", "clip_id": "clp_title"})], {}
    )
    assert updated.scenes[0].speech_clip_ids == []


def test_unbind_referenced_source_rejected():
    with pytest.raises(EditError, match="still referenced"):
        apply_ops(
            valid_content(),
            [ADAPT.validate_python({"op": "unbind_source", "snapshot_id": str(IMG_SNAPSHOT)})],
            {},
        )


def test_failed_batch_leaves_input_untouched():
    content = valid_content()
    before = content_digest_of(content)
    with pytest.raises(EditError):
        apply_ops(
            content,
            [
                ADAPT.validate_python({"op": "remove_clip", "clip_id": "clp_title"}),
                ADAPT.validate_python({"op": "remove_clip", "clip_id": "clp_ghost"}),
            ],
            {},
        )
    assert content_digest_of(content) == before  # pure: the input never mutates


def test_duplicate_clip_remaps_internal_ids():
    clone = duplicate_clip(
        valid_content(),
        "clp_title",
        new_clip_id="clp_title_2",
        new_object_id="obj_title_2",
        new_animation_ids=["anm_fade_2"],
    )
    assert clone.clip_id == "clp_title_2"
    assert clone.object.object_id == "obj_title_2"
    assert clone.animations[0].animation_id == "anm_fade_2"
    # The copy's animation points at the COPY's object, never the original's.
    assert clone.animations[0].target_object_id == "obj_title_2"


# --- whole-candidate validator rejections ------------------------------------


def _clip_of(content: CompositionContent, clip_id: str):
    return next(
        c for t in content.timeline.tracks for c in t.clips if c.clip_id == clip_id
    )


def _invalid(ops_patch) -> str:
    """Apply a mutation to the sample content, return the rejection text."""
    content = valid_content()
    candidate = ops_patch(content)
    with pytest.raises(ContentValidationError) as exc:
        validate_content(candidate, SNAPSHOT_FACTS)
    return str(exc.value)


def test_static_source_must_not_carry_source_range():
    def patch(content: CompositionContent) -> CompositionContent:
        clip = content.timeline.tracks[0].clips[0]
        clip.source.source_range = TimeRange(start=0, end=FOUR_S_TICKS)
        return content

    assert "must not carry source_range" in _invalid(patch)


def test_audio_requires_source_window_and_1x_law():
    def no_window(content: CompositionContent) -> CompositionContent:
        _clip_of(content, "clp_bed").source.source_range = None
        return content

    assert "require a source_range" in _invalid(no_window)

    def stretched(content: CompositionContent) -> CompositionContent:
        _clip_of(content, "clp_bed").source.source_range.end = 2 * SOURCE_TIMEBASE
        return content

    assert "only 1× mapping" in _invalid(stretched)


def test_source_past_real_duration_rejected():
    def patch(content: CompositionContent) -> CompositionContent:
        bed = _clip_of(content, "clp_bed")
        bed.range.end = 5 * SOURCE_TIMEBASE
        bed.source.source_range.end = 5 * SOURCE_TIMEBASE
        return content

    assert "past the source's real duration" in _invalid(patch)


def test_unbound_or_digest_mismatched_source_rejected():
    def unbound(content: CompositionContent) -> CompositionContent:
        content.sources = [b for b in content.sources if b.snapshot_id != IMG_SNAPSHOT]
        return content

    assert "not bound in this version" in _invalid(unbound)

    def drifted(content: CompositionContent) -> CompositionContent:
        _clip_of(content, "clp_bg").source.snapshot_digest = "f" * 64
        return content

    assert "digest" in _invalid(drifted)


def test_same_track_overlap_rejected():
    def patch(content: CompositionContent) -> CompositionContent:
        # Move the title onto the main track — [1s, 4s] overlaps clp_bg's
        # [0, 4s], and same-track non-transition overlap is law-rejected.
        title = _clip_of(content, "clp_title")
        track_of = next(t for t in content.timeline.tracks if t.track_id == "trk_title")
        track_of.clips = [c for c in track_of.clips if c.clip_id != "clp_title"]
        next(t for t in content.timeline.tracks if t.track_id == "trk_main").clips.append(title)
        return content

    assert "overlap on one track" in _invalid(patch)


def test_animation_target_law():
    def cross_clip(content: CompositionContent) -> CompositionContent:
        _clip_of(content, "clp_bg").animations.append(
            _clip_of(content, "clp_title").animations[0].model_copy()
        )
        return content

    assert "owning clip" in _invalid(cross_clip)

    def duplicate_key(content: CompositionContent) -> CompositionContent:
        anim = _clip_of(content, "clp_title").animations[0]
        anim.keyframes.append(anim.keyframes[0].model_copy())
        return content

    assert "duplicate keyframe" in _invalid(duplicate_key)

    def gain_on_text(content: CompositionContent) -> CompositionContent:
        _clip_of(content, "clp_title").animations[0].property = "audio.gain"
        return content

    assert "non-audio object" in _invalid(gain_on_text)
