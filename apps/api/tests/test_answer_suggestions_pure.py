"""Pure tests for the suggestion lineage dark placement (ADR-099 §3/§4 —
批次 C·C+ commit 1): schemas, record stamping, the directed stale verdict,
and the provenance note.

No DB, no LLM, no HTTP (suite discipline). What is gated HERE:

- 零 diff 锁: with no ``suggestions`` input, both answer args behave exactly
  as before the field existed (defaults, dump shape, the shared validator
  leaving WrapUpArgs' semantics untouched);
- schema read tolerance (打字机律牙①): null suggestions read as the empty
  default, never a rejection; bare-string labels upgrade; blank labels
  drop; overlong rejects into the loop; extra recommended marks silence;
- ``build_suggestion_records``: provenance is code-stamped (1-based dock
  ids, source_turn, source_state.asset_ids) — the model's payload never
  carries it;
- ``suggestion_stale_reasons`` / ``compose_suggestion_note``: the three
  stale predicates are the whole definition (named, ordered); a fresh pick
  reads as a control event, a stale pick names what moved and bans silent
  adoption.
"""

import pytest

from app.chat.suggestions import (
    build_suggestion_records,
    compose_suggestion_note,
    suggestion_stale_reasons,
)
from app.models.schemas import (
    ChatAnswerArgs,
    PlanAnswerArgs,
    SuggestionItem,
    WrapUpArgs,
)


# ---- 零 diff 锁: no-suggestions behavior is byte-identical -----------------


def test_chat_answer_args_defaults_unchanged():
    args = ChatAnswerArgs()
    assert args.suggestions == []
    assert args.pending_disposition == "none"
    assert args.material_pending is False
    assert args.model_dump(mode="json") == {
        "pending_disposition": "none",
        "material_pending": False,
        "suggestions": [],
    }


def test_plan_answer_args_defaults_unchanged():
    args = PlanAnswerArgs()
    assert args.suggestions == []
    assert args.pending_disposition == "none"
    assert args.material_pending is False
    assert args.brief is None
    assert args.material_text is None


def test_null_suggestions_read_as_empty_both_seats():
    # 打字机律牙①: the model writes null when it means "no options" — a
    # rejection here costs the repair round that never streams.
    assert ChatAnswerArgs.model_validate({"suggestions": None}).suggestions == []
    assert PlanAnswerArgs.model_validate({"suggestions": None}).suggestions == []
    assert WrapUpArgs.model_validate({"suggestions": None}).suggestions == []


def test_wrap_up_validator_semantics_unchanged_by_extraction():
    # The shared-function extraction must not drift WrapUpArgs' contract:
    # blanks drop, bare strings upgrade, overlong rejects, extra
    # recommended marks silence.
    args = WrapUpArgs.model_validate(
        {"suggestions": ["做一个法语版", {"label": "  "}, {"label": "b", "recommended": True}]}
    )
    assert [s.label for s in args.suggestions] == ["做一个法语版", "b"]
    assert [s.recommended for s in args.suggestions] == [False, True]
    with pytest.raises(Exception):
        WrapUpArgs.model_validate({"suggestions": [{"label": "x" * 41}]})


# ---- schema validation (校验分层律, both answer seats) ---------------------


@pytest.mark.parametrize("cls", [ChatAnswerArgs, PlanAnswerArgs])
def test_answer_suggestions_validator(cls):
    args = cls.model_validate(
        {
            "suggestions": [
                "做一个法语版",
                {"label": "b", "recommended": True},
                {"label": "c", "recommended": True},
            ]
        }
    )
    assert [s.label for s in args.suggestions] == ["做一个法语版", "b", "c"]
    # Extra recommendation marks drop silently (cosmetic, never a repair).
    assert [s.recommended for s in args.suggestions] == [False, True, False]


@pytest.mark.parametrize("cls", [ChatAnswerArgs, PlanAnswerArgs])
def test_answer_suggestions_overlong_rejects_into_loop(cls):
    with pytest.raises(Exception):
        cls.model_validate({"suggestions": [{"label": "x" * 41}]})


@pytest.mark.parametrize("cls", [ChatAnswerArgs, PlanAnswerArgs])
def test_answer_suggestions_capped_at_three(cls):
    with pytest.raises(Exception):
        cls.model_validate({"suggestions": [{"label": str(i)} for i in range(4)]})


# ---- record stamping (provenance is code's, never the model's) -------------


def _item(label: str, recommended: bool = False) -> SuggestionItem:
    return SuggestionItem(label=label, recommended=recommended)


def test_build_suggestion_records_stamps_provenance():
    records = build_suggestion_records(
        [_item("a"), _item("b", recommended=True)], "msg-1", ["asset-1", "asset-2"]
    )
    assert records == [
        {
            "id": "1",
            "label": "a",
            "description": "",
            "recommended": False,
            "source_turn": "msg-1",
            "source_state": {"asset_ids": ["asset-1", "asset-2"]},
        },
        {
            "id": "2",
            "label": "b",
            "description": "",
            "recommended": True,
            "source_turn": "msg-1",
            "source_state": {"asset_ids": ["asset-1", "asset-2"]},
        },
    ]


def test_build_suggestion_records_empty_items_empty_block():
    assert build_suggestion_records([], "msg-1", ["asset-1"]) == []


# ---- the directed stale verdict (ADR-099 §4 — three predicates, zero more) -


def test_stale_reasons_empty_when_fresh():
    assert (
        suggestion_stale_reasons(
            assets_missing=False,
            assets_failed=False,
            new_understanding=False,
            plan_or_run_since=False,
        )
        == []
    )


def test_stale_reasons_named_and_ordered():
    reasons = suggestion_stale_reasons(
        assets_missing=True,
        assets_failed=True,
        new_understanding=True,
        plan_or_run_since=True,
    )
    assert reasons == [
        "the material it drew on was deleted",
        "the material it drew on failed processing",
        "new material understanding landed since",
        "a plan was docked or a run started since",
    ]


def test_stale_reasons_each_predicate_independent():
    assert suggestion_stale_reasons(
        assets_missing=True, assets_failed=False,
        new_understanding=False, plan_or_run_since=False,
    ) == ["the material it drew on was deleted"]
    assert suggestion_stale_reasons(
        assets_missing=False, assets_failed=False,
        new_understanding=False, plan_or_run_since=True,
    ) == ["a plan was docked or a run started since"]


# ---- the provenance note ----------------------------------------------------


def test_fresh_note_names_the_control_event():
    note = compose_suggestion_note("做一个法语版", [])
    assert "做一个法语版" in note
    assert "earlier suggestion card" in note
    assert "EARLIER" not in note  # fresh = no stale alarm


def test_stale_note_names_what_moved_and_bans_silence():
    note = compose_suggestion_note(
        "做一个法语版", ["new material understanding landed since"]
    )
    assert "做一个法语版" in note
    assert "new material understanding landed since" in note
    assert "never adopt it silently" in note
