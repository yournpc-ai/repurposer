"""scope_compile — the Content Plan → Execution Scope compiler (iter-2, ADR-089 §2).

Pure coverage (no DB, no LLM, no HTTP). Acceptance #1 of the iter-2
contract: the full output-mapping spectrum (clip ± language version / the
four writers / pointer resolution / the rejection loop), and the structural
law — a compiled chain NEVER contains select_clips (the execution world has
no second discoverer).
"""

from types import SimpleNamespace

import pytest

from app.pipeline.exploration_store import (
    CandidateSetSpec,
    ContentPlanSpec,
    SelectSpec,
)
from app.pipeline.scope_compile import ScopeCompileRejected, compile_plans

CSET_ID = "11111111-1111-1111-1111-111111111111"
SEL_ID = "22222222-2222-2222-2222-222222222222"
PLAN_ID = "33333333-3333-3333-3333-333333333333"
ASSET_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _cset(members=None) -> SimpleNamespace:
    members = members or [
        {"start": 12.0, "end": 18.9, "excerpt": "Our pricing is simple.", "speaker": "host"},
        {"start": 34.0, "end": 39.4, "excerpt": "Every tier includes the dashboard.", "speaker": None},
    ]
    spec = CandidateSetSpec(asset_id=ASSET_ID, topic="pricing", members=members)
    return SimpleNamespace(id=CSET_ID, spec=spec.model_dump(mode="json"), state="ready")


def _select(member_index: int = 0, sel_id: str = SEL_ID) -> SimpleNamespace:
    spec = SelectSpec(
        candidate_set_id=CSET_ID,
        member_index=member_index,
        verdict="Most complete answer",
        reason="It covers pricing end to end",
    )
    return SimpleNamespace(id=sel_id, spec=spec.model_dump(mode="json"), state="ready")


def _plan(outputs, state: str = "ready", plan_id: str = PLAN_ID, issues=None) -> SimpleNamespace:
    spec = ContentPlanSpec(select_id=SEL_ID, title="Pricing clip", outputs=outputs)
    payload = spec.model_dump(mode="json")
    if issues:
        payload["issues"] = issues
    return SimpleNamespace(id=plan_id, spec=payload, state=state)


def _compile(plans, **kwargs):
    kwargs.setdefault("source_language", "en")
    return compile_plans(plans, [_select()], [_cset()], **kwargs)


# ---- clip mapping (± language version) ----------------------------------------


class TestClipMapping:
    def test_bare_clip_compiles_to_cut_only(self):
        tasks = _compile(_plan_rows := [_plan([{"kind": "clip"}])])
        assert [t.tool for t in tasks] == ["cut_segments"]
        params = tasks[0].params
        assert params["segments"] == [{"start": 12.0, "end": 18.9}]
        assert params["asset_id"] == ASSET_ID
        assert "aspect" not in params

    def test_clip_with_aspect_carries_the_birth_frame(self):
        tasks = _compile([_plan([{"kind": "clip", "aspect": "1:1"}])])
        assert tasks[0].params["aspect"] == "1:1"

    def test_language_version_continues_with_translate(self):
        tasks = _compile([_plan([{"kind": "clip", "language": "fr"}])])
        assert [t.tool for t in tasks] == ["cut_segments", "translate_clip"]
        assert tasks[1].params == {"target_language": "fr", "bilingual": False}

    def test_bilingual_caption_mode_maps_the_flag(self):
        tasks = _compile(
            [_plan([{"kind": "clip", "language": "fr", "caption_mode": "bilingual"}])]
        )
        assert tasks[1].params == {"target_language": "fr", "bilingual": True}

    def test_dub_continues_with_dub_clip(self):
        tasks = _compile(
            [_plan([{"kind": "clip", "language": "fr", "dub": True}])]
        )
        assert [t.tool for t in tasks] == ["cut_segments", "dub_clip"]
        assert tasks[1].params == {"target_language": "fr"}

    def test_source_language_clip_needs_no_continuation(self):
        tasks = _compile([_plan([{"kind": "clip", "language": "en"}])])
        assert [t.tool for t in tasks] == ["cut_segments"]

    def test_unknown_source_still_honors_the_named_language(self):
        tasks = compile_plans(
            [_plan([{"kind": "clip", "language": "fr"}])],
            [_select()],
            [_cset()],
            source_language=None,
        )
        assert [t.tool for t in tasks] == ["cut_segments", "translate_clip"]

    def test_source_only_captions_with_a_target_language_is_a_rejection(self):
        with pytest.raises(ScopeCompileRejected, match="source_only"):
            _compile(
                [_plan([{"kind": "clip", "language": "fr", "caption_mode": "source_only"}])]
            )


# ---- writer mapping -------------------------------------------------------------


