"""Pure tests for the trigger-turn machinery (app/chat/trigger_turn.py) —
the chat edge agent's proactive speech (ADR-077 判词③, T3).

No DB, no LLM, no HTTP (suite discipline): the turn runner needs a session
and stays e2e-covered. What's gated HERE is the trigger turn's declared
contract:

- the whitelist IS the proactivity boundary (风险挂账③: 白名单外永不主动说话);
- the terminal tool's params law (suggestions are user-voice pills — a send
  without its text / a download without its output is a dead click, rejected
  at the schema so the loop iterates instead);
- the intent dump is self-describing (replay and the dedup guard read the
  same keys);
- the worker-side speech-language chain (ADR-080 界面语言唯一 owner: the
  conversation's stamped owner first; the run's pinned ui_language and the
  history's own evidence are owner-absent fallbacks; the project's
  content-language default never votes);
- the admission gate's two predicates (in-flight → defer/drop; a docked
  pending plan → silence, ADR-080 单一叙事者律);
- the agent's tool set is the reads plus ONE terminal, bounded.
"""

import pytest
from pydantic import ValidationError

from app.chat.perception import PERCEPTION_TOOLS
from app.chat.trigger_turn import (
    TRIGGER_CRAFT_DECOMPILED,
    TRIGGER_DUMP_TYPE,
    TRIGGER_RUN_COMPLETED,
    TRIGGER_UNDERSTANDING,
    TRIGGER_WHITELIST,
    _trigger_admission,
    _trigger_dump,
    _trigger_language,
    trigger_agent,
)
from app.models.schemas import Suggestion, WrapUpArgs
from app.models.tables import Conversation, Message, WorkflowRun


def test_whitelist_is_the_proactivity_boundary() -> None:
    # 案例拆解完成 (ADR-078 判词③ whitelist #3, 批次⑥ T5) joined on 2026-09-15.
    assert TRIGGER_WHITELIST == {
        "understanding_warmed",
        "run_completed",
        "craft_decompiled",
    }
    assert TRIGGER_UNDERSTANDING in TRIGGER_WHITELIST
    assert TRIGGER_RUN_COMPLETED in TRIGGER_WHITELIST
    assert TRIGGER_CRAFT_DECOMPILED in TRIGGER_WHITELIST


def test_tool_set_is_the_reads_plus_one_terminal() -> None:
    by_name = {t.name: t for t in trigger_agent.tools}
    assert set(by_name) == {"wrap_up", *PERCEPTION_TOOLS}
    assert by_name["wrap_up"].terminal
    assert all(
        by_name[name].terminal is False for name in PERCEPTION_TOOLS
    )
    # 报价 = fold: the bound plus the reads-plus-one roster stays far under
    # the hallucination line (简报 §4 挂账①).
    assert trigger_agent.max_iterations == 6
    assert len(trigger_agent.tools) <= 12


class TestSuggestionParamsLaw:
    def test_send_pill_needs_its_text(self) -> None:
        with pytest.raises(ValidationError, match="text"):
            Suggestion.model_validate(
                {"label": "法语版", "action": "send"}
            )

    def test_download_pill_needs_a_real_output_seat(self) -> None:
        with pytest.raises(ValidationError, match="output_id"):
            Suggestion.model_validate(
                {"label": "下载", "action": "download"}
            )

    def test_legal_pills_validate(self) -> None:
        send = Suggestion.model_validate(
            {"label": "做一个法语版", "action": "send", "text": "把这条做成法语版"}
        )
        assert send.text == "把这条做成法语版"
        download = Suggestion.model_validate(
            {
                "label": "Download the video",
                "action": "download",
                "output_id": "3f4a5b6c-7d8e-4f0a-b1c2-d3e4f5a6b7c8",
            }
        )
        assert download.output_id is not None

    def test_labels_are_capped(self) -> None:
        with pytest.raises(ValidationError):
            Suggestion.model_validate(
                {"label": "x" * 41, "action": "send", "text": "go"}
            )


class TestWrapUpArgs:
    def test_null_suggestions_is_tolerated(self) -> None:
        # 打字机律牙①: the model writes null when it means "no pills" —
        # the default applies instead of a rejection burning an iteration.
        args = WrapUpArgs.model_validate({"suggestions": None})
        assert args.suggestions == []

    def test_pills_cap_at_three(self) -> None:
        pill = {"label": "go", "action": "send", "text": "go"}
        with pytest.raises(ValidationError):
            WrapUpArgs.model_validate({"suggestions": [pill] * 4})
        args = WrapUpArgs.model_validate({"suggestions": [pill] * 3})
        assert len(args.suggestions) == 3

    def test_unknown_keys_reject(self) -> None:
        with pytest.raises(ValidationError):
            WrapUpArgs.model_validate({"suggestionz": []})


