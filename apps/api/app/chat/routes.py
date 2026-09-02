"""Generic chat API.

Conversations are the universal container for multi-turn interaction, but the
public API hides conversation management behind a single ``POST /api/v1/chat``
endpoint. The backend locates or creates the project conversation from
``project_id`` (project scope only — the asset scope is retired, ADR-041 D8;
a pointed-at product rides as ``focus_output``).

Transport (chat SSE): the endpoint content-negotiates on the ``Accept``
header. Plain callers get the one-shot JSON ``ChatResponse`` (unchanged);
``Accept: text/event-stream`` streams the turn: ``assistant.delta`` prose
previews while the verdict JSON generates, then one terminal ``turn.completed``
carrying the exact ChatResponse payload (or ``turn.failed``). The verdict
itself never changes — deltas are a preview channel, the envelope is
authoritative.
"""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.dependencies import DBDep, get_current_user_required
from app.models.schemas import (
    AnswerRequest,
    AnswerResponse,
    ChatMessageResponse,
    ChatRequest,
    ConversationResponse,
    MessageListResponse,
)
from app.models.tables import Conversation, User
from app.chat.service import (
    answer_question,
    chat,
    execute_chat_turn,
    find_conversation,
    latest_pending_question,
    list_conversation_messages,
    prepare_chat_turn,
)
from app.chat.stream_extract import ProseDeltaExtractor
from app.providers.llm.minimax import MiniMaxError
from app.pipeline.errors import user_error_line
from app.platform.project_context import get_project_for_user
from app.ui_locale import current_ui_language

chat_router = APIRouter()


