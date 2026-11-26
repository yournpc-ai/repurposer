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
liveness keepalives and the explicit phase-clear frame; ``question.preview`` docks the
pill the moment an ask_user call's arguments validate. The terminal envelope
(``turn.completed`` / ``turn.failed``) stays authoritative.
"""

import asyncio
import json
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import func, select

from app.agents.contexts import output_one_liner
from app.agents.tool_loop import BatchDeclared, BatchMember, ReadExecuting
from app.chat.activity import (
    KIND_READ,
    STATUS_ACTIVE,
    ActivityProjector,
    frame_persistence,
    project_tool_detail,
)
from app.chat.run_bus import run_bus
from app.chat.service import (
    TurnStopped,
    answer_question,
    append_activity_row,
    chat,
    compact_conversation_context,
    execute_chat_turn,
    list_conversation_messages,
    mark_turn_steps_failed,
    persist_partial_prose,
    persist_turn_failed_line,
    prepare_chat_turn,
    record_activity_forensics,
    record_candidates_log,
    settle_activity_row,
    settle_interrupted_turn,
    settle_failed_chat_turn,
    stamp_turn_failed,
    stop_turn_at_visible_frontier,
    upsert_message_feedback,
)
from app.chat.turn_tools import make_tool_echo_delta_filter
from app.dependencies import DBDep, get_current_user_required
from app.models.schemas import (
    ActiveRunSummary,
    AnswerRequest,
    AnswerResponse,
    ChatMention,
    ChatMessageResponse,
    ChatRequest,
    ChatTurnStopRequest,
    CompactConversationResponse,
    ConversationResponse,
    MessageFeedbackRequest,
    MessageFeedbackResponse,
    MessageFeedbackSummary,
    MessageListResponse,
    ProjectConversationSummary,
    RenameConversationRequest,
)
from app.models.tables import Conversation, ExportJob, MediaJob, Message, MessageFeedback, Project, User
from app.pipeline.errors import user_error_line
from app.platform.conversation_context import (
    find_conversation,
    latest_pending_question,
    visible_conversation_message_filter,
)
from app.platform.project_context import get_output_for_user, get_project_for_user
from app.providers.llm.base import LLMError
from app.ui_locale import current_ui_language

logger = structlog.get_logger()

chat_router = APIRouter()


@chat_router.get("/conversation", response_model=ConversationResponse)
async def get_conversation(
    project_id: UUID,
    conversation_id: UUID | None = None,
    include_context: bool = False,
    db: DBDep = None,
    current_user: User = Depends(get_current_user_required),
) -> ConversationResponse | None:
    """Get a specific project conversation or the most recently active one.

    Returns 404 if no matching conversation exists yet. Carries the latest
    unanswered question (dock rebuild) and compact_summary metadata.
    """
    await get_project_for_user(db, project_id, UUID(str(current_user.id)))
    conversation = await find_conversation(
        db,
        UUID(str(current_user.id)),
        project_id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    response = ConversationResponse.model_validate(conversation)
    compact = (conversation.context or {}).get("compact_summary")
    response.compact_summary = compact if isinstance(compact, dict) else None
    # Large model-facing history is opt-in; it is never accepted as input.
    if not include_context:
        response.context = None
    pending = await latest_pending_question(db, UUID(str(conversation.id)))
    if pending is not None:
        response.pending_question = ChatMessageResponse.model_validate(pending)
    active_summary = run_bus.active_run_summary(UUID(str(conversation.id)))
    if active_summary is not None:
        response.active_run = ActiveRunSummary.model_validate(active_summary)
    latest_seq = await db.scalar(
        select(func.max(Message.seq)).where(Message.conversation_id == conversation.id)
    )
    response.latest_seq = latest_seq
    return response


def _sse(event: str, data: str) -> str:
    """One SSE frame (same wire format as the run-events stream)."""
    return f"event: {event}\ndata: {data}\n\n"


_HEARTBEAT_SECONDS = 15


def _make_delta_hook(queue: asyncio.Queue, persist=None):
    """The prose channel → ``assistant.delta`` frames, verbatim.

    Chat's optional persister returns the server-owned trailing partial row id;
    the answer stream keeps the same text channel without a Stop frontier.
    """
    async def on_delta(fragment: str) -> None:
        message_id = await persist(fragment) if persist is not None else None
        payload = {"text": fragment}
        if message_id is not None:
            payload["message_id"] = message_id
        await queue.put(_sse("assistant.delta", json.dumps(payload)))

    return make_tool_echo_delta_filter(on_delta)


def _make_tool_call_hook(queue: asyncio.Queue, projector: ActivityProjector | None = None):
    """Stream activity immediately. A blocking question is delivered after its row commits."""
    async def on_tool_call(name: str) -> None:
        if projector is not None:
            for frame in projector.name_known(name):
                await queue.put(_activity_frame(frame))
        await queue.put(
            _sse("assistant.thinking", json.dumps({"phase": None}))
        )

    return on_tool_call


def _new_activity_projector() -> ActivityProjector:
    from app.chat.intent import intent_router

    from app.chat.conversation_context import conversation_context_tool

    return ActivityProjector([*intent_router.tools, conversation_context_tool()])


def _activity_frame(frame) -> str:
    """One serialized ``assistant.activity`` frame (ADR-087 §3 Phase 2):
    additive alongside the phase frames; ``_sse_pump`` passes it through
    untouched."""
    return _sse("assistant.activity", json.dumps(frame.to_dict(), ensure_ascii=False))


def _row_frame(kind: str, payload: dict) -> str:
    """One ``assistant.row.append`` / ``assistant.row.update`` frame
    (ADR-108 §3): the SSE wire mirrors the transcript array's operations —
    append fixes a row's position, update mutates it in place. The client's
    live reducer and its history replay eat the SAME semantics."""
    return _sse(f"assistant.row.{kind}", json.dumps(payload, ensure_ascii=False))


def _row_payload(message: Message) -> dict:
    """The row wire shape mirrors ChatMessageResponse (数组行 = 消息行)."""
    validated = ChatMessageResponse.model_validate(message)
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "role": message.role,
        "content": message.content or "",
        "turn_id": str(message.turn_id) if message.turn_id else None,
        "run_id": validated.run_id,
        "display_role": validated.display_role,
        "seq": message.seq,
        "intent": validated.intent,
        "question": validated.question,
        "answer": validated.answer,
        "blocks": message.blocks or [],
        "steps": validated.steps,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


_INTERNAL_TOOL_ERROR_RE = re.compile(
    r"Invalid\s+\w+\s+props|Check\s+get_\w+|Field\s+required|Extra\s+inputs\s+are\s+not\s+permitted|"
    r"Input\s+should\s+be|String\s+should\s+have|ValidationError|Include\s+the\s+complete\s+transition|"
    r"Unknown\s+block_id|candidate_id|content_digest|base_version_id",
    re.I,
)


def _is_internal_tool_error(message: str | None) -> bool:
    if not message:
        return False
    return bool(_INTERNAL_TOOL_ERROR_RE.search(message))


def _make_activity_persister(
    queue: asyncio.Queue,
    projector: ActivityProjector,
    conversation_id: UUID,
    turn_id: UUID | None = None,
    owner_db=None,
    run_id: str | None = None,
):
    """每帧一行 + SSE 镜像 (ADR-108 §2/§3/§5)。"""
    open_rows: dict[str, tuple[UUID, dict]] = {}

    async def _append(frame: dict) -> None:
        try:
            from app.models.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                row = await append_activity_row(
                    db, conversation_id, frame, turn_id=turn_id, run_id=run_id
                )
                await db.commit()
            if frame["status"] == STATUS_ACTIVE:
                open_rows[frame["activity_id"]] = (row.id, frame)
            if queue is not None:
                await queue.put(_row_frame("append", {"row": _row_payload(row)}))
        except TurnStopped:
            raise
        except Exception as e:  # noqa: BLE001 — additive history is best-effort
            logger.warning(
                "activity_row_append_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )

    async def append_open_read(event=None):
        if isinstance(event, BatchDeclared):
            from sqlalchemy import func
            from app.chat.editor_recovery import editor_lock_key
            from app.models.database import AsyncSessionLocal

            if turn_id and owner_db is not None:
                await owner_db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn_id))))
            declared = []
            async with AsyncSessionLocal() as db:
                for member in event.members:
                    frame = {
                        "activity_id": member.call_id, "kind": KIND_READ, "status": STATUS_ACTIVE,
                        "key": member.key, "at": datetime.now(UTC).isoformat(), "group_id": member.group_id,
                        "call_id": member.call_id, "tool_name": member.tool_name, "call_index": member.call_index,
                        "call_count": member.call_count, "call_state": "queued",
                    }
                    row = await append_activity_row(
                        db, conversation_id, frame, turn_id=turn_id, run_id=run_id
                    )
                    declared.append((row, frame))
                await db.commit()
            for row, frame in declared:
                open_rows[frame["activity_id"]] = (row.id, frame)
                if queue is not None:
                    await queue.put(_row_frame("append", {"row": _row_payload(row)}))
            return
        if isinstance(event, BatchMember):
            if event.call_id in open_rows:
                row_id, frame = open_rows[event.call_id]
                merged = {**frame, "call_state": event.state, "key": event.key}
                if event.params is not None:
                    detail = project_tool_detail(event.tool_name, event.params)
                    if detail is not None:
                        merged["detail"] = detail
                if event.user_error and not _is_internal_tool_error(event.user_error):
                    merged["error"] = event.user_error[:500]
                if event.state == "running":
                    merged["started_at"] = datetime.now(UTC).isoformat()
                    open_rows[event.call_id] = (row_id, merged)
                else:
                    open_rows.pop(event.call_id)
                    merged["status"] = {"completed": "completed", "failed": "failed", "provider_unknown": "failed"}.get(event.state, "cancelled")
                    merged["settled_at"] = datetime.now(UTC).isoformat()
                    if event.duration_ms is not None:
                        merged["duration_ms"] = event.duration_ms
                await update_row(row_id, merged)
            return
        desc = projector.open_activity()
        if event and event.group_id and event.call_id in open_rows:
            # A batch also includes tools without a standalone Activity presentation.
            key = desc[2] if desc else open_rows[event.call_id][1]["key"]
            desc = (event.call_id, KIND_READ, key)
        if desc is None:
            return None
        activity_id, kind, key = desc
        detail = projector.open_activity_detail(activity_id)
        if detail is None and event is not None:
            detail = project_tool_detail(event.tool_name, getattr(event, "params", None))
        if activity_id in open_rows and event and event.group_id:
            row_id, frame = open_rows[activity_id]
            merged = {
                **frame,
                "call_state": "running",
                "key": key,
                "started_at": datetime.now(UTC).isoformat(),
                **({"detail": detail} if detail is not None else {}),
            }
            open_rows[activity_id] = (row_id, merged)
            await update_row(row_id, merged)
            return
        if kind != KIND_READ or activity_id in open_rows:
            return None
        await _append(
            {
                "activity_id": activity_id,
                **({"call_id": event.call_id, "tool_name": event.tool_name} if event else {}),
                "kind": kind,
                "status": STATUS_ACTIVE,
                "key": key,
                "at": datetime.now(UTC).isoformat(),
                **({"detail": detail} if detail is not None else {}),
            }
        )

    async def update_row(row_id, frame):
        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await settle_activity_row(db, row_id, frame)
            await db.commit()
        if queue is not None:
            await queue.put(_row_frame("update", {"id": str(row_id), "frame": frame}))

    async def mirror(frame) -> None:
        """Persist-side mirror of one emitted activity frame — the mapping
        lives in ``frame_persistence`` (activity.py, 一法一座)."""
        action = frame_persistence(frame)
        if action == "append":
            await _append(frame.to_dict())  # born-terminal
            return
        updating = frame.status == STATUS_ACTIVE and frame.activity_id in open_rows
        if updating and open_rows[frame.activity_id][1].get("key") == frame.key:
            return
        if not updating and action != "settle":
            return
        entry = open_rows.get(frame.activity_id) if updating else open_rows.pop(frame.activity_id, None)
        if entry is None:
            return  # rejected before execute entry — never appended
        row_id, open_d = entry
        merged = {
            **open_d,
            "status": frame.status,
            "key": frame.key,
            **({} if updating else {"settled_at": frame.at}),
            **({"call_state": frame.status} if open_d.get("group_id") and not updating else {}),
        }
        if frame.duration_ms is not None:
            merged["duration_ms"] = frame.duration_ms
        if frame.detail is not None:
            merged["detail"] = frame.detail
        if frame.receipt is not None and frame.receipt.kind != "skill_read":
            merged["receipt"] = frame.receipt.model_dump(mode="json")
        try:
            await update_row(row_id, merged)
            if updating:
                open_rows[frame.activity_id] = (row_id, merged)
        except TurnStopped:
            raise
        except Exception as e:  # noqa: BLE001 — additive history is best-effort
            logger.warning(
                "activity_row_settle_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )

    async def cancel_open() -> None:
        """Client-disconnect path (BaseException — the sweep never runs):
        settle every appended-but-open row CANCELLED, so the durable
        transcript never claims a read is still in flight forever."""
        for row_id, open_d in list(open_rows.values()):
            merged = {**open_d, "status": "cancelled", "cancelled_at": datetime.now(UTC).isoformat()}
            if open_d.get("group_id"):
                merged["call_state"] = "not_executed" if open_d.get("call_state") == "queued" else "cancelled"
            try:
                await update_row(row_id, merged)
            except TurnStopped:
                continue
            except Exception as e:  # noqa: BLE001 — best-effort on teardown
                logger.warning("activity_row_cancel_failed", error=str(e))
        open_rows.clear()

    return append_open_read, mirror, cancel_open


def _make_loop_event_hook(queue: asyncio.Queue, projector: ActivityProjector, append_open_read, mirror):
    """The typed loop-event channel's SSE seat (U1): internal events in,
    user-safe activity frames out — the translation lives entirely in the
    projector. ReadExecuting additionally seats the row append (ADR-108)."""
    async def on_loop_event(event) -> None:
        if isinstance(event, (BatchDeclared, BatchMember)):
            await append_open_read(event)
            return
        frames = projector.feed_event(event)
        if isinstance(event, ReadExecuting):
            await append_open_read(event)
        for frame in frames:
            if queue is not None:
                await queue.put(_activity_frame(frame))
            await mirror(frame)

    return on_loop_event


def persistent_activity_hooks(db, conversation_id, turn_id):
    """No SSE subscriber: project JSON and Worker decisions into the same history."""
    projector = _new_activity_projector()
    append, mirror, cancel = _make_activity_persister(None, projector, conversation_id, turn_id, owner_db=db)

    async def on_tool_call(name):
        for frame in projector.name_known(name):
            await mirror(frame)

    return {"on_tool_call": on_tool_call,
            "on_loop_event": _make_loop_event_hook(None, projector, append, mirror)}, cancel


def _make_activity_hook(queue: asyncio.Queue, projector: ActivityProjector, mirror):
    """The work-session milestone channel's SSE seat (iter-2 ⑥, N-57): the
    plan turn fires ``explore_milestone`` at the exploration door's
    successes; the frame is born-completed and rides the same
    ``assistant.activity`` channel as the loop-event frames — and persists
    as its own array row (ADR-108 §2)."""
    async def on_activity(key: str, count: int) -> None:
        frame = projector.explore_milestone(key, count=count)
        await queue.put(_activity_frame(frame))
        await mirror(frame)

    return on_activity


def _make_candidates_hook(
    queue: asyncio.Queue,
    sink: list[dict],
    turn_id: UUID | None = None,
):
    """The Candidate Surface channel's SSE seat (Workspace 合同 v4.2 C8-c,
    2026-09-26): the exploration doors' payloads (a candidate set's members,
    a selection's repaint) stream as ``assistant.candidates`` frames the
    moment the door succeeds — the milestone channel's count-only whitelist
    never carries them. Every emitted payload ALSO lands in ``sink``; the
    completed path persists the sink as ONE candidates_log message row (the
    activity-row precedent), so the surface survives a refresh — 消息载数据链,
    no endpoint."""
    async def on_candidates(payload: dict) -> None:
        sink.append(payload)
        wire = {
            **payload,
            "turn_id": str(turn_id) if turn_id is not None else None,
        }
        await queue.put(
            _sse("assistant.candidates", json.dumps(wire, ensure_ascii=False))
        )

    return on_candidates


def _interim_prose_frame(
    text: str,
    at: str | None,
    message_id: str,
    seq: int | None,
    turn_id: UUID | None,
    run_id: str | None = None,
    display_role: str = "stage_note",
) -> str:
    """Interim prose carries its persisted row identity, Turn identity, Run identity, and display role."""
    return _sse(
        "assistant.interim_prose",
        json.dumps(
            {
                "text": text,
                "at": at,
                "message_id": message_id,
                "seq": seq,
                "turn_id": str(turn_id) if turn_id is not None else None,
                "run_id": run_id,
                "display_role": display_role,
            }
        ),
    )


async def _sweep_activities(queue: asyncio.Queue, projector: ActivityProjector, outcome: str, mirror=None) -> None:
    """The terminal sweep (T16-B, 终帧律的活动同形): before the envelope,
    every still-active activity is settled — no activity outlives its turn.
    Sweep frames persist through the same mirror (ADR-108 §5: a failed
    turn's rows settle failed, never vanish). mirror=None = a prepare-stage
    failure that never wired the persister (nothing was appended)."""
    for frame in projector.sweep(outcome):
        await queue.put(_activity_frame(frame))
        if mirror is not None:
            await mirror(frame)


async def _persist_activity_forensics(
    conversation_id: UUID, ref: str, projector: ActivityProjector
) -> None:
    """The turn's rejection forensic ledger (rejection 取证批): ONE
    never-rendered row, on BOTH turn outcomes (ADR-108 §5 — a failed turn's
    rejected attempts stay auditable too). Own session (the turn's session
    already closed), best-effort: a log failure degrades to a warning,
    never a failed turn."""
    rejections = projector.rejected_calls()
    if not rejections:
        return
    try:
        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await record_activity_forensics(
                db, conversation_id, ref=ref, rejections=rejections
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — additive history is best-effort
        logger.warning(
            "activity_forensics_persist_failed",
            conversation_id=str(conversation_id),
            error=str(e),
        )


async def _persist_candidates_log(
    conversation_id: UUID,
    ref: str,
    events: list[dict],
    turn_id: UUID | None = None,
) -> None:
    """Candidate surface 持久化 (v4.2 C8-c): the turn's emitted
    ``assistant.candidates`` payloads land as ONE candidates_log message row
    — same doctrine as activity-row persistence (completed path only, own
    session, best-effort), so a refresh replays the candidate card and its
    selection highlight instead of silently dropping them."""
    if not events:
        return
    try:
        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await record_candidates_log(
                db, conversation_id, events, ref=ref, turn_id=turn_id
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — additive history is best-effort
        logger.warning(
            "candidates_log_persist_failed",
            conversation_id=str(conversation_id),
            error=str(e),
        )


def _failure_detail(
    exc: Exception,
    ui_language: str,
    *,
    decision_committed: bool = False,
) -> str | dict:
    """Map an exception into a user-safe localized line or typed structured payload."""
    if isinstance(exc, HTTPException):
        return exc.detail if isinstance(exc.detail, dict) else str(exc.detail)
    if isinstance(exc, LLMError):
        return user_error_line(exc, ui_language)
    if getattr(exc, "user_key", None):
        return user_error_line(exc, ui_language)
    zh = (ui_language or "en").lower().startswith("zh")
    if decision_committed:
        return (
            "执行后续创作时遇到系统异常，你的确认选项与已采集素材已安全保留，点击重试即可继续。"
            if zh
            else "Something went wrong while continuing creation. Your selections and gathered materials are safely preserved — click Retry to resume."
        )
    return (
        "处理这一步时遇到系统异常，已完成的进度已保留，点击重试即可继续。"
        if zh
        else "Something went wrong during this step. Completed progress has been preserved — click Retry to continue."
    )


def _build_failure_checkpoint(
    exc: Exception,
    detail: str | dict,
    *,
    run_id: str | None = None,
    decision_committed: bool = False,
) -> dict | None:
    """Build durable metadata for a FailureCheckpointCard when the failure is prose-backed."""
    if not isinstance(detail, str) or not detail.strip():
        return None
    if isinstance(exc, HTTPException) and 400 <= exc.status_code < 500:
        code = "request_rejected"
        retryable = False
    elif isinstance(exc, LLMError):
        code = "model_unavailable"
        retryable = True
    else:
        code = "execution_error"
        retryable = True
    return {
        "code": code,
        "run_id": run_id,
        "retryable": retryable,
        "decision_committed": decision_committed,
        "user_message": detail,
    }


class _DetachableQueue:
    """SSE frame queue that drops writes cleanly once the HTTP client disconnects,
    while mirroring all live frames onto RunEventBus for re-attaching tabs."""

    def __init__(self, completed_event: str = "turn.completed", failed_event: str = "turn.failed") -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._detached = False
        self._bus_conversation_id: UUID | None = None
        self._bus_run_id: str | None = None
        self._bus_finished = False
        self._completed_event = completed_event
        self._failed_event = failed_event

    def bind_bus(self, conversation_id: UUID, run_id: str, turn_id: UUID | None = None) -> None:
        self._bus_conversation_id = conversation_id
        self._bus_run_id = run_id
        self._bus_finished = False
        run_bus.start_run(conversation_id, run_id=run_id, turn_id=turn_id)

    def bind_turn(self, turn_id: UUID | None) -> None:
        if self._bus_conversation_id is not None and self._bus_run_id is not None:
            run_bus.bind_turn(self._bus_conversation_id, self._bus_run_id, turn_id)

    def finish_bus(self, status: str, terminal_sse: str | None = None) -> None:
        if self._bus_finished:
            return
        if self._bus_conversation_id is not None and self._bus_run_id is not None:
            self._bus_finished = True
            run_bus.finish_run(
                self._bus_conversation_id,
                self._bus_run_id,
                status,
                terminal_sse=terminal_sse,
            )

    def _serialize_terminal(self, item: tuple) -> tuple[str, str | None]:
        kind = item[0]
        if kind == "stopped":
            return "cancelled", None
        if kind == "completed":
            return "completed", _sse(self._completed_event, json.dumps(item[1]))
        if len(item) == 2 and isinstance(item[1], dict):
            payload = dict(item[1])
        else:
            payload = {
                "detail": item[1],
                "turn_id": item[3] if len(item) > 3 else None,
            }
            if len(item) > 2 and item[2] is not None:
                payload["persisted"] = item[2]
            if len(item) > 4 and item[4] is not None:
                payload["message_id"] = item[4]
        return "failed", _sse(self._failed_event, json.dumps(payload))

    def signal_stopped(self) -> None:
        """Non-blocking terminal wakeup for _sse_pump when the turn task is cancelled via /stop."""
        self.finish_bus("cancelled")
        if not self._detached:
            try:
                self._queue.put_nowait(("stopped",))
            except asyncio.QueueFull:
                pass

    async def put(self, item) -> None:
        if self._bus_conversation_id is not None and self._bus_run_id is not None:
            if isinstance(item, str):
                run_bus.observe_frame(self._bus_conversation_id, self._bus_run_id, item)
            elif isinstance(item, tuple):
                status, frame = self._serialize_terminal(item)
                self.finish_bus(status, terminal_sse=frame)
        if self._detached:
            return
        await self._queue.put(item)

    async def get(self):
        return await self._queue.get()

    def detach(self) -> None:
        self._detached = True
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


# Strong references to active and detached turn tasks so Python's GC never
# drops a turn running after an SSE disconnect, while explicit /stop can still
# cancel the exact in-flight task immediately.
_ACTIVE_TURN_TASKS: dict[UUID, asyncio.Task] = {}
_DETACHED_TASKS: set[asyncio.Task] = set()


def _register_turn_task(turn_id: UUID | None, task: asyncio.Task | None) -> None:
    if turn_id is None or task is None:
        return
    _ACTIVE_TURN_TASKS[turn_id] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _ACTIVE_TURN_TASKS.get(turn_id) is done_task:
            _ACTIVE_TURN_TASKS.pop(turn_id, None)

    task.add_done_callback(_cleanup)


def _cancel_active_turn_task(turn_id: UUID) -> bool:
    task = _ACTIVE_TURN_TASKS.get(turn_id)
    if task is not None and not task.done():
        task.cancel()
        return True
    return False


def _retain_detached_task(task: asyncio.Task) -> None:
    _DETACHED_TASKS.add(task)

    def _on_done(done_task: asyncio.Task) -> None:
        _DETACHED_TASKS.discard(done_task)
        if done_task.cancelled():
            return
        exc = done_task.exception()
        if exc is not None:
            logger.warning("detached_turn_task_failed", error=str(exc))

    task.add_done_callback(_on_done)


async def _sse_pump(
    queue: _DetachableQueue | asyncio.Queue,
    task: asyncio.Task,
    completed_event: str,
    failed_event: str,
):
    """The ONE terminal-pump loop both turn streams share:
    frames (already-serialized ``str`` items) pass through, tuples terminate
    the stream with ``completed_event`` / ``failed_event``, a quiet client
    gets bare-{} thinking keepalives, and a client disconnect detaches the
    stream WITHOUT cancelling the running turn task so refreshes or tab closes
    let the agent finish and persist its result (only explicit /stop cancels).
    """
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield _sse("assistant.thinking", "{}")
                continue
            if isinstance(item, str):
                yield item
            elif item[0] == "stopped":
                if isinstance(queue, _DetachableQueue):
                    queue.finish_bus("cancelled")
                return
            elif item[0] == "completed":
                frame = _sse(completed_event, json.dumps(item[1]))
                if isinstance(queue, _DetachableQueue):
                    queue.finish_bus("completed", terminal_sse=frame)
                yield frame
                return
            else:
                if len(item) == 2 and isinstance(item[1], dict):
                    payload = dict(item[1])
                else:
                    payload = {
                        "detail": item[1],
                        "turn_id": item[3] if len(item) > 3 else None,
                    }
                    if len(item) > 2 and item[2] is not None:
                        payload["persisted"] = item[2]
                    if len(item) > 4 and item[4] is not None:
                        payload["message_id"] = item[4]
                frame = _sse(failed_event, json.dumps(payload))
                if isinstance(queue, _DetachableQueue):
                    queue.finish_bus("failed", terminal_sse=frame)
                yield frame
                return
    finally:
        if isinstance(queue, _DetachableQueue):
            queue.detach()
        if not task.done():
            _retain_detached_task(task)


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
    commit, the main Turn transaction rolls back; the durable opening user
    row and independently committed transcript facts survive. An explicit
    Stop then settles cancelled/retracted, while an accidental disconnect
    follows the existing failed/recovery path. (No
    ``request.is_disconnected()`` polling: the middleware's receive-channel
    bookkeeping breaks it.)
    """
    queue = _DetachableQueue("turn.completed", "turn.failed")
    projector = _new_activity_projector()
    candidate_events: list[dict] = []
    run_id = str(uuid4())

    async def run_turn() -> None:
        from app.models.database import AsyncSessionLocal

        prepared = None
        turn_user_message_id = None
        turn_conversation_id = None
        # Persister closures are wired after prepare (the conversation id is
        # known only then); the failure paths tolerate None (a prepare-stage
        # rejection has nothing appended yet).
        mirror = None
        cancel_open = None
        try:
            async with AsyncSessionLocal() as db:
                prepared = await prepare_chat_turn(db, user_id, data)
                # Capture pre-rollback (本地变量律 — the B2 fenced-tails
                # MissingGreenlet lesson): the failure stamp below reads this
                # after the turn's session has torn down.
                turn_user_message_id = prepared.user_message.id
                turn_conversation_id = prepared.conversation_id
                queue.bind_bus(UUID(str(turn_conversation_id)), run_id, turn_user_message_id)
                _register_turn_task(turn_user_message_id, asyncio.current_task())
                await queue.put(
                    _sse(
                        "turn.started",
                        json.dumps({"turn_id": str(turn_user_message_id), "run_id": run_id}),
                    )
                )

                async def _emit_title_update(updated: dict[str, str] | None) -> None:
                    if not updated or turn_conversation_id is None:
                        return
                    try:
                        await queue.put(
                            _sse(
                                "title.updated",
                                json.dumps(
                                    {
                                        "project_id": str(data.project_id),
                                        "conversation_id": str(turn_conversation_id),
                                        **updated,
                                    }
                                ),
                            )
                        )
                    except Exception:  # noqa: BLE001 — best-effort UI notification
                        pass

                async def _early_title_refine() -> None:
                    from app.chat.titles import maybe_refine_titles_after_turn

                    updated = await maybe_refine_titles_after_turn(
                        UUID(str(turn_conversation_id)),
                        data.project_id,
                    )
                    await _emit_title_update(updated)

                early_title_task = asyncio.create_task(_early_title_refine())
                append_open_read, mirror, cancel_open = _make_activity_persister(
                    queue,
                    projector,
                    UUID(str(turn_conversation_id)),
                    turn_user_message_id,
                    owner_db=db,
                    run_id=run_id,
                )
                partial_message_id = None

                async def persist_delta(fragment: str) -> str | None:
                    nonlocal partial_message_id
                    if fragment:
                        async with AsyncSessionLocal() as partial_db:
                            partial = await persist_partial_prose(
                                partial_db,
                                UUID(str(turn_conversation_id)),
                                turn_user_message_id,
                                fragment,
                                message_id=partial_message_id,
                            )
                            await partial_db.commit()
                        partial_message_id = partial.id
                    return str(partial_message_id) if partial_message_id else None

                on_delta = _make_delta_hook(queue, persist_delta)
                on_tool_call = _make_tool_call_hook(queue, projector)
                on_loop_event = _make_loop_event_hook(queue, projector, append_open_read, mirror)
                on_activity = _make_activity_hook(queue, projector, mirror)
                on_candidates = _make_candidates_hook(
                    queue, candidate_events, turn_user_message_id
                )


                async def on_reasoning(_fragment: str) -> None:
                    # Reasoning-content frames: liveness only, never shown.
                    await queue.put(_sse("assistant.thinking", "{}"))

                async def on_phase(phase: str | None) -> None:
                    # A REAL System Status switch: a labelled thinking frame
                    # ({"phase": "storyboarding"}) — the dock's status row
                    # shows the phase copy instead of the static fallback;
                    # {"phase": null} (the film span's exit) resets it. The
                    # bare {} keepalive frames above never carry a phase and
                    # never touch the client's label. Work evidence rides the
                    # Activity channel, never this one (三通道分家, Phase 3
                    # Batch B).
                    await queue.put(
                        _sse("assistant.thinking", json.dumps({"phase": phase}))
                    )

                async def on_interim_prose(
                    text: str,
                    at: str,
                    message_id: str,
                    seq: int | None,
                    *,
                    display_role: str = "stage_note",
                ) -> None:
                    nonlocal partial_message_id
                    # The persisted interim row replaces the trailing partial;
                    # later deltas birth a fresh partial with its own server id.
                    partial_message_id = None
                    await queue.put(
                        _interim_prose_frame(
                            text,
                            at,
                            message_id,
                            seq,
                            turn_user_message_id,
                            run_id=run_id,
                            display_role=display_role,
                        )
                    )

                async def on_row_append(message: Message) -> None:
                    await queue.put(
                        _row_frame("append", {"row": _row_payload(message)})
                    )

                response = await execute_chat_turn(
                    db, prepared, data, on_delta=on_delta, on_reasoning=on_reasoning,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                    run_id=run_id,
                )
            await _sweep_activities(queue, projector, "completed", mirror)
            if turn_conversation_id is not None and turn_user_message_id is not None:
                await _persist_activity_forensics(
                    turn_conversation_id, str(turn_user_message_id), projector
                )
                await _persist_candidates_log(
                    turn_conversation_id,
                    str(turn_user_message_id),
                    candidate_events,
                    turn_user_message_id,
                )
                if not early_title_task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(early_title_task), timeout=1.5)
                    except Exception:  # noqa: BLE001
                        early_title_task.cancel()
                from app.chat.titles import maybe_refine_titles_after_turn

                try:
                    refined = await maybe_refine_titles_after_turn(
                        turn_conversation_id,
                        data.project_id,
                    )
                    await _emit_title_update(refined)
                except Exception:  # noqa: BLE001 — cosmetic title update must never fail a completed turn
                    logger.warning("title_refine_after_turn_failed", exc_info=True)
            await queue.put(("completed", response.model_dump(mode="json")))
        except TurnStopped:
            # The Stop control response is the only outcome. No failure line,
            # terminal envelope or second durable-reply decision follows it.
            if cancel_open is not None:
                await cancel_open()
            await queue.put(("stopped",))
        except Exception as exc:  # noqa: BLE001 — terminal frame, not a crash
            # Server-side truth seat: the full stack + turn identifiers land
            # in the log BEFORE anything else (a failed turn must never again
            # be a stack-less "Internal server error" — the 14fa16b6 evidence
            # hole). Identifiers only: no prompt text, no payload bodies.
            logger.exception(
                "chat_turn_failed",
                conversation_id=(
                    str(turn_conversation_id) if turn_conversation_id else None
                ),
                user_message_id=(
                    str(turn_user_message_id) if turn_user_message_id else None
                ),
                project_id=str(data.project_id),
                user_id=str(user_id),
            )
            # Turn durability (交互完整性批 A): the user row committed in
            # prepare SURVIVES this failure — stamp it 'failed' (best-effort,
            # fresh session inside) and tell the client it persisted, so the
            # flow keeps the bubble instead of rolling the user's own words
            # back. A prepare-stage rejection (entry caps) never persisted —
            # persisted=False keeps the old rollback for those.
            detail = _failure_detail(exc, ui_language)
            interrupted_state, partial_failure = None, None
            failed_steps = None
            if turn_user_message_id is not None and turn_conversation_id is not None:
                interrupted_state, partial_failure = await settle_failed_chat_turn(
                    turn_user_message_id, turn_conversation_id,
                    detail if isinstance(detail, str) else None,
                )
                if partial_failure is not None and isinstance(detail, str):
                    detail = partial_failure.content
                await stamp_turn_failed(turn_user_message_id)
                failed_steps = await mark_turn_steps_failed(turn_user_message_id)
            checkpoint = _build_failure_checkpoint(exc, detail, run_id=run_id, decision_committed=False)
            failed_row = partial_failure
            if (
                partial_failure is None and isinstance(detail, str)
                and turn_conversation_id is not None
                and interrupted_state not in {"cancelled", "retracted"}
            ):
                failed_row = await persist_turn_failed_line(
                    turn_conversation_id,
                    detail,
                    turn_user_message_id,
                    run_id=run_id,
                    checkpoint=checkpoint,
                )
            await _sweep_activities(queue, projector, "failed", mirror)
            if cancel_open is not None:
                await cancel_open()
            if failed_steps:
                await queue.put(_sse("assistant.activity", json.dumps({"kind": "steps", "steps": failed_steps}, ensure_ascii=False)))
            if turn_conversation_id is not None and turn_user_message_id is not None:
                await _persist_activity_forensics(
                    turn_conversation_id, str(turn_user_message_id), projector
                )
            failed_payload: dict = {
                "detail": detail,
                "persisted": turn_user_message_id is not None,
                "turn_id": str(turn_user_message_id) if turn_user_message_id else None,
                "run_id": run_id,
            }
            if failed_row is not None and isinstance(detail, str):
                failed_payload["message_id"] = str(failed_row.id)
            if checkpoint is not None:
                failed_payload["checkpoint"] = checkpoint
            await queue.put(("failed", failed_payload))
        except BaseException:
            # Cancel (the client disconnected mid-turn or explicit /stop):
            # wake _sse_pump immediately and finish bus, then settle open rows.
            queue.signal_stopped()
            if cancel_open is not None:
                await cancel_open()
            if turn_user_message_id is not None and turn_conversation_id is not None:
                await settle_interrupted_turn(
                    turn_user_message_id,
                    turn_conversation_id,
                )
            if turn_user_message_id is not None:
                await stamp_turn_failed(turn_user_message_id)
            raise

    task = asyncio.create_task(run_turn())
    async for frame in _sse_pump(queue, task, "turn.completed", "turn.failed"):
        yield frame


