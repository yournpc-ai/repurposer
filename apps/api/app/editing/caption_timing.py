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
_PAUSE_TAG_RE = re.compile(r"<#\s*(\d+(?:\.\d+)?)\s*#>")


def strip_pause_tags(text: str) -> str:
    """Remove MiniMax inline pause tags (e.g. ``<#0.4#>``) for clean display/matching."""
    if not text or "<#" not in text:
        return text
    cleaned = _PAUSE_TAG_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


# Broadcast subtitle punctuation cleanup:
# - Chinese: omit 。，、；： (replace internal pause marks with single spaces, strip trailing),
#   while preserving ？ ！ 《》 “” ‘’ …… —— · decimals, domains, and time ratios (10:30).
# - English: strip trailing sentence/clause punctuation (. , ; :) without touching ellipses (...),
#   decimals (£18.7m), domains (OxValue.AI), or single-letter abbreviations (U.S.).
_ZH_OMIT_INTERNAL_RE = re.compile(r"[，、；：]|(?<!\d)[,;](?!\d)|(?<!\d):(?!\d|//)")
_ZH_OMIT_PERIOD_RE = re.compile(r"。+")
_EN_TRAILING_PUNCT_RE = re.compile(r"(?:[,;:]|(?<!\.)(?<!\b[A-Za-z])\.)+$")


def _format_single_caption_line(line: str, language: str | None = None) -> str:
    cleaned = " ".join(strip_pause_tags(line or "").split())
    if not cleaned:
        return ""
    lang = detect_text_language(cleaned, hint=language)
    if lang == "zh":
        cleaned = _ZH_OMIT_PERIOD_RE.sub(" ", cleaned)
        cleaned = _ZH_OMIT_INTERNAL_RE.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Avoid orphan spaces around preserved CJK wrapper/tone punctuation.
        cleaned = re.sub(r"\s+([？！》”’）])", r"\1", cleaned)
        cleaned = re.sub(r"([《“‘（])\s+", r"\1", cleaned)
        return cleaned.strip()
    cleaned = _EN_TRAILING_PUNCT_RE.sub("", cleaned).strip()
    return cleaned


def format_caption_punctuation(text: str, language: str | None = None) -> str:
    """Format subtitle text to broadcast/short-video punctuation standards.

    Processes bilingual multi-line captions independently per line so Chinese and
    English lines each follow their own punctuation convention.
    """
    if not text or not text.strip():
        return ""
    lines = text.splitlines()
    if len(lines) == 1:
        return _format_single_caption_line(lines[0], language=language)
    formatted = [_format_single_caption_line(line) for line in lines]
    return "\n".join(line for line in formatted if line)