@chat_router.get("/conversation", response_model=ConversationResponse)
async def get_conversation(
    project_id: UUID,
    db: DBDep = None,
    current_user: User = Depends(get_current_user_required),
) -> ConversationResponse | None:
    """Get the project's conversation (project scope only — the asset scope
    is retired, ADR-041 D8).

    Returns 404 if no conversation exists yet; the frontend should then show
    the initial intro and create the conversation on first message via
    ``POST /chat``. Carries the latest unanswered question (dock rebuild).
    """
    await get_project_for_user(db, project_id, UUID(str(current_user.id)))
    conversation = await find_conversation(
        db,
        UUID(str(current_user.id)),
        project_id,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    response = ConversationResponse.model_validate(conversation)
    pending = await latest_pending_question(db, UUID(str(conversation.id)))
    if pending is not None:
        response.pending_question = ChatMessageResponse.model_validate(pending)
    return response


def _sse(event: str, data: str) -> str:
    """One SSE frame (same wire format as the run-events stream)."""
    return f"event: {event}\ndata: {data}\n\n"


_HEARTBEAT_SECONDS = 15


async def _turn_stream(user_id: UUID, data: ChatRequest, ui_language: str):
    """SSE generator for one chat turn.

    The whole turn (prepare + execute) runs as a task on its OWN session —
    never the request-scoped one: this app's BaseHTTPMiddleware stack closes
    yield-dependency sessions when the route returns, before the generator
    body is iterated (same reason the run-events stream opens AsyncSessionLocal
    per poll). Raw LLM fragments feed the prose extractor (book path previews
    ``answer``, the chat loop previews ``text``/``summary``) and decoded prose
    lands in the queue as ``assistant.delta`` frames; fragments with no prose
    (reasoning, the <think> preamble, the verdict JSON tail) emit
    ``assistant.thinking`` keepalive frames so the indicator stays warm. The
    turn ends with exactly one terminal frame: ``turn.completed`` (the full
    ChatResponse) or ``turn.failed`` (a 4xx-class failure the JSON path would
    raise as an HTTP error — e.g. a recipe rejection — arrives here as a
    frame instead).

    A client disconnect cancels the response, hitting the ``finally`` below:
    the turn task is cancelled before its commit, the session teardown rolls
    back — preserving the "a failed turn persists nothing" contract the
    frontend rollback relies on. (No ``request.is_disconnected()`` polling:
    the middleware's receive-channel bookkeeping breaks it.)
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def run_turn() -> None:
        from app.models.database import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                prepared = await prepare_chat_turn(db, user_id, data)
                extractor = ProseDeltaExtractor(
                    ("answer",) if prepared.book_path else ("text", "summary")
                )

                async def on_delta(fragment: str) -> None:
                    text = extractor.feed(fragment)
                    if text:
                        await queue.put(
                            _sse("assistant.delta", json.dumps({"text": text}))
                        )
                    else:
                        # A non-prose fragment (the <think> preamble, the
                        # verdict JSON after the echo closes) still proves the
                        # model is alive — keep the thinking indicator warm.
                        await queue.put(_sse("assistant.thinking", "{}"))

                async def on_reasoning(_fragment: str) -> None:
                    # Reasoning-content frames: liveness only, never shown.
                    await queue.put(_sse("assistant.thinking", "{}"))

                response = await execute_chat_turn(
                    db, prepared, data, on_delta=on_delta, on_reasoning=on_reasoning
                )
            await queue.put(("completed", response.model_dump(mode="json")))
        except Exception as exc:  # noqa: BLE001 — terminal frame, not a crash
            # HTTPException detail is client-facing by contract (4xx reasons
            # the JSON path would surface). MiniMaxError = the provider
            # failed (no fabricated default book, 2026-08-14 裁定) — the
            # localized provider line (errors.USER_ERROR_LINES) rides the
            # frame; the raw 402/429/5xx text stays in structlog. Anything
            # else is an internal failure — the JSON path answers "Internal
            # server error" via the global handler, so the SSE path must not
            # leak str(exc) either.
            detail = (
                exc.detail
                if isinstance(exc, HTTPException)
                else user_error_line(exc, ui_language)
                if isinstance(exc, MiniMaxError)
                else "Internal server error"
            )
            await queue.put(("failed", str(detail)))

    task = asyncio.create_task(run_turn())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if isinstance(item, str):
                yield item
            elif item[0] == "completed":
                yield _sse("turn.completed", json.dumps(item[1]))
                return
            else:
                yield _sse("turn.failed", json.dumps({"detail": item[1]}))
                return
    finally:
        if not task.done():
            task.cancel()


@chat_router.post("", status_code=status.HTTP_201_CREATED)
async def send_chat_message(
    data: ChatRequest,
    request: Request,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
):
    """Send a message to the project's chat.

    The backend locates or creates the conversation, builds the context, and
    dispatches any background work. With ``Accept: text/event-stream`` the
    reply streams (assistant.delta previews + a terminal turn.completed
    envelope); anything else gets the one-shot JSON ChatResponse (201)
    exactly as before.
    """
    # Access check stays pre-stream on the request session — a 404/403 here is
    # a plain HTTP error on both paths.
    await get_project_for_user(db, data.project_id, UUID(str(current_user.id)))
    if "text/event-stream" not in request.headers.get("accept", ""):
        try:
            return await chat(db, UUID(str(current_user.id)), data)
        except MiniMaxError as e:
            # Provider failure on the one-shot path — same honesty rule as
            # the SSE frame: 502 with the localized line, never a fabricated
            # default book (editor dub endpoint precedent, routes/outputs).
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                user_error_line(e, current_ui_language() or "en"),
            ) from e
    return StreamingResponse(
        _turn_stream(
            UUID(str(current_user.id)), data, current_ui_language() or "en"
        ),
        media_type="text/event-stream",
        status_code=status.HTTP_200_OK,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@chat_router.post("/messages/{id}/answer", response_model=AnswerResponse)
async def answer_message(
    id: UUID,
    data: AnswerRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> AnswerResponse:
    """Answer a pending question (ask primitive).

    The answer endpoint doubles as the resume mechanism — writing the answer
    is what unblocks the pending decision: a task book start begins the run,
    a choice answer continues the conversation (the follow-up reply rides
    back in the response), interrupt wake lands in phase 4. Bail is a
    graceful exit, never an error.
    """
    message, follow_up = await answer_question(
        db, UUID(str(current_user.id)), id, data
    )
    return AnswerResponse(
        answered_question=ChatMessageResponse.model_validate(message),
        follow_up=(
            ChatMessageResponse.model_validate(follow_up)
            if follow_up is not None
            else None
        ),
    )
