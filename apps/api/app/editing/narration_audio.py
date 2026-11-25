"""Ordinary dialogue audio and native captions from a fixed narration word axis."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.editing.alignment import NarrationPayload, narration_words
from app.editing.caption_timing import chunk_timed_words
from app.editing.source_captions import source_caption_clips
from app.editing.edits import AddClip, AddTrack, BindSource, Op
from app.editing.schemas import (
    AudioObject,
    Clip,
    CompositionContent,
    TimeRange,
    Track,
)
from app.editing.timing import source_ticks_to_output_ticks


def narration_audio_ops(
    content: CompositionContent,
    *,
    scene_id: str,
    snapshot_id: UUID,
    snapshot_digest: str,
    alignment: Any,
) -> list[Op]:
    scene = next((item for item in content.scenes if item.scene_id == scene_id), None)
    if scene is None:
        raise ValueError(f"dialogue scene {scene_id!r} does not exist")
    if alignment.audio_snapshot_id != snapshot_id or alignment.audio_digest != snapshot_digest:
        raise ValueError("narration alignment and frozen audio identities differ")
    if alignment.status not in {"READY", "ALIGNED"} or not alignment.content_digest:
        raise ValueError("narration has no fixed word axis")
    payload = NarrationPayload.model_validate(alignment.payload)
    output_duration = source_ticks_to_output_ticks(payload.duration_ticks, content.settings.timebase)
    if output_duration > scene.range.duration:
        raise ValueError("Aligned narration exceeds its Scene; retime the Scene instead of trimming audio")
    duration = payload.duration_ticks
    ops: list[Op] = []
    if snapshot_id not in {binding.snapshot_id for binding in content.sources}:
        ops.append(BindSource(op="bind_source", snapshot_id=snapshot_id))
    dialogue_track = next(
        (track for track in content.timeline.tracks if track.kind == "audio" and track.role == "dialogue"),
        None,
    )
    if dialogue_track is None:
        dialogue_track = Track(
            track_id="trk_dialogue",
            kind="audio",
            role="dialogue",
            order=max((track.order for track in content.timeline.tracks if track.kind == "audio"), default=-1) + 1,
            clips=[],
        )
        ops.append(AddTrack(op="add_track", track=dialogue_track))
    if any(clip.clip_id == f"clp_dialogue_{scene_id}" for track in content.timeline.tracks for clip in track.clips):
        raise ValueError("this exact dialogue clip already exists")
    ops.append(AddClip(
        op="add_clip",
        track_id=dialogue_track.track_id,
        clip=Clip(
            clip_id=f"clp_dialogue_{scene_id}",
            range=TimeRange(start=scene.range.start, end=scene.range.start + output_duration),
            scene_id=scene_id,
            source={
                "snapshot_id": snapshot_id,
                "snapshot_digest": snapshot_digest,
                "source_range": {"start": 0, "end": duration},
            },
            object=AudioObject(kind="audio", object_id=f"obj_dialogue_{scene_id}", gain_db=0),
            animations=[],
        ),
    ))

    caption_track_id = f"trk_narration_caption_{scene_id}"
    if any(track.track_id == caption_track_id for track in content.timeline.tracks):
        raise ValueError(f"caption track {caption_track_id!r} already exists")
    ops.append(AddTrack(
        op="add_track",
        track=Track(
            track_id=caption_track_id, kind="visual", role="caption",
            order=max((track.order for track in content.timeline.tracks if track.kind == "visual"), default=-1) + 1,
            clips=[],
        ),
    ))
    for sentence in payload.sentences:
        clips = source_caption_clips(
            content, scene=scene, source_range=TimeRange(start=0, end=duration), sentence_id=sentence.sentence_id,
            phrases=chunk_timed_words(narration_words(sentence), verbatim=True), prefix="narration_caption",
            snapshot_id=snapshot_id, snapshot_digest=snapshot_digest, alignment=alignment.algorithm,
            narration_alignment_id=alignment.id, narration_content_digest=alignment.content_digest,
        )
        ops.extend(AddClip(op="add_clip", track_id=caption_track_id, clip=clip) for clip in clips)
    return ops
