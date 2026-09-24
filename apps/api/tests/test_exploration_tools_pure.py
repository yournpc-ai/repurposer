"""Pure tests for the exploration terminal tool family (app/chat/exploration_tools.py)
— the agent's product-semantic proposal verbs for the discovery chain
(ADR-088 §2; 施工合同 docs/tasks/agent-working-loop-iter-1.md §6).

No DB, no LLM, no HTTP (suite discipline): the execute half needs a session
and stays covered by the door's own suite (test_exploration_store_pure.py)
plus the iter-1 scenario. What's gated HERE:

- the registry's shape (five verbs, ALL terminal in the harness form —
  终态工具一调即停; the production projection's terminal law is pinned in
  TestRegistryShape too: candidates/selects ride back, propose_plans /
  revise_plan / revise_selects stop the turn, iter-2 ⑤/⑦ N-57, iter-3 S4
  N-58);
- 迁移弧纪律 (ADR-089 §8): harness-level in iter-1 — the family is NOT
  registered into the production turn tools (production wiring = iter-2 R6);
- 打字机律牙① (read tolerance): explicit null on the optional fields reads
  as the empty default, never a schema rejection (a rejected iteration
  never streams);
- extra="forbid" stays the unknown-key drift alarm (house wire law).
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.chat.exploration_tools import (
    EXPLORATION_READ_NAMES,
    EXPLORATION_TOOLS,
    PlanItem,
    ProposeCandidatesArgs,
    ProposePlansArgs,
    ProposeSelectsArgs,
    RevisePlanArgs,
    SelectItem,
)

_MEMBER = {"start": 12.0, "end": 18.5, "excerpt": "pricing is hard"}
_CANDIDATES = {
    "asset_id": str(uuid4()),
    "topic": "pricing",
    "goal": "find the pricing sections",
    "members": [_MEMBER],
}


class TestRegistryShape:
    def test_five_terminal_verbs(self) -> None:
        """The harness form: ALL five verbs terminal (终态工具一调即停);
        revise_plan joined as the family's fourth word (iter-2 ⑦, N-57),
        revise_selects as the fifth (iter-3 S4, N-58 — the pick swap)."""
        assert set(EXPLORATION_TOOLS) == {
            "propose_candidates",
            "propose_selects",
            "propose_plans",
            "revise_plan",
            "revise_selects",
        }
        for name, tool in EXPLORATION_TOOLS.items():
            assert tool.name == name
            assert tool.terminal, name  # 终态工具一调即停
            assert tool.params_model is not None, name
            assert tool.description.strip(), name

    def test_production_projection_terminal_law(self) -> None:
        """iter-2 ⑤ (R6, N-57): the production projection re-forms the SAME
        entries — candidates/selects NON-terminal (R2 一回合连续工作: the
        observations ride back and the loop iterates), propose_plans /
        revise_plan / revise_selects TERMINAL (the dock = the paid-boundary
        stop, R15; a pick swap can dock too — the three money states,
        iter-3 S4)."""
        from app.chat.exploration_tools import exploration_chat_tools

        projection = {t.name: t.terminal for t in exploration_chat_tools()}
        assert projection == {
            "propose_candidates": False,
            "propose_selects": False,
            "propose_plans": True,
            "revise_plan": True,
            "revise_selects": True,
        }
        # Same params models — zero wording/schema drift between the seats.
        by_name = {t.name: t for t in exploration_chat_tools()}
        for name, tool in EXPLORATION_TOOLS.items():
            assert by_name[name].params_model is tool.params_model
            assert by_name[name].description == tool.description

    def test_read_names_are_registered_perception_reads(self) -> None:
        """The harness's loop composes the verbs with EXISTING perception
        reads — every name must resolve in the read registry (no invented
        read seats)."""
        from app.chat.perception import PERCEPTION_TOOLS

        assert EXPLORATION_READ_NAMES
        for name in EXPLORATION_READ_NAMES:
            assert name in PERCEPTION_TOOLS, name

    def test_family_is_not_in_the_production_turn_tools(self) -> None:
        """迁移弧 (iter-1 harness-level): the verbs must NOT leak into the
        production chat agent's tool set before iter-2's R6 routing."""
        from app.chat.turn_tools import CHAT_TOOLS, PLAN_TOOLS

        production_names = {t.name for t in (*PLAN_TOOLS, *CHAT_TOOLS)}
        assert not (set(EXPLORATION_TOOLS) & production_names)


class TestReadTolerance:
    """打字机律牙①: null means 'skip this field' — the default applies,
    never a rejection burning an iteration."""

    def test_null_journey_id_reads_as_chain_open(self) -> None:
        args = ProposeCandidatesArgs.model_validate({**_CANDIDATES, "journey_id": None})
        assert args.journey_id is None
        assert args.goal == "find the pricing sections"

    def test_null_plan_title_reads_as_unnamed(self) -> None:
        item = PlanItem.model_validate(
            {"select_id": str(uuid4()), "title": None, "outputs": [{"kind": "clip"}]}
        )
        assert item.title == ""

    def test_revise_plan_nulls_read_as_keep_and_empty(self) -> None:
        """iter-2 ⑦: a null title reads as 'keep the current one' (the door's
        None semantics), a null instruction as the empty restatement."""
        args = RevisePlanArgs.model_validate(
            {
                "plan_id": str(uuid4()),
                "title": None,
                "instruction": None,
                "outputs": [{"kind": "post", "language": "en"}],
            }
        )
        assert args.title == ""
        assert args.instruction == ""
        assert args.outputs[0].kind == "post"


class TestOutputsDialectAbsorb:
    """顺形律 (probe E 实测 2026-09-24): the provider emits `outputs` as a
    bare object instead of a one-item list — the dialect is absorbed at the
    schema layer (wrap_single_object_list, 一个法一个家), never left to burn
    all 12 repair rounds on a params rejection."""

    def test_plan_item_bare_object_outputs_wraps(self) -> None:
        item = PlanItem.model_validate(
            {"select_id": str(uuid4()), "outputs": {"kind": "clip"}}
        )
        assert len(item.outputs) == 1
        assert item.outputs[0].kind == "clip"

    def test_plan_item_list_form_untouched(self) -> None:
        item = PlanItem.model_validate(
            {"select_id": str(uuid4()), "outputs": [{"kind": "clip"}, {"kind": "post"}]}
        )
        assert [o.kind for o in item.outputs] == ["clip", "post"]

    def test_revise_plan_bare_object_outputs_wraps(self) -> None:
        args = RevisePlanArgs.model_validate(
            {
                "plan_id": str(uuid4()),
                "instruction": "make it french",
                "outputs": {"kind": "post", "language": "fr"},
            }
        )
        assert len(args.outputs) == 1
        assert args.outputs[0].kind == "post"
        assert args.outputs[0].language == "fr"

    def test_revise_plan_list_form_untouched(self) -> None:
        args = RevisePlanArgs.model_validate(
            {"plan_id": str(uuid4()), "outputs": [{"kind": "post"}, {"kind": "article"}]}
        )
        assert [o.kind for o in args.outputs] == ["post", "article"]


class TestWireDoorCapParity:
    """校验分层律 (ADR-064): the wire's max_length mirrors the door spec's —
    an overlong verdict / reason / title rejects at the TOOL boundary (the
    loop's native params repair feeds it back), never as a raw door-side
    ValidationError escaping the echo path (2026-09-23 review catch)."""

    def test_wire_caps_match_the_door_caps(self) -> None:
        from app.pipeline.exploration_store import ContentPlanSpec, SelectSpec

        for wire_field, door_field in (
            (SelectItem.model_fields["verdict"], SelectSpec.model_fields["verdict"]),
            (SelectItem.model_fields["reason"], SelectSpec.model_fields["reason"]),
            (PlanItem.model_fields["title"], ContentPlanSpec.model_fields["title"]),
            # iter-2 ⑦: the revision verb's title wire obeys the same cap.
            (RevisePlanArgs.model_fields["title"], ContentPlanSpec.model_fields["title"]),
        ):
            wire_cap = next(
                (m.max_length for m in wire_field.metadata if hasattr(m, "max_length")),
                None,
            )
            door_cap = next(
                (m.max_length for m in door_field.metadata if hasattr(m, "max_length")),
                None,
            )
            assert wire_cap is not None and wire_cap == door_cap, (
                wire_field,
                door_field,
            )

    def test_overlong_verdict_rejects_at_the_wire(self) -> None:
        with pytest.raises(ValidationError):
            SelectItem.model_validate(
                {"member_index": 0, "verdict": "v" * 301, "reason": "r"}
            )

    def test_overlong_title_rejects_at_the_wire(self) -> None:
        with pytest.raises(ValidationError):
            PlanItem.model_validate(
                {"select_id": str(uuid4()), "title": "t" * 201, "outputs": [{"kind": "clip"}]}
            )


class TestDriftAlarm:
    """extra="forbid": the wire never licenses invented params."""

    def test_candidates_unknown_key_rejects(self) -> None:
        with pytest.raises(ValidationError):
            ProposeCandidatesArgs.model_validate({**_CANDIDATES, "asset": "the old name"})

    def test_member_unknown_key_rejects(self) -> None:
        with pytest.raises(ValidationError):
            ProposeCandidatesArgs.model_validate(
                {**_CANDIDATES, "members": [{**_MEMBER, "quote": "copied source"}]}
            )

    def test_selects_unknown_key_rejects(self) -> None:
        with pytest.raises(ValidationError):
            ProposeSelectsArgs.model_validate(
                {
                    "candidate_set_id": str(uuid4()),
                    "selects": [{"member_index": 0, "verdict": "v", "reason": "r", "score": 9}],
                }
            )

    def test_plan_output_unknown_key_rejects(self) -> None:
        with pytest.raises(ValidationError):
            ProposePlansArgs.model_validate(
                {
                    "plans": [
                        {
                            "select_id": str(uuid4()),
                            "outputs": [{"kind": "clip", "tool": "select_clips"}],
                        }
                    ]
                }
            )
