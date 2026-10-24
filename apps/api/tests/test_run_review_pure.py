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
    delivery_state,
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
        files: dict | None = None,
        render_status: str | None = None,
        quality: dict | None = None,
    ) -> None:
        self.type = type_
        self.language = language
        self.payload = payload or {}
        self.source_ref = source_ref or {}
        # render_spec 保持原样 (None 不塌缩成 {}) — 配乐三态要区分「记录
        # 缺失」与「有效 spec 无 music」, stub 必须先诚实保留缺失.
        self.render_spec = render_spec
        self.files = files or {}
        self.render_status = render_status
        self.quality = quality


def _clip(delivered: bool = True, **kw) -> LandedFact:
    """A clip fact; by default in the DELIVERED shape (ADR-096 §4 — render
    COMPLETED + the video file present), since the delivery tallies only
    count that shape. Pass ``delivered=False`` for the raw row (no render
    requested, no file)."""
    if delivered:
        kw.setdefault("render_status", "completed")
        kw.setdefault("files", {"video": "k.mp4"})
    return landed_fact(_OutputStub("clip", **kw))


def _film(delivered: bool = True, **kw) -> LandedFact:
    """A film fact — the same render contract as the clip family
    (``_RENDER_CONTRACTED``): delivered = render COMPLETED + the video file."""
    if delivered:
        kw.setdefault("render_status", "completed")
        kw.setdefault("files", {"video": "k.mp4"})
    return landed_fact(_OutputStub("film", **kw))


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

    def test_film_pinned_language_promises_the_pin(self) -> None:
        """launch_film rides the same :lang suffix law (2026-10-15 语言钉参):
        an English-pinned film that landed in Chinese is a proven gap."""
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "launch_film", "params": {"language": "en"}}),
            landed=[_film(language="en")],
        )
        assert review.gaps == ()
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "launch_film", "params": {"language": "en"}}),
            landed=[_film(language="zh")],
        )
        assert "missing_output:film:en" in review.gaps

    def test_film_unpinned_promises_no_language(self) -> None:
        """Unpinned = the storyboard declares it at run time — any landed
        language satisfies the promise."""
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "launch_film", "params": {}}),
            landed=[_film(language="zh")],
        )
        assert review.gaps == ()

    def test_film_undelivered_render_counts_as_missing(self) -> None:
        """The film rides the render contract: a row whose render never
        completed (or lost its file) never counts toward the promise."""
        review = compute_run_review(
            confirmed_scope=_scope({"tool": "launch_film", "params": {"language": "en"}}),
            landed=[_film(delivered=False, language="en")],
        )
        assert "missing_output:film:en" in review.gaps

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

    def test_payload_complete_but_file_missing_never_counts(self) -> None:
        """ADR-096 §4 (run completed ≠ artifact ready): a clip whose payload
        is complete but whose render never landed — NULL (no owner pended it),
        in flight, or a COMPLETED row with no video key — is excluded from
        the delivery tallies exactly like a render-FAILED row."""
        scope = _scope(
            {"tool": "cut_segments", "params": {"segments": [{"start": 0, "end": 1}]}},
        )
        for shape in (
            {"delivered": False},  # render_status NULL, no file
            {"render_status": "pending"},
            {"render_status": "rendering"},
            {"render_status": "completed", "files": {}},  # terminal contradiction
        ):
            review = compute_run_review(
                confirmed_scope=scope,
                landed=[_clip(**shape)],
            )
            assert "clip_shortfall:0/1" in review.gaps, shape
        # The delivered pair (COMPLETED + file) closes the same promise.
        review = compute_run_review(
            confirmed_scope=scope,
            landed=[_clip()],
        )
        assert review.gaps == ()

    def test_file_missing_output_uses_failed_branch_not_a_landed_line(self) -> None:
        """A file-missing render row has no product card or delivery audit;
        the fact block carries only the failed-delivery branch and its gap."""
        review = compute_run_review(
            confirmed_scope=None,
            landed=[_clip(delivered=False, payload={"duration": 30})],
        )
        lines = review_fact_lines(review)
        assert delivery_state(review) == "failed"
        assert lines[0] == "delivery=failed"
        assert "GAP output_not_ready:clip" in lines
        assert not any("landed clip" in line for line in lines)
        assert not any("render=NOT-READY" in line for line in lines)

    def test_render_failed_does_not_also_report_not_ready(self) -> None:
        review = compute_run_review(
            confirmed_scope=None,
            landed=[
                landed_fact(
                    _OutputStub(
                        "clip", render_status="failed", files={}
                    )
                )
            ],
        )
        lines = review_fact_lines(review)
        assert delivery_state(review) == "failed"
        assert lines[0] == "delivery=failed"
        assert "GAP render_failed:clip" in lines
        assert "GAP output_not_ready:clip" not in lines
        assert not any("landed clip" in line for line in lines)


