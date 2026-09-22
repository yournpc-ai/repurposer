"""Pure tests for the exploration terminal tool family (app/chat/exploration_tools.py)
— the agent's product-semantic proposal verbs for the discovery chain
(ADR-088 §2; 施工合同 docs/tasks/agent-working-loop-iter-1.md §6).

No DB, no LLM, no HTTP (suite discipline): the execute half needs a session
and stays covered by the door's own suite (test_exploration_store_pure.py)
plus the iter-1 scenario. What's gated HERE:

- the registry's shape (three verbs, ALL terminal — 终态工具一调即停; the
  reads stay the perception family's seat);
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
)

_MEMBER = {"start": 12.0, "end": 18.5, "excerpt": "pricing is hard"}
_CANDIDATES = {
    "asset_id": str(uuid4()),
    "topic": "pricing",
    "goal": "find the pricing sections",
    "members": [_MEMBER],
}


class TestRegistryShape:
    def test_three_terminal_verbs(self) -> None:
        assert set(EXPLORATION_TOOLS) == {
            "propose_candidates",
            "propose_selects",
            "propose_plans",
        }
        for name, tool in EXPLORATION_TOOLS.items():
            assert tool.name == name
            assert tool.terminal, name  # 终态工具一调即停
            assert tool.params_model is not None, name
            assert tool.description.strip(), name

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
