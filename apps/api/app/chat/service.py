"""Generic chat service.

A conversation is the universal container. It can be project-scoped (the
original prompt plus project-level follow-ups) or asset-scoped (a clip,
LinkedIn post, quote card, etc.).

The public surface is intentionally tiny: ``chat()`` takes a user message,
locates or creates the right conversation, assembles deterministic context,
and lets the intent agent propose (CHAT_ARCH §3, four-state: N-18 + N-21):

- task_list (non-empty) → compile_graph mode② → a new WorkflowRun
- ask                   → a typed question docked above the input; the old
                          "tasks=[] ask back" migrates to a freeform ask
- edit_ops              → Operation Model (ADR-032): registry-validated ops
                          applied to the target output, journaled with
                          message lineage
- answer                → a purely informational reply (capability /
                          progress / explanation / small talk) landing as a
                          plain assistant message — no run, no dock (G-4)

One LLM call per turn; the loop lives between turns, never inside one.

Ask primitive (intent-ask-primitive): a message may carry a typed
``question`` payload; ``answer`` NULL = pending. Pending questions dock above
the input (QuestionDock); answered ones archive in the flow as QA pairs. At
most one pending question per conversation — a newer question retires the
previous one (bail: superseded). While a choice question is pending, a
free-text message is mapped deterministically (autoResume, zero LLM): an
option letter/number/label hit answers with that option; otherwise
``allow_freeform`` records the text as a freeform answer; otherwise the text
is a new intent and the question stays pending.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minimax import MiniMaxError
from app.chat.intent import chat_intent_agent
from app.models.schemas import (
    AnswerPayload,
    AnswerProposal,
    AnswerRequest,
    AskOption,
    AskPayload,
    AskProposal,
    ChatMention,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    EditOpsProposal,
    InferredIntent,
    IntentSlot,
    PendingIntent,
    ProjectStatus,
    TaskItem,
    TaskListProposal,
)
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.operations.registry import OP_REGISTRY, validate_op
from app.operations.service import OpConflict, OpRejected, apply_operations
from app.pipeline.outputs import list_visible_outputs
from app.pipeline.registry import SkillRejected, dispatchable_skills

_ASK_BACK_TEXT = (
    "I want to make sure I do the right thing — could you be more specific? "
    "For example: re-cut highlights, remove filler words, add music, "
    "or rewrite a post."
)

_REVISE_FALLBACK_TEXT = "Got it — revising this asset based on your instruction."


def _edit_op_items(proposal: EditOpsProposal) -> list[dict]:
    """Normalize the LLM's tolerant EditOp shape into registry items.

    v1 stored extras verbatim; the registry is the adjudicator (ADR-032).
    Params may arrive nested or as top-level extras — merge, params win.
    """
    items = []
    for op in proposal.ops:
        params = {**(op.model_extra or {}), **(op.params or {})}
        for key in ("op", "type", "target"):
            params.pop(key, None)
        items.append({"op": op.op, "params": params})
    return items


def _validate_edit_ops(items: list[dict]) -> None:
    """Registry gate for edit ops (rejects unknown/system/precomputed ops
    before any state is touched — the repair loop gets the reason)."""
    if not items:
        raise OpRejected("empty edit ops")
    for item in items:
        try:
            validate_op(item["op"], item["params"], client=True)
        except (KeyError, ValueError) as e:
            raise OpRejected(str(e)) from e
        if OP_REGISTRY[item["op"]].precomputed:
            raise OpRejected(
                f"op '{item['op']}' needs a run — propose a task_list with "
                "translate_clip / dub_clip instead of edit_ops"
            )


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
    question: dict[str, Any] | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        attachments=attachments or [],
        mentions=mentions or [],
        workflow_run_id=workflow_run_id,
        intent=intent,
        question=question,
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


_RUN_STEP_PROGRESS_LIMIT = 12


def _format_step_progress(steps: list[WorkflowStep]) -> list[str]:
    """One quantified line per step of a run (G-2): ``kind: status —
    summary``. A waiting checkpoint's line reads as "waiting for you" on its
    own; a slot label preset at materialization ("Post · DE") rides the
    summary the same way. Capped — when a run outgrows the budget the tail
    (current + upcoming work) is what a progress question is about."""
    rows = []
    for step in steps:
        row = f"- {step.kind}: {step.status}"
        summary = (step.spec or {}).get("summary")
        if summary:
            row += f" — {summary}"
        rows.append(row)
    if len(rows) > _RUN_STEP_PROGRESS_LIMIT:
        omitted = len(rows) - _RUN_STEP_PROGRESS_LIMIT
        rows = [f"- … ({omitted} earlier steps omitted)"] + rows[
            -_RUN_STEP_PROGRESS_LIMIT:
        ]
    return rows


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
        steps = list(
            (
                await db.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == latest_run.id)
                    .order_by(WorkflowStep.seq)
                )
            )
            .scalars()
            .all()
        )
        progress = _format_step_progress(steps)
        if progress:
            # Node-level progress (G-2): "how far along / how much longer"
            # gets answered from real step states, not guessed.
            lines.append("Latest run steps:")
            lines.extend(progress)

    if conversation.asset_id:
        lines.append(
            f"This conversation is about the single {conversation.asset_type} "
            f"output id={conversation.asset_id}."
        )

    if recent:
        lines.append("Recent rounds:")
        for m in recent:
            if not m.content:
                continue
            line = f"- {m.role}: {m.content[:200]}"
            if m.question and m.answer:
                # Answered questions archive as QA pairs — the answer is the
                # user's decision and must be visible to the agent (a bare
                # "a" only makes sense next to the question it picked).
                answer = m.answer or {}
                reply = (
                    answer.get("text")
                    or answer.get("option_id")
                    or answer.get("kind")
                )
                line += f" (the user answered: {reply})"
            lines.append(line)

    pending = await latest_pending_question(db, UUID(str(conversation.id)))
    if pending is not None:
        # A still-open question (e.g. pick-only, no freeform): the agent must
        # not re-ask it nor ignore it — the next message may be its answer.
        lines.append(
            f"Pending question awaiting the user's answer: {pending.content}"
        )
        options = (pending.question or {}).get("options") or []
        if options:
            lines.append(
                "Options: "
                + "; ".join(
                    f"{o.get('id')}) {o.get('label')}" for o in options
                )
            )

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
            outputs=[
                IntentSlot.model_validate(s) for s in backfill.get("outputs", [])
            ],
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


# ---- Ask primitive: question / answer ------------------------------------
#
# One message row, two states: ``question`` payload present, ``answer`` NULL =
# pending. Pending questions dock above the input; answered ones archive as QA
# pairs. At most one pending question per conversation — a newer question
# retires the previous one (bail: superseded). ``content`` keeps the
# question's human text so it enters the LLM context history naturally.


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
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def is_pending_task_book(message: Message | None) -> bool:
    """A startable confirmation target (G-1): an unanswered task_book
    question — the only question kind a prose "start it" may answer."""
    return (
        message is not None
        and message.answer is None
        and (message.question or {}).get("kind") == "task_book"
    )


async def _settle_open_questions(
    db: AsyncSession, conversation_id: UUID, answer: AnswerPayload
) -> list[UUID]:
    """Answer every still-open question in one stroke (e.g. supersede).

    A superseded checkpoint question (kind=choice carrying workflow_run_id)
    can never be answered through the dock anymore — cascade-bail its parked
    run in the same stroke (node done, downstream skipped), so the single-
    pending invariant never strands a run. Returns the bailed run ids; the
    caller finalizes them after its commit. Flush-only.
    """
    from app.pipeline.orchestrator import bail_waiting_checkpoint

    open_questions = list(
        (
            await db.execute(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.question.isnot(None),
                    Message.answer.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    bailed_run_ids: list[UUID] = []
    for message in open_questions:
        message.answer = answer.model_dump(mode="json")
        if message.workflow_run_id is None:
            continue
        if (message.question or {}).get("kind") != "choice":
            continue
        run = await db.get(WorkflowRun, message.workflow_run_id)
        if run is None:
            continue
        if await bail_waiting_checkpoint(db, run) is not None:
            bailed_run_ids.append(UUID(str(run.id)))
    return bailed_run_ids


def _match_option(text: str, options: list[AskOption]) -> AskOption | None:
    """Deterministic autoResume mapping (zero LLM, prohibited-behavior #4):
    a free-text reply while a choice question is pending maps to an option
    by letter (id), number (1-based index), or the verbatim label. Anything
    else is deliberately NOT a match — semantic-level mapping is a later,
    LLM-assisted iteration.
    """
    normalized = text.strip().lower().rstrip(".。,，、!！?？:：)）]")
    if not normalized:
        return None
    for index, option in enumerate(options):
        if normalized == option.id.strip().lower():
            return option
        if normalized == str(index + 1):
            return option
        if normalized == option.label.strip().lower():
            return option
    return None


async def _dock_question(
    db: AsyncSession,
    conversation_id: UUID,
    content: str,
    payload: AskPayload,
    intent: dict[str, Any] | None = None,
) -> tuple[Message, list[UUID]]:
    """Raise a new pending question (ask 落库): at most one pending per
    conversation, so any still-open question retires as superseded first.
    The question's human text lives in ``content`` — it enters the LLM
    context history naturally and becomes the QA pair's Q line once
    answered. Returns the new message plus the run ids whose parked
    checkpoint was cascade-bailed by the supersede (finalized by the caller
    after its commit)."""
    bailed_run_ids = await _settle_open_questions(
        db,
        conversation_id,
        AnswerPayload(
            kind="bail", text="superseded", answered_at=datetime.now(UTC)
        ),
    )
    message = await _create_message(
        db,
        conversation_id,
        "assistant",
        content,
        question=payload.model_dump(mode="json"),
        intent=intent,
    )
    return message, bailed_run_ids


async def finalize_bailed_runs(run_ids: list[UUID]) -> None:
    """Settle runs cascade-bailed by a supersede (COMPLETED, never failed).

    Runs after the caller's commit — maybe_finalize_run reads committed
    state in its own session."""
    from app.pipeline.orchestrator import maybe_finalize_run

    for run_id in run_ids:
        await maybe_finalize_run(run_id)


def merge_explicit_slots(
    pinned: list[IntentSlot], inferred: list[IntentSlot]
) -> list[IntentSlot]:
    """Pin-merge rule (intent-ask-primitive §2.5): user-edited slots
    (``explicit=True``) survive re-inference untouched; the new inference
    only fills the slots the user did not pin.

    Match key = (type, language) — the identity that distinguishes same-type
    siblings (an English vs a German post). A pinned slot the new inference
    dropped entirely is re-appended (pinning means "keep this as asked").
    """
    merged = list(inferred)
    for pin in pinned:
        if not pin.explicit:
            continue
        for i, slot in enumerate(merged):
            if slot.type == pin.type and slot.language == pin.language:
                merged[i] = pin
                break
        else:
            merged.append(pin)
    return merged


def _task_book_summary(intent: InferredIntent) -> str:
    """One-line plan digest stored as the question's human text (data, not
    copy — localization happens at render time)."""
    labels = []
    for slot in intent.outputs:
        label = slot.type
        if slot.language:
            label += f"({slot.language})"
        if slot.count:
            label += f" ×{slot.count}"
        labels.append(label)
    return f"{', '.join(labels)} · {intent.language}"


async def record_intent_turn(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    turn_text: str,
    *,
    answer: str | None = None,
) -> None:
    """Archive one confirm-phase turn in the project conversation (B1).

    The user's words land as a user message — deduped against the latest
    user row so a refresh / double-fire replay never duplicates it (the
    first turn doubles as the conversation's seed prompt, which makes
    ``sync_task_book_question``'s own seed a no-op). An answer-action turn
    also lands the assistant's reply as a plain message — the exchange
    survives refresh like every other archive row. Flush-only; the caller
    commits.
    """
    conversation = await _get_or_create_project_conversation(db, user_id, project_id)
    conversation_id = UUID(str(conversation.id))
    if turn_text:
        last_user = (
            await db.execute(
                select(Message.content)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.role == "user",
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last_user != turn_text:
            await _create_message(db, conversation_id, "user", turn_text)
    if answer:
        await _create_message(db, conversation_id, "assistant", answer)


async def sync_task_book_question(
    db: AsyncSession,
    user_id: UUID,
    project: Project,
    intent: InferredIntent,
    prompt: str,
    reasons: list[str] | None = None,
) -> list[UUID]:
    """Keep exactly one pending task_book question per project conversation.

    Called by ``POST /projects/{id}/intent`` on every inference (first call
    and refinements alike): a fresh conversation first archives the original
    prompt, any still-open plan question is retired as superseded, and the
    new task book becomes the pending question. The needs_clarification
    ``reasons`` ride in the question's human text (data, localized at render)
    so the archive and the LLM context record WHY confirmation was asked.
    Returns the run ids whose parked checkpoint was cascade-bailed by the
    supersede (finalized by the caller after its commit). Flush-only.
    """
    conversation = await _get_or_create_project_conversation(
        db, user_id, UUID(str(project.id))
    )
    conversation_id = UUID(str(conversation.id))

    has_messages = (
        await db.execute(
            select(Message.id).where(Message.conversation_id == conversation_id).limit(1)
        )
    ).scalar_one_or_none()
    if has_messages is None and prompt:
        await _create_message(db, conversation_id, "user", prompt)

    content = f"Plan ready for confirmation: {_task_book_summary(intent)}"
    if reasons:
        content += f" (needs your check: {', '.join(reasons)})"
    _message, bailed_run_ids = await _dock_question(
        db, conversation_id, content, AskPayload(kind="task_book")
    )
    return bailed_run_ids


async def dock_checkpoint_question(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    run_id: UUID,
    content: str,
    payload: AskPayload,
) -> tuple[Message, list[UUID]]:
    """Dock the direction checkpoint's question (期 4, raised by the node
    runner). ``workflow_run_id`` is the dispatch marker: the answer endpoint
    recognizes a checkpoint question by it and resumes the parked run
    (answer = resume). The single-pending invariant still applies — docking
    supersedes any open question, and a superseded parked checkpoint is
    cascade-bailed (its run ids come back for the caller to finalize after
    commit). Flush-only; the caller commits."""
    conversation = await _get_or_create_project_conversation(db, user_id, project_id)
    message, bailed_run_ids = await _dock_question(
        db, UUID(str(conversation.id)), content, payload
    )
    message.workflow_run_id = run_id
    return message, bailed_run_ids


async def discard_unanswered_task_book(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
) -> None:
    """Drop an unanswered task_book question on the ``/generate`` path.

    /generate means the run started WITHOUT the user answering the docked
    question (auto-start on an explicit instruction, retries, targeted runs,
    API callers). No QA interaction happened, so the archive must not carry
    a fabricated Q/A pair — the question row is deleted outright. Genuine
    confirmations (the dock's Start button, a prose "looks good, start it")
    go through ``answer_question`` and still archive their QA pair.
    Flush-only — caller commits.
    """
    conversation = await find_conversation(db, user_id, project_id)
    if conversation is None:
        return
    pending = await latest_pending_question(db, UUID(str(conversation.id)))
    if pending is None or (pending.question or {}).get("kind") != "task_book":
        return
    await db.delete(pending)


async def answer_question(
    db: AsyncSession,
    user_id: UUID,
    message_id: UUID,
    data: AnswerRequest,
) -> tuple[Message, Message | None]:
    """Answer a pending question (``POST /chat/messages/{id}/answer``).

    The answer endpoint doubles as the resume mechanism (NAMING: answer =
    resume). Returns the answered question plus the assistant's follow-up
    when the answer continues the conversation. Dispatch by question kind:
    - task_book + bail   → drop the pending intent (project stays a draft;
                           the plan can be re-inferred from the prompt)
    - task_book + start  → start the run from the persisted pending intent
                           (kind "start" is the confirmation — no magic
                           option id; autonomy/intent only exist on it)
    - choice + answer    → record, then continue the conversation: the pick
                           rides into the next intent turn (the QA pair is
                           in context), the follow-up reply comes back here
    - choice + bail      → record only (a graceful exit, never a failure)
    A choice question carrying ``workflow_run_id`` is a direction checkpoint
    (期 4): the answer wakes the parked run (spec.answer → node back to
    pending → run back to RUNNING); bail settles the node done, cascade-
    skips the downstream, and the run completes — never failed.
    """
    from app.pipeline.orchestrator import (
        TaskSpec,
        bail_waiting_checkpoint,
        create_run,
        resume_waiting_checkpoint,
    )

    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    conversation = await db.get(Conversation, message.conversation_id)
    if conversation is None or UUID(str(conversation.user_id)) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if message.question is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Message is not a question")
    if message.answer is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Question already answered")

    question = AskPayload.model_validate(message.question)
    # Kind × question-kind contract: a task_book is only ever confirmed
    # (start) or dropped (bail); start is meaningless on any other question.
    if question.kind == "task_book" and data.kind not in ("start", "bail"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A task_book question accepts kind 'start' or 'bail' only.",
        )
    if question.kind != "task_book" and data.kind == "start":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Kind 'start' is only valid on a task_book question.",
        )
    option_label: str | None = None
    if data.kind == "option":
        if not question.options:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "This question has no options to pick from — answer in text.",
            )
        by_id = {o.id: o for o in question.options}
        if data.option_id not in by_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Unknown option_id '{data.option_id}' "
                f"(valid: {sorted(by_id)})",
            )
        option_label = by_id[str(data.option_id)].label

    message.answer = AnswerPayload(
        kind=data.kind,
        option_id=data.option_id if data.kind == "option" else None,
        # The QA archive shows the option's human label, not its bare id.
        text=(data.text if data.kind == "freeform" else None) or option_label,
        answered_at=datetime.now(UTC),
    ).model_dump(mode="json")

    follow_up: Message | None = None
    bailed_run_ids: list[UUID] = []

    if question.kind == "task_book":
        project = await db.get(Project, conversation.project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        if data.kind == "bail":
            # Graceful exit: the unconfirmed task book is dropped, the project
            # stays a draft and the prompt stays in the conversation — the
            # setup can be reopened any time. Never a failure.
            project.pending_intent = None
        else:
            # kind == "start" (the only other kind a task_book accepts).
            pending = (
                PendingIntent.model_validate(project.pending_intent)
                if isinstance(project.pending_intent, dict)
                else None
            )
            if pending is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "No pending task book to start."
                )
            # The review panel's edited task book (hand-edited slots marked
            # explicit) wins over the stored pending intent — panel edits
            # must reach the run they confirm.
            intent = data.intent or pending.intent
            outputs = list(intent.outputs) or [
                IntentSlot(type="post"),
                IntentSlot(type="quotes"),
                IntentSlot(type="article"),
            ]
            try:
                # Entry constraints (clips-media gate included) reject at the
                # birthplace — ValueError here is a client-facing 422.
                run = await create_run(
                    db,
                    project,
                    TaskSpec(
                        outputs=outputs,
                        target_language=intent.language or "en",
                        instruction=intent.specific_instruction
                        or pending.prompt
                        or None,
                        brand_template_id=(
                            str(pending.brand_template_id)
                            if pending.brand_template_id
                            else None
                        ),
                        dub_languages=intent.dub_languages,
                        autonomy=data.autonomy or "auto",
                        scope="full",
                    ),
                )
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
                ) from exc
            project.status = ProjectStatus.PROCESSING
            # The task book is confirmed now — drop the unconfirmed copy.
            project.pending_intent = None
            message.workflow_run_id = run.id

    elif question.kind == "choice" and message.workflow_run_id is not None:
        # Direction checkpoint (期 4): workflow_run_id is the dispatch
        # marker. The answer resumes the parked run — spec.answer written,
        # node back to pending, run back to RUNNING, the worker re-executes
        # the thin node. Bail is a graceful exit: node done (spec.bailed),
        # downstream cascade-skipped, run settles COMPLETED — never failed.
        run = await db.get(WorkflowRun, message.workflow_run_id)
        if run is not None:
            if data.kind == "bail":
                if await bail_waiting_checkpoint(db, run) is not None:
                    bailed_run_ids.append(UUID(str(run.id)))
            else:
                await resume_waiting_checkpoint(db, run, message.answer)

    elif question.kind == "choice" and data.kind in ("option", "freeform"):
        # 续聊: the answer unblocks the conversation — the user's pick is
        # their say for the next turn, with the QA pair in context.
        project = await db.get(Project, conversation.project_id)
        say = data.text or option_label or ""
        history = await list_conversation_messages(db, UUID(str(conversation.id)))
        follow_up, _run_id, bailed_run_ids = await _propose_turn(
            db, user_id, conversation, project, say, [], history[-6:]
        )

    await db.commit()
    if bailed_run_ids:
        # Bailed checkpoints settle COMPLETED (never FAILED, #5); each
        # aggregated summary carries the checkpoint's "Bailed by user" line
        # as the user-abort note.
        await finalize_bailed_runs(bailed_run_ids)
    await db.refresh(message)
    if follow_up is not None:
        await db.refresh(follow_up)
    return message, follow_up


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
) -> Message | None:
    """Create the project-scoped conversation and store the original prompt.

    A no-op when the conversation already has messages — the prompt is
    seeded by ``POST /projects/{id}/intent`` (first inference) since the ask
    primitive landed, so /generate callers must not duplicate it.
    """
    conversation = await _get_or_create_project_conversation(db, user_id, project_id)
    conversation_id = UUID(str(conversation.id))
    has_messages = (
        await db.execute(
            select(Message.id).where(Message.conversation_id == conversation_id).limit(1)
        )
    ).scalar_one_or_none()
    if has_messages is not None:
        return None
    return await _create_message(db, conversation_id, "user", prompt)


async def _propose_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation: Conversation,
    project: Project | None,
    text: str,
    mentions: list[ChatMention],
    recent: list[Message],
) -> tuple[Message, UUID | None, list[UUID]]:
    """One assistant turn after the user input is settled (CHAT_ARCH §3):
    assemble context, single intent call, adjudicate, record the reply.

    Shared by ``chat()`` and the choice-answer continuation in
    ``answer_question`` (the answer endpoint doubles as resume). Returns the
    assistant message, the dispatched run id if any, and the run ids whose
    parked checkpoint was cascade-bailed when a new docked question
    superseded it (finalized by the caller after its commit). Flush-only —
    the caller commits.
    """
    conversation_id = UUID(str(conversation.id))
    context = (
        await _build_context(db, project, conversation, recent, mentions)
        if project
        else {"text": ""}
    )

    proposal: TaskListProposal | EditOpsProposal | AskProposal | AnswerProposal | None = (
        None
    )
    try:
        result = await chat_intent_agent.propose(text, context)
        proposal = result.proposal
    except MiniMaxError:
        proposal = None

    run_id: UUID | None = None
    bailed_run_ids: list[UUID] = []
    assistant_message: Message | None = None
    assistant_content: str | None = None

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
                                "instruction": text,
                            },
                        )
                    ],
                    summary=text,
                )
                assistant_content = _REVISE_FALLBACK_TEXT
            except (SkillRejected, ValueError):
                assistant_content = _ASK_BACK_TEXT
        else:
            assistant_content = _ASK_BACK_TEXT
    elif isinstance(proposal, AskProposal):
        # Ask 落库 (N-18): the structured ask becomes the docked question.
        # The chat surface only has the choice form — task_book questions
        # are raised solely by the /intent code path and confirm is the
        # reserved cost-quote seat, so the agent's kind is adjudicated to
        # choice (LLM proposes, code adjudicates).
        assistant_message, bailed_run_ids = await _dock_question(
            db,
            conversation_id,
            proposal.question,
            AskPayload(
                kind="choice",
                options=proposal.options,
                allow_freeform=proposal.allow_freeform,
                cost_hint=proposal.cost_hint,
            ),
            intent=proposal.model_dump(mode="json"),
        )
    elif isinstance(proposal, AnswerProposal):
        # Direct answer (G-4, N-21): a purely informational reply lands as a
        # plain assistant message — no task, no run, no docked question
        # (same archival shape as the /intent answer turn, B1).
        assistant_content = proposal.text
    elif isinstance(proposal, EditOpsProposal):
        # Operation Model wiring (ADR-032): validate against the registry
        # (one repair round on rejection), then apply with message lineage.
        ops_items = _edit_op_items(proposal)
        try:
            _validate_edit_ops(ops_items)
        except OpRejected as first_error:
            repaired = False
            try:
                retry = await chat_intent_agent.propose(
                    text,
                    {**context, "repair_feedback": str(first_error)},
                )
                if isinstance(retry.proposal, EditOpsProposal):
                    ops_items = _edit_op_items(retry.proposal)
                    _validate_edit_ops(ops_items)
                    proposal = retry.proposal
                    repaired = True
                elif isinstance(retry.proposal, TaskListProposal) and retry.proposal.tasks:
                    run_id = await _create_run_from_tasks(
                        db, project, conversation, retry.proposal.tasks, retry.proposal.summary
                    )
                    proposal = retry.proposal
                    assistant_content = retry.proposal.summary
                    repaired = True
            except (OpRejected, SkillRejected, ValueError, MiniMaxError):
                pass
            if not repaired:
                proposal = None
                assistant_content = _cannot_do_text()
        if isinstance(proposal, EditOpsProposal):
            # Create the assistant message first (flush for the id), then
            # apply with message_id lineage — one commit at the tail.
            assistant_message = await _create_message(
                db,
                conversation_id,
                "assistant",
                proposal.summary,
                intent=proposal.model_dump(mode="json"),
            )
            try:
                await apply_operations(
                    db,
                    proposal.target_output_id,
                    ops_items,
                    source="chat",
                    user_id=user_id,
                    message_id=UUID(str(assistant_message.id)),
                )
                assistant_content = proposal.summary
            except (OpRejected, OpConflict) as e:
                assistant_message.content = _cannot_do_text()
                assistant_content = assistant_message.content
                proposal = None
            except HTTPException as e:
                # e.g. target has no render_spec — a legitimate "can't do that".
                assistant_message.content = str(e.detail)
                assistant_content = assistant_message.content
                proposal = None
    elif not proposal.tasks:
        # N-18 migration: the pre-ask "tasks=[] ask back" maps onto a
        # freeform ask (no options, free-text replies resume onto it).
        assistant_message, bailed_run_ids = await _dock_question(
            db,
            conversation_id,
            proposal.summary or _ASK_BACK_TEXT,
            AskPayload(kind="choice", options=[], allow_freeform=True),
            intent=proposal.model_dump(mode="json"),
        )
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
                    text,
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

    if assistant_message is None:
        assistant_message = await _create_message(
            db,
            conversation_id,
            "assistant",
            assistant_content,
            workflow_run_id=run_id,
            intent=proposal.model_dump(mode="json") if proposal else None,
        )
    return assistant_message, run_id, bailed_run_ids


async def chat(
    db: AsyncSession,
    user_id: UUID,
    request: ChatRequest,
) -> ChatResponse:
    """Send a message to a chat conversation and return the assistant reply.

    Single public entry point: locate/create the conversation, settle any
    pending choice question deterministically (autoResume), let the intent
    agent propose (one call), adjudicate via compile_graph (SkillRejected →
    one repair round → "I can't do that yet"), and record the turn.
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

    # Deterministic autoResume (zero LLM): while a choice question is
    # pending, the user's free text is its answer when it hits an option
    # (letter / number / verbatim label) or freeform replies are allowed —
    # otherwise it's a new intent and the question stays pending. A pending
    # task_book (unconfirmed plan) never resumes here: its answers are the
    # dock's Start/Cancel and /intent refinements.
    answered_question: Message | None = None
    pending = await latest_pending_question(db, conversation_id)
    if pending is not None:
        pending_payload = AskPayload.model_validate(pending.question)
        if pending_payload.kind == "choice":
            matched = _match_option(request.message, pending_payload.options)
            if matched is not None:
                pending.answer = AnswerPayload(
                    kind="option",
                    option_id=matched.id,
                    text=matched.label,
                    answered_at=datetime.now(UTC),
                ).model_dump(mode="json")
                answered_question = pending
            elif pending_payload.allow_freeform:
                pending.answer = AnswerPayload(
                    kind="freeform",
                    text=request.message,
                    answered_at=datetime.now(UTC),
                ).model_dump(mode="json")
                answered_question = pending
            await db.flush()

    if answered_question is not None and answered_question.workflow_run_id is not None:
        # Checkpoint autoResume (期 4): a typed answer to the docked direction
        # question takes the same dispatch as the answer endpoint — wake the
        # parked run. No LLM turn on top: the wake IS the continuation (the
        # step flow shows the run resuming), so the acknowledgment is a
        # deterministic line.
        from app.pipeline.orchestrator import resume_waiting_checkpoint

        run = await db.get(WorkflowRun, answered_question.workflow_run_id)
        if run is not None:
            await resume_waiting_checkpoint(db, run, answered_question.answer)
        decided = (answered_question.answer or {}).get("text") or (
            answered_question.answer or {}
        ).get("option_id") or ""
        assistant_message = await _create_message(
            db,
            conversation_id,
            "assistant",
            f"Direction locked: {decided}. Resuming the run.",
        )
        run_id = None
        bailed_run_ids = []
    else:
        assistant_message, run_id, bailed_run_ids = await _propose_turn(
            db,
            user_id,
            conversation,
            project,
            request.message,
            request.mentions,
            history[-6:],
        )

    await db.commit()
    await finalize_bailed_runs(bailed_run_ids)
    return ChatResponse(
        conversation_id=conversation_id,
        user_message=ChatMessageResponse.model_validate(user_message),
        assistant_message=ChatMessageResponse.model_validate(assistant_message),
        run_id=run_id,
        answered_question=(
            ChatMessageResponse.model_validate(answered_question)
            if answered_question is not None
            else None
        ),
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
