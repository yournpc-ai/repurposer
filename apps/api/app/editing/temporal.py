"""Frame-preserving slices, source-time beats and the temporal edit algebra.

The generic algebra resolves stable-id targets and explicit associations once,
then transforms one candidate. Output ranges and clip-local animation times
remain exact rationals until the shared tick quantizer; object values, layout,
copy and immutable snapshot identities are not temporal coordinates.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Literal
from uuid import NAMESPACE_URL, uuid5

from app.editing.animation import derive_text_parts
from app.editing.edits import EditError
from app.editing.schemas import (
    AudioObject,
    Clip,
    CompositionContent,
    Easing,
    EditTarget,
    GeneratorObject,
    Keyframe,
    SpeechObject,
    TextObject,
    TimeRange,
    VideoObject,
)
from app.editing.timing import (
    SOURCE_TIMEBASE,
    frames_to_ticks,
    output_ticks_to_source_ticks,
    quantize_ticks,
    ticks_to_frames,
)

if TYPE_CHECKING:
    from app.editing.edits import TemporalEdit


class TemporalEditError(EditError):
    """The requested target, linkage or media policy cannot preserve the work."""


class TemporalCapabilityError(TemporalEditError):
    """A deterministic media boundary, not a repairable argument rejection."""

    def __init__(self, message: str, *, medium: str) -> None:
        super().__init__(message)
        self.medium = medium


def _source_ticks(ticks, timebase):
    return output_ticks_to_source_ticks(ticks, timebase)


def _value(keys, frame):
    if frame <= keys[0][0]:
        return keys[0][1].value
    if frame >= keys[-1][0]:
        return keys[-1][1].value
    for (start, a), (end, b) in zip(keys, keys[1:]):
        if start <= frame < end:
            x = (frame - start) / (end - start)
            if a.easing.kind == "hold":
                return a.value
            if a.easing.kind == "cubic_bezier":
                x1, y1, x2, y2 = a.easing.params
                lo, hi, t = 0.0, 1.0, x
                for _ in range(24):
                    cx = 3 * (1-t)**2 * t * x1 + 3 * (1-t) * t*t * x2 + t**3
                    if cx < x:
                        lo = t
                    else:
                        hi = t
                    t = (lo + hi) / 2
                x = 3 * (1-t)**2 * t * y1 + 3 * (1-t) * t*t * y2 + t**3
            if isinstance(a.value, tuple):
                return tuple(v + (w-v)*x for v, w in zip(a.value, b.value))
            return a.value + (b.value-a.value)*x
    raise ValueError("animation has no segment at frame")


def slice_clip(content: CompositionContent, clip: Clip, kept: TimeRange, *, extend: bool = False) -> Clip:
    """Keep an output subrange, with no ripple; preserve every rendered frame.

    Curves (including staggered TextParts) are sampled at output frames. This
    avoids changing a clipped Bezier's shape by merely moving its endpoints.
    VideoObject's embedded original audio follows its exact source window.
    Pending Speech and Generator sources require semantic source edits, not
    arbitrary output cuts.
    """
    if not extend and not (clip.range.start <= kept.start < kept.end <= clip.range.end):
        raise ValueError("trim/split must keep a nonempty subrange of the clip")
    if isinstance(clip.object, (SpeechObject, GeneratorObject)):
        raise ValueError("pending Speech/Generator windows cannot be sliced as fixed media")
    result = copy.deepcopy(clip)
    settings = content.settings
    frame = lambda ticks: ticks_to_frames(ticks, settings.timebase, settings.fps.num, settings.fps.den)
    offset = frame(kept.start) - frame(clip.range.start)
    length = frame(kept.end) - frame(kept.start)
    if length <= 0:
        raise ValueError("slice must retain at least one output frame")
    result.range = kept
    if result.source and result.source.source_range:
        original = result.source.source_range
        source_length = _source_ticks(kept.duration, settings.timebase)
        first_frame = ticks_to_frames(original.start, SOURCE_TIMEBASE, settings.fps.num, settings.fps.den) + offset
        first_tick = frames_to_ticks(first_frame, SOURCE_TIMEBASE, settings.fps.num, settings.fps.den)
        result.source.source_range = TimeRange(start=first_tick, end=first_tick+source_length)
    result.animations = []
    for animation in clip.animations:
        parts = [None]
        if animation.text_part:
            assert isinstance(clip.object, TextObject)
            parts = [part.part_id for part in derive_text_parts(clip.object.text, animation.text_part.kind)
                     if part.part_id in animation.text_part.part_ids]
        for index, part_id in enumerate(parts):
            anim = copy.deepcopy(animation)
            shift = index * animation.text_part.stagger if animation.text_part else 0
            keys = [(frame(k.at + shift), k) for k in sorted(animation.keyframes, key=lambda k: k.at)]
            if part_id:
                anim.animation_id = uuid5(NAMESPACE_URL, f"slice:{animation.animation_id}:{part_id}").hex
                anim.text_part.part_ids = [part_id]
                anim.text_part.stagger = 0
            anim.keyframes = [Keyframe(
                at=frames_to_ticks(i, settings.timebase, settings.fps.num, settings.fps.den),
                value=_value(keys, offset+i), easing=Easing(kind="linear"),
            ) for i in range(length+1)
                if frames_to_ticks(i, settings.timebase, settings.fps.num, settings.fps.den) <= kept.duration]
            result.animations.append(anim)
    return result


# ---------------------------------------------------------------------------
# Generic target × operation × ripple/source-policy algebra (VIDEO_PROJECT §6.6)
# ---------------------------------------------------------------------------


def timeline_duration(content: CompositionContent) -> int:
    """The only total-duration law: every clip counts, including global audio."""
    return max(
        (clip.range.end for track in content.timeline.tracks for clip in track.clips),
        default=0,
    )


def _clips_by_id(content: CompositionContent) -> dict[str, Clip]:
    return {
        clip.clip_id: clip
        for track in content.timeline.tracks
        for clip in track.clips
    }


def _track_by_clip(content: CompositionContent) -> dict[str, str]:
    return {
        clip.clip_id: track.track_id
        for track in content.timeline.tracks
        for clip in track.clips
    }


@dataclass(frozen=True)
class ResolvedTarget:
    clip_ids: frozenset[str]
    scene_ids: frozenset[str]
    track_ids: frozenset[str]
    range: TimeRange | None


def resolve_temporal_target(
    content: CompositionContent,
    target: EditTarget,
    *,
    action: Literal["move", "trim", "split", "delete", "time_map"],
) -> ResolvedTarget:
    """Resolve only stable ids and declared relations, never time intersection.

    Scene membership and linked groups are symmetric. Derived captions follow
    Speech for every operation; deleting a caption alone does not delete its
    Speech. A linked group crossing a targeted Scene boundary must be named
    explicitly instead of being silently pulled into the edit.
    """
    clips = _clips_by_id(content)
    scenes = {scene.scene_id: scene for scene in content.scenes}
    tracks = {track.track_id: track for track in content.timeline.tracks}
    root_clip_ids: set[str] = set()
    root_scene_ids: set[str] = set()
    root_track_ids: set[str] = set()

    def require_clip(clip_id: str) -> None:
        if clip_id not in clips:
            raise TemporalEditError(f"clip {clip_id!r} does not exist in the base version")
        root_clip_ids.add(clip_id)

    def require_scene(scene_id: str) -> None:
        if scene_id not in scenes:
            raise TemporalEditError(f"scene {scene_id!r} does not exist in the base version")
        root_scene_ids.add(scene_id)

    def require_track(track_id: str) -> None:
        track = tracks.get(track_id)
        if track is None:
            raise TemporalEditError(f"track {track_id!r} does not exist in the base version")
        root_track_ids.add(track_id)
        root_clip_ids.update(clip.clip_id for clip in track.clips)

    if target.kind == "clip":
        require_clip(target.id or "")
    elif target.kind == "scene":
        require_scene(target.id or "")
    elif target.kind == "track":
        require_track(target.id or "")
    elif target.kind == "selection":
        for clip_id in target.clip_ids:
            require_clip(clip_id)
        for scene_id in target.scene_ids:
            require_scene(scene_id)
        for track_id in target.track_ids:
            require_track(track_id)
    else:
        root_clip_ids.update(clips)
        root_scene_ids.update(scenes)
        root_track_ids.update(tracks)

    selected_clip_ids = set(root_clip_ids)
    selected_scene_ids = set(root_scene_ids)
    if selected_scene_ids:
        selected_clip_ids.update(
            clip.clip_id for clip in clips.values() if clip.scene_id in selected_scene_ids
        )

    while True:
        additions: set[str] = set()
        selected_clips = [clips[clip_id] for clip_id in selected_clip_ids]
        groups = {clip.linked_group_id for clip in selected_clips if clip.linked_group_id}
        if groups:
            additions.update(
                clip.clip_id for clip in clips.values() if clip.linked_group_id in groups
            )
        speech_object_ids = {
            clip.object.object_id for clip in selected_clips if isinstance(clip.object, SpeechObject)
        }
        if speech_object_ids:
            additions.update(
                clip.clip_id
                for clip in clips.values()
                if isinstance(clip.object, TextObject)
                and clip.object.caption is not None
                and clip.object.caption.state == "derived"
                and clip.object.caption.speech_object_id in speech_object_ids
            )
        if action != "delete":
            captioned_speech_ids = {
                clip.object.caption.speech_object_id
                for clip in selected_clips
                if isinstance(clip.object, TextObject)
                and clip.object.caption is not None
                and clip.object.caption.state == "derived"
            }
            additions.update(
                clip.clip_id
                for clip in clips.values()
                if isinstance(clip.object, SpeechObject)
                and clip.object.object_id in captioned_speech_ids
            )
        additions -= selected_clip_ids
        if not additions:
            break
        selected_clip_ids.update(additions)
        if selected_scene_ids:
            selected_clip_ids.update(
                clip.clip_id for clip in clips.values() if clip.scene_id in selected_scene_ids
            )

    if root_scene_ids:
        for clip_id in selected_clip_ids - root_clip_ids:
            if clips[clip_id].scene_id not in root_scene_ids:
                raise TemporalEditError(
                    f"linked clip {clip_id!r} crosses the targeted Scene boundary; "
                    "name every related Scene/clip explicitly"
                )

    roots = [clips[clip_id].range for clip_id in root_clip_ids]
    roots.extend(scenes[scene_id].range for scene_id in root_scene_ids)
    if not roots and (action != "delete" or not root_track_ids):
        raise TemporalEditError("the temporal target resolves to no clips or scenes")
    target_range = None if not roots else TimeRange(
        start=min(item.start for item in roots),
        end=max(item.end for item in roots),
    )
    return ResolvedTarget(
        clip_ids=frozenset(selected_clip_ids),
        scene_ids=frozenset(selected_scene_ids),
        track_ids=frozenset(root_track_ids),
        range=target_range,
    )


def _translated(range_: TimeRange, delta: int) -> TimeRange:
    start, end = range_.start + delta, range_.end + delta
    if start < 0 or end <= start:
        raise TemporalEditError("the temporal edit would put an output range before time zero")
    return TimeRange(start=start, end=end)


def _mapped(range_: TimeRange, scale: Fraction, offset: Fraction) -> TimeRange:
    start = quantize_ticks(scale * range_.start + offset)
    end = quantize_ticks(scale * range_.end + offset)
    if start < 0 or end <= start:
        raise TemporalEditError("time_map must keep every output range nonempty and at/after zero")
    return TimeRange(start=start, end=end)


def _intersection(left: TimeRange, right: TimeRange) -> TimeRange | None:
    start, end = max(left.start, right.start), min(left.end, right.end)
    return TimeRange(start=start, end=end) if end > start else None


def _time_mapped_clip(
    content: CompositionContent,
    clip: Clip,
    scale: Fraction,
    offset: Fraction,
    source_policy: str | None,
) -> Clip:
    result = copy.deepcopy(clip)
    result.range = _mapped(clip.range, scale, offset)
    if scale != 1:
        if isinstance(clip.object, (SpeechObject, GeneratorObject, VideoObject)):
            raise TemporalCapabilityError(
                f"clip {clip.clip_id!r} ({clip.object.kind}) cannot preserve its reviewed "
                "semantics under an output-duration time_map",
                medium=clip.object.kind,
            )
        if isinstance(clip.object, AudioObject):
            if source_policy != "crop_1x":
                raise TemporalEditError(
                    f"audio clip {clip.clip_id!r} needs explicit source_policy='crop_1x'; "
                    "time_map never changes its playback rate"
                )
            if clip.source is None or clip.source.source_range is None:
                raise TemporalEditError(f"audio clip {clip.clip_id!r} has no fixed source window")
            source_start = clip.source.source_range.start
            source_duration = output_ticks_to_source_ticks(
                result.range.duration, content.settings.timebase
            )
            assert result.source is not None
            result.source.source_range = TimeRange(
                start=source_start,
                end=source_start + source_duration,
            )
    for animation in result.animations:
        for keyframe in animation.keyframes:
            # Quantize on the SAME output grid as the Clip, then rebase. This
            # keeps local 0 at 0 and a terminal keyframe exactly on the new
            # Clip end; independent rounding can otherwise drift by one tick.
            keyframe.at = quantize_ticks(
                scale * (clip.range.start + keyframe.at) + offset
            ) - result.range.start
        if animation.text_part is not None:
            animation.text_part.stagger = quantize_ticks(scale * animation.text_part.stagger)
    return result


def _trimmed_clip(
    content: CompositionContent,
    clip: Clip,
    kept: TimeRange,
    source_policy: str | None,
) -> Clip | None:
    intersection = _intersection(clip.range, kept)
    if intersection == clip.range:
        return copy.deepcopy(clip)
    if isinstance(clip.object, (SpeechObject, GeneratorObject)):
        raise TemporalCapabilityError(
            f"clip {clip.clip_id!r} ({clip.object.kind}) cannot be trimmed without "
            "changing its reviewed source semantics",
            medium=clip.object.kind,
        )
    if isinstance(clip.object, (AudioObject, VideoObject)) and source_policy != "crop_1x":
        raise TemporalEditError(
            f"fixed-media clip {clip.clip_id!r} needs explicit source_policy='crop_1x'"
        )
    if intersection is None:
        return None
    try:
        return slice_clip(content, clip, intersection)
    except ValueError as exc:
        raise TemporalEditError(f"clip {clip.clip_id!r} cannot be trimmed: {exc}") from exc


@dataclass(frozen=True)
class _RippleUnit:
    """One edited structural unit; Scene units ripple globally, Clip units per track."""

    track_id: str | None
    old_end: int
    delta: int


def apply_temporal_edit(content: CompositionContent, edit: TemporalEdit) -> CompositionContent:
    """Apply one generic edit to a deep-copied candidate or reject it whole."""
    resolved = resolve_temporal_target(content, edit.target, action=edit.action)
    original_clips = _clips_by_id(content)
    original_scenes = {scene.scene_id: scene for scene in content.scenes}
    track_of = _track_by_clip(content)
    direct_clips: dict[str, Clip | None] = {}
    direct_scenes = {}

    if edit.action == "move":
        assert edit.start is not None
        if resolved.range is None:
            raise TemporalEditError("move needs a target with a temporal range")
        delta = edit.start - resolved.range.start
        for clip_id in resolved.clip_ids:
            result = copy.deepcopy(original_clips[clip_id])
            result.range = _translated(result.range, delta)
            direct_clips[clip_id] = result
        for scene_id in resolved.scene_ids:
            result = copy.deepcopy(original_scenes[scene_id])
            result.range = _translated(result.range, delta)
            direct_scenes[scene_id] = result
    elif edit.action == "time_map":
        assert edit.scale is not None
        scale, offset = Fraction(str(edit.scale)), Fraction(edit.offset)
        for clip_id in resolved.clip_ids:
            direct_clips[clip_id] = _time_mapped_clip(
                content, original_clips[clip_id], scale, offset, edit.source_policy
            )
        for scene_id in resolved.scene_ids:
            result = copy.deepcopy(original_scenes[scene_id])
            result.range = _mapped(result.range, scale, offset)
            direct_scenes[scene_id] = result
    elif edit.action == "trim":
        assert edit.start is not None and edit.end is not None
        if resolved.range is None:
            raise TemporalEditError("trim needs a target with a temporal range")
        kept = TimeRange(start=edit.start, end=edit.end)
        if kept.start < resolved.range.start or kept.end > resolved.range.end:
            raise TemporalEditError("trim must keep a subrange of the resolved target")
        for clip_id in resolved.clip_ids:
            direct_clips[clip_id] = _trimmed_clip(
                content, original_clips[clip_id], kept, edit.source_policy
            )
        for scene_id in resolved.scene_ids:
            intersection = _intersection(original_scenes[scene_id].range, kept)
            result = copy.deepcopy(original_scenes[scene_id]) if intersection else None
            if result is not None and intersection is not None:
                result.range = intersection
            direct_scenes[scene_id] = result
    else:
        direct_clips = {clip_id: None for clip_id in resolved.clip_ids}
        direct_scenes = {scene_id: None for scene_id in resolved.scene_ids}

    units: list[_RippleUnit] = []
    if edit.ripple == "forward":
        for scene_id in resolved.scene_ids:
            old = original_scenes[scene_id].range
            new = direct_scenes[scene_id]
            new_end = new.range.end if new is not None else old.start
            if new_end != old.end:
                units.append(_RippleUnit(track_id=None, old_end=old.end, delta=new_end-old.end))
        for clip_id in resolved.clip_ids:
            original = original_clips[clip_id]
            if original.scene_id in resolved.scene_ids:
                continue
            old = original.range
            new = direct_clips[clip_id]
            new_end = new.range.end if new is not None else old.start
            if new_end != old.end:
                units.append(_RippleUnit(
                    track_id=track_of[clip_id], old_end=old.end, delta=new_end-old.end
                ))

    candidate = copy.deepcopy(content)
    affine: dict[str, tuple[Fraction, Fraction]] = {}
    direct_affine = (Fraction(1), Fraction(0))
    if edit.action == "time_map":
        assert edit.scale is not None
        direct_affine = (Fraction(str(edit.scale)), Fraction(edit.offset))
    for track in candidate.timeline.tracks:
        updated_clips: list[Clip] = []
        for clip in track.clips:
            if clip.clip_id in direct_clips:
                changed = direct_clips[clip.clip_id]
                if changed is not None:
                    updated_clips.append(changed)
                    if edit.action == "time_map":
                        affine[clip.clip_id] = direct_affine
                continue
            shift = sum(
                unit.delta for unit in units
                if unit.old_end <= clip.range.start
                and (unit.track_id is None or unit.track_id == track.track_id)
            )
            changed = copy.deepcopy(clip)
            if shift:
                changed.range = _translated(changed.range, shift)
            updated_clips.append(changed)
            if edit.action == "time_map":
                affine[clip.clip_id] = (Fraction(1), Fraction(shift))
        track.clips = updated_clips

    if edit.action == "delete" and resolved.track_ids:
        candidate.timeline.tracks = [
            track for track in candidate.timeline.tracks
            if track.track_id not in resolved.track_ids
        ]

    updated_scenes = []
    for scene in candidate.scenes:
        if scene.scene_id in direct_scenes:
            changed = direct_scenes[scene.scene_id]
            if changed is not None:
                updated_scenes.append(changed)
            continue
        shift = sum(
            unit.delta for unit in units
            if unit.track_id is None and unit.old_end <= scene.range.start
        )
        changed = copy.deepcopy(scene)
        if shift:
            changed.range = _translated(changed.range, shift)
        updated_scenes.append(changed)
    candidate.scenes = updated_scenes

    if edit.action in {"trim", "delete"}:
        affected_scene_ids = set(resolved.scene_ids) | {
            original_clips[clip_id].scene_id for clip_id in resolved.clip_ids
        }
        for scene in candidate.scenes:
            if scene.scene_id in affected_scene_ids:
                scene.visual_description = None

    final_clips = _clips_by_id(candidate)
    final_scenes = {scene.scene_id: scene for scene in candidate.scenes}
    for scene in candidate.scenes:
        scene.speech_clip_ids = [
            ref for ref in scene.speech_clip_ids
            if ref in final_clips and isinstance(final_clips[ref].object, SpeechObject)
        ]

    transitions = []
    for transition in candidate.timeline.transitions:
        if transition.from_clip_id not in final_clips or transition.to_clip_id not in final_clips:
            continue
        outgoing = final_clips[transition.from_clip_id]
        incoming = final_clips[transition.to_clip_id]
        if outgoing.range.end != incoming.range.start:
            raise TemporalEditError(
                f"transition {transition.transition_id!r} would lose its adjacent cut; "
                "target both clips with one compatible transform"
            )
        duration = transition.duration
        if edit.action == "time_map":
            outgoing_map = affine[outgoing.clip_id]
            incoming_map = affine[incoming.clip_id]
            if outgoing_map != incoming_map:
                raise TemporalEditError(
                    f"transition {transition.transition_id!r} crosses different time mappings"
                )
            duration = quantize_ticks(outgoing_map[0] * duration)
        transitions.append(transition.model_copy(update={"duration": duration}))
    candidate.timeline.transitions = transitions

    changed_clip_ids = set(resolved.clip_ids) | {
        clip_id for clip_id, clip in final_clips.items()
        if clip.range != original_clips[clip_id].range
    }
    changed_scene_ids = set(resolved.scene_ids) | {
        scene_id for scene_id, scene in final_scenes.items()
        if scene.range != original_scenes[scene_id].range
    }
    touched_groups = {
        original_clips[clip_id].linked_group_id
        for clip_id in changed_clip_ids
        if original_clips[clip_id].linked_group_id
    }
    for group_id in touched_groups:
        before = [clip for clip in original_clips.values() if clip.linked_group_id == group_id]
        after = [clip for clip in final_clips.values() if clip.linked_group_id == group_id]
        if len(before) != len(after):
            raise TemporalEditError(f"linked_group {group_id!r} would lose only part of its media")
        if after and any(clip.range != after[0].range for clip in after[1:]):
            raise TemporalEditError(f"linked_group {group_id!r} would lose synchronized output windows")

    for clip in final_clips.values():
        if not isinstance(clip.object, TextObject) or clip.object.caption is None:
            continue
        if clip.object.caption.state != "derived":
            continue
        speech = next(
            (
                candidate_clip for candidate_clip in final_clips.values()
                if isinstance(candidate_clip.object, SpeechObject)
                and candidate_clip.object.object_id == clip.object.caption.speech_object_id
            ),
            None,
        )
        if speech is None or speech.range != clip.range:
            raise TemporalEditError(
                f"derived caption {clip.clip_id!r} would lose its Speech window"
            )

    for clip in final_clips.values():
        if clip.scene_id is None:
            continue
        scene = final_scenes.get(clip.scene_id)
        if scene is None:
            raise TemporalEditError(f"clip {clip.clip_id!r} would retain a deleted Scene")
        if clip.clip_id in changed_clip_ids or scene.scene_id in changed_scene_ids:
            if clip.range.start < scene.range.start or clip.range.end > scene.range.end:
                raise TemporalEditError(
                    f"clip {clip.clip_id!r} would escape Scene {scene.scene_id!r}; "
                    "target the Scene or change the membership explicitly"
                )
    return candidate


def snap_cut(content, outgoing, incoming, music, facts, tolerance):
    """Frozen source grid → output frames; preserve the work's total duration."""
    from app.editing.timing import seconds_to_ticks

    if outgoing.range.end != incoming.range.start:
        raise ValueError("snap_cut needs adjacent clips")
    if not music.source or not music.source.source_range:
        raise ValueError("snap_cut needs a fixed music source window")
    grid = (facts.get("meta") or {}).get("beat_grid") or {}
    beats = grid.get("beats") or []
    source = music.source.source_range
    if not beats and grid.get("bpm"):
        period = 60 / grid["bpm"]
        beats = [i*period for i in range(int(source.end / SOURCE_TIMEBASE / period)+1)]
    candidates = []
    settings = content.settings
    for beat in beats:
        position = seconds_to_ticks(beat, SOURCE_TIMEBASE)
        if not source.start <= position < source.end:
            continue
        mapped = music.range.start + seconds_to_ticks(str(Fraction(position-source.start, SOURCE_TIMEBASE)), settings.timebase)
        mapped_frame = ticks_to_frames(mapped, settings.timebase, settings.fps.num, settings.fps.den)
        mapped = frames_to_ticks(mapped_frame, settings.timebase, settings.fps.num, settings.fps.den)
        if music.range.start <= mapped < music.range.end:
            candidates.append(mapped)
    if not candidates:
        raise ValueError("this frozen music window has no BeatGrid or BPM; no beat was fabricated")
    cut = min(candidates, key=lambda at: (abs(at-outgoing.range.end), at))
    if abs(cut-outgoing.range.end) > tolerance:
        raise ValueError("no beat inside the requested snap tolerance; cut remains unchanged")
    return [slice_clip(content, outgoing, TimeRange(start=outgoing.range.start, end=cut), extend=True),
            slice_clip(content, incoming, TimeRange(start=cut, end=incoming.range.end), extend=True)]
