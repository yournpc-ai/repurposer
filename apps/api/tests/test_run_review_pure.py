"""Pure tests for run_review — the closing audit's deterministic core
(iter-3 S5, ADR-088 §8 R21 / N-58; contract §4 S5).

No DB / no LLM / no HTTP: the module is a pure function seat, so the whole
spectrum gates here — extraction (``landed_fact``), the promise derivation
(``_promised_from_scope`` via ``compute_run_review``), the gap adjudication
(family presence / clip shortfall / track promises), and the bounded
prompt-feed rendering (caps are structural).

Spend is never a closing-beat fact (2026-09-24 用户拍板 — Claude/Codex
parity): the review carries no charge fact and no over-quote gap, so nothing
downstream can narrate cost.
"""

from app.pipeline.run_review import (
    LandedFact,
    RunReview,
    compute_run_review,
    landed_fact,
    review_fact_lines,
)


class _OutputStub:
    """An Output row stand-in — landed_fact reads attributes only."""

    def __init__(
        self,
        type_: str,
        *,
        language: str | None = None,
        payload: dict | None = None,
        source_ref: dict | None = None,
        render_spec: dict | None = None,
        quality: dict | None = None,
    ) -> None:
        self.type = type_
        self.language = language
        self.payload = payload or {}
        self.source_ref = source_ref or {}
        self.render_spec = render_spec or {}
        self.quality = quality


def _clip(**kw) -> LandedFact:
    return landed_fact(_OutputStub("clip", **kw))


# ---- extraction (landed_fact) -------------------------------------------------


class TestLandedFact:
    def test_clip_full_spec(self) -> None:
        f = _clip(
            language="fr",
            payload={"duration": 30},
            source_ref={"start_seconds": 12.0, "end_seconds": 42.5},
            render_spec={
                "caption_enabled": True,
                "caption_track": [{"text": "hi"}],
                "translation_track": [{"text": "salut"}],
                "dub": {"voice_id": "v"},
            },
            quality={"status": "passed"},
        )
        assert f.output_type == "clip"
        assert f.language == "fr"
        assert f.duration_s == 30
        assert f.cut_range_s == (12.0, 42.5)
        assert f.has_captions and f.has_translation and f.dubbed
        assert f.quality == "passed"

    def test_clip_bare_spec(self) -> None:
        f = _clip(render_spec={"caption_track": []})
        assert f.has_captions is False
        assert f.has_translation is False
        assert f.dubbed is False
        assert f.cut_range_s is None and f.duration_s is None
        assert f.quality is None

    def test_caption_disabled_reads_no_captions(self) -> None:
        f = _clip(
            render_spec={"caption_enabled": False, "caption_track": [{"text": "x"}]}
        )
        assert f.has_captions is False

    def test_writer_has_no_track_fields(self) -> None:
        f = landed_fact(_OutputStub("post", language="en", payload={"body": "…"}))
        assert f.output_type == "post"
        assert f.has_captions is None and f.has_translation is None
        assert f.dubbed is None and f.cut_range_s is None


# ---- the promise derivation + gap adjudication -----------------------------------


def _scope(*tasks: dict) -> dict:
    return {
        "confirmation_id": "c",
        "confirmed_at": "t",
        "confirmed_via": "dock_pill",
        "plans": [],
        "compiled_scope": list(tasks),
        "quote": {"total": [100, 200], "per_task": []},
    }


