"""Pure tests for edit_output's op assembly (ADR-090, E2 — S3).

No DB, no LLM, no HTTP. The matrix locks the controlled vocabulary's
pairing law (kind × params, 多给/缺给 = 域拒绝), the four kinds' op
translation (with the resolver's span verdict passed through), the trim
math and its bounds, the preset enum (L3 — free-form refuses), and the
world-witnessed fact echo's bilingual shape.
"""

from app.chat.propose_turn import _edit_fact_echo
import pytest
import pydantic
from app.models.schemas import (
    _EDIT_KIND_BY_PARAM,
    EditOutputArgs,
    edit_kind_for_params,
)
from app.pipeline.edit_ops import (
    KIND_PARAMS,
    EditRefusal,
    assemble_edit_op,
    kept_range,
    param_mismatch,
)
from app.pipeline.edit_span import ResolvedSpan, SpanRefusal

SPEC = {
    "segments": [
        {"start": 10.0, "end": 20.0, "hidden": False},
        {"start": 25.0, "end": 40.0, "hidden": False},
    ],
    "source": {"duration": 120.0},
}


class TestPairingLaw:
    def test_unknown_kind_refuses(self):
        assert param_mismatch("set_music", {}) is not None

    def test_missing_param_refuses(self):
        assert param_mismatch("remove_range", {}) is not None

    def test_empty_value_counts_as_missing(self):
        assert param_mismatch("set_title", {"title": "  "}) is not None

    def test_extra_param_refuses(self):
        assert param_mismatch("set_title", {"title": "X", "quote": "y"}) is not None

    def test_clean_pairing_passes(self):
        assert param_mismatch("set_trim", {"seconds": 3}) is None


class TestRemoveRange:
    def test_span_becomes_op_params(self):
        op = assemble_edit_op(
            "remove_range", {"quote": "welcome"},
            spec=SPEC, span=ResolvedSpan(10.0, 12.5, "exact"),
        )
        assert op == {"op": "remove_range", "params": {"start": 10.0, "end": 12.5}}

    def test_resolver_refusal_passes_through_ambiguous(self):
        r = assemble_edit_op(
            "remove_range", {"quote": "welcome"},
            spec=SPEC, span=SpanRefusal("ambiguous", 2),
        )
        assert isinstance(r, EditRefusal) and "2 times" in r.feedback

    def test_resolver_refusal_passes_through_not_found(self):
        r = assemble_edit_op(
            "remove_range", {"quote": "zzz"},
            spec=SPEC, span=SpanRefusal("not_found"),
        )
        assert isinstance(r, EditRefusal) and "not found" in r.feedback


class TestSetTrim:
    def test_shortens_tail(self):
        op = assemble_edit_op("set_trim", {"seconds": 3}, spec=SPEC)
        assert op == {"op": "set_trim", "params": {"start": 10.0, "end": 37.0}}

    def test_non_positive_refuses(self):
        assert isinstance(assemble_edit_op("set_trim", {"seconds": 0}, spec=SPEC), EditRefusal)
        assert isinstance(assemble_edit_op("set_trim", {"seconds": -3}, spec=SPEC), EditRefusal)

    def test_cutting_everything_refuses(self):
        r = assemble_edit_op("set_trim", {"seconds": 30}, spec=SPEC)
        assert isinstance(r, EditRefusal) and "leaves nothing" in r.feedback

    def test_no_kept_content_refuses(self):
        spec = {"segments": [{"start": 0, "end": 5, "hidden": True}]}
        assert isinstance(assemble_edit_op("set_trim", {"seconds": 1}, spec=spec), EditRefusal)

    def test_kept_range_skips_hidden(self):
        spec = {
            "segments": [
                {"start": 0.0, "end": 5.0, "hidden": False},
                {"start": 5.0, "end": 8.0, "hidden": True},
                {"start": 8.0, "end": 12.0, "hidden": False},
            ]
        }
        assert kept_range(spec) == (0.0, 12.0)


class TestSetCaptionStyle:
    def test_enum_preset_passes(self):
        op = assemble_edit_op(
            "set_caption_style", {"style": "karaoke-highlight"}, spec=SPEC
        )
        assert op == {"op": "set_caption_style", "params": {"preset": "karaoke-highlight"}}

    def test_free_form_refuses_with_enum(self):
        r = assemble_edit_op(
            "set_caption_style", {"style": "big-yellow-comic-sans"}, spec=SPEC
        )
        assert isinstance(r, EditRefusal) and "karaoke-highlight" in r.feedback


