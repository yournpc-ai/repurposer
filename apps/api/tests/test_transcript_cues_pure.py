"""Pure tests for the transcript cue law (app/tools/clips/transcript.py).

Gated here:

- **Byte stability of the extraction**: ``build_anchored_transcript`` was
  re-implemented on top of ``group_cues`` (the structured half of the ONE
  grouping law) — the prompt surface must not have moved a byte. The
  pre-extraction implementation is inlined below as the reference oracle
  (zero-hypothesis discipline: re-prove, never trust the refactor).
- **search_cues**: deterministic keyword retrieval — case-folded,
  CJK-safe, distinct-term scoring, timeline tie-break, honest total.
- **words_in_range / speaker_at**: the evidence-validation and segment-read
  primitives (overlap semantics, no silent invention).
"""

from app.tools.clips.transcript import (
    build_anchored_transcript,
    group_cues,
    search_cues,
    speaker_at,
    words_in_range,
)

# ---- the pre-extraction oracle (copy of the old body, verbatim semantics) ----

_LEGACY_SENTENCE_END = frozenset(".?!。！？;；")
_LEGACY_PAUSE_BREAK_S = 0.8
_LEGACY_LINE_WORD_CAP = 25


def _legacy_anchored(words, max_words=12000):
    texts: list[str] = []
    for w in words[:max_words]:
        text = str(w.get("word") or "").strip()
        if text:
            texts.append(text)
    if not texts:
        return ""
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
            len(line_words) >= _LEGACY_LINE_WORD_CAP
            or text[-1] in _LEGACY_SENTENCE_END
            or (
                nxt is not None
                and float(nxt.get("start") or 0.0) - line_end > _LEGACY_PAUSE_BREAK_S
            )
        ):
            _flush()
            line_words = []
    _flush()

    if len(words) > max_words:
        cutoff_min = float(timed[-1].get("end") or 0.0) / 60
        lines.append(f"[truncated: timeline beyond {cutoff_min:.0f}min not shown]")
    return "\n".join(lines)


def _words(*specs) -> list[dict]:
    """Compact word stream: (text, start, end) triples."""
    return [{"word": t, "start": s, "end": e} for t, s, e in specs]


class TestAnchoredByteStability:
    def test_english_sentence_breaks(self) -> None:
        words = _words(
            ("Hello", 0.0, 0.4),
            ("there.", 0.5, 0.9),
            ("Pricing", 1.0, 1.5),
            ("is", 1.6, 1.8),
            ("hard", 1.9, 2.3),
        )
        assert build_anchored_transcript(words) == _legacy_anchored(words)

    def test_pause_break_and_whitespace_words(self) -> None:
        words = _words(
            ("one", 0.0, 0.3),
            ("  ", 0.3, 0.4),  # whitespace-only — filtered by both
            ("two", 0.4, 0.7),
            ("three", 3.0, 3.5),  # pause > 0.8s breaks the line
        )
        assert build_anchored_transcript(words) == _legacy_anchored(words)

    def test_word_cap_break(self) -> None:
        words = _words(*[(f"w{i}", float(i), float(i) + 0.4) for i in range(30)])
        assert build_anchored_transcript(words) == _legacy_anchored(words)

    def test_cjk_punctuation_breaks(self) -> None:
        words = _words(
            ("定价", 0.0, 0.4),
            ("很", 0.4, 0.6),
            ("难。", 0.6, 1.0),
            ("募资", 1.1, 1.5),
        )
        assert build_anchored_transcript(words) == _legacy_anchored(words)

    def test_truncation_marker(self) -> None:
        words = _words(*[(f"w{i}", float(i * 2), float(i * 2) + 1.0) for i in range(20)])
        assert build_anchored_transcript(words, max_words=10) == _legacy_anchored(
            words, max_words=10
        )

    def test_empty_and_whitespace_only(self) -> None:
        assert build_anchored_transcript([]) == ""
        assert build_anchored_transcript([{"word": "  ", "start": 0, "end": 1}]) == ""

    def test_group_cues_structure_matches_lines(self) -> None:
        words = _words(
            ("Hello", 0.0, 0.4),
            ("there.", 0.5, 0.9),
            ("Pricing", 1.0, 1.5),
        )
        cues, truncated = group_cues(words)
        assert truncated is False
        assert cues == [
            {"start": 0.0, "end": 0.9, "text": "Hello there."},
            {"start": 1.0, "end": 1.5, "text": "Pricing"},
        ]


