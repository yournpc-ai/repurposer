"""Broadcast-grade timed phrase chunking and bilingual lockstep alignment for TTS captions."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_LATIN_ALNUM_RE = re.compile(r"[A-Za-z0-9]")

# Natural English break words (prefer breaking BEFORE these words when splitting long unpunctuated runs).
_EN_BREAK_BEFORE = frozenset({
    "and", "or", "but", "yet", "so", "with", "without", "from", "into", "onto",
    "for", "that", "which", "where", "while", "when", "across", "through",
    "using", "by", "to", "in", "on", "of", "at", "as", "than", "under", "over",
})

# Punctuation pause weights for spoken-duration distribution.
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


def is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x3040 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )


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


def _split_long_en_clause(clause: str, *, max_chars: int = 46, max_words: int = 8) -> list[str]:
    """Split a single long English/Latin clause on word boundaries without orphans."""
    words = clause.split()
    if len(words) <= 1:
        return [clause]
    if len(clause) <= max_chars and len(words) <= max_words:
        return [clause]
    # Keep concise single-clause lines (<= 8 words and <= 54 chars with no internal clause punctuation).
    if len(words) <= max_words and len(clause) <= 54 and not any(ch in _SOFT_PUNCT for ch in clause):
        return [clause]

    n_chunks = max(
        math.ceil(len(clause) / max_chars),
        math.ceil(len(words) / max_words),
        2,
    )
    # Never create more chunks than floor(len(words) / 2) so we avoid 1-word orphans.
    n_chunks = min(n_chunks, max(1, len(words) // 2))
    if n_chunks <= 1:
        return [clause]

    chunks: list[str] = []
    start = 0
    remaining_chunks = n_chunks
    while remaining_chunks > 1:
        rem_words = words[start:]
        rem_text_len = len(" ".join(rem_words))
        target_chars = rem_text_len / remaining_chunks
        target_words = len(rem_words) / remaining_chunks

        # Candidate cut indices (in rem_words): leave at least 2 words on left and >= 2*(remaining_chunks-1) on right.
        min_cut = 2
        max_cut = len(rem_words) - 2 * (remaining_chunks - 1)
        if max_cut < min_cut:
            break

        best_cut = min_cut
        best_score = float("inf")
        for cut in range(min_cut, max_cut + 1):
            left_text = " ".join(rem_words[:cut])
            char_diff = abs(len(left_text) - target_chars) / max(1.0, target_chars)
            word_diff = abs(cut - target_words) / max(1.0, target_words)
            overflow_penalty = 0.0
            if len(left_text) > max_chars:
                overflow_penalty += (len(left_text) - max_chars) * 0.25
            if cut > max_words:
                overflow_penalty += (cut - max_words) * 1.5
            # Natural phrase boundary bonus when breaking right before a preposition/conjunction.
            next_word = rem_words[cut].lower().strip("\"'()[].,;:!?")
            boundary_bonus = -0.35 if next_word in _EN_BREAK_BEFORE else 0.0
            score = char_diff + 0.5 * word_diff + overflow_penalty + boundary_bonus
            if score < best_score:
                best_score = score
                best_cut = cut

        chunks.append(" ".join(rem_words[:best_cut]))
        start += best_cut
        remaining_chunks -= 1

    tail = " ".join(words[start:])
    if tail:
        chunks.append(tail)
    return chunks


def _split_en_phrases(text: str, *, max_chars: int = 46, max_words: int = 8) -> list[str]:
    """Split an English/Latin cue into clean single-line broadcast phrases."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    words = normalized.split()
    has_internal_break = bool(_EN_CLAUSE_SPLIT_RE.search(normalized))
    if len(normalized) <= max_chars and len(words) <= max_words:
        return [normalized]
    if not has_internal_break and len(words) <= max_words and len(normalized) <= 54:
        return [normalized]

    raw_clauses = [part.strip() for part in _EN_CLAUSE_SPLIT_RE.split(normalized) if part and part.strip()]
    if not raw_clauses:
        return [normalized]

    # Merge tiny non-sentence clauses (or short adjacent clauses that fit comfortably on one line).
    merged_clauses: list[str] = []
    for clause in raw_clauses:
        if not merged_clauses:
            merged_clauses.append(clause)
            continue
        prev = merged_clauses[-1]
        prev_ends_sentence = prev[-1] in _STRONG_PUNCT
        combined = f"{prev} {clause}"
        combined_words = len(combined.split())
        clause_words = len(clause.split())
        prev_words = len(prev.split())
        # Merge if neither side is a full sentence break and combined fits target bounds,
        # OR if one side is a 1-word fragment that would look orphaned alone.
        if (
            (not prev_ends_sentence and len(combined) <= max_chars and combined_words <= max_words)
            or (clause_words == 1 and len(combined) <= max_chars + 6 and combined_words <= max_words + 1)
            or (prev_words == 1 and not prev_ends_sentence and len(combined) <= max_chars + 6)
        ):
            merged_clauses[-1] = combined
        else:
            merged_clauses.append(clause)

    # Split any clause still exceeding broadcast line limits.
    phrases: list[str] = []
    for clause in merged_clauses:
        phrases.extend(_split_long_en_clause(clause, max_chars=max_chars, max_words=max_words))

    # Final safety pass: never leave a 1-word trailing orphan when we can merge cleanly.
    if len(phrases) >= 2 and len(phrases[-1].split()) == 1:
        if len(f"{phrases[-2]} {phrases[-1]}") <= max_chars + 10:
            phrases[-2] = f"{phrases[-2]} {phrases[-1]}"
            phrases.pop()
        else:
            # Rebalance last two phrases so both have >= 2 words.
            rebalanced = _split_long_en_clause(f"{phrases[-2]} {phrases[-1]}", max_chars=max_chars, max_words=max_words)
            phrases = [*phrases[:-2], *rebalanced]

    return phrases


