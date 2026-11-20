import json
from copy import deepcopy
from uuid import uuid4

from app.chat.editor import EDITOR_NAMES

import pytest

from app.agents.tool_loop import ContextSnapshot, ToolObservation
from app.chat.context import conversation_messages
from app.chat.intent import intent_router
from app.chat.readiness import brief_with_user_constraints, website_promo_question_items
from app.chat.service import _backfill_brief_group
from app.chat.speech_language import conversation_speech_language
from app.models.schemas import (
    BrandColor,
    BrandSourceRef,
    BrandTagline,
    BrandTypography,
    BriefAnswerItem,
    CreativeState,
    MediaInput,
    MediaInputType,
    PendingPlan,
    QuestionPayload,
    seal_creative_state,
)
from app.models.tables import Message, Project, SourceSnapshot
from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration
from app.tools.video.brand import build_brand_profile
from app.tools.video.brand_agent import BrandProfileExtraction, brand_profile_agent
from test.core.test_website_promo_readiness import URL, asset, snapshot, website_question_arguments

pytestmark = pytest.mark.asyncio


def wire_copy(value):
    if isinstance(value, str):
        return str(value)
    if isinstance(value, list):
        return [wire_copy(item) for item in value]
    if isinstance(value, dict):
        return {key: wire_copy(item) for key, item in value.items()}
    return deepcopy(value)


class FakeToolProvider:
    capabilities = ProviderCapabilities(supports_native_tools=True)

    def __init__(self, calls, *, content="我来处理这一步。"):
        self.calls_to_make = list(calls)
        self.content = content
        self.wires = []

    async def generate_with_tools(self, *, messages, tools, **kwargs):
        self.wires.append({"messages": wire_copy(messages), "tools": wire_copy(tools)})
        batch = self.calls_to_make.pop(0)
        calls = batch if isinstance(batch, list) else [batch]
        return ToolGeneration(
            content=self.content,
            tool_calls=[ToolCall(id=f"call-{len(self.wires)}-{index}", name=name, arguments=arguments)
                        for index, (name, arguments) in enumerate(calls)],
        )

    async def generate_stream_with_tools(self, **kwargs):
        return await self.generate_with_tools(**kwargs)


def tool_names(wire):
    return {item["function"]["name"] for item in wire["tools"]}


def png():
    return MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/png",
        data_url="data:image/png;base64,iVBORw0KGgo=",
    )


def source_row(owner_id):
    return SourceSnapshot(
        id=uuid4(),
        owner_id=owner_id,
        kind="web",
        digest="a" * 64,
        storage_key="sources/page.json",
        meta={
            "canonical_url": URL,
            "lines": [
                {"line_id": "line_0000", "text": "Citations should be as universal as hashtags."}
            ],
            "views": snapshot()["views"],
        },
    )


class BrandFakeClient:
    def __init__(self):
        self.messages = None

    async def generate(self, *, messages, response_model, **kwargs):
        self.messages = wire_copy(messages)
        return BrandProfileExtraction(
            positioning="Universal citation infrastructure",
            taglines=[
                BrandTagline(
                    text="Citations should be as universal as hashtags.", line_ids=["line_0000"]
                )
            ],
            colors=[BrandColor(value="#DC0000", source="visual", confidence="inferred")],
            typography=[BrandTypography(candidate="Inter", source="visual", confidence="inferred")],
        )


