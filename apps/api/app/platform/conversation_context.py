"""Conversation-store read protocol (ADR-087 §6; MODULE_ARCH §4「Pipeline 只读」).

The Agent Interface OWNS ``conversations`` / ``messages`` — every WRITE
lives in ``app.chat.service`` (the pipeline's runtime/transport reaches the
few it needs through ``app.pipeline.conversation_bridge``). The READ shapes
below are the store's shared read protocol: pipeline's read access is
contract-sanctioned (§4 — run-association display, the lifecycle stamp's
chat facts, the original-prompt read), and one seat keeps one query shape
from forking across layers. Zero writes here, ever.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Conversation, Message


async def find_conversation(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
) -> Conversation | None:
    """Return the project's chat conversation, or None. (Conversations are
    project-scope only — the asset scope is retired, ADR-041 D8.)"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.project_id == project_id,
            Conversation.asset_id.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def latest_pending_question(
    db: AsyncSession, conversation_id: UUID
) -> Message | None:
    """The conversation's latest unanswered question (dock rebuild source).

    Zero in-memory state: the pending question is a plain row query (NULL
    answer = pending), so refresh / cross-device revival is free.
    """
    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.question.isnot(None),
            Message.answer.is_(None),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def is_pending_plan(message: Message | None) -> bool:
    """A startable confirmation target (G-1): an unanswered task_book
    question — the only question kind a prose "start it" may answer."""
    return (
        message is not None
        and message.answer is None
        and (message.question or {}).get("kind") == "task_book"
    )


async def get_project_prompt(db: AsyncSession, project_id: UUID) -> str | None:
    """Return the original prompt from the project's chat conversation."""
    result = await db.execute(
        select(Message)
        .join(Conversation)
        .where(
            Conversation.project_id == project_id,
            Conversation.asset_id.is_(None),
            Message.role == "user",
        )
        .order_by(Message.created_at.asc())
        .limit(1)
    )
    message = result.scalar_one_or_none()
    return str(message.content) if message and message.content else None
