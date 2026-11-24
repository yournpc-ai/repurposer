"""Deterministic core tests for pending question / approval side-conversation handling
and parallel update_focus batching."""

from __future__ import annotations

from copy import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agents.tool_loop import BatchDeclared, ContextSnapshot, ReadExecuting
from app.chat.intent import intent_router
from app.chat.plan_turn import run_plan_turn
from app.chat.prompts import assemble_video_round
from app.models import database as database_module
from app.models.schemas import ChatRequest
from app.models.tables import Conversation, Message, Project, User
from app.providers.llm.base import ToolCall, ToolGeneration


class _ScriptedClient:
    capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=False)

    def __init__(self, generations: list[ToolGeneration]):
        self._generations = list(generations)
        self.calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        assert self._generations, "Unexpected extra LLM iteration"
        return self._generations.pop(0)


async def _seed_pending_media_permission(db):
    user = User(email=f"{uuid4()}@example.test", name="tester")
    db.add(user)
    await db.flush()
    project = Project(user_id=user.id, title="Side chat project", language="zh")
    db.add(project)
    await db.flush()
    conv = Conversation(user_id=user.id, project_id=project.id, ui_language="zh")
    db.add(conv)
    await db.flush()
    opening = Message(
        id=uuid4(),
        conversation_id=conv.id,
        role="user",
        content="帮我生成一张封面图",
        seq=1,
        turn_state="settled",
    )
    opening.turn_id = opening.id
    db.add(opening)
    await db.flush()
    act_row = Message(
        id=uuid4(),
        conversation_id=conv.id,
        role="assistant",
        content="",
        turn_id=opening.id,
        seq=2,
        intent={
            "type": "activity",
            "frame": {
                "activity_id": "call-img-1",
                "kind": "read",
                "status": "active",
                "call_state": "awaiting_authorization",
                "key": "chat.activity.visualAssets",
            },
        },
    )
    db.add(act_row)
    await db.flush()
    pending_card = Message(
        id=uuid4(),
        conversation_id=conv.id,
        role="assistant",
        content="允许为「产品封面图」生成图片吗？最多使用 4 积分。",
        turn_id=opening.id,
        seq=3,
        question={
            "kind": "question",
            "question": "允许为「产品封面图」生成图片吗？最多使用 4 积分。",
            "options": [
                {"id": "approve", "label": "允许"},
                {"id": "decline", "label": "取消"},
            ],
        },
        intent={
            "editor_media": "media-1",
            "tool": "generate_image",
            "activity_id": str(act_row.id),
            "media_permission": {"quote": {"total": [4, 4]}},
        },
    )
    db.add(pending_card)
    await db.commit()
    return user, project, conv, pending_card, act_row


def test_assemble_video_round_preserves_editor_context_when_pending_without_works():
    pending_card = SimpleNamespace(
        question={
            "kind": "question",
            "question": "允许为「封面」生成图片吗？最多使用 4 积分。",
            "options": [{"id": "approve", "label": "允许"}, {"id": "decline", "label": "取消"}],
        },
        intent={"media_permission": {"quote": {"total": [4, 4]}}},
    )
    assembly = assemble_video_round({
        "tools": intent_router.tools,
        "snapshot": ContextSnapshot("empty"),
        "user_text": "顺便问一下，导出 1080p 要多久？",
        "pending_question": pending_card,
    })
    tool_names = {t.name for t in assembly.tools}
    assert "create_video" in tool_names
    assert "answer" in tool_names
    assert "update_focus" in tool_names
    assert assembly.allow_bare_reply is True
    assert '"awaiting_media_authorization": true' in assembly.context
    assert '"video_target": "unresolved"' not in assembly.context


def _patch_async_session(monkeypatch, database):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.project_context.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.conversation_context.AsyncSessionLocal", database)


@pytest.mark.asyncio
@pytest.mark.parametrize("use_answer_tool", [True, False])
async def test_side_question_with_pending_approval_answers_naturally_and_preserves_card(
    database, monkeypatch, use_answer_tool
):
    _patch_async_session(monkeypatch, database)
    async with database() as db:
        user, project, conv, pending_card, _act_row = await _seed_pending_media_permission(db)
        user_id, project_id, conv_id, pending_id = user.id, project.id, conv.id, pending_card.id

    reply_text = (
        "导出 1080p 短片通常需要 15–30 秒，导出前字体、颜色和位置随时都能调整。"
        "如果你确认要生成刚才那张封面图，可以直接点卡片上的「允许」，不想生图的话告诉我跳过就行。"
    )
    tool_calls = (
        [ToolCall(id="c1", name="answer", arguments={"pending_disposition": "none"})]
        if use_answer_tool
        else []
    )
    client = _ScriptedClient([ToolGeneration(content=reply_text, tool_calls=tool_calls)])
    monkeypatch.setattr(intent_router, "client", client)

    events = []
    async with database() as db:
        project = await db.get(Project, project_id)
        conv = await db.get(Conversation, conv_id)
        user_msg = Message(
            id=uuid4(),
            conversation_id=conv_id,
            role="user",
            content="顺便问一下，导出 1080p 要多久？导出前还能改字体吗？",
            seq=4,
            turn_state="in_flight",
        )
        user_msg.turn_id = user_msg.id
        db.add(user_msg)
        await db.flush()
        recent = list((await db.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq))).all())
        assistant_msg, settled = await run_plan_turn(
            db,
            user_id,
            conv,
            project,
            ChatRequest(project_id=project_id, message=user_msg.content),
            recent=recent,
            turn_id=user_msg.id,
            on_loop_event=events.append,
        )
        await db.commit()

        assert assistant_msg is not None
        assert assistant_msg.content == reply_text
        assert not (assistant_msg.blocks or []), "No stiff system_notice reminder block should be attached"
        assert "这次调整没有完成" not in assistant_msg.content
        assert "I'll state" not in assistant_msg.content
        assert len(client.calls) == 1, "Must settle on iteration 0 with zero retries/cancellations"
        assert settled is None

        refreshed_pending = await db.get(Message, pending_id)
        assert refreshed_pending.answer is None, "Pending authorization card must remain open"