async def test_legitevi_wire_requires_one_questionnaire_before_design(monkeypatch):
    form = website_question_arguments()
    subtitles = next(item for item in form["items"] if item["slot"] == "subtitle_languages")
    subtitles["options"] = [
        {"label": "简体中文", "value": {"item": "zh-CN"}},
        {"label": "英文", "value": {"item": "en-US"}},
    ]
    provider = FakeToolProvider(
        [
            ("prepare_video_materials", {"material_urls": [URL]}),
            ("analyze_brand", {}),
            ("ask_user", form),
        ]
    )
    monkeypatch.setattr(intent_router, "client", provider)
    brand_fake = BrandFakeClient()
    monkeypatch.setattr(brand_profile_agent, "client", brand_fake)
    text = f"给 {URL} 做一只宣传片"
    rows = [Message(role="user", content=text)]
    speech_language = conversation_speech_language(rows)
    assert speech_language and speech_language.split("-")[0] == "zh"
    owner_id = uuid4()
    state = CreativeState()
    world = ContextSnapshot("pending", frozenset(), resources=(("asset:1", asset()),))

    async def refresh_context():
        return world

    async def execute(name, params, prose):
        nonlocal state, world
        if name == "prepare_video_materials":
            world = ContextSnapshot(
                "ready",
                frozenset({"snapshot:1"}),
                resources=(("asset:1", asset("completed")), ("snapshot:1", snapshot())),
            )
            return ToolObservation("prepared", images=(png(),))
        if name == "analyze_brand":
            source = source_row(owner_id)
            extraction = await brand_profile_agent.call(
                brief_json="{}",
                evidence_json=(
                    '{"citable_lines":[{"line_id":"line_0000",'
                    '"text":"Citations should be as universal as hashtags."}]}'
                ),
                images=[png()],
            )
            ref = BrandSourceRef(
                snapshot_id="snapshot-1",
                digest=source.digest,
                view_ids=["hero"],
                line_ids=["line_0000"],
            )
            profile = build_brand_profile(extraction, snapshots=[source], source_refs=[ref])
            state = seal_creative_state(
                CreativeState(
                    brief=brief_with_user_constraints(text, state.brief),
                    brand_profile=profile,
                    source_refs=[ref],
                )
            )
            return ToolObservation("brand profile saved")
        if name == "ask_user":
            return None
        raise AssertionError(f"unexpected tool: {name}")

    def assemble(**facts):
        return __import__(
            "app.chat.prompts", fromlist=["assemble_video_round"]
        ).assemble_video_round(
            {
                **facts,
                "mode": "plan",
                "user_text": text,
                "source_text": text,
                "creative_state": state,
            }
        )

    result = await intent_router.call_loop(
        execute,
        round_assembler=assemble,
        refresh_context=refresh_context,
        dialogue=conversation_messages(rows),
        speech_language_hint=speech_language,
        message="",
        material_pending_line=(
            "此 URL 的网站采集仍在等待，页面尚不能用作可读证据。"
        ),
    )
    assert result.tool_name == "ask_user"
    assert len(provider.wires) == 3
    assert tool_names(provider.wires[0]) == {"prepare_video_materials", "answer", *EDITOR_NAMES}
    assert tool_names(provider.wires[1]) == {"analyze_brand", "answer", *EDITOR_NAMES}
    assert tool_names(provider.wires[2]) == {"ask_user", *EDITOR_NAMES}
    for wire in provider.wires:
        assert wire["messages"].count({"role": "user", "content": text}) == 1
        assert [message["role"] for message in wire["messages"][:2]] == ["system", "user"]
        assert f"对话语言：{speech_language}" in wire["messages"][0]["content"]
        assert "一轮一问" not in json.dumps(wire["tools"], ensure_ascii=False)
        assert "five slots" not in json.dumps(wire["tools"], ensure_ascii=False)
    first_user = provider.wires[0]["messages"][1]["content"]
    assert "网站采集仍在等待" in first_user
    assert "未上传文件" not in first_user
    first_system = provider.wires[0]["messages"][0]["content"]
    assert "官网宣传片取证" in first_system
    assert first_system.index("只读工具的名称") < first_system.index("视频创作（网站演示")
    assert first_system.index("视频创作（网站演示") < first_system.index("- answer：")
    full_context = "\n".join(
        str(message.get("content")) for message in provider.wires[0]["messages"]
    )
    assert "当前路径：website_promo" in full_context
    assert "采集已就绪：false" in full_context
    assert "正文已就绪：false" in full_context
    assert "所需视图已就绪：false" in full_context
    assert "Brief 已就绪：false" in full_context
    assert '"required_next_action": "prepare_video_materials"' in full_context
    assert full_context.count('"required_next_action":') == 1
    assert '"source_readiness"' not in full_context
    brand_parts = brand_fake.messages[1]["content"]
    assert sum(part.get("type") == "image_url" for part in brand_parts) == 1
    assert "Citations should be as universal as hashtags." in brand_parts[-1]["text"]

    ask_arguments = provider.wires[2]["messages"][0]
    assert "原生 ask_user" in ask_arguments["content"]
    ask_system = ask_arguments["content"]
    assert "- answer：" not in ask_system
    assert ask_system.index("原生 ask_user") < ask_system.index("待回答的问题：")
    current_wire = json.dumps(provider.wires[2]["messages"], ensure_ascii=False)
    assert "creative_state" in current_wire, current_wire
    assert '"source_refs"' not in provider.wires[2]["messages"][-2]["content"]
    assert "#DC0000" in current_wire
    assert "Citations should be as universal as hashtags." in current_wire
    ask_schema = next(
        item["function"]["parameters"]
        for item in provider.wires[2]["tools"]
        if item["function"]["name"] == "ask_user"
    )
    assert set(ask_schema["properties"]) == {"question", "items", "default_path"}
    assert set(ask_schema["required"]) == {"question", "items", "default_path"}
    assert ask_schema["properties"]["items"]["minItems"] == 5
    assert "Brief" not in ask_schema.get("$defs", {})
    questions = ask_schema["properties"]["items"]["items"]["anyOf"]
    assert [q["properties"]["slot"]["enum"][0] for q in questions] == [
        "production_direction", "target_seconds", "narration_language", "subtitle_languages", "aspect",
    ]
    assert "Option" not in ask_schema.get("$defs", {})
    for question in questions:
        assert question["properties"]["options"]["items"]["required"] == ["label", "value"]
    assert questions[1]["properties"]["options"]["items"]["properties"]["value"]["type"] == "integer"
    assert questions[3]["properties"]["options"]["minItems"] == 1
    assert questions[4]["properties"]["options"]["items"]["properties"]["value"]["enum"] == ["16:9", "9:16", "1:1"]
    asked = result.params
    asked.items = website_promo_question_items(asked.items, state.brief)
    assert [item.question for item in asked.items] == [item["question"] for item in form["items"]]
    assert [option.id for option in asked.items[0].options] == ["1", "2"]
    assert [option.value for option in asked.items[1].options] == [30, 60]
    assert [(o.label, o.value) for o in asked.items[3].options] == [("简体中文", ["zh-CN"]), ("英文", ["en-US"])]
    payload = QuestionPayload(
        kind="question",
        question=asked.question,
        items=asked.items,
        group_digest=__import__(
            "app.models.schemas", fromlist=["question_group_digest"]
        ).question_group_digest(asked.items, state.brief),
    )
    project = Project(
        id=uuid4(),
        user_id=owner_id,
        title="LegitEvi",
        pending_brief=PendingPlan(
            creative_state=state,
            brief=state.brief,
        ).model_dump(mode="json"),
    )
    answers = []
    for item in asked.items:
        pick = item.options[1 if item.slot in {"target_seconds", "subtitle_languages"} else 0]
        answers.append(BriefAnswerItem(slot=item.slot, kind="option", option_id=pick.id, text=pick.label))
    _backfill_brief_group(project, payload, answers)
    state = PendingPlan.model_validate(project.pending_brief).creative_state
    assert state.brief.production_direction.value == "官网推广 · 用真实案例演示产品"
    assert state.brief.target_seconds.value == 60
    assert state.brief.narration_language.value == "en"
    assert state.brief.subtitle_languages.value == ["en-US"]
    assert state.brief.aspect.value == "16:9"

    resumed_provider = FakeToolProvider([("answer", {})])
    monkeypatch.setattr(intent_router, "client", resumed_provider)

    async def execute_answer(name, params, prose):
        assert name == "answer"
        return None

    def assemble_answer(**facts):
        return __import__(
            "app.chat.prompts", fromlist=["assemble_video_round"]
        ).assemble_video_round(
            {
                **facts,
                "mode": "plan",
                "user_text": "submitted answers",
                "source_text": text,
                "creative_state": state,
            }
        )

    rows.append(Message(
        id=uuid4(), role="assistant", content="旁白语言？",
        answer={"kind": "option", "option_id": "1", "text": "English voiceover"},
    ))
    dialogue = conversation_messages(rows)
    resumed_language = conversation_speech_language(rows)
    assert resumed_language == speech_language
    await intent_router.call_loop(
        execute_answer,
        dialogue=dialogue,
        speech_language_hint=resumed_language,
        round_assembler=assemble_answer,
        refresh_context=refresh_context,
        message="",
    )
    assert len(resumed_provider.wires) == 1
    messages = resumed_provider.wires[0]["messages"]
    assert messages[-3:] == dialogue
    assert f"对话语言：{resumed_language}" in messages[0]["content"]
    assert state.brief.production_direction.value in str(messages)
    assert "design_video" in tool_names(resumed_provider.wires[0])
    assert "ask_user" not in tool_names(resumed_provider.wires[0])
    assert '"required_next_action": "design_video"' in str(resumed_provider.wires[0]["messages"])


