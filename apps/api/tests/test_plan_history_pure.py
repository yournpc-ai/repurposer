"""The approval turn must see the storyboard it just presented."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.chat.context import bounded_history, estimate_message_tokens
from app.models.tables import Message


@pytest.mark.asyncio
async def test_approval_prompt_keeps_budgeted_storyboard_and_final_question(monkeypatch):
    import app.chat.plan_turn as module
    from app.agents.tool_loop import jinja_env
    from app.chat.intent import intent_router
    from app.models.schemas import ChatRequest

    for name in (
        "latest_pending_question", "prime_web_page_captures_from_text",
        "resolve_default_persona",
    ):
        monkeypatch.setattr(module, name, AsyncMock(return_value=None))
    monkeypatch.setattr(module, "has_any_text_material", AsyncMock(return_value=False))
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = SimpleNamespace(execute=AsyncMock(return_value=result), get=AsyncMock(return_value=None))
    board = (
        "分镜如下：\n| 场景 | 画面 |\n"
        + "\n".join(f"| {i} | 官网页面与镜头说明 |" for i in range(1, 30))
        + "\n16:9；配乐 calm；旁白关闭。\n要按这一版开始做成片吗？"
    )
    old = Message(role="user", content="早期讨论" * 500)
    presentation = Message(role="assistant", content=board)
    recent = bounded_history([old, presentation], estimate_message_tokens(presentation))
    turn = module.PlanTurn(
        db, uuid4(), SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4(), user_id=uuid4(), pending_brief=None, persona_id=None),
        ChatRequest(project_id=uuid4(), message="开始做"),
    )
    await turn.assemble(recent)
    kwargs, _ = intent_router.assemble(**turn.infer_kwargs)
    prompt = jinja_env.get_template(intent_router.prompt).render(**kwargs)
    assert board in prompt
    assert "User message: 开始做" in prompt
    assert old.content not in prompt
