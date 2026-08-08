"""Deterministic output-fidelity checks (zero LLM, zero new dependencies).

Pure functions behind the DAG's ``verify`` node kind
(docs/tasks/output-quality-verify.md §2.1). Every check returns a
``CheckResult`` whose ``ok`` is tri-state:

- ``True``  — passed
- ``False`` — failed (bounce-worthy)
- ``None``  — skipped: no deterministic basis to judge (cross-language
  verbatim, non-product target language, missing inputs). Skipped is never
  counted as a failure — 无确定性依据不判决.
"""

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

# The six product languages (NAMING: en/zh/de/fr/es/it). Detection beyond
# these is out of scope — a non-product target means "skipped", not "fail".
PRODUCT_LANGUAGES = frozenset({"en", "zh", "de", "fr", "es", "it"})

_CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
_LATIN_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_PUNCT_RE = re.compile(r"[^\w\s一-鿿㐀-䶿]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"[.?!。！？;；\n]+")

# Compact stopword lists for the five latin product languages (zh is detected
# by CJK character ratio instead). Whole-word frequency decides; overlaps
# (in/la/de/un…) are expected and cancel out at ≥3 hits.
_STOPWORDS: dict[str, tuple[str, ...]] = {
    "en": ("the", "and", "of", "to", "in", "is", "that", "for", "on", "with",
           "as", "are", "this", "be", "it", "we", "you", "not", "have"),
    "de": ("der", "die", "und", "das", "ist", "in", "zu", "den", "mit", "von",
           "für", "auf", "nicht", "auch", "ein", "eine", "sich", "dem", "des"),
    "fr": ("le", "la", "les", "de", "des", "et", "est", "en", "un", "une",
           "du", "dans", "pour", "pas", "sur", "qui", "que", "au", "ce"),
    "es": ("el", "la", "los", "las", "de", "y", "en", "un", "una", "es",
           "con", "por", "para", "no", "del", "que", "se", "su", "al"),
    "it": ("il", "lo", "la", "gli", "le", "di", "e", "in", "un", "una",
           "è", "con", "per", "non", "del", "della", "che", "si", "da"),
}
_STOPWORD_RES: dict[str, re.Pattern[str]] = {
    lang: re.compile(
        r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE
    )
    for lang, words in _STOPWORDS.items()
}

# Length bounds (tokens = latin words + CJK chars). Latin bounds are the
# brief's; CJK bounds widen the prompts' own character targets by the same
# ~2× slack so a legitimately-sized Chinese post never false-fails.
_LENGTH_BOUNDS: dict[str, dict[str, tuple[int, int]]] = {
    "post": {"latin": (100, 500), "cjk": (200, 900)},
    "article": {"latin": (400, 1600), "cjk": (600, 3200)},
}

_SPAN_F1_THRESHOLD = 0.5
_VERBATIM_THRESHOLD = 0.85
# Below this many stopword hits a latin text is too short/ambiguous to judge.
_LANGUAGE_MIN_HITS = 3


@dataclass(frozen=True)
class CheckResult:
    """One deterministic check outcome (``ok=None`` means skipped)."""

    id: str
    ok: bool | None
    detail: str


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace (CJK kept)."""
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", text.lower())).strip()


def _tokens(text: str) -> list[str]:
    """Latin words lowercased + each CJK char as its own token."""
    lowered = text.lower()
    return _LATIN_WORD_RE.findall(lowered) + _CJK_RE.findall(lowered)


def _is_cjk_dominant(text: str) -> bool:
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_WORD_RE.findall(text))
    return cjk > 0 and cjk >= latin


def span_fidelity(source_text: str, span_words: list[str]) -> CheckResult:
    """Token F1 between a clip's ``source_text`` and its span's actual words."""
    if not source_text.strip() or not span_words:
        return CheckResult("span_fidelity", None, "missing source_text or span words")
    a = Counter(_tokens(source_text))
    b = Counter(_tokens(" ".join(span_words)))
    if not a or not b:
        return CheckResult("span_fidelity", None, "no tokens to compare")
    overlap = sum((a & b).values())
    f1 = 2 * overlap / (sum(a.values()) + sum(b.values()))
    ok = f1 >= _SPAN_F1_THRESHOLD
    return CheckResult(
        "span_fidelity", ok, f"token F1={f1:.2f} (threshold {_SPAN_F1_THRESHOLD})"
    )


def quote_verbatim(quote: str, source_texts: list[str]) -> CheckResult:
    """Best sentence-window difflib ratio of the quote against the sources.

    Skipped when scripts disagree (e.g. an English quote over a Chinese
    transcript) — cross-language fidelity has no deterministic basis here.
    """
    sources = [s for s in source_texts if s and s.strip()]
    if not quote.strip() or not sources:
        return CheckResult("quote_verbatim", None, "missing quote or source texts")
    if _is_cjk_dominant(quote) != any(_is_cjk_dominant(s) for s in sources):
        return CheckResult(
            "quote_verbatim", None, "script mismatch (cross-language) — not judged"
        )
    needle = _normalize(quote)
    if not needle:
        return CheckResult("quote_verbatim", None, "quote normalizes to empty")
    best = 0.0
    for source in sources:
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(source) if s.strip()]
        # Quotes may straddle a sentence boundary — compare singles and pairs.
        windows = sentences + [
            f"{sentences[i]} {sentences[i + 1]}" for i in range(len(sentences) - 1)
        ]
        for window in windows:
            candidate = _normalize(window)
            if not candidate:
                continue
            ratio = SequenceMatcher(None, needle, candidate).ratio()
            best = max(best, ratio)
    ok = best >= _VERBATIM_THRESHOLD
    return CheckResult(
        "quote_verbatim", ok,
        f"best match ratio={best:.2f} (threshold {_VERBATIM_THRESHOLD})",
    )


def detect_language(text: str) -> str | None:
    """Best-effort product-language detection; None when undetermined."""
    if _is_cjk_dominant(text):
        return "zh"
    scores = {
        lang: len(pattern.findall(text)) for lang, pattern in _STOPWORD_RES.items()
    }
    lang, hits = max(scores.items(), key=lambda kv: kv[1])
    if hits < _LANGUAGE_MIN_HITS:
        return None
    return lang


def language_match(text: str, target: str) -> CheckResult:
    """Detected product language must equal the target language."""
    if target not in PRODUCT_LANGUAGES:
        return CheckResult(
            "language_match", None, f"target '{target}' not a product language"
        )
    if not text.strip():
        return CheckResult("language_match", None, "empty text")
    detected = detect_language(text)
    if detected is None:
        return CheckResult("language_match", None, "language undetermined")
    return CheckResult(
        "language_match", detected == target,
        f"detected={detected}, target={target}",
    )


def avoid_words(text: str, avoid: list[str] | None) -> CheckResult:
    """Zero substring hits against the persona's avoid list (normalized)."""
    if not avoid:
        return CheckResult("avoid_words", True, "no avoid list configured")
    haystack = _normalize(text)
    hits = [w for w in avoid if w.strip() and _normalize(w) in haystack]
    return CheckResult(
        "avoid_words", not hits,
        f"{len(hits)} hit(s): {', '.join(hits)}" if hits else "no hits",
    )


def length_in_bounds(text: str, kind: Literal["post", "article"]) -> CheckResult:
    """Token count within the per-kind, per-script bounds."""
    bounds = _LENGTH_BOUNDS[kind]["cjk" if _is_cjk_dominant(text) else "latin"]
    n = len(_tokens(text))
    ok = bounds[0] <= n <= bounds[1]
    return CheckResult(
        "length_in_bounds", ok, f"{n} tokens (bounds {bounds[0]}–{bounds[1]})"
    )


def count_match(actual: int, expected: int | None) -> CheckResult:
    """Produced item count equals the storyboard slot count."""
    if expected is None:
        return CheckResult("count_match", None, "no slot count to check against")
    return CheckResult(
        "count_match", actual == expected, f"{actual} produced, {expected} planned"
    )


def slide_count(actual: int, expected: int | None) -> CheckResult:
    """Carousel slide count equals the storyboard slot count."""
    if expected is None:
        return CheckResult("slide_count", None, "no slot count to check against")
    return CheckResult(
        "slide_count", actual == expected, f"{actual} slides, {expected} planned"
    )