@pytest.mark.parametrize("streaming", [False, True])
async def test_question_written_in_prose_then_unoffered_design_retries_the_form(monkeypatch, streaming):
    from unittest.mock import AsyncMock

    from test.core.test_website_promo_readiness import profile, round_assembly

    text = f"{URL} 给我的产品做一只宣传片"
    assembly = round_assembly(text, assets=[asset("completed")], snapshots=[snapshot()],
                              state=CreativeState(brand_profile=profile()))
    assert {t.name for t in assembly.tools} == {"ask_user"}
    replies = [
        ToolGeneration('想先跟你确认。]<]minimax[>[<tool_call><invoke name="ask_user">', []),
        ToolGeneration("我先按默认设定搭首稿。", [ToolCall(id="design", name="design_video", arguments={})]),
        ToolGeneration("想听听你打算怎样用这支片。", [
            ToolCall(id="ask", name="ask_user", arguments=website_question_arguments()),
        ]),
    ]
    provider = FakeToolProvider([])
    send = AsyncMock(side_effect=replies)
    monkeypatch.setattr(provider, "generate_stream_with_tools", send)
    monkeypatch.setattr(provider, "generate_with_tools", send)
    monkeypatch.setattr(intent_router, "client", provider)
    execute = AsyncMock(return_value=None)
    result = await intent_router.call_loop(
        execute, round_assembler=lambda **_: assembly, message=text,
        on_delta=(lambda _: None) if streaming else None,
    )
    assert all(tool_names(call.kwargs) == {"ask_user"} for call in send.await_args_list)
    assert "原生 tool_calls" in str(send.await_args_list[1].kwargs["messages"])
    assert execute.await_count == 1 and execute.await_args.args[0] == result.tool_name == "ask_user"
    assert "minimax" not in execute.await_args.args[2]
    assert len(result.params.items) == 5