class TestDeliveryState:
    def test_failed_film_has_no_delivery_or_consistency_audit(self) -> None:
        film = LandedFact(
            output_type="film",
            duration_s=88,
            render="failed",
            has_file=False,
            music_bed=True,
            film_check=("confirmed=v1 digest:match DRIFT", "drift:home.page"),
        )
        review = compute_run_review(confirmed_scope=None, landed=[film])
        lines = review_fact_lines(review)
        assert delivery_state(review) == "failed"
        assert "film_drift:film" not in review.gaps
        assert not any("landed film" in line or "drift:" in line for line in lines)
        assert not any("duration=88s" in line or "music=bed" in line for line in lines)

    def test_partial_delivery_shows_only_delivered_products_and_gaps(self) -> None:
        review = compute_run_review(
            confirmed_scope=None,
            landed=[
                landed_fact(_OutputStub("post", language="en")),
                _film(delivered=False, render_status="failed"),
            ],
        )
        lines = review_fact_lines(review)
        assert delivery_state(review) == "partial"
        assert lines[0] == "delivery=partial"
        assert any("landed post" in line for line in lines)
        assert not any("landed film" in line for line in lines)
        assert "GAP render_failed:film" in lines

    def test_empty_legacy_review_keeps_the_no_facts_fallback(self) -> None:
        review = RunReview(has_snapshot=False)
        assert delivery_state(review) == "unknown"
        assert review_fact_lines(review) == []


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


# ---------------------------------------------------------------------------
# film confirmed-vs-landed (ADR-139 sibling law — the d08af2af lesson: the
# closing beat once claimed a drift no fact supported; the check is
# deterministic, three-stated, and missing information NEVER reads as match)
# ---------------------------------------------------------------------------

from app.pipeline.run_review import film_delivery_check  # noqa: E402

_CONFIRMED = {
    "version": 3,
    "digest": "digest-v3",
    "board": {
        "scenes": [
            {"scene_id": "s1", "type": "words", "seconds": 4.0, "dark": False,
             "lines": ["你把专业讲清楚"]},
            {"scene_id": "s2", "type": "words", "seconds": 5.0, "dark": True,
             "lines": ["好内容值得持续被看见"]},
        ]
    },
    "params": {"aspect": "16:9", "music_mood": "off", "voiceover": False},
}


def _spec(**kw) -> dict:
    spec = {
        "fps": 30,
        "aspect": "16:9",
        "provenance": {"storyboard_digest": "digest-v3"},
        "scenes": [
            {"type": "words", "frames": 120, "dark": False,
             "lines": ["你把专业讲清楚"]},
            {"type": "words", "frames": 150, "dark": True,
             "lines": ["好内容值得持续被看见"]},
        ],
    }
    spec.update(kw)
    return spec


def test_film_check_match_when_the_landed_spec_proves_it() -> None:
    lines = film_delivery_check(_CONFIRMED, _spec(), {})
    assert lines == ("confirmed=v3 digest:match MATCH",)


def test_film_check_drift_names_the_changed_fields() -> None:
    spec = _spec()
    spec["scenes"][1]["lines"] = ["被改写的内容"]
    spec["aspect"] = "9:16"
    lines = film_delivery_check(_CONFIRMED, spec, {})
    assert lines[0] == "confirmed=v3 digest:match DRIFT"
    assert "drift:s2.lines" in lines
    assert any("aspect confirmed=16:9 landed=9:16" in l for l in lines)


def test_film_check_digest_mismatch_is_drift() -> None:
    spec = _spec(provenance={"storyboard_digest": "digest-v2"})
    lines = film_delivery_check(_CONFIRMED, spec, {})
    assert lines[0].endswith("DRIFT")
    assert any("content digest differs" in l for l in lines)


def test_film_check_ui_selector_resolution_is_not_drift() -> None:
    # page/shot are draft-time selectors. Baking resolves them to url/image;
    # their absence from the spec must not manufacture 2 drift fields per UI
    # scene when the storyboard digest is identical.
    confirmed = {
        "version": 1,
        "digest": "digest-ui",
        "board": {
            "scenes": [
                {
                    "scene_id": "home",
                    "type": "ui",
                    "seconds": 7.5,
                    "page": 0,
                    "shot": 0,
                    "frame": True,
                }
            ]
        },
        "params": {"aspect": "16:9", "music_mood": "off", "voiceover": False},
    }
    spec = {
        "fps": 30,
        "aspect": "16:9",
        "provenance": {"storyboard_digest": "digest-ui"},
        "scenes": [
            {
                "type": "ui",
                "frames": 225,
                "url": "www.zymix.ai",
                "image": "captures/home.png",
                "frame": True,
            }
        ],
    }
    assert film_delivery_check(confirmed, spec, {}) == (
        "confirmed=v1 digest:match MATCH",
    )