class TestComputeRunReview:
    def test_full_delivery_has_no_gaps(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope(
                {"tool": "cut_segments", "params": {"segments": [{"start": 0, "end": 30}]}},
                {"tool": "write_post", "params": {"language": "fr"}},
            ),
            landed=[
                _clip(language=None, payload={"duration": 30}),
                landed_fact(_OutputStub("post", language="fr")),
            ],
        )
        assert review.has_snapshot
        assert review.promised_clip_count == 1
        assert set(review.promised_types) == {"clip", "post:fr"}
        assert review.gaps == ()

    def test_missing_writer_family_is_a_gap(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "write_article", "params": {"language": "de"}}),
            landed=[],
        )
        assert "missing_output:article:de" in review.gaps

    def test_language_unnamed_promise_matches_any_language(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "write_post", "params": {}}),
            landed=[landed_fact(_OutputStub("post", language="zh"))],
        )
        assert review.gaps == ()

    def test_clip_shortfall_is_a_gap(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope(
                {"tool": "cut_segments", "params": {"segments": [{"start": 0, "end": 1}, {"start": 2, "end": 3}, {"start": 4, "end": 5}]}},
            ),
            landed=[_clip(payload={"duration": 1})],
        )
        assert "clip_shortfall:1/3" in review.gaps

    def test_legacy_select_clips_counts_too(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "select_clips", "params": {"count": 2}}),
            landed=[_clip(), _clip()],
        )
        assert review.promised_clip_count == 2
        assert not any(g.startswith("clip_shortfall") for g in review.gaps)

    def test_caption_version_and_dub_promises(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope(
                {"tool": "cut_segments", "params": {"segments": [{"start": 0, "end": 1}]}},
                {"tool": "translate_clip", "params": {"target_language": "fr"}},
                {"tool": "dub_clip", "params": {"target_language": "fr"}},
            ),
            landed=[_clip(render_spec={"caption_track": [{"text": "x"}]})],
        )
        assert "missing_caption_version:fr" in review.gaps
        assert "missing_dub" in review.gaps
        # A landed clip carrying both tracks closes both gaps.
        review2 = compute_run_review(
            confirmed_scope=_scope(
                {"tool": "cut_segments", "params": {"segments": [{"start": 0, "end": 1}]}},
                {"tool": "translate_clip", "params": {"target_language": "fr"}},
                {"tool": "dub_clip", "params": {"target_language": "fr"}},
            ),
            landed=[
                _clip(
                    render_spec={
                        "caption_track": [{"text": "x"}],
                        "translation_track": [{"text": "y"}],
                        "dub": {"voice_id": "v"},
                    }
                )
            ],
        )
        assert review2.gaps == ()

    def test_needs_human_collects_the_flagged_types(self) -> None:
        review = compute_run_review(
            confirmed_scope=None,
            landed=[
                _clip(quality={"status": "needs_human"}),
                landed_fact(_OutputStub("post", quality={"status": "needs_human"})),
                landed_fact(_OutputStub("article", quality={"status": "passed"})),
            ],
        )
        assert review.needs_human == ("clip", "post")

    def test_no_snapshot_is_read_tolerated(self) -> None:
        """Legacy run (no confirmed scope): the promise side stays EMPTY by
        design — gaps require a promise, so none can be named."""
        review = compute_run_review(
            confirmed_scope=None,
            landed=[_clip()],
        )
        assert not review.has_snapshot
        assert review.promised_types == ()
        assert review.gaps == ()


# ---- the bounded prompt-feed rendering ----------------------------------------------


class TestReviewFactLines:
    def test_lines_carry_the_facts(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope(
                {"tool": "cut_segments", "params": {"segments": [{"start": 12, "end": 42}]}},
                {"tool": "write_post", "params": {"language": "fr"}},
            ),
            landed=[
                _clip(
                    payload={"duration": 30},
                    source_ref={"start_seconds": 12.0, "end_seconds": 42.0},
                    render_spec={"caption_track": [{"text": "x"}]},
                    quality={"status": "passed"},
                ),
                landed_fact(_OutputStub("post", language="fr")),
            ],
        )
        lines = review_fact_lines(review)
        assert any(line.startswith("promised: clip, post:fr") for line in lines)
        assert any(
            "landed clip" in line and "duration=30s" in line and "cut=12.0–42.0s" in line
            and "captions=yes" in line and "verify=passed" in line
            for line in lines
        )
        assert any("landed post" in line and "lang=fr" in line for line in lines)
        assert not any(line.startswith("GAP") for line in lines)

    def test_gaps_render_as_stable_keys(self) -> None:
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "write_quotes", "params": {}}),
            landed=[],
        )
        lines = review_fact_lines(review)
        assert "GAP missing_output:quotes" in lines

    def test_caps_are_structural(self) -> None:
        landed = [_clip(payload={"duration": i}) for i in range(20)]
        review = RunReview(has_snapshot=False, landed=tuple(landed))
        lines = review_fact_lines(review)
        landed_lines = [line for line in lines if line.startswith("- landed")]
        assert len(landed_lines) == 12
        assert any("(8 more landed outputs)" in line for line in lines)

    def test_lines_never_speak_spend(self) -> None:
        """The 2026-09-24 ruling's structural pin: no matter what the scope's
        quote says, the prompt-feed block carries no charge line — the closing
        speech cannot narrate what it never sees."""
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "write_post", "params": {}}),
            landed=[landed_fact(_OutputStub("post"))],
        )
        lines = review_fact_lines(review)
        assert not any("charge" in line or "credit" in line for line in lines)
