from copy import deepcopy
from uuid import uuid4

import pytest

from app.agents.tool_loop import ContextSnapshot, ToolObservation
from app.chat.intent import intent_router
from app.chat.readiness import brief_with_user_constraints
from app.chat.speech_language import conversation_speech_language
from app.models.schemas import (
    BrandColor,
    BrandSourceRef,
    BrandTagline,
    BrandTypography,
    CreativeState,
    MediaInput,
    MediaInputType,
    seal_creative_state,
)
from app.models.tables import Message, SourceSnapshot
from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration
from app.tools.video.brand import build_brand_profile
from app.tools.video.brand_agent import BrandProfileExtraction, brand_profile_agent
from test.core.test_website_promo_readiness import URL, asset, snapshot

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


@pytest.mark.parametrize("submitted", [True, False])
@pytest.mark.parametrize("silent", [True, False])
async def test_storyboard_tool_prose_precedes_work_with_or_without_questionnaire_submit(monkeypatch, submitted, silent):
    from app.chat.prompts import assemble_video_round
    from test.core.test_website_promo_readiness import profile

    text = f"给 {URL} 做一只 30 秒、16:9、使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    state = CreativeState(brief=brief_with_user_constraints(text), brand_profile=profile())
    resources = (("asset:1", asset("completed")), ("snapshot:1", snapshot()))
    world = ContextSnapshot("evidence", frozenset(key for key, _ in resources), resources=resources)
    plan = {"name": "LegitEvi evidence promo", "shots": [{"headline": "用证据说明产品机制"}]}
    provider = FakeToolProvider([("create_video", plan)], content="" if silent else "先从证据链的起点讲起。")
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
        return ToolObservation("draft prepared", version_saved=True, stop_after_observation=True)

    await intent_router.call_loop(
        execute, round_assembler=assemble, message=text,
        on_delta=lambda _: None, on_interim_prose=events.append,
    )
    spoken = []
    if not silent:
        spoken = ["先从证据链的起点讲起。"]
    assert events == [*spoken, "create_video"]
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
    assert "create_video" in tool_names(provider.wires[-1])
    assert "ask_user" in tool_names(provider.wires[1])
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
    failed_names = tool_names(failed_provider.wires[0])
    assert "answer" in failed_names
    assert "create_video" not in failed_names
    assert "design_video" not in failed_names

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
    assert "create_video" in tool_names(generic_provider.wires[0])
    assert not {"design_video", "review_working_draft", "present_plan"} & tool_names(generic_provider.wires[0])
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

async def test_language_of_the_current_edit_overrides_an_older_english_turn():
    from types import SimpleNamespace

    rows = [SimpleNamespace(role="user", content=s) for s in (
        "Inspect the saved timeline and describe both clips.",
        "请裁剪已核对的第二段 elm_b，保留片段局部 0.3 到 7.6 秒，保存后告诉我新时长。",
    )]
    assert conversation_speech_language(rows) == "zh"
    rows[-1].content = "请查看项目素材列表，告诉我有几个素材。只读取，不需要生成。"
    assert conversation_speech_language(rows) == "zh"
    rows[-1].content = "Please inspect the clip named 开场采访 and tell me its duration."
    assert conversation_speech_language(rows) == "en"

async def test_mixed_terminal_and_invalid_member_keep_the_valid_sibling(monkeypatch):
    from app.agents.tool_loop import ChatTool
    from app.chat.editor import ClipArgs

    provider = FakeToolProvider([
        [("answer", {}), ("inspect_clip", {}), ("inspect_clip", {"clip_id": "known"})],
        ("answer", {}),
    ])
    monkeypatch.setattr(intent_router, "client", provider)
    accepted = []

    async def execute(name, params, speech):
        accepted.append(name)
        return ToolObservation("found known") if params is not None else None

    await intent_router.call_loop(
        execute,
        tools=[ChatTool("answer", "Reply", None),
               ChatTool("inspect_clip", "Read one clip", ClipArgs, terminal=False, batchable=True)],
        message="Inspect the clip",
    )
    assert accepted == ["inspect_clip", "answer"]
    replies = [m for m in provider.wires[1]["messages"] if m["role"] == "tool"]
    assert [r["tool_call_id"] for r in replies] == ["call-1-0", "call-1-1", "call-1-2"]
    assert "Not executed" in replies[0]["content"]
    assert "params_validation" in replies[1]["content"]
    assert replies[2]["content"] == "found known"
