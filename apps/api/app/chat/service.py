"""Generic chat service.

A conversation is the universal container. It can be project-scoped (the
original prompt plus project-level follow-ups) or asset-scoped (a clip,
LinkedIn post, quote card, etc.).

The public surface is intentionally tiny: ``chat()`` takes a user message,
locates or creates the right conversation, assembles deterministic context,
and lets the intent agent propose (CHAT_ARCH §3):

- task_list (non-empty) → compile_graph mode② → a new WorkflowRun
- task_list (empty)     → ask back — a legal answer, not a failure
- edit_ops              → boundary text (Operation Model is v2), no run

One LLM call per turn; the loop lives between turns, never inside one.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minimax import MiniMaxError
from app.chat.intent import chat_intent_agent
from app.models.schemas import (
    ChatMention,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    EditOpsProposal,
    TaskItem,
    TaskListProposal,
)
from app.models.tables import Asset, Conversation, Message, Project, WorkflowRun
from app.pipeline.outputs import list_visible_outputs
from app.pipeline.registry import SkillRejected, dispatchable_skills

_ASK_BACK_TEXT = (
    "I want to make sure I do the right thing — could you be more specific? "
    "For example: re-cut highlights, remove filler words, add music, "
    "or rewrite a post."
)

_EDIT_OPS_BOUNDARY_TEXT = (
    "That kind of precise edit (trimming a moment, cutting an ending) belongs "
    "in the editor for now — conversational edit ops land with the Operation "
    "Model. What I can do here: re-cut highlights, remove filler words, "
    "score the clips, or revise a script."
)

_REVISE_FALLBACK_TEXT = "Got it — revising this asset based on your instruction."


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
    mentions: list[dict[str, Any]] | None = None,
    workflow_run_id: UUID | None = None,
    intent: dict[str, Any] | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        attachments=attachments or [],
        mentions=mentions or [],
        workflow_run_id=workflow_run_id,
        intent=intent,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


async def _load_project(db: AsyncSession, project_id: UUID) -> Project | None:
    return await db.get(Project, project_id)


def _output_one_liner(output: Any) -> str:
    """A one-line label for a visible output (type + first creative line)."""
    payload = output.payload or {}
    for key in ("hook", "title", "body"):
        text = payload.get(key)
        if text:
            return str(text).split("\n", 1)[0][:80]
    return ""


async def _build_context(
    db: AsyncSession,
    project: Project,
    conversation: Conversation,
    recent: list[Message],
    mentions: list[ChatMention],
) -> dict[str, Any]:
    """Assemble the intent context deterministically (CHAT_ARCH §6, v1 scope):
    project summary (assets / visible outputs / latest run) + the last 3
    rounds + the mention list. Not a chat-history dump."""
    lines = [
        f"Project: {project.title} (id={project.id}, language={project.language})",
    ]

    assets = list(
        (await db.execute(select(Asset).where(Asset.project_id == project.id)))
        .scalars()
        .all()
    )
    if assets:
        lines.append("Assets:")
        for a in assets:
            lines.append(f"- {a.type} id={a.id} status={a.processing_status}")

    outputs = await list_visible_outputs(db, project.id)
    if outputs:
        lines.append("Current outputs:")
        for o in outputs:
            one_liner = _output_one_liner(o)
            lines.append(f"- {o.type} id={o.id}" + (f": {one_liner}" if one_liner else ""))

    latest_run = (
        await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project.id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run is not None:
        lines.append(f"Latest run: status={latest_run.status} id={latest_run.id}")

    if conversation.asset_id:
        lines.append(
            f"This conversation is about the single {conversation.asset_type} "
            f"output id={conversation.asset_id}."
        )

    if recent:
        lines.append("Recent rounds:")
        for m in recent:
            if m.content:
                lines.append(f"- {m.role}: {m.content[:200]}")

    if mentions:
        lines.append("Mentions (definite references):")
        for m in mentions:
            lines.append(f"- {m.type} id={m.id} label={m.label}")

    return {"text": "\n".join(lines)}


async def _create_run_from_tasks(
    db: AsyncSession,
    project: Project,
    conversation: Conversation,
    tasks: list[TaskItem],
    summary: str,
) -> UUID:
    """Dispatch a proposed task list through the ONLY run birthplace."""
    from app.pipeline.orchestrator import TaskSpec, create_run, derive_context_fields

    backfill = derive_context_fields(tasks)
    run = await create_run(
        db,
        project,
        TaskSpec(
            outputs=backfill.get("outputs") or [],
            clip_count=backfill.get("clip_count", 5),
            target_language=project.language or "en",
            instruction=summary,
            scope="full",
            target_id=UUID(str(conversation.asset_id)) if conversation.asset_id else None,
            tasks=tasks,
        ),
    )
    return run.id


def _cannot_do_text() -> str:
    available = ", ".join(entry.name for entry in dispatchable_skills())
    return f"I can't do that yet. What I can do: {available}."


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

    Single public entry point: locate/create the conversation, assemble
    context, let the intent agent propose (one call), adjudicate via
    compile_graph (SkillRejected → one repair round → "I can't do that yet"),
    and record the turn.
    """
    conversation = await _get_or_create_conversation(db, user_id, request)
    conversation_id = UUID(str(conversation.id))

    user_message = await _create_message(
        db,
        conversation_id,
        "user",
        request.message,
        attachments=[a.model_dump(mode="json") for a in request.attachments],
        mentions=[m.model_dump(mode="json") for m in request.mentions],
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

    context = (
        await _build_context(db, project, conversation, history[-6:], request.mentions)
        if project
        else {"text": ""}
    )

    proposal: TaskListProposal | EditOpsProposal | None = None
    try:
        result = await chat_intent_agent.propose(request.message, context)
        proposal = result.proposal
    except MiniMaxError:
        proposal = None

    run_id: UUID | None = None

    if proposal is None:
        # LLM failure fallback: asset-scoped → revise_script兜底;
        # project-scoped → ask back.
        if conversation.asset_id and project is not None:
            try:
                run_id = await _create_run_from_tasks(
                    db,
                    project,
                    conversation,
                    [
                        TaskItem(
                            skill="revise_script",
                            params={
                                "target_output_id": str(conversation.asset_id),
                                "instruction": request.message,
                            },
                        )
                    ],
                    summary=request.message,
                )
                assistant_content = _REVISE_FALLBACK_TEXT
            except (SkillRejected, ValueError):
                assistant_content = _ASK_BACK_TEXT
        else:
            assistant_content = _ASK_BACK_TEXT
    elif isinstance(proposal, EditOpsProposal):
        assistant_content = _EDIT_OPS_BOUNDARY_TEXT
    elif not proposal.tasks:
        assistant_content = proposal.summary or _ASK_BACK_TEXT
    else:
        try:
            run_id = await _create_run_from_tasks(
                db, project, conversation, proposal.tasks, proposal.summary
            )
            assistant_content = proposal.summary
        except ValueError as e:
            # Missing required input (media/transcript/…) — no repair round
            # can fix that; tell the user what's missing.
            assistant_content = f"I'm missing an input for that: {e}"
        except SkillRejected as first_error:
            # One bounded repair round with the rejection as feedback.
            repaired = False
            try:
                retry = await chat_intent_agent.propose(
                    request.message,
                    {
                        **context,
                        "repair_feedback": (
                            f"{first_error} "
                            f"(available: {getattr(first_error, 'suggestions', [])})"
                        ),
                    },
                )
                if (
                    isinstance(retry.proposal, TaskListProposal)
                    and retry.proposal.tasks
                ):
                    run_id = await _create_run_from_tasks(
                        db, project, conversation, retry.proposal.tasks, retry.proposal.summary
                    )
                    proposal = retry.proposal
                    assistant_content = retry.proposal.summary
                    repaired = True
            except (SkillRejected, ValueError, MiniMaxError):
                pass
            if not repaired:
                proposal = None
                assistant_content = _cannot_do_text()

    assistant_message = await _create_message(
        db,
        conversation_id,
        "assistant",
        assistant_content,
        workflow_run_id=run_id,
        intent=proposal.model_dump(mode="json") if proposal else None,
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
