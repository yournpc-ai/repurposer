"""Native caption phrase boundaries for measured words, sentence cues and translations."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from typing_extensions import TypedDict

_STRONG_PUNCT = frozenset(".!?。！？")
_SOFT_PUNCT = frozenset(",;:—–，；：、")
_CLOSING_WRAP = frozenset("\"'”’」』》）】)]")

# CJK tokenization: keep Latin/numeric runs (e.g. "Rookie Cut" words, "1080p", "3.5x", "85%") indivisible.
_CJK_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[._%×xX+-][A-Za-z0-9]+)*|\s+|.")

# English clause split: split right after sentence/clause punctuation followed by whitespace,
# or around spaced em/en dashes. Never splits inside decimals (4.2) or domains (OxValue.AI).
_EN_CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[.!?;:,])\s+|(?<=[—–])\s*|\s+(?=[—–])"
)

# CJK clause split: split right after Chinese/English clause punctuation (+ any immediately following closing quote/bracket).
_CJK_CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[。！？；，：、.!?;:,])(?![\"'”’」』》）】)\]])|(?<=[。！？；，：、.!?;:,][\"'”’」』》）】)\]])"
)


@dataclass(frozen=True)
class TimedPhrase:
    """One verbatim single-line (or aligned bilingual) caption phrase bounded in milliseconds."""

    text: str
    time_begin_ms: float
    time_end_ms: float
    word_timings: tuple[tuple[float, float], ...] | None = None


class TimedWord(TypedDict):
    text: str
    start_s: float
    end_s: float


def is_han_char(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF or 0x20000 <= code <= 0x2FA1F
    )


def is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return is_han_char(ch) or 0x3040 <= code <= 0x30FF or 0xAC00 <= code <= 0xD7AF


def detect_text_language(text: str, hint: str | None = None) -> str:
    """Detect whether ``text`` is primarily CJK ('zh') or Latin ('en')."""
    cjk_count = sum(1 for ch in text if is_cjk_char(ch))
    latin_count = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk_count > 0 and cjk_count >= max(2, latin_count * 0.35):
        return "zh"
    if latin_count > 0 and cjk_count == 0:
        return "en"
    if hint and hint.strip():
        norm = hint.strip().lower()
        if norm.startswith(("zh", "ja", "ko")):
            return "zh"
        return norm.split("-", 1)[0]
    return "zh" if cjk_count > 0 else "en"


def _cjk_visual_width(text: str) -> float:
    """Estimate line width in CJK character equivalents (CJK=1.0, Latin/digit/punct=0.55)."""
    width = 0.0
    for ch in text:
        if is_cjk_char(ch) or ch in "，。！？；：、（）《》「」『』“”":
            width += 1.0
        else:
            width += 0.55
    return width


def _spoken_weight(text: str, *, is_last: bool) -> float:
    """Estimate relative spoken duration weight for proportional timing distribution."""
    cjk_chars = 0
    alnum_chars = 0
    internal_pause = 0.0
    stripped = text.strip()
    if not stripped:
        return 1.0
    for idx, ch in enumerate(stripped):
        if is_cjk_char(ch):
            cjk_chars += 1
        elif ch.isalnum():
            alnum_chars += 1
        elif ch in _STRONG_PUNCT:
            if not (is_last and idx >= len(stripped) - 2):
                internal_pause += 3.5
        elif ch in _SOFT_PUNCT:
            if not (is_last and idx >= len(stripped) - 2):
                internal_pause += 2.0
    return max(1.0, cjk_chars * 2.2 + alnum_chars * 1.0 + internal_pause)


def _distribute_timing(
    phrases: list[str],
    time_begin_ms: float,
    time_end_ms: float,
) -> list[TimedPhrase]:
    """Distribute ``[time_begin_ms, time_end_ms]`` contiguously across ``phrases`` by spoken weight."""
    clean = [p.strip() for p in phrases if p and p.strip()]
    if not clean or time_end_ms <= time_begin_ms:
        return []
    if len(clean) == 1:
        return [TimedPhrase(text=clean[0], time_begin_ms=float(time_begin_ms), time_end_ms=float(time_end_ms))]

    weights = [
        _spoken_weight(phrase, is_last=(idx == len(clean) - 1))
        for idx, phrase in enumerate(clean)
    ]
    total_weight = sum(weights) or float(len(clean))
    total_ms = float(time_end_ms) - float(time_begin_ms)

    out: list[TimedPhrase] = []
    cursor = float(time_begin_ms)
    cumulative = 0.0
    for idx, (phrase, weight) in enumerate(zip(clean, weights, strict=True)):
        cumulative += weight
        if idx == len(clean) - 1:
            end_ms = float(time_end_ms)
        else:
            raw_end = float(time_begin_ms) + total_ms * (cumulative / total_weight)
            # Guarantee strictly monotonic non-zero span while reserving room for remaining phrases.
            min_end = cursor + 1.0
            max_end = float(time_end_ms) - float(len(clean) - 1 - idx)
            end_ms = round(max(min_end, min(raw_end, max_end)), 1) if max_end >= min_end else round(raw_end, 1)
        out.append(TimedPhrase(text=phrase, time_begin_ms=cursor, time_end_ms=end_ms))
        cursor = end_ms
    return out


def _phrase_ranges(tokens: list[str], language: str, max_chars: int, max_words: int) -> Iterator[tuple[int, int]]:
    """Yield token windows, preferring punctuation and keeping both sides readable."""
    cjk = language == "zh"
    width = _cjk_visual_width if cjk else len
    limit = min(19, max_chars) if cjk else max_chars
    start = 0
    while start < len(tokens):
        end = start + 1
        line = tokens[start]
        while end < len(tokens):
            candidate = line + tokens[end]
            if width(candidate.strip()) > limit or (not cjk and len(candidate.split()) > max_words):
                break
            line = candidate
            end += 1
        if end < len(tokens):
            def score(cut: int):
                left = "".join(tokens[start:cut]).strip()
                right = "".join(tokens[cut:end + 4]).strip()
                tiny = min(width(left), width(right)) < 4 if cjk else min(len(left.split()), len(right.split())) < 2
                punct = left.rstrip("".join(_CLOSING_WRAP))[-1:] in (_STRONG_PUNCT | _SOFT_PUNCT)
                return tiny, not punct, abs(width(left) - limit * 0.75)
            end = min(range(start + 1, end + 1), key=score)
        yield start, end
        start = end


def _text_tokens(text: str, language: str) -> list[str]:
    if language != "zh":
        return re.findall(r"\S+\s*", text)
    tokens: list[str] = []
    for token in _CJK_TOKEN_RE.findall(text):
        if tokens and (token.isspace() or token in _CLOSING_WRAP | _STRONG_PUNCT | _SOFT_PUNCT):
            tokens[-1] += token
        else:
            tokens.append(token)
    return tokens


def words_in_window(words: list[TimedWord], start_s: float, end_s: float) -> list[TimedWord]:
    return [
        TimedWord(text=w["text"], start_s=max(start_s, w["start_s"]), end_s=min(end_s, w["end_s"]))
        for w in words if (w["end_s"] > start_s or w["start_s"] == start_s) and w["start_s"] < end_s
    ]


def chunk_timed_words(
    words: list[TimedWord], language: str | None = None, *,
    max_chars: int = 46, max_words: int = 8, verbatim: bool = False,
) -> list[TimedPhrase]:
    """Split measured words at their boundaries. Verbatim tokens carry source spacing."""
    tokens = [word["text"] for word in words]
    lang = detect_text_language("".join(tokens), hint=language)
    if not verbatim and lang != "zh":
        tokens = [token.strip() + " " for token in tokens]
    phrases = []
    for first, end in _phrase_ranges(tokens, lang, max_chars, max_words):
        start_s = words[first]["start_s"]
        phrases.append(TimedPhrase(
            "".join(tokens[first:end]).strip(), start_s * 1000, words[end - 1]["end_s"] * 1000,
            tuple((w["start_s"] - start_s, w["end_s"] - start_s) for w in words[first:end]),
        ))
    return phrases


def split_cue_into_timed_phrases(
    text: str,
    time_begin_ms: float,
    time_end_ms: float,
    language: str | None = None,
) -> list[TimedPhrase]:
    """Split a single TTS cue into broadcast-grade timed single-line phrases.

    Preserves 100% verbatim spoken text and distributes ``[time_begin_ms, time_end_ms]``
    contiguously across the resulting phrases by spoken-weight length.
    """
    cleaned = " ".join((text or "").split())
    if not cleaned or time_end_ms <= time_begin_ms:
        return []
    lang = detect_text_language(cleaned, hint=language)
    tokens = _text_tokens(cleaned, lang)
    pieces = ["".join(tokens[i:j]).strip() for i, j in _phrase_ranges(tokens, lang, 46, 8)]
    return _distribute_timing(pieces, float(time_begin_ms), float(time_end_ms))


def align_translations_to_phrases(
    translations: list[str], primary_phrases: list[TimedPhrase],
) -> list[str]:
    count = len(primary_phrases)
    parts = [t.strip() for t in translations if t.strip()]
    if not count or not parts:
        return [""] * count
    if len(parts) == count:
        return parts
    lang = detect_text_language(" ".join(parts))
    joiner = "" if lang == "zh" else " "
    if len(parts) == 1:
        boundary = _CJK_CLAUSE_SPLIT_RE if lang == "zh" else _EN_CLAUSE_SPLIT_RE
        parts = [s.strip() for s in boundary.split(parts[0]) if s.strip()]
    while len(parts) > count:
        i = min(range(len(parts) - 1), key=lambda i: len(parts[i]) + len(parts[i + 1]))
        parts[i:i + 2] = [joiner.join(parts[i:i + 2])]
    while len(parts) < count:
        choices = [_text_tokens(part, lang) for part in parts]
        i = max(range(len(parts)), key=lambda i: len(choices[i]))
        tokens = choices[i]
        if len(tokens) < 2:
            break
        mid = len(tokens) // 2
        parts[i:i + 1] = ["".join(tokens[:mid]).strip(), "".join(tokens[mid:]).strip()]
    return parts + [""] * (count - len(parts))


def build_motion_block_caption_phrases(
    narration: str,
    *,
    cues: list[dict[str, Any]] | None,
    duration_ms: float,
    language: str,
    caption_translations: list[str] | None = None,
    caption_text: str | None = None,
) -> tuple[list[TimedPhrase], bool]:
    """Build verbatim millisecond-locked caption phrases for one narrated motion block act.

    Invariant:
    - Line 1 of every returned phrase is ALWAYS derived 100% verbatim from the spoken TTS
      ``cues`` (or ``narration`` when cues are absent) passed through
      ``split_cue_into_timed_phrases``.
    - Same-language paraphrased ``caption_text`` is ignored so spoken voice and captions
      never desync.
    - Bilingual translations (``caption_translations``, or second line / foreign-language
      ``caption_text``) align onto Line 2 across the exact same timed phrase windows.
    """
    narr_lang = detect_text_language(narration, hint=language)
    primary_phrases: list[TimedPhrase] = []

    if cues:
        prev_end = 0.0
        for cue in cues:
            cue_text = str(cue.get("text") or "").strip()
            if not cue_text:
                continue
            tb = max(prev_end, float(cue["time_begin"]))
            te = float(cue["time_end"])
            if te <= tb:
                continue
            chunked = split_cue_into_timed_phrases(cue_text, tb, te, language=narr_lang)
            if chunked:
                primary_phrases.extend(chunked)
                prev_end = chunked[-1].time_end_ms

    if not primary_phrases:
        primary_phrases = split_cue_into_timed_phrases(
            narration, 0.0, max(1.0, float(duration_ms)), language=narr_lang
        )

    if not primary_phrases:
        return [], False

    raw_translations: list[str] = []
    is_bilingual = False

    if caption_translations:
        cleaned_trans = [str(item).strip() for item in caption_translations if item and str(item).strip()]
        if cleaned_trans:
            raw_translations = cleaned_trans
            is_bilingual = True
    elif caption_text and caption_text.strip():
        lines = [ln.strip() for ln in caption_text.splitlines() if ln.strip()]
        if len(lines) >= 2:
            # Never replace Line 1 with paraphrased primary text; keep Line 2+ as translation.
            secondary = lines[1:]
            raw_translations = (
                secondary
                if len(secondary) == len(primary_phrases)
                else [" ".join(secondary)]
            )
            is_bilingual = True
        elif len(lines) == 1:
            cap_lang = detect_text_language(lines[0])
            if cap_lang != narr_lang:
                raw_translations = [lines[0]]
                is_bilingual = True
            # Same-language single-line caption_text is treated as a paraphrase and ignored.

    if not is_bilingual or not raw_translations:
        return primary_phrases, False

    aligned = align_translations_to_phrases(raw_translations, primary_phrases)
    bilingual_phrases = [
        TimedPhrase(
            text=f"{phrase.text}\n{t2}" if t2 else phrase.text,
            time_begin_ms=phrase.time_begin_ms,
            time_end_ms=phrase.time_end_ms,
        )
        for phrase, t2 in zip(primary_phrases, aligned, strict=True)
    ]
    return bilingual_phrases, True


__all__ = [
    "TimedPhrase",
    "TimedWord",
    "chunk_timed_words",
    "is_cjk_char",
    "align_translations_to_phrases",
    "build_motion_block_caption_phrases",
    "detect_text_language",
    "split_cue_into_timed_phrases",
]
