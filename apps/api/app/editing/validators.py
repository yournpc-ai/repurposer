"""Whole-candidate validation for CompositionContent (VIDEO_PROJECT §2.2).

The write door applies the full op batch and then validates the COMPLETE
candidate here — one seat for identity, reference, time and layout law.
Pure: snapshot facts arrive as plain data (the store resolves the rows), so
this module never touches the DB.
"""

from __future__ import annotations

from uuid import UUID

from app.editing.animation import derive_text_parts
from app.editing.fonts import LAYOUT_VERSION, SEGMENTATION_VERSION, font_resources
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    CompositionContent,
    GeneratorObject,
    ImageObject,
    ShapeObject,
    SpeechObject,
    TextObject,
    VideoObject,
    WebObject,
    speech_text_digest,
)
from app.editing.timing import source_ticks_to_output_ticks, ticks_to_frames

SnapshotFacts = dict[UUID, dict]


class ContentValidationError(ValueError):
    """The candidate version breaks content law; the batch never lands."""


def _fail(problems: list[str], msg: str) -> None:
    problems.append(msg)


def _validate_clip_source(
    clip: Clip, content: CompositionContent, snapshots: SnapshotFacts, problems: list[str]
) -> None:
    obj = clip.object
    src = clip.source
    if isinstance(obj, GeneratorObject):
        if src is not None:
            _fail(problems, f"clip {clip.clip_id}: generator sources are prepared, not bound media")
        if obj.runtime == "drawing-v1":
            expected_ticks = obj.output.duration_frames * content.settings.timebase // obj.output.fps
            if (
                expected_ticks * obj.output.fps != obj.output.duration_frames * content.settings.timebase
                or expected_ticks != clip.range.duration
            ):
                _fail(
                    problems,
                    f"clip {clip.clip_id}: program output frames/fps must exactly match its output window",
                )
        return
    if isinstance(obj, (TextObject, ShapeObject)):
        if src is not None:
            _fail(problems, f"clip {clip.clip_id}: {obj.kind} objects take no media source")
        if isinstance(obj, ShapeObject):
            return
        if obj.segmentation_version != SEGMENTATION_VERSION:
            _fail(problems, f"clip {clip.clip_id}: unsupported text segmentation version")
        if obj.layout_version != LAYOUT_VERSION:
            _fail(problems, f"clip {clip.clip_id}: unsupported text layout version")
        try:
            font_resources(obj.style.font.font_id, obj.style.font.digest, {obj.style.weight})
        except ValueError as exc:
            _fail(problems, f"clip {clip.clip_id}: {exc}")
        return
    if isinstance(obj, SpeechObject):
        if src is not None:
            _fail(problems, f"clip {clip.clip_id}: pending speech has no bound media source")
        return
    if src is None:
        _fail(problems, f"clip {clip.clip_id}: {obj.kind} objects require a source")
        return

    binding = next((b for b in content.sources if b.snapshot_id == src.snapshot_id), None)
    if binding is None:
        _fail(
            problems,
            f"clip {clip.clip_id}: source snapshot {src.snapshot_id} is not bound in this version",
        )
        return
    if binding.snapshot_digest != src.snapshot_digest:
        _fail(problems, f"clip {clip.clip_id}: source digest does not match the version binding")

    facts = snapshots.get(src.snapshot_id)
    if facts is None:
        _fail(problems, f"clip {clip.clip_id}: source snapshot {src.snapshot_id} does not exist")
        return
    if facts["digest"] != src.snapshot_digest:
        _fail(problems, f"clip {clip.clip_id}: source digest does not match the snapshot row")

    if isinstance(obj, (ImageObject, WebObject)):
        expected_kind = "web" if isinstance(obj, WebObject) else "image"
        if facts["kind"] != expected_kind:
            _fail(
                problems,
                f"clip {clip.clip_id}: {expected_kind} object bound to a {facts['kind']} snapshot",
            )
        if src.source_range is not None:
            _fail(problems, f"clip {clip.clip_id}: static sources must not carry source_range")
        if isinstance(obj, WebObject):
            views = (facts.get("meta") or {}).get("views") or []
            view = next((item for item in views if item.get("view_id") == obj.view_id), None)
            if view is None:
                _fail(
                    problems,
                    f"clip {clip.clip_id}: web view {obj.view_id} is absent "
                    "from the bound snapshot",
                )
            elif not view.get("storage_key") or len(str(view.get("digest", ""))) != 64:
                _fail(
                    problems, f"clip {clip.clip_id}: web view {obj.view_id} lacks immutable bytes"
                )
        return

    if isinstance(obj, (AudioObject, VideoObject)):
        expected_kind = "audio" if isinstance(obj, AudioObject) else "video"
        if facts["kind"] != expected_kind:
            _fail(
                problems,
                f"clip {clip.clip_id}: {expected_kind} object bound to a {facts['kind']} snapshot",
            )
        if src.source_range is None:
            _fail(problems, f"clip {clip.clip_id}: {expected_kind} sources require a source_range")
            return
        duration = facts.get("duration_ticks")
        if duration is None:
            _fail(problems, f"clip {clip.clip_id}: source snapshot has no probed duration")
            return
        if src.source_range.end > duration:
            _fail(
                problems,
                f"clip {clip.clip_id}: source_range ends past the source's real duration "
                f"({src.source_range.end} > {duration} source ticks) — a 1× clip may not "
                "invent source media",
            )
        source_len = source_ticks_to_output_ticks(
            src.source_range.duration, content.settings.timebase
        )
        if source_len != clip.range.duration:
            _fail(
                problems,
                f"clip {clip.clip_id}: source window ({source_len} ticks) and output window "
                f"({clip.range.duration} ticks) differ — only 1× mapping is supported",
            )