@pytest.mark.asyncio
async def test_explicit_pivot_skip_cleanly_declines_pending_media_permission(database, monkeypatch):
    _patch_async_session(monkeypatch, database)
    async with database() as db:
        user, project, conv, pending_card, act_row = await _seed_pending_media_permission(db)
        user_id, project_id, conv_id = user.id, project.id, conv.id
        pending_id, act_id = pending_card.id, act_row.id

    reply_text = "好，已跳过封面图生成，接下来直接帮你做成动态文字短片。"
    client = _ScriptedClient([
        ToolGeneration(
            content=reply_text,
            tool_calls=[ToolCall(id="c1", name="answer", arguments={"pending_disposition": "skip"})],
        )
    ])
    monkeypatch.setattr(intent_router, "client", client)

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = await db.get(Conversation, conv_id)
        user_msg = Message(
            id=uuid4(),
            conversation_id=conv_id,
            role="user",
            content="明白，先不用生成那张图了，直接做成文字动画吧",
            seq=4,
            turn_state="in_flight",
        )
        user_msg.turn_id = user_msg.id
        db.add(user_msg)
        await db.flush()
        recent = list((await db.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq))).all())
        assistant_msg, settled = await run_plan_turn(
            db,
            user_id,
            conv,
            project,
            ChatRequest(project_id=project_id, message=user_msg.content),
            recent=recent,
            turn_id=user_msg.id,
        )
        await db.commit()

        assert assistant_msg is not None
        assert assistant_msg.content == reply_text
        assert not (assistant_msg.blocks or [])
        assert settled is not None and settled.id == pending_id

        refreshed_pending = await db.get(Message, pending_id)
        assert refreshed_pending.answer["kind"] == "bail"
        assert refreshed_pending.intent["media_result"]["status"] == "declined"

        refreshed_act = await db.get(Message, act_id)
        assert refreshed_act.intent["frame"]["status"] == "cancelled"
        assert refreshed_act.intent["frame"]["call_state"] == "cancelled"


@pytest.mark.asyncio
async def test_pending_disposition_answer_never_auto_approves_paid_media_permission(database, monkeypatch):
    _patch_async_session(monkeypatch, database)
    async with database() as db:
        user, project, conv, pending_card, _act_row = await _seed_pending_media_permission(db)
        user_id, project_id, conv_id, pending_id = user.id, project.id, conv.id, pending_card.id

    client = _ScriptedClient([
        ToolGeneration(
            content="请点击上方授权卡片上的「允许」按钮确认扣费后我再开始生成。",
            tool_calls=[ToolCall(id="c1", name="answer", arguments={"pending_disposition": "answer"})],
        )
    ])
    monkeypatch.setattr(intent_router, "client", client)

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = await db.get(Conversation, conv_id)
        user_msg = Message(
            id=uuid4(),
            conversation_id=conv_id,
            role="user",
            content="可以，生吧",
            seq=4,
            turn_state="in_flight",
        )
        user_msg.turn_id = user_msg.id
        db.add(user_msg)
        await db.flush()
        recent = list((await db.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq))).all())
        _assistant_msg, settled = await run_plan_turn(
            db,
            user_id,
            conv,
            project,
            ChatRequest(project_id=project_id, message=user_msg.content),
            recent=recent,
            turn_id=user_msg.id,
        )
        await db.commit()

        assert settled is None
        refreshed_pending = await db.get(Message, pending_id)
        assert refreshed_pending.answer is None


@pytest.mark.asyncio
async def test_update_focus_batched_with_editor_tool_omits_focus_from_batch_declared():
    from app.agents.tool_loop import ToolObservation

    client = _ScriptedClient([
        ToolGeneration(
            content="",
            tool_calls=[
                ToolCall(id="c_focus", name="update_focus", arguments={"focus": "正在编排 Vox 风格开场幕"}),
                ToolCall(id="c_style", name="set_composition_style", arguments={"preset_id": "vox_editorial"}),
            ],
        ),
        ToolGeneration(
            content="已切换为 Vox 报刊风格。",
            tool_calls=[ToolCall(id="c_done", name="answer", arguments={"pending_disposition": "none"})],
        ),
    ])
    agent = copy(intent_router)
    agent.client = client
    events = []
    executed = []

    async def execute(name, _params, _speech):
        executed.append(name)
        if name == "answer":
            return None
        return ToolObservation("ok", ok=True, context_lifetime="call", persist=False)

    result = await agent.call_loop(
        execute,
        on_loop_event=events.append,
        message="换成 Vox 风格",
    )
    assert result.calls == ["update_focus", "set_composition_style", "answer"]
    assert executed == ["update_focus", "set_composition_style", "answer"]
    declared = [e for e in events if isinstance(e, BatchDeclared)]
    assert len(declared) == 1
    assert [m.tool_name for m in declared[0].members] == ["set_composition_style"]
    executing_tools = [e.tool_name for e in events if isinstance(e, ReadExecuting)]
    assert executing_tools == ["update_focus", "set_composition_style"]
