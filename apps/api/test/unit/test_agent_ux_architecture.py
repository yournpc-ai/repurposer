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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_loop_clears_active_rejections_after_tool_succeeds_and_redirects_create_video() -> None:
    """Reproduces 43748dc1: after create_video fails twice and then SUCCEEDS on
    iteration 2 (saving v1), a later post-v1 attempt to call create_video (which
    is retired from round_tools) must NOT inherit the 2 pre-success rejections to
    trigger immediate no_progress; instead it receives an actionable edit redirect
    and recovers cleanly."""
    from pydantic import BaseModel

    from app.agents.base import AGENTS
    from app.agents.tool_loop import (
        ChatTool,
        RoundAssembly,
        ToolLoopAgent,
        ToolObservation,
    )
    from app.chat.turn_tools import video_rejection_stop
    from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration

    class CreateArgs(BaseModel):
        valid: bool = False

    class EditArgs(BaseModel):
        note: str = ""

    class AnswerArgs(BaseModel):
        ok: bool = True

    create_tool = ChatTool(name="create_video", terminal=False, description="create", params_model=CreateArgs)
    edit_tool = ChatTool(name="update_motion_block", terminal=False, description="edit", params_model=EditArgs)
    answer_tool = ChatTool(name="answer", terminal=True, description="answer", params_model=AnswerArgs)

    scripted = [
        # Iter 0 & 1: create_video rejected twice with different reasons
        ToolGeneration(content="", tool_calls=[ToolCall(id="c0", name="create_video", arguments={"valid": False})]),
        ToolGeneration(content="", tool_calls=[ToolCall(id="c1", name="create_video", arguments={"valid": False})]),
        # Iter 2: create_video succeeds and saves v1!
        ToolGeneration(content="", tool_calls=[ToolCall(id="c2", name="create_video", arguments={"valid": True})]),
        # Iter 3: model accidentally calls retired create_video after v1 exists
        ToolGeneration(content="", tool_calls=[ToolCall(id="c3", name="create_video", arguments={"valid": True})]),
        # Iter 4: model follows actionable redirect to update_motion_block
        ToolGeneration(content="", tool_calls=[ToolCall(id="c4", name="update_motion_block", arguments={"note": "fix"})]),
        # Iter 5: finishes cleanly
        ToolGeneration(content="已基于初稿 v1 完成修订。", tool_calls=[ToolCall(id="c5", name="answer", arguments={"ok": True})]),
    ]
    seen_feedback: list[str] = []

    class FakeClient:
        provider = "fake"
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, *, messages, tools, **_kwargs):
            for msg in messages:
                content = msg.get("content")
                if isinstance(content, str) and "不再提供 create_video" in content:
                    seen_feedback.append(content)
            return scripted.pop(0)

    agent_name = f"test_recovery_{uuid4().hex[:8]}"
    loop = ToolLoopAgent(
        name=agent_name,
        system="chat/system.j2",
        prompt="chat/user.j2",
        tools=[create_tool, edit_tool, answer_tool],
        max_iterations=8,
        assemble=lambda **_kw: ({}, None),
        client=FakeClient(),
    )

    fail_count = 0

    async def execute(name: str, params, _prose: str):
        nonlocal fail_count
        if name == "create_video":
            if not params.valid:
                fail_count += 1
                return f"duration mismatch #{fail_count}"
            return ToolObservation("saved v1", ok=True, version_saved=True)
        if name == "update_motion_block":
            return ToolObservation("edited v2", ok=True, version_saved=True)
        return None

    def assembler(*, version_saved: bool, **_kw):
        offered = [edit_tool, answer_tool] if version_saved else [create_tool, edit_tool, answer_tool]
        return RoundAssembly(tools=offered, system="sys", enforce_offered_tools=True)

    try:
        result = await loop.call_loop(
            execute,
            round_assembler=assembler,
            should_stop_rejection=video_rejection_stop,
        )
    finally:
        AGENTS.pop(agent_name, None)
    assert result.no_progress_tool is None
    assert result.tool_name == "answer"
    assert "update_motion_block" in result.calls
    assert seen_feedback, "expected actionable redirect telling model to use edit tools instead of create_video"
    # Full forensic log still records all 3 rejections
    assert len(result.rejections) == 3