def _segments_with_pauses(text: str) -> list[tuple[str, float]]:
    """Split text on ``<#x.x#>`` pause tags, returning ``[(segment_text, trailing_pause_ms)]``."""
    if not text:
        return []
    if "<#" not in text:
        clean = " ".join(text.split())
        return [(clean, 0.0)] if clean else []
    segments: list[tuple[str, float]] = []
    cursor = 0
    for match in _PAUSE_TAG_RE.finditer(text):
        part = " ".join(text[cursor:match.start()].split())
        pause_ms = max(0.0, min(5000.0, float(match.group(1)) * 1000.0))
        if part:
            segments.append((part, pause_ms))
        elif segments:
            prev_text, prev_pause = segments[-1]
            segments[-1] = (prev_text, prev_pause + pause_ms)
        cursor = match.end()
    tail = " ".join(text[cursor:].split())
    if tail:
        segments.append((tail, 0.0))
    return segments

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

    Preserves 100% verbatim spoken text (with inline ``<#x.x#>`` pause tags stripped)
    and distributes ``[time_begin_ms, time_end_ms]`` across the resulting phrases
    while respecting explicit pause durations when present.
    """
    if not text or time_end_ms <= time_begin_ms:
        return []
    if "<#" in text:
        segments = _segments_with_pauses(text)
        if not segments:
            return []
        total_ms = float(time_end_ms) - float(time_begin_ms)
        total_pause_ms = sum(pause for _, pause in segments)
        # Keep explicit pauses bounded so spoken segments always retain real duration.
        pause_scale = min(1.0, (total_ms * 0.45) / total_pause_ms) if total_pause_ms > 0 else 1.0
        speech_budget_ms = max(1.0, total_ms - total_pause_ms * pause_scale)
        weights = [_spoken_weight(seg, is_last=(idx == len(segments) - 1)) for idx, (seg, _) in enumerate(segments)]
        total_weight = sum(weights) or float(len(segments))
        out: list[TimedPhrase] = []
        cursor = float(time_begin_ms)
        for idx, ((seg, pause_ms), weight) in enumerate(zip(segments, weights, strict=True)):
            seg_ms = speech_budget_ms * (weight / total_weight)
            seg_end = float(time_end_ms) if idx == len(segments) - 1 and pause_ms == 0.0 else min(float(time_end_ms), cursor + seg_ms)
            if seg_end > cursor:
                out.extend(split_cue_into_timed_phrases(seg, cursor, seg_end, language=language))
            cursor = min(float(time_end_ms), seg_end + pause_ms * pause_scale)
        return out
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    lang = detect_text_language(cleaned, hint=language)
    tokens = _text_tokens(cleaned, lang)
    pieces = ["".join(tokens[i:j]).strip() for i, j in _phrase_ranges(tokens, lang, 46, 8)]
    return _distribute_timing(pieces, float(time_begin_ms), float(time_end_ms))


def _norm_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_pause_tags(text or "")).strip().lower()


_ZH_DIGITS = "零一二三四五六七八九"
_EN_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _int_to_zh(n: int) -> str:
    if n < 0 or n > 999:
        return str(n)
    if n < 10:
        return _ZH_DIGITS[n]
    if n < 20:
        return "十" + ("" if n == 10 else _ZH_DIGITS[n % 10])
    if n < 100:
        t, o = divmod(n, 10)
        return _ZH_DIGITS[t] + "十" + ("" if o == 0 else _ZH_DIGITS[o])
    h, rem = divmod(n, 100)
    if rem == 0:
        return _ZH_DIGITS[h] + "百"
    if rem < 10:
        return _ZH_DIGITS[h] + "百零" + _ZH_DIGITS[rem]
    if rem < 20:
        return _ZH_DIGITS[h] + "百一十" + ("" if rem == 10 else _ZH_DIGITS[rem % 10])
    return _ZH_DIGITS[h] + "百" + _int_to_zh(rem)


def _int_to_en(n: int) -> list[str]:
    if n < 0 or n > 999:
        return [str(n)]
    if n < 20:
        return [_EN_ONES[n]]
    if n < 100:
        t, o = divmod(n, 10)
        if o == 0:
            return [_EN_TENS[t]]
        return [f"{_EN_TENS[t]}-{_EN_ONES[o]}", f"{_EN_TENS[t]} {_EN_ONES[o]}"]
    h, rem = divmod(n, 100)
    if rem == 0:
        return [f"{_EN_ONES[h]} hundred"]
    return [f"{_EN_ONES[h]} hundred {sub}" for sub in _int_to_en(rem)]


def _phrase_match_variants(phrase: str) -> list[str]:
    """Generate exact + spoken-number variants so '27 个' matches '二十七个' and '27' matches 'twenty-seven'."""
    base = _norm_match_text(phrase)
    if not base:
        return []
    variants: list[str] = [base]

    def _add(v: str) -> None:
        v = _norm_match_text(v)
        if v and v not in variants:
            variants.append(v)

    # Replace standalone integers (0..999) with Chinese & English spoken forms.
    nums = list(re.finditer(r"(?<![\d.])(\d{1,3})(?![\d.])", base))
    if nums:
        zh_sub = base
        en_hyphen = base
        en_space = base
        for m in reversed(nums):
            val = int(m.group(1))
            zh_word = _int_to_zh(val)
            en_forms = _int_to_en(val)
            zh_sub = zh_sub[: m.start()] + zh_word + zh_sub[m.end() :]
            en_hyphen = en_hyphen[: m.start()] + en_forms[0] + en_hyphen[m.end() :]
            en_space = en_space[: m.start()] + en_forms[-1] + en_space[m.end() :]
        _add(zh_sub)
        if "2" in base:
            _add(zh_sub.replace("二", "两", 1))
        _add(en_hyphen)
        _add(en_space)
        # Also bare spoken number itself when the phrase is a short metric value like "27 个" or "8%"
        if len(nums) == 1 and len(base) <= 10:
            val = int(nums[0].group(1))
            _add(_int_to_zh(val))
            for ef in _int_to_en(val):
                _add(ef)
    return variants


def resolve_cue_phrase_window_s(
    narration: str,
    phrase: str,
    *,
    cues: list[dict[str, Any]] | None,
    duration_s: float,
    speech_lead_s: float = 0.15,
    language: str | None = None,
    min_start_s: float = 0.0,
) -> tuple[float, float] | None:
    """Resolve a spoken ``phrase`` inside ``narration`` into act-local ``(start_s, end_s)``.

    Prefers real millisecond word timestamps (``cue["words"]`` from MiniMax
    ``subtitle_type="word"``) when available; otherwise falls back to sentence cues
    plus explicit ``<#x.x#>`` pause tags and spoken-weight distribution.
    Supports bilingual spoken-number normalization (e.g. ``27 个`` ↔ ``二十七个`` / ``twenty-seven``).
    """
    variants = _phrase_match_variants(phrase)
    clean_narration = _norm_match_text(narration)
    if not variants or not clean_narration or duration_s <= 0:
        return None

    # Build ordered acoustic spans [(text_chunk, start_ms, end_ms, join_direct)] across the act.
    # When cue["words"] is present, join tokens directly inside the same cue so sub-word English
    # tokens ("E"+"ight") reconstruct "eight" while keeping exact acoustic millisecond timestamps.
    joined_parts: list[str] = []
    span_ranges: list[tuple[int, int, str, float, float]] = []
    cursor = 0

    def _append_span(raw_text: str, tb_ms: float, te_ms: float, *, sep_before: bool) -> None:
        nonlocal cursor
        if sep_before and joined_parts and not joined_parts[-1].endswith(" ") and not raw_text.startswith(" "):
            joined_parts.append(" ")
            cursor += 1
        norm_part = raw_text.lower()
        if not norm_part:
            return
        start_ch = cursor
        joined_parts.append(norm_part)
        cursor += len(norm_part)
        span_ranges.append((start_ch, cursor, norm_part, tb_ms, te_ms))

    if cues:
        prev_end = 0.0
        for cue in cues:
            cue_words = cue.get("words")
            if isinstance(cue_words, list) and cue_words:
                first_in_cue = True
                for w in cue_words:
                    wt = strip_pause_tags(str(w.get("word") or ""))
                    if not wt:
                        continue
                    wb = max(0.0, float(w["time_begin"]))
                    we = max(wb, float(w["time_end"]))
                    _append_span(wt, wb, we, sep_before=first_in_cue)
                    first_in_cue = False
                    prev_end = max(prev_end, we)
                continue
            cue_text = str(cue.get("text") or "").strip()
            if not cue_text:
                continue
            tb = max(prev_end, float(cue["time_begin"]))
            te = float(cue["time_end"])
            if te <= tb:
                continue
            for tp in split_cue_into_timed_phrases(cue_text, tb, te, language=language):
                norm_tp = _norm_match_text(tp.text)
                if norm_tp:
                    _append_span(norm_tp, tp.time_begin_ms, tp.time_end_ms, sep_before=True)
                    prev_end = tp.time_end_ms
    if not span_ranges:
        for tp in split_cue_into_timed_phrases(narration, 0.0, duration_s * 1000.0, language=language):
            norm_tp = _norm_match_text(tp.text)
            if norm_tp:
                _append_span(norm_tp, tp.time_begin_ms, tp.time_end_ms, sep_before=True)
    if not span_ranges:
        return None

    haystack = "".join(joined_parts)
    char_map: list[int] = []
    compact_chars: list[str] = []
    for idx, ch in enumerate(haystack):
        if ch.isalnum() or is_cjk_char(ch):
            compact_chars.append(ch)
            char_map.append(idx)
    c_haystack = "".join(compact_chars)

    def _offset_to_ms(char_offset: int) -> float:
        for s_ch, e_ch, norm_part, tb_ms, te_ms in span_ranges:
            if char_offset <= e_ch:
                local_idx = max(0, char_offset - s_ch)
                if local_idx <= 0 or not norm_part:
                    return tb_ms
                if local_idx >= len(norm_part):
                    return te_ms
                prefix_w = _spoken_weight(norm_part[:local_idx], is_last=False)
                full_w = _spoken_weight(norm_part, is_last=True)
                ratio = max(0.0, min(1.0, prefix_w / max(full_w, 1.0)))
                return tb_ms + (te_ms - tb_ms) * ratio
        return span_ranges[-1][4]

    min_ms = max(0.0, (min_start_s - speech_lead_s) * 1000.0)

    def _find_after_min(needle: str) -> tuple[int, int] | None:
        search_from = 0
        while True:
            pos = haystack.find(needle, search_from)
            if pos < 0:
                break
            if _offset_to_ms(pos) >= min_ms - 50.0:
                return pos, pos + len(needle)
            search_from = pos + 1
        compact_needle = re.sub(r"[^\w\u4e00-\u9fff]+", "", needle)
        if not compact_needle:
            return None
        c_from = 0
        while True:
            c_pos = c_haystack.find(compact_needle, c_from)
            if c_pos < 0:
                return None
            pos = char_map[c_pos]
            end_pos = char_map[min(len(char_map) - 1, c_pos + len(compact_needle) - 1)] + 1
            if _offset_to_ms(pos) >= min_ms - 50.0:
                return pos, end_pos
            c_from = c_pos + 1

    match_span: tuple[int, int] | None = None
    for needle in variants:
        match_span = _find_after_min(needle)
        if match_span is not None:
            break
    if match_span is None:
        return None

    pos, end_pos = match_span
    start_ms = _offset_to_ms(pos)
    end_ms = max(start_ms + 150.0, _offset_to_ms(end_pos))
    start_s = round(max(0.0, min(duration_s - 0.1, speech_lead_s + start_ms / 1000.0)), 3)
    end_s = round(max(start_s + 0.15, min(duration_s, speech_lead_s + end_ms / 1000.0)), 3)
    return start_s, end_s


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
    narr_lang = detect_text_language(strip_pause_tags(narration), hint=language)
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
    "format_caption_punctuation",
    "resolve_cue_phrase_window_s",
    "split_cue_into_timed_phrases",
    "strip_pause_tags",
]
