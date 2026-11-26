"""Chat activity and questions — unit contracts."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from app.agents.tool_loop import ReadAccepted, ReadExecuting
from app.chat.activity import ActivityProjector
from app.chat.context import conversation_messages
from app.chat.service import _ask_content, _validate_group_answers, confirmation_need
from app.chat.turn_tools import _video_material_tools
from app.models.schemas import (
    AnswerPayload,
    AnswerRequest,
    Brief,
    BriefAnswerItem,
    BriefQuestionItem,
    BriefSlot,
    BriefSlotSource,
    PrepareVideoMaterialsArgs,
    ProjectBrief,
    QuestionPayload,
    question_group_digest,
)
from app.models.tables import Message, Project
from test.support.media_helpers import (
    group_payload,
    group_request,
    website_question_arguments,
)

pytestmark = pytest.mark.unit


def test_read_activity_opens_at_execute_after_the_interim_prose_seat():
    projector = ActivityProjector(_video_material_tools())

    assert projector.name_known("analyze_brand") == []
    assert projector.open_activity() is None
    executing = projector.feed_event(ReadExecuting(tool_name="analyze_brand", params=object()))
    assert projector.open_activity() is not None
    frames = [
        *executing,
        *projector.feed_event(ReadAccepted(tool_name="analyze_brand", ok=True)),
    ]

    assert [(frame.status, frame.key) for frame in frames] == [
        ("active", "chat.activity.brandAnalyze"),
        ("completed", "chat.activity.brandAnalyzeDone"),
    ]


@pytest.mark.parametrize(("params", "key"), [
    ({"material_urls": ["https://www.legitevi.com/en"]}, "viewWebPage"),
    ({"material_music_ids": [uuid4()]}, "videoMaterials"),
    ({"material_urls": ["https://www.legitevi.com/en"], "material_music_ids": [uuid4()]}, "videoMaterials"),
])
def test_material_activity_matches_validated_inputs(params, key):
    projector = ActivityProjector(_video_material_tools())
    name = "prepare_video_materials"
    assert projector.name_known(name) == []
    active, = projector.feed_event(ReadExecuting(name, PrepareVideoMaterialsArgs(**params)))
    done, = projector.feed_event(ReadAccepted(tool_name=name, ok=True))
    assert active.key == f"chat.activity.{key}"
    assert done.key == f"chat.activity.{key}Done"
    assert active.activity_id == done.activity_id


def test_unbounded_native_quote_requires_confirmation_for_all_preferences():
    automatic = confirmation_need(
        execution="auto", credits="auto", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    execution_ask = confirmation_need(
        execution="ask", credits="auto", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    credits_ask = confirmation_need(
        execution="auto", credits="ask", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    above_guardrail = confirmation_need(
        execution="auto", credits="auto", quote_high=5001,
        unquotable=False, always_confirm_above=5000,
    )

    assert automatic.requires_confirmation and automatic.reason == "unquotable"
    assert execution_ask.requires_confirmation is True
    assert execution_ask.reason == "unquotable"
    assert credits_ask.requires_confirmation is True
    assert credits_ask.reason == "unquotable"
    assert above_guardrail.requires_confirmation is True
    assert above_guardrail.reason == "above_guardrail"


@pytest.mark.parametrize("ok", [False, True])
def test_mixed_material_steps_update_one_row_and_ignore_stale_progress(ok):
    from app.agents.tool_loop import ToolProgress

    projector = ActivityProjector(_video_material_tools())
    name = "prepare_video_materials"
    projector.name_known(name)
    params = PrepareVideoMaterialsArgs(material_urls=["https://www.legitevi.com/en"], material_music_ids=[uuid4()])
    start, = projector.feed_event(ReadExecuting(name, params, "call-1"))
    web, = projector.feed_event(ToolProgress("call-1", "view_webpage"))
    assert not projector.feed_event(ToolProgress("call-1", "view_webpage"))
    assert not projector.feed_event(ToolProgress("other", "import_music"))
    music, = projector.feed_event(ToolProgress("call-1", "import_music"))
    end, = projector.feed_event(ReadAccepted(name, ok))
    assert {f.activity_id for f in (start, web, music, end)} == {start.activity_id}
    assert [f.key for f in (start, web, music)] == [
        "chat.activity.videoMaterials", "chat.activity.viewWebPage", "chat.activity.importMusic",
    ]
    assert end.key == ("chat.activity.videoMaterialsDone" if ok else music.key)
    assert end.status == ("completed" if ok else "failed")
    assert not projector.feed_event(ToolProgress("call-1", "view_webpage"))


def test_all_chat_tool_registries_declare_a_presentation():
    from app.agents.candidate_correction import correction_tool
    from app.chat.conversation_context import conversation_context_tool
    from app.chat.intent import intent_router

    tools = intent_router.tools
    for tool in [*tools, conversation_context_tool(), correction_tool()]:
        assert tool.presentation is not None, tool.name
        assert tool.presentation.kind == "native" or tool.presentation.active_key, tool.name


def test_update_focus_emits_lightweight_sanitized_frame_without_persisting():
    from app.chat.activity import KIND_FOCUS, frame_persistence, sanitize_focus_text
    from app.chat.turn_tools import UPDATE_FOCUS_TOOL, UpdateFocusArgs

    assert UPDATE_FOCUS_TOOL.batchable is True
    assert UPDATE_FOCUS_TOOL.terminal is False
    projector = ActivityProjector([UPDATE_FOCUS_TOOL])
    assert projector.name_known("update_focus") == []
    assert projector.open_activity() is None

    raw = f"正在将 6 幕脚本编排为 Vox 风格 clip_id=clp_01 {uuid4()} /Users/demo/a.mp4"
    frames = projector.feed_event(
        ReadExecuting(tool_name="update_focus", params=UpdateFocusArgs(focus=raw), call_id="f1")
    )
    assert len(frames) == 1
    frame = frames[0]
    assert frame.kind == KIND_FOCUS
    assert frame.status == "active"
    assert frame.focus == "正在将 6 幕脚本编排为 Vox 风格"
    assert frame_persistence(frame) is None
    assert projector.open_activity() is None
    assert not projector.has_active()
    assert projector.feed_event(ReadAccepted(tool_name="update_focus", ok=True)) == []
    assert projector.settled_frames() == []
    assert sanitize_focus_text("a" * 80, max_len=20).endswith("…")


def test_project_tool_detail_covers_all_high_frequency_editor_tools_without_internal_ids():
    from app.chat.activity import project_tool_detail
    from app.chat.editor import (
        AudioDuckWindowArgs,
        EditAudioClipArgs,
        EditTextArgs,
        GenerateSfxArgs,
        InsertMotionBlockArgs,
        InsertTextArgs,
        SetCompositionStyleArgs,
        SetTransitionArgs,
        UpdateMotionBlockArgs,
    )

    leaked_id = str(uuid4())
    cases = [
        (
            "set_composition_style",
            SetCompositionStyleArgs(preset_id="vox_editorial"),
            {"kind": "style", "preset": "vox_editorial"},
        ),
        (
            "insert_motion_block",
            InsertMotionBlockArgs(
                block_id="data_chart",
                start_seconds=12.0,
                end_seconds=17.0,
                props={"title": "Growth", "bars": [{"label": "Q1", "value": 10}]},
            ),
            {"kind": "motion_block_insert", "block": "data_chart", "window": "12–17s"},
        ),
        (
            "update_motion_block",
            UpdateMotionBlockArgs(
                clip_id="clp_motion_99",
                props_patch={"camera_preset": "dolly_zoom", "callout_steps": []},
            ),
            {"kind": "motion_block_update", "aspects": ["camera", "callout"]},
        ),
        (
            "insert_text",
            InsertTextArgs(
                text="SARAH LIN · HEAD OF DESIGN",
                start_seconds=0.5,
                end_seconds=4.0,
                preset_id="lower_third_tag",
                position="bottom_left",
            ),
            {
                "kind": "text_insert",
                "preset": "lower_third_tag",
                "position": "bottom_left",
                "role": "title",
                "window": "0.5–4s",
                "snippet": "SARAH LIN · HEAD…",
            },
        ),
        (
            "insert_text",
            InsertTextArgs(
                text="第一行中文\nSecond English line",
                start_seconds=0.5,
                end_seconds=4.0,
                preset_id="bilingual_cinema",
                role="caption",
            ),
            {
                "kind": "text_insert",
                "preset": "bilingual_cinema",
                "role": "caption",
                "bilingual": True,
                "window": "0.5–4s",
                "snippet": "第一行中文",
            },
        ),
        (
            "insert_text",
            InsertTextArgs(from_audio_clip_id="clp_voice_01", preset_id="karaoke_focus"),
            {"kind": "text_caption_from_audio", "preset": "karaoke_focus"},
        ),
        (
            "edit_text",
            EditTextArgs(scope="all_derived_captions", preset_id="karaoke_focus"),
            {"kind": "text_edit", "scope": "all_derived_captions", "preset": "karaoke_focus"},
        ),
        (
            "generate_sfx",
            GenerateSfxArgs(recipe_id="sub_swell", base_clip_id="clp_sfx_01"),
            {"kind": "sfx", "recipe": "sub_swell"},
        ),
        (
            "edit_audio_clip",
            EditAudioClipArgs(
                clip_id="clp_bgm_01",
                gain_db=-24.0,
                fade_in_seconds=0.5,
                duck_windows=[AudioDuckWindowArgs(start_seconds=1.0, end_seconds=4.0)],
            ),
            {"kind": "audio_edit", "aspects": ["gain", "fade"]},
        ),
        (
            "set_transition",
            SetTransitionArgs(from_clip_id="clp_1", to_clip_id="clp_2", kind="zoom_through"),
            {"kind": "transition", "preset": "zoom_through"},
        ),
    ]
    for tool_name, params, expected in cases:
        detail = project_tool_detail(tool_name, params)
        assert detail == expected, (tool_name, detail)
        serialized = str(detail)
        assert "clp_" not in serialized
        assert leaked_id not in serialized


def test_group_validation_rejects_bad_membership_duplicates_required_and_freeform():
    payload = group_payload(allow_freeform=False)
    request = group_request(payload)
    with pytest.raises(HTTPException) as duplicate:
        _validate_group_answers(
            payload,
            request.model_copy(
                update={
                    "answers": [request.answers[0], request.answers[0], *request.answers[1:]],
                }
            ),
        )
    assert duplicate.value.status_code == 422

    with pytest.raises(HTTPException) as missing:
        _validate_group_answers(
            payload, request.model_copy(update={"answers": request.answers[:-1]})
        )
    assert missing.value.status_code == 422

    with pytest.raises(HTTPException) as wrong_option:
        _validate_group_answers(
            payload,
            request.model_copy(
                update={
                    "answers": [
                        BriefAnswerItem(slot="production_direction", kind="option", option_id="other"),
                        *request.answers[1:],
                    ],
                }
            ),
        )
    assert wrong_option.value.status_code == 422

    with pytest.raises(HTTPException) as freeform:
        _validate_group_answers(
            payload,
            request.model_copy(
                update={
                    "answers": [
                        BriefAnswerItem(slot="production_direction", kind="freeform", text="conference"),
                        *request.answers[1:],
                    ],
                }
            ),
        )
    assert freeform.value.status_code == 422

    with pytest.raises(HTTPException) as stale:
        _validate_group_answers(payload, request.model_copy(update={"group_digest": "0" * 64}))
    assert stale.value.status_code == 409


@pytest.mark.parametrize("kind", ["group", "bail"])
def test_questionnaire_rejects_removed_notes_on_submit_and_skip(kind):
    with pytest.raises(ValidationError) as error:
        TypeAdapter(AnswerRequest).validate_python({
            "kind": kind,
            "group_digest": "0" * 64,
            "answers": [{"slot": "constraints", "kind": "freeform", "text": "24 fps"}],
        })
    assert error.value.errors()[0]["loc"][-1] == "slot"


def test_plain_option_answer_needs_no_group_or_workflow():
    answer = AnswerPayload.model_validate(
        {
            "kind": "option",
            "option_id": "1",
            "text": "One",
            "answered_at": "2026-01-01T00:00:00Z",
        }
    )
    assert answer.answers == []
    question = QuestionPayload.model_validate(
        {
            "kind": "question",
            "question": "Choose",
            "options": [{"id": "1", "label": "One"}],
        }
    )
    assert question.kind == "question"
    assert question.items == []
    from pydantic import TypeAdapter, ValidationError

    from app.models.schemas import AnswerRequest
    with pytest.raises(ValidationError):
        TypeAdapter(AnswerRequest).validate_python({"kind": "start"})


def test_extended_single_slot_backfill_preserves_slot_types_and_creative_state():
    from app.chat.service import _backfill_brief_slot

    project = Project(id=uuid4(), user_id=uuid4(), title="Single slots")
    _backfill_brief_slot(project, "target_seconds", "60 seconds")
    _backfill_brief_slot(project, "subtitle_languages", "English")
    stored = ProjectBrief.model_validate(project.pending_brief)
    assert stored.brief.target_seconds.value == 60
    assert stored.brief.subtitle_languages.value == ["en"]
    assert stored.creative_state is not None
    assert stored.creative_state.content_digest


@pytest.mark.asyncio
async def test_streamed_ask_only_announces_activity():
    import asyncio

    from app.chat.routes import _make_tool_call_hook

    queue = asyncio.Queue()
    await _make_tool_call_hook(queue)("ask_user")
    assert queue.qsize() == 1
    assert queue.get_nowait().startswith("event: assistant.thinking")


def test_group_digest_ignores_code_owned_material_bookkeeping():
    payload = group_payload()
    before = Brief()
    after = before.model_copy(update={
        "material_state": BriefSlot(
            value="attached", source=BriefSlotSource.DEFAULT,
        ),
    })
    assert question_group_digest(payload.items, before) == question_group_digest(
        payload.items, after
    )


def test_group_title_stays_out_of_the_message_prose():
    from app.models.schemas import QuestionProposal

    ask = QuestionProposal(prose="Brand evidence is ready.", question="Production setup")
    assert _ask_content(ask, has_dock_options=True) == "Brand evidence is ready."
    assert _ask_content(ask) == "Brand evidence is ready.\n\nProduction setup"


@pytest.mark.parametrize("values", [
    [["zh-CN", "en-US"]],
    [["zh-CN", "en-US"], "zh-CN"],
    ["zh-CN", "en-US"],
])
def test_subtitle_choices_preserve_authored_labels_order_and_language_sets(values):
    from app.models.schemas import missing_brief_question_items

    form = website_question_arguments()
    subtitles = next(item for item in form["items"] if item["slot"] == "subtitle_languages")
    options = [{"label": f"Choice {i}", "value": value} for i, value in enumerate(values)]
    subtitles["options"] = options
    items = [BriefQuestionItem.model_validate(item) for item in form["items"]]
    result = next(i for i in missing_brief_question_items(items, Brief()) if i.slot == "subtitle_languages")
    assert [(o.label, o.value) for o in result.options] == [
        (o["label"], [o["value"]] if isinstance(o["value"], str) else o["value"]) for o in options
    ]


def test_native_history_includes_intervening_dialogue_and_places_dock_pick_at_submission():
    from datetime import UTC, datetime, timedelta

    start = datetime.now(UTC)
    rows = [
        Message(id=uuid4(), role="user", content="给 https://www.legitevi.com/en 做一只宣传片"),
        Message(id=uuid4(), role="assistant", content="官网内容看过了。", question={
            "question": "旁白用哪种语言？", "options": [{"id": "en", "label": "英文"}],
        }, answer={"kind": "option", "text": "英文", "answered_at": (start + timedelta(seconds=4)).isoformat()}),
        Message(id=uuid4(), role="user", content="先说说你的想法"),
        Message(id=uuid4(), role="assistant", content="我想用官网画面做开头。"),
        Message(id=uuid4(), role="assistant", content="我来搭分镜。"),
    ]
    for row, seconds in zip(rows, [0, 1, 2, 3, 5], strict=True):
        row.created_at = start + timedelta(seconds=seconds)
    dialogue = conversation_messages(rows)
    assert [m["content"] for m in dialogue] == [
        rows[0].content, "官网内容看过了。\n旁白用哪种语言？\n英文", rows[2].content,
        rows[3].content, "英文", rows[4].content,
    ]
    assert dialogue[4]["role"] == "user"
    rows.insert(4, Message(id=uuid4(), role="user", content="英文",
                           intent={"answered_question_id": str(rows[1].id)},
                           created_at=start + timedelta(seconds=4)))
    assert conversation_messages(rows) == dialogue


def test_autonomous_promo_export_and_internal_error_filters():
    from app.chat.routes import _is_internal_tool_error
    from app.chat.turn_tools import PLAN_READ_TOOLS
    from app.chat.video_turn_seats import asks_for_export

    assert asks_for_export("给oxvalue制作一条宣传片") is True
    assert asks_for_export("新品发布：https://agent.oxvalue.ai/") is True
    assert asks_for_export("Make a launch video for OxValue") is True
    assert asks_for_export("How long is this MP4?") is False
    assert asks_for_export("把 logo 往左移一点") is False
    assert asks_for_export("给oxvalue制作一条宣传片，只要草稿不用导出") is False

    assert _is_internal_tool_error(
        "Invalid bento_features props. Check get_blocks for its schema. eyebrow: String should have at most 32 characters"
    ) is True
    assert _is_internal_tool_error("Include the complete transition at 23.75–24.05 seconds.") is True
    assert _is_internal_tool_error("Source unavailable") is False

    by_name = {t.name: t for t in PLAN_READ_TOOLS}
    for name in ("search_blocks", "get_blocks", "search_sfx_library", "get_music"):
        pres = by_name[name].presentation
        assert pres is not None and pres.kind == "read" and pres.active_key and pres.done_key


def test_native_creation_ask_user_exposes_items_and_post_edit_prunes_it():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.editor import EDITOR_TOOLS
    from app.chat.prompts import assemble_video_round
    from app.chat.turn_tools import PLAN_TOOLS, _video_material_tools

    base_tools = [*PLAN_TOOLS, *_video_material_tools(), *EDITOR_TOOLS]
    fresh = assemble_video_round({
        "tools": base_tools,
        "drafts": (),
        "snapshot": ContextSnapshot("evidence", frozenset(), resources=()),
        "mode": "plan",
        "user_text": "给 https://agent.oxvalue.ai/ 制作一个宣传片",
    })
    ask_fresh = next(t for t in fresh.tools if t.name == "ask_user")
    _, fresh_params = ask_fresh.wire_view(ask_fresh.description, ask_fresh.params_model.model_json_schema())
    assert "items" in fresh_params["properties"]

    comp_resource = ("composition:1", {
        "kind": "composition",
        "composition_id": str(uuid4()),
        "name": "OxValue",
        "version_id": str(uuid4()),
        "version": 1,
        "base_ref": {"composition_id": str(uuid4()), "composition_version_id": str(uuid4()), "content_digest": "a" * 64},
    })
    editing = assemble_video_round({
        "tools": base_tools,
        "drafts": (),
        "snapshot": ContextSnapshot("evidence", frozenset({"composition:1"}), resources=(comp_resource,)),
        "mode": "plan",
        "user_text": "把标题字号调大一点",
    })
    ask_edit = next(t for t in editing.tools if t.name == "ask_user")
    _, edit_params = ask_edit.wire_view(ask_edit.description, ask_edit.params_model.model_json_schema())
    assert "items" not in edit_params["properties"]


@pytest.mark.asyncio
async def test_stamp_video_presentation_skips_partial_preview_after_delivery():
    from types import SimpleNamespace
    from app.chat.plan_turn import PlanTurn

    runner = object.__new__(PlanTurn)
    runner.project = Project(id=uuid4(), user_id=uuid4(), title="OxValue")
    runner.text = "交付成片"
    runner._video_presentation_pending = None
    runner._editor_preview_blocks = [{"kind": "video_storyboard", "scrub": {"kind": "range", "start_seconds": 18.0, "end_seconds": 30.0}}]
    runner._editor_delivery = {"output_id": str(uuid4()), "delivered_to_chat": True}
    msg = SimpleNamespace(id=uuid4(), blocks=[], intent={})

    await runner._stamp_video_presentation(msg)
    assert msg.blocks == []
    assert getattr(runner, "_editor_preview_blocks", None) is None


@pytest.mark.asyncio
async def test_turn_steps_survive_user_and_assistant_projection_and_stamp_turn_prose():
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from app.chat.plan_turn import PlanTurn
    from app.models.schemas import ChatMessageResponse, MessageRole

    steps = [
        {"title": "准备素材与配音", "status": "done"},
        {"title": "渲染并交付成片", "status": "in_progress"},
    ]
    user_dto = ChatMessageResponse(
        id=uuid4(),
        conversation_id=uuid4(),
        role=MessageRole.USER,
        content="开工",
        intent={"steps": steps},
        created_at=datetime.now(UTC),
    )
    assert user_dto.steps == steps

    runner = object.__new__(PlanTurn)
    runner.turn_id = None
    runner._latest_steps = steps
    runner._last_eval_meta = {}
    runner._video_presentation_pending = None
    runner.skill = None
    msg = SimpleNamespace(role="assistant", content="已交付成片。", question=None, intent={})
    await runner._stamp_turn_metadata(msg, completed=True)
    assert msg.intent["turn_prose"] is True
    assert msg.intent["steps"] == [
        {"title": "准备素材与配音", "status": "done"},
        {"title": "渲染并交付成片", "status": "done"},
    ]


@pytest.mark.asyncio
async def test_sse_pump_detaches_without_cancelling_turn_and_explicit_stop_cancels():
    import asyncio
    from app.chat.routes import (
        _DetachableQueue,
        _cancel_active_turn_task,
        _register_turn_task,
        _sse_pump,
    )

    queue = _DetachableQueue()
    finished = asyncio.Event()
    started = asyncio.Event()

    async def background_work():
        started.set()
        await queue.put("event: first\ndata: {}\n\n")
        await asyncio.sleep(0.03)
        # Writing after client disconnect must be a safe no-op
        await queue.put(("completed", {"ok": True}))
        finished.set()

    task = asyncio.create_task(background_work())
    turn_id = uuid4()
    _register_turn_task(turn_id, task)

    gen = _sse_pump(queue, task, "turn.completed", "turn.failed")
    first = await anext(gen)
    assert first.startswith("event: first")
    # Simulate F5 refresh / tab close disconnecting the SSE generator early
    await gen.aclose()
    assert not task.cancelled()
    await asyncio.wait_for(finished.wait(), timeout=1.0)
    assert task.done() and not task.cancelled()

    # Explicit /stop must still cancel an actively registered turn task immediately
    blocker = asyncio.Event()
    stop_turn_id = uuid4()

    async def long_work():
        await blocker.wait()

    stop_task = asyncio.create_task(long_work())
    _register_turn_task(stop_turn_id, stop_task)
    assert _cancel_active_turn_task(stop_turn_id) is True
    with pytest.raises(asyncio.CancelledError):
        await stop_task
