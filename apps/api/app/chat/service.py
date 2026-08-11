"""Generic chat service.

A conversation is the universal container. It can be project-scoped (the
original prompt plus project-level follow-ups) or asset-scoped (a clip,
LinkedIn post, quote card, etc.).

The public surface is intentionally tiny: ``chat()`` takes a user message,
locates or creates the right conversation, assembles deterministic context,
and lets the intent agent propose (CHAT_ARCH §3). It is the ONLY intent
surface (intent-surface-unification W1): project-scope turns before the
first run — or while a task book is pending — go through the plan path
(``_plan_turn``: build / refine / confirm the task book via the PlanAgent);
everything else goes to the four-state proposer:

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
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minimax import MiniMaxError
from app.agents.contexts import _build_context
from app.chat.intent import chat_intent_agent, plan_agent
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
    StartAnswerRequest,
    TaskItem,
    TaskListProposal,
)
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    Project,
    WorkflowRun,
)
from app.operations.registry import OP_REGISTRY, validate_op
from app.operations.service import OpConflict, OpRejected, apply_operations
from app.pipeline.asset_processing import has_renderable_media
from app.pipeline.assets import create_transcript_asset_from_text
from app.pipeline.recipes import resolve_recipe_launch
from app.skills import SkillRejected, dispatchable_skills

_ASK_BACK_TEXT = (
    "I want to make sure I do the right thing — could you be more specific? "
    "For example: re-cut highlights, remove filler words, add music, "
    "or rewrite a post."
)

_REVISE_FALLBACK_TEXT = "Got it — revising this asset based on your instruction."


def _ask_for_material_text(prompt: str) -> str:
    """Server-composed ask-for-material reply (zero-material safety net).

    The PlanAgent is instructed to write this itself; this is the backstop
    when it misfiles a material-less generate verdict. Language follows the
    prompt — the plan path's answer prose always speaks the user's language.
    """
    if any("一" <= ch <= "鿿" for ch in prompt):  # CJK Unified Ideographs
        return (
            "我还没有可以处理的素材。点输入框左侧的回形针上传视频、音频或图片，"
            "或者直接把文稿贴在对话里发给我——贴来的内容我会当作素材，"
            "不用特别标注。"
        )
    return (
        "I don't have any source material yet. Attach a video, audio, or "
        "image with the paperclip next to the input — or simply paste your "
        "text into the chat; pasted content is treated as your material, no "
        "special formatting needed."
    )



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


_SLOT_MERGE_FIELDS = ("count", "focus", "language", "tone_override")


def _match_slot(slots: list[IntentSlot], slot: IntentSlot) -> IntentSlot | None:
    """Find the slot representing the same logical output: same type AND
    language first (the identity that distinguishes same-type siblings — an
    English vs a German post), then same type alone (a language revision
    retargets the slot rather than creating a sibling)."""
    return next(
        (s for s in slots if s.type == slot.type and s.language == slot.language),
        None,
    ) or next((s for s in slots if s.type == slot.type), None)


def merge_prior_slots(
    base: list[IntentSlot],
    prior: list[IntentSlot],
    inferred: list[IntentSlot],
) -> list[IntentSlot]:
    """Three-way merge of the panel's book into a fresh re-inference.

    base = the last-served (stored) book; prior = the panel's current book
    (``explicit=True`` marks slots the user hand-edited); inferred = the
    LLM's fresh read of the conversation.

    Per field, for a hand-edited slot:

    - inference is null → no opinion; keep the panel value;
    - panel == base → the panel never moved this field; inference owns it;
    - inference == base → the LLM parroted the old state; the panel's newer
      edit wins;
    - both moved → **chat wins** (2026-08-05 ruling: chat IS how the user
      edits the plan — nothing is locked, the latest deliberate signal
      prevails).

    Slots the user never touched follow the inference wholesale. A hand-
    edited slot the inference dropped entirely is re-appended (protects
    panel edits from LLM omission; deleting a slot the user hand-edited
    must happen in the panel itself)."""
    merged = list(inferred)
    for pin in prior:
        if not pin.explicit:
            continue
        slot = _match_slot(merged, pin)
        if slot is None:
            merged.append(pin)
            continue
        base_slot = _match_slot(base, pin)
        for field in _SLOT_MERGE_FIELDS:
            inferred_value = getattr(slot, field)
            pin_value = getattr(pin, field)
            if inferred_value is None:
                # null = no opinion — the panel's current value stands.
                setattr(slot, field, pin_value)
                continue
            base_value = getattr(base_slot, field) if base_slot else None
            if pin_value != base_value and inferred_value == base_value:
                # The panel moved this field and the LLM merely parroted the
                # old state — the panel's edit wins. (Panel untouched, or
                # both moved: the inference stands — chat always wins.)
                setattr(slot, field, pin_value)
        slot.explicit = True
    return merged


def _task_book_summary(intent: InferredIntent) -> str:
    """One-line plan digest stored as the question's human text (data, not
    copy — localization happens at render time). Language is a per-slot
    property (2026-08-05 restructure), so each slot carries its own."""
    labels = []
    for slot in intent.outputs:
        label = slot.type
        if slot.language:
            label += f"({slot.language})"
        if slot.count:
            label += f" ×{slot.count}"
        labels.append(label)
    return ", ".join(labels)


async def sync_task_book_question(
    db: AsyncSession,
    user_id: UUID,
    project: Project,
    intent: InferredIntent,
    prompt: str,
    reasons: list[str] | None = None,
) -> list[UUID]:
    """Keep exactly one pending task_book question per project conversation.

    Called by the chat plan path on every inference (first call and
    refinements alike): a fresh conversation first archives the original
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
    # Reason keys ride the question PAYLOAD (data, localized at render) —
    # never baked into content, which is user-facing prose (the QA archive
    # renders it verbatim). The LLM context line re-appends them (keys are
    # the agent's vocabulary).
    _message, bailed_run_ids = await _dock_question(
        db,
        conversation_id,
        content,
        AskPayload(kind="task_book", reasons=reasons or []),
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
                # target_language is now a pure fallback (language is a
                # per-slot property): derive it from the first slot that
                # carries one, for legacy/null-slot reads downstream.
                run = await create_run(
                    db,
                    project,
                    TaskSpec(
                        outputs=outputs,
                        target_language=(
                            next((s.language for s in outputs if s.language), None)
                            or "en"
                        ),
                        instruction=intent.specific_instruction
                        or pending.prompt
                        or None,
                        persona_id=(
                            str(pending.persona_id)
                            if pending.persona_id
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

    A no-op when the conversation already has messages — the first message
    normally lands via the chat plan path, so /generate callers must not
    duplicate it.
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


async def _plan_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation: Conversation,
    project: Project,
    request: ChatRequest,
    recent: list[Message] | None = None,
    on_delta=None,
    on_reasoning=None,
) -> tuple[Message, UUID | None, Message | None, list[UUID]]:
    """Plan path (intent-surface-unification W1): build / refine / confirm
    the task book inside the chat loop — the ONLY intent surface.

    Entered for project-scope turns while a task book is pending (refine or
    prose confirmation) or before the project's first run (first turn / after
    a bail). The PlanAgent's three-action verdict dispatches:

    - generate → three-way merge (panel prior / recipe seed) + reasons + dock
      the (refined) task book
    - answer   → a plain assistant message; the stored book stays untouched
    - start    → the docked task book is answered kind=start (G-1 path: the
                 run comes from the only birthplace, answer_question)

    Returns the assistant message (the docked/answered question row for
    generate/start), the started run id, the answered task-book question (for
    ChatResponse.answered_question), and cascade-bailed run ids. The caller
    commits — except the start branch, where answer_question commits.
    """
    conversation_id = UUID(str(conversation.id))
    text = request.message
    if not text.strip() and request.attachments:
        # Attachment-only turn (files staged in the overlay's input group,
        # sent with no text): the persisted user message stays empty (the
        # chips carry the record), but the inference needs honest words —
        # the files themselves are listed in the Assets context block.
        names = ", ".join(a.name for a in request.attachments)
        text = (
            f"(I just attached new source files: {names}. "
            "No note — treat them as material for what I asked, or ask what "
            "I'd like made from them.)"
        )

    stored = (
        PendingIntent.model_validate(project.pending_intent)
        if isinstance(project.pending_intent, dict)
        else None
    )
    # Refinement turns infer against the accumulated prompt (the stored book's
    # prompt + this turn's own words); the archive already holds each turn as
    # its own user message, so no dedup bookkeeping is needed here.
    prompt = f"{stored.prompt}\n{text}" if stored and stored.prompt else text

    assets = list(
        (
            await db.execute(
                select(Asset).where(
                    Asset.project_id == project.id,
                    Asset.file_url.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    first_file = next((a for a in assets if a.file_url), None)
    filename = first_file.file_url.rsplit("/", 1)[-1] if first_file else None

    # Recipe launch validation (fail-fast, BEFORE inference): a rejected id
    # (reserved / unknown) must not burn an intent call.
    try:
        recipe = resolve_recipe_launch(request.recipe_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # plan_agent never raises MiniMaxError — its declared fallback (Agent
    # funnel 的声明兜底) is the default task book (dockable, editable,
    # startable; never a white screen). The presented plan rides along so the
    # start/revise verdict sees what is actually being confirmed; the recent
    # rounds ride along so the material/content judgment sees what just
    # happened (G-7 — e.g. the assistant asked for source material and the
    # user then pastes it; same "feed the context, never make the model guess
    # blind" precedent as presented_plan). on_delta (chat SSE) streams the raw
    # verdict fragments for the answer-prose preview; on_reasoning is a
    # liveness signal for the thinking indicator. None = today's one-shot call.
    recent_lines: list[str] = []
    for m in recent or []:
        attached = [a.get("name") for a in (m.attachments or []) if a.get("name")]
        if not m.content and not attached:
            continue
        line = f"- {m.role}: {(m.content or '')[:200]}"
        if attached:
            line += f" [attached: {', '.join(attached)}]"
        recent_lines.append(line)
    infer_kwargs: dict[str, Any] = dict(
        prompt=prompt,
        filename=filename,
        presented_plan=(
            _task_book_summary(stored.intent) if stored is not None else None
        ),
        recent=recent_lines or None,
    )
    if on_delta is not None:
        intent = await plan_agent.call_stream(
            on_delta=on_delta, on_reasoning=on_reasoning, **infer_kwargs
        )
    else:
        intent = await plan_agent.call(**infer_kwargs)

    # Declared-material promotion (2026-08-05 手测决策): the user explicitly
    # said "this is my transcript/content" — the pasted text becomes a real
    # TRANSCRIPT asset (visible, named; groundwork for the synthetic-talk
    # line). Never inferred from text length — the LLM extracts it only on an
    # explicit declaration.
    material_asset: Asset | None = None
    if intent.material_text and intent.material_text.strip():
        material_asset = await create_transcript_asset_from_text(
            db, UUID(str(project.id)), user_id, intent.material_text.strip()
        )
        assets.append(material_asset)

    # Zero-material safety net (same decision): a generate verdict with no
    # assets at all and no declared material must not dock a groundless task
    # book — degrade to the ask-for-material answer. Only when no book is
    # already on the table (a pending book's refine/start is untouched).
    if (
        intent.action == "generate"
        and stored is None
        and not assets
        and material_asset is None
    ):
        intent.action = "answer"
        intent.answer = _ask_for_material_text(prompt)

    has_media = await has_renderable_media(db, UUID(str(project.id)))

    # Three-way merge rule (2026-08-05 ruling): base = the last-served book,
    # prior = the panel's current book (explicit slots = hand-edited),
    # inferred = the LLM's fresh read. Hand-edited fields survive when the
    # LLM has no opinion or merely parrots the old state; anything the user's
    # message revises wins — chat IS how the plan is edited, nothing is
    # locked. Falls back to the stored pending intent when the caller did
    # not send its current book.
    prior = request.prior_intent or (stored.intent if stored else None)
    if prior is not None:
        base_slots = stored.intent.outputs if stored else []
        intent.outputs = merge_prior_slots(base_slots, prior.outputs, intent.outputs)
        # dub_languages, same three-way shape: an untouched panel list
        # follows the fresh inference wholesale (refine can add/drop/empty
        # languages); a panel-edited list survives an inference that is
        # silent (empty = no opinion) or merely parrots the old list; when
        # both diverge, chat wins. The confirm path (kind=start) always
        # honors the panel's list directly.
        stored_dub = stored.intent.dub_languages if stored else []
        if prior.dub_languages == stored_dub:
            pass  # panel untouched — inference owns it
        elif not intent.dub_languages or intent.dub_languages == stored_dub:
            intent.dub_languages = list(prior.dub_languages)
        # else: both moved — chat wins, the inference stands.

    # Recipe launch seed: a recipe is a PRESET, not a pin — "仅仅是第一版的
    # 东西". Resolved server-side (the recipe_id transport — MENTIONS §3) and
    # applied AFTER the panel prior: slot types the inference didn't produce
    # are appended so the first book matches the card's shape; dub_languages
    # fills only when the prompt named none. Nothing is explicit — every
    # field (and each slot's existence) is refine-able from the very next
    # turn. The LLM never interprets the recipe (validated pre-inference).
    if recipe is not None:
        seeded = {s.type for s in intent.outputs}
        for slot in recipe.outputs:
            if slot.type not in seeded:
                intent.outputs.append(slot.model_copy())
        if not intent.dub_languages:
            intent.dub_languages = list(recipe.dub_languages)
        intent.outputs_explicit = True

    clips_slot = next((s for s in intent.outputs if s.type == "clips"), None)
    reasons: list[str] = []
    if not intent.outputs_explicit:
        reasons.append("outputs_default")
    if clips_slot is not None and clips_slot.count is None:
        reasons.append("clip_count_default")
    if clips_slot is not None and not has_media:
        reasons.append("clips_without_media")

    # An answer action without answer text is an LLM misfire — degrade to a
    # plan turn (dock the book for confirmation) rather than clobber the
    # stored task book with an empty answer.
    if intent.action == "answer" and not intent.answer:
        intent.action = "generate"

    if intent.action == "start":
        # G-1: a prose confirmation ("looks good, start it") is not a
        # revision — it answers the docked task_book question with
        # kind=start, so the run still comes from the only birthplace
        # (answer_question → create_run, which also clears pending_intent in
        # the same transaction). The dock's autonomy tier rides the request —
        # a review-tier choice must survive a prose confirmation.
        pending_question = await latest_pending_question(db, conversation_id)
        if is_pending_task_book(pending_question) and stored is not None:
            answered, _follow_up = await answer_question(
                db, user_id, UUID(str(pending_question.id)),
                StartAnswerRequest(kind="start", autonomy=request.autonomy),
            )
            # answer_question commits — the run, the answer and the cleared
            # pending intent land in one transaction.
            return answered, UUID(str(answered.workflow_run_id)), answered, []
        if stored is not None:
            # Nothing startable right now. Never overwrite a stored task book
            # with a start-action misfire's fields: re-dock the stored book
            # unchanged.
            bailed_run_ids = await sync_task_book_question(
                db, user_id, project, stored.intent, stored.prompt,
                reasons=stored.reasons,
            )
            question = await latest_pending_question(db, conversation_id)
            assert question is not None  # sync_task_book_question just docked it
            return question, None, None, bailed_run_ids
        intent.action = "generate"

    if intent.action == "answer" and intent.answer:
        # Capability question: the reply lands as a plain assistant message
        # and the stored task book stays untouched — an answer turn never
        # overwrites the plan the user is confirming.
        assistant_message = await _create_message(
            db, conversation_id, "assistant", intent.answer
        )
        return assistant_message, None, None, []

    # A turn that omits persona_id must not clobber the persona choice an
    # earlier turn made.
    persona_id = request.persona_id
    if persona_id is None and isinstance(project.pending_intent, dict):
        persona_id = project.pending_intent.get("persona_id")

    # Persist the unconfirmed task book on the project: leaving the chat and
    # coming back (any device) restores this exact plan. Cleared once the run
    # starts. The dock above the input rebuilds from the task_book question.
    project.pending_intent = PendingIntent(
        prompt=prompt,
        intent=intent,
        reasons=reasons,
        persona_id=persona_id,
    ).model_dump(mode="json")
    bailed_run_ids = await sync_task_book_question(
        db, user_id, project, intent, prompt, reasons=reasons
    )
    question = await latest_pending_question(db, conversation_id)
    assert question is not None  # sync_task_book_question just docked it
    return question, None, None, bailed_run_ids


async def _propose_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation: Conversation,
    project: Project | None,
    text: str,
    mentions: list[ChatMention],
    recent: list[Message],
    on_delta=None,
    on_reasoning=None,
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
        await _build_context(
            db,
            project,
            conversation,
            recent,
            mentions,
            await latest_pending_question(db, conversation_id),
        )
        if project
        else {"text": ""}
    )

    proposal: TaskListProposal | EditOpsProposal | AskProposal | AnswerProposal | None = (
        None
    )
    try:
        if on_delta is not None:
            # Chat SSE: stream the verdict; raw fragments feed the prose
            # preview extractor. Repair rounds stay non-streaming (the funnel
            # handles that — N-26).
            result = await chat_intent_agent.call_stream(
                message=text, context=context,
                on_delta=on_delta, on_reasoning=on_reasoning,
            )
        else:
            result = await chat_intent_agent.call(message=text, context=context)
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
        # are raised solely by the plan path and confirm is the
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
            ),
            intent=proposal.model_dump(mode="json"),
        )
    elif isinstance(proposal, AnswerProposal):
        # Direct answer (G-4, N-21): a purely informational reply lands as a
        # plain assistant message — no task, no run, no docked question
        # (same archival shape as a plan-path answer turn, B1).
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
                retry = await chat_intent_agent.call(
                    message=text, context=context,
                    repair_feedback=str(first_error),
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
            # One bounded repair round with the rejection as feedback (the
            # funnel's reserved kwarg — the echo lives in Agent.call).
            repaired = False
            try:
                retry = await chat_intent_agent.call(
                    message=text, context=context,
                    repair_feedback=(
                        f"{first_error} "
                        f"(available: {getattr(first_error, 'suggestions', [])})"
                    ),
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


@dataclass
class PreparedTurn:
    """chat() phase-1 output (chat SSE, intent-surface-unification W2).

    Everything decided before the LLM call: conversation, the persisted user
    message, a deterministically answered question (autoResume), the canned
    checkpoint-resume reply when the turn needs no LLM at all, and the
    plan-path dispatch bit. All 4xx-raising validation lives in phase 1 so a
    streaming route can raise plain HTTP errors before the SSE response
    starts; phase 2 (``execute_chat_turn``) only runs the agent turn, commits
    once at the end, and assembles the response.
    """

    user_id: UUID
    conversation: Conversation
    conversation_id: UUID
    user_message: Message
    project: Project | None
    history: list[Message]
    answered_question: Message | None
    checkpoint_reply: Message | None
    plan_path: bool


async def prepare_chat_turn(
    db: AsyncSession,
    user_id: UUID,
    request: ChatRequest,
) -> PreparedTurn:
    """chat() phase 1: settle everything up to the dispatch decision."""
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
    # dock's Start/Cancel and plan-path refinements below.
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
            elif pending_payload.allow_freeform and request.message.strip():
                # A blank attachment-only turn never answers a checkpoint —
                # the files ride the intent paths below instead.
                pending.answer = AnswerPayload(
                    kind="freeform",
                    text=request.message,
                    answered_at=datetime.now(UTC),
                ).model_dump(mode="json")
                answered_question = pending
            await db.flush()

    checkpoint_reply: Message | None = None
    plan_path = False
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
        checkpoint_reply = await _create_message(
            db,
            conversation_id,
            "assistant",
            f"Direction locked: {decided}. Resuming the run.",
        )
    else:
        # Plan path dispatch (intent-surface-unification W1): this endpoint is
        # the ONLY intent surface. A project-scope turn goes to the plan path
        # (task-book build / refine / confirm via the PlanAgent) while a task
        # book is pending or before the project's first run; everything else
        # goes to the four-state proposer. Asset-scope turns never build task
        # books.
        if project is not None and conversation.asset_id is None:
            if is_pending_task_book(pending):
                plan_path = True
            elif not isinstance(project.pending_intent, dict):
                has_runs = (
                    await db.execute(
                        select(WorkflowRun.id)
                        .where(WorkflowRun.project_id == project.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                plan_path = has_runs is None

    return PreparedTurn(
        user_id=user_id,
        conversation=conversation,
        conversation_id=conversation_id,
        user_message=user_message,
        project=project,
        history=history,
        answered_question=answered_question,
        checkpoint_reply=checkpoint_reply,
        plan_path=plan_path,
    )


async def execute_chat_turn(
    db: AsyncSession,
    prepared: PreparedTurn,
    request: ChatRequest,
    on_delta=None,
    on_reasoning=None,
) -> ChatResponse:
    """chat() phase 2: run the agent turn, commit once, assemble the response.

    ``on_delta`` (chat SSE) receives raw LLM verdict fragments for the prose
    preview channel; ``on_reasoning`` receives reasoning fragments as a
    liveness signal for the thinking indicator. None (the JSON path, repair
    rounds, answer_question's continuation) keeps today's one-shot calls.
    """
    if prepared.checkpoint_reply is not None:
        assistant_message = prepared.checkpoint_reply
        run_id = None
        bailed_run_ids: list[UUID] = []
    elif prepared.plan_path:
        # The plan agent's context excludes this turn's own message (already
        # the prompt being judged); the latest few rounds before it are the
        # disambiguating conversation (G-7).
        recent = [
            m for m in prepared.history if m.id != prepared.user_message.id
        ][-5:]
        assistant_message, run_id, plan_answered, bailed_run_ids = await _plan_turn(
            db,
            prepared.user_id,
            prepared.conversation,
            prepared.project,
            request,
            recent=recent,
            on_delta=on_delta,
            on_reasoning=on_reasoning,
        )
        if plan_answered is not None:
            prepared.answered_question = plan_answered
    else:
        assistant_message, run_id, bailed_run_ids = await _propose_turn(
            db,
            prepared.user_id,
            prepared.conversation,
            prepared.project,
            request.message,
            request.mentions,
            prepared.history[-6:],
            on_delta=on_delta,
            on_reasoning=on_reasoning,
        )

    await db.commit()
    await finalize_bailed_runs(bailed_run_ids)
    return ChatResponse(
        conversation_id=prepared.conversation_id,
        user_message=ChatMessageResponse.model_validate(prepared.user_message),
        assistant_message=ChatMessageResponse.model_validate(assistant_message),
        run_id=run_id,
        answered_question=(
            ChatMessageResponse.model_validate(prepared.answered_question)
            if prepared.answered_question is not None
            else None
        ),
    )


async def chat(
    db: AsyncSession,
    user_id: UUID,
    request: ChatRequest,
) -> ChatResponse:
    """Send a message to a chat conversation and return the assistant reply.

    Single public entry point (JSON path): prepare the turn (locate/create
    the conversation, settle any pending choice question deterministically),
    then execute it (intent agent proposes, compile_graph adjudicates, one
    commit). The SSE path calls the two phases itself so prose deltas can
    stream between them.
    """
    prepared = await prepare_chat_turn(db, user_id, request)
    return await execute_chat_turn(db, prepared, request)


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
