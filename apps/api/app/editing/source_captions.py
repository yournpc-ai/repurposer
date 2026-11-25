"""Native caption tracks projected from a frozen upload's ASR sentences."""
from __future__ import annotations

from uuid import UUID

from app.editing.caption_timing import TimedPhrase, chunk_timed_words, split_cue_into_timed_phrases, words_in_window
from app.editing.edits import AddClip, AddTrack, Op
from app.editing.revisions import text_safe_layout
from app.editing.schemas import (
    Clip,
    CompositionContent,
    Scene,
    SourceCaptionDerivation,
    TextObject,
    TimeRange,
    Track,
    speech_text_digest,
)
from app.editing.source_selection import SourceSentence
from app.editing.text_presets import default_caption_text_style
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks, source_ticks_to_output_ticks


def source_caption_clips(
    content: CompositionContent, *, scene: Scene, source_range: TimeRange, sentence_id: str,
    phrases: list[TimedPhrase], prefix: str, snapshot_id: UUID, snapshot_digest: str,
    alignment: str = "faster-whisper-source-v1", narration_alignment_id: UUID | None = None,
    narration_content_digest: str | None = None,
) -> list[Clip]:
    default_style = default_caption_text_style(
        content.settings,
        font_size=max(28, round(content.settings.width * 38 / 1920)),
        align="center",
        line_height=1.3,
    )
    layout = text_safe_layout(content.settings.width, content.settings.height, "bottom", role="caption")
    clips = []
    for index, phrase in enumerate(phrases, 1):
        start = max(source_range.start, seconds_to_ticks(phrase.time_begin_ms / 1000))
        end = min(source_range.end, seconds_to_ticks(phrase.time_end_ms / 1000))
        if end <= start:
            continue
        timebase = content.settings.timebase
        out_start = scene.range.start + source_ticks_to_output_ticks(start - source_range.start, timebase)
        out_end = scene.range.start + source_ticks_to_output_ticks(end - source_range.start, timebase)
        if out_end <= out_start:
            continue
        if out_end > scene.range.end:
            raise ValueError(f"caption {sentence_id!r} escapes its source window")
        suffix = f"{prefix}_{scene.scene_id}_{sentence_id}"
        if len(phrases) > 1:
            suffix += f"_p{index}"
        clips.append(Clip(
            clip_id=f"clp_{suffix}", range=TimeRange(start=out_start, end=out_end), scene_id=scene.scene_id,
            object=TextObject(
                kind="text", object_id=f"obj_{suffix}", text=phrase.text, layout=layout, style=default_style,
                caption=SourceCaptionDerivation(
                    snapshot_id=snapshot_id, snapshot_digest=snapshot_digest, sentence_id=sentence_id,
                    source_range=TimeRange(start=start, end=end), source_text_digest=speech_text_digest(phrase.text),
                    alignment=alignment, narration_alignment_id=narration_alignment_id,
                    narration_content_digest=narration_content_digest,
                ),
            ),
        ))
    return clips


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
    clips = []
    for sentence in sentences:
        if sentence.words:
            words = words_in_window(sentence.words, source_range.start / SOURCE_TIMEBASE, source_range.end / SOURCE_TIMEBASE)
            phrases = chunk_timed_words(words, verbatim=True)
        else:
            phrases = split_cue_into_timed_phrases(sentence.text, sentence.start * 1000, sentence.end * 1000)
        clips.extend(source_caption_clips(
            content, scene=scene, source_range=source_range, sentence_id=sentence.sentence_id,
            phrases=phrases, prefix="caption", snapshot_id=snapshot_id, snapshot_digest=snapshot_digest,
        ))
    ops: list[Op] = []
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
