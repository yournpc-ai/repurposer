"""Generic chat service.

A chat conversation is the universal container. It can be project-scoped (the
original prompt plus project-level follow-ups) or asset-scoped (a clip,
LinkedIn post, quote card, etc.).

The public surface is intentionally tiny: ``chat()`` takes a user message,
locates or creates the right conversation, builds the correct context, and returns
an assistant reply. Background work is dispatched through ``WorkflowRun``.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ChatIntent, ChatMessageResponse, ChatRequest, ChatResponse
from app.models.tables import Conversation, Message, Project


async def _get_or_create_project_conversation(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.project_id == project_id,
            Conversation.asset_id.is_(None),
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(
            user_id=user_id,
            project_id=project_id,
            title="Project chat",
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
    return conversation


async def _get_or_create_asset_conversation(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    asset_id: UUID,
    asset_type: str,
    title: str | None = None,
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.project_id == project_id,
            Conversation.asset_id == asset_id,
            Conversation.asset_type == asset_type,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(
            user_id=user_id,
            project_id=project_id,
            asset_id=asset_id,
            asset_type=asset_type,
            title=title or f"{asset_type} chat",
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
    return conversation


async def _get_or_create_conversation(
    db: AsyncSession,
    user_id: UUID,
    request: ChatRequest,
) -> Conversation:
    if request.asset_id and request.asset_type:
        return await _get_or_create_asset_conversation(
            db,
            user_id,
            request.project_id,
            request.asset_id,
            request.asset_type,
        )
    return await _get_or_create_project_conversation(db, user_id, request.project_id)


async def _create_message(
    db: AsyncSession,
    conversation_id: UUID,
    role: str,
    content: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
    workflow_run_id: UUID | None = None,
    intent: dict[str, Any] | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        attachments=attachments or [],
        workflow_run_id=workflow_run_id,
        intent=intent,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


async def _load_project(db: AsyncSession, project_id: UUID) -> Project | None:
    return await db.get(Project, project_id)


def _build_context(
    project: Project,
    conversation: Conversation,
    messages: list[Message],
) -> dict[str, Any]:
    """Build the context object fed to the chat intent parser."""
    return {
        "project": {
            "id": str(project.id),
            "title": project.title,
            "event_name": project.event_name,
            "language": project.language,
        },
        "conversation": {
            "id": str(conversation.id),
            "scope": "asset" if conversation.asset_id else "project",
            "asset_id": str(conversation.asset_id) if conversation.asset_id else None,
            "asset_type": conversation.asset_type,
        },
        "history": [
            {"role": m.role, "content": m.content} for m in messages[-20:]
        ],
    }


async def _parse_chat_intent(
    context: dict[str, Any],
    user_message: str,
) -> ChatIntent:
    """Parse a user message into a structured chat intent.

    Lightweight rule-based fallback so the chat module works before the
    LLM-based parser is wired in. The contract (ChatIntent) is stable, so
    swapping to an LLM call later is a drop-in change.
    """
    text = user_message.lower()

    # Translation
    for lang in ("german", "french", "spanish", "italian", "chinese"):
        if lang in text or f"to {lang[:2]}" in text:
            return ChatIntent(
                action="translate",
                target_language=_lang_code(lang),
                instruction=user_message,
            )

    # Render
    if "render" in text or "export" in text or "生成视频" in text:
        return ChatIntent(action="render", instruction=user_message)

    # Shorten / lengthen
    if "shorter" in text or "短一点" in text or "缩短" in text:
        return ChatIntent(action="revise", operation="shorten", instruction=user_message)
    if "longer" in text or "长一点" in text or "加长" in text:
        return ChatIntent(action="revise", operation="lengthen", instruction=user_message)

    # Music
    if "music" in text or "音乐" in text or "bgm" in text:
        if "remove" in text or "去掉" in text or "关" in text:
            return ChatIntent(action="toggle_music", parameters={"enabled": False})
        return ChatIntent(action="select_music", instruction=user_message)

    # Default: generic revise/regenerate
    return ChatIntent(action="revise", instruction=user_message)


def _lang_code(name: str) -> str:
    mapping = {
        "german": "de",
        "french": "fr",
        "spanish": "es",
        "italian": "it",
        "chinese": "zh",
    }
    return mapping.get(name, "en")


def _reply_for_intent(intent: ChatIntent, has_run: bool) -> str:
    """Return a short assistant reply based on the parsed intent."""
    if intent.action == "translate":
        lang = intent.target_language or "the requested language"
        return f"Translating to {lang}..." if has_run else f"Translated to {lang}."
    if intent.action == "render":
        return "Rendering the video..." if has_run else "Rendered."
    if intent.action == "revise":
        return "Revising based on your feedback..." if has_run else "Revised."
    if intent.action in ("select_music", "generate_music"):
        return "Updating the music..." if has_run else "Music updated."
    if intent.action == "toggle_music":
        enabled = intent.parameters.get("enabled", True)
        return "Music enabled." if enabled else "Music disabled."
    return "Got it."


async def _dispatch_intent_to_run(
    db: AsyncSession,
    conversation: Conversation,
    intent: ChatIntent,
) -> UUID | None:
    """Dispatch a parsed intent to a WorkflowRun via the orchestrator.

    Returns the created run id, or None if the intent needs no background work.
    """
    from app.pipeline.orchestrator import TaskSpec, create_run

    scope = "full"
    target_id = None
    if conversation.asset_type == "clip":
        scope = "clip"
        target_id = UUID(str(conversation.asset_id)) if conversation.asset_id else None
    elif conversation.asset_type == "derivative":
        scope = "derivative"
        target_id = UUID(str(conversation.asset_id)) if conversation.asset_id else None

    operation = "regenerate"
    if intent.action == "translate":
        operation = "translate"
    elif intent.action == "render":
        operation = "render"
    elif intent.action == "revise":
        operation = intent.parameters.get("operation", "regenerate")

    project = await db.get(Project, UUID(str(conversation.project_id)))
    if project is None:
        return None

    run = await create_run(
        db,
        project,
        TaskSpec(
            outputs=["clips"] if scope == "clip" else [],
            clip_count=1,
            target_language=intent.target_language or "en",
            instruction=intent.instruction,
            scope=scope,
            operation=operation,
            target_id=target_id,
        ),
    )
    return run.id


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


async def seed_project_prompt(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    prompt: str,
) -> Message:
    """Create the project-scoped conversation and store the original prompt."""
    conversation = await _get_or_create_project_conversation(db, user_id, project_id)
    return await _create_message(db, UUID(str(conversation.id)), "user", prompt)


async def chat(
    db: AsyncSession,
    user_id: UUID,
    request: ChatRequest,
) -> ChatResponse:
    """Send a message to a chat conversation and return the assistant reply.

    This is the single public entry point for chat: it locates or creates the
    conversation, builds the correct context, parses intent, dispatches background
    work, and returns the assistant message.
    """
    conversation = await _get_or_create_conversation(db, user_id, request)
    conversation_id = UUID(str(conversation.id))

    user_message = await _create_message(
        db,
        conversation_id,
        "user",
        request.message,
        attachments=[a.model_dump(mode="json") for a in request.attachments],
    )

    project = await _load_project(db, UUID(str(conversation.project_id)))
    history = list(
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
        ).scalars()
    )

    context = _build_context(project, conversation, history) if project else {}
    intent = await _parse_chat_intent(context, request.message)

    run_id: UUID | None = None
    if intent.action not in ("toggle_music", "adjust_gain"):
        run_id = await _dispatch_intent_to_run(db, conversation, intent)

    assistant_content = _reply_for_intent(intent, run_id is not None)
    assistant_message = await _create_message(
        db,
        conversation_id,
        "assistant",
        assistant_content,
        workflow_run_id=run_id,
        intent=intent.model_dump(mode="json"),
    )

    await db.commit()
    return ChatResponse(
        conversation_id=conversation_id,
        user_message=ChatMessageResponse.model_validate(user_message),
        assistant_message=ChatMessageResponse.model_validate(assistant_message),
        run_id=run_id,
    )


async def find_conversation(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    asset_id: UUID | None = None,
    asset_type: str | None = None,
) -> Conversation | None:
    """Return an existing chat conversation for the given scope, or None."""
    query = select(Conversation).where(
        Conversation.user_id == user_id,
        Conversation.project_id == project_id,
    )
    if asset_id and asset_type:
        query = query.where(
            Conversation.asset_id == asset_id,
            Conversation.asset_type == asset_type,
        )
    else:
        query = query.where(Conversation.asset_id.is_(None))
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_conversation_messages(
    db: AsyncSession,
    conversation_id: UUID,
) -> list[Message]:
    """Return messages in a conversation, oldest first."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())
