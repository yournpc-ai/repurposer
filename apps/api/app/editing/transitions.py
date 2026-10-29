"""Centered dissolves over adjacent opaque media, with real source handles."""
from app.editing.schemas import ImageObject, Transform, VideoObject, WebObject
from app.editing.timing import SOURCE_TIMEBASE, ticks_to_frames


def transition_windows(content, snapshots):
    settings = content.settings
    frame = lambda ticks: ticks_to_frames(ticks, settings.timebase, settings.fps.num, settings.fps.den)
    rows = []
    used_pairs = set()
    for transition in content.timeline.transitions:
        track = next((track for track in content.timeline.tracks
                      if any(c.clip_id == transition.from_clip_id for c in track.clips)
                      and any(c.clip_id == transition.to_clip_id for c in track.clips)), None)
        if track is None or track.kind != "visual":
            raise ValueError("crossfade needs two clips on the same visual track")
        a = next(c for c in track.clips if c.clip_id == transition.from_clip_id)
        b = next(c for c in track.clips if c.clip_id == transition.to_clip_id)
        if a.range.end != b.range.start:
            raise ValueError("crossfade needs adjacent clips; it does not move their cut")
        cut, duration = frame(a.range.end), frame(transition.duration)
        if duration < 2:
            raise ValueError("crossfade needs at least two output frames")
        start, end = cut-duration//2, cut+(duration-duration//2)
        if start < frame(a.range.start) or end > frame(b.range.end):
            raise ValueError("crossfade window exceeds its adjacent clips")
        pair = (a.clip_id, b.clip_id)
        if pair in used_pairs:
            raise ValueError("one crossfade per adjacent pair")
        used_pairs.add(pair)
        for clip, before, after in ((a, 0, end-cut), (b, cut-start, 0)):
            obj = clip.object
            if not isinstance(obj, (VideoObject, ImageObject, WebObject)):
                raise ValueError("crossfade currently consumes fixed image/web/video media")
            box = obj.layout
            if (box.x, box.y, box.width, box.height) != (0, 0, settings.width, settings.height) or obj.fit != "cover":
                raise ValueError("first crossfade consumer needs full-canvas opaque media with cover fit")
            if obj.opacity != 1 or obj.transform != Transform() or any(
                animation.property != "audio.gain" for animation in clip.animations
            ):
                raise ValueError("first crossfade consumer needs opaque full-canvas media without external visual transforms or opacity animation")
            if clip.source and clip.source.source_range:
                src = clip.source.source_range
                total = snapshots[clip.source.snapshot_id].get("duration_ticks")
                source_frame = lambda ticks: ticks_to_frames(ticks, SOURCE_TIMEBASE, settings.fps.num, settings.fps.den)
                if source_frame(src.start) < before or total is None or source_frame(src.end)+after > source_frame(total):
                    raise ValueError("crossfade needs real source handles; choose a shorter transition or a wider source window")
        if any(row["start_frame"] < end and start < row["end_frame"]
               and set(pair) & {row["from_clip_id"], row["to_clip_id"]} for row in rows):
            raise ValueError("crossfades sharing a clip must not overlap")
        rows.append({"transition_id": transition.transition_id, "kind": "crossfade",
                     "from_clip_id": a.clip_id, "to_clip_id": b.clip_id,
                     "start_frame": start, "end_frame": end, "cut_frame": cut})
    return rows