async def _answer_stream(
    user_id: UUID, message_id: UUID, data: AnswerRequest, ui_language: str
):
    """SSE generator for one answer turn with Two-Phase Decision Commit."""
    queue = _DetachableQueue("answer.completed", "answer.failed")
    projector = _new_activity_projector()
    candidate_events: list[dict] = []
    run_id = str(uuid4())

    async def run_answer() -> None:
        from app.models.database import AsyncSessionLocal

        mirror = None
        cancel_open = None
        conversation_id = None  # bound inside the try; the failure seat guards
        answer_turn_id = None
        decision_committed = False
        try:
            async with AsyncSessionLocal() as db:
                # The answer continuation inherits the question's persisted
                # opening-turn association; it never invents a user row.
                conversation_id, answer_turn_id, answer_project_id = (
                    await db.execute(
                        select(Message.conversation_id, Message.turn_id, Conversation.project_id)
                        .join(Conversation, Conversation.id == Message.conversation_id)
                        .where(Message.id == message_id)
                    )
                ).one()
                queue.bind_bus(UUID(str(conversation_id)), run_id, answer_turn_id)
                _register_turn_task(answer_turn_id, asyncio.current_task())
                append_open_read, mirror, cancel_open = _make_activity_persister(
                    queue,
                    projector,
                    UUID(str(conversation_id)),
                    answer_turn_id,
                    owner_db=db,
                    run_id=run_id,
                )
                on_delta = _make_delta_hook(queue)
                on_tool_call = _make_tool_call_hook(queue, projector)
                on_loop_event = _make_loop_event_hook(queue, projector, append_open_read, mirror)
                on_activity = _make_activity_hook(queue, projector, mirror)
                on_candidates = _make_candidates_hook(
                    queue, candidate_events, answer_turn_id
                )

                async def on_phase(phase: str | None) -> None:
                    await queue.put(
                        _sse("assistant.thinking", json.dumps({"phase": phase}))
                    )

                async def on_interim_prose(
                    text: str,
                    at: str,
                    message_id: str,
                    seq: int | None,
                    *,
                    display_role: str = "stage_note",
                ) -> None:
                    await queue.put(
                        _interim_prose_frame(
                            text,
                            at,
                            message_id,
                            seq,
                            answer_turn_id,
                            run_id=run_id,
                            display_role=display_role,
                        )
                    )

                async def on_row_append(message: Message) -> None:
                    await queue.put(
                        _row_frame("append", {"row": _row_payload(message)})
                    )

                async def on_decision_committed(answered_msg: Message, rid: str | None) -> None:
                    nonlocal decision_committed
                    decision_committed = True
                    await queue.put(
                        _sse(
                            "decision.committed",
                            json.dumps(
                                {
                                    "run_id": rid or run_id,
                                    "turn_id": str(answer_turn_id) if answer_turn_id else None,
                                    "answered_question": ChatMessageResponse.model_validate(
                                        answered_msg
                                    ).model_dump(mode="json"),
                                }
                            ),
                        )
                    )

                message, follow_up = await answer_question(
                    db,
                    user_id,
                    message_id,
                    data,
                    on_delta=on_delta,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                    on_decision_committed=on_decision_committed,
                    run_id=run_id,
                )
            await _sweep_activities(queue, projector, "completed", mirror)
            await _persist_activity_forensics(
                UUID(str(conversation_id)), str(message_id), projector
            )
            await _persist_candidates_log(
                message.conversation_id,
                str(message.id),
                candidate_events,
                answer_turn_id,
            )
            from app.chat.titles import maybe_refine_titles_after_turn

            try:
                refined_after_answer = await maybe_refine_titles_after_turn(
                    UUID(str(conversation_id)),
                    answer_project_id,
                )
                if refined_after_answer and answer_project_id is not None:
                    await queue.put(
                        _sse(
                            "title.updated",
                            json.dumps(
                                {
                                    "project_id": str(answer_project_id),
                                    "conversation_id": str(conversation_id),
                                    **refined_after_answer,
                                }
                            ),
                        )
                    )
            except Exception:  # noqa: BLE001 — cosmetic title update must never fail a completed turn
                logger.warning("title_refine_after_answer_failed", exc_info=True)
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
            logger.exception(
                "answer_turn_failed",
                conversation_id=str(conversation_id) if conversation_id else None,
                message_id=str(message_id),
                user_id=str(user_id),
                decision_committed=decision_committed,
            )
            detail = _failure_detail(exc, ui_language, decision_committed=decision_committed)
            failed_steps = (
                await mark_turn_steps_failed(answer_turn_id)
                if answer_turn_id is not None
                else None
            )
            checkpoint = _build_failure_checkpoint(
                exc, detail, run_id=run_id, decision_committed=decision_committed
            )
            failed_row = None
            if isinstance(detail, str) and conversation_id is not None:
                failed_row = await persist_turn_failed_line(
                    UUID(str(conversation_id)),
                    detail,
                    answer_turn_id,
                    run_id=run_id,
                    checkpoint=checkpoint,
                )
            await _sweep_activities(queue, projector, "failed", mirror)
            if cancel_open is not None:
                await cancel_open()
            if failed_steps:
                await queue.put(
                    _sse(
                        "assistant.activity",
                        json.dumps({"kind": "steps", "steps": failed_steps}, ensure_ascii=False),
                    )
                )
            failed_payload: dict = {
                "detail": detail,
                "turn_id": str(answer_turn_id) if answer_turn_id else None,
                "run_id": run_id,
                "decision_committed": decision_committed,
                "persisted": decision_committed or failed_row is not None,
            }
            if failed_row is not None:
                failed_payload["message_id"] = str(failed_row.id)
            if checkpoint is not None:
                failed_payload["checkpoint"] = checkpoint
            await queue.put(("failed", failed_payload))
        except BaseException:
            queue.signal_stopped()
            if cancel_open is not None:
                await cancel_open()
            raise

    task = asyncio.create_task(run_answer())
    async for frame in _sse_pump(queue, task, "answer.completed", "answer.failed"):
        yield frame


