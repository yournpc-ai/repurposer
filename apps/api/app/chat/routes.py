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
liveness keepalives, the System Status label (``composing`` — the sole
survivor after Phase 3 Batch B retired creating_run on the B4 dead-window
forensics), and the explicit clear frame; ``question.preview`` docks the
pill the moment an ask_user call's arguments validate. The terminal envelope
(``turn.completed`` / ``turn.failed``) stays authoritative.
"""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.contexts import output_one_liner
from app.dependencies import DBDep, get_current_user_required
from app.models.schemas import (
    AnswerRequest,
    AnswerResponse,
    ChatMention,
    ChatMessageResponse,
    ChatRequest,
    ConversationResponse,
    MessageListResponse,
)
from app.models.tables import Conversation, Project, User
from app.chat.activity import ActivityProjector
from app.chat.service import (
    answer_question,
    chat,
    execute_chat_turn,
    list_conversation_messages,
    prepare_chat_turn,
    stamp_turn_failed,
)
from app.providers.llm.base import LLMError
from app.pipeline.errors import user_error_line
from app.platform.conversation_context import (
    find_conversation,
    latest_pending_question,
)
from app.platform.project_context import get_output_for_user, get_project_for_user
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


def _make_tool_hooks(queue: asyncio.Queue, projector: ActivityProjector | None = None):
    """The structure frames (both turn pumps share the shape):

    - ``on_tool_call``: a call's NAME became known — one fact, ONE
      projection (Phase 3 Batch B ③): the Activity projector's
      ``name_known`` (the user-safe work evidence, ADR-087 §3). The retired
      parallel-render System Status labels (drafting / inspecting+key /
      repairing) are gone — the Activity frames speak for the work now
      (三通道分家). Every name-known moment ALSO emits the explicit phase
      clear ``{"phase": null}`` (I-PFA-06 清除协议, 2026-09-18 定型):
      whatever System Status label preceded it (``composing`` — the only
      surviving label, emitted at a read's observation-acceptance) never
      outlives its activity by inheritance; a no-op when no label is set.
      The terminal envelope closes whatever remains (终帧律, client-side).
    - ``on_tool_ready``: an ask_user call's arguments completed and validated
      (pre-execution) — preview-dock the pill NOW instead of waiting out the
      loop. Fires on every iteration; a rejected ask's preview rolls back
      with the turn's other previews.
    """
    async def on_tool_call(name: str) -> None:
        if projector is not None:
            for frame in projector.name_known(name):
                await queue.put(_activity_frame(frame))
        await queue.put(
            _sse("assistant.thinking", json.dumps({"phase": None}))
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


def _activity_frame(frame) -> str:
    """One serialized ``assistant.activity`` frame (ADR-087 §3 Phase 2):
    additive alongside the phase frames; ``_sse_pump`` passes it through
    untouched."""
    return _sse("assistant.activity", json.dumps(frame.to_dict(), ensure_ascii=False))


def _make_loop_event_hook(queue: asyncio.Queue, projector: ActivityProjector):
    """The typed loop-event channel's SSE seat (U1): internal events in,
    user-safe activity frames out — the translation lives entirely in the
    projector."""
    async def on_loop_event(event) -> None:
        for frame in projector.feed_event(event):
            await queue.put(_activity_frame(frame))

    return on_loop_event


def _make_activity_hook(queue: asyncio.Queue, projector: ActivityProjector):
    """The work-session milestone channel's SSE seat (iter-2 ⑥, N-57): the
    plan turn fires ``explore_milestone`` at the exploration door's
    successes; the frame is born-completed and rides the same
    ``assistant.activity`` channel as the loop-event frames."""
    async def on_activity(key: str, count: int) -> None:
        await queue.put(_activity_frame(projector.explore_milestone(key, count=count)))

    return on_activity


async def _sweep_activities(queue: asyncio.Queue, projector: ActivityProjector, outcome: str) -> None:
    """The terminal sweep (T16-B, 终帧律的活动同形): before the envelope,
    every still-active activity is settled — no activity outlives its turn."""
    for frame in projector.sweep(outcome):
        await queue.put(_activity_frame(frame))


def _failure_detail(exc: Exception, ui_language: str) -> str | dict:
    """The ONE error→frame mapping both turn pumps share (2026-09-05 减法批).

    HTTPException detail is client-facing by contract (4xx reasons the JSON
    path would surface). A STRUCTURED detail (the credits.insufficient
    payload, API.md §4) passes through as the object — the client renders
    its typed form (the dock's grey row), never a repr'd dict. LLMError
    = the provider failed (no fabricated default plan, 2026-08-14 裁定) —
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
                # A 3-tuple's third element is the turn-durability flag
                # (交互完整性批 A): the user row survived the failure — the
                # client keeps the bubble instead of rolling it back. The
                # answer stream's 2-tuples simply omit it (their failure
                # semantics are unchanged).
                payload = {"detail": item[1]}
                if len(item) > 2:
                    payload["persisted"] = item[2]
                yield _sse(failed_event, json.dumps(payload))
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
    projector = ActivityProjector()

    async def run_turn() -> None:
        from app.models.database import AsyncSessionLocal

        prepared = None
        turn_user_message_id = None
        try:
            async with AsyncSessionLocal() as db:
                prepared = await prepare_chat_turn(db, user_id, data)
                # Capture pre-rollback (本地变量律 — the B2 fenced-tails
                # MissingGreenlet lesson): the failure stamp below reads this
                # after the turn's session has torn down.
                turn_user_message_id = prepared.user_message.id
                on_delta = _make_delta_hook(queue)
                on_tool_call, on_tool_ready = _make_tool_hooks(queue, projector)
                on_loop_event = _make_loop_event_hook(queue, projector)
                on_activity = _make_activity_hook(queue, projector)

                async def on_reasoning(_fragment: str) -> None:
                    # Reasoning-content frames: liveness only, never shown.
                    await queue.put(_sse("assistant.thinking", "{}"))

                async def on_phase(phase: str) -> None:
                    # A REAL System Status switch: a labelled thinking frame
                    # ({"phase": "composing"}) — the dock's status row shows
                    # the phase copy instead of the static fallback. The bare
                    # {} keepalive frames above never carry a phase and never
                    # touch the client's label. Work evidence rides the
                    # Activity channel, never this one (三通道分家, Phase 3
                    # Batch B).
                    await queue.put(
                        _sse("assistant.thinking", json.dumps({"phase": phase}))
                    )

                async def on_checkpoint(text: str) -> None:
                    # The checkpoint channel (ADR-085): a quiet iteration's
                    # grounded result statement after an eligible read. The
                    # row is persisted runner-side (flush-only, the turn's
                    # one commit lands it); this frame carries the full text
                    # live — the client finalizes the current bubble segment
                    # and types the checkpoint into a new one (the typewriter
                    # law holds: quiet iterations stream nothing, the frame
                    # paces out client-side).
                    await queue.put(
                        _sse("assistant.checkpoint", json.dumps({"text": text}))
                    )

                response = await execute_chat_turn(
                    db, prepared, data, on_delta=on_delta, on_reasoning=on_reasoning,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call, on_tool_ready=on_tool_ready,
                    on_checkpoint=on_checkpoint,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                )
            await _sweep_activities(queue, projector, "completed")
            await queue.put(("completed", response.model_dump(mode="json")))
        except Exception as exc:  # noqa: BLE001 — terminal frame, not a crash
            # Turn durability (交互完整性批 A): the user row committed in
            # prepare SURVIVES this failure — stamp it 'failed' (best-effort,
            # fresh session inside) and tell the client it persisted, so the
            # flow keeps the bubble instead of rolling the user's own words
            # back. A prepare-stage rejection (entry caps) never persisted —
            # persisted=False keeps the old rollback for those.
            if turn_user_message_id is not None:
                await stamp_turn_failed(turn_user_message_id)
            await _sweep_activities(queue, projector, "failed")
            await queue.put(
                ("failed", _failure_detail(exc, ui_language), turn_user_message_id is not None)
            )
        except BaseException:
            # Cancel (the client disconnected mid-turn): same durability
            # stamp, then let the cancellation propagate.
            if turn_user_message_id is not None:
                await stamp_turn_failed(turn_user_message_id)
            raise

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
    projector = ActivityProjector()

    async def run_answer() -> None:
        from app.models.database import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                on_delta = _make_delta_hook(queue)
                on_tool_call, on_tool_ready = _make_tool_hooks(queue, projector)
                on_loop_event = _make_loop_event_hook(queue, projector)
                on_activity = _make_activity_hook(queue, projector)

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
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                )
            await _sweep_activities(queue, projector, "completed")
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
            await _sweep_activities(queue, projector, "failed")
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
            # default plan (editor dub endpoint precedent, routes/outputs).
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
    is what unblocks the pending decision: a plan start begins the run,
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


# ---- Output regeneration (ADR-058) ------------------------------------------
# The card's Regenerate click IS the pointing gesture: this endpoint is an
# Agent Interface operation wearing an /outputs URL — it synthesizes the
# user's chat turn with the output riding as an @-mention chip. It lives in
# the chat layer (its transport), mounted at /api/v1/outputs by the
# composition root (Phase 5 dependency direction — pipeline never imports
# chat; moved verbatim from pipeline/routes/outputs.py).

outputs_regenerate_router = APIRouter()

CLIP_TYPES = {"clip"}
DERIVATIVE_TYPES = {"post", "quotes", "carousel", "article"}


class OutputRegenerateRequest(BaseModel):
    """Request to regenerate an output with an optional instruction."""

    instruction: str | None = Field(
        default=None,
        description="Steering prompt for the regeneration.",
    )
    target_language: str = Field(
        default="en",
        description="Target language code, e.g. en/zh/fr/de/es/it",
    )


@outputs_regenerate_router.post("/{output_id}/regenerate", response_model=dict)
async def regenerate_output(
    output_id: UUID,
    data: OutputRegenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Queue regeneration of a single output through the generic chat layer."""
    output = await get_output_for_user(db, output_id, UUID(str(current_user.id)))
    if output.type not in CLIP_TYPES | DERIVATIVE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Output type {output.type} is not regenerable",
        )
    # 归档不可变 (Final Hardening B2, ADR-091 §5): regenerating an archived
    # version would rewrite history in place — restore it first.
    if output.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archived version is read-only — restore it first "
            "(POST /outputs/{id}/restore)",
        )

    project = await db.get(Project, output.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # The fallback message lands in the MAIN project conversation's history
    # as the user's own turn (asset-scoped chats are retired, ADR-041 D8) —
    # localize it like every other server-composed user-facing line.
    zh = (current_ui_language() or "en").startswith("zh")
    type_label = (
        {"clip": "视频", "quotes": "金句卡", "post": "帖子",
         "carousel": "轮播", "article": "文章"}.get(output.type, output.type)
        if zh else output.type
    )
    result = await chat(
        db,
        UUID(str(current_user.id)),
        ChatRequest(
            project_id=UUID(str(project.id)),
            message=data.instruction or (
                f"重做这个{type_label}" if zh else f"Regenerate this {output.type}"
            ),
            # Asset-scoped conversations are retired (ADR-041 D8): the card's
            # Regenerate click IS the pointing gesture, so the output rides as
            # an @-mention chip (ADR-058 — the definite-reference channel; the
            # pinned id resolves the revision target deterministically).
            mentions=[
                ChatMention(
                    type="output",
                    id=str(output_id),
                    label=output_one_liner(output) or output.type,
                )
            ],
        ),
    )

    return {
        "run_id": str(result.run_id) if result.run_id else None,
        "message_id": str(result.assistant_message.id),
        "conversation_id": str(result.conversation_id),
    }
