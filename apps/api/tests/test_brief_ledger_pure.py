"""Tests for the BriefLedger 顺形律 + 校验分层律 (ADR-064, 2026-09-11).

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP):
- constraints 的正典形状 = 来源化条目数组（模型的第一直觉写法）；
- 边界归一化接住三种来路（旧对象包数组 / 裸字符串条目 / off-enum 来源）；
- 校验分层：brief 账本归一化后仍无法解析时丢字段不杀回合（关键载荷
  action/tasks/answer 已严格校验）。
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    BriefLedger,
    BriefSlot,
    BriefSlotSource,
    InferredIntent,
)


class TestConstraintsNormalization:
    def test_canonical_shape_is_a_list_of_sourced_items(self):
        ledger = BriefLedger.model_validate(
            {
                "constraints": [
                    {"value": "keep 1:1", "source": "user-stated"},
                    {"value": "no stock narrator", "source": "inferred"},
                ]
            }
        )
        assert [c.value for c in ledger.constraints] == [
            "keep 1:1",
            "no stock narrator",
        ]
        assert ledger.constraints[0].source == BriefSlotSource.USER_STATED

    def test_legacy_object_wrapped_list(self):
        """存量 pending_brief 行：对象包数组 → 逐项展开，来源继承。"""
        ledger = BriefLedger.model_validate(
            {"constraints": {"value": ["a", "b"], "source": "user-stated"}}
        )
        assert [c.value for c in ledger.constraints] == ["a", "b"]
        assert all(c.source == BriefSlotSource.USER_STATED for c in ledger.constraints)

    def test_legacy_object_wrapped_bare_string(self):
        """修复轮曾产出的形状：对象包一整句字符串 → 单条目。"""
        ledger = BriefLedger.model_validate(
            {"constraints": {"value": "one long sentence", "source": "inferred"}}
        )
        assert [c.value for c in ledger.constraints] == ["one long sentence"]

    def test_bare_string_items(self):
        ledger = BriefLedger.model_validate({"constraints": ["keep 1:1"]})
        assert [c.value for c in ledger.constraints] == ["keep 1:1"]

    def test_off_enum_source_coerces_to_inferred(self):
        """模型自造来源词（"explicit"/"user_request"）降 inferred——永不把
        来路不明的值升格成 user-stated。"""
        ledger = BriefLedger.model_validate(
            {"constraints": [{"value": "x", "source": "explicit"}]}
        )
        assert ledger.constraints[0].source == BriefSlotSource.INFERRED

    def test_unrecognizable_shape_reads_as_no_opinion(self):
        """完全无法辨认的 constraints 按无意见处理——簿记不杀回合。"""
        ledger = BriefLedger.model_validate({"constraints": 42})
        assert ledger.constraints == []

    def test_null_is_no_opinion(self):
        assert BriefLedger.model_validate({"constraints": None}).constraints == []

    def test_typed_instances_pass_through(self):
        """代码侧构造路径（BriefSlot 实例直传）不被归一化吞掉。"""
        ledger = BriefLedger(
            constraints=[BriefSlot(value="keep 1:1", source=BriefSlotSource.USER_STATED)]
        )
        assert [c.value for c in ledger.constraints] == ["keep 1:1"]


class TestLayeredValidation:
    """校验分层律：brief 是咨询性簿记——garbled 账本丢字段，回合照活。"""

    def test_garbled_brief_drops_the_field_not_the_turn(self):
        intent = InferredIntent.model_validate(
            {
                "action": "draft",
                "answer": "Got it — drafting the plan.",
                "tasks": [{"tool": "write_post", "params": {}}],
                "brief": {"topic": ["not", "a", "slot"]},
            }
        )
        assert intent.action == "draft"
        assert intent.brief is None
        assert [t.tool for t in intent.tasks] == ["write_post"]

    def test_well_formed_brief_survives(self):
        intent = InferredIntent.model_validate(
            {
                "action": "draft",
                "answer": "Got it.",
                "tasks": [{"tool": "write_post", "params": {}}],
                "brief": {"topic": {"value": "grid storage", "source": "user-stated"}},
            }
        )
        assert intent.brief is not None
        assert intent.brief.topic.value == "grid storage"

    def test_critical_payload_stays_strict(self):
        """分层不是松化：关键载荷（tasks 形状）仍然严格拒收。"""
        with pytest.raises(ValidationError):
            InferredIntent.model_validate(
                {"action": "draft", "answer": "x", "tasks": [{"skill": "write_post"}]}
            )
