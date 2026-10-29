"""Frame-preserving clip slices and source-time beat mapping."""
from __future__ import annotations

import copy
from fractions import Fraction
from uuid import NAMESPACE_URL, uuid5

from app.editing.animation import derive_text_parts
from app.editing.schemas import Clip, CompositionContent, Easing, Keyframe, SpeechObject, TextObject, TimeRange
from app.editing.timing import SOURCE_TIMEBASE, frames_to_ticks, ticks_to_frames


def _source_ticks(ticks, timebase):
    value = Fraction(ticks * SOURCE_TIMEBASE, timebase)
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


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
    Pending Speech requires text/alignment edits, not arbitrary audio cuts.
    """
    if not extend and not (clip.range.start <= kept.start < kept.end <= clip.range.end):
        raise ValueError("trim/split must keep a nonempty subrange of the clip")
    if isinstance(clip.object, SpeechObject):
        raise ValueError("edit pending Speech text/window explicitly; split/trim targets fixed media or native visuals")
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
