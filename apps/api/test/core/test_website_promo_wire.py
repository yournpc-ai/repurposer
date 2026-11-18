import json
from copy import deepcopy
from uuid import uuid4

import pytest

from app.agents.tool_loop import ContextSnapshot, ToolObservation
from app.chat.intent import intent_router
from app.chat.readiness import brief_with_user_constraints
from app.chat.service import _backfill_brief_group
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
from app.models.tables import Project, SourceSnapshot
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

    def __init__(self, calls):
        self.calls_to_make = list(calls)
        self.wires = []

    async def generate_with_tools(self, *, messages, tools, **kwargs):
        self.wires.append({"messages": wire_copy(messages), "tools": wire_copy(tools)})
        name, arguments = self.calls_to_make.pop(0)
        return ToolGeneration(
            content="我来处理这一步。",
            tool_calls=[ToolCall(id=f"call-{len(self.wires)}", name=name, arguments=arguments)],
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


def group_arguments():
    values = (
        ("purpose", "website"),
        ("target_seconds", "60"),
        ("narrative_mode", "mission_tech"),
        ("narration_language", "en"),
        ("subtitle_languages", "en"),
        ("aspect", "16:9"),
    )
    return {
        "question": "Confirm the production setup",
        "options": [],
        "items": [
            {
                "slot": slot,
                "question": f"Choose {slot}",
                "options": [option_id],
                "required": True,
                "allow_freeform": True,
                "default_path": f"Safe {slot}",
            }
            for slot, option_id in values
        ],
        "default_path": "Use safe defaults",
    }


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


async def test_vague_legitevi_wire_gates_source_brand_group_then_design(monkeypatch):
    provider = FakeToolProvider(
        [
            ("prepare_video_materials", {"material_urls": [URL]}),
            ("analyze_brand", {}),
            ("ask_user", group_arguments()),
        ]
    )
    monkeypatch.setattr(intent_router, "client", provider)
    brand_fake = BrandFakeClient()
    monkeypatch.setattr(brand_profile_agent, "client", brand_fake)
    text = f"给 {URL} 做一只宣传片"
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
        dialogue=[{"role": "user", "content": text}],
        message="",
        material_pending_line=(
            "Website capture is pending for this URL. The page is not readable evidence yet."
        ),
    )
    assert result.tool_name == "ask_user"
    assert len(provider.wires) == 3
    assert tool_names(provider.wires[0]) == {"prepare_video_materials", "answer"}
    assert tool_names(provider.wires[1]) == {"analyze_brand", "answer"}
    assert tool_names(provider.wires[2]) == {"ask_user", "answer"}
    assert "design_video" not in tool_names(provider.wires[2])
    for wire in provider.wires:
        assert wire["messages"].count({"role": "user", "content": text}) == 1
        assert [message["role"] for message in wire["messages"][:2]] == ["system", "user"]
        assert "一轮一问" not in json.dumps(wire["tools"], ensure_ascii=False)
        assert "five slots" not in json.dumps(wire["tools"], ensure_ascii=False)
    first_user = provider.wires[0]["messages"][1]["content"]
    assert "Website capture is pending" in first_user
    assert "No file uploaded" not in first_user
    first_system = provider.wires[0]["messages"][0]["content"]
    assert "WEBSITE PROMO EVIDENCE" in first_system
    assert first_system.index("READ TOOLS:") < first_system.index("Video works")
    assert first_system.index("Video works") < first_system.index("- answer:")
    full_context = "\n".join(
        str(message.get("content")) for message in provider.wires[0]["messages"]
    )
    assert "CURRENT ROUTE: website_promo" in full_context
    assert "Capture ready: false" in full_context
    assert "Text ready: false" in full_context
    assert "Required views ready: false" in full_context
    assert "Brief ready: false" in full_context
    assert '"required_next_action": "prepare_video_materials"' in full_context
    assert full_context.count('"required_next_action":') == 1
    assert '"source_readiness"' not in full_context
    brand_parts = brand_fake.messages[1]["content"]
    assert sum(part.get("type") == "image_url" for part in brand_parts) == 1
    assert "Citations should be as universal as hashtags." in brand_parts[-1]["text"]

    ask_arguments = provider.wires[2]["messages"][0]
    assert "WEBSITE PROMO BRIEFING" in ask_arguments["content"]
    ask_system = ask_arguments["content"]
    assert ask_system.index("Video works") < ask_system.index("- answer:")
    assert ask_system.index("- answer:") < ask_system.index("- ask_user:")
    assert ask_system.index("- ask_user:") < ask_system.index("PENDING QUESTION:")
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
    assert ask_schema["properties"]["items"]["minItems"] == 1
    assert "Brief" not in ask_schema.get("$defs", {})
    assert "required" not in ask_schema["$defs"]["BriefQuestionItem"]["properties"]
    assert "allow_freeform" not in ask_schema["$defs"]["BriefQuestionItem"]["properties"]
    assert ask_schema["$defs"]["BriefQuestionItem"]["properties"]["slot"]["enum"] == [
        "purpose", "target_seconds", "narrative_mode", "narration_language",
        "subtitle_languages", "aspect",
    ]
    assert "Option" not in ask_schema.get("$defs", {})
    assert ask_schema["$defs"]["BriefQuestionItem"]["properties"]["options"]["items"]["type"] == "string"
    assert "recommended_id" not in ask_schema["$defs"]["BriefQuestionItem"]["properties"]
    assert [option.id for option in result.params.items[0].options] == ["1"]
    asked = result.params
    assert len(asked.items) == 6
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
    answers = [
        BriefAnswerItem(
            slot=item.slot, kind="option", option_id=item.options[0].id, text=item.options[0].label
        )
        for item in asked.items
    ]
    _backfill_brief_group(project, payload, answers)
    state = PendingPlan.model_validate(project.pending_brief).creative_state

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

    dialogue = [{"role": "user", "content": text}, {"role": "assistant", "content": "旁白语言？"},
                {"role": "user", "content": "英语"}]
    await intent_router.call_loop(
        execute_answer,
        dialogue=dialogue,
        round_assembler=assemble_answer,
        refresh_context=refresh_context,
        message="",
    )
    assert len(resumed_provider.wires) == 1
    messages = resumed_provider.wires[0]["messages"]
    assert messages[-3:] == dialogue
    assert "design_video" in tool_names(resumed_provider.wires[0])
    assert '"required_next_action": "design_video"' in str(resumed_provider.wires[0]["messages"])


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
    assert tool_names(failed_provider.wires[0]) == {"answer"}

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
    assert "CURRENT ROUTE: website_promo" not in str(generic_provider.wires[0]["messages"])
    assert "promo-video" not in generic_provider.wires[0]["messages"][0]["content"]





