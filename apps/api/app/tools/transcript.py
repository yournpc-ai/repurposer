"""Transcript shaping helpers (pure functions).

``build_anchored_transcript`` replaces the old ``source_words[:400]`` JSON
blob in the clip agent prompt: the full talk as timestamped cue lines the
LLM can copy coarse timestamps from (code snaps them to word boundaries —
see ``app.pipeline.clip_spec.locate_span``).
"""

from typing import Any

# Cue-break triggers, whichever fires first: sentence-ending punctuation,
# an inter-word pause longer than this, or a line reaching the word cap.
_SENTENCE_END = frozenset(".?!。！？;；")
_PAUSE_BREAK_S = 0.8
_LINE_WORD_CAP = 25


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
    texts: list[str] = []
    for w in words[:max_words]:
        text = str(w.get("word") or "").strip()
        if text:
            texts.append(text)
    if not texts:
        return ""

    # Keep the original word dicts in step with the non-empty texts.
    timed = [w for w in words[:max_words] if str(w.get("word") or "").strip()]

    lines: list[str] = []
    line_words: list[str] = []
    line_start = 0.0
    line_end = 0.0

    def _flush() -> None:
        if line_words:
            lines.append(f"[{line_start:.1f}-{line_end:.1f}] {' '.join(line_words)}")

    for i, text in enumerate(texts):
        if not line_words:
            line_start = float(timed[i].get("start") or 0.0)
        line_words.append(text)
        line_end = float(timed[i].get("end") or line_start)
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

    if len(words) > max_words:
        cutoff_min = float(timed[-1].get("end") or 0.0) / 60
        lines.append(f"[truncated: timeline beyond {cutoff_min:.0f}min not shown]")

    return "\n".join(lines)
