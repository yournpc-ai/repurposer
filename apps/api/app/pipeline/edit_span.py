"""quote→range resolver (ADR-090, E3 — the edit face's deterministic span service).

The LLM never writes execution facts (冻结条 2): a range request arrives as
QUOTE TEXT only, and resolving it to seconds is code's job. ``locate_span``
(production face) is best-effort and never refuses; the edit face is the
opposite posture — a confidence spectrum with a domain-refusal loop:

    numeric (the server already knows the card's displayed range)
      > exact marker match (the quote's full token sequence, one occurrence)
      > unique tolerant match (prefix/suffix probes or CJK substring, once)
      > ambiguous / not found = REFUSE with an answerable form
        (「这句在片里出现了两次，说第几次」/「没找到这句，把原话贴我」 —
        the chat layer composes the line, this module returns the verdict).

Everything here is pure: cues in (the clip spec's caption_track rows as
dicts), a ResolvedSpan or a SpanRefusal out. Never guesses, never raises.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.pipeline.clip_spec import _norm

_CJK_RE = re.compile(r"[一-鿿㐀-䶿]")


@dataclass(frozen=True)
class ResolvedSpan:
    start: float
    end: float
    tier: str  # "numeric" | "exact" | "unique"


@dataclass(frozen=True)
class SpanRefusal:
    reason: str  # "ambiguous" | "not_found"
    occurrences: int = 0


def _cue_start(cue: dict[str, Any]) -> float:
    return float(cue.get("start") or 0.0)


def _cue_end(cue: dict[str, Any]) -> float:
    return float(cue.get("end") or 0.0)


def _snap_numeric(cues: list[dict[str, Any]], numeric: tuple[float, float]) -> ResolvedSpan:
    """Snap a caller-known range to cue boundaries with COVER semantics (a
    cue overlapping the range belongs to it — the remove_range posture).
    No cues = nothing to snap to; the raw range stands."""
    s, e = float(numeric[0]), float(numeric[1])
    if not cues:
        return ResolvedSpan(s, max(s, e), "numeric")
    start_idx = next(
        (i for i, c in enumerate(cues) if _cue_end(c) > s), len(cues) - 1
    )
    end_idx = next(
        (i for i in range(len(cues) - 1, -1, -1) if _cue_start(cues[i]) < e), 0
    )
    if end_idx < start_idx:
        end_idx = start_idx
    return ResolvedSpan(_cue_start(cues[start_idx]), _cue_end(cues[end_idx]), "numeric")


def _unique_probe(
    flat: list[tuple[str, int]], tokens: list[str], want: str
) -> int | None | str:
    """Progressively shorter probes (locate_span's tolerance, adjudicated):
    the first probe length that hits decides — one hit = the index, several
    = AMBIGUOUS, none at any length = None."""
    for size in range(min(len(tokens), 6), 0, -1):
        probe = tokens[:size] if want == "start" else tokens[-size:]
        hits: list[int] = []
        for i in range(0, len(flat) - size + 1):
            if [t for t, _ in flat[i : i + size]] == probe:
                hits.append(i)
        if len(hits) == 1:
            i = hits[0]
            return i if want == "start" else i + size - 1
        if len(hits) > 1:
            return "ambiguous"
    return None


def _resolve_tokens(cues: list[dict[str, Any]], tokens: list[str]) -> ResolvedSpan | SpanRefusal:
    flat: list[tuple[str, int]] = []  # (token, cue_idx)
    for idx, cue in enumerate(cues):
        for t in _norm(str(cue.get("text") or "")):
            flat.append((t, idx))
    if not flat:
        return SpanRefusal("not_found")

    n = len(tokens)
    hits = [
        i
        for i in range(len(flat) - n + 1)
        if [t for t, _ in flat[i : i + n]] == tokens
    ]
    if len(hits) == 1:
        i = hits[0]
        return ResolvedSpan(
            _cue_start(cues[flat[i][1]]), _cue_end(cues[flat[i + n - 1][1]]), "exact"
        )
    if len(hits) > 1:
        return SpanRefusal("ambiguous", len(hits))

    start_hit = _unique_probe(flat, tokens, "start")
    if start_hit == "ambiguous":
        return SpanRefusal("ambiguous", 2)
    end_hit = _unique_probe(flat, tokens, "end")
    if end_hit == "ambiguous":
        return SpanRefusal("ambiguous", 2)
    if start_hit is None or end_hit is None or end_hit < start_hit:
        return SpanRefusal("not_found")
    return ResolvedSpan(
        _cue_start(cues[flat[start_hit][1]]),
        _cue_end(cues[flat[end_hit][1]]),
        "unique",
    )


def _resolve_substring(cues: list[dict[str, Any]], q: str) -> ResolvedSpan | SpanRefusal:
    """CJK path: no whitespace tokenization — the normalized quote is one
    character run searched over the concatenated cue texts, then mapped back
    to cue indices through per-cue char offsets."""
    parts = ["".join(_norm(str(cue.get("text") or ""))) for cue in cues]
    concat = "".join(parts)
    if not concat or not q:
        return SpanRefusal("not_found")
    hits: list[int] = []
    pos = 0
    while True:
        i = concat.find(q, pos)
        if i < 0:
            break
        hits.append(i)
        pos = i + 1  # overlapping occurrences count twice — 多义是真多义
    if not hits:
        return SpanRefusal("not_found")
    if len(hits) > 1:
        return SpanRefusal("ambiguous", len(hits))

    i = hits[0]
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for p in parts:
        offsets.append((cursor, cursor + len(p)))
        cursor += len(p)
    first = next(idx for idx, (_a, b) in enumerate(offsets) if b > i)
    last = next(
        idx for idx in range(len(offsets) - 1, -1, -1) if offsets[idx][0] < i + len(q)
    )
    tier = "exact" if first == last and q == parts[first] else "unique"
    return ResolvedSpan(_cue_start(cues[first]), _cue_end(cues[last]), tier)


def resolve_quote_span(
    cues: list[dict[str, Any]],
    quote: str | None = None,
    *,
    numeric: tuple[float, float] | None = None,
) -> ResolvedSpan | SpanRefusal:
    """The edit face's span adjudication (E3 置信谱). ``numeric`` = the
    server-known range (the product card's displayed interval — the LLM
    never writes it); ``quote`` = the user's quoted words. Empty input is a
    refusal, never a guess."""
    if numeric is not None:
        return _snap_numeric(cues, numeric)
    tokens = _norm(quote or "")
    if not cues or not tokens:
        return SpanRefusal("not_found")
    if any(_CJK_RE.search(t) for t in tokens):
        return _resolve_substring(cues, "".join(tokens))
    return _resolve_tokens(cues, tokens)
