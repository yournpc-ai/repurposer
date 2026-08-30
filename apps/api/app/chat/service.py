"""Generic chat service.

A conversation is the universal container — always project-scoped (the
original prompt plus project-level follow-ups). Asset-scoped conversations
are retired (ADR-041 D8): product chat lives in the project conversation,
and the product the user points at rides each turn as ``focus_output``
(焦点注入 — one context line, never a scope).

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

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    Output,
    Project,
    WorkflowRun,
)
from app.operations.registry import OP_REGISTRY, validate_op
from app.operations.service import OpConflict, OpRejected, apply_operations
from app.pipeline.asset_processing import has_any_text_material, has_renderable_media
from app.pipeline.assets import create_transcript_asset_from_text
from app.pipeline.derivative_dispatch import (
    DerivativeWriterNode,
    _project_source_language,
    derive_quote_alt_language,
)
from app.pipeline.graph import MEDIA, NODE_KINDS
from app.providers.llm.minimax import MiniMaxError
from app.tools import ToolRejected, validate_task_list

logger = structlog.get_logger()

# Chat entry caps (2026-08-20 ruling) — enforced in prepare_chat_turn.
MAX_MESSAGE_CHARS = 20_000
MAX_ATTACHMENTS_PER_TURN = 5
MAX_MENTIONS_PER_TURN = 10
# Plan-accumulation prompt: keep the original intent (head) and the newest
# refinements (tail); middle prose yields — those revisions already live in
# the task book's slots.
MAX_ACCUM_PROMPT_CHARS = 4_000

_ASK_BACK_TEXT = (
    "I want to make sure I do the right thing — could you be more specific? "
    "For example: re-cut highlights, remove filler words, add music, "
    "or rewrite a post."
)


def _ask_for_material_text(prompt: str) -> str:
    """Server-composed ask-for-material reply (zero-material safety net).

    The PlanAgent is instructed to write this itself; this is the backstop
    when it misfiles a material-less generate verdict. Language follows the
    prompt — the plan path's answer prose always speaks the user's language.
    """
    if _prefers_zh(prompt):
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


async def _create_message(
    db: AsyncSession,
    conversation_id: UUID,
    role: str,
    content: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
    mentions: list[dict[str, Any]] | None = None,
    focus_output: dict[str, Any] | None = None,
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
        focus_output=focus_output,
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
    tasks: list[TaskItem],
    summary: str,
    caption_mode: str | None = None,
) -> UUID:
    """Dispatch a proposed task list through the ONLY run birthplace."""
    from app.pipeline.orchestrator import TaskSpec, create_run, first_task_language

    run = await create_run(
        db,
        project,
        TaskSpec(
            tasks=tasks,
            target_language=first_task_language(tasks) or project.language or "en",
            instruction=summary,
            scope="full",
            caption_mode=caption_mode,
        ),
    )
    return run.id


def _prefers_zh(text: str) -> bool:
    """Language heuristic for server-composed reply lines — the CJK check
    rides the user's own words (the turn's text), not a stored setting."""
    return any("一" <= ch <= "鿿" for ch in text)  # CJK Unified Ideographs


# Caption mode for captioned-video runs (Phase 1, 2026-08-25, RECIPES §4.7):
# the chat path asks the user to pick bilingual / source_only / target_only
# when a `write_quotes` task is proposed without an explicit caption-mode
# hint. Three layers of detection, in priority order:
#
#  1. LLM-set on InferredIntent.caption_mode (the plan agent recognises the
#     user's wording — "bilingual subtitles" / "中英双语字幕" — and sets it).
#  2. Code-level keyword scan on the user prompt (defence-in-depth: the LLM
#     may miss the phrasing, but a literal "bilingual"/"双语" is unambiguous).
#  3. Otherwise: dock a choice question, the answer rides the AskProposal path.
#
# Single source of truth for the option_id encoding — answer_question uses
# the same prefix to recover the choice (caption_mode_bilingual / _source_only
# / _target_only → Literal value), so the question and the answer share a
# hand-shake no LLM can break.
_CAPTION_MODE_KEYWORDS_BILINGUAL: tuple[str, ...] = (
    "bilingual",
    "bilingual subtitles",
    "bilingual captions",
    "双语",
    "中英双语",
    "中英对照",
    "双语字幕",
    "中英",
)
_CAPTION_MODE_KEYWORDS_SOURCE_ONLY: tuple[str, ...] = (
    "source only",
    "source language only",
    "源语言",
    "原文",
    "原声字幕",
    "只保留原",
    "只保留源",
)
_CAPTION_MODE_KEYWORDS_TARGET_ONLY: tuple[str, ...] = (
    "target only",
    "target language only",
    "目标语言",
    "只保留目标",
)


def _detect_caption_mode(prompt: str) -> str | None:
    """Code-level keyword scan — the LLM may set caption_mode too, but a
    literal "bilingual"/"双语" is unambiguous so we don't waste a question.
    Source/target-only is intentionally left for the chat to ask: the user's
    intent is genuinely ambiguous without knowing the source language."""
    text = (prompt or "").lower()
    if any(kw in text for kw in _CAPTION_MODE_KEYWORDS_BILINGUAL):
        return "bilingual"
    return None


def _needs_caption_mode_question(tasks: list) -> bool:
    """Quote-card chain (write_quotes) is the only recipe currently asking
    for caption mode — registry-native via the DerivativeWriterNode check,
    no parallel "which tools need subtitles" list."""
    return any(
        isinstance(NODE_KINDS.get(t.tool), DerivativeWriterNode)
        and t.tool == "write_quotes"
        for t in tasks
    )


async def _caption_choice_is_meaningful(
    db: AsyncSession, project: Project, tasks: list
) -> bool:
    """§2.3/D4 (2026-08-28): is there a DISTINCT second language to offer?

    Bilingual/target-only only make sense when an alt language exists that
    differs from the source material's language. Derivation order (same as
    the run-time path): the task's own target language (user-named) → the
    project/UI locale. When every candidate equals the source, the choice
    question would be theatre — skip it and let the caller stamp
    ``source_only``.
    """
    source = await _project_source_language(db, project)
    task_language = next(
        (
            (t.params or {}).get("language")
            for t in tasks
            if getattr(t, "tool", None) == "write_quotes"
        ),
        None,
    )
    return (
        derive_quote_alt_language(source, task_language, project.language)
        is not None
    )


def _build_caption_mode_question(text: str) -> AskProposal:
    """The caption-mode choice question — bilingual is the canonical default
    (matches the recipe's example prompt and the reference images). The
    option_id prefix `caption_mode_` is a handshake the answer path uses to
    recover the choice (caption_mode_bilingual → Literal "bilingual")."""
    zh = _prefers_zh(text)
    if zh:
        return AskProposal(
            type="ask",
            question="字幕模式？",
            kind="choice",
            options=[
                AskOption(id="caption_mode_bilingual", label="双语字幕（推荐）"),
                AskOption(id="caption_mode_source_only", label="只保留源语言"),
                AskOption(id="caption_mode_target_only", label="只保留目标语言"),
            ],
            allow_freeform=False,
        )
    return AskProposal(
        type="ask",
        question="Caption mode?",
        kind="choice",
        options=[
            AskOption(id="caption_mode_bilingual", label="Bilingual (recommended)"),
            AskOption(id="caption_mode_source_only", label="Source language only"),
            AskOption(id="caption_mode_target_only", label="Target language only"),
        ],
        allow_freeform=False,
    )


def _recover_caption_mode_from_answer(message: Message) -> str | None:
    """Read a docked caption-mode question's answer off the message row.
    The option_id prefix `caption_mode_` is the handshake; free-form answers
    fall back to a keyword scan (the LLM may have written a localised label
    like 'bilingual' as freeform text)."""
    answer = message.answer if isinstance(message.answer, dict) else None
    if not answer:
        return None
    option_id = answer.get("option_id")
    if isinstance(option_id, str) and option_id.startswith("caption_mode_"):
        return option_id[len("caption_mode_"):]
    text = (answer.get("text") or "").lower()
    if any(kw in text for kw in _CAPTION_MODE_KEYWORDS_BILINGUAL):
        return "bilingual"
    if any(kw in text for kw in _CAPTION_MODE_KEYWORDS_SOURCE_ONLY):
        return "source_only"
    if any(kw in text for kw in _CAPTION_MODE_KEYWORDS_TARGET_ONLY):
        return "target_only"
    return None


def _resolved_caption_mode(project: Project) -> str | None:
    """The answered caption mode stashed on the pending intent, if any.

    The answer fast path writes it onto ``pending_intent.intent.caption_mode``
    and every consumption site (plan-turn overwrite, propose-turn run) must
    INHERIT it — a fresh verdict's ``caption_mode=None`` is "not mentioned
    this turn", never "the user retracted the answer".
    """
    pending = project.pending_intent if isinstance(project.pending_intent, dict) else None
    if not pending:
        return None
    intent = pending.get("intent") or {}
    mode = intent.get("caption_mode")
    return str(mode) if mode else None


def _has_resolved_caption_mode(project: Project) -> bool:
    """A caption-mode question was already answered and the answer is
    reflected in the stored pending_intent — the next plan turn re-uses it
    instead of re-docking the question (the user has spoken). Mirrors the
    pending_intent's role for the task book (CHAT_ARCH §3)."""
    return _resolved_caption_mode(project) is not None


async def _derive_chat_caption_mode(
    db: AsyncSession, project: Project, tasks: list, text: str
) -> str | None:
    """The propose path's caption-mode derivation for an immediate run:
    fresh keyword > stashed answer > source_only when no distinct alt
    language exists (§2.3/D4 — the question would be theatre). Returns
    None when the chain carries no captioned task.

    The single funnel for every chat-path run birth (2026-08-29): the
    main dispatch AND both LLM-repair re-dispatches — a repaired
    task_list is the same run birth and must not lose the mode (the
    repair sites used to call ``_create_run_from_tasks`` bare)."""
    if not _needs_caption_mode_question(tasks):
        return None
    mode = _detect_caption_mode(text) or _resolved_caption_mode(project)
    if mode is None and not await _caption_choice_is_meaningful(db, project, tasks):
        mode = "source_only"
    return mode


def _is_caption_mode_question(question: AskPayload) -> bool:
    """Identify a docked caption-mode question by its option_id prefix — the
    only stable handshake between the dock and the answer paths."""
    return bool(question.options) and all(
        o.id.startswith("caption_mode_") for o in question.options
    )


def _replay_stashed_caption_intent(message: Message) -> InferredIntent | None:
    """Recover the stashed intent the caption-mode question was holding.

    Two shapes ride the question's ``intent`` field:
      - ``TaskListProposal`` from ``_propose_turn`` (chat_intent_agent path;
        carries ``type="task_list"`` + ``tasks`` + ``summary``) — we wrap it
        back into an InferredIntent, the same shape plan-path stores
      - bare ``InferredIntent`` from ``_plan_turn`` (plan_agent path; first
        turn goes here) — used as-is, the LLM already gave us a complete intent

    Returns None when the stash is missing or unrecognized — the caller
    degrades to a no-op (the answer is recorded but no follow-up docks).
    """
    stashed = message.intent
    if not isinstance(stashed, dict):
        return None
    if stashed.get("type") == "task_list":
        # _propose_turn path: TaskListProposal
        try:
            tlp = TaskListProposal.model_validate(stashed)
        except Exception:  # noqa: BLE001 — bad stash, degrade
            return None
        return InferredIntent(tasks=tlp.tasks)
    if "tasks" in stashed and "action" in stashed:
        # _plan_turn path: bare InferredIntent (the plan agent's verdict)
        try:
            return InferredIntent.model_validate(stashed)
        except Exception:  # noqa: BLE001
            return None
    return None


async def _compute_book_reasons(
    db: AsyncSession,
    project: Project,
    intent: InferredIntent,
) -> list[str]:
    """Re-derive the soft-signal reasons for a docked task book (Phase 1
    answer path needs this — the caption_mode replay rebuilds the
    PendingIntent from the stashed intent and the reasons computed in
    _plan_turn are scoped to that function's stack).

    Pure function over (db, project, intent) — the answer path passes the
    replay_intent (caption_mode already stamped) and the project, and gets
    back the same reasons the original dock would have. Registry-native
    checks; no parallel tool lists.
    """
    reasons: list[str] = []
    if not intent.tasks_explicit:
        reasons.append("chain_default")
    clips_task = next((t for t in intent.tasks if t.tool == "select_clips"), None)
    if clips_task is not None and (clips_task.params or {}).get("count") is None:
        reasons.append("clip_count_default")
    has_media = await has_renderable_media(db, UUID(str(project.id)))
    if not has_media and any(_needs_media(t.tool) for t in intent.tasks):
        reasons.append("clips_without_media")
    has_text_tribe = any(
        isinstance(NODE_KINDS.get(t.tool), DerivativeWriterNode)
        for t in intent.tasks
    )
    if has_text_tribe and not await has_any_text_material(
        db, UUID(str(project.id))
    ):
        reasons.append("text_without_material")
    return reasons


def _needs_media(tool: str) -> bool:
    """True iff a tool's node requires MEDIA or materializes source.

    Hoisted out of _plan_turn (2026-08-25) so the answer path's
    ``_compute_book_reasons`` and the plan path's carve-out can both
    call it. Registry-native: walks ``node.requires`` + ``node.after``
    rather than maintaining a parallel tool list (RECIPES §4.6).
    """
    node = NODE_KINDS.get(tool)
    if node is None:
        return False
    return any(r.key == MEDIA.key for r in node.requires) or (
        "materialize_source" in (node.after or ())
    )


def _run_active_text(text: str) -> str:
    """The active-run plain line (shared by the chat dispatch's degrade and
    the plan surface's late-turn zombie-dock guard)."""
    return (
        "上一批还在生成中——完成后再安排新的。"
        if _prefers_zh(text)
        else "A batch is still generating — once it finishes, send the next one."
    )


async def _active_run_line(
    db: AsyncSession, project: Project, text: str
) -> str | None:
    """Late-turn guard: return the active-run line when a concurrent Start
    birthed a run while this turn was in flight — None means the coast is
    clear. Deliberately lock-free: locking the project row here would invert
    the Start path's Message→Project lock order (deadlock). The millisecond
    check-then-dock window this leaves is backstopped by create_run's own
    serialized guard — a zombie book confirmed later gets the clean
    RunAlreadyActiveError 422, never a second run."""
    from app.pipeline.orchestrator import has_active_run  # deferred: import cycle

    if await has_active_run(db, project.id):
        return _run_active_text(text)
    return None


def _cannot_do_text(text: str) -> str:
    """The refusal line (both intent surfaces). Human capability words only —
    registry tool names are internal vocabulary, never user-facing
    (2026-08-20 review: the null-params incident had ~50% of recipe launches
    reading this line in English with tool slugs in it)."""
    if _prefers_zh(text):
        return (
            "这个我现在还做不了。可以点名想要什么——"
            "比如竖屏短片、帖子、金句卡，或者另一个语言的版本。"
        )
    return (
        "I can't do that yet. Try naming what you want — like vertical "
        "clips, a post, quote cards, or a version in another language."
    )


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

    A superseded interrupt question (kind=choice carrying workflow_run_id)
    can never be answered through the dock anymore — cascade-bail its parked
    run in the same stroke (node done, downstream skipped), so the single-
    pending invariant never strands a run. Returns the bailed run ids; the
    caller finalizes them after its commit. Flush-only.
    """
    from app.pipeline.orchestrator import bail_waiting_interrupt

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
        if await bail_waiting_interrupt(db, run) is not None:
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
    interrupt was cascade-bailed by the supersede (finalized by the caller
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


def _task_chain_digest(tasks: list) -> str:
    """The chain's compact digest — fed to the PlanAgent as the presented
    plan (it revises the WHOLE chain, so it must see every task + param) and
    used as the summary fallback when no derived preview exists."""
    labels = []
    for task in tasks:
        params = task.params if isinstance(task.params, dict) else {}
        label = task.tool
        chips = []
        lang = params.get("language") or params.get("target_language")
        if lang:
            chips.append(str(lang))
        if params.get("count") is not None:
            chips.append(f"×{params['count']}")
        if params.get("bilingual"):
            chips.append("bilingual")
        if params.get("aspect"):
            chips.append(str(params["aspect"]))
        if chips:
            label += "(" + ", ".join(chips) + ")"
        labels.append(label)
    return ", ".join(labels)


def _task_book_summary(derived: list[dict], tasks: list) -> str:
    """One-line plan digest stored as the question's human text (data, not
    copy — localization happens at render time). The derived preview is the
    primary source (what the user will GET, ADR-043); the raw chain is the
    fallback when no preview was computed."""
    labels = []
    for row in derived:
        label = str(row.get("type") or "")
        if row.get("variant"):
            label += f"·{row['variant']}"
        if row.get("language"):
            label += f"({row['language']})"
        if row.get("count"):
            label += f" ×{row['count']}"
        if row.get("bilingual"):
            label += " bilingual"
        if label:
            labels.append(label)
    return ", ".join(labels) if labels else _task_chain_digest(tasks)


async def sync_task_book_question(
    db: AsyncSession,
    user_id: UUID,
    project: Project,
    intent: InferredIntent,
    prompt: str,
    reasons: list[str] | None = None,
    derived: list[dict] | None = None,
) -> list[UUID]:
    """Keep exactly one pending task_book question per project conversation.

    Called by the chat plan path on every inference (first call and
    refinements alike): a fresh conversation first archives the original
    prompt, any still-open plan question is retired as superseded, and the
    new task book becomes the pending question. The needs_clarification
    ``reasons`` ride in the question's human text (data, localized at render)
    so the archive and the LLM context record WHY confirmation was asked.
    Returns the run ids whose parked interrupt was cascade-bailed by the
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

    content = f"Plan ready for confirmation: {_task_book_summary(derived or [], intent.tasks)}"
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


