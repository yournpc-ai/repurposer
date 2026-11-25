"""NarrationAlignment payload law, canonical digests and word-anchor resolution.

All source timings are integer ticks. Text ranges are half-open Unicode scalar
offsets into the exact script; matching normalization never replaces that text.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.editing.animation import derive_text_parts
from app.editing.schemas import (
    Animation,
    Easing,
    Keyframe,
    NarrationAlignmentRef,
    NarrationAnchor,
    TextPartTarget,
)
from app.editing.caption_timing import TimedWord
from app.editing.timing import SOURCE_TIMEBASE, source_ticks_to_output_ticks

NARRATION_ALGORITHM = "faster-whisper-script-v1"
NARRATION_NORMALIZATION = "nfkc-casefold-script-tokens-v1"


class NarrationSemantics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal[
        "definition", "process", "comparison", "evidence", "example", "summary", "transition"
    ]
    weight: Literal["main", "sub"]
    entities: list[str] = Field(default=[], max_length=12)
    needs: list[Literal["native_text", "diagram", "real_media", "data", "generator"]] = Field(
        default=[], max_length=5
    )
    emphasis_word_ids: list[str] = Field(default=[], max_length=24)


class NarrationWord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word_id: str
    text: str
    text_start: int = Field(ge=0)
    text_end: int = Field(gt=0)
    start_tick: int = Field(ge=0)
    end_tick: int = Field(gt=0)
    timing: Literal["anchored", "interpolated"]

    @model_validator(mode="after")
    def _ordered(self) -> NarrationWord:
        if self.text_end <= self.text_start or self.end_tick <= self.start_tick:
            raise ValueError(f"word {self.word_id} has an empty text or time range")
        return self


class NarrationSentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: str
    text: str
    text_start: int = Field(ge=0)
    text_end: int = Field(gt=0)
    start_tick: int = Field(ge=0)
    end_tick: int = Field(gt=0)
    match: float = Field(ge=0, le=1)
    status: Literal["aligned", "review_required"]
    words: list[NarrationWord] = Field(min_length=1)
    semantics: NarrationSemantics | None = None

    @model_validator(mode="after")
    def _ordered(self) -> NarrationSentence:
        if self.text_end <= self.text_start or self.end_tick <= self.start_tick:
            raise ValueError(f"sentence {self.sentence_id} has an empty text or time range")
        previous_end = -1
        word_ids = set()
        for word in self.words:
            if word.word_id in word_ids:
                raise ValueError(f"duplicate word id {word.word_id}")
            word_ids.add(word.word_id)
            if not (self.text_start <= word.text_start < word.text_end <= self.text_end):
                raise ValueError(f"word {word.word_id} escapes its sentence text")
            if self.text[word.text_start - self.text_start:word.text_end - self.text_start] != word.text:
                raise ValueError(f"word {word.word_id} does not preserve the original script")
            if not (self.start_tick <= word.start_tick < word.end_tick <= self.end_tick):
                raise ValueError(f"word {word.word_id} escapes its sentence timing")
            if word.start_tick < previous_end:
                raise ValueError(f"sentence {self.sentence_id} has non-monotonic word timing")
            previous_end = word.end_tick
        if self.words[0].start_tick != self.start_tick or self.words[-1].end_tick != self.end_tick:
            raise ValueError(f"sentence {self.sentence_id} timing does not bound its words")
        if self.semantics is not None and any(
            word_id not in word_ids for word_id in self.semantics.emphasis_word_ids
        ):
            raise ValueError(f"sentence {self.sentence_id} emphasis references an unknown word")
        return self


def narration_words(sentence: NarrationSentence) -> list[TimedWord]:
    """Attach the script's inter-word punctuation and spacing to its measured tokens."""
    words = []
    for i, word in enumerate(sentence.words):
        start = word.text_start if i else sentence.text_start
        end = sentence.words[i + 1].text_start if i + 1 < len(sentence.words) else sentence.text_end
        words.append(TimedWord(
            text=sentence.text[start - sentence.text_start:end - sentence.text_start],
            start_s=word.start_tick / SOURCE_TIMEBASE, end_s=word.end_tick / SOURCE_TIMEBASE,
        ))
    return words


class NarrationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_timebase: int = Field(gt=0)
    duration_ticks: int = Field(gt=0)
    sentences: list[NarrationSentence] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> NarrationPayload:
        previous_text_end = 0
        previous_tick = 0
        sentence_ids = set()
        word_ids = set()
        for sentence in self.sentences:
            if sentence.sentence_id in sentence_ids:
                raise ValueError(f"duplicate sentence id {sentence.sentence_id}")
            sentence_ids.add(sentence.sentence_id)
            if sentence.text_start < previous_text_end or sentence.start_tick < previous_tick:
                raise ValueError("narration sentences must be monotonic in text and time")
            if sentence.end_tick > self.duration_ticks:
                raise ValueError(f"sentence {sentence.sentence_id} exceeds the real audio duration")
            for word in sentence.words:
                if word.word_id in word_ids:
                    raise ValueError(f"duplicate word id {word.word_id}")
                word_ids.add(word.word_id)
            previous_text_end = sentence.text_end
            previous_tick = sentence.end_tick
        return self


def _canonical(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _identity(
    payload: NarrationPayload,
    *,
    text_digest: str,
    audio_digest: str,
    algorithm: str,
    normalization_version: str,
    provider: str,
    model: str,
) -> dict:
    return {
        "text_digest": text_digest,
        "audio_digest": audio_digest,
        "algorithm": algorithm,
        "normalization_version": normalization_version,
        "provider": provider,
        "model": model,
        "payload": payload.model_dump(mode="json"),
    }


def alignment_timing_digest(
    payload: NarrationPayload,
    *,
    text_digest: str,
    audio_digest: str,
    algorithm: str,
    normalization_version: str,
    provider: str,
    model: str,
) -> str:
    identity = _identity(
        payload,
        text_digest=text_digest,
        audio_digest=audio_digest,
        algorithm=algorithm,
        normalization_version=normalization_version,
        provider=provider,
        model=model,
    )
    for sentence in identity["payload"]["sentences"]:
        sentence.pop("semantics", None)
    return _canonical(identity)


def alignment_content_digest(
    payload: NarrationPayload,
    *,
    text_digest: str,
    audio_digest: str,
    algorithm: str,
    normalization_version: str,
    provider: str,
    model: str,
) -> str:
    return _canonical(
        _identity(
            payload,
            text_digest=text_digest,
            audio_digest=audio_digest,
            algorithm=algorithm,
            normalization_version=normalization_version,
            provider=provider,
            model=model,
        )
    )


def find_word(payload: NarrationPayload, word_id: str) -> tuple[NarrationSentence, NarrationWord]:
    matches = [
        (sentence, word)
        for sentence in payload.sentences
        for word in sentence.words
        if word.word_id == word_id
    ]
    if len(matches) != 1:
        raise ValueError(f"narration word {word_id!r} is missing or ambiguous")
    return matches[0]


def word_occurrence(sentence: NarrationSentence, text: str, occurrence: int | None = None) -> NarrationWord:
    """Resolve exact script text without silently choosing a repeated word."""
    matches = [word for word in sentence.words if word.text == text]
    if occurrence is None:
        if len(matches) != 1:
            raise ValueError(f"narration word {text!r} is missing or ambiguous")
        return matches[0]
    if occurrence < 0 or occurrence >= len(matches):
        raise ValueError(f"narration word occurrence {occurrence} is out of range")
    return matches[occurrence]


def narration_anchor_part_kind(
    payload: NarrationPayload,
    *,
    caption_text: str,
    word_ids: list[str],
    caption_text_start: int | None = None,
) -> Literal["word", "grapheme"]:
    """One caption uses one TextPart hierarchy, including bilingual phrases."""
    for word_id in word_ids:
        sentence, word = find_word(payload, word_id)
        text_start = sentence.text_start if caption_text_start is None else caption_text_start
        text_end = text_start + len(caption_text)
        if (
            text_start < sentence.text_start
            or text_end > sentence.text_end
            or caption_text != sentence.text[text_start - sentence.text_start:text_end - sentence.text_start]
            or word.text_start < text_start
            or word.text_end > text_end
        ):
            raise ValueError(f"word {word_id} can only anchor its own exact caption phrase")
        local_range = (word.text_start - text_start, word.text_end - text_start)
        if not any(
            (item.text_range.start, item.text_range.end) == local_range
            for item in derive_text_parts(caption_text, "word")
        ):
            return "grapheme"
    return "word"


@dataclass(frozen=True)
class NarrationWordPlacement:
    sentence: NarrationSentence
    word: NarrationWord
    part_kind: Literal["word", "grapheme"]
    part_ids: list[str]
    start: int
    end: int
    duration: int


def resolve_narration_word(
    payload: NarrationPayload,
    *,
    caption_text: str,
    word_id: str,
    output_timebase: int,
    part_kind: Literal["word", "grapheme"] = "word",
    caption_text_start: int | None = None,
    clip_start_tick: int | None = None,
    clip_end_tick: int | None = None,
) -> NarrationWordPlacement:
    """Resolve exact caption identity and source timing into Clip-local ticks."""
    sentence, word = find_word(payload, word_id)
    text_start = sentence.text_start if caption_text_start is None else caption_text_start
    text_end = text_start + len(caption_text)
    if (
        text_start < sentence.text_start
        or text_end > sentence.text_end
        or caption_text != sentence.text[text_start - sentence.text_start:text_end - sentence.text_start]
        or word.text_start < text_start
        or word.text_end > text_end
    ):
        raise ValueError(f"word {word_id} can only anchor its own exact caption phrase")
    local_range = (word.text_start - text_start, word.text_end - text_start)
    if part_kind == "word":
        parts = [
            item for item in derive_text_parts(caption_text, "word")
            if (item.text_range.start, item.text_range.end) == local_range
        ]
    else:
        parts = [
            item for item in derive_text_parts(caption_text, "grapheme")
            if local_range[0] <= item.text_range.start and item.text_range.end <= local_range[1]
        ]
    if not parts or "".join(item.text for item in parts) != word.text:
        raise ValueError(f"word {word_id} has no unambiguous caption TextPart")

    clip_source_start = sentence.start_tick if clip_start_tick is None else clip_start_tick
    clip_source_end = sentence.end_tick if clip_end_tick is None else clip_end_tick
    clip_start = source_ticks_to_output_ticks(clip_source_start, output_timebase)
    clip_end = source_ticks_to_output_ticks(clip_source_end, output_timebase)
    start = source_ticks_to_output_ticks(word.start_tick, output_timebase) - clip_start
    end = source_ticks_to_output_ticks(word.end_tick, output_timebase) - clip_start
    duration = clip_end - clip_start
    if start < 0 or end <= start or end > duration:
        raise ValueError(f"word {word_id} resolves outside its caption clip")
    return NarrationWordPlacement(
        sentence=sentence,
        word=word,
        part_kind=part_kind,
        part_ids=[part.part_id for part in parts],
        start=start,
        end=end,
        duration=duration,
    )


def narration_word_animation(
    payload: NarrationPayload,
    *,
    alignment: NarrationAlignmentRef,
    speech_object_id: str,
    target_object_id: str,
    animation_id: str,
    caption_text: str,
    word_id: str,
    output_timebase: int,
    part_kind: Literal["word", "grapheme"] = "word",
    caption_text_start: int | None = None,
    clip_start_tick: int | None = None,
    clip_end_tick: int | None = None,
) -> Animation:
    """Compatibility wrapper for one scale-only resolved word animation."""
    placement = resolve_narration_word(
        payload,
        caption_text=caption_text,
        word_id=word_id,
        output_timebase=output_timebase,
        part_kind=part_kind,
        caption_text_start=caption_text_start,
        clip_start_tick=clip_start_tick,
        clip_end_tick=clip_end_tick,
    )
    start, end = placement.start, placement.end
    if end - start == 1:
        keyframes = [
            Keyframe(at=start, value=1.12, easing=Easing(kind="cubic_bezier", params=(0.22, 1, 0.36, 1))),
            Keyframe(at=end, value=1.0),
        ]
    else:
        middle = start + max(1, (end - start) // 2)
        keyframes = [
            Keyframe(at=start, value=1.0),
            Keyframe(
                at=middle,
                value=1.12,
                easing=Easing(kind="cubic_bezier", params=(0.22, 1, 0.36, 1)),
            ),
            Keyframe(at=end, value=1.0),
        ]
    return Animation(
        animation_id=animation_id,
        target_object_id=target_object_id,
        text_part=TextPartTarget(kind=part_kind, part_ids=placement.part_ids, stagger=0),
        property="transform.scale",
        keyframes=keyframes,
        narration_anchor=NarrationAnchor(
            alignment_id=alignment.alignment_id,
            content_digest=alignment.content_digest,
            speech_object_id=speech_object_id,
            word_id=word_id,
        ),
    )
