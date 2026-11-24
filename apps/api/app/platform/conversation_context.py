"""Owned conversation, pending question and project prompt reads."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Conversation, Message


def visible_conversation_message_filter():
    """SQL predicate matching visible chat messages (excluding internal activity/forensics/partial rows)."""
    return or_(
        Message.intent.is_(None),
        Message.intent["type"].astext.is_(None),
        ~Message.intent["type"].astext.in_(
            ("activity", "activity_forensics", "candidates_log", "partial")
        ),
    )


async def find_conversation(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    conversation_id: UUID | None = None,
) -> Conversation | None:
    """Return a specific project conversation or the most recently active one."""
    stmt = select(Conversation).where(
        Conversation.user_id == user_id,
        Conversation.project_id == project_id,
        Conversation.asset_id.is_(None),
    )
    if conversation_id is not None:
        stmt = stmt.where(Conversation.id == conversation_id)
    else:
        stmt = stmt.order_by(
            Conversation.updated_at.desc().nullslast(),
            Conversation.created_at.desc(),
            Conversation.id.desc(),
        ).limit(1)
    result = await db.execute(stmt)
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
        .order_by(Conversation.created_at.asc(), Message.seq.asc())
        .limit(1)
    )
    message = result.scalar_one_or_none()
    return str(message.content) if message and message.content else None