@pytest.mark.parametrize("submitted", [True, False])
@pytest.mark.parametrize("silent", [True, False])
async def test_storyboard_tool_prose_precedes_work_with_or_without_questionnaire_submit(monkeypatch, submitted, silent):
    from app.chat.prompts import assemble_video_round
    from test.core.test_website_promo_readiness import profile

    text = f"给 {URL} 做一只 30 秒、16:9、使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    state = CreativeState(brief=brief_with_user_constraints(text), brand_profile=profile())
    resources = (("asset:1", asset("completed")), ("snapshot:1", snapshot()))
    world = ContextSnapshot("evidence", frozenset(key for key, _ in resources), resources=resources)
    plan = {"scene_plan": [{"scene_id": "intro", "intent": "用证据说明产品机制"}]}
    provider = FakeToolProvider([("design_video", plan)] * 2, content="" if silent else "先从证据链的起点讲起。")
    monkeypatch.setattr(intent_router, "client", provider)
    events = []

    def assemble(**facts):
        return assemble_video_round({
            **facts, "mode": "plan", "user_text": text, "creative_state": state, "snapshot": world,
            "media_journey": {"opening_id": "opening"}, "group_answer_submitted": submitted,
            "speech_language": "zh",
        })

    async def execute(name, params, prose):
        events.append(name)
        provider.content = ""
        return ToolObservation("draft prepared", stop_after_observation=events.count(name) == 2)

    await intent_router.call_loop(
        execute, round_assembler=assemble, message=text,
        on_delta=lambda _: None, on_interim_prose=events.append,
    )
    spoken = []
    if not silent:
        spoken = ["先从证据链的起点讲起。"]
    elif submitted:
        spoken = ["收到，我会按你选的方向安排这支 30 秒短片的开场和镜头顺序。"]
    assert events == [*spoken, "design_video", "design_video"]
    assert ("用户刚提交制作偏好" in str(provider.wires[0]["messages"])) == submitted
    following = assemble(tools=intent_router.tools, interim_prose_count=1)
    assert following.stream_prose
    assert following.acknowledgment is None
    assert "用户刚提交制作偏好" not in following.system


