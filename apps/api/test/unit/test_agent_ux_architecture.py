"""Unit contracts for the Antigravity-grade Agent UX architecture upgrades.

Covers:
1. BriefQuestionItem read-tolerance for omitted options[].value (zero retry tax)
2. ChatMessageResponse deterministic display_role & run_id projection (Live == Replay)
3. RunEventBus multi-subscriber fan-out, live snapshot, and terminal cleanup
4. Localized Failure Checkpoint generation (no raw 'Internal server error' leaks)
5. analyze_brand batchability alignment with video_editor.j2
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.chat.routes import _build_failure_checkpoint, _failure_detail
from app.chat.run_bus import RunEventBus
from app.chat.turn_tools import _video_material_tools
from app.models.schemas import (
    AnalyzeBrandArgs,
    BriefQuestionItem,
    ChatMessageResponse,
    MessageRole,
)


@pytest.mark.unit
def test_brief_question_item_infers_missing_option_values() -> None:
    """Reproduces the 18-error ask_user payload where the model omitted `value`."""
    direction = BriefQuestionItem.model_validate(
        {
            "slot": "production_direction",
            "question": "这条片子主要讲什么？",
            "options": [
                {"id": "dir_workflow", "label": "产品工作流实演", "description": "四步闭环"},
                {"id": "dir_pain", "label": "痛点与信任背书"},
            ],
        }
    )
    assert direction.options[0].value == "产品工作流实演"

    seconds = BriefQuestionItem.model_validate(
        {
            "slot": "target_seconds",
            "question": "成片时长？",
            "recommended_id": 45,
            "options": [
                {"id": 30, "label": "30 秒"},
                {"id": 45, "label": "45 秒"},
                {"id": 60, "label": "60 秒"},
            ],
        }
    )
    assert seconds.recommended_id == "45"
    assert seconds.options[0].id == "30"
    assert seconds.options[0].value == 30
    assert seconds.options[1].id == "45"
    assert seconds.options[1].value == 45

    subs = BriefQuestionItem.model_validate(
        {
            "slot": "subtitle_languages",
            "question": "字幕语言？",
            "options": [
                {"id": "en", "label": "英文"},
                {"id": "zh_en", "label": "中英双语"},
            ],
        }
    )
    assert subs.options[0].value == ["en"]
    assert subs.options[1].value == ["zh", "en"]


@pytest.mark.unit
def test_chat_message_response_projects_display_role_and_run_id() -> None:
    now = datetime.now(UTC)
    base = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": MessageRole.ASSISTANT,
        "created_at": now,
    }

    stage_note = ChatMessageResponse.model_validate(
        {
            **base,
            "content": "我先把官网采集完成，拿到真实页面内容再动手。",
            "intent": {"type": "interim_prose", "run_id": "run-1"},
        }
    )
    assert stage_note.display_role == "stage_note"
    assert stage_note.run_id == "run-1"

    framing = ChatMessageResponse.model_validate(
        {
            **base,
            "content": (
                "官网已经采到真实内容了。OxValue 是一家做专利与无形资产估值的受治理 AI 工作台，"
                "核心主张是 Value what others cannot see。下面确认几个关键偏好。"
            ),
            "question": {"kind": "question", "question": "OxValue 宣传片的关键偏好", "items": [{"slot": "target_seconds"}]},
            "intent": {"run_id": "run-1"},
        }
    )
    assert framing.display_role == "question_framing"

    stub = ChatMessageResponse.model_validate(
        {
            **base,
            "content": "请确认下面几项。",
            "question": {"kind": "question", "question": "确认偏好", "items": [{"slot": "target_seconds"}]},
        }
    )
    assert stub.display_role == "question_framing_stub"

    failure = ChatMessageResponse.model_validate(
        {
            **base,
            "content": "创建初稿时遇到系统异常",
            "intent": {"type": "turn_failed", "run_id": "run-2"},
        }
    )
    assert failure.display_role == "failure_checkpoint"
    assert failure.run_id == "run-2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_event_bus_tracks_snapshot_and_fans_out() -> None:
    bus = RunEventBus()
    conv_id = uuid4()
    turn_id = uuid4()
    bus.start_run(conv_id, run_id="run-abc", turn_id=turn_id)

    async with bus.subscribe(conv_id) as (state, sub_q):
        assert state is not None and sub_q is not None
        focus_frame = 'event: assistant.activity\ndata: {"kind":"focus","focus":"正在采集官网"}\n\n'
        steps_frame = 'event: assistant.activity\ndata: {"kind":"steps","steps":[{"title":"采集","status":"done"}]}\n\n'
        bus.observe_frame(conv_id, "run-abc", focus_frame)
        bus.observe_frame(conv_id, "run-abc", steps_frame)

        summary = bus.active_run_summary(conv_id)
        assert summary is not None
        assert summary["live_focus"] == "正在采集官网"
        assert summary["steps"] == [{"title": "采集", "status": "done"}]
        assert await sub_q.get() == focus_frame
        assert await sub_q.get() == steps_frame

        terminal = 'event: turn.completed\ndata: {}\n\n'
        bus.finish_run(conv_id, "run-abc", "completed", terminal_sse=terminal)
        assert await sub_q.get() == terminal
        assert await sub_q.get() is None

    assert bus.active_run_summary(conv_id) is None


@pytest.mark.unit
def test_failure_detail_and_checkpoint_never_leak_raw_internal_error() -> None:
    zh_msg = _failure_detail(RuntimeError("boom"), "zh-CN", decision_committed=True)
    assert isinstance(zh_msg, str)
    assert "Internal server error" not in zh_msg
    assert "安全保留" in zh_msg

    cp = _build_failure_checkpoint(
        RuntimeError("boom"), zh_msg, run_id="run-2", decision_committed=True
    )
    assert cp is not None
    assert cp["retryable"] is True
    assert cp["decision_committed"] is True
    assert cp["run_id"] == "run-2"


@pytest.mark.unit
def test_analyze_brand_is_batchable() -> None:
    tools = {t.name: t for t in _video_material_tools()}
    assert tools["analyze_brand"].batchable is True


@pytest.mark.unit
def test_analyze_brand_args_tolerates_flat_fields_bare_values_and_extras() -> None:
    """Models often pass flat brief fields or bare scalars to analyze_brand;
    validation must accept them on the first try instead of burning 2 retry loops."""
    parsed = AnalyzeBrandArgs.model_validate(
        {
            "url": "https://agent.oxvalue.ai/",
            "brand_name": "OxValue",
            "target_seconds": 45,
            "narration_language": "en",
            "subtitle_languages": ["en"],
            "production_direction": "产品工作流实演",
        }
    )
    assert parsed.brief is not None
    assert parsed.brief.target_seconds.value == 45
    assert parsed.brief.narration_language.value == "en"
    assert parsed.brief.subtitle_languages.value == ["en"]
    assert parsed.brief.production_direction.value == "产品工作流实演"

    nested_bare = AnalyzeBrandArgs.model_validate(
        {
            "brief": {
                "target_seconds": 30,
                "narrative_mode": "voiceover",
                "unknown_key": "ignored",
            }
        }
    )
    assert nested_bare.brief is not None
    assert nested_bare.brief.target_seconds.value == 30
    assert nested_bare.brief.narrative_mode.value == "voiceover"


@pytest.mark.unit
def test_chat_message_response_distinguishes_stage_note_and_rail_note() -> None:
    now = datetime.now(UTC)
    base = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": MessageRole.ASSISTANT,
        "created_at": now,
    }
    opening_note = ChatMessageResponse.model_validate(
        {**base, "content": "方向已确认，我现在开始备料。", "intent": {"type": "interim_prose", "run_id": "r2"}}
    )
    mid_run_note = ChatMessageResponse.model_validate(
        {
            **base,
            "content": "官网截图齐了，现在读积木参数。",
            "intent": {"type": "interim_prose", "run_id": "r2", "rail_note": True},
        }
    )
    assert opening_note.display_role == "stage_note"
    assert mid_run_note.display_role == "rail_note"