async def dock_interrupt_question(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    run_id: UUID,
    content: str,
    payload: AskPayload,
) -> tuple[Message, list[UUID]]:
    """Dock the direction interrupt's question (期 4, raised by the node
    runner). ``workflow_run_id`` is the dispatch marker: the answer endpoint
    recognizes a interrupt question by it and resumes the parked run
    (answer = resume). The single-pending invariant still applies — docking
    supersedes any open question, and a superseded parked interrupt is
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
    question (retries, targeted runs, direct API callers — the overlay's own
    Start always goes through ``answer_question``). No QA interaction
    happened, so the archive must not carry a fabricated Q/A pair — the
    question row is deleted outright. Genuine confirmations (the dock's
    Start button, a prose "looks good, start it") go through
    ``answer_question`` and still archive their QA pair.
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
    A choice question carrying ``workflow_run_id`` is a direction interrupt
    (期 4): the answer wakes the parked run (spec.answer → node back to
    pending → run back to RUNNING); bail settles the node done, cascade-
    skips the downstream, and the run completes — never failed.
    """
    from app.pipeline.orchestrator import (
        TaskSpec,
        bail_waiting_interrupt,
        create_run,
        first_task_language,
        resume_waiting_interrupt,
    )

    # Row lock to the request boundary: a double-clicked Start (or retry)
    # otherwise passes the answer-is-None check concurrently and births two
    # paid runs off one task book. The second waiter re-reads post-commit and
    # hits the 409 below.
    message = await db.get(Message, message_id, with_for_update=True)
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

    # Caption-mode fast path (Phase 1, 2026-08-25, RECIPES §4.7): the question
    # is one of ours when every option_id starts with ``caption_mode_``. The
    # user picked a mode, so we re-stitch the stashed intent (a TaskListProposal
    # from _propose_turn, or a bare InferredIntent from _plan_turn's first
    # turn) into an InferredIntent + PendingIntent and dock a task_book
    # question — the user then confirms with Start like any normal generation.
    # Skipping _propose_turn here is intentional: the LLM would re-derive the
    # task list from the option label alone, which is the brittle 续聊 path.
    if (
        question.kind == "choice"
        and data.kind in ("option", "freeform")
        and _is_caption_mode_question(question)
        and message.intent is not None
        and isinstance(message.intent, dict)
    ):
        recovered_mode = _recover_caption_mode_from_answer(message)
        if recovered_mode is not None:
            stashed_intent = _replay_stashed_caption_intent(message)
            if stashed_intent is not None:
                project = await db.get(Project, conversation.project_id)
                if project is not None:
                    # Pull the original user prompt out of the conversation's
                    # first user message — the stashed intent carries only
                    # the structural chain, the prompt text is in the
                    # conversation timeline.
                    prompt_text = await get_project_prompt(
                        db, UUID(str(project.id))
                    ) or ""
                    # The stashed InferredIntent already carries tasks +
                    # specific_instruction (from the plan path) — keep them
                    # verbatim, just stamp caption_mode. The chat path
                    # stashed a TaskListProposal (no specific_instruction) —
                    # synthesize one from the prompt so the downstream
                    # text-tribe agents see the user's intent. caption_mode
                    # itself rides the structured field end-to-end
                    # (intent → PendingIntent → TaskSpec → run.context) —
                    # no machine marker in the prose.
                    if stashed_intent.specific_instruction:
                        replay_intent = stashed_intent.model_copy(
                            update={"caption_mode": recovered_mode}
                        )
                    else:
                        replay_intent = stashed_intent.model_copy(
                            update={
                                "specific_instruction": prompt_text or None,
                                "caption_mode": recovered_mode,
                            }
                        )
                    project.pending_intent = PendingIntent(
                        prompt=prompt_text,
                        intent=replay_intent,
                        reasons=await _compute_book_reasons(db, project, replay_intent),
                        persona_id=(
                            project.pending_intent.get("persona_id")
                            if isinstance(project.pending_intent, dict)
                            else None
                        ),
                        derived=[],
                    ).model_dump(mode="json")
                    # sync_task_book_question docks a task_book question; its
                    # bailed_run_ids are the cascade-bailed run interrupts (none
                    # here, but the contract is the same).
                    bailed_run_ids = await sync_task_book_question(
                        db, user_id, project, replay_intent, prompt_text,
                        reasons=project.pending_intent["reasons"],
                    )
                    follow_up = await latest_pending_question(db, UUID(str(conversation.id)))
                    # Skip the 续聊 fallback below — the task book question is
                    # the follow_up, no need to re-propose.
                    await db.commit()
                    if bailed_run_ids:
                        await finalize_bailed_runs(bailed_run_ids)
                    await db.refresh(message)
                    if follow_up is not None:
                        await db.refresh(follow_up)
                    return message, follow_up

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
            # The review panel's edited task book wins over the stored
            # pending intent — panel edits must reach the run they confirm.
            # Panel edits ARE task-list mutations (ADR-043): the same data
            # structure the LLM proposes, so the confirmed chain ships
            # verbatim — no merge machinery.
            intent = data.intent or pending.intent
            # caption_mode is intent metadata the review panel never edits —
            # a panel-submitted intent without it (client-side normalize may
            # strip fields it doesn't know) says "not mentioned", never
            # "retracted". Inherit the answered mode from the stored pending
            # intent (2026-08-29 — the same doctrine as the plan-turn
            # overwrite fix; without it, answer→Start via the PANEL dropped
            # the mode even though answer→Start via prose kept it).
            if (
                intent.caption_mode is None
                and pending.intent.caption_mode is not None
            ):
                intent = intent.model_copy(
                    update={"caption_mode": pending.intent.caption_mode}
                )
            tasks = list(intent.tasks)
            if not tasks:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "The task book is empty — nothing to start.",
                )
            try:
                # Entry constraints (clips-media gate included) reject at the
                # birthplace — ValueError here is a client-facing 422.
                # target_language is a pure fallback (language is a per-task
                # param): derive it from the first task that carries one.
                run = await create_run(
                    db,
                    project,
                    TaskSpec(
                        tasks=tasks,
                        target_language=(
                            first_task_language(tasks)
                            or project.language
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
                        autonomy=data.autonomy or "auto",
                        scope="full",
                        # Caption mode rides the run context verbatim from
                        # the InferredIntent — the chat path's caption-mode
                        # question stores it on the intent (RECIPES §4.7).
                        caption_mode=intent.caption_mode,
                    ),
                )
            except ToolRejected as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
                ) from exc
            project.status = ProjectStatus.PROCESSING
            # The task book is confirmed now — drop the unconfirmed copy.
            project.pending_intent = None
            message.workflow_run_id = run.id

    elif question.kind == "choice" and message.workflow_run_id is not None:
        # Direction interrupt (期 4): workflow_run_id is the dispatch
        # marker. The answer resumes the parked run — spec.answer written,
        # node back to pending, run back to RUNNING, the worker re-executes
        # the thin node. Bail is a graceful exit: node done (spec.bailed),
        # downstream cascade-skipped, run settles COMPLETED — never failed.
        run = await db.get(WorkflowRun, message.workflow_run_id)
        if run is not None:
            if data.kind == "bail":
                if await bail_waiting_interrupt(db, run) is not None:
                    bailed_run_ids.append(UUID(str(run.id)))
            else:
                await resume_waiting_interrupt(db, run, message.answer)

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
        # Bailed interrupts settle COMPLETED (never FAILED, #5); each
        # aggregated summary carries the interrupt's "Bailed by user" line
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

    - generate → three-way merge (panel prior / fresh inference) + reasons +
      dock the (refined) task book
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
    if len(prompt) > MAX_ACCUM_PROMPT_CHARS:
        # Long refinement histories: keep the original intent (head) and the
        # newest refinements (tail) — middle prose yields. Nothing is lost
        # for planning: accepted revisions are merged into the book's slots
        # (merge_prior_slots), the prompt is only the intent's narrative.
        prompt = (
            prompt[: MAX_ACCUM_PROMPT_CHARS // 2].rstrip()
            + "\n…\n"
            + prompt[-MAX_ACCUM_PROMPT_CHARS // 2 :].lstrip()
        )

    assets = list(
        (
            await db.execute(
                select(Asset)
                .where(
                    Asset.project_id == project.id,
                    Asset.file_url.isnot(None),
                )
                # Deterministic "first asset" for filename/excerpt picks —
                # the repo convention (jobs.py / projects.py).
                .order_by(Asset.created_at)
            )
        )
        .scalars()
        .all()
    )
    first_file = next((a for a in assets if a.file_url), None)
    filename = first_file.file_url.rsplit("/", 1)[-1] if first_file else None
    # The plan layer reads the material's opening, not just its filename
    # (track-model §7.4 折中版 — mechanical slice, zero extra LLM): the first
    # asset carrying text (transcript beats extracted_text), capped.
    material_excerpt = next(
        (
            excerpt
            for a in assets
            if (excerpt := (a.transcript or a.extracted_text or "").strip())
        ),
        None,
    )
    if material_excerpt:
        material_excerpt = material_excerpt[:800]

    # plan_agent provider failures propagate as MiniMaxError — no fabricated
    # default book (2026-08-14 裁定: a wrong plan that looks real misleads,
    # and Start would spend a paid run on it); the route boundary turns it
    # into a 502 with the localized provider line. The presented plan rides
    # along so the
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
    # The presented chain (ADR-043): the panel's current task list when the
    # caller sends one (hand edits ride along), else the stored book's. The
    # PlanAgent sees it as a JSON chain and re-emits the WHOLE refined chain
    # — panel edits survive because the LLM preserves what the message does
    # not revise (chat revisions always win; the field-level merge machinery
    # died with the slots grammar).
    prior = request.prior_intent or (stored.intent if stored else None)
    # The LLM revises the exact chain, not a prose digest — ship the JSON.
    presented_plan = (
        json.dumps([t.model_dump(mode="json") for t in prior.tasks], ensure_ascii=False)
        if prior is not None and prior.tasks
        else None
    )
    infer_kwargs: dict[str, Any] = dict(
        prompt=prompt,
        filename=filename,
        presented_plan=presented_plan,
        recent=recent_lines or None,
        # The transform-target rule's authoritative signal (同源语言护栏 —
        # the plan surface's only other language hint is the filename).
        file_language=(first_file.meta or {}).get("language") if first_file else None,
        material_excerpt=material_excerpt,
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
    # 2026-08-24 lift carve-out: when the chain is copy-writers alone
    # (write_post / write_quotes / write_carousel / write_article) the
    # draft comes from prompt + persona style, no material gate. Letting
    # the book dock with the `text_without_material` reason (computed
    # below from ``has_any_text_material``) is the designed soft signal —
    # NOT a blocker. Mixed chains (writers + media-needing) are still
    # defended here because the LLM is supposed to drop the media-needing
    # rows in EXCEPTION 2; if it doesn't, this guard catches it.
    # The "ask for material" backstop (RECIPES §4.6 S13 regression guard) is
    # two-pronged:
    #  1. A chain that mixes media-needing tasks with no attached file → ask
    #     for material (clips / dub / subtitle work can't run without a source).
    #  2. A vague, EXPLICITLY default proposal with no material → ask for
    #     clarification ("what product exactly?").
    # But the LLM's `tasks_explicit` flag is brittle: prompts like "make a
    # quote card" or "write a post about leadership" name a specific recipe
    # yet the LLM often defaults to `tasks_explicit=False`, which would
    # short-circuit the no-material copy-writer lift. The carve-out: a
    # PURE copy-writer chain (no media-needing task in the list) skips the
    # `tasks_explicit` gate — the lift's own check downstream lets the
    # copy-writer draft from prompt + persona style without source material.
    def _zero_material_net(verdict: InferredIntent) -> bool:
        """True when the zero-material safety net must downgrade this generate
        verdict to an ask-for-material answer.

        Recomputed from the verdict's CURRENT task list — the misfire flips
        below (answer-misfire, start-misfire) re-apply the net AFTER the
        chain-adjudication repair may have swapped ``intent.tasks``, so
        pre-computed flags would judge the wrong chain (2026-08-28: the
        answer-misfire flip let a clips×3 book dock with zero material —
        S13 red; the flags must follow the chain being docked)."""
        media_task = any(_needs_media(t.tool) for t in verdict.tasks)
        only_writers = bool(verdict.tasks) and not media_task
        return (
            not assets
            and material_asset is None
            and (
                media_task
                or (not verdict.tasks_explicit and not only_writers)
            )
        )

    if intent.action == "generate" and stored is None and _zero_material_net(intent):
        intent.action = "answer"
        intent.answer = _ask_for_material_text(prompt)

    # Chain adjudication (ADR-043): the registry validates the proposed task
    # list — one bounded repair round on rejection (the funnel's reserved
    # kwarg), then degrade to an answer, never a docked broken book.
    if intent.action == "generate":
        try:
            validate_task_list(intent.tasks)
            if not intent.tasks:
                raise ToolRejected("empty task list")
        except ToolRejected as first_error:
            repaired_intent: InferredIntent | None = None
            try:
                retry = await plan_agent.call(
                    **infer_kwargs,
                    repair_feedback=(
                        f"{first_error} "
                        f"(available: {getattr(first_error, 'suggestions', [])})"
                    ),
                )
                validate_task_list(retry.tasks)
                if retry.tasks:
                    repaired_intent = retry
            except (ToolRejected, MiniMaxError):
                pass
            if repaired_intent is not None:
                intent = repaired_intent
            else:
                # The degrade says "can't do that" — log what was actually
                # proposed and why it was rejected, or the refusal class is
                # invisible (2026-08-19: recipe-template launches died here).
                logger.info(
                    "plan_chain_rejected",
                    error=str(first_error),
                    proposed=[t.tool for t in intent.tasks],
                    repair="failed",
                )
                intent.action = "answer"
                intent.answer = _cannot_do_text(prompt)

    reasons = await _compute_book_reasons(db, project, intent)

    # An answer action without answer text is an LLM misfire — degrade to a
    # plan turn (dock the book for confirmation) when a chain exists, else
    # answer with the capability line; never clobber the stored task book
    # with an empty answer or dock an empty chain.
    if intent.action == "answer" and not intent.answer:
        if intent.tasks:
            intent.action = "generate"
            # The zero-material net re-applies verbatim (S13, 2026-08-28):
            # the net above ran while the action was still "answer" and
            # skipped this verdict — without the re-check, an answer-misfire
            # carrying a media-needing chain docks a groundless book with
            # zero material (the exact hole the start-misfire branch below
            # already closes; this is the missed sibling).
            if stored is None and _zero_material_net(intent):
                intent.action = "answer"
                intent.answer = _ask_for_material_text(prompt)
        else:
            intent.answer = _cannot_do_text(prompt)

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
                # The review panel's edited book rides along (typed Start
                # parity): dropping prior_intent here would execute the
                # stored chain and silently discard the user's panel edits.
                StartAnswerRequest(
                    kind="start",
                    autonomy=request.autonomy,
                    intent=request.prior_intent,
                ),
            )
            # answer_question commits — the run, the answer and the cleared
            # pending intent land in one transaction.
            return answered, UUID(str(answered.workflow_run_id)), answered, []
        if stored is not None:
            # Nothing startable right now. Never overwrite a stored task book
            # with a start-action misfire's fields: re-dock the stored book
            # unchanged. Unless a run started concurrently — then the plan is
            # moot and re-docking would raise a book over an active run.
            active_line = await _active_run_line(db, project, text)
            if active_line is not None:
                assistant_message = await _create_message(
                    db, conversation_id, "assistant", active_line
                )
                return assistant_message, None, None, []
            bailed_run_ids = await sync_task_book_question(
                db, user_id, project, stored.intent, stored.prompt,
                reasons=stored.reasons, derived=stored.derived,
            )
            question = await latest_pending_question(db, conversation_id)
            assert question is not None  # sync_task_book_question just docked it
            return question, None, None, bailed_run_ids
        # Start-misfire → treat the turn as a fresh generate verdict: the
        # zero-material safety net re-applies verbatim (the net above ran
        # while the action was still "start" and skipped it). Without this
        # a "start" verdict for a media-needing chain with nothing attached
        # would dock a groundless book — the exact hole the net exists to
        # close (D8, 2026-08-27).
        intent.action = "generate"
        if _zero_material_net(intent):
            intent.action = "answer"
            intent.answer = _ask_for_material_text(prompt)

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

    # Derived preview (ADR-043): dry-run the chain through compile_graph and
    # project what it will make — the plan card's "you'll get" section. A
    # chain that can't compile here (e.g. transform with no media anywhere)
    # still docks, flagged by its reason — the birthplace rejects for real.
    from app.pipeline.orchestrator import derive_plan_preview

    try:
        derived = await derive_plan_preview(db, project, intent.tasks)
    except (ToolRejected, ValueError):
        derived = []

    # Persist the unconfirmed task book on the project: leaving the chat and
    # coming back (any device) restores this exact plan. Cleared once the run
    # starts. The dock above the input rebuilds from the task_book question.
    # But first the late-turn guard: a concurrent Start committed while this
    # refine was in flight — docking now would raise a task book over an
    # active run (the zombie dock). Degrade to the active-run line.
    active_line = await _active_run_line(db, project, text)
    if active_line is not None:
        assistant_message = await _create_message(
            db, conversation_id, "assistant", active_line
        )
        return assistant_message, None, None, []
    # Caption mode for captioned-video runs (Phase 1 plan-path fix,
    # 2026-08-25, RECIPES §4.7): the plan_path is the FIRST-turn entry
    # point for fresh projects — the chat path's elif alone leaves the very
    # first "make a quote card" prompt to dock a task_book without ever
    # asking which caption mode the user wants. Mirror the chat path's
    # three escape hatches (LLM-set / keyword / prior answer) and dock a
    # caption_mode choice before the task_book; the bare InferredIntent
    # rides the question's `intent` field, the answer path replays it
    # verbatim back into PendingIntent (chat_path stashes a TaskListProposal,
    # plan_path stashes an InferredIntent — both shapes handled).
    if (
        intent.action == "generate"
        and _needs_caption_mode_question(intent.tasks)
        and intent.caption_mode is None
        and _detect_caption_mode(text) is None
        and _detect_caption_mode(intent.specific_instruction or "") is None
        and not _has_resolved_caption_mode(project)
    ):
        if await _caption_choice_is_meaningful(db, project, intent.tasks):
            caption_question = _build_caption_mode_question(text)
            stashed_intent = intent.model_dump(mode="json")
            assistant_message, bailed_run_ids = await _dock_question(
                db,
                conversation_id,
                caption_question.question,
                AskPayload(
                    kind="choice",
                    options=caption_question.options,
                    allow_freeform=caption_question.allow_freeform,
                ),
                intent=stashed_intent,
            )
            return assistant_message, None, None, bailed_run_ids
        # §2.3/D4 (2026-08-28): no distinct alt language exists (the source
        # material's language equals every candidate) — bilingual would
        # print one language twice. Skip the question entirely and stamp
        # source_only; the run falls through to the task-book dock.
        intent = intent.model_copy(update={"caption_mode": "source_only"})
    # Caption-mode keyword auto-classification (Phase 1 plan-path fix,
    # 2026-08-25, RECIPES §4.7): when the user prompt carries an
    # unambiguous bilingual keyword ("双语" / "bilingual" / "中英对照" /
    # "双语字幕" / "中英双语"), stamp intent.caption_mode="bilingual" so
    # the run lands with the right value even when the LLM didn't set it.
    # Source / target-only keywords stay null here — they're ambiguous
    # without knowing the source language, the chat question handles them.
    keyword_mode = _detect_caption_mode(text)
    if keyword_mode is not None and intent.caption_mode is None:
        intent = intent.model_copy(update={"caption_mode": keyword_mode})
    # Inherit the answered caption mode before the overwrite below
    # (2026-08-29 追问丢答 root-fix): this write replaces the stored
    # pending_intent wholesale, and the fresh verdict's caption_mode is
    # None on any refinement turn that doesn't re-mention it — without
    # the inherit, "answer bilingual → 改成 5 张 → Start" landed a run
    # with no caption_mode (single-language cards) and the NEXT turn
    # re-asked the already-answered question. Precedence: fresh LLM-set
    # > fresh keyword > stashed answer.
    if intent.caption_mode is None:
        stashed_mode = _resolved_caption_mode(project)
        if stashed_mode is not None:
            intent = intent.model_copy(update={"caption_mode": stashed_mode})
    project.pending_intent = PendingIntent(
        prompt=prompt,
        intent=intent,
        reasons=reasons,
        persona_id=persona_id,
        derived=derived,
    ).model_dump(mode="json")
    bailed_run_ids = await sync_task_book_question(
        db, user_id, project, intent, prompt, reasons=reasons, derived=derived
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
    focus_output_id: UUID | None = None,
    on_delta=None,
    on_reasoning=None,
) -> tuple[Message, UUID | None, list[UUID]]:
    """One assistant turn after the user input is settled (CHAT_ARCH §3):
    assemble context, single intent call, adjudicate, record the reply.

    Shared by ``chat()`` and the choice-answer continuation in
    ``answer_question`` (the answer endpoint doubles as resume). Returns the
    assistant message, the dispatched run id if any, and the run ids whose
    parked interrupt was cascade-bailed when a new docked question
    superseded it (finalized by the caller after its commit). Flush-only —
    the caller commits.
    """
    conversation_id = UUID(str(conversation.id))
    context = (
        await _build_context(
            db,
            project,
            recent,
            mentions,
            await latest_pending_question(db, conversation_id),
            focus_output_id,
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
        # LLM failure: ask back — the only failure form (prohibition #7;
        # the asset-scope revise_script guess retired with the scope itself).
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
                        db, project, retry.proposal.tasks, retry.proposal.summary,
                        # A repaired task_list is the same run birth — the
                        # caption mode rides the shared funnel (2026-08-29).
                        caption_mode=await _derive_chat_caption_mode(
                            db, project, retry.proposal.tasks, text
                        ),
                    )
                    proposal = retry.proposal
                    assistant_content = retry.proposal.summary
                    repaired = True
            except (OpRejected, ToolRejected, ValueError, MiniMaxError):
                pass
            if not repaired:
                proposal = None
                assistant_content = _cannot_do_text(text)
        if isinstance(proposal, EditOpsProposal):
            # Mentions forward client-pinned ids verbatim (MENTIONS §35) —
            # authorize before any write: the target must be an output of
            # THIS project. Every other write path (editor routes / revise /
            # render / derivative targets) re-checks ownership at execution;
            # the chat surface's only write had none (cross-tenant IDOR).
            target = await db.get(Output, proposal.target_output_id)
            if (
                project is None
                or target is None
                or UUID(str(target.project_id)) != UUID(str(project.id))
            ):
                proposal = None
                assistant_content = _cannot_do_text(text)
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
            except (OpRejected, OpConflict):
                assistant_message.content = _cannot_do_text(text)
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
    elif (
        # Caption mode for captioned-video runs (Phase 1, 2026-08-25, RECIPES
        # §4.7): when the chain asks for a quote card and the user didn't name
        # a caption mode, dock the bilingual/source/target choice BEFORE
        # letting the run start — the answer rides run.context.caption_mode
        # downstream (write_quotes Phase 2 reads it, Remotion Phase 3 layouts
        # off it). Escape hatches on THIS path: the user prompt carries an
        # unambiguous keyword, or the stored pending_intent already locked
        # the choice from an earlier answer (so a follow-up refinement turn
        # doesn't re-ask). The plan path's third hatch (LLM-set caption_mode
        # on InferredIntent) does not exist here — TaskListProposal carries
        # no intent, the chat intent agent has no caption_mode field to set.
        # (2026-08-29 root-fix: this condition previously READ
        # ``proposal.intent.*`` — a field that has never existed on
        # TaskListProposal — so every write_quotes chat proposal 500'd
        # before the question could dock.)
        isinstance(proposal, TaskListProposal)
        and _needs_caption_mode_question(proposal.tasks)
        and _detect_caption_mode(text) is None
        and not _has_resolved_caption_mode(project)
        and await _caption_choice_is_meaningful(db, project, proposal.tasks)
    ):
        caption_question = _build_caption_mode_question(text)
        # The original TaskListProposal's dump is stashed on the docked
        # question's `intent` field — the answer path replays it once the
        # user picks a mode, rather than re-running the plan agent (the plan
        # would otherwise re-enter the question-dock loop). The intent we
        # replay is a `TaskListProposal`-shaped dict (not an InferredIntent):
        # the resume code path below knows to convert it into an
        # InferredIntent + PendingIntent + task_book dock.
        stashed_proposal = proposal.model_dump(mode="json")
        assistant_message, bailed_run_ids = await _dock_question(
            db,
            conversation_id,
            caption_question.question,
            AskPayload(
                kind="choice",
                options=caption_question.options,
                allow_freeform=caption_question.allow_freeform,
            ),
            intent=stashed_proposal,
        )
    else:
        # Caption-mode resolution for the immediate run (2026-08-29
        # root-fix): the chat path's proposal carries no intent — the mode
        # is derived here and rides TaskSpec.caption_mode → run.context
        # end-to-end. The derivation lives in _derive_chat_caption_mode
        # (keyword > stashed answer > source_only-if-no-distinct-alt) so
        # the main dispatch and the repair re-dispatches share one funnel.
        # (Replaces two blocks that READ ``proposal.intent.*`` — a field
        # that never existed on TaskListProposal: the §2.3/D4 narrowing was
        # unreachable dead code, and the keyword block 500'd on ANY
        # task_list proposal carrying a bilingual keyword.)
        caption_mode: str | None = None
        if isinstance(proposal, TaskListProposal):
            caption_mode = await _derive_chat_caption_mode(
                db, project, proposal.tasks, text
            )
        try:
            run_id = await _create_run_from_tasks(
                db, project, proposal.tasks, proposal.summary,
                caption_mode=caption_mode,
            )
            assistant_content = proposal.summary
        except ValueError as e:
            from app.pipeline.orchestrator import (  # deferred: import cycle
                RunAlreadyActiveError,
            )

            if isinstance(e, RunAlreadyActiveError):
                # Active-run guard fired — say THAT, not the missing-material
                # line (the guard's own 422 copy rides the typed endpoints).
                assistant_content = _run_active_text(text)
            else:
                # Missing required input (media/transcript/…) — no repair round
                # can fix that. The raw exception carries registry vocabulary;
                # it goes to the log, the user gets a plain line in their
                # language (same posture as _cannot_do_text, 2026-08-20).
                logger.info("run_birth_missing_input", error=str(e))
                assistant_content = (
                    "还缺素材——先发我视频、音频或文字稿，我再开工。"
                    if _prefers_zh(text)
                    else "I'm missing the material for that — attach a video, "
                    "audio, or transcript first, then I'll get to work."
                )
        except ToolRejected as first_error:
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
                        db, project, retry.proposal.tasks, retry.proposal.summary,
                        # A repaired task_list is the same run birth — the
                        # caption mode rides the shared funnel (2026-08-29).
                        caption_mode=await _derive_chat_caption_mode(
                            db, project, retry.proposal.tasks, text
                        ),
                    )
                    proposal = retry.proposal
                    assistant_content = retry.proposal.summary
                    repaired = True
            except (ToolRejected, ValueError, MiniMaxError):
                pass
            if not repaired:
                proposal = None
                assistant_content = _cannot_do_text(text)

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
    interrupt-resume reply when the turn needs no LLM at all, and the
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
    interrupt_reply: Message | None
    plan_path: bool


async def prepare_chat_turn(
    db: AsyncSession,
    user_id: UUID,
    request: ChatRequest,
) -> PreparedTurn:
    """chat() phase 1: settle everything up to the dispatch decision."""
    # Entry caps (2026-08-20 ruling): the chat box is for talk, not bulk
    # payload — long documents belong in file uploads. Beyond the caps the
    # turn would only fail deeper (LLM context, DB row size), so reject at
    # the door with a friendly pointer. Language follows the turn's text.
    zh = _prefers_zh(request.message)
    if len(request.message) > MAX_MESSAGE_CHARS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "内容太长了——长文稿请作为文件上传，对话里放不下。"
            if zh
            else "That's too much for the chat box — upload long documents as files instead.",
        )
    if len(request.attachments) > MAX_ATTACHMENTS_PER_TURN:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"一次最多带 {MAX_ATTACHMENTS_PER_TURN} 个附件。"
            if zh
            else f"At most {MAX_ATTACHMENTS_PER_TURN} attachments per message.",
        )
    if len(request.mentions) > MAX_MENTIONS_PER_TURN:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"一条消息最多 @ {MAX_MENTIONS_PER_TURN} 个引用。"
            if zh
            else f"At most {MAX_MENTIONS_PER_TURN} @-mentions per message.",
        )

    conversation = await _get_or_create_project_conversation(
        db, user_id, request.project_id
    )
    conversation_id = UUID(str(conversation.id))

    user_message = await _create_message(
        db,
        conversation_id,
        "user",
        request.message,
        attachments=[a.model_dump(mode="json") for a in request.attachments],
        mentions=[m.model_dump(mode="json") for m in request.mentions],
        focus_output=(
            request.focus_output.model_dump(mode="json") if request.focus_output else None
        ),
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
                # A blank attachment-only turn never answers a interrupt —
                # the files ride the intent paths below instead.
                pending.answer = AnswerPayload(
                    kind="freeform",
                    text=request.message,
                    answered_at=datetime.now(UTC),
                ).model_dump(mode="json")
                answered_question = pending
            await db.flush()

    interrupt_reply: Message | None = None
    plan_path = False
    if answered_question is not None and answered_question.workflow_run_id is not None:
        # Interrupt autoResume (期 4): a typed answer to the docked direction
        # question takes the same dispatch as the answer endpoint — wake the
        # parked run. No LLM turn on top: the wake IS the continuation (the
        # step flow shows the run resuming), so the acknowledgment is a
        # deterministic line.
        from app.pipeline.orchestrator import resume_waiting_interrupt

        run = await db.get(WorkflowRun, answered_question.workflow_run_id)
        if run is not None:
            await resume_waiting_interrupt(db, run, answered_question.answer)
        decided = (answered_question.answer or {}).get("text") or (
            answered_question.answer or {}
        ).get("option_id") or ""
        # Deterministic acknowledgment — display language follows the
        # request's UI locale (the option label is already localized).
        from app.ui_locale import current_ui_language

        interrupt_reply = await _create_message(
            db,
            conversation_id,
            "assistant",
            f"方向已锁定：{decided}。继续生成。"
            if (current_ui_language() or "").startswith("zh")
            else f"Direction locked: {decided}. Resuming the run.",
        )
    else:
        # Plan path dispatch (intent-surface-unification W1): this endpoint is
        # the ONLY intent surface. A turn goes to the plan path (task-book
        # build / refine / confirm via the PlanAgent) while a task book is
        # pending or before the project's first run; everything else goes to
        # the four-state proposer. (Conversations are project-scope only —
        # ADR-041 D8.)
        if project is not None:
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
        interrupt_reply=interrupt_reply,
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
    if prepared.interrupt_reply is not None:
        assistant_message = prepared.interrupt_reply
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
            focus_output_id=(request.focus_output.id if request.focus_output else None),
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
) -> Conversation | None:
    """Return the project's chat conversation, or None. (Conversations are
    project-scope only — the asset scope is retired, ADR-041 D8.)"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.project_id == project_id,
            Conversation.asset_id.is_(None),
        )
    )
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