async def _resume_stream(
    user_id: UUID, conversation_id: UUID, ui_language: str
):
    """SSE generator that resumes a conversation from its latest failed checkpoint
    without re-creating a user message or re-asking an already-answered question."""
    from app.chat.service import _lock_turn_for_final_commit, _lock_turn_for_transcript_write, _plan_turn
    from app.metering import bind_conversation_turn, fold_conversation_usage

    queue = _DetachableQueue("turn.completed", "turn.failed")
    projector = _new_activity_projector()
    candidate_events: list[dict] = []
    run_id = str(uuid4())

    async def run_resume() -> None:
        from app.models.database import AsyncSessionLocal

        mirror = None
        cancel_open = None
        turn_user_message_id: UUID | None = None
        try:
            async with AsyncSessionLocal() as db:
                conversation = await db.get(Conversation, conversation_id)
                if conversation is None or UUID(str(conversation.user_id)) != user_id:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
                project = await db.get(Project, conversation.project_id)
                if project is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
                recent = await list_conversation_messages(db, conversation_id)
                opening = next((m for m in reversed(recent) if m.role == "user"), None)
                if opening is None:
                    raise HTTPException(status.HTTP_409_CONFLICT, "No turn to resume")
                turn_user_message_id = opening.id
                queue.bind_bus(conversation_id, run_id, turn_user_message_id)
                _register_turn_task(turn_user_message_id, asyncio.current_task())
                await queue.put(
                    _sse(
                        "turn.started",
                        json.dumps({"turn_id": str(turn_user_message_id), "run_id": run_id}),
                    )
                )
                resumed_steps: list[dict] | None = None
                async with AsyncSessionLocal() as state_db:
                    locked = await _lock_turn_for_transcript_write(state_db, turn_user_message_id)
                    locked.turn_state = "in_flight"
                    # Reset any failed step back to in_progress on retry
                    locked_intent = dict(locked.intent or {})
                    if isinstance(locked_intent.get("steps"), list) and locked_intent["steps"]:
                        locked_intent["steps"] = [
                            {**s, "status": "in_progress"} if isinstance(s, dict) and s.get("status") == "failed" else s
                            for s in locked_intent["steps"]
                        ]
                        locked.intent = locked_intent
                        resumed_steps = locked_intent["steps"]
                    await state_db.commit()
                if resumed_steps:
                    await queue.put(
                        _sse(
                            "assistant.activity",
                            json.dumps({"kind": "steps", "steps": resumed_steps}, ensure_ascii=False),
                        )
                    )

                append_open_read, mirror, cancel_open = _make_activity_persister(
                    queue,
                    projector,
                    conversation_id,
                    turn_user_message_id,
                    owner_db=db,
                    run_id=run_id,
                )
                on_delta = _make_delta_hook(queue)
                on_tool_call = _make_tool_call_hook(queue, projector)
                on_loop_event = _make_loop_event_hook(queue, projector, append_open_read, mirror)
                on_activity = _make_activity_hook(queue, projector, mirror)
                on_candidates = _make_candidates_hook(queue, candidate_events, turn_user_message_id)

                async def on_reasoning(_fragment: str) -> None:
                    await queue.put(_sse("assistant.thinking", "{}"))

                async def on_phase(phase: str | None) -> None:
                    await queue.put(_sse("assistant.thinking", json.dumps({"phase": phase})))

                async def on_interim_prose(
                    text: str,
                    at: str,
                    mid: str,
                    seq: int | None,
                    *,
                    display_role: str = "stage_note",
                ) -> None:
                    await queue.put(
                        _interim_prose_frame(
                            text,
                            at,
                            mid,
                            seq,
                            turn_user_message_id,
                            run_id=run_id,
                            display_role=display_role,
                        )
                    )

                async def on_row_append(msg: Message) -> None:
                    await queue.put(_row_frame("append", {"row": _row_payload(msg)}))

                # Reconstruct the continuation prompt cleanly from opening + latest answered QA if any
                answered_q = next(
                    (m for m in reversed(recent) if m.turn_id == turn_user_message_id and m.question and m.answer),
                    None,
                )
                resume_text = opening.content or ""
                if answered_q is not None:
                    ans_text = (answered_q.answer or {}).get("text") or ""
                    q_title = (answered_q.question or {}).get("question") or ""
                    resume_text = (
                        f"{resume_text}\n\nQuestion: {q_title}\nUser answer: {ans_text}\n\n"
                        "(Previous attempt encountered an error; resume and complete the task from preserved materials and brief.)"
                    )
                if resumed_steps:
                    steps_json = json.dumps(resumed_steps, ensure_ascii=False)
                    resume_text = (
                        f"{resume_text}\n\n"
                        f"(Existing step progress: {steps_json}. Reuse these exact step titles, keep completed steps as 'done', and immediately advance the active step as you proceed.)"
                    )
                with bind_conversation_turn(
                    conversation_id=conversation_id,
                    turn_id=turn_user_message_id,
                    project_id=project.id,
                ) as usage:
                    assistant_message, _ = await _plan_turn(
                        db,
                        user_id,
                        conversation,
                        project,
                        ChatRequest(
                            project_id=project.id,
                            conversation_id=conversation_id,
                            message=resume_text,
                            mentions=opening.mentions or [],
                            attachments=opening.attachments or [],
                        ),
                        recent=recent,
                        turn_id=turn_user_message_id,
                        run_id=run_id,
                        group_answer_submitted=bool(answered_q and (answered_q.answer or {}).get("kind") == "group"),
                        on_delta=on_delta,
                        on_reasoning=on_reasoning,
                        on_phase=on_phase,
                        on_tool_call=on_tool_call,
                        on_interim_prose=on_interim_prose,
                        on_loop_event=on_loop_event,
                        on_activity=on_activity,
                        on_candidates=on_candidates,
                        on_row_append=on_row_append,
                    )
                await fold_conversation_usage(
                    db, user_id=user_id, project_id=project.id, accrued=usage.accrued
                )
                turn_row = await _lock_turn_for_final_commit(db, turn_user_message_id)
                turn_row.turn_state = "settled"
                conv_row = await db.get(Conversation, conversation_id)
                if conv_row is not None:
                    conv_row.updated_at = datetime.now(UTC)
                await db.commit()
                await db.refresh(turn_row)
                if assistant_message is not None:
                    await db.refresh(assistant_message)
            await _sweep_activities(queue, projector, "completed", mirror)
            await _persist_activity_forensics(conversation_id, str(turn_user_message_id), projector)
            await _persist_candidates_log(
                conversation_id, str(turn_user_message_id), candidate_events, turn_user_message_id
            )
            from app.models.schemas import ChatResponse

            await queue.put(
                (
                    "completed",
                    ChatResponse(
                        conversation_id=conversation_id,
                        user_message=ChatMessageResponse.model_validate(turn_row),
                        assistant_message=(
                            ChatMessageResponse.model_validate(assistant_message)
                            if assistant_message is not None
                            else None
                        ),
                    ).model_dump(mode="json"),
                )
            )
        except TurnStopped:
            if cancel_open is not None:
                await cancel_open()
            await queue.put(("stopped",))
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "resume_turn_failed",
                conversation_id=str(conversation_id),
                turn_id=str(turn_user_message_id) if turn_user_message_id else None,
                user_id=str(user_id),
            )
            detail = _failure_detail(exc, ui_language, decision_committed=True)
            failed_steps = (
                await mark_turn_steps_failed(turn_user_message_id)
                if turn_user_message_id is not None
                else None
            )
            if turn_user_message_id is not None:
                await stamp_turn_failed(turn_user_message_id)
            checkpoint = _build_failure_checkpoint(exc, detail, run_id=run_id, decision_committed=True)
            failed_row = (
                await persist_turn_failed_line(
                    conversation_id, detail, turn_user_message_id, run_id=run_id, checkpoint=checkpoint
                )
                if isinstance(detail, str)
                else None
            )
            await _sweep_activities(queue, projector, "failed", mirror)
            if cancel_open is not None:
                await cancel_open()
            if failed_steps:
                await queue.put(
                    _sse(
                        "assistant.activity",
                        json.dumps({"kind": "steps", "steps": failed_steps}, ensure_ascii=False),
                    )
                )
            failed_payload: dict = {
                "detail": detail,
                "persisted": True,
                "turn_id": str(turn_user_message_id) if turn_user_message_id else None,
                "run_id": run_id,
                "decision_committed": True,
            }
            if failed_row is not None:
                failed_payload["message_id"] = str(failed_row.id)
            if checkpoint is not None:
                failed_payload["checkpoint"] = checkpoint
            await queue.put(("failed", failed_payload))
        except BaseException:
            queue.signal_stopped()
            if cancel_open is not None:
                await cancel_open()
            raise

    task = asyncio.create_task(run_resume())
    async for frame in _sse_pump(queue, task, "turn.completed", "turn.failed"):
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
    # The generator owns a separate session. Release the preflight read
    # before a long-lived response can occupy a second pool connection.
    await db.close()
    return StreamingResponse(
        _turn_stream(
            UUID(str(current_user.id)), data, current_ui_language() or "en"
        ),
        media_type="text/event-stream",
        status_code=status.HTTP_200_OK,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@chat_router.post("/turns/{turn_id}/stop")
async def stop_chat_turn(
    turn_id: UUID,
    data: ChatTurnStopRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Settle Stop once, atomically, at the client-visible frontier."""
    message = await db.get(Message, turn_id)
    conversation = (
        await db.get(Conversation, message.conversation_id) if message else None
    )
    if (
        message is None
        or message.role != "user"
        or message.turn_id != turn_id
        or conversation is None
        or conversation.user_id != current_user.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turn not found")
    state = await stop_turn_at_visible_frontier(db, turn_id, data)
    _cancel_active_turn_task(turn_id)
    return {"accepted": True, "turn_state": state}


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
    from app.chat.editor_recovery import recover_interrupted_edits
    if await recover_interrupted_edits(db, id):
        await db.commit()
    messages = await list_conversation_messages(db, id)
    feedback_rows = list(
        await db.scalars(
            select(MessageFeedback).where(
                MessageFeedback.conversation_id == id,
                MessageFeedback.user_id == current_user.id,
            )
        )
    )
    feedback_by_msg = {
        fb.message_id: MessageFeedbackSummary(
            rating=fb.rating,
            reason=fb.reason,
            tags=list(fb.tags or []),
            updated_at=fb.updated_at,
        )
        for fb in feedback_rows
    }
    items = []
    for m in messages:
        item = ChatMessageResponse.model_validate(m)
        if m.id in feedback_by_msg:
            item.feedback = feedback_by_msg[m.id]
        items.append(item)
    compact = (conversation.context or {}).get("compact_summary")
    return MessageListResponse(
        items=items,
        compact_summary=compact if isinstance(compact, dict) else None,
    )


@chat_router.patch("/conversations/{conversation_id}", response_model=ProjectConversationSummary)
async def rename_chat_conversation(
    conversation_id: UUID,
    data: RenameConversationRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> ProjectConversationSummary:
    """Rename an owned project conversation."""
    from sqlalchemy import func

    conversation = await db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.user_id != current_user.id
        or conversation.project_id is None
        or conversation.asset_id is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    conversation.title = data.title
    conversation.title_user_edited = True
    conversation.context = {**(conversation.context or {}), "title_user_edited": True}
    conversation.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(conversation)
    msg_count = int(
        await db.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation.id,
                Message.role.in_(("user", "assistant")),
                visible_conversation_message_filter(),
            )
        )
        or 0
    )
    has_active_job = bool(
        await db.scalar(
            select(ExportJob.id)
            .join(Message, ExportJob.receipt_id == Message.id)
            .where(
                Message.conversation_id == conversation.id,
                ExportJob.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        or await db.scalar(
            select(MediaJob.id)
            .join(Message, MediaJob.receipt_id == Message.id)
            .where(
                Message.conversation_id == conversation.id,
                MediaJob.status.in_(("queued", "running")),
            )
            .limit(1)
        )
    )
    pending_q = await latest_pending_question(db, UUID(str(conversation.id)))
    has_pending_question = bool(
        pending_q
        and isinstance(pending_q.question, dict)
        and (pending_q.question.get("options") or pending_q.question.get("items"))
    )
    compact = (conversation.context or {}).get("compact_summary")
    return ProjectConversationSummary(
        id=conversation.id,
        project_id=conversation.project_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=msg_count,
        has_active_job=has_active_job,
        has_pending_question=has_pending_question,
        compacted=bool(isinstance(compact, dict) and compact.get("summary")),
        compacted_at=compact.get("compacted_at") if isinstance(compact, dict) else None,
    )


@chat_router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_conversation(
    conversation_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete an owned project conversation when it has no active or unsettled jobs."""
    from sqlalchemy import String, cast, delete, func
    from app.models.tables import CreditTransaction
    from app.platform.billing import settled_job_amounts
    from app.ui_locale import current_ui_language

    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
            Conversation.project_id.is_not(None),
            Conversation.asset_id.is_(None),
        )
        .with_for_update()
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    message_ids = list(
        await db.scalars(
            select(Message.id).where(Message.conversation_id == conversation.id)
        )
    )
    if message_ids:
        conflict = (
            "该对话仍有正在执行或待核对费用的任务，暂时无法删除。"
            if (current_ui_language() or "").startswith("zh")
            else "This conversation has active work or unsettled charges. Try again after settlement."
        )
        for model, ref_key in ((MediaJob, "media_job_id"), (ExportJob, "export_id")):
            jobs = (
                await db.execute(
                    select(model, Message.intent)
                    .join(Message, model.receipt_id == Message.id)
                    .where(model.receipt_id.in_(message_ids))
                )
            ).all()
            if not jobs:
                continue
            if any(job.status not in {"succeeded", "failed", "cancelled"} for job, _ in jobs):
                raise HTTPException(status.HTTP_409_CONFLICT, conflict)
            job_ids = [job.id for job, _ in jobs]
            reference = CreditTransaction.ref[ref_key].astext
            totals = (
                await db.execute(
                    select(reference, CreditTransaction.kind, func.sum(CreditTransaction.amount))
                    .join(model, cast(model.id, String) == reference)
                    .where(
                        model.id.in_(job_ids),
                        CreditTransaction.user_id == current_user.id,
                        CreditTransaction.kind.in_(("hold", "release", "capture")),
                    )
                    .group_by(reference, CreditTransaction.kind)
                )
            ).all()
            amounts = {(key, kind): amount for key, kind, amount in totals}
            for job, intent in jobs:
                result = (intent or {}).get("media_result") or {}
                expected = settled_job_amounts(job, result, export=model is ExportJob)
                if expected is None or any(
                    amounts.get((str(job.id), kind), 0) != value
                    for kind, value in expected.items()
                ):
                    raise HTTPException(status.HTTP_409_CONFLICT, conflict)

        await db.execute(delete(MediaJob).where(MediaJob.receipt_id.in_(message_ids)))
        await db.execute(delete(ExportJob).where(ExportJob.receipt_id.in_(message_ids)))

    await db.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await db.commit()


@chat_router.post(
    "/conversations/{conversation_id}/compact",
    response_model=CompactConversationResponse,
)
async def compact_chat_conversation(
    conversation_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> CompactConversationResponse:
    """Compact settled history of an owned conversation into context['compact_summary']."""
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    record = await compact_conversation_context(db, conversation)
    return CompactConversationResponse(
        conversation_id=conversation.id,
        summary=record["summary"],
        key_decisions=list(record.get("key_decisions") or []),
        compacted_through_seq=int(record["compacted_through_seq"]),
        compacted_at=record["compacted_at"],
        message_count=int(record["message_count"]),
    )


@chat_router.post(
    "/messages/{message_id}/feedback",
    response_model=MessageFeedbackResponse,
)
async def submit_message_feedback(
    message_id: UUID,
    data: MessageFeedbackRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> MessageFeedbackResponse:
    """Record or clear per-user good/bad evaluation feedback with a frozen turn snapshot."""
    row = await upsert_message_feedback(
        db,
        UUID(str(current_user.id)),
        message_id,
        rating=data.rating,
        reason=data.reason,
        tags=data.tags,
    )
    if row is None:
        return MessageFeedbackResponse(message_id=message_id, feedback=None)
    return MessageFeedbackResponse(
        message_id=message_id,
        feedback=MessageFeedbackSummary(
            rating=row.rating,
            reason=row.reason,
            tags=list(row.tags or []),
            updated_at=row.updated_at,
        ),
    )


@chat_router.get("/skills")
async def list_chat_skills(
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Selectable video Skills; creative bodies stay server-side."""
    from app.skills.resolution import list_available_skills

    options = await list_available_skills(db, owner_id=UUID(str(current_user.id)))
    return {"items": [option.model_dump(mode="json") for option in options]}


@chat_router.get("/references")
async def list_chat_references(
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """The existing mention picker gets a small owner-scoped global feed."""
    from app.models.tables import Asset, CompositionVersion, Output
    from app.pipeline.outputs import is_delivered_output, visible_outputs_stmt
    assets = (await db.scalars(select(Asset).where(Asset.user_id == current_user.id)
        .order_by(Asset.created_at.desc()).limit(100))).all()
    outputs = (await db.scalars(visible_outputs_stmt().join(Project, Output.project_id == Project.id)
        .where(Project.user_id == current_user.id)
        .order_by(Output.created_at.desc()).limit(100))).all()
    delivered = [output for output in outputs if is_delivered_output(output)]
    version_ids = list(dict.fromkeys(
        output.composition_version_id for output in delivered
        if output.composition_version_id is not None
    ))
    versions = list((
        await db.execute(select(CompositionVersion).where(CompositionVersion.id.in_(version_ids)))
    ).scalars().all()) if version_ids else []
    version_numbers = {version.id: version.version for version in versions}
    return {
        "assets": [{"id": str(a.id), "title": a.title or a.display_name or str(a.id),
                    "type": a.type.value} for a in assets],
        "outputs": [{"id": str(o.id), "type": o.type,
                     "name": (o.payload or {}).get("name") or output_one_liner(o) or o.type,
                     "composition_version_number": version_numbers.get(o.composition_version_id)}
                    for o in delivered],
    }


@chat_router.get("/video/versions/{version_id}/storyboard")
async def read_video_storyboard(
    version_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
    scrub: str | None = None,
) -> dict:
    """The canonical storyboard DTO behind a presenting message block.
    Tools use the complete facts; the visible reply is the LLM's grounded
    Markdown overview. Owner-scoped; an unknown/foreign version reads 404,
    never a leak."""
    from app.editing.service import video_version_read  # deferred: editing seam
    from app.editing.store import CompositionNotFound, PermissionDenied
    from app.models.schemas import VideoRangeScrubTarget, VideoScrubTarget
    from app.tools.video.preview import ScrubTargetError, enrich_video_scrub

    try:
        read = await video_version_read(
            db, owner_id=UUID(str(current_user.id)), version_id=version_id
        )
        if scrub is None:
            return read
        try:
            target = TypeAdapter(VideoScrubTarget | VideoRangeScrubTarget).validate_python(json.loads(scrub))
        except (ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(422, "Invalid Scrub target") from None
        return await enrich_video_scrub(
            db, read, owner_id=UUID(str(current_user.id)), target=target
        )
    except ScrubTargetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except (CompositionNotFound, PermissionDenied):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video version not found",
        ) from None


class VideoClipRevision(BaseModel):
    base_ref: dict
    track_id: str = Field(min_length=1, max_length=64)
    clip: dict
    request_id: str = Field(min_length=1, max_length=120)


@chat_router.put("/video/versions/{version_id}/clips/{clip_id}")
async def revise_video_clip(
    version_id: UUID,
    clip_id: str,
    data: VideoClipRevision,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Apply one complete Clip from the deterministic Scrub Input gesture."""
    from app.editing.edits import ClipEntityWrite
    from app.editing.schemas import Clip
    from app.editing.service import revise_video
    from app.editing.store import (
        CompositionNotFound,
        ContentDigestMismatch,
        PermissionDenied,
        StaleBase,
    )
    from app.models.schemas import ReviseVideoArgs, VideoVersionRef

    base_ref = VideoVersionRef.model_validate(data.base_ref)
    clip = Clip.model_validate(data.clip)
    if (
        base_ref.composition_version_id != version_id
        or clip.clip_id != clip_id
        or clip.object.kind != "text"
    ):
        raise HTTPException(422, "The Scrub target does not match this saved version")
    args = ReviseVideoArgs(
        base_ref=base_ref,
        clips=[ClipEntityWrite(track_id=data.track_id, clip=clip)],
    )
    try:
        return await revise_video(
            db,
            owner_id=UUID(str(current_user.id)),
            args=args,
            request_id=f"scrub:{data.request_id}",
        )
    except (StaleBase, ContentDigestMismatch):
        raise HTTPException(
            409, "This video changed elsewhere. Reopen the current version before applying."
        ) from None
    except (CompositionNotFound, PermissionDenied):
        raise HTTPException(404, "Video version not found") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class VideoPresentationComplete(BaseModel):
    composition_version_id: UUID
    presentation_digest: str


@chat_router.post("/messages/{message_id}/video-presentation")
async def complete_video_presentation(
    message_id: UUID,
    data: VideoPresentationComplete,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Client completed the creative overview; this is not user approval."""
    message = await db.get(Message, message_id)
    conversation = await db.get(Conversation, message.conversation_id) if message else None
    if conversation is None:
        raise HTTPException(404, "Presentation not found")
    project = await get_project_for_user(db, conversation.project_id, current_user.id)
    await db.refresh(project, with_for_update=True)
    await db.refresh(message, with_for_update=True)
    from app.editing.service import video_version_read
    from app.models.schemas import ProjectBrief
    stored = ProjectBrief.model_validate(project.pending_brief or {})
    receipt = stored.video_presentation or {}
    expected = str(data.composition_version_id)
    read = await video_version_read(db, owner_id=current_user.id,
                                    version_id=data.composition_version_id)
    block = next((b for b in message.blocks or []
                  if b.get("composition_version_id") == expected
                  and b.get("kind") == "video_storyboard"
                  and (b.get("scrub") or {}).get("kind") != "range"), None)
    if (not block or block.get("content_digest", read["content_digest"]) != read["content_digest"]
            or read["presentation_digest"] != data.presentation_digest):
        raise HTTPException(409, "Presentation does not match the saved version")
    # The block is a version reference, while its presentation receipt lives
    # outside the immutable version. A refresh ACKs the DTO actually shown
    # now and re-stamps that receipt; an old presentation hash still fails.
    message.blocks = [
        {**b, "content_digest": read["content_digest"],
         "presentation_digest": data.presentation_digest,
         "presentation_complete": True} if b is block else b
        for b in message.blocks
    ]
    # Completion belongs to the message even when another work is now active.
    if receipt.get("presented_message_id") != str(message_id):
        await db.commit()
        return {"accepted": False}
    if receipt.get("composition_version_id") != expected or receipt.get("content_digest", read["content_digest"]) != read["content_digest"]:
        raise HTTPException(409, "Presentation receipt is stale")
    receipt = {**receipt, "content_digest": read["content_digest"],
               "presentation_digest": data.presentation_digest,
               "presentation_complete": True}
    project.pending_brief = stored.model_copy(
        update={"video_presentation": receipt}
    ).model_dump(mode="json")
    await db.commit()
    return {"accepted": True}


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


@chat_router.post("/conversations/{conversation_id}/resume")
async def resume_conversation_run(
    conversation_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
):
    """Resume a conversation after a failure checkpoint without duplicating the user turn."""
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or UUID(str(conversation.user_id)) != UUID(str(current_user.id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    if run_bus.active_run(conversation_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A run is already active in this conversation")
    await db.close()
    return StreamingResponse(
        _resume_stream(
            UUID(str(current_user.id)), conversation_id, current_ui_language() or "en"
        ),
        media_type="text/event-stream",
        status_code=status.HTTP_200_OK,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@chat_router.get("/conversations/{conversation_id}/events")
async def stream_conversation_events(
    conversation_id: UUID,
    after_seq: int = 0,
    db: DBDep = None,
    current_user: User = Depends(get_current_user_required),
):
    """Re-attachable SSE stream: catches up persisted rows with seq > after_seq
    and subscribes to any in-flight RunEventBus stream for seamless tab-switch recovery."""
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or UUID(str(conversation.user_id)) != UUID(str(current_user.id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    missed_rows = list(
        (
            await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.seq > after_seq,
                    visible_conversation_message_filter(),
                )
                .order_by(Message.seq.asc())
            )
        ).scalars().all()
    )
    catchup_frames = [_row_frame("append", {"row": _row_payload(m)}) for m in missed_rows]
    await db.close()

    async def _gen():
        for frame in catchup_frames:
            yield frame
        async with run_bus.subscribe(conversation_id) as (state, sub_q):
            if state is None or sub_q is None:
                yield _sse("run.synced", json.dumps({"active": False}))
                return
            yield _sse(
                "run.synced",
                json.dumps(
                    {
                        "active": True,
                        "run_id": state.run_id,
                        "turn_id": str(state.turn_id) if state.turn_id else None,
                        "live_focus": state.live_focus,
                        "steps": state.steps,
                    },
                    ensure_ascii=False,
                ),
            )
            while True:
                try:
                    item = await asyncio.wait_for(sub_q.get(), timeout=_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield _sse("assistant.thinking", "{}")
                    continue
                if item is None:
                    return
                yield item

    return StreamingResponse(
        _gen(),
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
        # assistant_message is None only on the material-pending suppression
        # path — unreachable here (a regenerate turn carries no fresh
        # uploads), guarded for the Optional contract.
        "message_id": (
            str(result.assistant_message.id)
            if result.assistant_message is not None
            else None
        ),
        "conversation_id": str(result.conversation_id),
    }