class TestSetTitle:
    def test_title_op(self):
        op = assemble_edit_op("set_title", {"title": "  New title "}, spec=SPEC)
        assert op == {"op": "set_title", "params": {"text": "New title", "enabled": True}}


class TestFactEcho:
    def test_remove_range_bilingual(self):
        op = {"op": "remove_range", "params": {"start": 0.0, "end": 4.2}}
        assert "0.0–4.2s" in _edit_fact_echo("remove_range", op, zh=True)
        assert "0.0–4.2s" in _edit_fact_echo("remove_range", op, zh=False)

    def test_each_kind_speaks_its_fact(self):
        cases = {
            "set_trim": {"op": "set_trim", "params": {"start": 0, "end": 37.0}},
            "set_caption_style": {"op": "set_caption_style", "params": {"preset": "karaoke-highlight"}},
            "set_title": {"op": "set_title", "params": {"text": "X"}},
        }
        for kind, op in cases.items():
            assert _edit_fact_echo(kind, op, zh=True)
            assert _edit_fact_echo(kind, op, zh=False)


class TestKindInference:
    """顺形律 decode (probe H; Final Hardening B1 — the ONLY kind source):
    one filled param determines the verb; the schema has NO kind field, so
    an explicit kind key is rejected as an extra (schema == production
    dispatch, never a paper control)."""

    def test_param_verb_bijection_pinned(self):
        assert KIND_PARAMS == {v: k for k, v in _EDIT_KIND_BY_PARAM.items()}

    def test_quote_infers_remove_range(self):
        args = EditOutputArgs.model_validate(
            {"target": {"output_id": "11111111-1111-1111-1111-111111111111"},
             "params": {"quote": "welcome back"}}
        )
        assert edit_kind_for_params(args.params) == "remove_range"

    def test_each_param_infers_its_kind(self):
        cases = {"seconds": 3, "style": "karaoke-highlight", "title": "X"}
        for key, value in cases.items():
            args = EditOutputArgs.model_validate({"params": {key: value}})
            assert edit_kind_for_params(args.params) == _EDIT_KIND_BY_PARAM[key]

    def test_no_kind_field_exists(self):
        # B1: a stray ``kind`` key is forbidden input (extra="forbid"), never
        # a silent override — the loop also strips it, so it can never reach
        # production dispatch.
        with pytest.raises(pydantic.ValidationError):
            EditOutputArgs.model_validate(
                {"kind": "remove_range", "params": {"quote": "x"}}
            )

    def test_no_params_stays_none(self):
        args = EditOutputArgs.model_validate({})
        assert edit_kind_for_params(args.params) is None

    def test_two_params_stays_none(self):
        args = EditOutputArgs.model_validate(
            {"params": {"quote": "x", "seconds": 3}}
        )
        assert edit_kind_for_params(args.params) is None


class TestSingleControlledEntry:
    """Final Hardening B1 (2026-09-24, ADR-090): the Agent's ONLY edit entry
    is edit_output's controlled enum — the raw-ops verb is gone from the
    chat tool set, and the chat write door's vocabulary invariant holds in
    the registry itself."""

    def test_chat_tools_have_no_raw_ops_verb(self):
        from app.chat.turn_tools import CHAT_TOOLS

        names = {t.name for t in CHAT_TOOLS}
        assert "apply_edit_ops" not in names
        assert "edit_output" in names

    def test_mvp_four_are_llm_visible(self):
        from app.operations.registry import OP_REGISTRY

        for name in ("remove_range", "set_trim", "set_caption_style", "set_title"):
            assert OP_REGISTRY[name].llm_visible is True

    def test_track_ops_stay_out_of_chat_vocabulary(self):
        from app.operations.registry import OP_REGISTRY

        hidden = {n for n, d in OP_REGISTRY.items() if not d.llm_visible}
        assert hidden == {
            "reorder_segments",
            "insert_segment",
            "set_transition",
            "add_layer",
            "remove_layer",
            "move_layer",
        }
