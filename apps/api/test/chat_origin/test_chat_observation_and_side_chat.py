"""Chat observation and side chat — chat origin contracts."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.agents.tool_loop import ReadExecuting
from app.chat.activity import (
    KIND_STEPS,
    ActivityProjector,
    finalize_steps,
    frame_persistence,
    sanitize_steps,
)
from app.chat.intent import intent_router
from app.models import database as database_module
from app.models.schemas import ChatMessageResponse
from app.models.tables import Conversation, Message, MessageSeqCounter, Project, User
from app.providers.llm.base import ToolCall, ToolGeneration
from test.support.chat_http import scripted_chat
from test.support.db_helpers import _project, _user

pytestmark = pytest.mark.chat_origin




@pytest.mark.asyncio
async def test_update_steps_parallel_batch_sanitization_and_persistence(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.project_context.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.conversation_context.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)

    # Pure projector & sanitization test
    sanitized = sanitize_steps([
        {"title": "处理 clp_abc123 与 550e8400-e29b-41d4-a716-446655440000 画面", "status": "in_progress"},
        {"title": "调用 update_steps 更新进度", "status": "pending"},
    ])
    assert sanitized is not None
    assert "clp_abc123" not in sanitized[0]["title"]
    assert "550e8400" not in sanitized[0]["title"]
    assert "update_steps" not in sanitized[1]["title"]

    finalized = finalize_steps(sanitized, completed=True)
    assert finalized[0]["status"] == "done"
    assert finalized[1]["status"] == "pending"

    projector = ActivityProjector(intent_router.tools)
    assert projector.name_known("update_steps") == []
    emitted = projector.feed_event(
        ReadExecuting(
            tool_name="update_steps",
            call_id="c1",
            params=SimpleNamespace(steps=sanitized),
        )
    )
    assert len(emitted) == 1
    assert emitted[0].kind == KIND_STEPS
    assert emitted[0].activity_id == "__steps__"
    assert frame_persistence(emitted[0]) is None
    assert projector.latest_steps() == sanitized

    # HTTP turn: parallel update_steps + list_project_media -> persisted intent["steps"] & eval_meta
    generations = [
        ToolGeneration(
            content="",
            tool_calls=[
                ToolCall(
                    id="call_steps_1",
                    name="update_steps",
                    arguments={
                        "steps": [
                            {"title": "盘点项目素材", "status": "in_progress"},
                            {"title": "编排三幕短片", "status": "pending"},
                            {"title": "配齐转场音效", "status": "pending"},
                        ]
                    },
                ),
                ToolCall(id="call_media_1", name="list_project_media", arguments={}),
            ],
        ),
        ToolGeneration(
            content="素材已盘点完毕，可以开始制作。",
            tool_calls=[],
        ),
    ]
    _, frames = await scripted_chat(database, monkeypatch, owner, project_id, "先盘点素材再做三幕短片", generations)
    activities = [data for event, data in frames if event == "assistant.activity"]
    for frame in activities:
        assert all(member.get("tool_name") != "update_steps" for member in frame.get("members", []))
    step_frames = [f for f in activities if f["kind"] == KIND_STEPS]
    assert len(step_frames) == 1
    assert len(step_frames[0]["steps"]) == 3
    async with database() as db:
        assistant_msg = await db.get(Message, UUID(frames[-1][1]["assistant_message"]["id"]))

    # Persisted on assistant Message.intent["steps"] (in_progress promoted to done) and eval_meta stored
    assert assistant_msg is not None
    assert assistant_msg.intent["steps"][0]["status"] == "done"
    assert assistant_msg.intent["eval_meta"]["model_name"] == "test-eval-model-v1"
    assert len(assistant_msg.intent["eval_meta"]["system_prompt_sha256"]) == 64

    # Serialized ChatMessageResponse exposes steps and hides eval_meta
    serialized = ChatMessageResponse.model_validate(assistant_msg)
    assert serialized.steps is not None and len(serialized.steps) == 3
    assert "eval_meta" not in (serialized.intent or {})




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
    db.add_all([pending_card, MessageSeqCounter(conversation_id=conv.id, last_seq=3)])
    await db.commit()
    return user, project, conv, pending_card, act_row




@pytest.mark.asyncio
@pytest.mark.parametrize("use_answer_tool", [True, False])
async def test_side_question_with_pending_approval_answers_naturally_and_preserves_card(
    database, monkeypatch, use_answer_tool
):
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
    generations = [ToolGeneration(content=reply_text, tool_calls=tool_calls)]
    client, frames = await scripted_chat(database, monkeypatch, user_id, project_id, "顺便问一下，导出 1080p 要多久？导出前还能改字体吗？", generations,
                                         conversation_id=str(conv_id))
    terminal = frames[-1][1]
    async with database() as db:
        assistant_msg = await db.get(Message, UUID(terminal["assistant_message"]["id"]))
        settled = await db.get(Message, UUID(terminal["answered_question"]["id"])) if terminal["answered_question"] else None

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
    async with database() as db:
        user, project, conv, pending_card, act_row = await _seed_pending_media_permission(db)
        user_id, project_id, conv_id = user.id, project.id, conv.id
        pending_id, act_id = pending_card.id, act_row.id

    reply_text = "好，已跳过封面图生成，接下来直接帮你做成动态文字短片。"
    generations = [
        ToolGeneration(
            content=reply_text,
            tool_calls=[ToolCall(id="c1", name="answer", arguments={"pending_disposition": "skip"})],
        )
    ]
    client, frames = await scripted_chat(database, monkeypatch, user_id, project_id, "明白，先不用生成那张图了，直接做成文字动画吧", generations,
                                         conversation_id=str(conv_id))
    terminal = frames[-1][1]
    async with database() as db:
        assistant_msg = await db.get(Message, UUID(terminal["assistant_message"]["id"]))
        settled = await db.get(Message, UUID(terminal["answered_question"]["id"])) if terminal["answered_question"] else None

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
    async with database() as db:
        user, project, conv, pending_card, _act_row = await _seed_pending_media_permission(db)
        user_id, project_id, conv_id, pending_id = user.id, project.id, conv.id, pending_card.id

    generations = [
        ToolGeneration(
            content="请点击上方授权卡片上的「允许」按钮确认扣费后我再开始生成。",
            tool_calls=[ToolCall(id="c1", name="answer", arguments={"pending_disposition": "answer"})],
        )
    ]
    client, frames = await scripted_chat(database, monkeypatch, user_id, project_id, "可以，生吧", generations,
                                         conversation_id=str(conv_id))
    terminal = frames[-1][1]
    async with database() as db:
        assistant_msg = await db.get(Message, UUID(terminal["assistant_message"]["id"]))
        settled = await db.get(Message, UUID(terminal["answered_question"]["id"])) if terminal["answered_question"] else None

        assert settled is None
        refreshed_pending = await db.get(Message, pending_id)
        assert refreshed_pending.answer is None