def _quantized_keys_have_collisions(
    anim: Animation, content: CompositionContent, shift: int
) -> bool:
    settings = content.settings
    frames = [
        ticks_to_frames(kf.at + shift, settings.timebase, settings.fps.num, settings.fps.den)
        for kf in anim.keyframes
    ]
    return len(frames) != len(set(frames))


def _validate_animation(
    clip: Clip, anim: Animation, content: CompositionContent, problems: list[str]
) -> None:
    obj = clip.object
    clip_ticks = clip.range.duration
    if anim.target_object_id != obj.object_id:
        _fail(
            problems,
            f"animation {anim.animation_id}: target {anim.target_object_id} is not an object "
            f"of its owning clip {clip.clip_id} (cross-clip targets never resolve)",
        )
    if anim.property == "audio.gain" and not isinstance(obj, (AudioObject, SpeechObject, VideoObject)):
        _fail(problems, f"animation {anim.animation_id}: audio.gain on a non-audio object")
    if anim.property != "audio.gain" and isinstance(obj, (AudioObject, SpeechObject)):
        _fail(problems, f"animation {anim.animation_id}: visual property on an audio object")

    seen_at: set[int] = set()
    for kf in anim.keyframes:
        if kf.at in seen_at:
            _fail(problems, f"animation {anim.animation_id}: duplicate keyframe at {kf.at}")
        seen_at.add(kf.at)
        if kf.at > clip_ticks:
            _fail(
                problems,
                f"animation {anim.animation_id}: keyframe at {kf.at} is past the clip's "
                f"local duration ({clip_ticks})",
            )
        if anim.property == "transform.position":
            if not isinstance(kf.value, tuple):
                _fail(problems, f"animation {anim.animation_id}: transform.position needs [x, y]")
        else:
            if not isinstance(kf.value, (int, float)) or isinstance(kf.value, bool):
                _fail(problems, f"animation {anim.animation_id}: {anim.property} needs a scalar")
            elif anim.property == "opacity" and not 0 <= kf.value <= 1:
                _fail(problems, f"animation {anim.animation_id}: opacity out of [0, 1]")
            elif anim.property == "transform.scale" and not 0 < kf.value <= 10:
                _fail(problems, f"animation {anim.animation_id}: scale out of (0, 10]")
            elif anim.property == "audio.gain" and not 0 <= kf.value <= 4:
                _fail(problems, f"animation {anim.animation_id}: gain out of [0, 4]")

    shifts = [0]
    if anim.text_part is not None:
        if not isinstance(obj, TextObject):
            _fail(problems, f"animation {anim.animation_id}: TextPart target on a non-text object")
            return
        target = anim.text_part
        if len(target.part_ids) != len(set(target.part_ids)):
            _fail(problems, f"animation {anim.animation_id}: duplicate TextPart target")
        parts = {part.part_id: part for part in derive_text_parts(obj.text, target.kind)}
        selected = [parts.get(part_id) for part_id in target.part_ids]
        missing = [part_id for part_id, part in zip(target.part_ids, selected) if part is None]
        if missing:
            _fail(
                problems,
                f"animation {anim.animation_id}: TextPart target(s) {missing} do not match the "
                "current text; re-target explicitly instead of remapping by index",
            )
            return
        ordered = sorted(
            (part for part in selected if part is not None), key=lambda p: p.text_range.start
        )
        shifts = [index * target.stagger for index in range(len(ordered))]
        for shift in shifts:
            if anim.keyframes and max(kf.at for kf in anim.keyframes) + shift > clip_ticks:
                _fail(
                    problems,
                    f"animation {anim.animation_id}: staggered keyframes exceed the clip window",
                )
    for shift in shifts:
        if _quantized_keys_have_collisions(anim, content, shift):
            _fail(
                problems,
                f"animation {anim.animation_id}: distinct keyframes collapse onto one output frame",
            )


