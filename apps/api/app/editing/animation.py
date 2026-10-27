"""Deterministic TextPart derivation shared by validation and compilation.

Text ranges use Unicode scalar offsets (Python code points / JS code points),
not UTF-8 bytes or UTF-16 code units. Part IDs bind kind, text, range, layout
unit and segmentation version; an array position is never an identity.

The v1 grapheme segmenter covers combining marks, variation selectors, emoji
modifiers, ZWJ sequences and regional-indicator pairs. Word segmentation is
lexical (letter/number runs with internal apostrophes/hyphens), not a language
dictionary. Layout lines are explicit newline-delimited lines; browser inline
layout remains the single paint-time text flow.
"""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.editing.fonts import SEGMENTATION_VERSION

TextPartKind = Literal["line", "word", "grapheme"]


class TextRange(BaseModel):
    """Half-open Unicode-scalar range; empty lines are legal."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> TextRange:
        if self.end < self.start:
            raise ValueError("text range end must not precede start")
        return self


class TextPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: str
    kind: TextPartKind
    text: str
    text_range: TextRange
    # The explicit line whose inline flow lays out this part. For a line part
    # this equals text_range; for word/grapheme parts it is the enclosing line.
    layout_range: TextRange


def _fnv1a64(data: bytes) -> str:
    value = 0xCBF29CE484222325
    for byte in data:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def _part(kind: TextPartKind, chars: list[str], start: int, end: int, line: TextRange) -> TextPart:
    text = "".join(chars[start:end])
    identity = (
        f"{SEGMENTATION_VERSION}|{kind}|{len(chars[start:end])}:{text}|"
        f"{start}|{end}|{line.start}|{line.end}"
    ).encode()
    return TextPart(
        part_id=f"{kind}:{start}:{end}:{_fnv1a64(identity)}",
        kind=kind,
        text=text,
        text_range=TextRange(start=start, end=end),
        layout_range=line,
    )


def _line_ranges(chars: list[str]) -> list[TextRange]:
    lines: list[TextRange] = []
    start = 0
    index = 0
    while index < len(chars):
        char = chars[index]
        if char in ("\n", "\r"):
            lines.append(TextRange(start=start, end=index))
            if char == "\r" and index + 1 < len(chars) and chars[index + 1] == "\n":
                index += 1
            start = index + 1
        index += 1
    lines.append(TextRange(start=start, end=len(chars)))
    return lines


def _is_mark(char: str) -> bool:
    return unicodedata.category(char).startswith("M")


def _is_variation(char: str) -> bool:
    value = ord(char)
    return 0xFE00 <= value <= 0xFE0F or 0xE0100 <= value <= 0xE01EF


def _is_emoji_modifier(char: str) -> bool:
    return 0x1F3FB <= ord(char) <= 0x1F3FF


def _is_regional_indicator(char: str) -> bool:
    return 0x1F1E6 <= ord(char) <= 0x1F1FF


def _graphemes(chars: list[str], line: TextRange) -> list[TextPart]:
    parts: list[TextPart] = []
    index = line.start
    while index < line.end:
        end = index + 1
        regional_count = 1 if _is_regional_indicator(chars[index]) else 0
        while end < line.end:
            previous = chars[end - 1]
            char = chars[end]
            if (
                previous == "‍"
                or char == "‍"
                or _is_mark(char)
                or _is_variation(char)
                or _is_emoji_modifier(char)
            ):
                end += 1
                continue
            if (
                _is_regional_indicator(previous)
                and _is_regional_indicator(char)
                and regional_count % 2 == 1
            ):
                regional_count += 1
                end += 1
                continue
            break
        parts.append(_part("grapheme", chars, index, end, line))
        index = end
    return parts


def _is_word(cluster: str) -> bool:
    return bool(cluster) and all(unicodedata.category(c)[0] in {"L", "N", "M"} for c in cluster)


def _is_joiner(cluster: str) -> bool:
    return cluster in {"'", "’", "-", "‐", "‑"}


def _words(chars: list[str], line: TextRange) -> list[TextPart]:
    graphemes = _graphemes(chars, line)
    words: list[TextPart] = []
    open_start: int | None = None
    open_end: int | None = None

    def flush() -> None:
        nonlocal open_start, open_end
        if open_start is not None and open_end is not None:
            words.append(_part("word", chars, open_start, open_end, line))
        open_start = open_end = None

    for index, grapheme in enumerate(graphemes):
        start, end = grapheme.text_range.start, grapheme.text_range.end
        cluster = grapheme.text
        is_word = _is_word(cluster)
        next_is_word = index + 1 < len(graphemes) and _is_word(graphemes[index + 1].text)
        if is_word:
            if open_start is None:
                open_start = start
            open_end = end
            continue
        if _is_joiner(cluster) and open_start is not None and next_is_word:
            open_end = end
            continue
        flush()
        if cluster and not cluster.isspace():
            words.append(_part("word", chars, start, end, line))
    flush()
    return words


def derive_text_parts(text: str, kind: TextPartKind) -> list[TextPart]:
    """Derive one part family from the complete TextObject, never from clips."""
    chars = list(text)
    lines = _line_ranges(chars)
    if kind == "line":
        return [_part("line", chars, line.start, line.end, line) for line in lines]
    if kind == "grapheme":
        return [part for line in lines for part in _graphemes(chars, line)]
    if kind == "word":
        return [part for line in lines for part in _words(chars, line)]
    raise ValueError(f"unsupported TextPart kind {kind}")


def derive_text_part_families(text: str, kinds: set[TextPartKind]) -> list[TextPart]:
    """Line flow plus every targeted family, deduplicated by stable ID."""
    parts: dict[str, TextPart] = {}
    for part in derive_text_parts(text, "line"):
        parts[part.part_id] = part
    for kind in sorted(kinds - {"line"}):
        for part in derive_text_parts(text, kind):
            parts[part.part_id] = part
    return list(parts.values())
