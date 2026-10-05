"""取证回放 (2026-10-06): project 7de5bb51「你看看这个」回合的完整 payload
字节级重建——真实 PlanTurn.assemble + intent_router assemble + jinja 渲染，
零 LLM 调用。拨回的世界状态：17:42 装配时不存在 pending 问题（ask 是该
回合的产物），故 latest_pending_question 打回 None。

Run: cd apps/api && uv run python scratch/replay_youkanikan_turn.py
"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

import app.chat.plan_turn as pt_mod
from app.agents.base import jinja_env
from app.chat.intent import intent_router
from app.chat.plan_turn import PlanTurn
from app.models.database import AsyncSessionLocal
from app.models.schemas import ChatRequest
from app.models.tables import Conversation, Message, Project

PROJECT_ID = UUID("7de5bb51-f0bb-4b37-8d9f-431e7ff55821")
USER_MSG_ID = UUID("dc9c4432-f0c7-445d-9934-c8f161366134")
ASK_BORN_AT = datetime(2026, 10, 5, 17, 46, 42, tzinfo=UTC)


async def main() -> None:
    # Dial-back: at assemble time (17:42) no pending question existed — the
    # ask row is THIS turn's product, so the pending probe reads None.
    async def _no_pending(db, cid):  # noqa: ANN001, ANN202
        return None

    pt_mod.latest_pending_question = _no_pending

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, PROJECT_ID)
        conv = (
            await db.execute(
                select(Conversation).where(Conversation.project_id == PROJECT_ID)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at)
                )
            )
            .scalars()
            .all()
        )
        # The route's recent window at 17:42: the turns before this one
        # (the current user row excluded, the ask not yet born).
        recent = [
            m
            for m in rows
            if m.created_at < ASK_BORN_AT and m.id != USER_MSG_ID
        ][-5:]
        request = ChatRequest(project_id=PROJECT_ID, message="你看看这个")
        turn = PlanTurn(db, UUID(str(conv.user_id)), conv, project, request)
        await turn.assemble(recent)
        template_kwargs, _media = intent_router.assemble(**turn.infer_kwargs)
        user_prompt = jinja_env.get_template("intent_router.j2").render(
            **template_kwargs
        )
        print("=" * 30, "SYSTEM", "=" * 30)
        print(intent_router.system)
        print("=" * 30, "USER", "=" * 30)
        print(user_prompt)
        print("=" * 30, "TOOLS", "=" * 30)
        for t in intent_router.tools:
            print("-", getattr(t, "name", t))


asyncio.run(main())