def test_film_check_missing_information_is_never_a_match() -> None:
    # No confirmed stamp → not-comparable (the fabrication guard's core).
    assert film_delivery_check(None, _spec(), {}) == (
        "not-comparable:no-confirmed-storyboard",
    )
    # Confirmed stamp but the landed row carries no spec scenes.
    assert film_delivery_check(_CONFIRMED, {"scenes": []}, {}) == (
        "not-comparable:no-landed-spec",
    )


def test_film_check_timing_leg_undershoot_only_with_snap_tolerance() -> None:
    # 4.0s @30fps = 120 frames; the beat snap's ±6-frame window is free.
    spec = _spec()
    spec["scenes"][0]["frames"] = 115
    assert film_delivery_check(_CONFIRMED, spec, {})[0].endswith("MATCH")
    spec["scenes"][0]["frames"] = 113  # beyond the tolerance → proven short
    lines = film_delivery_check(_CONFIRMED, spec, {})
    assert "drift:s1.frames" in lines


def test_film_check_unexplained_growth_is_unverified_never_match() -> None:
    # Over-tolerance growth is a legal allocator adjustment, but with no
    # flex record it is UNEXPLAINED — it narrows the verdict to the checked
    # scope and names the scene, never reads as verified-consistent.
    spec = _spec()
    spec["scenes"][0]["frames"] = 200
    lines = film_delivery_check(_CONFIRMED, spec, {})
    assert lines[0] == "confirmed=v3 digest:match MATCH-ON-CHECKED-SCOPE"
    assert any("unchecked:" in l and "timing(unverified growth)" in l for l in lines)
    assert any("timing-note:s1 frames 200 vs ~120" in l for l in lines)


def test_film_check_narration_flex_stands_the_timing_leg_down() -> None:
    # ADR-136's flex rebalances scene seconds by design — separately
    # disclosed, so the timing leg stands down entirely: timing reads as
    # UNCHECKED, never as verified.
    spec = _spec()
    spec["scenes"][0]["frames"] = 30
    lines = film_delivery_check(
        _CONFIRMED, spec, {"narration_flex": {"borrowed_s": 2.0}}
    )
    assert lines[0] == "confirmed=v3 digest:match MATCH-ON-CHECKED-SCOPE"
    assert any("unchecked:" in l and "timing(narration-flex" in l for l in lines)


def test_film_check_unavailable_digest_narrows_the_verdict() -> None:
    spec = _spec(provenance={})
    lines = film_delivery_check(_CONFIRMED, spec, {})
    assert lines[0] == "confirmed=v3 digest:unavailable MATCH-ON-CHECKED-SCOPE"
    assert any(l == "unchecked: digest" for l in lines)


def test_film_check_missing_timing_fields_narrow_the_verdict() -> None:
    spec = _spec()
    del spec["scenes"][1]["frames"]
    lines = film_delivery_check(_CONFIRMED, spec, {})
    assert lines[0].endswith("MATCH-ON-CHECKED-SCOPE")
    assert any("missing seconds/frames" in l for l in lines)


def test_film_check_audio_param_legs() -> None:
    # Confirmed voiceover off but narration audio landed.
    spec = _spec()
    spec["scenes"][0]["audio"] = "https://cdn/x.mp3"
    lines = film_delivery_check(_CONFIRMED, spec, {})
    assert any("audio landed but voiceover confirmed off" in l for l in lines)
    # Confirmed music off but a bed landed.
    spec2 = _spec(music={"mood": "calm"})
    lines2 = film_delivery_check(_CONFIRMED, spec2, {})
    assert any("music landed but confirmed off" in l for l in lines2)


def test_landed_fact_reads_the_confirmed_stamp_not_the_live_draft() -> None:
    """The comparison's board comes from the caller-stamped confirmed
    version — landed_fact never reaches for anything live."""
    fact = landed_fact(
        _OutputStub("film", render_spec=_spec(), render_status="completed",
                    files={"video": "k.mp4"}),
        film_confirmed=_CONFIRMED,
    )
    assert fact.film_check == ("confirmed=v3 digest:match MATCH",)
    # A clip row never carries the check.
    clip = _clip()
    assert clip.film_check is None