@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_one_service_message_per_accepted_call_without_a_turn_cap(monkeypatch, streaming):
    from app.agents.tool_loop import ChatTool, ToolObservation

    class Provider(FakeToolProvider):
        async def generate_with_tools(self, **kwargs):
            return self.calls_to_make.pop(0)

    def call(n, name):
        return ToolCall(id=f"call-{n}", name=name, arguments={})

    requests = [
        ToolGeneration("这一批不应执行。", [call("a", "read"), call("b", "read")]),
        ToolGeneration("", [call("c", "read")]),
        *(ToolGeneration(f"查看素材 {i}。", [call(i, "read")]) for i in range(6)),
        ToolGeneration("已完成。", [call("end", "answer")]),
    ]
    provider = Provider(requests)
    monkeypatch.setattr(intent_router, "client", provider)
    events = []

    async def execute(name, params, speech):
        events.append(name)
        return ToolObservation("observed") if name == "read" else None

    result = await intent_router.call_loop(
        execute, tools=[
            ChatTool(name="read", description="Read", params_model=None, terminal=False, batchable=True),
            ChatTool(name="answer", description="Reply", params_model=None),
        ],
        message="给 https://www.legitevi.com/en 做一只宣传片",
        on_interim_prose=events.append,
        on_delta=(lambda _: None) if streaming else None,
    )
    assert events == [entry for i in range(6) for entry in (f"查看素材 {i}。", "read")] + ["answer"]
    assert result.prose == "已完成。"
