"""Chat message router."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user
from app.models.schemas import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
    MessageUpdate,
)
from app.models.tables import Message, User
from app.services.project_context import get_project_for_user

router = APIRouter()


@router.post(
    "",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    project_id: UUID,
    data: MessageCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Message:
    """Create a chat message in a project thread."""
    project = await get_project_for_user(db, project_id, current_user.id)

    message = Message(
        project_id=project_id,
        role=data.role.value,
        content=data.content,
        attachments=[a.model_dump(mode="json") for a in data.attachments],
        meta=data.meta.model_dump(mode="json") if data.meta else {},
        parent_message_id=data.parent_message_id,
    )
    db.add(message)
    project.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(message)
    return message


@router.get(
    "",
    response_model=MessageListResponse,
)
async def list_messages(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> MessageListResponse:
    """List chat messages for a project, oldest first."""
    await get_project_for_user(db, project_id, current_user.id)

    result = await db.execute(
        select(Message)
        .where(Message.project_id == project_id)
        .order_by(Message.created_at.asc())
    )
    items = list(result.scalars().all())
    return MessageListResponse(items=items)


@router.get(
    "/{message_id}",
    response_model=MessageResponse,
)
async def get_message(
    project_id: UUID,
    message_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Message:
    """Get a single chat message."""
    await get_project_for_user(db, project_id, current_user.id)

    message = await db.get(Message, message_id)
    if message is None or message.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    return message


@router.put(
    "/{message_id}",
    response_model=MessageResponse,
)
async def update_message(
    project_id: UUID,
    message_id: UUID,
    data: MessageUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Message:
    """Update a chat message (e.g. append markers or results)."""
    await get_project_for_user(db, project_id, current_user.id)

    message = await db.get(Message, message_id)
    if message is None or message.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    if data.content is not None:
        message.content = data.content
    if data.attachments is not None:
        message.attachments = [a.model_dump(mode="json") for a in data.attachments]
    if data.meta is not None:
        message.meta = data.meta.model_dump(mode="json")

    await db.commit()
    await db.refresh(message)
    return message


@router.delete(
    "/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_message(
    project_id: UUID,
    message_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a chat message."""
    await get_project_for_user(db, project_id, current_user.id)

    message = await db.get(Message, message_id)
    if message is None or message.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    await db.delete(message)
    await db.commit()
