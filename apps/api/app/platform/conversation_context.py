"""Owned conversation, pending question and project prompt reads."""

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
        .order_by(Message.seq.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


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
        .order_by(Message.seq.asc())
        .limit(1)
    )
    message = result.scalar_one_or_none()
    return str(message.content) if message and message.content else None
