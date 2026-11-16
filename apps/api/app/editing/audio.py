"""Ordinary audio-track expansion for Composition edit operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.editing.timing import seconds_to_ticks


@dataclass(frozen=True)
class MusicBed:
    snapshot_id: UUID
    snapshot_digest: str
    duration_ticks: int


def _keyframe(at: int, value: float, easing: str = "linear") -> dict[str, Any]:
    return {
        "at": at,
        "value": value,
        "easing": (
            {"kind": "linear", "params": None}
            if easing == "linear"
            else {"kind": "cubic_bezier", "params": [0.16, 1.0, 0.3, 1.0]}
        ),
    }


def instantiate_music_bed(
    bed: MusicBed, *, total_ticks: int, timebase: int
) -> list[dict[str, Any]]:
    """Tile one pinned audio source on the ordinary global music track."""
    if bed.duration_ticks <= 0 or total_ticks <= 0:
        return []
    track_id = "trk_music"
    gain_db = -20.0
    fade_in = seconds_to_ticks(1.0, timebase)
    fade_out = seconds_to_ticks(2.0, timebase)
    ops: list[dict[str, Any]] = [
        {
            "op": "add_track",
            "track": {
                "track_id": track_id,
                "kind": "audio",
                "role": "music",
                "order": 0,
                "clips": [],
            },
        },
        {"op": "bind_source", "snapshot_id": str(bed.snapshot_id)},
    ]
    position = 0
    index = 0
    while position < total_ticks:
        length = min(bed.duration_ticks, total_ticks - position)
        first = position == 0
        last = position + length >= total_ticks
        keyframes: list[dict[str, Any]] = []
        if first:
            keyframes.extend([_keyframe(0, 0.0), _keyframe(min(fade_in, length), 1.0, "ease")])
        else:
            keyframes.append(_keyframe(0, 1.0))
        if last:
            hold = length - fade_out
            if hold > keyframes[-1]["at"]:
                keyframes.append(_keyframe(hold, 1.0))
            if length > keyframes[-1]["at"]:
                keyframes.append(_keyframe(length, 0.0))
        object_id = f"obj_music_{index}"
        ops.append({
            "op": "add_clip",
            "track_id": track_id,
            "clip": {
                "clip_id": f"clp_music_{index}",
                "range": {"start": position, "end": position + length},
                "scene_id": None,
                "source": {
                    "snapshot_id": str(bed.snapshot_id),
                    "snapshot_digest": bed.snapshot_digest,
                    "source_range": {"start": 0, "end": length},
                },
                "object": {"kind": "audio", "object_id": object_id, "gain_db": gain_db},
                "animations": [{
                    "animation_id": f"anm_music_{index}_gain",
                    "target_object_id": object_id,
                    "text_part": None,
                    "property": "audio.gain",
                    "keyframes": keyframes,
                }],
            },
        })
        position += length
        index += 1
    return ops