async def test_url_and_suggestion_preserve_speech_language_until_user_writes_in_english():
    source_turn = uuid4()
    rows = [
        Message(role="user", content=f"给 {URL} 做一只宣传片"),
        Message(id=source_turn, role="assistant", content="Which voiceover would you like?"),
        Message(role="user", content="Use the English voiceover for this film.",
                suggestion_ref={"source_turn": str(source_turn), "suggestion_id": "en"}),
        Message(role="user", content=URL),
    ]
    chinese = conversation_speech_language(rows)
    assert chinese and chinese.split("-")[0] == "zh"
    rows.append(Message(role="user", content="Please walk me through your plan for the film."))
    english = conversation_speech_language(rows)
    assert english and english.split("-")[0] == "en"


async def test_complete_legitevi_never_reasks_and_has_no_forced_skill(monkeypatch):
    provider = FakeToolProvider(
        [
            ("prepare_video_materials", {"material_urls": [URL]}),
            ("analyze_brand", {}),
            ("answer", {}),
        ]
    )
    monkeypatch.setattr(intent_router, "client", provider)
    monkeypatch.setattr(brand_profile_agent, "client", BrandFakeClient())
    text = (
        f"给 {URL} 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    )
    state = CreativeState()
    world = ContextSnapshot("pending", frozenset(), resources=(("asset:1", asset()),))

    async def refresh_context():
        return world

    async def execute(name, params, prose):
        nonlocal state, world
        if name == "prepare_video_materials":
            world = ContextSnapshot(
                "ready",
                frozenset({"snapshot:1"}),
                resources=(("asset:1", asset("completed")), ("snapshot:1", snapshot())),
            )
            return ToolObservation("prepared", images=(png(),))
        if name == "analyze_brand":
            source = source_row(uuid4())
            extraction = await brand_profile_agent.call(
                brief_json="{}", evidence_json="{}", images=[png()]
            )
            ref = BrandSourceRef(snapshot_id="snapshot-1", digest=source.digest)
            profile = build_brand_profile(extraction, snapshots=[source], source_refs=[ref])
            state = seal_creative_state(
                CreativeState(
                    brief=brief_with_user_constraints(text, state.brief),
                    brand_profile=profile,
                    source_refs=[ref],
                )
            )
            return ToolObservation("brand profile saved")
        assert name == "answer"
        return None

    def assemble(**facts):
        return __import__(
            "app.chat.prompts", fromlist=["assemble_video_round"]
        ).assemble_video_round(
            {
                **facts,
                "mode": "plan",
                "user_text": text,
                "source_text": text,
                "creative_state": state,
            }
        )

    result = await intent_router.call_loop(
        execute, round_assembler=assemble, refresh_context=refresh_context, message=text
    )
    assert result.tool_name == "answer"
    assert len(provider.wires) == 3
    assert "design_video" in tool_names(provider.wires[-1])
    assert "ask_user" not in tool_names(provider.wires[1])
    assert "ask_user" not in result.calls
    assert "AVAILABLE VIDEO ROUTES" not in provider.wires[-1]["messages"][0]["content"]
    assert "promo-video" not in provider.wires[-1]["messages"][0]["content"]


async def test_failed_capture_and_non_website_paths(monkeypatch):
    failed_provider = FakeToolProvider([("answer", {})])
    monkeypatch.setattr(intent_router, "client", failed_provider)
    text = f"给 {URL} 做一只宣传片"

    async def refresh_failed():
        return ContextSnapshot("failed", frozenset(), resources=(("asset:1", asset("failed")),))

    async def execute(name, params, prose):
        assert name == "answer"
        return None

    def assemble_failed(**facts):
        return __import__(
            "app.chat.prompts", fromlist=["assemble_video_round"]
        ).assemble_video_round(
            {
                **facts,
                "mode": "plan",
                "user_text": text,
                "source_text": text,
                "creative_state": CreativeState(),
            }
        )

    await intent_router.call_loop(
        execute, round_assembler=assemble_failed, refresh_context=refresh_failed, message=text
    )
    assert tool_names(failed_provider.wires[0]) == {"answer", *EDITOR_NAMES}

    generic_provider = FakeToolProvider([("answer", {})])
    monkeypatch.setattr(intent_router, "client", generic_provider)

    async def refresh_generic():
        return ContextSnapshot("generic", frozenset(), resources=())

    def assemble_generic(**facts):
        return __import__(
            "app.chat.prompts", fromlist=["assemble_video_round"]
        ).assemble_video_round(
            {
                **facts,
                "mode": "plan",
                "user_text": "做一只宣传片",
                "source_text": "做一只宣传片",
                "creative_state": CreativeState(),
            }
        )

    await intent_router.call_loop(
        execute,
        round_assembler=assemble_generic,
        refresh_context=refresh_generic,
        message="做一只宣传片",
    )
    assert "design_video" in tool_names(generic_provider.wires[0])
    assert "当前路径：website_promo" not in str(generic_provider.wires[0]["messages"])
    assert "promo-video" not in generic_provider.wires[0]["messages"][0]["content"]





@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_stage_speech_precedes_activity_and_silent_calls_can_continue(monkeypatch, streaming):
    from app.agents.tool_loop import ChatTool, ToolObservation

    class Provider(FakeToolProvider):
        async def generate_with_tools(self, **kwargs):
            self.wires.append(wire_copy(kwargs["messages"]))
            return self.calls_to_make.pop(0)

    def call(n, name):
        return ToolCall(id=f"call-{n}", name=name, arguments={})

    original = {
        "role": "assistant", "reasoning_content": "test-only protocol marker",
        "tool_calls": [{"id": "call-c", "type": "function",
                        "function": {"name": "analyze_brand", "arguments": "{  }"}}],
    }
    requests = [
        ToolGeneration("同时检查两项。", [call("a", "read"), call("b", "read")]),
        ToolGeneration("", [call("c", "analyze_brand")], assistant_message=original),
        ToolGeneration("", [call("again", "analyze_brand")]),
        *(ToolGeneration(f"查看素材 {i}。", [call(i, "read")]) for i in range(6)),
        ToolGeneration("已完成。", [call("end", "answer")]),
    ]
    provider = Provider(requests)
    monkeypatch.setattr(intent_router, "client", provider)
    events = []

    async def execute(name, params, speech):
        events.append(name)
        return ToolObservation("observed") if name != "answer" else None

    result = await intent_router.call_loop(
        execute, tools=[
            ChatTool(name="analyze_brand", description="Read the brand", params_model=None, terminal=False),
            ChatTool(name="read", description="Read", params_model=None, terminal=False, batchable=True),
            ChatTool(name="answer", description="Reply", params_model=None),
        ],
        message="给 https://www.legitevi.com/en 做一只宣传片",
        speech_language_hint="zh",
        on_interim_prose=events.append,
        on_delta=(lambda _: None) if streaming else None,
    )
    assert original in provider.wires[2]
    assert events[:5] == ["同时检查两项。", "read", "read", "analyze_brand", "analyze_brand"]
    assert events[5:] == [entry for i in range(6) for entry in (f"查看素材 {i}。", "read")] + ["answer"]
    assert result.prose == "已完成。"