@pytest.mark.asyncio
async def test_write_receipts_survive_version_bumps_and_stale_preview_keeps_compact_receipt():
    """Live E2E 0db96fa1 regression:
    1) Write tool receipts (create_video, generate_sfx, update_motion_block) must NOT vanish from
       observation_tail when a later write bumps the composition version; otherwise the model
       forgets it created v1 or placed SFX and duplicates work.
    2) preview_range (valid_for_key + images + project_text) must strip stale base64 images when a
       newer version is saved while keeping its compact project_text window receipt.
    """
    from app.agents.tool_loop import (
        AGENTS,
        ChatTool,
        ContextSnapshot,
        RoundAssembly,
        ToolLoopAgent,
        ToolObservation,
    )
    from app.models.schemas import MediaInput, MediaInputType
    from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration
    from pydantic import BaseModel

    class EmptyArgs(BaseModel):
        pass

    class AnswerArgs(BaseModel):
        text: str = "done"

    sfx_tool = ChatTool(name="generate_sfx", description="sfx", params_model=EmptyArgs, terminal=False)
    preview_tool = ChatTool(name="preview_range", description="preview", params_model=EmptyArgs, terminal=False)
    edit_tool = ChatTool(name="update_motion_block", description="edit", params_model=EmptyArgs, terminal=False)
    answer_tool = ChatTool(name="answer", description="done", params_model=AnswerArgs, terminal=True)

    observed_requests: list[list[dict]] = []

    class FakeClient:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        def __init__(self):
            self.step = 0

        async def generate_with_tools(self, *, messages, **_kw):
            observed_requests.append(messages)
            self.step += 1
            if self.step == 1:
                return ToolGeneration(content="", tool_calls=[ToolCall(id="c1", name="generate_sfx", arguments={})])
            if self.step == 2:
                return ToolGeneration(content="", tool_calls=[ToolCall(id="c2", name="preview_range", arguments={})])
            if self.step == 3:
                return ToolGeneration(content="", tool_calls=[ToolCall(id="c3", name="update_motion_block", arguments={})])
            return ToolGeneration(content="ok", tool_calls=[ToolCall(id="c4", name="answer", arguments={"text": "ok"})])

    current_version = ["composition:v1:d1"]

    async def refresh_context():
        return ContextSnapshot(text="ctx", keys=frozenset(current_version))

    async def execute(name, _params, _prose):
        if name == "generate_sfx":
            current_version[0] = "composition:v2:d2"
            return ToolObservation('{"placed": true, "recipe_id": "deep_hit", "at": 0.15}', ok=True, version_saved=True)
        if name == "preview_range":
            img = MediaInput(
                type=MediaInputType.IMAGE,
                mime="image/png",
                data_url="data:image/png;base64,ZmFrZS1wbmctYnl0ZXM=",
            )
            return ToolObservation(
                '{"window_seconds": [0, 12], "full": true}',
                ok=True,
                images=(img,),
                valid_for_key="composition:v2:d2",
                project_text='{"window_seconds": [0, 12], "frames_omitted_after_newer_version": true}',
            )
        if name == "update_motion_block":
            current_version[0] = "composition:v3:d3"
            return ToolObservation('{"edited": "clp_mg_14"}', ok=True, version_saved=True)
        return None

    agent_name = "test_write_receipts_and_preview_compact"
    AGENTS.pop(agent_name, None)
    loop = ToolLoopAgent(
        name=agent_name,
        system="chat/system.j2",
        prompt="chat/user.j2",
        assemble=lambda **_kw: ({}, None),
        tools=[sfx_tool, preview_tool, edit_tool, answer_tool],
        max_iterations=6,
        client=FakeClient(),
    )

    try:
        result = await loop.call_loop(
            execute,
            refresh_context=refresh_context,
            round_assembler=lambda **_kw: RoundAssembly(
                tools=[sfx_tool, preview_tool, edit_tool, answer_tool],
                system="sys",
            ),
        )
    finally:
        AGENTS.pop(agent_name, None)

    assert result.tool_name == "answer"
    # On step 4 (after v3 saved), inspect what the model saw in tool messages:
    final_msgs = observed_requests[-1]
    tool_msgs = {m["tool_call_id"]: m for m in final_msgs if m.get("role") == "tool"}
    # 1) generate_sfx write receipt survived v2 -> v3 version bump!
    assert "c1" in tool_msgs
    assert "deep_hit" in str(tool_msgs["c1"]["content"])
    # 2) preview_range survived as compact text receipt with NO stale image bytes!
    assert "c2" in tool_msgs
    c2_content = tool_msgs["c2"]["content"]
    assert isinstance(c2_content, str), f"expected image-free string receipt, got {type(c2_content)}"
    assert "frames_omitted_after_newer_version" in c2_content
    assert "ZmFrZS1wbmctYnl0ZXM=" not in c2_content
    # 3) update_motion_block write receipt is present too
    assert "c3" in tool_msgs