class TestWriterMapping:
    @pytest.mark.parametrize(
        "kind,tool",
        [
            ("post", "write_post"),
            ("article", "write_article"),
            ("quotes", "write_quotes"),
            ("carousel", "write_carousel"),
        ])
    def test_four_writers(self, kind, tool):
        tasks = _compile([_plan([{"kind": kind, "language": "de", "brief": "the pricing angle"}])])
        assert [t.tool for t in tasks] == [tool]
        params = tasks[0].params
        assert params["language"] == "de"
        # The plan's per-output brief rides the existing focus field.
        assert params["focus"] == "the pricing angle"
        # The writer's material narrows to the select's span (iter-2 ②).
        assert params["source_span"] == {
            "start": 12.0,
            "end": 18.9,
            "asset_id": ASSET_ID,
        }

    def test_writer_language_defaults(self):
        tasks = _compile([_plan([{"kind": "post"}])], default_language="zh")
        assert tasks[0].params["language"] == "zh"
        assert "focus" not in tasks[0].params  # no brief → no focus key

    def test_span_pointer_follows_the_selects_member(self):
        tasks = compile_plans(
            [_plan([{"kind": "post", "language": "en"}])],
            [_select(member_index=1)],
            [_cset()],
            source_language="en",
        )
        assert tasks[0].params["source_span"]["start"] == 34.0


# ---- the rejection loop ---------------------------------------------------------


class TestRejections:
    def test_draft_plan_rejects_with_its_issues(self):
        with pytest.raises(ScopeCompileRejected, match="open gaps.*bilingual"):
            _compile(
                [_plan(
                    [{"kind": "clip", "caption_mode": "bilingual"}],
                    state="draft",
                    issues=["output 0: bilingual captions need a target language"],
                )]
            )

    def test_compiled_or_superseded_never_recompile(self):
        for state in ("compiled", "superseded"):
            with pytest.raises(ScopeCompileRejected, match=state):
                _compile([_plan([{"kind": "post"}], state=state)])

    def test_revised_plans_compile(self):
        tasks = _compile([_plan([{"kind": "post", "language": "en"}], state="revised")])
        assert [t.tool for t in tasks] == ["write_post"]

    def test_unresolvable_select_pointer(self):
        with pytest.raises(ScopeCompileRejected, match="not in this journey's selects"):
            compile_plans(
                [_plan([{"kind": "post"}])], [], [_cset()], source_language="en"
            )

    def test_missing_candidate_set(self):
        with pytest.raises(ScopeCompileRejected, match="candidate set"):
            compile_plans(
                [_plan([{"kind": "post"}])], [_select()], [], source_language="en"
            )

    def test_member_index_outside_the_set(self):
        with pytest.raises(ScopeCompileRejected, match="outside the candidate set"):
            compile_plans(
                [_plan([{"kind": "post"}])],
                [_select(member_index=9)],
                [_cset()],
                source_language="en",
            )

    def test_no_plans_is_a_rejection(self):
        with pytest.raises(ScopeCompileRejected, match="no content plans"):
            compile_plans([], [_select()], [_cset()], source_language="en")

    def test_registry_adjudication_reenters(self):
        """The task cap is real money — an over-wide package is a compile
        rejection (B3 上移: only registry-legal chains reach the dock)."""
        plans = [
            _plan(
                [{"kind": "clip"}, {"kind": "post"}],
                plan_id=f"44444444-4444-4444-4444-{i:012d}",
            )
            for i in range(6)  # 6 × 2 = 12 tasks > MAX_TASKS_PER_RUN
        ]
        with pytest.raises(ScopeCompileRejected, match="tasks max"):
            _compile(plans)


# ---- chain shape -----------------------------------------------------------------


class TestChainShape:
    def test_multi_plan_chain_order(self):
        plans = [
            _plan([{"kind": "clip", "language": "fr"}], plan_id="55555555-5555-5555-5555-555555555551"),
            _plan([{"kind": "post", "language": "en"}], plan_id="55555555-5555-5555-5555-555555555552"),
        ]
        tasks = _compile(plans)
        assert [t.tool for t in tasks] == ["cut_segments", "translate_clip", "write_post"]

    def test_never_select_clips(self):
        """The structural law: no compiled chain ever contains the
        discovery-flavored execution tool (R12 + iter-1 开工裁决)."""
        plans = [
            _plan(
                [
                    {"kind": "clip", "language": "fr", "dub": True},
                    {"kind": "post", "language": "en", "brief": "angle"},
                    {"kind": "quotes", "language": "zh"},
                    {"kind": "carousel"},
                    {"kind": "article", "language": "de"},
                ]
            )
        ]
        tasks = _compile(plans)
        assert "select_clips" not in [t.tool for t in tasks]
        assert [t.tool for t in tasks] == [
            "cut_segments",
            "dub_clip",
            "write_post",
            "write_quotes",
            "write_carousel",
            "write_article",
        ]