def test_trigger_dump_is_self_describing() -> None:
    pill = Suggestion.model_validate(
        {
            "label": "Download",
            "action": "download",
            "output_id": "3f4a5b6c-7d8e-4f0a-b1c2-d3e4f5a6b7c8",
        }
    )
    dump = _trigger_dump(TRIGGER_RUN_COMPLETED, "run-1", [pill])
    assert dump["type"] == TRIGGER_DUMP_TYPE
    assert dump["trigger"] == "run_completed"
    assert dump["ref"] == "run-1"
    # JSON-mode dump (the row's intent column is plain JSON) — the UUID
    # serialized to its string form.
    assert dump["suggestions"] == [
        {
            "label": "Download",
            "action": "download",
            "text": None,
            "output_id": "3f4a5b6c-7d8e-4f0a-b1c2-d3e4f5a6b7c8",
        }
    ]


class TestTriggerLanguage:
    """Worker-born speech language (ADR-080 界面语言唯一 owner): the
    conversation's stamped ui_language owner wins first; the run's pin and
    the history's own evidence are the owner-absent fallbacks; "en" last.
    The project's content-language default never votes (a defaulted "zh"
    content language must not drag an English conversation's proactive
    speech into Chinese)."""

    def test_conversation_owner_wins_over_everything(self) -> None:
        conversation = Conversation(ui_language="zh")
        run = WorkflowRun(context={"ui_language": "en"})
        history = [Message(role="user", content="make me a post")]
        assert _trigger_language(run, history, conversation) == "zh"

    def test_run_pin_is_the_first_fallback(self) -> None:
        run = WorkflowRun(context={"ui_language": "zh"})
        history = [Message(role="user", content="make me a post")]
        assert _trigger_language(run, history) == "zh"
        # An ownerless conversation behaves like no conversation.
        assert (
            _trigger_language(run, history, Conversation(ui_language=None))
            == "zh"
        )

    def test_latest_user_message_is_the_evidence(self) -> None:
        history = [
            Message(role="user", content="帮我剪三条短片"),
            Message(role="assistant", content="好的"),
        ]
        assert _trigger_language(None, history) == "zh"
        history.append(Message(role="user", content="actually, one post"))
        assert _trigger_language(None, history) == "en"

    def test_no_evidence_falls_to_en(self) -> None:
        assert _trigger_language(None, []) == "en"
        # Assistant-only history is not evidence either.
        assert (
            _trigger_language(None, [Message(role="assistant", content="你好")])
            == "en"
        )


# ---- Turn admission (交互完整性批 B, 2026-09-17) ------------------------------
#
# The gate's pure decision law: a proactive turn NEVER overtakes an in-flight
# user turn — defer while the politeness bound holds, drop into silence at
# the bound (never blind speech). The DB read itself stays e2e-covered
# (S19's mid-turn fire).


def test_admission_proceeds_when_no_user_turn_is_in_flight() -> None:
    assert _trigger_admission(False, 0, 15) == "proceed"
    assert _trigger_admission(False, 15, 15) == "proceed"


def test_admission_defers_while_the_bound_holds() -> None:
    assert _trigger_admission(True, 0, 15) == "defer"
    assert _trigger_admission(True, 14, 15) == "defer"


def test_admission_drops_at_the_bound_never_speaks_blind() -> None:
    assert _trigger_admission(True, 15, 15) == "drop"
    assert _trigger_admission(True, 99, 15) == "drop"


# ---- Pending-plan silence (ADR-080 单一叙事者律, 2026-09-17) ------------------
#
# The gate's second predicate: no turn in flight, but a plan sits docked
# awaiting Start → the trigger stays SILENT (its "what I saw" narration is
# already covered by the plan's echo prose — speaking again is pure
# microphone-grabbing). The predicate itself is the shared is_pending_plan;
# what's locked HERE is that the trigger's silence consumes exactly it.


def test_pending_plan_silence_reads_is_pending_plan() -> None:
    from app.chat.service import is_pending_plan

    # An unanswered task_book row = a docked plan = silence.
    docked = Message(
        role="assistant",
        content="plan",
        question={"kind": "task_book", "options": []},
    )
    assert is_pending_plan(docked) is True
    # Answered plans and generic questions do NOT silence the trigger.
    answered = Message(
        role="assistant",
        content="plan",
        question={"kind": "task_book", "options": []},
        answer={"kind": "start"},
    )
    assert is_pending_plan(answered) is False
    generic = Message(
        role="assistant",
        content="q",
        question={"kind": "question", "options": [{"id": "a", "label": "x"}]},
    )
    assert is_pending_plan(generic) is False
    assert is_pending_plan(None) is False