class TestSearchCues:
    def _cues(self) -> list[dict]:
        return [
            {"start": 0.0, "end": 4.0, "text": "Welcome to the webinar today."},
            {"start": 4.2, "end": 9.0, "text": "Pricing is hard for founders."},
            {"start": 9.5, "end": 14.0, "text": "Pricing tiers vs pricing value."},
            {"start": 14.5, "end": 20.0, "text": "Fundraising closes the talk."},
        ]

    def test_casefolded_single_term(self) -> None:
        matches, total = search_cues(self._cues(), "PRICING")
        assert total == 2
        assert [m["start"] for m in matches] == [4.2, 9.5]
        assert all("pricing" in m["hits"] for m in matches)

    def test_distinct_term_scoring_and_timeline_tiebreak(self) -> None:
        matches, _ = search_cues(self._cues(), "pricing value tiers")
        # cue 2 hits all three terms, cue 1 hits one — score wins over order
        assert matches[0]["start"] == 9.5
        assert matches[0]["hits"] == ["pricing", "value", "tiers"]

    def test_cjk_substring(self) -> None:
        cues = [
            {"start": 0.0, "end": 3.0, "text": "我们今天聊定价策略"},
            {"start": 3.5, "end": 6.0, "text": "然后讲募资"},
        ]
        matches, total = search_cues(cues, "定价")
        assert total == 1
        assert matches[0]["text"] == "我们今天聊定价策略"

    def test_limit_and_honest_total(self) -> None:
        cues = [{"start": float(i), "end": float(i) + 1, "text": "pricing note"} for i in range(30)]
        matches, total = search_cues(cues, "pricing", limit=5)
        assert len(matches) == 5
        assert total == 30

    def test_blank_query_and_no_hits(self) -> None:
        assert search_cues(self._cues(), "   ") == ([], 0)
        assert search_cues(self._cues(), "quantum") == ([], 0)


class TestWordsInRange:
    def test_overlap_semantics(self) -> None:
        words = _words(
            ("a", 0.0, 1.0),
            ("b", 1.2, 2.0),
            ("c", 2.5, 3.0),
            ("d", 3.5, 4.0),
        )
        # range touches a (boundary), covers b, clips c's start, misses d
        assert words_in_range(words, 1.0, 2.5) == "a b c"

    def test_empty_range_and_gaps(self) -> None:
        words = _words(("a", 0.0, 1.0))
        assert words_in_range(words, 5.0, 6.0) == ""
        assert words_in_range([{"word": " ", "start": 0.0, "end": 1.0}], 0.0, 1.0) == ""


class TestSpeakerAt:
    def test_max_overlap_turn_wins(self) -> None:
        smap = {
            "turns": [
                {"start": 0.0, "end": 5.0, "speaker": "left"},
                {"start": 5.0, "end": 12.0, "speaker": "right"},
            ]
        }
        assert speaker_at(smap, 4.0, 8.0) == "right"  # 4s vs 1s overlap
        assert speaker_at(smap, 0.0, 4.0) == "left"

    def test_no_map_no_overlap(self) -> None:
        assert speaker_at(None, 0.0, 1.0) is None
        assert speaker_at({"turns": []}, 0.0, 1.0) is None
        assert speaker_at({"turns": [{"start": 9.0, "end": 10.0, "speaker": "x"}]}, 0.0, 1.0) is None
