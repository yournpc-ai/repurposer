"""Semantic source selection over a frozen ASR word axis."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.editing.caption_timing import TimedWord
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks
from app.editing.transcript import word_groups


class SourceSentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: str
    start: float
    end: float
    text: str
    words: list[TimedWord] = Field(default_factory=list, exclude=True)


class SourceSelectionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_ids: list[str] = Field(min_length=1, max_length=64)
    include_previous: bool = False


@dataclass(frozen=True)
class SourceWindow:
    sentences: tuple[SourceSentence, ...]
    start: float
    end: float


def source_sentences(words: Any, *, duration_ticks: int) -> tuple[SourceSentence, ...]:
    if not isinstance(words, list) or not words:
        raise ValueError("the frozen video has no ASR word axis")
    import math

    previous_start = 0.0
    for raw in words:
        if not isinstance(raw, dict) or not str(raw.get("word") or "").strip():
            raise ValueError("the ASR word axis contains an empty word")
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("the ASR word axis has invalid timing") from exc
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("the ASR word axis has invalid timing")
        if start < previous_start or end < start or start < 0:
            raise ValueError("the ASR word axis is non-monotonic")
        if seconds_to_ticks(end, SOURCE_TIMEBASE) > duration_ticks:
            raise ValueError("the ASR word axis exceeds the frozen video duration")
        previous_start = start
    if len(words) > 12000:
        raise ValueError("the ASR word axis exceeds the supported source-analysis budget")
    sentences = tuple(
        SourceSentence(
            sentence_id=f"asr_{index:04d}",
            start=float(group[0]["start"]),
            end=max(float(w["end"]) for w in group),
            text="".join(w["word"] for w in group).strip(),
            words=[TimedWord(text=w["word"], start_s=float(w["start"]), end_s=float(w["end"])) for w in group],
        )
        for index, group in enumerate(word_groups(words), start=1)
        if max(float(w["end"]) for w in group) > float(group[0]["start"])
    )
    if not sentences:
        raise ValueError("the frozen video has no usable ASR sentences")
    return sentences


def resolve_selection(
    sentences: tuple[SourceSentence, ...], answer: SourceSelectionAnswer
) -> SourceWindow:
    positions = {sentence.sentence_id: index for index, sentence in enumerate(sentences)}
    unknown = [sentence_id for sentence_id in answer.sentence_ids if sentence_id not in positions]
    if unknown:
        raise ValueError(f"selection names unknown ASR sentences: {', '.join(unknown)}")
    indexes = [positions[sentence_id] for sentence_id in answer.sentence_ids]
    if len(set(indexes)) != len(indexes):
        raise ValueError("selection contains duplicate ASR sentences")
    indexes.sort()
    if answer.include_previous and indexes[0] > 0 and indexes[0] - 1 not in indexes:
        indexes.insert(0, indexes[0] - 1)
    if indexes != list(range(indexes[0], indexes[-1] + 1)):
        raise ValueError("one Scene needs one contiguous source selection; use separate Scenes for separate parts")
    selected = tuple(sentences[index] for index in indexes)
    return SourceWindow(sentences=selected, start=selected[0].start, end=selected[-1].end)


async def resolve_source_query(
    query: str,
    words: Any,
    *,
    duration_ticks: int,
    selector: Callable[[str, tuple[SourceSentence, ...]], Awaitable[SourceSelectionAnswer]],
) -> SourceWindow:
    if not query.strip():
        raise ValueError("source_query must describe the desired source passage")
    sentences = source_sentences(words, duration_ticks=duration_ticks)
    answer = await selector(query=query.strip(), sentences=sentences)
    if not isinstance(answer, SourceSelectionAnswer):
        answer = SourceSelectionAnswer.model_validate(answer)
    return resolve_selection(sentences, answer)
