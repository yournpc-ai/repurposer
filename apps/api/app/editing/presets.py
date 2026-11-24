"""Built-in native text presets and their deterministic edit-op expansion.

A preset is a birth-time authoring method only. These pure functions resolve
TextParts and optional READY narration facts, then return ordinary write-door
ops. Saved versions and video-spec contain only Tracks/Clips/Objects and final
keyframes; neither a renderer nor a later revision loads this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.editing.alignment import (
    NARRATION_ALGORITHM,
    NarrationPayload,
    NarrationSentence,
    find_word,
    narration_anchor_part_kind,
    resolve_narration_word,
)
from app.editing.animation import derive_text_parts
from app.editing.edits import AddClip, AddTrack, EditTarget, Op, UpdateClip
from app.editing.schemas import (
    Animation,
    CaptionDerivation,
    Clip,
    CompositionContent,
    Easing,
    ImageObject,
    Keyframe,
    LayoutBox,
    NarrationAlignmentRef,
    NarrationAnchor,
    ShapeObject,
    SpeechObject,
    TextObject,
    TextPartTarget,
    TextStyle,
    TimeRange,
    Track,
    Transform,
    VideoObject,
    WebObject,
    speech_text_digest,
)
from app.editing.timing import (
    frames_to_ticks,
    output_ticks_to_source_ticks,
    source_ticks_to_output_ticks,
    ticks_to_frames,
)


class PresetError(ValueError):
    """A preset cannot preserve its native content/timing contract."""


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NarrationWordInput(_Params):
    payload: NarrationPayload
    alignment: NarrationAlignmentRef
    word_id: str


class CaptionPhrasesParams(_Params):
    payload: NarrationPayload
    alignment: NarrationAlignmentRef
    track_id: str = "trk_caption"
    cue: Literal["sentence", "phrase"] = "sentence"
    max_characters: int = Field(default=24, ge=4, le=80)
    max_words: int = Field(default=8, ge=1, le=32)
    layout: LayoutBox | None = None
    style: TextStyle | None = None


class TextRevealParams(_Params):
    clip_id: str
    kind: Literal["line", "word", "grapheme"] = "word"
    part_ids: list[str] | None = None
    duration: int = Field(gt=0)
    stagger: int = Field(default=0, ge=0)
    offset: tuple[float, float] = (0.0, 24.0)
    blur: float = Field(default=6.0, ge=0, le=100)


class TextImpactParams(_Params):
    narration: NarrationWordInput
    clip_id: str | None = None
    scale: float = Field(default=1.35, gt=1, le=2)
    blur: float = Field(default=8.0, ge=0, le=32)
    landing_y: float = Field(default=-24.0, ge=-200, le=200)


class TypewriterParams(_Params):
    clip_id: str
    interval: int = Field(gt=0)
    cursor: bool = False
    cursor_track_id: str | None = None
    cursor_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")

    @model_validator(mode="after")
    def _cursor_track(self) -> TypewriterParams:
        if self.cursor and not self.cursor_track_id:
            raise ValueError("a typewriter cursor needs its native shape track")
        return self


class KeywordFillParams(_Params):
    clip_id: str | None = None
    kind: Literal["line", "word", "grapheme"] = "word"
    part_ids: list[str] | None = None
    at: int | None = Field(default=None, ge=0)
    narration: NarrationWordInput | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: float | None = Field(default=None, ge=0, le=64)
    weight: Literal[400, 500, 600, 700, 800, 900] | None = None

    @model_validator(mode="after")
    def _target_and_change(self) -> KeywordFillParams:
        if self.narration is None and (self.clip_id is None or not self.part_ids or self.at is None):
            raise ValueError("keyword-fill needs explicit clip/parts/time or one narration word")
        if not any(
            value is not None
            for value in (self.color, self.stroke_color, self.stroke_width, self.weight)
        ):
            raise ValueError("keyword-fill needs at least one paint change")
        return self


class WordCycleNarrationInput(_Params):
    payload: NarrationPayload
    alignment: NarrationAlignmentRef
    word_ids: list[str] = Field(min_length=2, max_length=5)


class WordCycleParams(_Params):
    clip_id: str
    words: list[str] = Field(min_length=2, max_length=5)
    period: int | None = Field(default=None, gt=0)
    transition: int | None = Field(default=None, gt=0)
    narration: WordCycleNarrationInput | None = None

    @model_validator(mode="after")
    def _stable_words(self) -> WordCycleParams:
        if any(not word.strip() or word != word.strip() or "\n" in word for word in self.words):
            raise ValueError("word-cycle words must be non-empty single-line slots")
        if self.narration is not None:
            if len(self.narration.word_ids) != len(self.words):
                raise ValueError("word-cycle narration ids must match the words")
            if self.period is not None:
                raise ValueError("word-cycle uses either a fixed period or narration anchors")
        return self


class ClaimLine(_Params):
    text: str = Field(min_length=1, max_length=120)
    keyword: str | None = Field(default=None, min_length=1, max_length=40)


class ClaimLayoutParams(_Params):
    lines: list[ClaimLine] = Field(min_length=2, max_length=5)
    mode: Literal["stacked", "split"] = "stacked"
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    stagger: int = Field(ge=0)
    hold: int = Field(gt=0)
    style: TextStyle | None = None
    accent: str = Field(default="#F59E0B", pattern=r"^#[0-9a-fA-F]{6}$")

    @model_validator(mode="after")
    def _split_pair(self) -> ClaimLayoutParams:
        if self.mode == "split" and len(self.lines) != 2:
            raise ValueError("split claim-layout needs exactly two lines")
        return self


class HighlightSweepParams(_Params):
    text: str = Field(min_length=1, max_length=160)
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    hold: int = Field(gt=0)
    color: str = Field(default="#FDE047", pattern=r"^#[0-9a-fA-F]{6}$")
    style: TextStyle | None = None


class PathUnderlineParams(_Params):
    clip_id: str
    reveal: int = Field(gt=0)
    hold: int = Field(gt=0)
    color: str = Field(default="#F59E0B", pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: float = Field(default=8.0, gt=0, le=64)
    offset_y: float = Field(default=8.0, ge=0, le=200)


class CalloutParams(_Params):
    label: str = Field(min_length=1, max_length=120)
    range: TimeRange
    label_layout: LayoutBox
    target: LayoutBox
    target_clip_id: str | None = None
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    hold: int = Field(gt=0)
    color: str = Field(default="#2563EB", pattern=r"^#[0-9a-fA-F]{6}$")
    style: TextStyle | None = None


class FlowStepsParams(_Params):
    steps: list[str] = Field(min_length=2, max_length=5)
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    stagger: int = Field(ge=0)
    hold: int = Field(gt=0)


class ComparisonColumn(_Params):
    title: str = Field(min_length=1, max_length=80)
    items: list[str] = Field(min_length=1, max_length=5)
    accent: str = Field(default="#60A5FA", pattern=r"^#[0-9a-fA-F]{6}$")


class ComparisonColumnsParams(_Params):
    columns: list[ComparisonColumn] = Field(min_length=2, max_length=2)
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    stagger: int = Field(ge=0)
    hold: int = Field(gt=0)


class StackCard(_Params):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    body: str | None = Field(default=None, min_length=1, max_length=240)
    source_clip_id: str | None = None

    @model_validator(mode="after")
    def _one_card_source(self) -> StackCard:
        if (self.title is None) == (self.source_clip_id is None):
            raise ValueError("a stack card needs either native title/body or one frozen media clip")
        if self.source_clip_id is not None and self.body is not None:
            raise ValueError("a media stack card does not take native body text")
        return self


class CardStackParams(_Params):
    cards: list[StackCard] = Field(min_length=2, max_length=6)
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=1)
    stagger: int = Field(ge=0)
    hold: int = Field(gt=0)
    overshoot: float = Field(default=1.04, gt=1, le=1.2)
    deal_offset: tuple[float, float] = (160.0, -80.0)
    fan_offset: float = Field(default=12.0, ge=0, le=64)


class ListItem(_Params):
    text: str = Field(min_length=1, max_length=200)
    checked: bool | None = None


class ListRevealParams(_Params):
    text_color: str = Field(default="#111827", pattern=r"^#[0-9A-Fa-f]{6}$")
    items: list[ListItem] = Field(min_length=2, max_length=8)
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    stagger: int = Field(ge=0)
    hold: int = Field(gt=0)


class NotificationEvent(_Params):
    title: str = Field(min_length=1, max_length=100)
    body: str | None = Field(default=None, min_length=1, max_length=200)


class NotificationStackParams(_Params):
    events: list[NotificationEvent] = Field(min_length=2, max_length=5)
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    stagger: int = Field(ge=0)
    collapse: int = Field(gt=0)
    hold: int = Field(gt=0)
    card_height: float = Field(default=120.0, gt=40, le=400)
    stack_offset: float = Field(default=32.0, gt=0, le=200)


class TitleLockupParams(_Params):
    title: str = Field(min_length=1, max_length=160)
    subtitle: str | None = Field(default=None, min_length=1, max_length=240)
    brand_clip_id: str | None = None
    range: TimeRange
    layout: LayoutBox
    scene_id: str | None = None
    reveal: int = Field(gt=0)
    stagger: int = Field(ge=0)
    hold: int = Field(gt=0)
    style: TextStyle | None = None


@dataclass(frozen=True)
class _CaptionSpan:
    text_start: int
    text_end: int
    start_tick: int
    end_tick: int


def _find_track(content: CompositionContent, track_id: str) -> Track:
    track = next((item for item in content.timeline.tracks if item.track_id == track_id), None)
    if track is None:
        raise PresetError(f"track {track_id!r} does not exist")
    return track


def _find_clip(content: CompositionContent, clip_id: str) -> tuple[Track, Clip]:
    for track in content.timeline.tracks:
        clip = next((item for item in track.clips if item.clip_id == clip_id), None)
        if clip is not None:
            return track, clip
    raise PresetError(f"clip {clip_id!r} does not exist")


def _text_clip(content: CompositionContent, clip_id: str) -> tuple[Track, Clip, TextObject]:
    track, clip = _find_clip(content, clip_id)
    if not isinstance(clip.object, TextObject):
        raise PresetError(f"clip {clip_id!r} is not native text")
    return track, clip, clip.object


def _ease() -> Easing:
    return Easing(kind="cubic_bezier", params=(0.16, 1.0, 0.3, 1.0))


def _hold() -> Easing:
    return Easing(kind="hold")


def _animation(
    animation_id: str,
    object_id: str,
    property_name: str,
    keyframes: list[Keyframe],
    *,
    target: TextPartTarget | None = None,
    anchor: NarrationAnchor | None = None,
) -> Animation:
    return Animation(
        animation_id=animation_id,
        target_object_id=object_id,
        text_part=target,
        property=property_name,
        keyframes=keyframes,
        narration_anchor=anchor,
    )


def _speech_for_sentence(
    content: CompositionContent,
    sentence: NarrationSentence,
    alignment: NarrationAlignmentRef,
) -> Clip:
    matches: list[Clip] = []
    for track in content.timeline.tracks:
        for clip in track.clips:
            obj = clip.object
            if not isinstance(obj, SpeechObject) or obj.alignment is None:
                continue
            if (
                obj.alignment.alignment_id == alignment.alignment_id
                and obj.alignment.content_digest == alignment.content_digest
                and obj.text == sentence.text
                and clip.source is not None
                and clip.source.source_range is not None
                and clip.source.source_range.start == sentence.start_tick
                and clip.source.source_range.end == sentence.end_tick
            ):
                matches.append(clip)
    if len(matches) != 1:
        raise PresetError(f"sentence {sentence.sentence_id!r} has no unique aligned SpeechClip")
    return matches[0]


def _caption_source_window(
    content: CompositionContent,
    caption_clip: Clip,
    speech_clip: Clip,
) -> tuple[int, int]:
    if speech_clip.source is None or speech_clip.source.source_range is None:
        raise PresetError("aligned caption speech lacks its source window")
    timebase = content.settings.timebase
    source = speech_clip.source.source_range
    start = source.start + output_ticks_to_source_ticks(
        caption_clip.range.start - speech_clip.range.start, timebase
    )
    end = source.start + output_ticks_to_source_ticks(
        caption_clip.range.end - speech_clip.range.start, timebase
    )
    if start < source.start or end > source.end or end <= start:
        raise PresetError("caption cue escapes its aligned speech source window")
    return start, end


def _caption_for_word(
    content: CompositionContent,
    narration: NarrationWordInput,
    clip_id: str | None = None,
) -> tuple[Clip, NarrationSentence, int]:
    sentence, word = find_word(narration.payload, narration.word_id)
    candidates: list[tuple[Clip, int]] = []
    for track in content.timeline.tracks:
        for clip in track.clips:
            if clip_id is not None and clip.clip_id != clip_id:
                continue
            obj = clip.object
            if not isinstance(obj, TextObject) or obj.caption is None:
                continue
            caption = obj.caption
            if (
                caption.state != "derived"
                or caption.narration_alignment_id != narration.alignment.alignment_id
                or caption.narration_content_digest != narration.alignment.content_digest
                or (caption.sentence_id is not None and caption.sentence_id != sentence.sentence_id)
            ):
                continue
            text_start = sentence.text_start if caption.text_start is None else caption.text_start
            text_end = text_start + len(obj.text)
            if (
                text_start >= sentence.text_start
                and text_end <= sentence.text_end
                and word.text_start >= text_start
                and word.text_end <= text_end
                and obj.text == sentence.text[
                    text_start - sentence.text_start:text_end - sentence.text_start
                ]
            ):
                candidates.append((clip, text_start))
    if len(candidates) != 1:
        raise PresetError(f"word {narration.word_id!r} has no unique native caption target")
    clip, text_start = candidates[0]
    return clip, sentence, text_start


def _resolved_caption_word(
    content: CompositionContent,
    clip: Clip,
    sentence: NarrationSentence,
    caption_text_start: int,
    narration: NarrationWordInput,
):
    obj = clip.object
    assert isinstance(obj, TextObject) and obj.caption is not None
    speech = _speech_for_sentence(content, sentence, narration.alignment)
    source_start, source_end = _caption_source_window(content, clip, speech)
    caption_text_end = caption_text_start + len(obj.text)
    emphasis = list(sentence.semantics.emphasis_word_ids) if sentence.semantics else []
    related = [
        word_id for word_id in emphasis
        if (
            (word := find_word(narration.payload, word_id)[1]).text_start >= caption_text_start
            and word.text_end <= caption_text_end
        )
    ]
    if narration.word_id not in related:
        related.append(narration.word_id)
    kind = narration_anchor_part_kind(
        narration.payload,
        caption_text=obj.text,
        word_ids=related,
        caption_text_start=caption_text_start,
    )
    return resolve_narration_word(
        narration.payload,
        caption_text=obj.text,
        word_id=narration.word_id,
        output_timebase=content.settings.timebase,
        part_kind=kind,
        caption_text_start=caption_text_start,
        clip_start_tick=source_start,
        clip_end_tick=source_end,
    )


def _word_anchor(clip: Clip, narration: NarrationWordInput) -> NarrationAnchor:
    obj = clip.object
    assert isinstance(obj, TextObject) and isinstance(obj.caption, CaptionDerivation)
    return NarrationAnchor(
        alignment_id=narration.alignment.alignment_id,
        content_digest=narration.alignment.content_digest,
        speech_object_id=obj.caption.speech_object_id,
        word_id=narration.word_id,
    )


def _phrase_spans(sentence: NarrationSentence, params: CaptionPhrasesParams) -> list[_CaptionSpan]:
    if params.cue == "sentence":
        return [_CaptionSpan(
            sentence.text_start, sentence.text_end, sentence.start_tick, sentence.end_tick
        )]
    spans: list[_CaptionSpan] = []
    group: list[int] = []
    words = sentence.words

    def flush(next_index: int) -> None:
        nonlocal group
        if not group:
            return
        first = words[group[0]]
        text_end = words[next_index].text_start if next_index < len(words) else sentence.text_end
        while text_end > first.text_start and sentence.text[
            text_end - 1 - sentence.text_start
        ].isspace():
            text_end -= 1
        end_tick = words[next_index].start_tick if next_index < len(words) else sentence.end_tick
        spans.append(_CaptionSpan(first.text_start, text_end, first.start_tick, end_tick))
        group = []

    for index, word in enumerate(words):
        group.append(index)
        first = words[group[0]]
        next_word = words[index + 1] if index + 1 < len(words) else None
        trailing_end = next_word.text_start if next_word is not None else sentence.text_end
        trailing = sentence.text[
            word.text_end - sentence.text_start:trailing_end - sentence.text_start
        ]
        if (
            any(mark in trailing for mark in "，,、；;：:。！？!?")
            or word.text_end - first.text_start >= params.max_characters
            or len(group) >= params.max_words
        ):
            flush(index + 1)
    flush(len(words))
    return spans


def _expand_caption_phrases(
    content: CompositionContent, params: CaptionPhrasesParams
) -> list[Op]:
    track = _find_track(content, params.track_id)
    if track.kind != "visual" or track.role != "caption":
        raise PresetError("caption-phrases needs a visual caption track")
    width, height = content.settings.width, content.settings.height
    layout = params.layout or LayoutBox(x=160.0, y=float(height - 170), width=float(width - 320), height=120.0)
    from app.editing.text_presets import default_caption_text_style

    style = params.style or default_caption_text_style(
        content.settings,
        font_size=max(24, round(width * 34 / 1920)),
        align="center",
        line_height=1.3,
    )
    ops: list[Op] = []
    for sentence in params.payload.sentences:
        speech = _speech_for_sentence(content, sentence, params.alignment)
        speech_obj = speech.object
        assert isinstance(speech_obj, SpeechObject)
        if any(
            isinstance(clip.object, TextObject)
            and isinstance(clip.object.caption, CaptionDerivation)
            and clip.object.caption.speech_object_id == speech_obj.object_id
            for clip in track.clips
        ):
            raise PresetError(f"sentence {sentence.sentence_id!r} already has linked captions")
        for ordinal, span in enumerate(_phrase_spans(sentence, params), start=1):
            start = source_ticks_to_output_ticks(span.start_tick, content.settings.timebase)
            end = source_ticks_to_output_ticks(span.end_tick, content.settings.timebase)
            if end <= start:
                raise PresetError(f"sentence {sentence.sentence_id!r} has an empty caption cue")
            suffix = "" if params.cue == "sentence" else f"_p{ordinal}"
            object_id = f"obj_aligned_{sentence.sentence_id}_caption{suffix}"
            text = sentence.text[
                span.text_start - sentence.text_start:span.text_end - sentence.text_start
            ]
            clip = Clip(
                clip_id=f"clp_aligned_{sentence.sentence_id}_caption{suffix}",
                range=TimeRange(start=start, end=end),
                scene_id=speech.scene_id,
                source=None,
                object=TextObject(
                    kind="text",
                    object_id=object_id,
                    text=text,
                    layout=layout.model_copy(deep=True),
                    style=style.model_copy(deep=True),
                    caption=CaptionDerivation(
                        speech_object_id=speech_obj.object_id,
                        source_text_digest=speech_text_digest(speech_obj.text),
                        alignment=NARRATION_ALGORITHM,
                        state="derived",
                        narration_alignment_id=params.alignment.alignment_id,
                        narration_content_digest=params.alignment.content_digest,
                        sentence_id=sentence.sentence_id,
                        text_start=span.text_start if params.cue == "phrase" else None,
                        text_end=span.text_end if params.cue == "phrase" else None,
                    ),
                ),
            )
            ops.append(AddClip(op="add_clip", track_id=track.track_id, clip=clip))
    return ops


def _expand_text_reveal(content: CompositionContent, params: TextRevealParams) -> list[Op]:
    _, clip, obj = _text_clip(content, params.clip_id)
    part_ids = params.part_ids or [part.part_id for part in derive_text_parts(obj.text, params.kind)]
    if not part_ids:
        raise PresetError("text-reveal needs at least one TextPart")
    target = TextPartTarget(kind=params.kind, part_ids=part_ids, stagger=params.stagger)
    end = params.duration + (len(part_ids) - 1) * params.stagger
    if end > clip.range.duration:
        raise PresetError("text-reveal stagger exceeds its clip window")
    prefix = f"anm_reveal_{clip.clip_id}"
    animations = [
        _animation(f"{prefix}_opacity", obj.object_id, "opacity", [
            Keyframe(at=0, value=0.0, easing=_ease()),
            Keyframe(at=params.duration, value=1.0),
        ], target=target),
        _animation(f"{prefix}_position", obj.object_id, "transform.position", [
            Keyframe(at=0, value=params.offset, easing=_ease()),
            Keyframe(at=params.duration, value=(0.0, 0.0)),
        ], target=target),
    ]
    if params.blur > 0:
        animations.append(_animation(f"{prefix}_blur", obj.object_id, "filter.blur", [
            Keyframe(at=0, value=params.blur, easing=_ease()),
            Keyframe(at=params.duration, value=0.0),
        ], target=target))
    return [UpdateClip(
        op="update_clip", clip_id=clip.clip_id, animations=[*clip.animations, *animations]
    )]


def _expand_text_impact(content: CompositionContent, params: TextImpactParams) -> list[Op]:
    clip, sentence, text_start = _caption_for_word(content, params.narration, params.clip_id)
    obj = clip.object
    assert isinstance(obj, TextObject)
    placement = _resolved_caption_word(content, clip, sentence, text_start, params.narration)
    settings = content.settings
    impact_end = placement.start + min(
        placement.end - placement.start,
        frames_to_ticks(4, settings.timebase, settings.fps.num, settings.fps.den),
    )
    if ticks_to_frames(placement.start, settings.timebase, settings.fps.num, settings.fps.den) == ticks_to_frames(
        impact_end, settings.timebase, settings.fps.num, settings.fps.den
    ):
        raise PresetError("text-impact needs at least one distinct output frame")
    target = TextPartTarget(kind=placement.part_kind, part_ids=placement.part_ids, stagger=0)
    anchor = _word_anchor(clip, params.narration)
    prefix = f"anm_impact_{params.narration.word_id}"
    pairs = (
        ("opacity", 0.0, 1.0),
        ("transform.scale", params.scale, 1.0),
        ("filter.blur", params.blur, 0.0),
        ("transform.position", (0.0, params.landing_y), (0.0, 0.0)),
    )
    animations = [
        _animation(
            f"{prefix}_{property_name.replace('.', '_')}",
            obj.object_id,
            property_name,
            [
                Keyframe(at=placement.start, value=before, easing=_ease()),
                Keyframe(at=impact_end, value=after),
            ],
            target=target,
            anchor=anchor,
        )
        for property_name, before, after in pairs
    ]
    return [UpdateClip(
        op="update_clip", clip_id=clip.clip_id, animations=[*clip.animations, *animations]
    )]


def _expand_typewriter(content: CompositionContent, params: TypewriterParams) -> list[Op]:
    _, clip, obj = _text_clip(content, params.clip_id)
    parts = derive_text_parts(obj.text, "grapheme")
    if not parts:
        raise PresetError("typewriter needs at least one grapheme")
    settings = content.settings
    frame = frames_to_ticks(1, settings.timebase, settings.fps.num, settings.fps.den)
    if (len(parts) - 1) * params.interval + frame > clip.range.duration:
        raise PresetError("typewriter graphemes exceed their clip window")
    target = TextPartTarget(
        kind="grapheme", part_ids=[part.part_id for part in parts], stagger=params.interval
    )
    reveal = _animation(
        f"anm_typewriter_{clip.clip_id}_opacity",
        obj.object_id,
        "opacity",
        [
            Keyframe(at=0, value=0.0, easing=_hold()),
            Keyframe(at=frame, value=1.0),
        ],
        target=target,
    )
    ops: list[Op] = [UpdateClip(
        op="update_clip", clip_id=clip.clip_id, animations=[*clip.animations, reveal]
    )]
    if params.cursor:
        track = _find_track(content, params.cursor_track_id or "")
        if track.kind != "visual":
            raise PresetError("a typewriter cursor needs a visual track")
        token = uuid5(NAMESPACE_URL, f"typewriter-cursor:{clip.clip_id}").hex[:12]
        cursor = Clip(
            clip_id=f"clp_cursor_{token}",
            range=clip.range.model_copy(deep=True),
            scene_id=clip.scene_id,
            source=None,
            object=ShapeObject(
                kind="shape",
                object_id=f"obj_cursor_{token}",
                shape="rect",
                layout=LayoutBox(
                    x=min(settings.width - 4.0, obj.layout.x + obj.layout.width + 12.0),
                    y=obj.layout.y,
                    width=4.0,
                    height=obj.layout.height,
                ),
                fill=params.cursor_color,
                stroke=None,
                stroke_width=0.0,
                corner_radius=0.0,
                path=None,
            ),
        )
        ops.append(AddClip(op="add_clip", track_id=track.track_id, clip=cursor))
    return ops


def _expand_keyword_fill(content: CompositionContent, params: KeywordFillParams) -> list[Op]:
    anchor: NarrationAnchor | None = None
    if params.narration is not None:
        clip, sentence, text_start = _caption_for_word(content, params.narration, params.clip_id)
        obj = clip.object
        assert isinstance(obj, TextObject)
        placement = _resolved_caption_word(content, clip, sentence, text_start, params.narration)
        kind, part_ids, at = placement.part_kind, placement.part_ids, placement.start
        anchor = _word_anchor(clip, params.narration)
    else:
        _, clip, obj = _text_clip(content, params.clip_id or "")
        kind, part_ids, at = params.kind, params.part_ids or [], params.at or 0
    if at >= clip.range.duration:
        raise PresetError("keyword-fill switch must occur inside its clip")
    target = TextPartTarget(kind=kind, part_ids=part_ids, stagger=0)
    base = obj.style
    changes: list[tuple[str, float | str, float | str]] = []
    if params.color is not None:
        changes.append(("text.color", base.color, params.color))
    if params.stroke_color is not None:
        changes.append((
            "text.stroke_color", base.stroke.color if base.stroke else "#000000", params.stroke_color
        ))
    if params.stroke_width is not None:
        changes.append((
            "text.stroke_width", base.stroke.width if base.stroke else 0.0, params.stroke_width
        ))
    if params.weight is not None:
        changes.append(("text.weight", float(base.weight), float(params.weight)))
    animations: list[Animation] = []
    for property_name, before, after in changes:
        keyframes = (
            [Keyframe(at=0, value=after, easing=_hold())]
            if at == 0 else [
                Keyframe(at=0, value=before, easing=_hold()),
                Keyframe(at=at, value=after),
            ]
        )
        animations.append(_animation(
            f"anm_fill_{clip.clip_id}_{at}_{property_name.replace('.', '_')}",
            obj.object_id,
            property_name,
            keyframes,
            target=target,
            anchor=anchor,
        ))
    return [UpdateClip(
        op="update_clip", clip_id=clip.clip_id, animations=[*clip.animations, *animations]
    )]


def _cycle_starts(content: CompositionContent, clip: Clip, params: WordCycleParams) -> list[int]:
    if params.narration is None:
        period = params.period or frames_to_ticks(
            30, content.settings.timebase, content.settings.fps.num, content.settings.fps.den
        )
        return [index * period for index in range(len(params.words))]
    starts: list[int] = []
    for text, word_id in zip(params.words, params.narration.word_ids, strict=True):
        sentence, word = find_word(params.narration.payload, word_id)
        if text != word.text:
            raise PresetError(f"word-cycle slot {text!r} does not match narration word {word_id!r}")
        speech = _speech_for_sentence(content, sentence, params.narration.alignment)
        assert speech.source is not None and speech.source.source_range is not None
        absolute = speech.range.start + (
            source_ticks_to_output_ticks(word.start_tick, content.settings.timebase)
            - source_ticks_to_output_ticks(
                speech.source.source_range.start, content.settings.timebase
            )
        )
        starts.append(absolute - clip.range.start)
    return starts


def _indexed_cycle_animations(
    content: CompositionContent,
    clip: Clip,
    starts: list[int],
    index: int,
    transition: int,
) -> list[Animation]:
    settings = content.settings
    duration = clip.range.duration
    start = starts[index]
    end = starts[index + 1] if index + 1 < len(starts) else duration
    active = end - start
    if active <= 0 or start < 0 or end > duration:
        raise PresetError("word-cycle anchors must be monotonic and inside the clip")
    blend = min(transition, active // 3)
    if blend <= 0:
        raise PresetError("word-cycle slots need at least three output ticks")
    checkpoints = sorted({0, start, start + blend, end - blend, end})
    frames = [ticks_to_frames(at, settings.timebase, settings.fps.num, settings.fps.den) for at in checkpoints]
    if len(set(frames)) != len(frames):
        raise PresetError("word-cycle transition keyframes collapse onto one output frame")

    opacity_points: dict[int, float] = {0: 1.0 if start == 0 else 0.0}
    if start > 0:
        opacity_points[start] = 1.0
    if end < duration:
        opacity_points[end] = 0.0
    opacity = _animation(
        f"anm_cycle_{clip.clip_id}_opacity",
        clip.object.object_id,
        "opacity",
        [Keyframe(at=at, value=value, easing=_hold()) for at, value in sorted(opacity_points.items())],
    )

    blur_points: dict[int, float] = {0: 12.0, start + blend: 0.0}
    position_points: dict[int, tuple[float, float]] = {
        0: (0.0, 24.0), start + blend: (0.0, 0.0)
    }
    if start > 0:
        blur_points[start] = 12.0
        position_points[start] = (0.0, 24.0)
    if end < duration:
        blur_points[end - blend] = 0.0
        blur_points[end] = 12.0
        position_points[end - blend] = (0.0, 0.0)
        position_points[end] = (0.0, -24.0)
    blur = _animation(
        f"anm_cycle_{clip.clip_id}_blur",
        clip.object.object_id,
        "filter.blur",
        [Keyframe(at=at, value=value, easing=_ease()) for at, value in sorted(blur_points.items())],
    )
    position = _animation(
        f"anm_cycle_{clip.clip_id}_position",
        clip.object.object_id,
        "transform.position",
        [Keyframe(at=at, value=value, easing=_ease()) for at, value in sorted(position_points.items())],
    )
    return [opacity, blur, position]


def _expand_word_cycle(content: CompositionContent, params: WordCycleParams) -> list[Op]:
    track, clip, obj = _text_clip(content, params.clip_id)
    if obj.caption is not None:
        raise PresetError("word-cycle uses an independent native text slot, not a derived caption")
    starts = _cycle_starts(content, clip, params)
    transition = params.transition or frames_to_ticks(
        3, content.settings.timebase, content.settings.fps.num, content.settings.fps.den
    )
    max_order = max(
        (item.order for item in content.timeline.tracks if item.kind == "visual"), default=track.order
    )
    ops: list[Op] = []
    for index, text in enumerate(params.words):
        current = clip.model_copy(deep=True)
        current.object.text = text
        current.animations = []
        if index == 0:
            current.animations = _indexed_cycle_animations(content, current, starts, index, transition)
            ops.append(UpdateClip(
                op="update_clip", clip_id=clip.clip_id,
                object=current.object, animations=current.animations,
            ))
            continue
        token = uuid5(NAMESPACE_URL, f"word-cycle:{clip.clip_id}:{index}").hex[:12]
        current.clip_id = f"clp_cycle_{token}"
        current.object.object_id = f"obj_cycle_{token}"
        current.animations = _indexed_cycle_animations(content, current, starts, index, transition)
        new_track = Track(
            track_id=f"trk_cycle_{token}",
            kind="visual",
            role=track.role,
            order=max_order + index,
            clips=[],
        )
        ops.append(AddTrack(op="add_track", track=new_track))
        ops.append(AddClip(op="add_clip", track_id=new_track.track_id, clip=current))
    return ops


def _layout_inside(content: CompositionContent, layout: LayoutBox, label: str) -> None:
    if (
        layout.x < 0
        or layout.y < 0
        or layout.x + layout.width > content.settings.width
        or layout.y + layout.height > content.settings.height
    ):
        raise PresetError(f"{label} escapes the composition canvas")


def _require_final_hold(range_: TimeRange, finished: int, hold: int) -> None:
    if finished + hold > range_.duration:
        raise PresetError("preset entrance and final hold exceed their clip window")


def _native_style(
    font_size: int,
    *,
    color: str = "#FFFFFF",
    weight: Literal[400, 500, 600, 700, 800, 900] = 700,
    align: Literal["left", "center", "right"] = "center",
) -> TextStyle:
    return TextStyle(
        font_size=font_size,
        color=color,
        background=None,
        weight=weight,
        align=align,
        line_height=1.2,
    )


def _native_text(text: str, layout: LayoutBox, style: TextStyle) -> TextObject:
    return TextObject(
        kind="text", object_id="obj_pending", text=text,
        layout=layout.model_copy(deep=True), style=style.model_copy(deep=True),
    )


def _native_shape(
    layout: LayoutBox,
    *,
    shape: Literal["rect", "ellipse", "path"] = "rect",
    fill: str | None = "#FFFFFF",
    stroke: str | None = None,
    stroke_width: float = 0.0,
    corner_radius: float = 0.0,
    path: str | None = None,
) -> ShapeObject:
    return ShapeObject(
        kind="shape", object_id="obj_pending", shape=shape,
        layout=layout.model_copy(deep=True), fill=fill, stroke=stroke,
        stroke_width=stroke_width, corner_radius=corner_radius, path=path,
    )


class _NativeGroup:
    """Deterministic ordinary tracks for one birth-time preset expansion."""

    def __init__(
        self,
        content: CompositionContent,
        name: str,
        range_: TimeRange,
        scene_id: str | None,
    ) -> None:
        self.range = range_
        self.scene_id = scene_id
        self.token = uuid5(
            NAMESPACE_URL,
            f"native-group:{name}:{range_.start}:{range_.end}:{scene_id}:{len(content.timeline.tracks)}",
        ).hex[:12]
        self.order = max(
            (track.order for track in content.timeline.tracks if track.kind == "visual"),
            default=-1,
        ) + 1
        self.count = 0
        self.ops: list[Op] = []

    def add(
        self,
        obj: TextObject | ShapeObject | ImageObject | WebObject | VideoObject,
        *,
        animations: list[Animation] | None = None,
        source: Any = None,
        scene_id: str | None = None,
        role: Literal["main", "title", "caption", "dialogue", "music", "effect"] = "effect",
    ) -> Clip:
        suffix = f"{self.token}_{self.count:02d}"
        current = obj.model_copy(deep=True)
        current.object_id = f"obj_{suffix}"
        current_animations = [item.model_copy(deep=True) for item in animations or []]
        for index, animation in enumerate(current_animations):
            animation.animation_id = f"anm_{suffix}_{index:02d}"
            animation.target_object_id = current.object_id
        clip = Clip(
            clip_id=f"clp_{suffix}",
            range=self.range.model_copy(deep=True),
            scene_id=self.scene_id if scene_id is None else scene_id,
            source=source.model_copy(deep=True) if source is not None else None,
            object=current,
            animations=current_animations,
        )
        track = Track(
            track_id=f"trk_{suffix}", kind="visual", role=role,
            order=self.order, clips=[clip],
        )
        self.order += 1
        self.count += 1
        self.ops.append(AddTrack(op="add_track", track=track))
        return clip


def _entrance(
    obj: TextObject | ShapeObject | ImageObject | WebObject | VideoObject,
    *,
    at: int,
    duration: int,
    offset: tuple[float, float] = (0.0, 24.0),
    blur: float = 0.0,
    scale: float | None = None,
) -> list[Animation]:
    end = at + duration
    animations = [_animation(
        "anm_pending_opacity", obj.object_id, "opacity",
        [Keyframe(at=at, value=0.0, easing=_ease()), Keyframe(at=end, value=1.0)],
    )]
    if offset != (0.0, 0.0):
        animations.append(_animation(
            "anm_pending_position", obj.object_id, "transform.position",
            [Keyframe(at=at, value=offset, easing=_ease()), Keyframe(at=end, value=(0.0, 0.0))],
        ))
    if blur > 0:
        animations.append(_animation(
            "anm_pending_blur", obj.object_id, "filter.blur",
            [Keyframe(at=at, value=blur, easing=_ease()), Keyframe(at=end, value=0.0)],
        ))
    if scale is not None:
        animations.append(_animation(
            "anm_pending_scale", obj.object_id, "transform.scale",
            [Keyframe(at=at, value=scale, easing=_ease()), Keyframe(at=end, value=1.0)],
        ))
    return animations


def _keyword_paint(obj: TextObject, keyword: str | None, accent: str) -> list[Animation]:
    if keyword is None:
        return []
    if not keyword.strip() or obj.text.count(keyword) != 1:
        raise PresetError("claim-layout keywords must be non-empty and occur exactly once")
    start = obj.text.index(keyword)
    end = start + len(keyword)
    part_ids = [
        part.part_id for part in derive_text_parts(obj.text, "grapheme")
        if part.text_range.start >= start and part.text_range.end <= end
    ]
    if not part_ids:
        raise PresetError("claim-layout keyword has no native grapheme target")
    target = TextPartTarget(kind="grapheme", part_ids=part_ids, stagger=0)
    return [
        _animation(
            "anm_pending_keyword_color", obj.object_id, "text.color",
            [Keyframe(at=0, value=accent, easing=_hold())], target=target,
        ),
        _animation(
            "anm_pending_keyword_weight", obj.object_id, "text.weight",
            [Keyframe(at=0, value=900.0, easing=_hold())], target=target,
        ),
    ]


def _expand_claim_layout(content: CompositionContent, params: ClaimLayoutParams) -> list[Op]:
    _layout_inside(content, params.layout, "claim-layout")
    _require_final_hold(
        params.range, params.reveal + (len(params.lines) - 1) * params.stagger, params.hold
    )
    group = _NativeGroup(content, "claim-layout", params.range, params.scene_id)
    base = params.style or _native_style(76, color="#111827", weight=900)
    count = len(params.lines)
    gap = 48.0
    for index, line in enumerate(params.lines):
        if params.mode == "stacked":
            height = params.layout.height / count
            layout = LayoutBox(
                x=params.layout.x, y=params.layout.y + index * height,
                width=params.layout.width, height=height,
            )
            offset = (0.0, 32.0)
        else:
            width = (params.layout.width - gap) / 2
            layout = LayoutBox(
                x=params.layout.x + index * (width + gap), y=params.layout.y,
                width=width, height=params.layout.height,
            )
            offset = (-40.0 if index == 0 else 40.0, 0.0)
        obj = _native_text(line.text, layout, base)
        group.add(obj, animations=[
            *_entrance(obj, at=index * params.stagger, duration=params.reveal, offset=offset, blur=6.0),
            *_keyword_paint(obj, line.keyword, params.accent),
        ], role="title")
    return group.ops


def _expand_highlight_sweep(content: CompositionContent, params: HighlightSweepParams) -> list[Op]:
    _layout_inside(content, params.layout, "highlight-sweep")
    _require_final_hold(params.range, params.reveal, params.hold)
    group = _NativeGroup(content, "highlight-sweep", params.range, params.scene_id)
    width, height = params.layout.width, params.layout.height
    sweep = _native_shape(
        params.layout, shape="path", fill=None, stroke=params.color, stroke_width=height,
        path=f"M 0 {height / 2} L {width} {height / 2}",
    )
    group.add(sweep, animations=[_animation(
        "anm_pending_reveal", sweep.object_id, "path.reveal",
        [Keyframe(at=0, value=0.0, easing=_ease()), Keyframe(at=params.reveal, value=1.0)],
    )])
    style = params.style or _native_style(54, color="#111827", weight=800)
    text = _native_text(params.text, params.layout, style)
    group.add(text, role="title")
    return group.ops


def _expand_path_underline(content: CompositionContent, params: PathUnderlineParams) -> list[Op]:
    track, clip, obj = _text_clip(content, params.clip_id)
    _require_final_hold(clip.range, params.reveal, params.hold)
    height = max(16.0, params.stroke_width * 3)
    layout = LayoutBox(
        x=obj.layout.x, y=obj.layout.y + obj.layout.height + params.offset_y,
        width=obj.layout.width, height=height,
    )
    _layout_inside(content, layout, "path-underline")
    width = layout.width
    path = (
        f"M 0 {height * 0.6} Q {width * 0.25} 0 {width * 0.5} {height * 0.55} "
        f"Q {width * 0.75} {height} {width} {height * 0.4}"
    )
    underline = _native_shape(
        layout, shape="path", fill=None, stroke=params.color,
        stroke_width=params.stroke_width, path=path,
    )
    group = _NativeGroup(content, "path-underline", clip.range, clip.scene_id)
    group.order = max(group.order, track.order + 1)
    group.add(underline, animations=[_animation(
        "anm_pending_reveal", underline.object_id, "path.reveal",
        [Keyframe(at=0, value=0.0, easing=_ease()), Keyframe(at=params.reveal, value=1.0)],
    )])
    return group.ops


def _expand_callout(content: CompositionContent, params: CalloutParams) -> list[Op]:
    _layout_inside(content, params.label_layout, "callout label")
    _layout_inside(content, params.target, "callout target")
    _require_final_hold(params.range, params.reveal, params.hold)
    scene_id = params.scene_id
    if params.target_clip_id is not None:
        _, target_clip = _find_clip(content, params.target_clip_id)
        target_obj = target_clip.object
        if not isinstance(target_obj, (ImageObject, WebObject, VideoObject)) or target_clip.source is None:
            raise PresetError("callout targets need a sourced frozen image/web/video clip")
        box = target_obj.layout
        if (
            params.target.x < box.x
            or params.target.y < box.y
            or params.target.x + params.target.width > box.x + box.width
            or params.target.y + params.target.height > box.y + box.height
            or params.range.start < target_clip.range.start
            or params.range.end > target_clip.range.end
        ):
            raise PresetError("callout target must stay inside its frozen media layout and visible window")
        scene_id = scene_id if scene_id is not None else target_clip.scene_id
    group = _NativeGroup(content, "callout", params.range, scene_id)
    x1 = params.label_layout.x + params.label_layout.width / 2
    y1 = params.label_layout.y + params.label_layout.height / 2
    x2 = params.target.x + params.target.width / 2
    y2 = params.target.y + params.target.height / 2
    pad = 8.0
    line_layout = LayoutBox(
        x=max(0.0, min(x1, x2) - pad), y=max(0.0, min(y1, y2) - pad),
        width=max(1.0, abs(x2 - x1) + 2 * pad), height=max(1.0, abs(y2 - y1) + 2 * pad),
    )
    _layout_inside(content, line_layout, "callout leader")
    line = _native_shape(
        line_layout, shape="path", fill=None, stroke=params.color, stroke_width=3.0,
        path=f"M {x1 - line_layout.x} {y1 - line_layout.y} L {x2 - line_layout.x} {y2 - line_layout.y}",
    )
    group.add(line, animations=[
        *_entrance(line, at=0, duration=params.reveal, offset=(0.0, 0.0)),
        _animation(
            "anm_pending_reveal", line.object_id, "path.reveal",
            [Keyframe(at=0, value=0.0, easing=_ease()), Keyframe(at=params.reveal, value=1.0)],
        ),
    ])
    capsule = _native_shape(
        params.label_layout, fill=params.color, corner_radius=min(32.0, params.label_layout.height / 2)
    )
    group.add(capsule, animations=_entrance(capsule, at=0, duration=params.reveal, offset=(0.0, 0.0)))
    style = params.style or _native_style(34, color="#FFFFFF", weight=700)
    label = _native_text(params.label, params.label_layout, style)
    group.add(label, animations=_entrance(label, at=0, duration=params.reveal, offset=(0.0, 0.0)))
    return group.ops


def _expand_flow_steps(content: CompositionContent, params: FlowStepsParams) -> list[Op]:
    _layout_inside(content, params.layout, "flow-steps")
    if any(not step.strip() for step in params.steps):
        raise PresetError("flow-steps needs real non-empty step labels")
    _require_final_hold(
        params.range, params.reveal + (len(params.steps) - 1) * params.stagger, params.hold
    )
    group = _NativeGroup(content, "flow-steps", params.range, params.scene_id)
    count = len(params.steps)
    gap = 72.0
    width = (params.layout.width - gap * (count - 1)) / count
    if width <= 80:
        raise PresetError("flow-steps nodes are too narrow for native labels")
    centers: list[tuple[float, float]] = []
    for index, text in enumerate(params.steps):
        x = params.layout.x + index * (width + gap)
        layout = LayoutBox(x=x, y=params.layout.y, width=width, height=params.layout.height)
        centers.append((x + width / 2, params.layout.y + params.layout.height / 2))
        if index > 0:
            previous = centers[index - 1]
            current = centers[index]
            line_layout = LayoutBox(
                x=previous[0], y=previous[1] - 2.0,
                width=current[0] - previous[0], height=4.0,
            )
            line = _native_shape(
                line_layout, shape="path", fill=None, stroke="#6B7280", stroke_width=4.0,
                path=f"M 0 2 L {line_layout.width} 2",
            )
            at = index * params.stagger
            group.add(line, animations=[_animation(
                "anm_pending_reveal", line.object_id, "path.reveal",
                [Keyframe(at=at, value=0.0, easing=_ease()), Keyframe(at=at + params.reveal, value=1.0)],
            )])
        node = _native_shape(layout, fill="#111827", corner_radius=20.0)
        animations = _entrance(node, at=index * params.stagger, duration=params.reveal)
        group.add(node, animations=animations)
        label = _native_text(text, layout, _native_style(34, weight=700))
        group.add(label, animations=_entrance(
            label, at=index * params.stagger, duration=params.reveal, blur=4.0
        ))
    return group.ops


def _expand_comparison_columns(
    content: CompositionContent, params: ComparisonColumnsParams
) -> list[Op]:
    _layout_inside(content, params.layout, "comparison-columns")
    if any(
        not value.strip()
        for column in params.columns
        for value in [column.title, *column.items]
    ):
        raise PresetError("comparison-columns needs real non-empty labels and items")
    deepest = max(len(column.items) for column in params.columns)
    _require_final_hold(params.range, params.reveal + deepest * params.stagger, params.hold)
    group = _NativeGroup(content, "comparison-columns", params.range, params.scene_id)
    gap = 48.0
    panel_width = (params.layout.width - gap) / 2
    row_height = (params.layout.height - 136.0) / deepest
    if row_height < 32:
        raise PresetError("comparison-columns rows are too short for native text")
    for column_index, column in enumerate(params.columns):
        x = params.layout.x + column_index * (panel_width + gap)
        panel_layout = LayoutBox(
            x=x, y=params.layout.y, width=panel_width, height=params.layout.height
        )
        panel = _native_shape(panel_layout, fill="#111827", corner_radius=24.0)
        group.add(panel, animations=_entrance(
            panel, at=0, duration=params.reveal, offset=(0.0, 0.0)
        ))
        title_layout = LayoutBox(
            x=x + 32.0, y=params.layout.y + 28.0,
            width=panel_width - 64.0, height=64.0,
        )
        title = _native_text(
            column.title, title_layout,
            _native_style(44, color=column.accent, weight=900, align="left"),
        )
        group.add(title, animations=_entrance(title, at=0, duration=params.reveal, blur=4.0))
        for item_index, item in enumerate(column.items, start=1):
            item_layout = LayoutBox(
                x=x + 32.0,
                y=params.layout.y + 112.0 + (item_index - 1) * row_height,
                width=panel_width - 64.0, height=row_height,
            )
            obj = _native_text(
                item, item_layout, _native_style(32, color="#F9FAFB", weight=500, align="left")
            )
            group.add(obj, animations=_entrance(
                obj, at=item_index * params.stagger, duration=params.reveal, blur=4.0
            ))
    return group.ops


def _card_entrance(
    obj: TextObject | ShapeObject | ImageObject | WebObject,
    *,
    at: int,
    reveal: int,
    final: tuple[float, float],
    deal: tuple[float, float],
    overshoot: float,
) -> list[Animation]:
    middle = at + reveal // 2
    end = at + reveal
    if not at < middle < end:
        raise PresetError("card-stack overshoot needs two distinct entrance segments")
    return [
        _animation(
            "anm_pending_opacity", obj.object_id, "opacity",
            [Keyframe(at=at, value=0.0, easing=_ease()), Keyframe(at=middle, value=1.0)],
        ),
        _animation(
            "anm_pending_position", obj.object_id, "transform.position",
            [
                Keyframe(
                    at=at,
                    value=(deal[0] + final[0], deal[1] + final[1]),
                    easing=_ease(),
                ),
                Keyframe(at=end, value=final),
            ],
        ),
        _animation(
            "anm_pending_scale", obj.object_id, "transform.scale",
            [
                Keyframe(at=at, value=0.92, easing=_ease()),
                Keyframe(at=middle, value=overshoot, easing=_ease()),
                Keyframe(at=end, value=1.0),
            ],
        ),
    ]


def _expand_card_stack(content: CompositionContent, params: CardStackParams) -> list[Op]:
    _layout_inside(content, params.layout, "card-stack")
    _require_final_hold(
        params.range, params.reveal + (len(params.cards) - 1) * params.stagger, params.hold
    )
    group = _NativeGroup(content, "card-stack", params.range, params.scene_id)
    for index, card in enumerate(params.cards):
        at = index * params.stagger
        final = (index * params.fan_offset, index * params.fan_offset)
        if card.source_clip_id is not None:
            _, source_clip = _find_clip(content, card.source_clip_id)
            if not isinstance(source_clip.object, (ImageObject, WebObject)) or source_clip.source is None:
                raise PresetError("card-stack media cards need sourced frozen image/web clips")
            obj = source_clip.object.model_copy(deep=True)
            obj.layout = params.layout.model_copy(deep=True)
            obj.transform = Transform()
            obj.opacity = 1.0
            group.add(
                obj,
                animations=_card_entrance(
                    obj, at=at, reveal=params.reveal, final=final,
                    deal=params.deal_offset, overshoot=params.overshoot,
                ),
                source=source_clip.source,
                scene_id=params.scene_id if params.scene_id is not None else source_clip.scene_id,
            )
            continue
        panel = _native_shape(
            params.layout, fill="#FFFFFF", stroke="#E5E7EB", stroke_width=2.0, corner_radius=24.0
        )
        animations = _card_entrance(
            panel, at=at, reveal=params.reveal, final=final,
            deal=params.deal_offset, overshoot=params.overshoot,
        )
        group.add(panel, animations=animations)
        title_height = 72.0 if card.body else params.layout.height - 48.0
        title_layout = LayoutBox(
            x=params.layout.x + 28.0, y=params.layout.y + 24.0,
            width=params.layout.width - 56.0, height=title_height,
        )
        title = _native_text(
            card.title or "", title_layout,
            _native_style(42, color="#111827", weight=900, align="left"),
        )
        group.add(title, animations=_card_entrance(
            title, at=at, reveal=params.reveal, final=final,
            deal=params.deal_offset, overshoot=params.overshoot,
        ))
        if card.body:
            body_layout = LayoutBox(
                x=params.layout.x + 28.0, y=params.layout.y + 112.0,
                width=params.layout.width - 56.0, height=params.layout.height - 136.0,
            )
            body = _native_text(
                card.body, body_layout,
                _native_style(28, color="#4B5563", weight=500, align="left"),
            )
            group.add(body, animations=_card_entrance(
                body, at=at, reveal=params.reveal, final=final,
                deal=params.deal_offset, overshoot=params.overshoot,
            ))
    return group.ops


def _expand_list_reveal(content: CompositionContent, params: ListRevealParams) -> list[Op]:
    _layout_inside(content, params.layout, "list-reveal")
    _require_final_hold(
        params.range, params.reveal + (len(params.items) - 1) * params.stagger, params.hold
    )
    group = _NativeGroup(content, "list-reveal", params.range, params.scene_id)
    row_height = params.layout.height / len(params.items)
    if row_height < 32:
        raise PresetError("list-reveal rows are too short for native text")
    for index, item in enumerate(params.items):
        at = index * params.stagger
        text_x = params.layout.x + (64.0 if item.checked is not None else 0.0)
        layout = LayoutBox(
            x=text_x, y=params.layout.y + index * row_height,
            width=params.layout.width - (text_x - params.layout.x), height=row_height,
        )
        obj = _native_text(item.text, layout, _native_style(38, color=params.text_color, weight=600, align="left"))
        group.add(obj, animations=_entrance(obj, at=at, duration=params.reveal, offset=(24.0, 0.0), blur=4.0))
        if item.checked is not None:
            mark_layout = LayoutBox(
                x=params.layout.x, y=layout.y, width=48.0, height=row_height
            )
            mark = _native_text(
                "✓" if item.checked else "×", mark_layout,
                _native_style(
                    40, color="#16A34A" if item.checked else "#6B7280", weight=900
                ),
            )
            group.add(mark, animations=_entrance(
                mark, at=at, duration=params.reveal, offset=(24.0, 0.0), blur=4.0
            ))
    return group.ops


def _notification_entrance(
    obj: TextObject | ShapeObject,
    *,
    at: int,
    reveal: int,
    collapse_at: int,
    collapse: int,
    expanded_y: float,
    card_height: float,
) -> list[Animation]:
    reveal_end = at + reveal
    points: dict[int, tuple[float, float]] = {
        at: (0.0, expanded_y - card_height - 24.0),
        reveal_end: (0.0, expanded_y),
        collapse_at + collapse: (0.0, 0.0),
    }
    if collapse_at > reveal_end:
        points[collapse_at] = (0.0, expanded_y)
    return [
        _animation(
            "anm_pending_opacity", obj.object_id, "opacity",
            [Keyframe(at=at, value=0.0, easing=_ease()), Keyframe(at=reveal_end, value=1.0)],
        ),
        _animation(
            "anm_pending_position", obj.object_id, "transform.position",
            [Keyframe(at=point, value=value, easing=_ease()) for point, value in sorted(points.items())],
        ),
    ]


def _expand_notification_stack(
    content: CompositionContent, params: NotificationStackParams
) -> list[Op]:
    _layout_inside(content, params.layout, "notification-stack")
    count = len(params.events)
    expanded_height = count * params.card_height + (count - 1) * 16.0
    collapsed_height = params.card_height + (count - 1) * params.stack_offset
    if expanded_height > params.layout.height or collapsed_height > params.layout.height:
        raise PresetError("notification-stack expanded and collapsed cards must fit their layout")
    collapse_at = params.reveal + (count - 1) * params.stagger
    _require_final_hold(params.range, collapse_at + params.collapse, params.hold)
    group = _NativeGroup(content, "notification-stack", params.range, params.scene_id)
    for index, event in enumerate(params.events):
        final_y = params.layout.y + index * params.stack_offset
        expanded_y = params.layout.y + index * (params.card_height + 16.0)
        card_layout = LayoutBox(
            x=params.layout.x, y=final_y, width=params.layout.width, height=params.card_height
        )
        kwargs = {
            "at": index * params.stagger,
            "reveal": params.reveal,
            "collapse_at": collapse_at,
            "collapse": params.collapse,
            "expanded_y": expanded_y - final_y,
            "card_height": params.card_height,
        }
        panel = _native_shape(
            card_layout, fill="#FFFFFF", stroke="#E5E7EB", stroke_width=2.0, corner_radius=20.0
        )
        group.add(panel, animations=_notification_entrance(panel, **kwargs))
        text = event.title if event.body is None else f"{event.title}\n{event.body}"
        text_layout = LayoutBox(
            x=card_layout.x + 24.0, y=card_layout.y + 16.0,
            width=card_layout.width - 48.0, height=card_layout.height - 32.0,
        )
        obj = _native_text(text, text_layout, _native_style(30, color="#111827", weight=700, align="left"))
        group.add(obj, animations=_notification_entrance(obj, **kwargs))
    return group.ops


def _expand_title_lockup(content: CompositionContent, params: TitleLockupParams) -> list[Op]:
    _layout_inside(content, params.layout, "title-lockup")
    entrance_count = 2 if params.subtitle is not None else 1
    _require_final_hold(
        params.range, params.reveal + (entrance_count - 1) * params.stagger, params.hold
    )
    group = _NativeGroup(content, "title-lockup", params.range, params.scene_id)
    brand_height = 112.0 if params.brand_clip_id is not None else 0.0
    subtitle_height = 72.0 if params.subtitle is not None else 0.0
    title_height = params.layout.height - brand_height - subtitle_height
    if title_height <= 0:
        raise PresetError("title-lockup leaves no native title layout")
    if params.brand_clip_id is not None:
        _, source_clip = _find_clip(content, params.brand_clip_id)
        if not isinstance(source_clip.object, ImageObject) or source_clip.source is None:
            raise PresetError("title-lockup brand needs a sourced frozen image clip")
        brand = source_clip.object.model_copy(deep=True)
        brand.layout = LayoutBox(
            x=params.layout.x + (params.layout.width - brand_height) / 2,
            y=params.layout.y, width=brand_height, height=brand_height,
        )
        brand.fit = "contain"
        brand.transform = Transform()
        brand.opacity = 1.0
        group.add(
            brand,
            animations=_entrance(brand, at=0, duration=params.reveal, offset=(0.0, 0.0)),
            source=source_clip.source,
            scene_id=params.scene_id if params.scene_id is not None else source_clip.scene_id,
        )
    title_layout = LayoutBox(
        x=params.layout.x, y=params.layout.y + brand_height,
        width=params.layout.width, height=title_height,
    )
    title = _native_text(
        params.title, title_layout,
        params.style or _native_style(88, color="#111827", weight=900),
    )
    group.add(title, animations=_entrance(
        title, at=0, duration=params.reveal, offset=(0.0, 0.0), blur=8.0, scale=1.06
    ), role="title")
    if params.subtitle is not None:
        subtitle_layout = LayoutBox(
            x=params.layout.x, y=params.layout.y + brand_height + title_height,
            width=params.layout.width, height=subtitle_height,
        )
        subtitle = _native_text(
            params.subtitle, subtitle_layout,
            _native_style(36, color=params.style.color if params.style else "#4B5563", weight=500),
        )
        group.add(subtitle, animations=_entrance(
            subtitle, at=params.stagger, duration=params.reveal, offset=(0.0, 16.0), blur=4.0
        ))
    return group.ops


@dataclass(frozen=True)
class PresetDefinition:
    parameters: type[_Params]
    expander: Callable[[CompositionContent, Any], list[Op]]


PRESET_REGISTRY: dict[str, PresetDefinition] = {
    "caption-phrases": PresetDefinition(CaptionPhrasesParams, _expand_caption_phrases),
    "text-reveal": PresetDefinition(TextRevealParams, _expand_text_reveal),
    "text-impact": PresetDefinition(TextImpactParams, _expand_text_impact),
    "typewriter": PresetDefinition(TypewriterParams, _expand_typewriter),
    "keyword-fill": PresetDefinition(KeywordFillParams, _expand_keyword_fill),
    "word-cycle": PresetDefinition(WordCycleParams, _expand_word_cycle),
    "claim-layout": PresetDefinition(ClaimLayoutParams, _expand_claim_layout),
    "highlight-sweep": PresetDefinition(HighlightSweepParams, _expand_highlight_sweep),
    "path-underline": PresetDefinition(PathUnderlineParams, _expand_path_underline),
    "callout": PresetDefinition(CalloutParams, _expand_callout),
    "flow-steps": PresetDefinition(FlowStepsParams, _expand_flow_steps),
    "comparison-columns": PresetDefinition(ComparisonColumnsParams, _expand_comparison_columns),
    "card-stack": PresetDefinition(CardStackParams, _expand_card_stack),
    "list-reveal": PresetDefinition(ListRevealParams, _expand_list_reveal),
    "notification-stack": PresetDefinition(NotificationStackParams, _expand_notification_stack),
    "title-lockup": PresetDefinition(TitleLockupParams, _expand_title_lockup),
}


def expand_preset_at_target(
    preset_id: str,
    content: CompositionContent,
    target: EditTarget,
    parameters: dict[str, Any] | None = None,
) -> list[Op]:
    """Resolve a user-selected candidate at one explicit native target.

    Clip-targeted text motion derives bounded defaults from the actual clip;
    structured layout Presets still require their declared content parameters.
    The returned value is always the ordinary write-door op family.
    """
    supplied = dict(parameters or {})
    if target.kind == "clip":
        assert target.id is not None
        _, clip = _find_clip(content, target.id)
        if "clip_id" in supplied and supplied["clip_id"] != target.id:
            raise PresetError("apply_preset target and parameters.clip_id disagree")
        supplied["clip_id"] = target.id
        frame = frames_to_ticks(1, content.settings.timebase, content.settings.fps.num, content.settings.fps.den)
        if preset_id == "text-reveal":
            supplied.setdefault("kind", "word")
            supplied.setdefault("duration", min(frames_to_ticks(18, content.settings.timebase, content.settings.fps.num, content.settings.fps.den), clip.range.duration))
            supplied.setdefault("stagger", 0)
        elif preset_id == "typewriter":
            _, _, obj = _text_clip(content, target.id)
            supplied.setdefault("interval", max(frame, clip.range.duration // max(1, len(obj.text))))
            supplied.setdefault("cursor", False)
        elif preset_id == "keyword-fill":
            _, _, obj = _text_clip(content, target.id)
            parts = derive_text_parts(obj.text, "word")
            if not parts:
                raise PresetError("keyword-fill needs a native text word")
            supplied.setdefault("kind", "word")
            supplied.setdefault("part_ids", [parts[0].part_id])
            supplied.setdefault("at", 0)
            supplied.setdefault("color", "#F59E0B")
        elif preset_id == "path-underline":
            reveal = min(frames_to_ticks(18, content.settings.timebase, content.settings.fps.num, content.settings.fps.den), clip.range.duration // 2)
            supplied.setdefault("reveal", max(frame, reveal))
            supplied.setdefault("hold", clip.range.duration - supplied["reveal"])
        ops = expand_preset(preset_id, content, supplied)
        if preset_id in {"text-reveal", "typewriter"}:
            # Entrance Presets replace the target's prior TextPart motion rather
            # than stacking incompatible word/grapheme hierarchies. Whole-object
            # motion and every unnamed content field remain untouched.
            replaced = {
                animation.animation_id
                for animation in clip.animations
                if animation.text_part is not None
            }
            for op in ops:
                if isinstance(op, UpdateClip) and op.clip_id == clip.clip_id and op.animations is not None:
                    op.animations = [
                        animation for animation in op.animations
                        if animation.animation_id not in replaced
                    ]
        return ops
    if target.kind == "scene":
        assert target.id is not None
        scene = next((item for item in content.scenes if item.scene_id == target.id), None)
        if scene is None:
            raise PresetError(f"scene {target.id!r} does not exist")
        supplied.setdefault("scene_id", target.id)
        supplied.setdefault("range", scene.range.model_dump(mode="json"))
    elif target.kind == "timeline":
        end = max((clip.range.end for track in content.timeline.tracks for clip in track.clips), default=0)
        if end <= 0:
            raise PresetError("a timeline Preset needs a non-empty composition")
        supplied.setdefault("range", TimeRange(start=0, end=end).model_dump(mode="json"))
    else:
        raise PresetError("apply_preset needs one clip, scene or timeline target, not an ambiguous set")
    return expand_preset(preset_id, content, supplied)


def expand_preset(
    preset_id: str, content: CompositionContent, parameters: dict[str, Any] | _Params
) -> list[Op]:
    """Resolve one registered preset into ordinary ops for the sole write door."""
    definition = PRESET_REGISTRY.get(preset_id)
    if definition is None:
        raise PresetError(f"unknown native preset {preset_id!r}")
    params = (
        parameters if isinstance(parameters, definition.parameters)
        else definition.parameters.model_validate(parameters)
    )
    return definition.expander(content, params)
