"""Pure tests for the quote→range resolver (ADR-090 E3 — S2 confidence spectrum).

No DB, no LLM, no HTTP. The matrix locks the four tiers and the refusal
loop: numeric > exact > unique-tolerant > ambiguous/not-found refuse, plus
the CJK substring path and the boundary edges (empty cues / empty quote /
probe collisions).
"""

from app.pipeline.edit_span import (
    ResolvedSpan,
    SpanRefusal,
    resolve_quote_span,
)


def _cues(*rows: tuple[float, float, str]) -> list[dict]:
    return [{"start": s, "end": e, "text": t} for s, e, t in rows]


EN = _cues(
    (0.0, 0.5, "Welcome"),
    (0.5, 1.2, "back everyone"),
    (1.2, 2.0, "today"),
    (2.0, 3.4, "we discuss pricing"),
    (3.4, 4.2, "and the roadmap"),
    (4.2, 5.0, "let's begin"),
)


class TestNumericTier:
    def test_snaps_with_cover_semantics(self):
        r = resolve_quote_span(EN, numeric=(0.7, 3.0))
        assert r == ResolvedSpan(0.5, 3.4, "numeric")  # overlapping cues covered

    def test_empty_cues_raw_range_stands(self):
        r = resolve_quote_span([], numeric=(1.0, 2.5))
        assert r == ResolvedSpan(1.0, 2.5, "numeric")

    def test_inverted_range_clamps(self):
        r = resolve_quote_span([], numeric=(3.0, 1.0))
        assert r == ResolvedSpan(3.0, 3.0, "numeric")


class TestExactTier:
    def test_single_occurrence(self):
        r = resolve_quote_span(EN, "we discuss pricing")
        assert r == ResolvedSpan(2.0, 3.4, "exact")

    def test_multi_cue_phrase(self):
        r = resolve_quote_span(EN, "welcome back everyone")
        assert r == ResolvedSpan(0.0, 1.2, "exact")

    def test_punctuation_and_case_normalized(self):
        r = resolve_quote_span(EN, "We, discuss... pricing!")
        assert r == ResolvedSpan(2.0, 3.4, "exact")

    def test_two_occurrences_refuse_ambiguous(self):
        cues = EN + _cues((6.0, 7.0, "we discuss pricing"))
        r = resolve_quote_span(cues, "we discuss pricing")
        assert isinstance(r, SpanRefusal) and r.reason == "ambiguous"
        assert r.occurrences == 2


class TestUniqueTolerantTier:
    def test_light_rewording_resolves(self):
        # "discuss the pricing" — not contiguous in "we discuss pricing";
        # prefix/suffix probes each land exactly once → tolerant tier.
        r = resolve_quote_span(EN, "discuss the pricing")
        assert isinstance(r, ResolvedSpan) and r.tier == "unique"
        assert (r.start, r.end) == (2.0, 3.4)

    def test_unique_start_and_end_span(self):
        # "welcome ... today" — no contiguous match; prefix/suffix probes
        # each unique → the span between them.
        r = resolve_quote_span(EN, "welcome everyone today")
        assert isinstance(r, ResolvedSpan) and r.tier == "unique"
        assert (r.start, r.end) == (0.0, 2.0)

    def test_ambiguous_probe_refuses(self):
        cues = _cues(
            (0.0, 1.0, "the end is near"),
            (2.0, 3.0, "the end is here"),
        )
        r = resolve_quote_span(cues, "the end is coming")
        assert isinstance(r, SpanRefusal) and r.reason == "ambiguous"

    def test_nothing_matches_refuses_not_found(self):
        r = resolve_quote_span(EN, "quarterly earnings report")
        assert isinstance(r, SpanRefusal) and r.reason == "not_found"


class TestCJKSubstringPath:
    ZH = _cues(
        (0.0, 1.5, "大家好欢迎来到本期节目"),
        (1.5, 3.0, "今天我们聊聊定价策略"),
        (3.0, 4.5, "还有明年的路线图"),
    )

    def test_whole_cue_is_exact(self):
        r = resolve_quote_span(self.ZH, "今天我们聊聊定价策略")
        assert r == ResolvedSpan(1.5, 3.0, "exact")

    def test_cross_cue_run_is_unique(self):
        r = resolve_quote_span(self.ZH, "定价策略还有明年")
        assert isinstance(r, ResolvedSpan) and r.tier == "unique"
        assert (r.start, r.end) == (1.5, 4.5)

    def test_repeated_run_refuses_ambiguous(self):
        cues = self.ZH + _cues((5.0, 6.0, "再谈定价策略"))
        r = resolve_quote_span(cues, "定价策略")
        assert isinstance(r, SpanRefusal) and r.reason == "ambiguous"
        assert r.occurrences == 2

    def test_miss_refuses_not_found(self):
        r = resolve_quote_span(self.ZH, "市场占有率")
        assert isinstance(r, SpanRefusal) and r.reason == "not_found"


class TestEdges:
    def test_empty_quote_refuses(self):
        r = resolve_quote_span(EN, "")
        assert isinstance(r, SpanRefusal) and r.reason == "not_found"

    def test_none_quote_refuses(self):
        r = resolve_quote_span(EN, None)
        assert isinstance(r, SpanRefusal) and r.reason == "not_found"

    def test_empty_cues_quote_refuses(self):
        r = resolve_quote_span([], "welcome back")
        assert isinstance(r, SpanRefusal) and r.reason == "not_found"

    def test_numeric_wins_over_quote(self):
        r = resolve_quote_span(EN, "we discuss pricing", numeric=(4.2, 5.0))
        assert r.tier == "numeric" and (r.start, r.end) == (4.2, 5.0)