def validate_content(content: CompositionContent, snapshots: SnapshotFacts) -> None:
    """Validate the COMPLETE candidate; raise ContentValidationError listing
    every violation found (one honest report, not the first failure)."""
    problems: list[str] = []

    for label, ids in (
        ("snapshot", [str(b.snapshot_id) for b in content.sources]),
        ("scene", [s.scene_id for s in content.scenes]),
        ("track", [t.track_id for t in content.timeline.tracks]),
        ("clip", [c.clip_id for t in content.timeline.tracks for c in t.clips]),
        ("object", [c.object.object_id for t in content.timeline.tracks for c in t.clips]),
        (
            "animation",
            [
                a.animation_id
                for t in content.timeline.tracks
                for c in t.clips
                for a in c.animations
            ],
        ),
    ):
        dupes = {item for item in ids if ids.count(item) > 1}
        if dupes:
            _fail(problems, f"duplicate {label} ids: {sorted(dupes)}")

    if not content.timeline.tracks:
        _fail(problems, "a version needs at least one track")

    total_ticks = 0
    scene_ids = {scene.scene_id for scene in content.scenes}
    clips_by_id: dict[str, Clip] = {}

    for track in content.timeline.tracks:
        seen_orders = [item.order for item in content.timeline.tracks if item.kind == track.kind]
        if seen_orders.count(track.order) > 1:
            _fail(
                problems,
                f"track {track.track_id}: {track.kind} order {track.order} is not unique",
            )
        ordered = sorted(track.clips, key=lambda clip: (clip.range.start, clip.range.end))
        for previous, following in zip(ordered, ordered[1:]):
            if following.range.start < previous.range.end:
                _fail(
                    problems,
                    f"track {track.track_id}: clips {previous.clip_id} and {following.clip_id} "
                    "overlap on one track",
                )
        for clip in track.clips:
            clips_by_id[clip.clip_id] = clip
            total_ticks = max(total_ticks, clip.range.end)
            if track.kind == "audio" and not isinstance(clip.object, (AudioObject, SpeechObject)):
                _fail(problems, f"clip {clip.clip_id}: non-audio object on an audio track")
            if track.kind == "visual" and isinstance(clip.object, (AudioObject, SpeechObject)):
                _fail(problems, f"clip {clip.clip_id}: audio object on a visual track")
            if isinstance(clip.object, SpeechObject) and track.role != "dialogue":
                _fail(problems, f"clip {clip.clip_id}: speech requires a dialogue track")
            if isinstance(clip.object, TextObject) and clip.object.caption is not None:
                if track.kind != "visual" or track.role != "caption":
                    _fail(problems, f"clip {clip.clip_id}: derived captions require a visual caption track")
            if clip.scene_id is not None and clip.scene_id not in scene_ids:
                _fail(problems, f"clip {clip.clip_id}: scene {clip.scene_id} does not exist")
            _validate_clip_source(clip, content, snapshots, problems)
            part_kinds = {
                anim.text_part.kind for anim in clip.animations if anim.text_part is not None
            }
            if "word" in part_kinds and "grapheme" in part_kinds:
                _fail(
                    problems,
                    f"clip {clip.clip_id}: mixed word + grapheme TextPart hierarchy is unsupported",
                )
            seen_targets: set[tuple[str, str | None]] = set()
            for anim in clip.animations:
                part_ids = anim.text_part.part_ids if anim.text_part is not None else [None]
                for part_id in part_ids:
                    key = (anim.property, part_id)
                    if key in seen_targets:
                        _fail(
                            problems,
                            f"clip {clip.clip_id}: overlapping animations on "
                            f"{anim.target_object_id}.{anim.property} for TextPart {part_id}",
                        )
                    seen_targets.add(key)
                _validate_animation(clip, anim, content, problems)

    speech_clips = {
        clip.object.object_id: clip
        for clip in clips_by_id.values()
        if isinstance(clip.object, SpeechObject)
    }
    for clip in clips_by_id.values():
        if not isinstance(clip.object, TextObject) or clip.object.caption is None:
            continue
        derivation = clip.object.caption
        speech_clip = speech_clips.get(derivation.speech_object_id)
        if speech_clip is None:
            _fail(problems, f"clip {clip.clip_id}: caption speech source does not exist")
            continue
        if clip.scene_id != speech_clip.scene_id:
            _fail(problems, f"clip {clip.clip_id}: caption and speech must belong to the same scene")
        if derivation.state == "derived" and clip.range != speech_clip.range:
            _fail(problems, f"clip {clip.clip_id}: derived caption must share its speech window")
        speech = speech_clip.object
        assert isinstance(speech, SpeechObject)
        if derivation.state == "derived" and (
            clip.object.text != speech.text
            or derivation.source_text_digest != speech_text_digest(speech.text)
        ):
            _fail(problems, f"clip {clip.clip_id}: derived caption does not match its speech text")

    for scene in content.scenes:
        if total_ticks and scene.range.end > total_ticks:
            _fail(
                problems,
                f"scene {scene.scene_id}: range ends past the timeline's last clip",
            )
        for ref in scene.speech_clip_ids:
            speech_clip = clips_by_id.get(ref)
            if speech_clip is None:
                _fail(problems, f"scene {scene.scene_id}: speech clip {ref} does not exist")
            elif not isinstance(speech_clip.object, SpeechObject):
                _fail(problems, f"scene {scene.scene_id}: clip {ref} is not a SpeechClip")
            elif speech_clip.scene_id != scene.scene_id:
                _fail(problems, f"scene {scene.scene_id}: speech clip {ref} belongs to another scene")
            elif (
                speech_clip.range.start < scene.range.start
                or speech_clip.range.end > scene.range.end
            ):
                _fail(problems, f"scene {scene.scene_id}: speech clip {ref} escapes the reviewed scene window")

    if content.timeline.transitions:
        from app.editing.transitions import transition_windows
        try:
            transition_windows(content, snapshots)
        except ValueError as exc:
            _fail(problems, str(exc))
    if total_ticks == 0:
        _fail(problems, "a version needs at least one clip")
    if problems:
        raise ContentValidationError("; ".join(problems))
