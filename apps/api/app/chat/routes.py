"""Generic chat API.

Conversations are the universal container for multi-turn interaction, but the
public API hides conversation management behind a single ``POST /api/v1/chat``
endpoint. The backend locates or creates the right conversation based on
``project_id`` and optional ``asset_id`` / ``asset_type``.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.chat.intent import composer_intent_agent
from app.dependencies import DBDep, get_current_user_required
from app.models.schemas import (
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    InferIntentRequest,
    InferIntentResponse,
    MessageListResponse,
)
from app.models.tables import Conversation, User
from app.chat.service import chat, find_conversation, list_conversation_messages
from app.platform.project_context import get_project_for_user

chat_router = APIRouter()


@chat_router.get("/conversation", response_model=ConversationResponse)
async def get_conversation(
    project_id: UUID,
    asset_id: UUID | None = None,
    asset_type: Literal["clip", "derivative"] | None = None,
    db: DBDep = None,
    current_user: User = Depends(get_current_user_required),
) -> Conversation | None:
    """Get the existing conversation for a project or asset scope.

    Returns 404 if no conversation exists yet; the frontend should then show
    the initial intro and create the conversation on first message via
    ``POST /chat``.
    """
    await get_project_for_user(db, project_id, UUID(str(current_user.id)))
    conversation = await find_conversation(
        db,
        UUID(str(current_user.id)),
        project_id,
        asset_id,
        asset_type,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


@chat_router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def send_chat_message(
    data: ChatRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> ChatResponse:
    """Send a message to a project or asset chat.

    The backend automatically locates or creates the conversation, builds the
    appropriate context, and dispatches any background work.
    """
    await get_project_for_user(db, data.project_id, UUID(str(current_user.id)))
    return await chat(db, UUID(str(current_user.id)), data)


@chat_router.get("/conversations/{id}/messages", response_model=MessageListResponse)
async def list_chat_messages(
    id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> MessageListResponse:
    """List messages in a conversation, oldest first."""
    conversation = await db.get(Conversation, id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    messages = await list_conversation_messages(db, id)
    return MessageListResponse(items=[ChatMessageResponse.model_validate(m) for m in messages])


# ---- Intent inference -------------------------------------------------

intent_router = APIRouter()


@intent_router.post("/infer-intent", response_model=InferIntentResponse)
async def infer_intent(request: InferIntentRequest) -> InferIntentResponse:
    """Infer structured generation intent from a user prompt.

    Returns suggested language, outputs, tone and a distilled instruction.
    The frontend presents these as an editable confirmation layer.
    """
    intent = await composer_intent_agent.infer(
        prompt=request.prompt,
        filename=request.filename,
    )
    return InferIntentResponse(intent=intent)
