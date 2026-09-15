"""Generic chat API.

Conversations are the universal container for multi-turn interaction, but the
public API hides conversation management behind a single ``POST /api/v1/chat``
endpoint. The backend locates or creates the project conversation from
``project_id`` (project scope only — the asset scope is retired, ADR-041 D8;
a pointed-at product rides the message as an @-mention chip, ADR-058).

Transport (chat SSE): the endpoint content-negotiates on the ``Accept``
header. Plain callers get the one-shot JSON ``ChatResponse`` (unchanged);
``Accept: text/event-stream`` streams the turn. ADR-077 判词② (2026-09-14):
the action JSON retired into terminal tool calls, so the prose channel IS
the reply — ``assistant.delta`` frames carry it verbatim (dialect-stripped at
the client seam, typewriter law native); ``assistant.thinking`` carries
liveness keepalives and REAL phase labels (drafting / creating_run /
repairing, plus the perception family's ``inspecting`` frames — T2b — which
add the registry entry's i18n copy ``key``; the tool name never crosses to
the user face); ``question.preview`` docks the
pill the moment an ask_user call's arguments validate. The terminal envelope
(``turn.completed`` / ``turn.failed``) stays authoritative.
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
from app.chat.perception import PERCEPTION_TOOLS
from app.chat.service import (
    THINKING_PHASE_DRAFTING,
    THINKING_PHASE_INSPECTING,
    answer_question,
    chat,
    execute_chat_turn,
    find_conversation,
    latest_pending_question,
    list_conversation_messages,
    prepare_chat_turn,
)
from app.providers.llm.base import LLMError
from app.pipeline.errors import user_error_line
from app.platform.project_context import get_project_for_user
from app.ui_locale import current_ui_language

# The trigger-turn agent (T3, ADR-077 判词③) takes no calls HERE either —
# the pipeline's two whitelist seats (warm understanding / run finalized)
# fire it. Importing the module registers "trigger_turn" in AGENTS at
# startup (the service.py precedent for the two chat agents), so a broken
# import fails the boot, never a mid-run first fire.
from app.chat import trigger_turn as _trigger_turn  # noqa: F401

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


def _question_preview_frame(payload: dict) -> str:
    """The ``question.preview`` frame for one validated ask_user call
    (2026-09-09 用户拍板——「选项该和这句话一起来」; 2026-09-14 the tool-loop
    seat): the pill's whole payload (question/options/allow_freeform/slot/
    default_path) has VALIDATED the moment the call's arguments complete —
    the loop may still reject it, so the client rolls the preview back on a
    flip or turn.failed; the terminal envelope stays authoritative."""
    return _sse(
        "question.preview",
        json.dumps(
            {
                "question": payload.get("question"),
                "options": payload.get("options") or [],
                "allow_freeform": payload.get("allow_freeform", True),
                "slot": payload.get("slot"),
                "default_path": payload.get("default_path"),
            },
            ensure_ascii=False,
        ),
    )


_HEARTBEAT_SECONDS = 15


def _make_delta_hook(queue: asyncio.Queue):
    """The prose channel → ``assistant.delta`` frames, verbatim (ADR-077
    判词②: prose is the content channel now — every fragment is reply text,
    dialect-stripped at the client seam; the extractor's JSON-sifting and
    the non-prose keepalive both retired with the action payload)."""
    async def on_delta(fragment: str) -> None:
        await queue.put(_sse("assistant.delta", json.dumps({"text": fragment})))

    return on_delta


def _make_tool_hooks(queue: asyncio.Queue):
    """The structure frames (both turn pumps share the shape):

    - ``on_tool_call``: a call's NAME became known — the phase beat's tool
      seat (相位完整律 2026-09-10, re-seated 2026-09-14): a plan-shaped call
      (present_plan / propose_tasks / apply_edit_ops / edit_graph) moves the
      row's beat to `drafting` the moment the model commits to it, replacing
      the retired "tasks"/"ops" substring scan over the JSON stream — the
      name-known signal is earlier and false-positive-free by construction.
      A PERCEPTION call (T2b 感知族) emits the inspecting family instead:
      phase "inspecting" + the registry entry's i18n copy key — the user
      reads 「正在查曲库…」 while the tool NAME never crosses to the user
      face (简报 §3 禁令).
    - ``on_tool_ready``: an ask_user call's arguments completed and validated
      (pre-execution) — preview-dock the pill NOW instead of waiting out the
      loop. Fires on every iteration; a rejected ask's preview rolls back
      with the turn's other previews.
    """
    async def on_tool_call(name: str) -> None:
        if name in ("present_plan", "propose_tasks", "apply_edit_ops", "edit_graph"):
            await queue.put(
                _sse(
                    "assistant.thinking",
                    json.dumps({"phase": THINKING_PHASE_DRAFTING}),
                )
            )
        elif name in PERCEPTION_TOOLS:
            await queue.put(
                _sse(
                    "assistant.thinking",
                    json.dumps(
                        {
                            "phase": THINKING_PHASE_INSPECTING,
                            "key": PERCEPTION_TOOLS[name].activity_key,
                        }
                    ),
                )
            )

    async def on_tool_ready(name: str, params) -> None:
        if name == "ask_user" and params is not None:
            await queue.put(
                _question_preview_frame(
                    {
                        "question": params.question,
                        "options": [
                            o.model_dump(mode="json") for o in params.options
                        ],
                        "allow_freeform": params.allow_freeform,
                        "slot": getattr(params, "slot", None),
                        "default_path": params.default_path,
                    }
                )
            )

    return on_tool_call, on_tool_ready


def _failure_detail(exc: Exception, ui_language: str) -> str | dict:
    """The ONE error→frame mapping both turn pumps share (2026-09-05 减法批).

    HTTPException detail is client-facing by contract (4xx reasons the JSON
    path would surface). A STRUCTURED detail (the credits.insufficient
    payload, API.md §4) passes through as the object — the client renders
    its typed form (the dock's grey row), never a repr'd dict. LLMError
    = the provider failed (no fabricated default book, 2026-08-14 裁定) —
    the localized provider line (errors.USER_ERROR_LINES) rides the frame;
    the raw 402/429/5xx text stays in structlog. Anything else is an
    internal failure — the JSON path answers "Internal server error" via the
    global handler, so the SSE path must not leak str(exc) either.
    """
    if isinstance(exc, HTTPException):
        return exc.detail if isinstance(exc.detail, dict) else str(exc.detail)
    if isinstance(exc, LLMError):
        return user_error_line(exc, ui_language)
    return "Internal server error"


async def _sse_pump(
    queue: asyncio.Queue,
    task: asyncio.Task,
    completed_event: str,
    failed_event: str,
):
    """The ONE terminal-pump loop both turn streams share (2026-09-05 减法批):
    frames (already-serialized ``str`` items) pass through, tuples terminate
    the stream with ``completed_event`` / ``failed_event``, a quiet client
    gets heartbeat comments, and a disconnect cancels the turn task — which
    lands in the task's ``finally`` BEFORE its commit, so the session
    teardown rolls the turn back ("a failed turn persists nothing").

    Queue protocol (turn-specific bodies only push tuples):
    ``("completed", <JSON-able payload>)`` / ``("failed", <detail str|dict>)``
    — a dict detail is a typed failure payload (credits.insufficient), sent
    as the frame's ``detail`` object verbatim.
    """
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
                yield _sse(completed_event, json.dumps(item[1]))
                return
            else:
                yield _sse(failed_event, json.dumps({"detail": item[1]}))
                return
    finally:
        if not task.done():
            task.cancel()


async def _turn_stream(user_id: UUID, data: ChatRequest, ui_language: str):
    """SSE generator for one chat turn.

    The whole turn (prepare + execute) runs as a task on its OWN session —
    never the request-scoped one: this app's BaseHTTPMiddleware stack closes
    yield-dependency sessions when the route returns, before the generator
    body is iterated (same reason the run-events stream opens AsyncSessionLocal
    per poll). The prose channel lands in the queue as ``assistant.delta``
    frames verbatim; reasoning fragments emit ``assistant.thinking``
    keepalive frames so the indicator stays warm; the tool hooks carry the
    phase beat and the question preview. The turn ends with exactly one
    terminal frame: ``turn.completed`` (the full ChatResponse) or
    ``turn.failed`` (a 4xx-class failure the JSON path would raise as an
    HTTP error — e.g. a recipe rejection — arrives here as a frame instead).

    A client disconnect cancels the response, which lands in the pump's
    ``finally`` (see ``_sse_pump``): the turn task is cancelled before its
    commit, the session teardown rolls back — preserving the "a failed turn
    persists nothing" contract the frontend rollback relies on. (No
    ``request.is_disconnected()`` polling: the middleware's receive-channel
    bookkeeping breaks it.)
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def run_turn() -> None:
        from app.models.database import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                prepared = await prepare_chat_turn(db, user_id, data)
                on_delta = _make_delta_hook(queue)
                on_tool_call, on_tool_ready = _make_tool_hooks(queue)

                async def on_reasoning(_fragment: str) -> None:
                    # Reasoning-content frames: liveness only, never shown.
                    await queue.put(_sse("assistant.thinking", "{}"))

                async def on_phase(phase: str) -> None:
                    # A REAL phase switch (chat-flow-sequencing C): a labelled
                    # thinking frame ({"phase": "drafting" | "creating_run" |
                    # "repairing"}) — the dock's thinking row shows the
                    # phase copy instead of the static fallback. The bare {}
                    # keepalive frames above never carry a phase and never
                    # touch the client's label.
                    await queue.put(
                        _sse("assistant.thinking", json.dumps({"phase": phase}))
                    )

                response = await execute_chat_turn(
                    db, prepared, data, on_delta=on_delta, on_reasoning=on_reasoning,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call, on_tool_ready=on_tool_ready,
                )
            await queue.put(("completed", response.model_dump(mode="json")))
        except Exception as exc:  # noqa: BLE001 — terminal frame, not a crash
            await queue.put(("failed", _failure_detail(exc, ui_language)))

    task = asyncio.create_task(run_turn())
    async for frame in _sse_pump(queue, task, "turn.completed", "turn.failed"):
        yield frame


