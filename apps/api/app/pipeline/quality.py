"""Deterministic output-fidelity checks (zero LLM, zero new dependencies).

Pure functions behind the DAG's ``verify`` node kind
(docs/tasks/output-quality-verify.md §2.1, upgraded by
docs/tasks/output-quality-line.md §2.4 质检环 v2). Every check returns a
``CheckResult`` whose ``ok`` is tri-state:

- ``True``  — passed
- ``False`` — failed (bounce-worthy)
- ``None``  — skipped: no deterministic basis to judge (cross-language
  verbatim, non-product target language, missing inputs). Skipped is never
  counted as a failure — 无确定性依据不判决.

``cls`` routes the exhausted path (§2.4.5): ``fidelity`` failures (保真/逐字/
语言/规格正确性) degrade to the non-blocking ``needs_human`` badge; ``craft``
failures (钩子/节奏/强调) escalate to the interrupt on double-fail. ``judge``
verdicts (the LLM half, §2.7) are recorded for the 机制信号 ledger but never
gate until the human calibration set lands (judge 漂移无地面真值不可检测).
"""

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

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
    # Routing class (§2.4.5): fidelity → needs_human badge on exhaustion;
    # craft → interrupt escalation on double-fail; judge → ledger-only
    # (advisory until the §2.7 calibration set exists).
    cls: str = "fidelity"


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


# ---------------------------------------------------------------------------
# Craft checks (产物质量线期 3, §2.4.1 可测量项) — clip render-spec anatomy.
# The bands are the §2.1 先验 table's defaults: they drive verify verdicts,
# never acceptance gates (解剖校准前, 禁止行为 #3). 钩子延迟 is zero by
# construction (locate_span snaps to the first word) and 响度 is owned by the
# render service's loudnorm pass — neither is re-measured here.
# ---------------------------------------------------------------------------

_DWELL_MIN_S = 1.3
_DWELL_MAX_S = 6.0
# Emphasis cues must sit within this of a semantic/acoustic hint to count as
# content-aligned (强调贴内容).
_EMPHASIS_ALIGN_TOLERANCE_S = 0.75
# The caption block's vertical band around its anchor (normalized frame
# coords): ±this around caption_position.y.
_CAPTION_BAND_HALF_H = 0.08
_CAPTION_X_RANGE = (0.08, 0.92)  # the 84%-wide caption block


def _kept_span(spec: dict) -> tuple[float, float] | None:
    """The clip's [start, end] from its kept segments (None when empty)."""
    kept = [s for s in (spec.get("segments") or []) if not s.get("hidden")]
    if not kept:
        return None
    return (
        min(float(s.get("start", 0)) for s in kept),
        max(float(s.get("end", 0)) for s in kept),
    )


def shot_dwells(spec: dict) -> CheckResult:
    """图停甜区 (craft): planned ``image_shots`` dwells, or the legacy even
    split's implied dwell — both must sit in the §2.1 band."""
    source = spec.get("source") or {}
    if source.get("kind") != "stills":
        return CheckResult("shot_dwells", None, "not a stills spec", cls="craft")
    dwells = [
        float(s.get("dwell_s") or 0)
        for s in (source.get("image_shots") or [])
        if float(s.get("dwell_s") or 0) > 0
    ]
    if not dwells:
        images = source.get("image_urls") or []
        span = _kept_span(spec)
        if not images or span is None or span[1] <= span[0]:
            return CheckResult("shot_dwells", None, "no backing visuals", cls="craft")
        dwells = [(span[1] - span[0]) / len(images)] * len(images)
    bad = [
        (i + 1, d) for i, d in enumerate(dwells) if d < _DWELL_MIN_S or d > _DWELL_MAX_S
    ]
    return CheckResult(
        "shot_dwells",
        not bad,
        f"{len(dwells)} dwells in band"
        if not bad
        else f"shots {', '.join(f'#{i} {d:.1f}s' for i, d in bad)} outside "
        f"{_DWELL_MIN_S}–{_DWELL_MAX_S}s",
        cls="craft",
    )