def test_search_voices_uses_voices_activity_key():
    from app.chat.perception import perception_chat_tools

    tools = {t.name: t for t in perception_chat_tools("search_voices", "search_music")}
    assert tools["search_voices"].presentation.active_key == "chat.inspecting.voices"
    assert tools["search_music"].presentation.active_key == "chat.inspecting.music"


def test_coerce_motion_block_props_covers_zoom_follows_click_and_int_fields():
    from app.editing.revisions import coerce_motion_block_props
    from app.editing.schemas import validate_motion_block_props

    coerced = coerce_motion_block_props(
        "zoom_follows_click",
        {
            "theme": "dark",
            "headline": "Every figure keeps its evidence",
            "target_x": "0.84",
            "target_y": "0.45",
            "zoom_scale": "1.7",
            "click_at_ratio": "0.4",
            "show_backdrop": "true",
        },
    )
    validated = validate_motion_block_props("zoom_follows_click", coerced)
    assert validated.target_x == 0.84
    assert validated.target_y == 0.45
    assert validated.click_at_ratio == 0.4
    assert validated.show_backdrop is True


def test_project_editor_reply_preserves_workbench_deep_links():
    from app.chat.editor import project_editor_reply

    out_id = "0dc71ce0-08e1-5b89-bdff-6b5494588de0"
    ver_id = "452cc303-db44-4a76-bf4b-0df7b46ff55f"
    labels = {
        out_id: ("这份素材", "this media"),
        ver_id: ("第 32 版", "version 32"),
    }
    raw = (
        f"[打开成片](#workbench:output/{out_id}) ｜ "
        f"[分镜脚本](#workbench:storyboard/{ver_id})\n"
        f"已基于 {ver_id} 导出 {out_id}。"
    )
    projected = project_editor_reply(raw, labels, "导出成片")
    assert f"(#workbench:output/{out_id})" in projected
    assert f"(#workbench:storyboard/{ver_id})" in projected
    assert "已基于 第 32 版 导出 这份素材。" in projected


def test_pause_tags_strip_from_captions_and_parse_minimax_cues():
    from app.editing.caption_timing import (
        build_motion_block_caption_phrases,
        strip_pause_tags,
    )
    from app.providers.voice import _parse_subtitle_cues

    raw = "Most real value <#0.4#> never reaches the balance sheet."
    assert strip_pause_tags(raw) == "Most real value never reaches the balance sheet."

    # MiniMax may return cleaned subtitle text with pause tags omitted
    cues = _parse_subtitle_cues(
        [
            {
                "text": "Most real value never reaches the balance sheet.",
                "text_begin": 0,
                "text_end": 48,
                "time_begin": 0,
                "time_end": 3200,
            }
        ],
        source_text=raw,
    )
    assert len(cues) == 1
    assert "<#" not in cues[0]["text"]

    phrases, bilingual = build_motion_block_caption_phrases(
        raw, cues=None, duration_ms=3400.0, language="en"
    )
    assert bilingual is False
    assert phrases
    assert all("<#" not in p.text for p in phrases)