def test_compute_run_review_flags_a_drifted_film() -> None:
    drifted = _spec()
    drifted["scenes"][1]["lines"] = ["被改写的内容"]
    film = landed_fact(
        _OutputStub("film", render_spec=drifted, render_status="completed",
                    files={"video": "k.mp4"}),
        film_confirmed=_CONFIRMED,
    )
    review = compute_run_review(
        confirmed_scope={"compiled_scope": [{"tool": "launch_film", "params": {}}]},
        landed=[film],
    )
    assert "film_drift:film" in review.gaps
    # A matched film adds no gap.
    matched = landed_fact(
        _OutputStub("film", render_spec=_spec(), render_status="completed",
                    files={"video": "k.mp4"}),
        film_confirmed=_CONFIRMED,
    )
    review2 = compute_run_review(
        confirmed_scope={"compiled_scope": [{"tool": "launch_film", "params": {}}]},
        landed=[matched],
    )
    assert "film_drift:film" not in review2.gaps


def test_review_fact_lines_render_the_check_headline_and_details() -> None:
    drifted = _spec()
    drifted["scenes"][1]["lines"] = ["被改写的内容"]
    film = landed_fact(
        _OutputStub("film", render_spec=drifted, render_status="completed",
                    files={"video": "k.mp4"}),
        film_confirmed=_CONFIRMED,
    )
    review = compute_run_review(confirmed_scope=None, landed=[film])
    text = "\n".join(review_fact_lines(review))
    assert "confirmed=v3 digest:match DRIFT" in text
    assert "drift:s2.lines" in text


def test_film_check_animation_timing_fields_participate_in_drift() -> None:
    """Batch B: the confirmed-vs-landed adjudication compares the animation
    timing fields — a spec that landed different timing is DRIFT, a null on
    the board against an absent spec key reads equal (legacy boards stay
    MATCH)."""
    import copy

    confirmed = copy.deepcopy(_CONFIRMED)
    confirmed["board"]["scenes"][0].update(
        {"enter": "words", "enter_start": 0.3, "enter_interval": 0.12,
         "enter_duration": 0.25}
    )
    spec = _spec()
    spec["scenes"][0].update(
        {"enter": "words", "enter_start": 0.3, "enter_interval": 0.12,
         "enter_duration": 0.25}
    )
    lines = film_delivery_check(confirmed, spec, {})
    assert lines == ("confirmed=v3 digest:match MATCH",)

    drifted = _spec()
    drifted["scenes"][0].update(
        {"enter": "words", "enter_start": 0.5, "enter_interval": 0.12,
         "enter_duration": 0.25}
    )
    lines = film_delivery_check(confirmed, drifted, {})
    assert lines[0].endswith("DRIFT")
    assert "drift:s1.enter_start" in lines

    # Null on the confirmed board == absent on the landed spec (no drift).
    nulled = copy.deepcopy(_CONFIRMED)
    nulled["board"]["scenes"][0].update(
        {k: None for k in ("enter_start", "enter_interval", "enter_duration",
                           "enter_hold_until", "motion_start", "motion_end")}
    )
    lines = film_delivery_check(nulled, _spec(), {})
    assert lines == ("confirmed=v3 digest:match MATCH",)


class TestFilmMusicBed:
    """配乐三态 (事故 7886d879 + P2 未知态): DELIVERY FACTS 的落地床只读
    烘焙 render_spec —— 有效 spec(带 scenes 锚) 有 music 块 = bed, 有效
    spec 明确无 = none; 记录缺失/空记录/半写(无 scenes 锚) = unknown,
    永不塌缩成 none/off; 未指定 mood 永不被读成「无音乐」; 非 film 产物
    永不携带该字段。配置在场 ≠ 试听确认有声。"""

    def test_extraction_reads_the_baked_spec(self) -> None:
        # 有效音乐配置
        f = _film(render_spec={"scenes": [{"frames": 96}], "music": {"url": "music/trk.mp3", "gain_db": -20.0}})
        assert f.music_bed is True
        # 有效 spec 明确无 music
        f = _film(render_spec={"scenes": [{"frames": 96}]})
        assert f.music_bed is False
        # spec 缺失 (None) → unknown
        f = _film(render_spec=None)
        assert f.music_bed is None
        # 空记录 ({}) → unknown
        f = _film(render_spec={})
        assert f.music_bed is None
        # 半写记录 (有 music 但无 scenes 锚) → unknown, 不轻信
        f = _film(render_spec={"music": {"url": "m.mp3"}})
        assert f.music_bed is None
        # 非 film 永不携带
        assert _clip().music_bed is None

    def test_fact_lines_carry_the_three_states(self) -> None:
        review = compute_run_review(
            confirmed_scope=None,
            landed=[_film(render_spec={"scenes": [{}], "music": {"url": "m.mp3"}})],
        )
        assert any("music=bed" in line for line in review_fact_lines(review))
        review = compute_run_review(
            confirmed_scope=None,
            landed=[_film(render_spec={"scenes": [{}]})],
        )
        assert any("music=none" in line for line in review_fact_lines(review))
        # 缺失/空记录 → unknown, 永不印成 none
        for thin in (None, {}, {"music": {"url": "m.mp3"}}):
            review = compute_run_review(
                confirmed_scope=None, landed=[_film(render_spec=thin)]
            )
            lines = review_fact_lines(review)
            assert any("music=unknown" in line for line in lines), thin
            assert not any("music=none" in line for line in lines), thin
        # 非 film 行不出现该 token.
        review = compute_run_review(confirmed_scope=None, landed=[_clip()])
        assert not any("music=" in line for line in review_fact_lines(review))


