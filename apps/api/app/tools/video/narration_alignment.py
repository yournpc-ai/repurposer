"""Deterministic final-script alignment over the existing faster-whisper facts.

The ASR transcript never replaces the reviewed script. Normalized character
alignment supplies direct word anchors; uncovered runs receive explicit,
monotonic interpolation and low-coverage sentences stay review_required.
"""
from __future__ import annotations

import bisect
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from fractions import Fraction
from typing import Any

from app.editing.alignment import (
    NarrationPayload,
    NarrationSentence,
    NarrationWord,
)
from app.editing.timing import SOURCE_TIMEBASE, quantize_ticks

_MIN_SENTENCE_MATCH = 0.6
_SENTENCE_END = set(".!?。！？；;\n")


class NarrationAlignmentError(ValueError):
    pass


@dataclass(frozen=True)
class _ScriptToken:
    text: str
    start: int
    end: int
    normalized: str
    normalized_start: int
    normalized_end: int


@dataclass(frozen=True)
class _AsrToken:
    start_tick: int
    end_tick: int
    normalized_start: int
    normalized_end: int


def _cjk(char: str) -> bool:
    value = ord(char)
    return (
        0x3400 <= value <= 0x4DBF
        or 0x4E00 <= value <= 0x9FFF
        or 0xF900 <= value <= 0xFAFF
        or 0x20000 <= value <= 0x2FA1F
    )


def _word_char(char: str) -> bool:
    return not _cjk(char) and unicodedata.category(char)[0] in {"L", "N", "M"}


