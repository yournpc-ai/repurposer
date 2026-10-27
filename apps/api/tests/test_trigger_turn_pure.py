"""Pure tests for the trigger-turn machinery (app/chat/trigger_turn.py) —
the chat edge agent's proactive speech (ADR-077 判词③, T3).

No DB, no LLM, no HTTP (suite discipline): the turn runner needs a session
and stays e2e-covered. What's gated HERE is the trigger turn's declared
contract:

- the whitelist IS the proactivity boundary (风险挂账③: 白名单外永不主动说话);
- the terminal tool's params law (ADR-081: suggestions are dock-worthy
  option labels — blanks drop, overlong rejects into the loop, null reads
  as none; the send/download pill form is retired; 一问拍一体化 2026-09-27:
  each carries a one-line reason + at most one recommended mark, bare
  strings read in as labels 读容忍);
- the suggestion dock's payload law (numbered 1/2/3 option ids the
  autoResume grammar + the dock badge share; the bare question is
  code-assembled in the turn's speech language; the recommended mark lands
  as the positional recommended_id);
- the intent dump is self-describing (the dedup guard reads the same keys);
- the worker-side speech-language chain (ADR-080 界面语言唯一 owner: the
  conversation's stamped owner first; the run's pinned ui_language and the
  history's own evidence are owner-absent fallbacks; the project's
  content-language default never votes);
- the admission gate's two predicates (in-flight → defer/drop; a docked
  pending plan → silence, ADR-080 单一叙事者律);
- the agent's tool set is the reads plus ONE terminal, bounded.
"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.chat.intent import _speech_language_line
from app.chat.service import _match_option
from app.chat.trigger_turn import (
    _FAILURE_FACT_CAP,
    TRIGGER_DUMP_TYPE,
    _chrome_language,
    _failure_fact_lines,
    _suggestions_payload,
    _trigger_admission,
    _trigger_dump,
    _trigger_language,
    _with_upload_retry_suggestion,
    _wrap_up_rejection,
    trigger_agent,
)
from app.models.schemas import SuggestionItem, WrapUpArgs
from app.models.tables import Conversation, Message, WorkflowRun, WorkflowStep
from app.pipeline.trigger_events import (
    TRIGGER_CRAFT_DECOMPILED,
    TRIGGER_RUN_COMPLETED,
    TRIGGER_RUN_FAILED,
    TRIGGER_WHITELIST,
    run_id_from_trigger_ref,
    run_trigger_ref,
)


def test_whitelist_is_the_proactivity_boundary() -> None:
    # 素材理解接力已死 (ADR-102): the wait-for-material world ended with the
    # dormant-asset law. The boundary is the three world events (a total
    # failure speaks since ADR-135 — the receipt alone carries neither the
    # reason nor the next step); adding a kind is an ADR-level review,
    # never a drive-by.
    assert TRIGGER_WHITELIST == {
        "run_completed",
        "run_failed",
        "craft_decompiled",
    }
    assert TRIGGER_RUN_COMPLETED in TRIGGER_WHITELIST
    assert TRIGGER_RUN_FAILED in TRIGGER_WHITELIST
    assert TRIGGER_CRAFT_DECOMPILED in TRIGGER_WHITELIST


def test_upload_recovery_terminals_get_fresh_dedup_refs() -> None:
    run_id = UUID("00000000-0000-0000-0000-000000000001")
    assert run_trigger_ref(run_id, TRIGGER_RUN_FAILED, {}) == str(run_id)
    first = run_trigger_ref(run_id, TRIGGER_RUN_FAILED, {"upload_retry_count": 1})
    second = run_trigger_ref(run_id, TRIGGER_RUN_FAILED, {"upload_retry_count": 2})
    assert first != second != str(run_id)
    assert (
        run_trigger_ref(run_id, TRIGGER_RUN_FAILED, {"upload_retry_count": 1})
        == first
    )
    assert run_id_from_trigger_ref(first) == run_id
    completed = run_trigger_ref(
        run_id, TRIGGER_RUN_COMPLETED, {"upload_retry_count": 2}
    )
    assert completed == second
    assert run_id_from_trigger_ref(completed) == run_id


def test_tool_set_is_the_reads_plus_one_terminal() -> None:
    from app.chat.turn_tools import CHAT_READ_TOOLS

    by_name = {t.name: t for t in trigger_agent.tools}
    # The trigger set filters CHAT_READ_TOOLS (import-time built): the
    # deployment-gated media discovery read (list_project_media) rides only
    # when the film edit capability's gate was ON at process start — the
    # expectation keys off the same source, never a frozen registry dump.
    expected = {
        "wrap_up",
        *(t.name for t in CHAT_READ_TOOLS if t.name != "design_storyboard"),
    }
    assert set(by_name) == expected
    assert by_name["wrap_up"].terminal
    assert all(
        by_name[name].terminal is False for name in expected if name != "wrap_up"
    )
    # 报价 = fold: the bound plus the reads-plus-one roster stays far under
    # the hallucination line (简报 §4 挂账① — Agno 的 20-tool 线). The budget
    # tracks the family's REGISTERED growth (16 reads + wrap_up after the
    # web pair get_web_page/search_web, 2026-10-15; +1 with the gated media
    # discovery read riding in gate-ON processes; +3 with the ADR-145 video
    # family — design_video/revise_video replace the filtered
    # design_storyboard and get_video_version joins as the version read,
    # gate-ON processes) — bump it deliberately, never silently.
    assert trigger_agent.max_iterations == 6
    assert len(trigger_agent.tools) <= 21


class TestWrapUpArgs:
    """ADR-081 选项语法统一律 + 一问拍一体化 (2026-09-27): suggestions dock as
    a real numbered options question; each carries a one-line reason and at
    most one recommended mark; the send/download pill form retired."""

    def test_null_suggestions_is_tolerated(self) -> None:
        # 打字机律牙①: the model writes null when it means "no options" —
        # the default applies instead of a rejection burning an iteration.
        args = WrapUpArgs.model_validate({"suggestions": None})
        assert args.suggestions == []

    def test_bare_strings_upgrade_to_labels(self) -> None:
        # 读容忍: the pre-integration wire shape was a bare string per
        # option — the model's old habit reads in as the label, never a
        # repair round for a cosmetic upgrade.
        args = WrapUpArgs.model_validate({"suggestions": ["做一个法语版"]})
        assert [s.label for s in args.suggestions] == ["做一个法语版"]
        assert args.suggestions[0].description == ""
        assert args.suggestions[0].recommended is False

    def test_labels_cap_at_three(self) -> None:
        with pytest.raises(ValidationError):
            WrapUpArgs.model_validate({"suggestions": ["a", "b", "c", "d"]})
        args = WrapUpArgs.model_validate({"suggestions": ["a", "b", "c"]})
        assert [s.label for s in args.suggestions] == ["a", "b", "c"]

    def test_blank_labels_drop_overlong_rejects(self) -> None:
        # A blank label means "fewer options" — dropped, not an iteration
        # burned; an overlong one cannot ride a dock row — reject.
        args = WrapUpArgs.model_validate({"suggestions": ["做一个法语版", "  "]})
        assert [s.label for s in args.suggestions] == ["做一个法语版"]
        with pytest.raises(ValidationError, match="40"):
            WrapUpArgs.model_validate({"suggestions": ["x" * 41]})

    def test_extra_recommended_marks_drop_first_wins(self) -> None:
        # 一问拍一体化: at most ONE recommendation survives — extras drop
        # silently (cosmetic, never worth a repair round).
        args = WrapUpArgs.model_validate(
            {
                "suggestions": [
                    {"label": "a", "recommended": True},
                    {"label": "b", "recommended": True},
                ]
            }
        )
        assert [s.recommended for s in args.suggestions] == [True, False]

    def test_unknown_keys_reject(self) -> None:
        with pytest.raises(ValidationError):
            WrapUpArgs.model_validate({"suggestionz": []})


class TestWrapUpGuardrail:
    """wrap_up 边界护栏 (2026-09-30 用户拍板 — execute_guardrail 同族):
    suggestions 数对 trigger 旅程法 — run_completed 硬顶 =0(下一步在收尾句,
    永不在 dock);run_failed 硬顶 =2(ADR-135: 零落地没有产物卡可骑,下一
    步 dock 成可点选项,但每个都必须是能成功的步)。素材接力已死
    (ADR-102),其硬地板律随之消亡。"""

    def test_run_completed_rejects_any_option(self) -> None:
        items = WrapUpArgs.model_validate({"suggestions": ["再做一条"]}).suggestions
        rejection = _wrap_up_rejection(TRIGGER_RUN_COMPLETED, items)
        assert rejection is not None and "suggestions=[]" in rejection

    def test_run_completed_passes_empty(self) -> None:
        assert _wrap_up_rejection(TRIGGER_RUN_COMPLETED, []) is None

    def test_run_failed_allows_the_next_step_and_one_fallback(self) -> None:
        # ADR-135: nothing landed — the dock IS the next step's affordance.
        one = WrapUpArgs.model_validate({"suggestions": ["把旁白改短,重新设计分镜"]}).suggestions
        assert _wrap_up_rejection(TRIGGER_RUN_FAILED, one) is None
        two = WrapUpArgs.model_validate(
            {"suggestions": ["把旁白改短,重新设计分镜", "再试一次"]}
        ).suggestions
        assert _wrap_up_rejection(TRIGGER_RUN_FAILED, two) is None
        assert _wrap_up_rejection(TRIGGER_RUN_FAILED, []) is None

    def test_run_failed_rejects_a_third_option(self) -> None:
        three = WrapUpArgs.model_validate({"suggestions": ["a", "b", "c"]}).suggestions
        rejection = _wrap_up_rejection(TRIGGER_RUN_FAILED, three)
        assert rejection is not None and "at most 2" in rejection

    def test_other_triggers_unpoliced(self) -> None:
        # 护栏只管有法在身的 trigger — 未来新 trigger 默认自由,
        # 立法时才进表(不过度设计律)。
        assert _wrap_up_rejection("some_future_trigger", []) is None


class TestFailureFactLines:
    """The FAILURE FACTS pure core (ADR-135): one line per failed VERDICT
    step (including render/upload fan-out), the baked
    user-facing error line carried verbatim (never re-derived), bounded
    by the cap."""

    def test_failed_verdict_steps_each_get_a_line(self) -> None:
        steps = [
            WorkflowStep(
                kind="film_narration",
                status="failed",
                error="有一句旁白调速后仍然放不下它的场景——让我重新设计分镜,把这句改短一点。",
            ),
            WorkflowStep(kind="render_film", status="skipped"),
            WorkflowStep(kind="capture", status="done"),
        ]
        lines = _failure_fact_lines(steps, frozenset())
        assert lines == [
            "FAILED STEP: film_narration — "
            "有一句旁白调速后仍然放不下它的场景——让我重新设计分镜,把这句改短一点。"
        ]

    def test_render_failures_enter_the_block(self) -> None:
        # A render/upload failure is also the run's delivery failure.
        steps = [
            WorkflowStep(kind="render_clip", status="failed", error="视频渲染失败,请重试"),
            WorkflowStep(kind="dub", status="done"),
        ]
        assert _failure_fact_lines(steps, frozenset({"render_clip"})) == [
            "FAILED STEP: render_clip — 视频渲染失败,请重试"
        ]

    def test_missing_error_reads_honestly_and_the_cap_binds(self) -> None:
        steps = [
            WorkflowStep(kind=f"step_{i}", status="failed", error=None)
            for i in range(_FAILURE_FACT_CAP + 2)
        ]
        lines = _failure_fact_lines(steps, frozenset())
        assert len(lines) == _FAILURE_FACT_CAP
        assert all("no error recorded" in line for line in lines)


class TestSuggestionsPayload:
    """The docked question built from the labels (ADR-081): numbered ids
    (the 1/2/3 grammar autoResume + the dock badge share), freeform pencil
    on, the bare question code-assembled in the turn's speech language.
    一问拍一体化 (2026-09-27): the reason line rides each option and the
    recommended mark lands as the positional recommended_id."""

    def test_numbered_options_in_order(self) -> None:
        payload = _suggestions_payload(
            [SuggestionItem(label="剪一个金句快剪版"), SuggestionItem(label="出个 30 秒精华版")],
            "zh",
        )
        assert payload.kind == "question"
        assert payload.allow_freeform is True
        assert [o.id for o in payload.options] == ["1", "2"]
        assert [o.label for o in payload.options] == [
            "剪一个金句快剪版",
            "出个 30 秒精华版",
        ]
        assert payload.recommended_id is None
        # The positional number hit resolves each option (the dock grammar).
        assert _match_option("1", payload.options).label == "剪一个金句快剪版"
        assert _match_option("2", payload.options).label == "出个 30 秒精华版"

    def test_reason_and_recommendation_ride_the_payload(self) -> None:
        payload = _suggestions_payload(
            [
                SuggestionItem(label="a", description="理由甲"),
                SuggestionItem(label="b", description="理由乙", recommended=True),
            ],
            "zh",
        )
        assert [o.description for o in payload.options] == ["理由甲", "理由乙"]
        # The mark lands as the option's POSITIONAL id (the dock grammar).
        assert payload.recommended_id == "2"

    def test_bare_question_follows_the_speech_language(self) -> None:
        # Semantic assertion: the contract is LANGUAGE-following (zh → the
        # Chinese line, en → the English line), not a frozen casing — the
        # copy is deliberate sentence-case ("What's next?"), so match
        # case-insensitively.
        assert "接下来" in _suggestions_payload([SuggestionItem(label="a")], "zh").question
        en_question = _suggestions_payload([SuggestionItem(label="a")], "en").question
        assert "next" in en_question.lower()
        assert "接下来" not in en_question


class TestUploadRetrySuggestion:
    """An upload-only recovery is a real user journey, not an LLM style
    preference: a finished render's failed upload must always offer that
    next step, recommended, with at most one honest fallback."""

    def test_retry_is_localized_recommended_and_first(self) -> None:
        for language, label in (("zh", "重新上传"), ("en", "Retry upload")):
            items = _with_upload_retry_suggestion(
                [SuggestionItem(label="重新渲染", recommended=True)], language
            )
            assert [item.label for item in items] == [label, "重新渲染"]
            assert [item.recommended for item in items] == [True, False]
            expected = "缓存" if language == "zh" else "cache"
            assert expected in items[0].description

    def test_retry_deduplicates_and_keeps_one_fallback(self) -> None:
        items = _with_upload_retry_suggestion(
            [
                SuggestionItem(label="Retry upload", recommended=True),
                SuggestionItem(label="Try a different format"),
                SuggestionItem(label="Change the storyboard"),
            ],
            "en",
        )
        assert [item.label for item in items] == [
            "Retry upload",
            "Try a different format",
        ]
        assert len(items) == 2


def test_trigger_dump_is_self_describing() -> None:
    dump = _trigger_dump(TRIGGER_RUN_COMPLETED, "run-1", [SuggestionItem(label="做一个法语版")])
    assert dump["type"] == TRIGGER_DUMP_TYPE
    assert dump["trigger"] == "run_completed"
    assert dump["ref"] == "run-1"
    # Labels ride for forensics only — the dock rebuilds from the row's
    # question payload, never from the dump.
    assert dump["suggestions"] == ["做一个法语版"]


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


class TestTriggerSpeechLanguageLaw:
    """The trigger's speech-language directive (2026-10-15 语言律修订):
    mirror=False mirrors the CONVERSATION's user messages (never the English
    system-event line), with the interface language demoted to a no-signal
    floor — the absolute interface pin split the single narrator in two."""

    def test_mirror_false_mirrors_the_conversation(self) -> None:
        line = _speech_language_line("en", mirror=False)
        assert "mirror" in line.lower()
        # The event line is named as a system signal, never the voice.
        assert "system signal" in line

    def test_mirror_false_names_the_floor_in_its_own_tongue(self) -> None:
        assert "中文" in _speech_language_line("zh", mirror=False)
        assert "English" in _speech_language_line("en", mirror=False)

    def test_mirror_false_carries_no_absolute_pin(self) -> None:
        line = _speech_language_line("zh", mirror=False).lower()
        assert "absolute" not in line
        assert "never the interface" not in line

    def test_chrome_follows_the_actual_speech(self) -> None:
        # A Chinese-bearing speech gets the zh chrome even on an en floor —
        # the model mirrored the conversation, the chrome follows it.
        assert _chrome_language("成片好了，配乐也在。", "en") == "zh"
        # A non-CJK speech rides the floor (残留列账: a German conversation
        # on an en UI gets the English title — the floor IS the fallback).
        assert _chrome_language("Der Film ist fertig.", "en") == "en"
        assert _chrome_language("Der Film ist fertig.", "zh") == "zh"
        assert _chrome_language("", "zh") == "zh"


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
    from app.platform.conversation_context import is_pending_plan

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


# ---- 交付收敛 (7276ef13 ④ 修复批 B) ----------------------------------------------
#
# run_completed rides its own READLESS agent: the deterministic DELIVERY
# FACTS block is the delivery's whole record, the review is written ONCE
# and closed — the incident's pre-read narration prelude (「先读一下这支短片
# 的当前分镜…」 merged ahead of the terminal speech) has no seat when no
# read tool exists. run_failed / craft_decompiled keep the read-bearing
# agent (their reads are the honesty base — nothing pre-assembled exists
# for a failure's cause or a skeleton's gaps).


def test_delivery_agent_holds_only_the_terminal() -> None:
    """The run_completed roster: wrap_up alone (terminal), thrice-bounded —
    a read-bearing delivery opened with process narration; with no reads
    on the roster that prelude is structurally impossible."""
    from app.chat.trigger_turn import delivery_agent

    assert delivery_agent.name == "trigger_delivery"
    assert [t.name for t in delivery_agent.tools] == ["wrap_up"]
    assert delivery_agent.tools[0].terminal
    assert delivery_agent.max_iterations == 3
    # The read-bearing agent is untouched (the failure/skeleton turns keep
    # their eyes — locked by test_tool_set_is_the_reads_plus_one_terminal).
    assert any(t.name == "get_run_status" for t in trigger_agent.tools)


def test_delivery_system_prompt_never_invites_a_read() -> None:
    """run_completed has its own readless, outcome-branched prompt. The
    failure/craft prompt keeps its read invitations instead of carrying a
    second copy of the delivery law."""
    from app.chat.prompts import delivery_system, trigger_system

    delivery = delivery_system()
    general = trigger_system()
    for tool_name in ("get_output_spec", "get_run_status", "get_craft_skeleton"):
        assert tool_name not in delivery
    for tool_name in ("get_run_status", "get_craft_skeleton"):
        assert tool_name in general
    assert "READ TOOLS" in general
    assert "READ TOOLS" not in delivery
    assert "latest tool and run outcome" in delivery
    assert "selects exactly ONE branch" in delivery
    for branch in ("delivery=failed", "delivery=partial", "delivery=delivered"):
        assert branch in delivery
    assert "run_completed" not in general


@pytest.mark.parametrize("canvas_visible", [True, False, None])
def test_delivery_prompt_has_no_surface_handoff_and_keeps_output_ids_internal(
    canvas_visible,
) -> None:
    """Every canvas state gets the same delivery-only speech law. The
    assembled user context still carries output ids for internal location."""
    from app.agents.base import jinja_env
    from app.chat.trigger_turn import delivery_agent

    output_id = "00000000-0000-0000-0000-000000000001"
    environment = (
        ""
        if canvas_visible is None
        else f"Environment: canvas_visible={str(canvas_visible).lower()}"
    )
    context_text = "\n".join(
        part
        for part in (environment, "Current outputs:", f"- film id={output_id}")
        if part
    )
    template_kwargs, _ = delivery_agent.assemble(
        event_line="Delivery turn. Use the DELIVERY FACTS.",
        context_text=context_text,
        language="en",
    )
    user_prompt = jinja_env.get_template(delivery_agent.prompt).render(
        **template_kwargs
    )
    assert output_id in user_prompt

    prompt = delivery_agent.system
    lowered = prompt.lower()
    for retired in ("canvas_visible", "card", "tappable", "handoff"):
        assert retired not in lowered
    assert "actual delivery outcome" in prompt
    assert "interface entry points or navigation" in prompt
    assert "Internal identifiers in the context never appear in the reply" in prompt
    assert "`id=` values are lookup keys" in prompt


def test_delivery_event_line_carries_the_latest_outcome() -> None:
    """The event line pairs conversation context with deterministic latest
    tool/run facts and one matching reply branch. An empty block (a legacy
    run / the fire-and-forget degrade) says so honestly."""
    from app.chat.trigger_turn import _delivery_event_line

    line = _delivery_event_line("run-1", ["LANDED film: x", "GAP: y"])
    assert "DELIVERY FACTS" in line
    assert "LANDED film: x" in line and "GAP: y" in line
    assert "wrap_up" in line
    assert "Review what it produced" not in line  # the retired read order
    legacy = _delivery_event_line("run-2", [])
    assert "never invent" in legacy
    assert "DELIVERY FACTS" not in legacy