async def _answer_stream(
    user_id: UUID, message_id: UUID, data: AnswerRequest, ui_language: str
):
    """SSE generator for one answer turn (2026-09-04 验收批).

    Mirrors ``_turn_stream`` for the answer endpoint: the answer's
    continuation IS an LLM turn (a slot answer resumes the BOOK path — the
    echo prose generates here), so an option click deserves the same prose
    stream as a typed turn instead of a frozen second followed by an instant
    blob. Wire is identical — ``assistant.delta`` prose, ``assistant.thinking``
    keepalives / phase labels, the tool hooks (the phase beat + the
    question preview — questions 2..N of the 每轮一问 sequence arrive as
    answer-continuation follow-ups, 2026-09-09 对称拍板), one terminal frame
    (``answer.completed`` = the full AnswerResponse, ``answer.failed`` =
    the JSON path's error as a frame).
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def run_answer() -> None:
        from app.models.database import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                on_delta = _make_delta_hook(queue)
                on_tool_call, on_tool_ready = _make_tool_hooks(queue)

                async def on_phase(phase: str) -> None:
                    await queue.put(
                        _sse("assistant.thinking", json.dumps({"phase": phase}))
                    )

                message, follow_up = await answer_question(
                    db,
                    user_id,
                    message_id,
                    data,
                    on_delta=on_delta,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                )
            await queue.put(
                (
                    "completed",
                    AnswerResponse(
                        answered_question=ChatMessageResponse.model_validate(message),
                        follow_up=(
                            ChatMessageResponse.model_validate(follow_up)
                            if follow_up is not None
                            else None
                        ),
                    ).model_dump(mode="json"),
                )
            )
        except Exception as exc:  # noqa: BLE001 — terminal frame, not a crash
            await queue.put(("failed", _failure_detail(exc, ui_language)))

    task = asyncio.create_task(run_answer())
    async for frame in _sse_pump(queue, task, "answer.completed", "answer.failed"):
        yield frame


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
    reply streams (assistant.delta prose + a terminal turn.completed
    envelope); anything else gets the one-shot JSON ChatResponse (201)
    exactly as before.
    """
    # Access check stays pre-stream on the request session — a 404/403 here is
    # a plain HTTP error on both paths.
    await get_project_for_user(db, data.project_id, UUID(str(current_user.id)))
    if "text/event-stream" not in request.headers.get("accept", ""):
        try:
            return await chat(db, UUID(str(current_user.id)), data)
        except LLMError as e:
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
    request: Request,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> AnswerResponse:
    """Answer a pending question (the ask_user machinery).

    The answer endpoint doubles as the resume mechanism — writing the answer
    is what unblocks the pending decision: a task book start begins the run,
    a choice answer continues the conversation (the follow-up reply rides
    back in the response), interrupt wake lands in phase 4. Bail is a
    graceful exit, never an error.

    With ``Accept: text/event-stream`` the continuation streams
    (``assistant.delta`` prose + a terminal ``answer.completed`` envelope
    carrying this same AnswerResponse) — an option click is the primary
    answering gesture (ADR-053) and its continuation generates the echo
    prose, so it gets the same typing animation as a typed turn. The
    pill-Start path keeps the one-shot JSON (no LLM continuation there).
    """
    if "text/event-stream" not in request.headers.get("accept", ""):
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
    return StreamingResponse(
        _answer_stream(
            UUID(str(current_user.id)), id, data, current_ui_language() or "en"
        ),
        media_type="text/event-stream",
        status_code=status.HTTP_200_OK,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