def test_resolve_motion_block_cue_phrases_maps_words_to_numeric_props():
    from app.chat.editor_create import resolve_motion_block_cue_phrases
    from app.editing.revisions import coerce_motion_block_props
    from app.editing.schemas import validate_motion_block_props

    narration = "Live valuation shows £18.7m enterprise value <#0.3#> backed by 94% evidence coverage."
    cues = [{"text": "Live valuation shows £18.7m enterprise value backed by 94% evidence coverage.", "time_begin": 0.0, "time_end": 4200.0}]

    resolved_metrics = resolve_motion_block_cue_phrases(
        "metric_grid",
        {
            "title": "Live Valuation",
            "items": [
                {"value": "£18.7m", "label": "Enterprise Value", "cue_phrase": "£18.7m"},
                {"value": "94%", "label": "Evidence Coverage", "cue_phrase": "94%"},
            ],
        },
        narration=narration,
        cues=cues,
        duration_s=4.8,
        speech_lead_s=0.15,
        language="en",
    )
    validated_metrics = validate_motion_block_props(
        "metric_grid", coerce_motion_block_props("metric_grid", resolved_metrics)
    )
    assert validated_metrics.items[0].reveal_at_s is not None
    assert validated_metrics.items[1].reveal_at_s is not None
    assert validated_metrics.items[0].reveal_at_s < validated_metrics.items[1].reveal_at_s

    resolved_showcase = resolve_motion_block_cue_phrases(
        "product_showcase",
        {
            "cursor": {"x": 0.5, "y": 0.4, "cue_phrase": "£18.7m"},
            "callout_steps": [
                {"x": 0.3, "y": 0.3, "width": 0.25, "height": 0.15, "label": "Value", "cue_phrase": "£18.7m"},
                {"x": 0.6, "y": 0.3, "width": 0.25, "height": 0.15, "label": "Coverage", "cue_phrase": "94%"},
            ],
        },
        narration=narration,
        cues=cues,
        duration_s=4.8,
        speech_lead_s=0.15,
        language="en",
    )
    validated_showcase = validate_motion_block_props(
        "product_showcase", coerce_motion_block_props("product_showcase", resolved_showcase)
    )
    assert validated_showcase.cursor is not None
    assert validated_showcase.cursor.click_at_s > 0.5
    assert len(validated_showcase.callout_steps) == 2
    assert validated_showcase.callout_steps[0].end_s <= validated_showcase.callout_steps[1].start_s


def test_narration_synth_config_distinguishes_speed_and_emotion():
    from app.tools.video.narration import narration_synth_config

    default_cfg = narration_synth_config()
    assert "speed" not in default_cfg
    assert "emotion" not in default_cfg

    fast_calm = narration_synth_config(speed=1.06, emotion="calm")
    assert fast_calm["speed"] == 1.06
    assert fast_calm["emotion"] == "calm"
    assert fast_calm != default_cfg


def test_brand_promo_skill_registered_and_cli_promo_excluded_from_auto_discovery():
    from app.skills import SKILL_REGISTRY
    from app.skills.resolution import _EXPLICIT_ONLY_BUILTIN_SKILLS, get_builtin_skill_option

    assert "brand-promo" in SKILL_REGISTRY
    opt = get_builtin_skill_option("brand-promo")
    assert opt.skill_id == "brand-promo"
    assert "promo-video" in _EXPLICIT_ONLY_BUILTIN_SKILLS


def test_editor_ticks_quantizes_arbitrary_floats_cleanly():
    from app.chat.editor import _ticks

    assert _ticks(2.9333, 90000) == 263997
    assert _ticks(4.16667, 90000) == 375000
    assert _ticks(0, 90000) == 0
    with pytest.raises(ValueError, match="non-negative"):
        _ticks(-0.5, 90000)


