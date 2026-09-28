"""Pure tests for the chat + plan paths' tool-args schemas (ADR-077 判词②
tool-loop form) — the wire contract the provider's tool_calls compile
against.

No DB, no LLM, no HTTP (suite discipline). What is gated HERE:

- P0-② 对账 (2026-09-22): ``ProposeTasksArgs.specific_instruction`` exists and
  carries the distilled-EXTRA contract (the chat path no longer forces the
  raw user message down as the instruction — the model submits distilled
  extras, and the propose seat's fallback reads tolerate its absence);
- 打字机律牙① (read tolerance): an explicit ``null`` on the optional string
  fields reads as the empty default, never a schema rejection (a rejected
  iteration never streams — the prose would pop in as one blob);
- 一问拍一体化 (2026-09-27): the ask card's schema contract — every option
  carries its one-line ``description`` (null reads as ""), the
  ``recommended_id`` mark survives only when it names a shipped option
  (``resolve_recommended_id`` — a stale or imagined id drops silently,
  never a repair round), and the plan path's tools all seat
  ``pending_disposition`` (the deflection settlement the zombie-card
  incident was missing);
- ``extra="forbid"`` stays the unknown-key alarm.
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ChatAnswerArgs,
    ChatAskArgs,
    Option,
    PlanAnswerArgs,
    PlanAskArgs,
    PresentPlanArgs,
    ProposeTasksArgs,
    resolve_recommended_id,
)

_TASK = {"tool": "write_post", "params": {"language": "en"}}


class TestProposeTasksArgsSpecificInstruction:
    def test_field_exists_and_defaults_to_none(self) -> None:
        args = ProposeTasksArgs.model_validate({"tasks": [_TASK]})
        assert args.specific_instruction is None

    def test_distilled_value_rides(self) -> None:
        args = ProposeTasksArgs.model_validate(
            {
                "tasks": [_TASK],
                "specific_instruction": "focus on the Q&A section",
            }
        )
        assert args.specific_instruction == "focus on the Q&A section"

    def test_explicit_null_reads_as_absent(self) -> None:
        """读容忍兜底: the model writes null when it means 'nothing extra' —
        that must never be a schema rejection (the rejected-iteration typewriter
        hole); it reads as the empty default."""
        args = ProposeTasksArgs.model_validate(
            {"tasks": [_TASK], "specific_instruction": None, "name": None}
        )
        assert args.specific_instruction is None
        assert args.name == ""

    def test_unknown_keys_still_rejected(self) -> None:
        """extra='forbid' is the drift alarm — the distilled contract never
        licenses invented params."""
        with pytest.raises(ValidationError):
            ProposeTasksArgs.model_validate(
                {"tasks": [_TASK], "instruction": "the old field name"}
            )


# ---- 一问拍一体化 (2026-09-27, Claude-Card parity) -----------------------------
#
# The ask card's schema contract: the option's reason line and the ONE
# recommendation mark ride the wire; the pending-question disposition seats
# on every plan-path terminal tool (the zombie-card incident's missing
# gate). SuggestionItem/WrapUpArgs coverage lives in test_trigger_turn_pure.


class TestOptionDescription:
    def test_reason_line_rides(self) -> None:
        option = Option.model_validate(
            {"id": "1", "label": "长文", "description": "最省事，先出一条"}
        )
        assert option.description == "最省事，先出一条"

    def test_null_and_absent_read_as_empty(self) -> None:
        # 读容忍: code-built options (asset_role) and legacy rows carry no
        # reason line; the model writing null means the same.
        assert Option.model_validate({"id": "1", "label": "x"}).description == ""
        assert (
            Option.model_validate({"id": "1", "label": "x", "description": None}).description
            == ""
        )


class TestResolveRecommendedId:
    _OPTIONS = [Option(id="1", label="a"), Option(id="2", label="b")]

    def test_a_shipped_option_id_survives(self) -> None:
        assert resolve_recommended_id("2", self._OPTIONS) == "2"

    def test_stale_or_imagined_ids_drop_silently(self) -> None:
        # Cosmetic, never worth a rejection round — the asset_role
        # code-built options invalidate any LLM-written id the same way.
        assert resolve_recommended_id("3", self._OPTIONS) is None
        assert resolve_recommended_id("asset-uuid", self._OPTIONS) is None

    def test_none_and_empty_options_pass_through_to_none(self) -> None:
        assert resolve_recommended_id(None, self._OPTIONS) is None
        assert resolve_recommended_id("1", []) is None


class TestPlanAskArgsCardFields:
    def test_reason_mark_and_disposition_ride(self) -> None:
        args = PlanAskArgs.model_validate(
            {
                "question": "接下来做什么？",
                "options": [
                    {"id": "1", "label": "长文", "description": "最省事"},
                    {"id": "2", "label": "金句卡"},
                ],
                "recommended_id": "1",
                "pending_disposition": "answer",
            }
        )
        assert args.recommended_id == "1"
        assert args.options[1].description == ""
        assert args.pending_disposition == "answer"

    def test_nulls_read_as_defaults(self) -> None:
        # 打字机律牙①: the model writes null for "no mark / nothing pending"
        # — never a schema rejection burning a non-streaming iteration.
        args = PlanAskArgs.model_validate(
            {
                "question": "q",
                "options": None,
                "recommended_id": None,
                "pending_disposition": None,
                "slot": None,
            }
        )
        assert args.options == []
        assert args.recommended_id is None
        assert args.pending_disposition == "none"
        assert args.slot is None


class TestPendingDispositionSeats:
    """The zombie-card fix: every plan-path terminal tool seats the
    disposition so an engaging free-text reply (incl. the deflection
    'which do you recommend?') settles the docked question."""

    def test_present_plan_seats_disposition(self) -> None:
        args = PresentPlanArgs.model_validate({"pending_disposition": "answer"})
        assert args.pending_disposition == "answer"
        assert PresentPlanArgs.model_validate({}).pending_disposition == "none"
        assert (
            PresentPlanArgs.model_validate({"pending_disposition": None}).pending_disposition
            == "none"
        )

    def test_plan_answer_seats_disposition(self) -> None:
        args = PlanAnswerArgs.model_validate({"pending_disposition": "skip"})
        assert args.pending_disposition == "skip"
        assert PlanAnswerArgs.model_validate({}).pending_disposition == "none"

    def test_an_invented_disposition_rejects(self) -> None:
        with pytest.raises(ValidationError):
            PlanAskArgs.model_validate(
                {"question": "q", "pending_disposition": "defer"}
            )


class TestChatAskArgsCardFields:
    def test_recommended_id_null_reads_as_absent(self) -> None:
        args = ChatAskArgs.model_validate(
            {"question": "q", "recommended_id": None, "options": None}
        )
        assert args.recommended_id is None
        assert args.options == []

    def test_disposition_defaults_to_none(self) -> None:
        assert ChatAskArgs.model_validate({"question": "q"}).pending_disposition == "none"

    def test_null_disposition_reads_as_none(self) -> None:
        # 打字机律牙① on the chat path's seats too: the model's
        # null-means-skip habit must never reject the call (a rejected
        # iteration never streams).
        assert (
            ChatAskArgs.model_validate(
                {"question": "q", "pending_disposition": None}
            ).pending_disposition
            == "none"
        )
        assert (
            ChatAnswerArgs.model_validate(
                {"pending_disposition": None}
            ).pending_disposition
            == "none"
        )