def _normalize(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", value).casefold()
        if unicodedata.category(char)[0] in {"L", "N", "M"}
    )


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        boundary = char in _SENTENCE_END
        if char == "." and index + 1 < len(text) and text[index + 1].isdigit():
            boundary = False
        if char == "." and index + 1 < len(text) and not text[index + 1].isspace():
            boundary = False
        if boundary:
            end = index + 1
            while end < len(text) and text[end] in "\"'’”）)]}":
                end += 1
            spans.append((start, end))
            start = end
            index = end
        else:
            index += 1
    if start < len(text):
        spans.append((start, len(text)))
    trimmed = []
    for begin, end in spans:
        raw = text[begin:end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        if right > left:
            trimmed.append((begin + left, begin + right))
    if not trimmed:
        raise NarrationAlignmentError("the exact narration script has no speakable tokens")
    return trimmed


def _tokens(text: str, start: int, end: int) -> list[tuple[str, int, int]]:
    tokens: list[tuple[str, int, int]] = []
    index = start
    while index < end:
        char = text[index]
        if _cjk(char):
            tokens.append((char, index, index + 1))
            index += 1
            continue
        if not _word_char(char):
            index += 1
            continue
        token_end = index + 1
        while token_end < end:
            current = text[token_end]
            if _word_char(current):
                token_end += 1
                continue
            if (
                current in {"'", "’", "-", "‐", "‑"}
                and token_end + 1 < end
                and _word_char(text[token_end + 1])
            ):
                token_end += 2
                continue
            break
        tokens.append((text[index:token_end], index, token_end))
        index = token_end
    return tokens


def _script_tokens(text: str, spans: list[tuple[int, int]]) -> list[list[_ScriptToken]]:
    normalized_offset = 0
    result = []
    for start, end in spans:
        sentence_tokens = []
        for token_text, token_start, token_end in _tokens(text, start, end):
            normalized = _normalize(token_text)
            if not normalized:
                continue
            sentence_tokens.append(
                _ScriptToken(
                    token_text,
                    token_start,
                    token_end,
                    normalized,
                    normalized_offset,
                    normalized_offset + len(normalized),
                )
            )
            normalized_offset += len(normalized)
        if not sentence_tokens:
            raise NarrationAlignmentError("a narration sentence has no speakable tokens")
        result.append(sentence_tokens)
    return result


def _asr_tokens(asr: dict[str, Any], duration_ticks: int) -> tuple[list[_AsrToken], str]:
    raw_words = asr.get("words") or []
    if not isinstance(raw_words, list):
        raise NarrationAlignmentError("faster-whisper returned no word list")
    normalized_parts = []
    facts = []
    offset = 0
    for raw in raw_words:
        if not isinstance(raw, dict):
            raise NarrationAlignmentError("faster-whisper returned a malformed word")
        normalized = _normalize(str(raw.get("word") or ""))
        if not normalized:
            continue
        try:
            start = quantize_ticks(Fraction(str(raw["start"])) * SOURCE_TIMEBASE)
            end = quantize_ticks(Fraction(str(raw["end"])) * SOURCE_TIMEBASE)
        except (KeyError, TypeError, ValueError) as exc:
            raise NarrationAlignmentError("faster-whisper returned invalid word timing") from exc
        if start < 0 or end <= start or end > duration_ticks:
            raise NarrationAlignmentError("ASR word timing is non-monotonic or exceeds the audio duration")
        if facts and start < facts[-1].start_tick:
            raise NarrationAlignmentError("ASR word timing is non-monotonic")
        facts.append(_AsrToken(start, end, offset, offset + len(normalized)))
        normalized_parts.append(normalized)
        offset += len(normalized)
    return facts, "".join(normalized_parts)


def _boundary_time(tokens: list[_AsrToken], starts: list[int], offset: int) -> int:
    index = bisect.bisect_right(starts, offset) - 1
    index = max(0, min(index, len(tokens) - 1))
    token = tokens[index]
    if offset <= token.normalized_start:
        return token.start_tick
    if offset >= token.normalized_end:
        return token.end_tick
    fraction = Fraction(offset - token.normalized_start, token.normalized_end - token.normalized_start)
    return quantize_ticks(token.start_tick + fraction * (token.end_tick - token.start_tick))


def _interpolate(
    anchors: list[tuple[int, int] | None], duration_ticks: int
) -> list[tuple[int, int]]:
    result = list(anchors)
    index = 0
    while index < len(result):
        if result[index] is not None:
            index += 1
            continue
        group_start = index
        while index < len(result) and result[index] is None:
            index += 1
        previous = result[group_start - 1] if group_start else None
        following = result[index] if index < len(result) else None
        start = previous[1] if previous is not None else 0
        end = following[0] if following is not None else duration_ticks
        count = index - group_start
        if end - start <= count:
            raise NarrationAlignmentError("too few source ticks for monotonic word interpolation")
        boundaries = [start]
        boundaries.extend(start + (end - start) * step // (count + 1) for step in range(1, count + 1))
        boundaries.append(end)
        for offset in range(count):
            pair = (boundaries[offset], boundaries[offset + 1])
            if pair[1] <= pair[0]:
                raise NarrationAlignmentError("word interpolation collapsed to zero duration")
            result[group_start + offset] = pair
    previous_end = 0
    for pair in result:
        assert pair is not None
        if pair[0] < previous_end or pair[1] <= pair[0] or pair[1] > duration_ticks:
            raise NarrationAlignmentError("aligned words are non-monotonic or exceed the audio duration")
        previous_end = pair[1]
    return [pair for pair in result if pair is not None]


def align_narration(
    *,
    text: str,
    asr: dict[str, Any],
    duration_ticks: int,
    source_timebase: int = SOURCE_TIMEBASE,
) -> NarrationPayload:
    if source_timebase != SOURCE_TIMEBASE:
        raise NarrationAlignmentError("the source snapshot uses an unsupported timebase")
    if duration_ticks <= 0:
        raise NarrationAlignmentError("the audio snapshot has no positive source duration")
    spans = _sentence_spans(text)
    sentences_tokens = _script_tokens(text, spans)
    flat_tokens = [token for sentence in sentences_tokens for token in sentence]
    asr_tokens, asr_normalized = _asr_tokens(asr, duration_ticks)
    script_normalized = "".join(token.normalized for token in flat_tokens)

    mapped: list[int | None] = [None] * len(script_normalized)
    matcher = SequenceMatcher(None, script_normalized, asr_normalized, autojunk=False)
    for script_start, asr_start, length in matcher.get_matching_blocks():
        for offset in range(length):
            mapped[script_start + offset] = asr_start + offset

    asr_starts = [token.normalized_start for token in asr_tokens]
    anchors: list[tuple[int, int] | None] = []
    for token in flat_tokens:
        positions = mapped[token.normalized_start:token.normalized_end]
        if not positions or any(position is None for position in positions) or not asr_tokens:
            anchors.append(None)
            continue
        start_offset = min(position for position in positions if position is not None)
        end_offset = max(position for position in positions if position is not None) + 1
        start = _boundary_time(asr_tokens, asr_starts, start_offset)
        end = _boundary_time(asr_tokens, asr_starts, end_offset)
        anchors.append((start, end) if end > start else None)
    timings = _interpolate(anchors, duration_ticks)

    sentences = []
    token_offset = 0
    for sentence_index, (span, tokens) in enumerate(zip(spans, sentences_tokens, strict=True), start=1):
        words = []
        for local_index, token in enumerate(tokens):
            index = token_offset + local_index
            start, end = timings[index]
            words.append(
                NarrationWord(
                    word_id=f"w{index + 1:06d}",
                    text=token.text,
                    text_start=token.start,
                    text_end=token.end,
                    start_tick=start,
                    end_tick=end,
                    timing="anchored" if anchors[index] is not None else "interpolated",
                )
            )
        token_offset += len(tokens)
        match = sum(anchors[token_offset - len(tokens) + i] is not None for i in range(len(tokens))) / len(tokens)
        sentences.append(
            NarrationSentence(
                sentence_id=f"s{sentence_index:04d}",
                text=text[span[0]:span[1]],
                text_start=span[0],
                text_end=span[1],
                start_tick=words[0].start_tick,
                end_tick=words[-1].end_tick,
                match=match,
                status="aligned" if match >= _MIN_SENTENCE_MATCH else "review_required",
                words=words,
            )
        )
    return NarrationPayload(
        source_timebase=source_timebase,
        duration_ticks=duration_ticks,
        sentences=sentences,
    )
