"""Native caption tracks projected from a frozen upload's ASR sentences."""
from __future__ import annotations

from uuid import UUID

from app.editing.edits import AddClip, AddTrack, Op
from app.editing.schemas import (
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
from app.editing.source_selection import SourceSentence
from app.editing.timing import seconds_to_ticks, source_ticks_to_output_ticks


def source_caption_ops(
    content: CompositionContent,
    *,
    scene_id: str,
    snapshot_id: UUID,
    snapshot_digest: str,
    source_range: TimeRange,
    sentences: tuple[SourceSentence, ...],
) -> list[Op]:
    scene = next((item for item in content.scenes if item.scene_id == scene_id), None)
    if scene is None:
        raise ValueError(f"caption scene {scene_id!r} does not exist")
    track_id = f"trk_caption_{scene_id}"
    if any(track.track_id == track_id for track in content.timeline.tracks):
        raise ValueError(f"caption track {track_id!r} already exists")
    timebase = content.settings.timebase
    ops: list[Op] = []
    clips: list[Clip] = []
    for sentence in sentences:
        start = max(source_range.start, seconds_to_ticks(sentence.start))
        end = min(source_range.end, seconds_to_ticks(sentence.end))
        if end <= start:
            continue
        output_start = scene.range.start + source_ticks_to_output_ticks(
            start - source_range.start, timebase
        )
        output_end = scene.range.start + source_ticks_to_output_ticks(
            end - source_range.start, timebase
        )
        if output_end <= output_start or output_start < scene.range.start or output_end > scene.range.end:
            raise ValueError(f"caption {sentence.sentence_id!r} escapes its source window")
        text = sentence.text.strip()
        if not text:
            continue
        object_id = f"obj_caption_{scene_id}_{sentence.sentence_id}"
        clips.append(Clip(
            clip_id=f"clp_caption_{scene_id}_{sentence.sentence_id}",
            range=TimeRange(start=output_start, end=output_end),
            scene_id=scene_id,
            source=None,
            object=TextObject(
                kind="text",
                object_id=object_id,
                text=text,
                layout=LayoutBox(
                    x=content.settings.width * 0.08,
                    y=content.settings.height - 190,
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
                    source_range=TimeRange(start=start, end=end),
                    source_text_digest=speech_text_digest(text),
                ),
            ),
            animations=[],
        ))
    if not clips:
        raise ValueError("the selected source window has no ASR captions")
    order = max(
        (track.order for track in content.timeline.tracks if track.kind == "visual"),
        default=-1,
    ) + 1
    ops.append(AddTrack(
        op="add_track",
        track=Track(
            track_id=track_id,
            kind="visual",
            role="caption",
            order=order,
            clips=[],
        ),
    ))
    ops.extend(AddClip(op="add_clip", track_id=track_id, clip=clip) for clip in clips)
    return ops