def caption_sync(spec: dict) -> CheckResult:
    """字幕同步 (fidelity-class spec correctness): cues monotonic, positive
    duration, and inside the kept span (one word-length of straddle tolerated
    — remove_range keeps straddling cues by design)."""
    cues = spec.get("caption_track") or []
    if not cues:
        return CheckResult("caption_sync", None, "no caption track")
    span = _kept_span(spec)
    if span is None:
        return CheckResult("caption_sync", None, "no kept segments")
    lo, hi = span[0] - 0.75, span[1] + 0.75
    problems: list[str] = []
    prev_start = None
    for i, c in enumerate(cues):
        start, end = float(c.get("start", 0)), float(c.get("end", 0))
        if end <= start:
            problems.append(f"cue {i + 1} non-positive duration")
        if start < lo or end > hi:
            problems.append(f"cue {i + 1} outside the clip span")
        if prev_start is not None and start < prev_start - 1e-6:
            problems.append(f"cue {i + 1} out of order")
        prev_start = start
    return CheckResult(
        "caption_sync",
        not problems,
        f"{len(cues)} cues in sync" if not problems else "; ".join(problems[:3]),
    )


def _frame_drawn_rect(
    img_w: float, img_h: float, frame_w: float, frame_h: float, fill_mode: str
) -> tuple[float, float, float, float]:
    """The image's drawn rect (x, y, w, h, frame-normalized) under the brand
    fill mode — cover (fill) / contain (fit), centered, mirroring objectFit."""
    if img_w <= 0 or img_h <= 0:
        return (0.0, 0.0, 1.0, 1.0)
    scale = (
        max(frame_w / img_w, frame_h / img_h)
        if fill_mode != "fit"
        else min(frame_w / img_w, frame_h / img_h)
    )
    drawn_w = img_w * scale / frame_w
    drawn_h = img_h * scale / frame_h
    return ((1.0 - drawn_w) / 2, (1.0 - drawn_h) / 2, drawn_w, drawn_h)


_ASPECT_FRAMES = {"9:16": (1080.0, 1920.0), "1:1": (1080.0, 1080.0), "16:9": (1920.0, 1080.0)}


def face_safe_area(spec: dict, anchors_by_url: dict[str, dict]) -> CheckResult:
    """人脸安全区 (craft, stills): no backing image's face may land inside the
    caption band. Geometry: the shot's image is drawn per the brand fill mode
    into the aspect frame; faces (normalized source coords) map through the
    drawn rect; the caption band is ±_CAPTION_BAND_HALF_H around
    caption_position.y over the 84% block width. Skipped when no shot carries
    face anchors."""
    source = spec.get("source") or {}
    if source.get("kind") != "stills":
        return CheckResult("face_safe_area", None, "not a stills spec", cls="craft")
    urls = [s.get("image_url") for s in (source.get("image_shots") or [])] or list(
        source.get("image_urls") or []
    )
    aspect = spec.get("aspect") if spec.get("aspect") in _ASPECT_FRAMES else "9:16"
    frame_w, frame_h = _ASPECT_FRAMES[aspect]
    fill_mode = ((spec.get("brand") or {}).get("fill_mode")) or "fill"
    pos = spec.get("caption_position") or {}
    band_y = float(pos.get("y", 0.84))
    band = (band_y - _CAPTION_BAND_HALF_H, band_y + _CAPTION_BAND_HALF_H)
    collisions: list[str] = []
    checked = 0
    for url in urls:
        anchors = anchors_by_url.get(url or "")
        if not anchors or not anchors.get("faces"):
            continue
        checked += 1
        rect = _frame_drawn_rect(
            float(anchors.get("width") or 0),
            float(anchors.get("height") or 0),
            frame_w,
            frame_h,
            fill_mode,
        )
        for face in anchors["faces"]:
            fx, fy, fw, fh = (float(v) for v in face[:4])
            # Source-normalized → frame-normalized through the drawn rect.
            cx0 = rect[0] + fx * rect[2]
            cy0 = rect[1] + fy * rect[3]
            cx1 = rect[0] + (fx + fw) * rect[2]
            cy1 = rect[1] + (fy + fh) * rect[3]
            overlap_y = max(0.0, min(cy1, band[1]) - max(cy0, band[0]))
            overlap_x = max(
                0.0, min(cx1, _CAPTION_X_RANGE[1]) - max(cx0, _CAPTION_X_RANGE[0])
            )
            if overlap_y > 0 and overlap_x > 0:
                face_area = max((cx1 - cx0) * (cy1 - cy0), 1e-6)
                if overlap_x * overlap_y / face_area > 0.5:
                    collisions.append(f"face at y≈{cy0:.2f} under the caption band")
                    break
    if checked == 0:
        return CheckResult("face_safe_area", None, "no face anchors on shots", cls="craft")
    return CheckResult(
        "face_safe_area",
        not collisions,
        f"{checked} anchored visual(s) clear"
        if not collisions
        else "; ".join(collisions[:2]),
        cls="craft",
    )