# ---- composite elements (ADR-140) ---------------------------------------------

_CONFIRMED_COMPOSITE = {
    "version": 1,
    "digest": "digest-c1",
    "board": {
        "scenes": [
            {
                "scene_id": "s1",
                "type": "composite",
                "seconds": 8.0,
                "dark": False,
                "elements": [
                    {"kind": "video", "element_id": "e1",
                     "asset": "11111111-1111-1111-1111-111111111111",
                     "source_start": 10.0, "source_end": 18.0, "at": 0.0,
                     "duration": None, "keep_audio": False, "z": 0,
                     "fit": "cover",
                     "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}},
                    {"kind": "text", "element_id": "e2", "tone": "light",
                     "lines": ["逐字出现"], "at": 1.0, "until": 7.0,
                     "enter": "words", "enter_interval": 0.3, "z": 0,
                     "copy_text": "逐字出现",
                     "rect": {"x": 0.05, "y": 0.3, "w": 0.4, "h": 0.4}},
                ],
            }
        ]
    },
    "params": {"aspect": "16:9", "music_mood": "off", "voiceover": False},
}


def _composite_spec() -> dict:
    """The landed spec for _CONFIRMED_COMPOSITE: asset id resolved to the
    storage key, identity keys renamed, null stays out."""
    return {
        "fps": 30,
        "aspect": "16:9",
        "provenance": {"storyboard_digest": "digest-c1"},
        "scenes": [
            {
                "type": "composite",
                "frames": 240,
                "dark": False,
                "elements": [
                    {"kind": "video", "id": "e1", "src": "u/demo/video.mp4",
                     "source_start": 10.0, "source_end": 18.0, "at": 0.0,
                     "keep_audio": False, "z": 0, "fit": "cover",
                     "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}},
                    {"kind": "text", "id": "e2", "tone": "light",
                     "lines": ["逐字出现"], "at": 1.0, "until": 7.0,
                     "enter": "words", "enter_interval": 0.3, "z": 0,
                     "rect": {"x": 0.05, "y": 0.3, "w": 0.4, "h": 0.4}},
                ],
            }
        ],
    }


def test_film_check_composite_match_normalized() -> None:
    """Board asset ids vs spec src keys, element_id vs id, null-stays-out —
    the normalized comparator reads them as the same composition."""
    lines = film_delivery_check(_CONFIRMED_COMPOSITE, _composite_spec(), {})
    assert lines == ("confirmed=v1 digest:match MATCH",)


def test_film_check_composite_element_drift_named_per_element() -> None:
    spec = _composite_spec()
    spec["scenes"][0]["elements"][1]["lines"] = ["被改写的文字"]
    spec["scenes"][0]["elements"][0]["source_start"] = 12.0
    lines = film_delivery_check(_CONFIRMED_COMPOSITE, spec, {})
    assert lines[0].endswith("DRIFT")
    assert "drift:s1.e2.lines" in lines
    assert "drift:s1.e1.source_start" in lines


def test_film_check_composite_identity_rides_the_digest_leg() -> None:
    """Without a matching digest the asset→key resolution cannot be proven
    here — it lands in the UNCHECKED scope, named, never verified."""
    spec = _composite_spec()
    spec["provenance"] = {"storyboard_digest": "other"}
    lines = film_delivery_check(_CONFIRMED_COMPOSITE, spec, {})
    assert lines[0].endswith("DRIFT")
    assert any("asset→key identity" in l for l in lines)