def test_run_event_bus_clears_stale_live_focus_when_active_step_advances():
    import json

    from app.chat.run_bus import RunEventBus

    bus = RunEventBus()
    conv_id = uuid4()
    bus.start_run(conv_id, run_id="r1")

    def _sse(payload: dict) -> str:
        return f"event: assistant.activity\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    bus.observe_frame(
        conv_id,
        "r1",
        _sse({
            "kind": "steps",
            "steps": [
                {"title": "准备素材与配音配乐", "status": "done"},
                {"title": "编排 45 秒分镜、字幕与动效", "status": "in_progress"},
                {"title": "铺排音效并预览复查", "status": "pending"},
            ],
        }),
    )
    bus.observe_frame(conv_id, "r1", _sse({"kind": "focus", "focus": "正在编排 45 秒分镜、字幕与动效"}))
    assert bus.active_run_summary(conv_id)["live_focus"] == "正在编排 45 秒分镜、字幕与动效"

    # Advancing to Step 3 clears stale Step 2 focus
    bus.observe_frame(
        conv_id,
        "r1",
        _sse({
            "kind": "steps",
            "steps": [
                {"title": "准备素材与配音配乐", "status": "done"},
                {"title": "编排 45 秒分镜、字幕与动效", "status": "done"},
                {"title": "铺排音效并预览复查", "status": "in_progress"},
            ],
        }),
    )
    assert bus.active_run_summary(conv_id)["live_focus"] is None


def test_unwrap_item_dialect_restores_single_item_arrays_using_json_schema():
    from app.agents.arguments import normalize_numeric_arguments, unwrap_item_dialect
    from app.tools.research.capture import CaptureRequest

    schema = CaptureRequest.model_json_schema()
    raw = {
        "source_url": "https://agent.oxvalue.ai/",
        "source_snapshot_id": "a5c88812-0a03-5777-99eb-32b441b0540c",
        "source_snapshot_digest": "eaa91242cf07f53bd69da3aed33a6f2eb88fd934e3515d2b112ed2b7ef55565e",
        "route": "/",
        "viewport": {"width": "1440", "height": "900"},
        "states": [
            {
                "state_id": "st1",
                "actions": {"item": {"kind": "wait", "milliseconds": "400"}},
            }
        ],
        "targets": [{"target_id": "t_val", "element_id": "s0e7"}],
        "outputs": [
            {
                "output_id": "out_val",
                "state_id": "st1",
                "kind": "elements",
                "target_ids": {"item": "t_val"},
                "scale": "4",
            }
        ],
    }
    unwrapped = unwrap_item_dialect(raw, schema)
    normalized, _ = normalize_numeric_arguments(unwrapped, schema)
    validated = CaptureRequest.model_validate(normalized)
    assert len(validated.states[0].actions) == 1
    assert validated.states[0].actions[0].milliseconds == 400
    assert validated.outputs[0].target_ids == ["t_val"]
    assert validated.outputs[0].scale == 4

    # Stray leaked <item> XML prefix/suffix on list elements is also cleaned
    cleaned = unwrap_item_dialect(
        {"resources": ["<item>dfdb41b2-7adf-52d3-a0c6-ca8d0f2a1961", "31a54431-4ffb-57a2-b372-394b2e64765d</item>"]}
    )
    assert cleaned["resources"] == [
        "dfdb41b2-7adf-52d3-a0c6-ca8d0f2a1961",
        "31a54431-4ffb-57a2-b372-394b2e64765d",
    ]


def test_brief_question_target_seconds_infers_value_from_label_not_ordinal_id():
    from app.models.schemas import BriefQuestionItem

    item = BriefQuestionItem.model_validate({
        "slot": "target_seconds",
        "question": "成片时长？",
        "options": [
            {"id": "1", "label": "45 秒"},
            {"id": "2", "label": "30 秒"},
            {"id": "3", "label": "60 秒"},
        ],
    })
    assert [opt.value for opt in item.options] == [45, 30, 60]
