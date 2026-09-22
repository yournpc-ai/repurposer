"""Transcript shaping helpers (pure functions).

``build_anchored_transcript`` replaces the old ``source_words[:400]`` JSON
blob in the clip agent prompt: the full talk as timestamped cue lines the
LLM can copy coarse timestamps from (code snaps them to word boundaries —
see ``app.pipeline.clip_spec.locate_span``).

The cue-grouping law lives in ``group_cues`` — ``build_anchored_transcript``
is its string formatting half (byte-stable since the extraction; the prompt
surface never moved). The exploration family (ADR-088) consumes the same
law structurally: ``search_cues`` is the discovery read's deterministic
retrieval core, ``words_in_range`` / ``speaker_at`` feed the evidence
validation and the segment reads.
"""

from typing import Any, TypedDict

# Cue-break triggers, whichever fires first: sentence-ending punctuation,
# an inter-word pause longer than this, or a line reaching the word cap.
_SENTENCE_END = frozenset(".?!。！？;；")
_PAUSE_BREAK_S = 0.8
_LINE_WORD_CAP = 25


class Cue(TypedDict):
    """One cue: a line's worth of speech with its timeline anchor."""

    start: float
    end: float
    text: str


def _timed_words(words: list[dict[str, Any]], max_words: int) -> list[dict[str, Any]]:
    """The capped, non-empty word stream (the one both cue consumers share)."""
    return [w for w in words[:max_words] if str(w.get("word") or "").strip()]


def group_cues(words: list[dict[str, Any]], max_words: int = 12000) -> tuple[list[Cue], bool]:
    """Group word-level timestamps into cues (the ONE grouping law).

    Args:
        words: ASR output as ``{"word", "start", "end"}`` dicts (seconds).
        max_words: Hard cap on covered words (~90 min of speech).

    Returns:
        ``(cues, truncated)`` — cues in timeline order; ``truncated`` says
        words beyond the cap exist (the caller renders the honest marker —
        never a silent window).
    """
    timed = _timed_words(words, max_words)
    cues: list[Cue] = []
    line_words: list[str] = []
    line_start = 0.0
    line_end = 0.0

    def _flush() -> None:
        if line_words:
            cues.append(
                Cue(start=line_start, end=line_end, text=" ".join(line_words))
            )

    for i, w in enumerate(timed):
        text = str(w.get("word") or "").strip()
        if not line_words:
            line_start = float(w.get("start") or 0.0)
        line_words.append(text)
        line_end = float(w.get("end") or line_start)
        nxt = timed[i + 1] if i + 1 < len(timed) else None
        if (
            len(line_words) >= _LINE_WORD_CAP
            or text[-1] in _SENTENCE_END
            or (
                nxt is not None
                and float(nxt.get("start") or 0.0) - line_end > _PAUSE_BREAK_S
            )
        ):
            _flush()
            line_words = []
    _flush()

    return cues, len(words) > max_words


def build_anchored_transcript(
    words: list[dict[str, Any]], max_words: int = 12000
) -> str:
    """Group word-level timestamps into cue lines with ``[start-end]`` anchors.

    Args:
        words: ASR output as ``{"word", "start", "end"}`` dicts (seconds).
        max_words: Hard cap on covered words (~90 min of speech). Overflow is
            dropped and the final line carries an explicit truncation marker —
            never a silent window.

    Returns:
        Lines of ``[12.3-18.7] And that is why the model had to change``,
        one per cue; empty string when there are no words.
    """
    cues, truncated = group_cues(words, max_words)
    lines = [f"[{c['start']:.1f}-{c['end']:.1f}] {c['text']}" for c in cues]
    if truncated:
        cutoff_min = (cues[-1]["end"] if cues else 0.0) / 60
        lines.append(f"[truncated: timeline beyond {cutoff_min:.0f}min not shown]")
    return "\n".join(lines)


def search_cues(
    cues: list[Cue], query: str, *, limit: int = 20
) -> tuple[list[dict[str, Any]], int]:
    """Keyword retrieval over cues — the discovery read's deterministic core.

    Terms = the query's whitespace-split tokens, case-folded; a cue scores
    by distinct-term substring hits (CJK-safe — no segmentation needed).
    Matches sort by hit count desc, then timeline asc. Returns
    ``(matches, total)`` — matches capped at ``limit`` (each carries
    ``hits`` = the matched terms), total = the full hit count so the caller
    can render the honest omission note.
    """
    terms = [t for t in query.casefold().split() if t]
    if not terms:
        return [], 0
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for idx, cue in enumerate(cues):
        hay = cue["text"].casefold()
        hits = [t for t in terms if t in hay]
        if hits:
            scored.append(
                (
                    -len(hits),
                    idx,
                    {
                        "start": cue["start"],
                        "end": cue["end"],
                        "text": cue["text"],
                        "hits": hits,
                    },
                )
            )
    scored.sort(key=lambda s: (s[0], s[1]))
    total = len(scored)
    return [m for _, _, m in scored[:limit]], total


def words_in_range(words: list[dict[str, Any]], start: float, end: float) -> str:
    """The speech inside ``[start, end]`` — every word whose interval
    overlaps the range, joined like the cue text (single spaces)."""
    picked: list[str] = []
    for w in words:
        text = str(w.get("word") or "").strip()
        if not text:
            continue
        ws = float(w.get("start") or 0.0)
        we = float(w.get("end") or ws)
        if we >= start and ws <= end:
            picked.append(text)
    return " ".join(picked)


def speaker_at(
    speaker_map: dict[str, Any] | None, start: float, end: float
) -> str | None:
    """The dominant speaker of ``[start, end]`` — the turn with the maximum
    temporal overlap; ``None`` when there is no speaker_map or no overlap
    (audio assets carry none — the signal is visual, ADR-045 D4)."""
    turns = (speaker_map or {}).get("turns") or []
    best: tuple[float, str] | None = None
    for turn in turns:
        ts = float(turn.get("start") or 0.0)
        te = float(turn.get("end") or ts)
        overlap = min(end, te) - max(start, ts)
        if overlap > 0 and (best is None or overlap > best[0]):
            best = (overlap, str(turn.get("speaker") or ""))
    return best[1] if best and best[1] else None
