"""Ordinary dialogue audio and native captions from a READY NarrationAlignment."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.editing.alignment import NarrationPayload
from app.editing.edits import AddClip, AddTrack, BindSource, Op
from app.editing.schemas import (
    AudioObject,
    Clip,
    CompositionContent,
    LayoutBox,
    SourceCaptionDerivation,
    TextObject,
    TextStyle,
    TimeRange,
    Track,
    speech_text_digest,
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
    if alignment.status != "READY" or not alignment.content_digest:
        raise ValueError("narration alignment is not READY")
    payload = NarrationPayload.model_validate(alignment.payload)
    output_duration = source_ticks_to_output_ticks(payload.duration_ticks, content.settings.timebase)
    if output_duration > scene.range.duration:
        raise ValueError("READY narration exceeds its Scene; retime the Scene instead of trimming audio")
    duration = payload.duration_ticks
    caption_sentences = [
        (sentence, sentence.start_tick, sentence.end_tick)
        for sentence in payload.sentences
    ]
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
    if caption_sentences:
        ops.append(AddTrack(
            op="add_track",
            track=Track(
                track_id=caption_track_id,
                kind="visual",
                role="caption",
                order=max((track.order for track in content.timeline.tracks if track.kind == "visual"), default=-1) + 1,
                clips=[],
            ),
        ))
    for sentence, source_start, source_end in caption_sentences:
        output_start = scene.range.start + source_ticks_to_output_ticks(
            source_start, content.settings.timebase
        )
        output_end = scene.range.start + source_ticks_to_output_ticks(
            source_end, content.settings.timebase
        )
        if output_end <= output_start or output_end > scene.range.end:
            raise ValueError(f"narration caption {sentence.sentence_id!r} escapes its audio window")
        text = sentence.text.strip()
        ops.append(AddClip(
            op="add_clip",
            track_id=caption_track_id,
            clip=Clip(
                clip_id=f"clp_narration_caption_{scene_id}_{sentence.sentence_id}",
                range=TimeRange(start=output_start, end=output_end),
                scene_id=scene_id,
                source=None,
                object=TextObject(
                    kind="text",
                    object_id=f"obj_narration_caption_{scene_id}_{sentence.sentence_id}",
                    text=text,
                    layout=LayoutBox(
                        x=content.settings.width * 0.08,
                        y=content.settings.height - 340,
                        width=content.settings.width * 0.84,
                        height=130,
                    ),
                    style=TextStyle(
                        font_size=max(28, round(content.settings.width * 38 / 1920)),
                        color="#FFFFFF",
                        background=None,
                        weight=600,
                        align="center",
                        line_height=1.3,
                    ),
                    caption=SourceCaptionDerivation(
                        snapshot_id=snapshot_id,
                        snapshot_digest=snapshot_digest,
                        sentence_id=sentence.sentence_id,
                        source_range=TimeRange(start=source_start, end=source_end),
                        source_text_digest=speech_text_digest(text),
                        alignment=alignment.algorithm,
                        narration_alignment_id=alignment.id,
                        narration_content_digest=alignment.content_digest,
                    ),
                ),
                animations=[],
            ),
        ))
    return ops