def emphasis_alignment(spec: dict, hint_times: list[float]) -> CheckResult:
    """强调贴内容 (craft): every emphasized caption cue (the editor's
    caption_pop beats) must sit within tolerance of a semantic/acoustic hint
    (understanding emphasis_words + prosody peaks — the two channels' times
    supplied side by side by the caller). Skipped when the spec has no
    emphasized cues or no hints exist (flat material is data, not failure)."""
    emphasized = [
        c for c in (spec.get("caption_track") or []) if c.get("emphasis")
    ]
    if not emphasized:
        return CheckResult(
            "emphasis_alignment", None, "no emphasized cues", cls="craft"
        )
    if not hint_times:
        return CheckResult(
            "emphasis_alignment", None, "no emphasis evidence on the material", cls="craft"
        )
    misses = []
    for c in emphasized:
        mid = (float(c.get("start", 0)) + float(c.get("end", 0))) / 2
        if not any(abs(mid - t) <= _EMPHASIS_ALIGN_TOLERANCE_S for t in hint_times):
            misses.append(f"'{str(c.get('text') or '')[:20]}' @ {mid:.1f}s")
    return CheckResult(
        "emphasis_alignment",
        not misses,
        f"{len(emphasized)} emphasized cue(s) on evidence"
        if not misses
        else f"emphasis off-evidence: {', '.join(misses[:3])}",
        cls="craft",
    )


# ---------------------------------------------------------------------------
# The per-type check matrix (verify 节点的纯函数半边): plain dicts in,
# CheckResults out — the node (pipeline/verify.py) adapts ORM rows into these
# item shapes. Set-level checks (count) attach to the FIRST item only.
# ---------------------------------------------------------------------------


def run_checks(
    for_type: str, items: list[dict[str, Any]], ctx: dict[str, Any]
) -> list[list[CheckResult]]:
    """Run the type's deterministic checklist over one executor's outputs.

    ``ctx``: ``source_texts`` (asset texts), ``target_language``, ``avoid``
    (persona avoid words), ``expected_count`` (storyboard slot count).
    Item shapes per type — clips: ``spec`` / ``source_text`` / ``span_words``
    / ``hint_times`` / ``anchors_by_url``; quotes: ``quotes``; post/article:
    ``text``; carousel: ``slides``.
    """
    results: list[list[CheckResult]] = []
    for item in items:
        checks: list[CheckResult] = []
        if for_type == "clips":
            spec = item.get("spec") or {}
            checks.append(
                span_fidelity(item.get("source_text") or "", item.get("span_words") or [])
            )
            checks.append(shot_dwells(spec))
            checks.append(caption_sync(spec))
            checks.append(face_safe_area(spec, item.get("anchors_by_url") or {}))
            checks.append(emphasis_alignment(spec, item.get("hint_times") or []))
        elif for_type == "quotes":
            for q in item.get("quotes") or []:
                checks.append(quote_verbatim(q.get("quote") or "", ctx["source_texts"]))
        elif for_type in ("post", "article"):
            text = item.get("text") or ""
            checks.append(language_match(text, ctx["target_language"]))
            checks.append(avoid_words(text, ctx.get("avoid")))
            checks.append(length_in_bounds(text, for_type))
        elif for_type == "carousel":
            slides = item.get("slides") or []
            body = "\n".join(f"{s.get('title', '')} {s.get('body', '')}" for s in slides)
            checks.append(language_match(body, ctx["target_language"]))
            checks.append(avoid_words(body, ctx.get("avoid")))
            checks.append(slide_count(len(slides), ctx.get("expected_count")))
        results.append(checks)
    if for_type in ("clips", "quotes") and results:
        actual = (
            len(items)
            if for_type == "clips"
            else sum(len(i.get("quotes") or []) for i in items)
        )
        results[0].append(count_match(actual, ctx.get("expected_count")))
    return results


def failed_checks(checks: list[CheckResult]) -> list[CheckResult]:
    """The bounce-worthy subset: failures only — skipped is never a failure,
    and judge-class verdicts never gate (advisory until §2.7 calibration)."""
    return [c for c in checks if c.ok is False and c.cls != "judge"]