def _tokenize_cjk(text: str) -> list[str]:
    """Tokenize mixed CJK/Latin text into atomic units, attaching closing punctuation to prior token."""
    raw = _CJK_TOKEN_RE.findall(text)
    tokens: list[str] = []
    for tok in raw:
        if tokens and len(tok) == 1 and tok in (_CLOSING_WRAP | _STRONG_PUNCT | _SOFT_PUNCT):
            tokens[-1] += tok
        elif tokens and tok.isspace():
            tokens[-1] += tok
        else:
            tokens.append(tok)
    return [t for t in tokens if t]


def _split_long_cjk_clause(clause: str, *, max_width: float = 19.0) -> list[str]:
    """Split an over-long CJK clause into balanced chunks without orphans or mid-word Latin breaks."""
    width = _cjk_visual_width(clause)
    if width <= max_width + 1.0:
        return [clause]

    tokens = _tokenize_cjk(clause)
    if len(tokens) <= 1:
        return [clause]

    n_chunks = max(2, math.ceil(width / max_width))
    # Prevent creating chunks smaller than ~4 visual units.
    n_chunks = min(n_chunks, max(1, int(width // 5.0)))
    if n_chunks <= 1:
        return [clause]

    chunks: list[str] = []
    start = 0
    remaining_chunks = n_chunks
    while remaining_chunks > 1:
        rem_tokens = tokens[start:]
        rem_text = "".join(rem_tokens)
        rem_width = _cjk_visual_width(rem_text)
        target = rem_width / remaining_chunks

        best_cut = 1
        best_score = float("inf")
        acc = ""
        for cut in range(1, len(rem_tokens)):
            acc += rem_tokens[cut - 1]
            left_w = _cjk_visual_width(acc)
            right_w = rem_width - left_w
            # Avoid tiny orphans (< 4 visual units) on either side.
            if left_w < 3.5 or right_w < 3.5 * (remaining_chunks - 1):
                continue
            score = abs(left_w - target)
            if left_w > max_width + 1.0:
                score += (left_w - max_width) * 2.0
            # Slight preference for breaking after whitespace or before common Chinese discourse markers.
            next_tok = rem_tokens[cut]
            if acc.endswith(" "):
                score -= 0.8
            elif next_tok in ("在", "将", "把", "让", "从", "为", "与", "和", "并", "让", "用"):
                score -= 0.4
            if score < best_score:
                best_score = score
                best_cut = cut

        chunk_text = "".join(rem_tokens[:best_cut]).strip()
        if chunk_text:
            chunks.append(chunk_text)
        start += best_cut
        remaining_chunks -= 1

    tail = "".join(tokens[start:]).strip()
    if tail:
        chunks.append(tail)
    return chunks or [clause]


def _split_cjk_phrases(text: str, *, max_width: float = 19.0) -> list[str]:
    """Split a Chinese/CJK cue into crisp single-line broadcast phrases (max ~18-20 chars, zero orphans)."""
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []
    total_w = _cjk_visual_width(normalized)
    raw_clauses = [part.strip() for part in _CJK_CLAUSE_SPLIT_RE.split(normalized) if part and part.strip()]

    # Short single-sentence cues stay whole; multi-sentence cues (> 15 chars with '。！？') may still split.
    if total_w <= max_width + 1.0:
        has_mid_sentence_break = len(raw_clauses) >= 2 and any(
            c[-1] in _STRONG_PUNCT for c in raw_clauses[:-1]
        )
        if not has_mid_sentence_break or total_w <= 14.0:
            return [normalized]

    if not raw_clauses:
        return [normalized]

    # Step 1: Merge tiny leading/trailing orphan clauses (<= 3.5 visual width) or short adjacent clauses.
    merged: list[str] = []
    idx = 0
    while idx < len(raw_clauses):
        clause = raw_clauses[idx]
        c_w = _cjk_visual_width(clause)
        if c_w <= 3.5 and idx + 1 < len(raw_clauses):
            # Attach tiny leading fragment (e.g. "是的，") to the next clause so it never flashes as an orphan.
            raw_clauses[idx + 1] = clause + raw_clauses[idx + 1]
            idx += 1
            continue
        if merged:
            prev = merged[-1]
            prev_ends_sentence = prev[-1] in _STRONG_PUNCT
            combined = prev + clause
            combined_w = _cjk_visual_width(combined)
            if (not prev_ends_sentence and combined_w <= max_width) or (c_w <= 3.5 and combined_w <= max_width + 4.0):
                merged[-1] = combined
                idx += 1
                continue
        merged.append(clause)
        idx += 1

    # Step 2: Split any clause still wider than max_width.
    phrases: list[str] = []
    for clause in merged:
        phrases.extend(_split_long_cjk_clause(clause, max_width=max_width))

    # Step 3: Final orphan guard — never leave a 1-2 char trailing phrase.
    if len(phrases) >= 2 and _cjk_visual_width(phrases[-1]) <= 3.5:
        combined = phrases[-2] + phrases[-1]
        if _cjk_visual_width(combined) <= max_width + 3.0:
            phrases[-2] = combined
            phrases.pop()
        else:
            phrases = [*phrases[:-2], *_split_long_cjk_clause(combined, max_width=max_width)]

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
    cleaned = re.sub(r"[ \t]+", " ", (text or "")).strip()
    if not cleaned or time_end_ms <= time_begin_ms:
        return []
    lang = detect_text_language(cleaned, hint=language)
    if lang == "zh":
        pieces = _split_cjk_phrases(cleaned)
    else:
        pieces = _split_en_phrases(cleaned)
    return _distribute_timing(pieces, float(time_begin_ms), float(time_end_ms))


def _split_translation_to_count(text: str, count: int, weights: list[float]) -> list[str]:
    """Split a single translation string into ``count`` balanced natural segments."""
    clean = " ".join(text.split())
    if count <= 1 or not clean:
        return [clean] if clean else [""] * max(1, count)

    lang = detect_text_language(clean)
    if lang == "zh":
        # Prefer natural Chinese clause splits if they already match count.
        clauses = [p.strip() for p in _CJK_CLAUSE_SPLIT_RE.split(clean) if p and p.strip()]
        if len(clauses) == count:
            return clauses
        tokens = _tokenize_cjk(clean)
        if len(tokens) < count:
            return [clean, *[""] * (count - 1)]
        total_w = sum(weights) or float(count)
        total_len = _cjk_visual_width(clean)
        out: list[str] = []
        start = 0
        cum_target = 0.0
        for idx in range(count - 1):
            cum_target += total_len * (weights[idx] / total_w)
            best_cut = start + 1
            best_diff = float("inf")
            max_cut = len(tokens) - (count - 1 - idx)
            for cut in range(start + 1, max_cut + 1):
                cur_w = _cjk_visual_width("".join(tokens[:cut]))
                diff = abs(cur_w - cum_target)
                if diff < best_diff:
                    best_diff = diff
                    best_cut = cut
            out.append("".join(tokens[start:best_cut]).strip())
            start = best_cut
        out.append("".join(tokens[start:]).strip())
        return out

    # English / Latin translation: prefer clause punctuation when it matches count.
    clauses = [p.strip() for p in _EN_CLAUSE_SPLIT_RE.split(clean) if p and p.strip()]
    if len(clauses) == count:
        return clauses

    words = clean.split()
    if len(words) < count:
        return [clean, *[""] * (count - 1)]

    total_w = sum(weights) or float(count)
    total_chars = len(clean)
    out = []
    start = 0
    cum_target = 0.0
    for idx in range(count - 1):
        cum_target += total_chars * (weights[idx] / total_w)
        best_cut = start + 1
        best_score = float("inf")
        max_cut = len(words) - (count - 1 - idx)
        for cut in range(start + 1, max_cut + 1):
            prefix = " ".join(words[:cut])
            score = abs(len(prefix) - cum_target)
            # Strong bonus if prefix ends at clause punctuation, smaller bonus before prepositions.
            if prefix[-1] in (_SOFT_PUNCT | _STRONG_PUNCT):
                score -= 8.0
            elif cut < len(words) and words[cut].lower().strip("\"'.,;:!?") in _EN_BREAK_BEFORE:
                score -= 3.0
            if score < best_score:
                best_score = score
                best_cut = cut
        out.append(" ".join(words[start:best_cut]))
        start = best_cut
    out.append(" ".join(words[start:]))
    return out


def align_translations_to_phrases(
    translations: list[str],
    primary_phrases: list[TimedPhrase],
) -> list[str]:
    """Align second-language translation line(s) 1:1 to ``primary_phrases``."""
    n = len(primary_phrases)
    if n == 0:
        return []
    clean = [t.strip() for t in translations if t and t.strip()]
    if not clean:
        return [""] * n
    if len(clean) == n:
        return clean

    weights = [
        _spoken_weight(p.text, is_last=(idx == n - 1))
        for idx, p in enumerate(primary_phrases)
    ]

    if len(clean) == 1:
        return _split_translation_to_count(clean[0], n, weights)

    if len(clean) > n:
        # Merge adjacent shortest pairs until len == n.
        merged = list(clean)
        joiner = "" if detect_text_language(clean[0]) == "zh" else " "
        while len(merged) > n:
            best_i = min(
                range(len(merged) - 1),
                key=lambda i: len(merged[i]) + len(merged[i + 1]),
            )
            merged[best_i] = f"{merged[best_i]}{joiner}{merged[best_i + 1]}"
            merged.pop(best_i + 1)
        return merged

    # 1 < len(clean) < n: iteratively split the longest segment into 2 until len == n.
    expanded = list(clean)
    while len(expanded) < n:
        longest_idx = max(range(len(expanded)), key=lambda i: len(expanded[i]))
        pieces = _split_translation_to_count(expanded[longest_idx], 2, [1.0, 1.0])
        if len(pieces) < 2 or not pieces[1]:
            break
        expanded[longest_idx : longest_idx + 1] = pieces
    while len(expanded) < n:
        expanded.append("")
    return expanded


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
    "align_translations_to_phrases",
    "build_motion_block_caption_phrases",
    "detect_text_language",
    "split_cue_into_timed_phrases",
]
