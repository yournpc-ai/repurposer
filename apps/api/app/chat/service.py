"""Generic chat service.

A conversation is the universal container — always project-scoped (the
original prompt plus project-level follow-ups). Asset-scoped conversations
are retired (ADR-041 D8): product chat lives in the project conversation,
and the product the user points at rides the message as an @-mention chip
(ADR-058 — the focus_output transport is write-retired, old rows read back).

The public surface is intentionally tiny: ``chat()`` takes a user message,
locates or creates the right conversation, assembles deterministic context,
and lets the intent agent propose (CHAT_ARCH §3). It is the ONLY intent
surface (intent-surface-unification W1): project-scope turns before the
first run — or while a plan is pending — go through the plan path
(``_plan_turn``: build / refine / confirm the plan via the intent router);
everything else goes to the chat-path proposer (``_propose_turn``).

ADR-077 判词② (2026-09-14): both turns run the bounded tool loop — the
action union retired into the terminal tool set (type = tool name, fields =
params), the guardrails live inside the executions, and the loop itself is
side-effect-free (``app/chat/plan_turn.py`` / ``app/chat/propose_turn.py``;
the two names above are shims). The write doors never moved:

- propose_tasks / edit_graph → compile_graph via ``_create_run_from_tasks``
  (the ONLY run birthplace; wiring resolves through ``apply_wiring_ops`` first)
- ask_user                → a typed question docked above the input
- edit_output             → the precise edit (ADR-090; Final Hardening B1 —
                            the ONLY edit verb): one controlled registry op
                            journaled with message lineage, then re-render
- answer                  → a purely informational reply (capability /
                            progress / explanation / small talk) landing as a
                            plain assistant message — no run, no dock (G-4)

ask_user 机器 (the ask_user machinery): a message may carry a typed
``question`` payload; ``answer`` NULL = pending. Pending questions dock above
the input (QuestionDock); answered ones collapse into the flow as answered
questions. At
most one pending question per conversation — a newer question retires the
previous one (bail: superseded). While a question is pending, a
free-text message is mapped deterministically (autoResume, zero LLM): an
option letter/number/label hit answers with that option; otherwise
``allow_freeform`` records the text as a freeform answer; otherwise the text
is a new intent and the question stays pending.
"""

import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import TYPE_CHECKING, Any
from uuid import UUID


if TYPE_CHECKING:
    from app.pipeline.lifecycle import ConfirmationNeed

import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


# The two chat agents no longer take calls HERE (the turn runners —
# app/chat/plan_turn.py / propose_turn.py — drive them through the tool
# loop); importing the declarations module keeps them registered in AGENTS
# at startup (the orchestrator's roster self-check walks it).
from app.chat.intent import chat_intent_agent as _chat_intent_agent  # noqa: F401
from app.chat.intent import intent_router as _intent_router  # noqa: F401
from app.chat.suggestions import (
    build_suggestion_records,
    compose_suggestion_note,
    suggestion_stale_reasons,
)
from app.chat.turn_tools import strip_tool_echoes
from app.metering import bind_conversation_turn, fold_conversation_usage
from app.models.schemas import (
    AnswerPayload,
    AnswerRequest,
    AssetStatus,
    AssetType,
    Brief,
    BriefSlot,
    BriefSlotSource,
    ChatMention,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatTurnStopRequest,
    InferredIntent,
    Option,
    PendingPlan,
    PlanEstimate,
    ProjectStatus,
    QuestionPayload,
    QuestionProposal,
    SkillReference,
    StartAnswerRequest,
    SuggestionRef,
    TaskItem,
)
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    MessageSeqCounter,
    Project,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.asset_processing import has_renderable_media
from app.pipeline.graph import MEDIA, NODE_KINDS
from app.platform.billing import CreditsInsufficientError
from app.platform.configs import get_config
from app.platform.conversation_context import (
    find_conversation,
    is_pending_plan,
    latest_pending_question,
)
from app.platform.user_settings import read_confirmation_prefs
from app.tools import ToolRejected

logger = structlog.get_logger()

# Chat entry caps (2026-08-20 ruling) — enforced in prepare_chat_turn.
MAX_MESSAGE_CHARS = 20_000
MAX_ATTACHMENTS_PER_TURN = 5
MAX_MENTIONS_PER_TURN = 10


def _material_gate_text(text: str) -> str:
    """出书门槛·素材根 (ADR-052 B2 D2-C2): media-needing chain + brief
    material "none" + no plan on the table — the missing root is the material
    itself, so the reply asks for it and nothing docks (the retired
    zero-material net's S13 outcome, folded into the gate). Language follows
    the turn's text — the plan path's prose always speaks the user's language.
    """
    if _prefers_zh(text):
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


def _topic_gate_question(text: str) -> dict[str, str]:
    """出书门槛·主题问 (D2-C2): the code-composed ONE topic ask for a rootless
    draft call — the backstop for an LLM that drafted a bare wish. Freeform
    only (options=[] — 策略②'s one-word options are the LLM's to source from
    the persona / project context; code composes no fabricated choices)."""
    if _prefers_zh(text):
        return {
            "question": "想做什么主题？一个词或一句话就行——比如「面向初创创始人的领导力」。",
            "default_path": "跳过也可以——我会按你的人设风格先起草一版。",
        }
    return {
        "question": (
            "What topic should it be about? One word or phrase is enough — "
            "e.g. 'leadership for first-time founders'."
        ),
        "default_path": "Skip it and I'll draft in your persona's style first.",
    }


def _draft_from_persona_echo(text: str) -> str:
    """出书门槛·默认路径声明 (提问策略③ / 验收③): asked once and still
    rootless, the docked draft-from-persona plan's echo is code-composed —
    a code-forced dock never borrows the LLM's voice for the declaration."""
    if _prefers_zh(text):
        return (
            "我先按你的人设风格起草了这版——直接开始就行；"
            "想换主题，一句话告诉我。"
        )
    return (
        "I drafted this in your persona's style — start it as-is, or tell "
        "me the topic in one line and I'll re-angle it."
    )


def _bare_question(message: Message) -> str:
    """The question row's BARE question (ask 三分解剖 ②): the payload's
    ``question`` when the row carries one, else its content (legacy rows and
    prose-less questions store the bare question AS the content — read
    tolerance, same doctrine as the payload's other upgrades)."""
    return (message.question or {}).get("question") or message.content or ""


def _ask_content(ask: QuestionProposal, *, has_dock_options: bool = False) -> str:
    """The question row's content (ask 三分解剖 ①): the framing prose when
    the ask brings one. A TEXT ask (options/items empty — it never docks)
    keeps its bare question IN the speech; a docked ask keeps the title only
    in the payload."""
    prose = ask.prose.strip()
    if not prose:
        return ask.question
    if not ask.options and not has_dock_options:
        return f"{prose}\n\n{ask.question}"
    return prose


def _reminder_tail(text: str, question: str, default_path: str | None) -> str:
    """Build the interjection reminder's localized system-notice text."""
    if _prefers_zh(text):
        tail = f"\n\n（还在等你的回答：{question}"
        tail += f"——{default_path}）" if default_path else "——一句话就行）"
        return tail
    tail = f"\n\n(Still waiting for your answer: {question}"
    tail += f" — {default_path})" if default_path else " — one short line is enough)"
    return tail


def _system_notice(text: str) -> dict[str, str]:
    return {"kind": "system_notice", "text": text.strip()}


def _reminder_block(
    text: str, question: str, default_path: str | None
) -> dict[str, str]:
    return _system_notice(_reminder_tail(text, question, default_path))


def _auto_start_rejected_line(detail: dict[str, Any] | None) -> str:
    """Build the auto-start rejection's localized system-notice text.
    ``credits.insufficient`` names the two real numbers; every other 422
    gets the generic retry line. Language follows the request's UI locale."""
    from app.ui_locale import current_ui_language  # deferred: request ctx

    zh = (current_ui_language() or "").startswith("zh")
    if detail and detail.get("code") == "credits.insufficient":
        balance = detail.get("balance")
        required = detail.get("required")
        if balance is not None and required is not None:
            if zh:
                return (
                    f"\n\n（开工没有成功——积分不足：当前余额 {balance}，"
                    f"这个方案约需 {required}。计划保留在这里。）"
                )
            return (
                f"\n\n(The work couldn't start — not enough credits: your "
                f"balance is {balance}, this plan needs about {required}. "
                "The plan stays here.)"
            )
    if zh:
        return "\n\n（开工没有成功——计划保留在这里，再说一次「开始」即可重试。）"
    return (
        "\n\n(The work couldn't start — the plan stays here; "
        'say "start" to try again.)'
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
        # 新生标记 (ADR-108 §1 FK 取证): the row is flushed but UNCOMMITTED,
        # so alloc_message_seq's fresh-session upsert would violate the
        # counter's FK — route this session's allocations in-transaction.
        db.info.setdefault(_FRESH_CONVERSATIONS_INFO, set()).add(
            UUID(str(conversation.id))
        )
    return conversation


def _resume_ack_line(decided: str, outcome: str) -> str:
    """The direction-interrupt wake acknowledgment (期 4 + R1 B3 再挂+明示):
    ``resumed`` = the locked-direction line; ``blocked`` (another run holds
    the project's execution authority) = the honest parked line — the answer
    is saved, the run continues once the current generation finishes.
    Display language follows the request's UI locale (the option label is
    already localized). Shared by the answer endpoint, the chat autoResume,
    and the tool-loop disposition wake."""
    from app.ui_locale import current_ui_language  # deferred: request ctx

    zh = (current_ui_language() or "").startswith("zh")
    if outcome == "blocked":
        return (
            "你的回答已收到——等当前生成完成后，这条会继续。"
            if zh
            else "Got your answer — it will continue once the current generation finishes."
        )
    return (
        f"方向已锁定：{decided}。继续生成。"
        if zh
        else f"Direction locked: {decided}. Resuming the run."
    )


# interaction_policy_version 戳 (ADR-099 §7, 批次 C·C+ commit 2): every
# assistant row created through _create_message carries the interaction
# policy's version in its intent dump — observation & regression ONLY (the
# context assembler never reads intent into the model's surface, so the
# stamp stays invisible to the model). Bump when the interaction policy
# (constitution / form spectrum) changes.
# v2 (ADR-101): the material-pending commitment lane retired — replies
# ground on the bounded-wait read or speak the honest wait, never a marked
# promise.
INTERACTION_POLICY_VERSION = "interaction_constitution.v2"


# Session-``info`` key marking conversations BORN in this session (stamped
# by ``_get_or_create_project_conversation``) — ``alloc_message_seq`` reads
# it to route the first turn's allocations through the caller's own
# transaction (the fresh-session path can't see the uncommitted parent and
# would violate the counter's FK).
_FRESH_CONVERSATIONS_INFO = "chat.fresh_conversations"


async def alloc_message_seq(conversation_id: UUID, db: AsyncSession | None = None) -> int:
    """Transcript 数组序分配器 (ADR-108 §1): bump the conversation's counter
    under its OWN short transaction and return the new value — never call
    this inside a chat turn's long transaction. The counter lives on the
    dedicated message_seq_counters row (NEVER the conversations row: the
    turn transaction holds that row's lock from prepare's first flush on,
    for minutes — a fresh-session UPDATE on it would self-deadlock against
    the very turn awaiting the allocation). Gap-tolerant by design: a
    rolled-back turn leaves holes in seq; monotonicity is the contract,
    contiguity is not.

    新生会话例外 (2026-10-08 FK 取证): the counter row's FK needs the
    conversation COMMITTED, but a conversation born this turn is only
    flushed — a fresh-session upsert violates the FK (parent invisible),
    and retrying it once the counter exists in-session would block on the
    speculative-insertion lock (self-deadlock: the turn awaits the
    allocation). So when ``db`` carries this conversation in its
    ``_FRESH_CONVERSATIONS_INFO`` mark (stamped by
    ``_get_or_create_project_conversation`` at birth), the upsert rides the
    caller's OWN session — same transaction sees its own parent, and the
    counter lock's lifetime is bounded by prepare's input-durability
    commit, which discards the mark; every later allocation takes the
    short-transaction path again."""
    from app.models.database import AsyncSessionLocal  # deferred: module-load order

    def _upsert_stmt():
        return (
            pg_insert(MessageSeqCounter)
            .values(conversation_id=conversation_id, last_seq=1)
            .on_conflict_do_update(
                index_elements=["conversation_id"],
                set_={"last_seq": MessageSeqCounter.last_seq + 1},
            )
            .returning(MessageSeqCounter.last_seq)
        )

    if db is not None and conversation_id in db.info.get(_FRESH_CONVERSATIONS_INFO, ()):
        result = await db.execute(_upsert_stmt())
        return result.scalar_one()
    async with AsyncSessionLocal() as s:
        result = await s.execute(_upsert_stmt())
        seq = result.scalar_one()
        await s.commit()
        return seq


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
    suggestions: list[dict[str, Any]] | None = None,
    suggestion_ref: dict[str, Any] | None = None,
    turn_id: UUID | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> Message:
    if role == "assistant":
        # 工具名回响 sanitizer (2026-09-30 用户拍板 — 彻底删掉): the model
        # occasionally echoes its own call as a bare '[tool_name]' prose
        # line; the ack sentence already covers it and machine vocabulary
        # never reaches the user.
        content = strip_tool_echoes(content)
        intent = {
            **(intent or {}),
            "interaction_policy_version": INTERACTION_POLICY_VERSION,
        }
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
        suggestions=suggestions or [],
        suggestion_ref=suggestion_ref,
        turn_id=turn_id,
        blocks=blocks or [],
        seq=await alloc_message_seq(conversation_id, db),
    )
    db.add(message)
    await db.flush()
    if role == "user" and message.turn_id is None:
        # The opening row is its own turn identity. This is an id assignment,
        # not a backfill or an inference about any neighbouring row.
        message.turn_id = message.id
        await db.flush()
    await db.refresh(message)
    return message


async def _parked_interrupt_run(
    db: AsyncSession, run_id: UUID
) -> WorkflowRun | None:
    """A run id on a question is only an anchor until a waiting step proves
    it is a direction interrupt. Trigger suggestions share the same column."""
    run = await db.get(WorkflowRun, run_id)
    if run is None:
        return None
    parked_step_id = (
        await db.execute(
            select(WorkflowStep.id)
            .where(
                WorkflowStep.run_id == run.id,
                WorkflowStep.status == "waiting",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return run if parked_step_id is not None else None


async def _load_project(db: AsyncSession, project_id: UUID) -> Project | None:
    return await db.get(Project, project_id)


async def _create_run_from_tasks(
    db: AsyncSession,
    project: Project,
    tasks: list[TaskItem],
    summary: str,
    instruction: str | None = None,
    name: str | None = None,
    source_asset_id: str | None = None,
    exemplar_asset_id: str | None = None,
) -> UUID:
    """Dispatch a proposed task list through the ONLY run birthplace.

    A user-level shortfall converts to the structured 422 HERE — the chat
    dispatch's single conversion point (BILLING §7): every dispatch path
    (the judged start, both repair re-dispatches) then raises the same
    ``{code, balance, required}`` the typed Start's answer endpoint raises,
    the repair handlers' broad ValueError catches never swallow it, and the
    SSE turn pump carries it as the turn.failed frame the dock renders as
    its grey row (入流灰行, 双路同语义).

    ``instruction`` overrides the run's plan instruction (default = the
    summary): the wiring revision path pins the edited node program here
    (the writers' GenerationContext.instruction steers the rewrite).

    ``name`` = the proposer's fresh naming of the run (ADR-058 — LLM 建图时
    命名), stored on run.context via TaskSpec; the receipt title and the
    completion line read it instead of any frozen-params template.

    ``source_asset_id`` / ``exemplar_asset_id`` = the 资产角色 pins (ADR-078
    判词④), computed by the caller (a mention pin or the inherited
    conversation pins — propose_turn's seat), riding TaskSpec → run.context
    verbatim. create_run validates them at the birthplace (422 on a
    non-project / non-video exemplar).
    """
    from app.pipeline.orchestrator import TaskSpec, create_run, first_task_language

    if not (name or "").strip():
        # 二源律的可观测座 (ADR-058): the fallback chain label is legal but
        # silent — count every run an LLM proposal SHOULD have named and
        # didn't, so the unnamed rate is visible instead of the frozen-params
        # template quietly coming back.
        logger.info("unnamed_proposal", path="chat_dispatch", project_id=str(project.id))
    try:
        from app.tools.video.production import latest_video_approval
        run = await create_run(
            db,
            project,
            TaskSpec(
                tasks=tasks,
                target_language=first_task_language(tasks) or project.language or "en",
                instruction=instruction or summary,
                scope="full",
                source_asset_id=source_asset_id,
                exemplar_asset_id=exemplar_asset_id,
                name=name or None,
                video_authorized_by=await latest_video_approval(db, project),
            ),
        )
    except CreditsInsufficientError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "code": "credits.insufficient",
                "balance": exc.balance,
                "required": exc.required,
            },
        ) from exc
    return run.id


def _prefers_zh(text: str) -> bool:
    """Language heuristic for server-composed reply lines — the CJK check
    rides the user's own words (the turn's text), not a stored setting."""
    return any("一" <= ch <= "鿿" for ch in text)  # CJK Unified Ideographs


async def _safe_task_estimate(
    db: AsyncSession, project: Project, tasks: list[TaskItem]
) -> PlanEstimate | None:
    """The dock payload's credits quotation, degraded like the derived
    preview (the plan-turn's own posture): an uncompilable/unquotable chain
    docks quote-less, never blocked."""
    from app.pipeline.orchestrator import derive_task_estimates  # deferred

    try:
        return await derive_task_estimates(db, project, tasks)
    except (ToolRejected, ValueError):
        return None


async def resolve_confirmation_need(
    db: AsyncSession,
    user_id: UUID,
    estimate: PlanEstimate | None,
    production_intent: bool | None = True,
    unmet_condition: bool = False,
    copy_drift: bool = False,
    require_quote: bool = False,
) -> "ConfirmationNeed":
    """The dock's confirmation conjunct (ADR-117 §4): read the user's two
    prefs + the guardrail config, fold the quote, run the pure law. The
    result is stamped onto the docked question's payload at presentation
    time — the client's pill predicate and the start gate both read THAT
    stamp, never a re-derivation.

    ``production_intent`` (ADR-139): the dock seats pass the birth turn's
    assertion verbatim (None = unasserted → the safe-side hold); the
    fallback default ``True`` covers non-dock re-dock seats (the start_run
    misfire re-dock never auto-starts, so its stamp only re-derives the
    prefs law). ``unmet_condition`` (7276ef13 ③): the dock seats pass the
    birth turn's design shortfall (a requested change was refused this
    turn) — the conditional authorization never auto-spends on the
    unfixed version. ``copy_drift`` (7276ef13 定点收尾②): the dock seats
    pass the birth turn's drift hold (the published copy drifted from the
    user-verifiable original) — auto start holds until the user sees the
    drift note and chooses."""
    from app.pipeline.lifecycle import ConfirmationNeed, confirmation_need

    user = await db.get(User, user_id)
    execution, credits = read_confirmation_prefs(
        user.settings if user is not None else None
    )
    guardrail = await get_config(db, "billing.always_confirm_above")
    quote_high = int(estimate.total[1]) if estimate is not None else None
    unquotable = estimate is None or any(t is None for t in estimate.per_task)
    if require_quote and unquotable:
        return ConfirmationNeed(True, "unquotable", quote_high, True)
    return confirmation_need(
        execution=execution,
        credits=credits,
        quote_high=quote_high,
        unquotable=unquotable,
        always_confirm_above=guardrail,
        production_intent=production_intent,
        unmet_condition=unmet_condition,
        copy_drift=copy_drift,
    )


# ---- brief (DIALOG_WORKFLOW §2.4, ADR-052 B2) --------------------------------

_SOURCE_RANK: dict[BriefSlotSource, int] = {
    BriefSlotSource.DEFAULT: 0,
    BriefSlotSource.INFERRED: 1,
    BriefSlotSource.USER_STATED: 2,
}

_BRIEF_SCALAR_SLOTS = (
    "topic", "audience", "tone", "material_state", "production_direction", "purpose", "target_seconds",
    "narrative_mode", "narration_language", "subtitle_languages", "aspect",
    "voice_requirements", "must_include", "avoid", "success_criteria",
)


_CONSTRAINT_DIGITS = re.compile(r"\d+")


def _constraint_key(text: str) -> str:
    """constraints 归并键：归一化条目文本（大小写/空白不敏感，数字归 #——
    同一约束维度的重申同键：'keep it under 200 words' 与 'keep it under 100
    words' 是一条约束的两次说法，重申走逐项 precedence 原位替换，不攒出自相
    矛盾的双条目。S12 矩阵即此键的规格）。"""
    return _CONSTRAINT_DIGITS.sub("#", " ".join(text.split()).lower())


def _merge_constraints(
    proposed: list[BriefSlot[str]], stored: list[BriefSlot[str]]
) -> list[BriefSlot[str]]:
    """constraints 合并（顺形律 2026-09-11, ADR-064）= keyed union：键 = 归一化
    条目文本，同文本冲突按逐项 precedence（user-stated > inferred > default，
    与标量槽同一把尺——用户亲口说的约束永不被推断顶掉）。顺序 = stored 原序
    + 新条目追加（brief 稳定可读）。"""
    merged = list(stored)
    index = {
        _constraint_key(item.value): i for i, item in enumerate(merged) if item.value
    }
    for item in proposed:
        if not item.value:
            continue
        key = _constraint_key(item.value)
        existing_idx = index.get(key)
        if existing_idx is None:
            index[key] = len(merged)
            merged.append(item)
        elif _SOURCE_RANK[item.source] >= _SOURCE_RANK[merged[existing_idx].source]:
            merged[existing_idx] = item
    return merged


def merge_brief(update: Brief | None, stored: Brief) -> Brief:
    """Brief merge — pure (LLM proposes, code decides; 禁 LLM 合并槽位).

    The router proposes a full update every plan turn; code lands it per
    slot by source precedence (user-stated > inferred > default):
    - a no-opinion slot (value=None) never lands — the stored value survives;
    - the update wins when its source ranks AT LEAST the stored source's —
      so user-stated is never reverse-overwritten by inference or defaults
      (含 repair 重试与 ask 答复回填), while the user re-stating a slot
      (user-stated again) always wins — chat 修订恒胜.
    - scalar slots (topic/audience/tone/material_state) replace per-slot;
      constraints 是数组槽，按条目 keyed union（同一把 precedence 尺逐项
      应用，ADR-064 顺形律）。
    """
    if update is None:
        return stored
    merged = stored.model_copy(deep=True)
    for field_name in _BRIEF_SCALAR_SLOTS:
        proposed: BriefSlot = getattr(update, field_name)
        if proposed is None or proposed.value is None:
            continue
        current: BriefSlot = getattr(merged, field_name)
        if _SOURCE_RANK[proposed.source] >= _SOURCE_RANK[current.source]:
            setattr(merged, field_name, proposed)
    merged.constraints = _merge_constraints(update.constraints, merged.constraints)
    return merged


def _backfill_brief_slot(project: Project, slot: str, value: str) -> None:
    """ask 答复回填 (ADR-052 B2 D2-C1): the docked question's brief slot
    takes the user's answer as a user-stated value. Routed through
    merge_brief (user-stated 恒胜 — never a 反向覆盖), never a direct write.
    Creates the brief-only row when none exists (defensive — the ask dock
    normally wrote one)."""
    stored = (
        PendingPlan.model_validate(project.pending_brief)
        if isinstance(project.pending_brief, dict)
        else PendingPlan()
    )
    update = Brief()
    normalized: Any = value
    if slot == "target_seconds" and isinstance(value, str):
        match = re.search(r"\d+", value)
        normalized = int(match.group(0)) if match else value
    elif slot == "subtitle_languages" and isinstance(value, str):
        normalized = [
            _language_code(part) for part in re.split(r"[+,，、/\s]+", value) if part.strip()
        ]
    elif slot in {"must_include", "avoid", "success_criteria"} and isinstance(value, str):
        normalized = [value]
    setattr(
        update,
        slot,
        BriefSlot(value=normalized, source=BriefSlotSource.USER_STATED),
    )
    stored.brief = merge_brief(update, stored.brief)
    from app.chat.readiness import creative_state_for_pending, creative_state_with_brief
    from app.models.schemas import CreativeState

    stored.creative_state = creative_state_with_brief(
        creative_state_for_pending(stored) or CreativeState(), stored.brief
    )
    project.pending_brief = stored.model_dump(mode="json")


def _language_code(value: str) -> str:
    normalized = value.strip().lower()
    return {
        "english": "en", "英文": "en", "英语": "en", "en": "en",
        "chinese": "zh", "中文": "zh", "汉语": "zh", "zh": "zh",
    }.get(normalized, normalized)


def _group_slot_value(item, answer) -> Any:
    from app.models.schemas import BriefAnswerItem

    assert isinstance(answer, BriefAnswerItem)
    if answer.kind == "option":
        return next(option.value for option in item.options if option.id == answer.option_id)
    display = (answer.text or "").strip()
    if item.slot == "target_seconds":
        match = re.search(r"\d+", display)
        if match is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "target_seconds needs a number")
        return int(match.group(0))
    if item.slot == "aspect":
        match = re.search(r"16:9|9:16|1:1", display)
        if match is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "aspect must be 16:9, 9:16 or 1:1")
        return match.group(0)
    if item.slot == "narration_language":
        return _language_code(display)
    if item.slot == "subtitle_languages":
        values = re.split(r"[+,，、/\s]+", display)
        languages = [_language_code(value) for value in values if value.strip()]
        if not languages or any(not value for value in languages):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "subtitle_languages needs at least one language")
        return list(dict.fromkeys(languages))
    if item.slot in {"must_include", "avoid", "success_criteria"}:
        return [display]
    return display


def _validate_group_answers(
    question: QuestionPayload, data, *, require_required: bool = True
) -> list:
    from app.models.schemas import BriefAnswerItem

    if not question.items or not question.group_digest:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This question is not a clarification group")
    if data.group_digest != question.group_digest:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "question.group_digest_mismatch"})
    by_slot = {item.slot: item for item in question.items}
    seen: set[str] = set()
    normalized: list[BriefAnswerItem] = []
    for answer in data.answers:
        if answer.slot in seen:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Duplicate answer slot '{answer.slot}'")
        seen.add(answer.slot)
        item = by_slot.get(answer.slot)
        if item is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unexpected answer slot '{answer.slot}'")
        if answer.kind == "option":
            option = next((option for option in item.options if option.id == answer.option_id), None)
            if option is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown option for slot '{answer.slot}'")
            answer = answer.model_copy(update={"text": option.label})
        else:
            text = (answer.text or "").strip()
            if not item.allow_freeform:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Freeform is disabled for slot '{answer.slot}'")
            if not text or len(text) > 4000:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid freeform length for slot '{answer.slot}'")
            answer = answer.model_copy(update={"text": text})
        normalized.append(answer)
    missing = [item.slot for item in question.items if item.required and item.slot not in seen]
    if require_required and missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Missing required slots: {missing}")
    return normalized


def _backfill_brief_group(project: Project, question: QuestionPayload, answers: list) -> None:
    stored = PendingPlan.model_validate(project.pending_brief or {})
    by_slot = {item.slot: item for item in question.items}
    for answer in answers:
        update = Brief()
        item = by_slot[answer.slot]
        value = _group_slot_value(item, answer)
        if item.slot == "production_direction" and answer.kind == "freeform":
            from app.chat.readiness import direction_with_known_details

            value = direction_with_known_details(stored.brief, value)
        setattr(update, item.slot, BriefSlot(
            value=value,
            source=BriefSlotSource.USER_STATED,
        ))
        stored.brief = merge_brief(update, stored.brief)
    from app.chat.readiness import (
        creative_state_for_pending, creative_state_with_brief, infer_task_kind, resolve_legacy_direction,
    )
    from app.models.schemas import CreativeState

    if infer_task_kind(stored.prompt or "") == "website_promo":
        resolve_legacy_direction(stored.brief)
    stored.creative_state = creative_state_with_brief(
        creative_state_for_pending(stored) or CreativeState(), stored.brief
    )
    project.pending_brief = stored.model_dump(mode="json")


async def _apply_website_promo_group_defaults(db: AsyncSession, project: Project) -> None:
    from app.chat.readiness import (
        creative_state_for_pending,
        creative_state_with_brief,
        infer_task_kind,
        website_promo_default_brief,
    )
    from app.models.schemas import CreativeState
    from app.models.tables import SourceSnapshot

    stored = PendingPlan.model_validate(project.pending_brief or {})
    if infer_task_kind(stored.prompt) != "website_promo":
        return
    state = creative_state_for_pending(stored) or CreativeState()
    profile = state.brand_profile
    refs = profile.source_refs if profile is not None else state.source_refs
    snapshot_ids = []
    for ref in refs:
        try:
            snapshot_ids.append(UUID(str(ref.snapshot_id)))
        except (ValueError, TypeError, AttributeError):
            continue
    snapshots = (
        list((await db.scalars(
            select(SourceSnapshot).where(SourceSnapshot.id.in_(snapshot_ids))
        )).all())
        if snapshot_ids
        else []
    )
    stored.brief = website_promo_default_brief(
        stored.brief,
        snapshots,
        fallback_language="zh" if _prefers_zh(stored.prompt) else "en",
    )
    stored.creative_state = creative_state_with_brief(state, stored.brief)
    project.pending_brief = stored.model_dump(mode="json")


# ---- 资产角色 (ADR-078 判词④): the role question + the pin settles -----------
#
# 判词④: source = the user's own material; reference/exemplar = the case whose
# craft the decompiler reverse-compiles. Disambiguation = the ask_user machine
# (slot="asset_role") or an @-mention; the pins are settled by CODE ONLY — the
# LLM frames the question but its options are built here (id = asset id), and
# the answer decodes by id, never by a guessed filename. reference 常驻可回读:
# the pins ride PendingPlan → TaskSpec → run.context verbatim, and the
# skeleton row itself is content-addressed (the read tool re-reads it any
# time). Roles are reversible between runs (a fresh mention re-pins).


def _build_role_question(text: str, assets: list[Asset]) -> QuestionProposal | None:
    """The role-disambiguation question — code-built (the caption-mode
    question's precedent): the options ARE the project's videos (option id =
    asset id, label = filename), so the answer settles deterministically.
    None = fewer than two videos attached (nothing to disambiguate). The
    default path keeps upload order: first video = the material."""
    videos = [a for a in assets if a.type == AssetType.VIDEO and a.file_url]
    if len(videos) < 2:
        return None
    zh = _prefers_zh(text)
    options = [
        Option(id=str(a.id), label=a.display_name or a.type.value) for a in videos
    ]
    first_name = videos[0].display_name or videos[0].type.value
    if zh:
        return QuestionProposal(
            question="哪个是你的原片？另一个会当参照案例，拆解它的风格。",
            options=options,
            allow_freeform=True,
            slot="asset_role",
            default_path=f"跳过按上传顺序：{first_name} 当原片，另一个当案例。",
        )
    return QuestionProposal(
        question="Which one is your own video? The other becomes the style reference I decompile.",
        options=options,
        allow_freeform=True,
        slot="asset_role",
        default_path=f"Skip keeps upload order: {first_name} is the material, the other the reference.",
    )


async def _project_videos(db: AsyncSession, project: Project) -> list[Asset]:
    """The project's attached videos in upload order (the honest prior the
    role question's default path promises)."""
    return list(
        (
            await db.execute(
                select(Asset)
                .where(
                    Asset.project_id == project.id,
                    Asset.type == AssetType.VIDEO,
                    Asset.file_url.isnot(None),
                )
                .order_by(Asset.created_at)
            )
        )
        .scalars()
        .all()
    )


async def _stamp_role_pins(
    db: AsyncSession,
    project: Project,
    source: Asset,
    exemplar: Asset | None,
) -> None:
    """The ONE role-pin write (判词④): the PendingPlan seats + the exemplar's
    warm fire (the skeleton materializes before any run asks; the claim gate
    holds the run until processing drains, and the processing-completion
    seat re-fires the warm for a still-processing exemplar). Both settle
    paths — the answer's pick and the bail's default — write through here,
    and nothing else does."""
    stored = (
        PendingPlan.model_validate(project.pending_brief)
        if isinstance(project.pending_brief, dict)
        else PendingPlan()
    )
    stored.source_asset_id = str(source.id)
    stored.exemplar_asset_id = str(exemplar.id) if exemplar is not None else None
    project.pending_brief = stored.model_dump(mode="json")
    logger.info(
        "asset_roles_settled",
        project_id=str(project.id),
        source=str(source.id),
        exemplar=str(exemplar.id) if exemplar is not None else None,
    )


async def _settle_role_answer(
    db: AsyncSession, project: Project, data: AnswerRequest, say: str
) -> None:
    """The role question's option/freeform answer → pins by code. An option
    hit names the user's original directly (option id = asset id, built by
    ``_build_role_question``); a freeform answer substring-matches a video
    filename (both directions — 'the second one, b.mp4' carries the name).
    Unresolvable answers settle NOTHING — the plan proceeds pin-less and the
    decompiler simply isn't injected (honest degrade, never a guess)."""
    videos = await _project_videos(db, project)
    source: Asset | None = None
    if data.kind == "option" and data.option_id:
        source = next((v for v in videos if str(v.id) == str(data.option_id)), None)
    if source is None and say.strip():
        needle = say.strip().lower()
        source = next(
            (
                v
                for v in videos
                if (name := (v.display_name or "").lower())
                and (needle in name or name in needle)
            ),
            None,
        )
    if source is None:
        logger.info("role_answer_unresolved", project_id=str(project.id))
        return
    exemplar = next((v for v in videos if v.id != source.id), None)
    await _stamp_role_pins(db, project, source, exemplar)


async def _settle_default_role_pins(db: AsyncSession, project: Project) -> None:
    """The bail path's promised default (the question's own default_path):
    skip = upload order — the first video is the material, the next the
    exemplar."""
    videos = await _project_videos(db, project)
    if len(videos) < 2:
        return
    await _stamp_role_pins(db, project, videos[0], videos[1])


async def _compute_plan_reasons(
    db: AsyncSession,
    project: Project,
    intent: InferredIntent,
) -> list[str]:
    """Re-derive the soft-signal reasons for a docked plan.

    Pure function over (db, project, intent) — the answer path passes the
    Registry-native checks over the current production tools.
    """
    reasons: list[str] = []
    if not intent.tasks_explicit:
        reasons.append("chain_default")
    has_media = await has_renderable_media(db, UUID(str(project.id)))
    if not has_media and any(_needs_media(t.tool) for t in intent.tasks):
        reasons.append("clips_without_media")
    return reasons


def _needs_media(tool: str) -> bool:
    """True iff a tool's node requires MEDIA or materializes source.

    Hoisted out of _plan_turn (2026-08-25) so the answer path's
    ``_compute_plan_reasons`` and the plan path's carve-out can both
    call it. Registry-native: walks ``node.requires`` + ``node.after``
    rather than maintaining a parallel tool list (RECIPES §4.6).
    """
    node = NODE_KINDS.get(tool)
    if node is None:
        return False
    return any(r.key == MEDIA.key for r in node.requires)


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
    serialized guard — a zombie plan confirmed later gets the clean
    RunAlreadyActiveError 422, never a second run."""
    from app.pipeline.orchestrator import has_active_run  # deferred: import cycle

    if await has_active_run(db, project.id):
        return _run_active_text(text)
    return None


def _loop_incomplete_text(text: str, result) -> str:
    """An execution limit is not evidence that a requested capability is absent."""
    observations = getattr(result, "observations", [])
    rejections = getattr(result, "rejections", [])
    video_tools = {"design_video", "split_clip"}
    saved = bool(getattr(result, "version_saved", False))
    prepared = any(name in {"prepare_video_materials", "capture_web"} and ok for name, ok in observations)
    rejected = any(r.tool_name in video_tools for r in rejections) or any(name in video_tools and not ok for name, ok in observations)
    material_failed = any(name in {"prepare_video_materials", "capture_web"} and not ok for name, ok in observations)
    if _prefers_zh(text):
        if saved:
            return "作品版本已保存，但本轮后续处理未完成。当前保存内容仍保留。"
        prefix = "已成功准备的素材仍保留。" if prepared else ""
        if rejected:
            return prefix + "本轮作品提交未通过校验，已达到本轮处理上限，尚未保存本轮修改。"
        if material_failed:
            return prefix + "仍有素材准备失败，本轮未能完成作品。已成功的资源仍保留。"
        return prefix + "本轮已达到处理次数上限，尚未完成你的请求。"
    if saved:
        return "The work version was saved, but this turn's follow-up did not finish. The saved content remains available."
    prefix = "Successfully prepared materials remain available. " if prepared else ""
    if rejected:
        return prefix + "The work submission did not pass validation before this turn's limit. This turn's changes were not saved."
    if material_failed:
        return prefix + "Some material preparation failed, so the work is incomplete. Successfully prepared resources remain available."
    return prefix + "This turn reached its processing limit before completing your request."


def _cannot_do_text(text: str) -> str:
    """The refusal line (both intent surfaces). Human capability words only —
    registry tool names are internal vocabulary, never user-facing
    (2026-08-20 review: the null-params incident had ~50% of recipe launches
    reading this line in English with tool slugs in it)."""
    if _prefers_zh(text):
        return "这个我现在还做不了。请描述要制作或修改的视频、要整理的画布，或想咨询的问题。"
    return (
        "I can't do that yet. Try describing a video to create or edit, "
        "a canvas to organize, or a question to answer."
    )


def _video_capability_text(text: str, facts: dict[str, Any]) -> str:
    """Honest close for a deterministic video-media capability refusal.

    The refusal carries the standing version read, not a prose draft. This
    seat only turns those facts into the user's language; it never invents a
    successful revision or an unrelated product suggestion.
    """
    version = int(facts["version"])
    duration = float(facts["duration_seconds"])
    duration_text = f"{duration:.3f}".rstrip("0").rstrip(".")
    medium = str(facts.get("medium") or "")
    is_current = bool(facts.get("is_current"))
    if _prefers_zh(text):
        constraint = {
            "speech": "旁白原文和语速",
            "generator": "待生成媒体的内容",
            "video": "真实视频素材的内容和播放速度",
            "audio": "音频内容和播放速度",
        }.get(medium, "相关媒体内容")
        standing = (
            f"当前分镜仍是第 {version} 版，总时长 {duration_text} 秒。"
            if is_current else
            f"这次修改所基于的第 {version} 版分镜总时长为 {duration_text} 秒。"
        )
        return (
            standing + "这次时间修改没有保存新版本，也没有开始制作。"
            f"在必须保持{constraint}不变的前提下，这项时间修改无法完成。"
            "可以保留现有分镜；如果你明确允许调整相关媒体内容，再重新安排时长。"
        )
    constraint = {
        "speech": "the narration wording and playback speed",
        "generator": "the pending generated media's content",
        "video": "the video footage and playback speed",
        "audio": "the audio content and playback speed",
    }.get(medium, "the related media content")
    standing = (
        f"The current storyboard is still version {version}, {duration_text} seconds. "
        if is_current else
        f"The storyboard used for this edit is version {version}, {duration_text} seconds. "
    )
    return (
        standing + "This timing change saved no new version and started no production. "
        f"This timing change cannot be completed while preserving {constraint}. "
        "You can keep the existing storyboard, or explicitly allow changes to "
        "the related media before planning a new duration."
    )


def _video_review_failure_text(text: str, facts: dict[str, Any]) -> str:
    """Close a failed recheck from the earlier report, never a generic ask-back."""
    zh = _prefers_zh(text)
    previous = facts.get("previous_report")
    if not isinstance(previous, dict):
        if zh:
            return (
                "这次成片检查没有完成，也没有形成新的审片报告；"
                "没有修改或重新制作成片。是否重新检查，由你决定。"
            )
        return (
            "This video review did not complete and produced no new report. "
            "The video was not changed or produced again. You decide whether to retry."
        )

    scope = previous.get("scope") if isinstance(previous.get("scope"), dict) else {}
    frames = previous.get("frames") if isinstance(previous.get("frames"), list) else []
    findings = previous.get("findings") if isinstance(previous.get("findings"), list) else []
    summary = str(previous.get("summary") or "").strip()
    if summary and _prefers_zh(summary) != zh:
        summary = ""
    raw_times = facts.get("at_seconds")
    times = [
        f"{float(value):g}"
        for value in (raw_times if isinstance(raw_times, list) else [])
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]
    observations = [
        str(finding.get("observed") or "").strip()
        for finding in findings
        if isinstance(finding, dict) and str(finding.get("observed") or "").strip()
    ]
    finding_count = len(observations)
    observations = [value for value in observations if _prefers_zh(value) == zh]

    if zh:
        checked = f"上一次检查已完成，实际解码并检查了 {len(frames)} 个采样帧"
        if scope.get("audio_signal_checked"):
            checked += "，并完成了音频流与 RMS/峰值等信号检查"
        elif scope.get("deterministic_output_checks"):
            checked += "，并完成了确定性媒体检查"
        checked += "。"
        if observations:
            checked += "当时的发现是：" + "；".join(observations) + "。"
        elif finding_count:
            checked += f"当时记录了 {finding_count} 条内容发现。"
        else:
            checked += "当时的采样帧中没有内容发现。"
        if summary:
            checked += f"上一次报告摘要：{summary}"
            if not summary.endswith(("。", "！", "？", ".", "!", "?")):
                checked += "。"
        focused = (
            f"刚才针对 {'、'.join(times)} 秒的定点复查没有完成"
            if times else "刚才的复查没有完成"
        )
        return (
            checked
            + focused + "，没有形成新的审片报告，因此不能据此更新这次定点检查的判断；"
            "上一次报告仍只代表它自己的采样与检查范围。"
            "连续运动、音画同步和主观听感仍未检查。"
            "没有修改或重新制作成片。是否再次复查，由你决定。"
        )

    checked = f"The earlier review completed and checked {len(frames)} actual decoded sample frames"
    if scope.get("audio_signal_checked"):
        checked += ", with audio-stream and signal measurements such as RMS and peak"
    elif scope.get("deterministic_output_checks"):
        checked += ", with deterministic media checks"
    checked += ". "
    if observations:
        checked += "Its findings were: " + "; ".join(observations) + ". "
    elif finding_count:
        checked += f"It recorded {finding_count} content findings. "
    else:
        checked += "It recorded no content findings in those sampled frames. "
    if summary:
        checked += f"Earlier report summary: {summary}"
        if not summary.endswith((".", "!", "?", "。", "！", "？")):
            checked += "."
        checked += " "
    focused = (
        f"The focused recheck at {', '.join(times)} seconds did not complete"
        if times else "The recheck did not complete"
    )
    return (
        checked
        + focused + " and produced no valid new report, so it cannot update the conclusions "
        "for those points. The earlier report remains limited to its own samples and scope. "
        "Continuous motion, audio-visual synchronization and perceived listening quality "
        "remain unchecked. The video was not changed or produced again. "
        "You decide whether to review it again."
    )


def _video_review_report_text(text: str, report: dict[str, Any]) -> str:
    """Close from a completed report when the later prose continuation fails.

    The focused reviewer has already persisted its findings. Losing the outer
    model call must not erase that work or misread it as an ambiguous request.
    """
    zh = _prefers_zh(text)
    scope = report.get("scope") if isinstance(report.get("scope"), dict) else {}
    frames = report.get("frames") if isinstance(report.get("frames"), list) else []
    findings = report.get("findings") if isinstance(report.get("findings"), list) else []
    summary = str(report.get("summary") or "").strip()
    if summary and _prefers_zh(summary) != zh:
        summary = ""
    observations = [
        value
        for finding in findings
        if isinstance(finding, dict)
        and (value := str(finding.get("observed") or "").strip())
        and _prefers_zh(value) == zh
    ]
    if summary:
        content = summary
        if not content.endswith(("。", "！", "？", ".", "!", "?")):
            content += "。" if zh else "."
        if observations:
            content += (
                "具体发现：" + "；".join(observations) + "。"
                if zh else "Specific findings: " + "; ".join(observations) + ". "
            )
    elif observations:
        content = (
            "本次检查发现：" + "；".join(observations) + "。"
            if zh else "This review found: " + "; ".join(observations) + ". "
        )
    elif zh:
        content = (
            f"本次检查已完成，实际解码并检查了 {len(frames)} 个采样帧；"
            + (f"记录了 {len(findings)} 条内容发现。" if findings else "这些采样帧中没有内容发现。")
        )
    else:
        content = (
            f"This review completed and checked {len(frames)} actual decoded sample frames; "
            + (
                f"it recorded {len(findings)} content findings. "
                if findings else "those sampled frames contained no content findings. "
            )
        )
    unchecked: list[str] = []
    if not scope.get("motion_and_transitions_checked"):
        unchecked.append("连续运动与转场" if zh else "continuous motion and transitions")
    if scope.get("audio_signal_checked"):
        unchecked.append("主观听感" if zh else "perceived listening quality")
    if not scope.get("audio_and_av_sync_checked"):
        unchecked.append("音画同步" if zh else "audio-visual synchronization")
    if unchecked:
        content += (
            "本次未检查" + "、".join(unchecked) + "；结论只覆盖上述采样与信号范围。"
            if zh else "This review did not check " + ", ".join(unchecked)
            + "; its conclusions cover only the samples and signals above. "
        )
    return content + ("本次没有修改成片。" if zh else "The video was not changed. ")


def _sfx_import_failure_text(text: str) -> str:
    """Close a failed selection honestly; the next search or pick is the user's."""
    if _prefers_zh(text):
        return (
            "这段音频没有导入成功，也没有修改当前作品。"
            "你可以让我重新搜索一批候选，或选择另一个候选。"
        )
    return (
        "That sound could not be imported, and the current work was not changed. "
        "You can ask for a new search or choose a different candidate."
    )


def _design_blocked_text(text: str, refusal: str | None) -> str:
    """The design-beat degrade line (both intent surfaces): the turn's
    storyboard design never started because the begin was refused. The
    refusal REASON selects the honesty class — ``in_flight`` is the only
    one that may narrate a live design (a committed marker proved it);
    everything else is a state conflict with an UNKNOWN holder. Never the
    capability refusal (``_cannot_do_text``): an internal startup conflict
    is not "text films unsupported", and no variant promises recovery —
    the only next step on offer is a fresh message (a new turn re-reads
    the world)."""
    if _prefers_zh(text):
        if refusal == "in_flight":
            return (
                "分镜还没有生成——另一个分镜设计还在进行中，这次没有开始制作。"
                "等它落定后再跟我说一声即可。"
            )
        return (
            "分镜尚未生成——启动设计时遇到状态冲突，本次没有开始制作。"
            "你再发一句话，我会重新尝试设计。"
        )
    if refusal == "in_flight":
        return (
            "The storyboard isn't drafted — another storyboard design is "
            "still in flight on this project, so this one never started. "
            "Ask me again once it settles."
        )
    return (
        "The storyboard isn't drafted — starting the design hit a state "
        "conflict on the project, so nothing was produced this time. Send "
        "me another message and I'll try the design again."
    )


def _markdown_cell(value: object) -> str:
    text = str(value or "—")
    return text.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def _video_no_progress_text(text: str, read: dict) -> str:
    """Present the saved video facts when a later correction exhausts its loop."""
    from app.editing.service import storyboard_presentation_rows

    zh = _prefers_zh(text)
    rows = storyboard_presentation_rows(read)
    if zh:
        intro = "下面的分镜已经保存。最后一次后续调整未完成，未写入这版；本次没有开始制作。"
        header = "| 镜头 | 时间 | 屏幕文字 | 画面与目的 |"
        divider = "| --- | --- | --- | --- |"
        footer = "请先查看这个已保存版本；未完成的调整仍需另行处理。"
    else:
        intro = (
            "The storyboard below is saved. The last follow-up adjustment did not "
            "complete and is not included; no production started."
        )
        header = "| Shot | Time | On-screen text | Picture and purpose |"
        divider = "| --- | --- | --- | --- |"
        footer = "Review this saved version first; the unfinished adjustment still needs separate handling."
    table = [header, divider]
    for row in rows:
        direction = row.get("scene_visual_description") or row.get("scene_intent")
        table.append(
            "| "
            + " | ".join((
                _markdown_cell(row.get("shot")),
                f"{float(row['start_seconds']):.2f}–{float(row['end_seconds']):.2f}s",
                _markdown_cell(row.get("text")),
                _markdown_cell(direction),
            ))
            + " |"
        )
    payload = read["storyboard"]
    settings = payload["settings"]
    facts = (
        f"时长 {float(payload['duration_seconds']):.1f} 秒；"
        f"画布 {settings['width']}×{settings['height']}；{float(settings['fps']):g}fps。"
        if zh else
        f"Duration {float(payload['duration_seconds']):.1f}s; "
        f"canvas {settings['width']}×{settings['height']}; {float(settings['fps']):g}fps."
    )
    return "\n\n".join((intro, "\n".join(table), facts, footer))


def _design_no_progress_text(
    text: str, *, version_saved: bool, video_read: dict | None = None
) -> str:
    """Honest close after the loop's Film rejection policy stops a retry.

    The two states are deliberately different: a failed correction must not
    erase the fact that an earlier version was saved this turn, while a
    failed first design must not claim that any new storyboard exists.
    """
    if video_read is not None:
        return _video_no_progress_text(text, video_read)
    if _prefers_zh(text):
        if version_saved:
            return (
                "这次后续调整没有完成，我已停止重复尝试。最近保存的分镜版本"
                "和已有成片都保留，本次没有开始新的制作。请再发一次，我会"
                "从最近保存的版本继续。"
            )
        return (
            "这次调整没有完成，我没有保存新的分镜，也没有开始制作。我已停止"
            "重复尝试。请再发一次，我会重新尝试。"
        )
    if version_saved:
        return (
            "This follow-up change did not complete, so I stopped the repeated "
            "attempts. The latest saved storyboard and existing films are "
            "unchanged, and no new production started. Send the request again "
            "and I'll continue from the latest saved version."
        )
    return (
        "This change did not complete. I did not save a new storyboard or "
        "start production, and I stopped the repeated attempts. Send the "
        "request again and I'll retry."
    )


# ---- ask_user 机器 (the ask_user machinery): question / answer ------------
#
# One message row, two states: ``question`` payload present, ``answer`` NULL =
# pending. Pending questions dock above the input; answered ones collapse into
# the flow. At most one pending question per conversation — a newer question
# retires the previous one (bail: superseded). ``content`` keeps the
# question's human text so it enters the LLM context history naturally.


async def _settle_open_questions(
    db: AsyncSession, conversation_id: UUID, answer: AnswerPayload
) -> list[UUID]:
    """Answer every still-open question in one stroke (e.g. supersede).

    A superseded interrupt question (kind=question carrying workflow_run_id)
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
        # Raw-dict read (no pydantic pass): rows stored before the kind
        # convergence still spell "choice" — tolerate both spellings on read,
        # never written.
        if (message.question or {}).get("kind") not in ("question", "choice"):
            continue
        run = await db.get(WorkflowRun, message.workflow_run_id)
        if run is None:
            continue
        if await bail_waiting_interrupt(db, run) is not None:
            bailed_run_ids.append(UUID(str(run.id)))
    return bailed_run_ids


def _match_option(text: str, options: list[Option]) -> Option | None:
    """Deterministic autoResume mapping (zero LLM, prohibited-behavior #4):
    a free-text reply while a question with options is pending maps to an option
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
        # Positional letter — the dock badge renders a/b/c by index, never the
        # raw id (2026-09-10: the LLM may spell ids as slugs like
        # "tech_innovation"), so a typed letter must resolve by position even
        # for older rows whose stored ids are slugs.
        if normalized == chr(ord("a") + index):
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
    payload: QuestionPayload,
    intent: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> tuple[Message, list[UUID]]:
    """Raise a new pending question (ask 落库): at most one pending per
    conversation, so any still-open question retires as superseded first.
    The agent's speech lives in ``content`` — the framing prose when the ask
    brings one (ask 三分解剖 ①), else the bare question — entering the LLM
    context history naturally; the bare question rides the payload's
    ``question`` field (解剖 ② — dock title, QA archive, reminder tail).
    Returns the new message plus the run ids whose parked interrupt was
    cascade-bailed by the supersede (finalized by the caller after its
    commit)."""
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
        blocks=blocks,
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
    """The chain's compact digest — fed to the intent router as the presented
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


async def sync_plan_question(
    db: AsyncSession,
    user_id: UUID,
    project: Project,
    intent: InferredIntent,
    prompt: str,
    reasons: list[str] | None = None,
    derived: list[dict] | None = None,
    brief: Brief | None = None,
    echo: str | None = None,
    estimate: PlanEstimate | None = None,
    plans: list[dict] | None = None,
    need: "ConfirmationNeed | None" = None,
) -> list[UUID]:
    """Keep exactly one pending task_book question per project conversation.

    Called by the chat plan path on every inference (first call and
    refinements alike): a fresh conversation first archives the original
    prompt, any still-open plan question is retired as superseded, and the
    new plan becomes the pending question. The needs_clarification
    ``reasons`` ride in the question's human text (data, localized at render)
    so the archive and the LLM context record WHY confirmation was asked.
    ``brief`` (ADR-052 B3) stamps the merged brief into the question payload
    — the plan card renders the agent's own understanding from it, never a
    blank form. ``estimate`` (BILLING §7) stamps the chain's credits
    quotation (total + per-task marginal, the dry-run compile's fold × the
    live ratio) — the dock pill reads the total, the plan card's task rows
    the per-task prices; None docks quote-less, never blocked. ``echo`` = the
    turn's plan-introduction prose (intent.answer,
    or the stored draft's echo on a code-path re-dock) — since 2026-09-04 it
    IS the row's ``content`` so the echo survives as a real message entity
    (live journey pushes it into the flow before docking; the restore replay
    renders it as the flow line above the answered archive). An empty echo
    stores empty content (the docked card / plan prose are the question's
    face, never a machine digest line). Returns the run ids whose parked
    interrupts were cascade-bailed by the supersede. Flush-only.
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

    # The echo prose IS the question row's content (2026-09-04 echo 实体化):
    # the answered archive renders confirmQuestion and the flow renders this
    # prose as its own message — a machine digest ("Plan ready for
    # confirmation: …") has no seat anywhere anymore.
    content = (echo or "").strip()
    # Reason keys ride the question PAYLOAD (data, localized at render) —
    # never baked into content, which is user-facing prose (the answered
    # question renders it verbatim). The LLM context line re-appends them (keys are
    # the agent's vocabulary).
    # 计划行自完备 (2026-09-08, 方案 B): the chain stamps the row's `intent`
    # column and the derived preview the payload — the docked row IS the
    # whole plan card (the B3 brief stamp's precedent: frozen with the row,
    # re-stamped every dock), and the SSE envelope needs no pending-brief
    # refetch to render it.
    # 授权前移 (ADR-117 §4): the confirmation conjunct is computed ONCE here,
    # at presentation time (prefs + guardrail + the quote fold), and stamped
    # into the payload — the client's pill predicate and the auto-start
    # drive both read this stamp, never a re-derivation. A caller that
    # already computed it (the dock seats, for the echo's held variant)
    # passes it through — one computation per dock.
    if need is None:
        need = await resolve_confirmation_need(db, user_id, estimate)
    version_notice = None
    if need.reason == "unmet_condition":
        version_notice = ("当前版本仍有未落实的修改。可以继续修改，或确认使用当前版本。" if _prefers_zh(prompt) else
                          "The requested changes are incomplete. You can revise further or confirm the current version.")
    elif need.reason == "copy_drift":
        version_notice = ("当前版本的文案与原文有出入。可以恢复原文，或确认使用当前版本。" if _prefers_zh(prompt) else
                          "The copy differs from the original. You can restore it or confirm the current version.")
    _message, bailed_run_ids = await _dock_question(
        db,
        conversation_id,
        content,
        QuestionPayload(
            kind="task_book",
            reasons=reasons or [],
            brief=brief,
            estimate_credits=estimate,
            requires_confirmation=need.requires_confirmation,
            confirm_reason=need.reason,
            quote_high=need.quote_high,
            unquotable=need.unquotable,
            derived=derived or [],            # 决策包阅读层 (iter-2 ③): the Content Plans behind the compiled
            # chain; empty on the router-drafted docks (读容忍).
            plans=plans or [],
        ),
        intent=intent.model_dump(mode="json"),
        blocks=[_system_notice(version_notice)] if version_notice else None,
    )
    return bailed_run_ids


async def _auto_start_docked_plan(
    db: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    project: Project,
    turn_id: UUID | None = None,
    defer_start_commit: bool = False,
) -> tuple[Message, UUID] | None:
    """ADR-117 §2 授权前移 — the auto regime's presentation-time start.

    ADR-139: the auto 道 waives the approval beat, it never manufactures
    the production request — a dock born from a message without production
    intent carries the ``awaiting_production`` stamp and waits here like
    any confirm-owing dock (the Start pill stays as the standing offer).

    Called right after a plan docks. Chat Turn callers pass
    ``defer_start_commit=True`` so the outer Stop fence owns the Run/hold
    commit; the presentation-ACK endpoint retains the default local commit.
    The dock's presentation-time stamp
    (``requires_confirmation``/``quote_high``/``unquotable`` — computed once
    by ``resolve_confirmation_need`` at the dock) is handed back to
    ``evaluate_start_gate`` as the authorization conjunct: a dock that owes
    no confirm beat (both prefs auto, quote under the guardrail, quotable)
    AND a startable lifecycle stamp fire the SAME start machine
    (``answer_question`` kind="start") immediately with
    ``confirmed_via="auto"`` — 呈现即开工, zero new chrome. Returns the
    answered question + run id, or None when the plan stays docked:

    - ``start.needs_confirm`` → the confirm pill's beat (ask modes /
      guardrail / unquotable) — the dock waits for the user's gesture.
    - a structural gate block (material unready, a live run, ...) → the
      dock waits exactly like the ask regime; the user's next beat
      re-drives it.
    - the birthplace's own 422 (credits shortfall / a stale-chain reject)
      → the dock stays; the failure is logged, never swallowed silently.

    A rejected attempt undoes the answer write it made, so the docked
    question's answer cell stays open for the user's later beat.

    ``turn_id`` is supplied only by the runner that docked this plan in the
    current user turn. Presentation-ACK recovery calls without it, so an old
    answered plan can never be re-parented into a newer turn.
    """
    pending_question = await latest_pending_question(db, conversation_id)
    if not is_pending_plan(pending_question):
        return None
    assert pending_question is not None  # is_pending_plan guarantees the row
    pending_video = (project.pending_brief or {}).get("video_presentation") or {}
    raw_tasks = (pending_question.intent or {}).get("tasks") or []
    for raw_task in raw_tasks:
        if raw_task.get("tool") == "produce_video":
            ref = (raw_task.get("params") or {}).get("version_ref") or {}
            if (not pending_video.get("presentation_complete") or any(
                    pending_video.get(k) != ref.get(k)
                    for k in ("composition_id", "composition_version_id", "content_digest"))):
                return None
    payload = QuestionPayload.model_validate(pending_question.question)
    # Read tolerance (PendingPlan._drop_legacy_flags 同款): _create_message
    # stamps every assistant intent with INTERACTION_POLICY_VERSION — an
    # observation key, never part of the router's intent shape; InferredIntent
    # is extra=forbid, so the stamp must be dropped on read-back.
    intent = (
        InferredIntent.model_validate(
            {
                k: v
                for k, v in pending_question.intent.items()
                if k != "interaction_policy_version"
            }
        )
        if isinstance(pending_question.intent, dict)
        else None
    )
    from app.pipeline.lifecycle import (  # deferred: chat → pipeline
        ConfirmationNeed,
        evaluate_start_gate,
        project_lifecycle,
    )
    from app.ui_locale import current_ui_language  # deferred: request ctx

    stamp = await project_lifecycle(
        db,
        project,
        pending_question=pending_question,
        pending_plan=True,
        ui_language=current_ui_language() or "en",
    )
    gate = evaluate_start_gate(
        has_pending_plan=intent is not None,
        effective_tasks_nonempty=bool(intent and intent.tasks),
        stamp=stamp,
        # The authorization conjunct reads the presentation-time stamp
        # verbatim (the gate never re-derives prefs/quote — the docked
        # payload is the single stamp, the client reads the same flag).
        confirmation=ConfirmationNeed(
            requires_confirmation=payload.requires_confirmation,
            reason=payload.confirm_reason,
            quote_high=payload.quote_high,
            unquotable=payload.unquotable,
        ),
        docked_this_turn=True,
        # ADR-129: the film conjuncts hold on the auto 道 too — a review
        # hold or a redesign between dock and this beat keeps the plan
        # docked (the auto start never leaps over them).
    )
    if gate is not None:
        logger.info(
            "auto_start_held",
            project_id=str(project.id),
            code=gate.code,
            reason=gate.reason,
            blockers=list(gate.blockers),
        )
        return None
    try:
        if turn_id is not None:
            # This is the dock born by the current runner, not an answered
            # plan recovered from history. Stamp it BEFORE answer_question so
            # the start commit and any continuation inherit the same identity.
            pending_question.turn_id = turn_id
        answered, _follow_up = await answer_question(
            db,
            user_id,
            UUID(str(pending_question.id)),
            StartAnswerRequest(kind="start"),
            # The run births on standing authorization (ADR-117 §2) — the
            # snapshot records the channel, not an explicit gesture.
            confirmed_via="auto",
            turn_id=turn_id,
            defer_start_commit=defer_start_commit,
        )
    except HTTPException as exc:
        # Undo the answer write whatever the status family — the pre-write
        # raises never reached it (this is then an idempotent no-op), and
        # the post-write family must not leave an answered dock with no
        # run: the birthplace's 422s (credits shortfall / stale-chain
        # reject / a raced structural block) fire after the early answer
        # write by construction, and the gate's post-write 409
        # ``start.no_pending_plan`` would too, should the two plan sources
        # (the question's intent column vs project.pending_brief) ever
        # diverge mid-turn.
        pending_question.answer = None
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
            # The auto 道 must not fail silent: the echo's work-start beat
            # already spoke, no pill renders (requires_confirmation=False),
            # and the ask 道's surfacing (the client grey row off the 422)
            # never fires here — so the reason lands as a persisted system
            # block, keeping live envelope and replay on the same read path.
            pending_question.blocks = [
                *(pending_question.blocks or []),
                _system_notice(_auto_start_rejected_line(
                    exc.detail if isinstance(exc.detail, dict) else None
                )),
            ]
        await db.flush()
        logger.info(
            "auto_start_rejected",
            project_id=str(project.id),
            detail=str(exc.detail)[:200],
        )
        return None
    return answered, UUID(str(answered.workflow_run_id))


async def dock_interrupt_question(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    run_id: UUID,
    content: str,
    payload: QuestionPayload,
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


async def discard_unanswered_plan(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
) -> None:
    """Drop an unanswered task_book question on the ``/generate`` path.

    /generate means the run started WITHOUT the user answering the docked
    question (retries, targeted runs, direct API callers — the overlay's own
    Start always goes through ``answer_question``). No question was
    answered, so the flow must not carry a fabricated answered question — the
    question row is deleted outright. Genuine confirmations (the dock's
    Start button, a prose "looks good, start it") go through
    ``answer_question`` and still collapse into the flow as usual.
    Flush-only — caller commits.
    """
    conversation = await find_conversation(db, user_id, project_id)
    if conversation is None:
        return
    pending = await latest_pending_question(db, UUID(str(conversation.id)))
    if pending is None or (pending.question or {}).get("kind") != "task_book":
        return
    await db.delete(pending)


def _suggestion_ref_for(message: Message, data: AnswerRequest) -> SuggestionRef | None:
    """The trigger suggestion pick's provenance, code-reconstructed at the
    answer endpoint (ADR-099 §4): the answered row IS the source turn and
    the picked option id IS the suggestion id, so no wire change is needed
    on this path — the ref exists only when the row carries suggestion
    records and the answer is an option pick. Freeform / record-less rows
    ride ref-less, exactly as before."""
    if data.kind != "option" or not (message.suggestions or []):
        return None
    return SuggestionRef(
        source_turn=UUID(str(message.id)), suggestion_id=data.option_id
    )


async def _continue_chat_answer(
    db: AsyncSession,
    user_id: UUID,
    conversation: Conversation,
    question: QuestionPayload,
    data: AnswerRequest,
    option_label: str | None,
    *,
    suggestion_ref: SuggestionRef | None = None,
    on_delta=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_interim_prose=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
    turn_id: UUID | None = None,
) -> tuple[Message | None, UUID | None, list[UUID], Any]:
    """The generic question-answer 续聊 continuation: the user's pick is
    their say for the next turn. The archived question and its answer
    enter the model transcript with their respective speaker roles.
    Dispatch: asset_role answers pin by code, brief-slot answers backfill
    user-stated, everything else (ADR-081 trigger suggestions, plain asks)
    rides plan-or-propose by the project's run state. Two seats call this:
    the no-run-id branch and the interrupt branch's not-parked fall-through
    (a trigger suggestion's run id is a display anchor, not a park marker).
    ``suggestion_ref`` (ADR-099 §4): a trigger suggestion pick's provenance,
    code-reconstructed from the answered row (the row IS the source turn,
    the option id IS the suggestion id) — it rides into the turn so the
    pick lands as a named control event, never as fresh anonymous input.
    Returns (follow_up, run_id, bailed_run_ids, extra) — extra is the plan
    path's answered dump or the proposal path's settled question, both
    advisory to the caller."""
    project = await db.get(Project, conversation.project_id)
    say = (
        (data.text if data.kind == "freeform" else None)
        or option_label
        or (" · ".join(answer.text or answer.option_id or "" for answer in data.answers) if data.kind == "group" else "")
    )
    recent = await list_conversation_messages(db, UUID(str(conversation.id)))
    # 输入耐久边界 (the answer continuation's ONE seam — prepare_chat_turn's
    # input-durability commit's mirror): every settle write the answer
    # implies — an asset_role pick's code-settled pins (ADR-078 判词④), a
    # brief-slot answer's user-stated backfill (ADR-052 B2 D2-C1), and the
    # answered row itself — lands in this ONE commit BEFORE the LLM
    # continuation. Two laws ride it: ① the user's answer survives a
    # continuation failure (a turn rollback never revokes a spoken answer);
    # ② uncommitted, the settle write's flush holds the Project row lock to
    # the request boundary, and the design beat's side-session NOWAIT begin
    # reads THIS turn's own lock as contention — a refusal no in-turn retry
    # can clear. The refresh restarts the continuation on committed truth:
    # the seam released the row, and a concurrent request may have moved it
    # in between, so nothing below decides on pre-commit state.
    if project is not None and data.kind == "group":
        _backfill_brief_group(project, question, answers=data.answers)
    elif project is not None and question.slot == "asset_role":
        await _settle_role_answer(db, project, data, say)
    elif project is not None and question.slot is not None:
        _backfill_brief_slot(project, question.slot, say)
    await db.commit()
    if project is not None:
        await db.refresh(project)
    if question.slot == "asset_role" and project is not None:
        # 资产角色消歧的答复落 pin (ADR-078 判词④): the pins settled by
        # CODE above (the option id IS the asset id — _settle_role_answer);
        # the plan path resumes on the pinned plan.
        follow_up, run_id, answered, bailed = await _plan_turn(
            db,
            user_id,
            conversation,
            project,
            ChatRequest(project_id=project.id, message=say),
            recent=recent,
            on_delta=on_delta,
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_interim_prose=on_interim_prose,
            on_loop_event=on_loop_event,
            on_activity=on_activity,
            on_candidates=on_candidates,
            on_row_append=on_row_append,
            turn_id=turn_id,
        )
        return follow_up, run_id, bailed, answered
    if (question.slot is not None or data.kind == "group") and project is not None:
        # ask 一等动作的答复回填 (ADR-052 B2 D2-C1): the brief slot took
        # the answer user-stated at the seam; the plan path resumes on the
        # enriched brief — draft the (now-rooted) plan or ask the next
        # deciding slot. The answer text rides as the turn's message so
        # the router sees it as the user's own words.
        follow_up, run_id, answered, bailed = await _plan_turn(
            db,
            user_id,
            conversation,
            project,
            ChatRequest(project_id=project.id, message=say),
            group_answer_submitted=data.kind == "group",
            recent=recent,
            on_delta=on_delta,
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_interim_prose=on_interim_prose,
            on_loop_event=on_loop_event,
            on_activity=on_activity,
            on_candidates=on_candidates,
            on_row_append=on_row_append,
            turn_id=turn_id,
        )
        return follow_up, run_id, bailed, answered
    # 选项语法统一律 (ADR-081): trigger suggestion questions land here —
    # the picked label is the user's say. Dispatch by the project's run
    # state (the same probe prepare_chat_turn runs): a PRE-FIRST-RUN pick
    # (the understanding-warmed dock) must draft a PLAN — falling into the
    # proposal path would answer a "make me X" pick with proposal tools
    # instead of a plan.
    has_runs = None
    if project is not None:
        has_runs = (
            await db.execute(
                select(WorkflowRun.id)
                .where(WorkflowRun.project_id == project.id)
                .limit(1)
            )
        ).scalar_one_or_none()
    if project is not None and has_runs is None:
        follow_up, run_id, answered, bailed = await _plan_turn(
            db,
            user_id,
            conversation,
            project,
            ChatRequest(
                project_id=project.id, message=say, suggestion_ref=suggestion_ref
            ),
            recent=recent,
            on_delta=on_delta,
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_interim_prose=on_interim_prose,
            on_loop_event=on_loop_event,
            on_activity=on_activity,
            on_candidates=on_candidates,
            on_row_append=on_row_append,
            turn_id=turn_id,
        )
        return follow_up, run_id, bailed, answered
    follow_up, run_id, bailed, settled = await _propose_turn(
        db, user_id, conversation, project, say, [], recent,
        suggestion_ref=suggestion_ref,
        on_delta=on_delta,
        # I-PFA-06 parity (Batch B 验收修复): the chat-path continuation
        # needs the phase pipe too — a film design span on this branch
        # reports its System Status labels through it (and clears them at
        # the span's exit).
        on_phase=on_phase,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_interim_prose=on_interim_prose,
        on_loop_event=on_loop_event,
        on_activity=on_activity,
        on_candidates=on_candidates,
        on_row_append=on_row_append,
        turn_id=turn_id,
    )
    return follow_up, run_id, bailed, settled


def _creative_run_context(pending: PendingPlan | None, context: dict | None) -> dict:
    if (
        pending is None or pending.creative_state is None
        or (context or {}).get("version_ref")
    ):
        return {}
    return {"creative_state": pending.creative_state.model_dump(mode="json")}


async def submit_confirmed_tasks(db, project, pending, tasks, *, name, instruction,
                                 confirmation_id, confirmed_via, quote):
    """Materialize an authorized request and its accounting scope in the caller transaction."""
    from app.pipeline.orchestrator import TaskSpec, create_run, first_task_language
    from app.tools.video.production import latest_video_approval

    pending = pending or PendingPlan()
    run = await create_run(
        db,
        project,
        TaskSpec(
            tasks=tasks,
            video_authorized_by=await latest_video_approval(db, project),
            target_language=first_task_language(tasks) or project.language or "en",
            instruction=instruction or pending.prompt or None,
            persona_id=str(pending.persona_id) if pending.persona_id else None,
            scope="full",
            # Caption mode rides the run context verbatim from
            # the InferredIntent — the chat path's caption-mode
            # question stores it on the intent (RECIPES §4.7).
            # 资产角色 pins (ADR-078 判词④): settled on the
            # PendingPlan by the role question / the mention,
            # riding TaskSpec → run.context verbatim. The panel
            # never edits them (it edits the intent only), so
            # the stored pending's pins are the confirmed ones.
            source_asset_id=pending.source_asset_id,
            exemplar_asset_id=pending.exemplar_asset_id,
            # The router's fresh naming of the plan (ADR-058) —
            # the receipt title and completion line read it.
            name=name or None,
        ),
        reuse_video_production=True,
    )
    _scope_user = await db.get(User, project.user_id)
    _scope_execution, _scope_credits = read_confirmation_prefs(
        _scope_user.settings if _scope_user is not None else None
    )
    run.context = {
        **(run.context or {}),
        **_creative_run_context(pending, run.context),
        "confirmed_scope": {
            "confirmation_id": str(confirmation_id),
            "confirmed_at": datetime.now(UTC).isoformat(),
            "confirmed_via": confirmed_via,
            "compiled_scope": [task.model_dump(mode="json") for task in tasks],
            "quote": quote,
            "settings": {
                "confirm_execution": _scope_execution,
                "confirm_credits": _scope_credits,
                "billing.always_confirm_above": await get_config(
                    db, "billing.always_confirm_above"
                ),
            },
        },
    }
    project.status = ProjectStatus.PROCESSING
    return run


async def answer_question(
    db: AsyncSession,
    user_id: UUID,
    message_id: UUID,
    data: AnswerRequest,
    on_delta=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_interim_prose=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
    confirmed_via: str = "dock_pill",
    turn_id: UUID | None = None,
    defer_start_commit: bool = False,
) -> tuple[Message, Message | None]:
    """Answer a pending question (``POST /chat/messages/{id}/answer``).

    The answer endpoint doubles as the resume mechanism (NAMING: answer =
    resume). Returns the answered question plus the assistant's follow-up
    when the answer continues the conversation. Dispatch by question kind:
    - task_book + bail   → drop the pending brief (project stays a draft;
                           the plan can be re-inferred from the prompt)
    - task_book + start  → start the run from the persisted pending brief
                           (kind "start" is the confirmation — no magic
                           option id; the edited plan rides only on it)
    - question + answer  → record, then continue the conversation: the pick
                           rides into the next intent turn framed with the
                           answered question's bare text (作答语境帧),
                           the follow-up reply comes back here.
                           A brief-ask (payload.slot) backfills the brief
                           user-stated and resumes the BOOK path
    - question + bail    → record only (a graceful exit, never a failure) —
                           except a brief-ask bail, which TAKES the default
                           path: the plan path resumes and docks the
                           draft-from-persona plan (提问策略③)
    A question carrying ``workflow_run_id`` is a direction interrupt
    (期 4): the answer wakes the parked run (spec.answer → node back to
    pending → run back to RUNNING); bail settles the node done, cascade-
    skips the downstream, and the run completes — never failed.

    ``on_delta``/``on_phase`` (answer SSE, 2026-09-04 验收批): the answer's
    continuation is an LLM turn (a slot answer resumes the BOOK path — the
    echo prose generates here), so the endpoint streams like POST /chat;
    these callbacks carry the prose previews / phase labels. None keeps the
    one-shot JSON behavior the pill-Start path uses (no LLM there).

    ``confirmed_via`` (iter-2 ④, ADR-089 §4 R20): the confirmation channel
    stamped into the Confirmed Scope Snapshot — "dock_pill" (the typed
    answer endpoint, the default) or "chat_reply" (the plan path's
    start_run tool answered in prose, N-57).

    ``defer_start_commit`` is only for a Start nested in a caller-owned Chat
    Turn. The Run/hold/answer writes flush but do not commit until the outer
    opening-row Stop fence passes; a worker therefore cannot claim a Run whose
    Turn was retracted/cancelled. Direct answer endpoints keep the commit here.
    """
    if defer_start_commit and data.kind != "start":
        raise ValueError("defer_start_commit is valid only for task_book Start")

    from app.pipeline.orchestrator import (
        bail_waiting_interrupt,
        resume_waiting_interrupt,
    )

    # A nested Start takes the opening-row fence BEFORE the pending-question
    # lock. Stop uses the same opening → transcript order, so the two cannot
    # deadlock; a Stop that arrived first rejects the Start before any Run/hold.
    # If Start arrived first, its outer commit finishes before Stop can proceed.
    if defer_start_commit:
        start_turn_id = turn_id
        if start_turn_id is None:
            turn_ref = await db.get(Message, message_id)
            start_turn_id = turn_ref.turn_id if turn_ref is not None else None
        if start_turn_id is not None:
            await _lock_turn_for_transcript_write(db, start_turn_id)
            # The outer transaction now owns this fence until its one final
            # commit. Independent transcript sessions in the SAME async turn
            # must share that ownership instead of waiting on their owner;
            # Stop arrives in a different context and still takes the lock.
            _TURN_ROW_LOCKS_HELD.set(
                _TURN_ROW_LOCKS_HELD.get() | {start_turn_id}
            )

    media_receipt = await db.get(Message, message_id)
    if media_receipt is not None and (media_receipt.intent or {}).get("media_permission"):
        await _lock_turn_for_transcript_write(db, media_receipt.turn_id)

    # Row lock to the request boundary: a double-clicked Start (or retry)
    # otherwise passes the answer-is-None check concurrently and births two
    # paid runs off one plan. The second waiter re-reads post-commit and
    # hits the 409 below.
    message = await db.get(
        Message, message_id, with_for_update=True, populate_existing=True
    )
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    # A dock answer creates no synthetic user row. Its continuation inherits
    # the answered question's persisted opening-turn association; an explicit
    # caller-owned turn (chat-reply Start) wins when supplied.
    turn_id = turn_id or message.turn_id
    conversation = await db.get(Conversation, message.conversation_id)
    if conversation is None or UUID(str(conversation.user_id)) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if message.question is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Message is not a question")
    question = QuestionPayload.model_validate(message.question)
    if message.answer is not None:
        # D3 (Phase 4 B6): on the confirmation seat the stale-start blocks
        # are machine-readable — a superseded task_book is no longer the
        # current confirmation scope; a re-start is a double gesture.
        if question.kind == "task_book":
            if (message.answer or {}).get("text") == "superseded":
                raise HTTPException(
                    status.HTTP_409_CONFLICT, {"code": "start.scope_mismatch"}
                )
            raise HTTPException(
                status.HTTP_409_CONFLICT, {"code": "start.already_answered"}
            )
        # 普通问题同律 (2026-09-28): a plain question's double-answer is
        # machine-readable too — the raw English string used to leak into
        # the global toast. Superseded = a newer question took the floor
        # (the click raced the re-dock); anything else = a double gesture.
        if (message.answer or {}).get("text") == "superseded":
            raise HTTPException(
                status.HTTP_409_CONFLICT, {"code": "question.superseded"}
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "question.already_answered"}
        )
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

    group_answers = (
        _validate_group_answers(
            question,
            data,
            require_required=data.kind == "group",
        )
        if data.kind == "group" or (data.kind == "bail" and question.items)
        else []
    )
    if group_answers:
        data = data.model_copy(update={"answers": group_answers})
    group_text = " · ".join(answer.text or answer.option_id or "" for answer in group_answers)
    message.answer = AnswerPayload(
        kind=data.kind,
        option_id=data.option_id if data.kind == "option" else None,
        # The answered question shows the option's human label, not its bare id.
        text=(data.text if data.kind == "freeform" else None) or option_label or group_text or None,
        group_digest=(
            data.group_digest
            if data.kind == "group" or (data.kind == "bail" and question.items)
            else None
        ),
        answers=group_answers,
        answered_at=datetime.now(UTC),
    ).model_dump(mode="json")

    follow_up: Message | None = None
    bailed_run_ids: list[UUID] = []
    # 会话层计量 (ADR-117 D3): the continuation branches below are the LLM
    # seats — each binds its own ledger (the elif chain is exclusive) and
    # folds it right there; the row rides this function's own commit.
    _usage_project_id = (
        UUID(str(conversation.project_id))
        if conversation.project_id is not None
        else None
    )

    if (message.intent or {}).get("media_permission"):
        from sqlalchemy import func
        from app.chat.editor_media import answer_media_permission, wait_for_media_result, continue_media_turn
        from app.chat.editor_recovery import editor_lock_key
        from app.models.database import AsyncSessionLocal

        if data.kind not in ("option", "bail"):
            raise HTTPException(422, "Select Allow or Decline.")
        project = await db.get(Project, conversation.project_id)
        try:
            execution = await answer_media_permission(db, project, message, data.option_id == "approve" and data.kind == "option")
        except CreditsInsufficientError as exc:
            raise HTTPException(422, {"code": "credits.insufficient", "balance": exc.balance,
                                      "required": exc.required}) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if execution is not None:
            # The answer row and submission commit together. Keep Stop and history recovery
            # fenced through the wait, without retaining the submission's row locks.
            async with AsyncSessionLocal() as continuation:
                if not await continuation.scalar(select(func.pg_try_advisory_xact_lock(editor_lock_key(turn_id)))):
                    raise HTTPException(409, "The original question is still being saved.")
                opening = await db.get(Message, turn_id)
                opening.turn_state = "in_flight"
                await db.commit()
                execution = await wait_for_media_result(project, execution)
                if on_row_append:
                    await on_row_append(execution)
                follow_up = await continue_media_turn(
                    continuation, project, execution, on_delta=on_delta, on_phase=on_phase,
                    on_tool_call=on_tool_call, on_tool_ready=on_tool_ready, on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event, on_activity=on_activity, on_candidates=on_candidates,
                    on_row_append=on_row_append,
                )
                if follow_up is not None:
                    follow_up = await db.get(Message, follow_up.id, populate_existing=True)
    elif question.kind == "task_book":
        # Project row lock (并发护栏, Message → Project order — the message
        # lock above lands first): a storyboard redesign's BEGIN commits its
        # in-flight marker in its own mini-transaction; without this lock a
        # marker landing between the gate facts below and the run birth
        # would race the Start. The design beat's begin takes the row
        # NOWAIT, so a Start holding it wins the race (旧 run 有效) and the
        # loser fails closed on re-read.
        project = await db.get(
            Project, conversation.project_id, with_for_update=True
        )
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        if data.kind == "bail":
            # Graceful exit: the unconfirmed plan is dropped, the project
            # stays a draft and the prompt stays in the conversation — the
            # setup can be reopened any time. Never a failure. The plan's
            project.pending_brief = None
        else:
            # kind == "start" (the only other kind a task_book accepts).
            pending = (
                PendingPlan.model_validate(project.pending_brief)
                if isinstance(project.pending_brief, dict)
                else None
            )
            # The review panel's edited plan wins over the stored
            # pending brief — panel edits must reach the run they confirm.
            # Panel edits ARE task-list mutations (ADR-043): the same data
            # structure the LLM proposes, so the confirmed chain ships
            # verbatim — no merge machinery.
            intent = (data.intent or pending.intent) if pending is not None else None
            tasks = list(intent.tasks) if intent is not None else []
            # D3 (Phase 4 B6): the Start seat enforces the SAME four-
            # conjunction lifecycle truth the client reads (门禁三) — "the
            # button is disabled" is the first line, never the only one.
            # The structural guards (no pending plan / empty chain) and the
            # projection verdict (material / adjudication / prerequisite /
            # active conflicting run) all surface as machine-readable codes
            # before paid create_run, never as disguised business errors.
            from app.pipeline.lifecycle import (  # deferred: chat → pipeline
                evaluate_start_gate,  # only, one-directional
                project_lifecycle,
            )
            from app.ui_locale import current_ui_language  # deferred

            stamp = await project_lifecycle(
                db,
                project,
                pending_question=message,
                # The branch guarantees task_book — pass the plan flag
                # directly: the answer write above precedes this dispatch,
                # so is_pending_plan (which requires an UNANSWERED row)
                # always reads False here and would flip the gatherer into
                # its prerequisite branch, blocking every Start.
                pending_plan=True,
                ui_language=current_ui_language() or "en",
            )
            gate = evaluate_start_gate(
                has_pending_plan=intent is not None,
                effective_tasks_nonempty=bool(tasks),
                stamp=stamp,
                # ADR-129: the film conjuncts — active draft, presented-draft
                # match (token / fingerprint), review hold.
            )
            if gate is not None:
                detail: dict[str, Any] = {"code": gate.code}
                if gate.blockers:
                    detail["blockers"] = list(gate.blockers)
                raise HTTPException(gate.http_status, detail)
            try:
                # Entry constraints (clips-media gate included) reject at the
                # birthplace — ValueError here is a client-facing 422.
                # target_language is a pure fallback (language is a per-task
                # param): derive it from the first task that carries one.
                if not (intent.name or "").strip():
                    # Same observability seat as _create_run_from_tasks
                    # (ADR-058): the plan SHOULD carry the router's name.
                    logger.info(
                        "unnamed_proposal", path="plan_start",
                        project_id=str(project.id),
                    )
                run = await submit_confirmed_tasks(
                    db, project, pending, tasks, name=intent.name, instruction=intent.specific_instruction,
                    confirmation_id=message.id, confirmed_via=confirmed_via,
                    quote=(message.question or {}).get("estimate_credits"),
                )
            except ToolRejected as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
                ) from exc
            except CreditsInsufficientError as exc:
                # Same structured shortfall payload as the typed /generate
                # endpoint (BILLING §7) — the dock renders the grey row off
                # {code, balance, required}. BEFORE ValueError (it subclasses it).
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    {
                        "code": "credits.insufficient",
                        "balance": exc.balance,
                        "required": exc.required,
                    },
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
                ) from exc
            project.pending_brief = None
            message.workflow_run_id = run.id


    elif question.kind == "question" and message.workflow_run_id is not None:
        # Direction interrupt (期 4) — but the run-id column alone does NOT
        # prove one: a run_completed trigger's suggestion question also
        # carries it as the display anchor (trigger_turn stamps it for the
        # canvas/rerun references), and _suggestions_payload's contract is
        # "no run marker — the generic continuation carries the pick". The
        # real marker is a node PARKED in waiting. Answering a trigger pill
        # through the interrupt seat used to no-op (resume → "idle" → zero
        # continuation — the live-acceptance dead-exit red 2026-09-24); the
        # pick now falls through to the generic 续聊 branch below.
        run = await _parked_interrupt_run(db, message.workflow_run_id)
        if run is not None:
            if data.kind == "bail":
                if await bail_waiting_interrupt(db, run) is not None:
                    bailed_run_ids.append(UUID(str(run.id)))
            else:
                outcome = await resume_waiting_interrupt(db, run, message.answer)
                if outcome == "blocked":
                    follow_up = await _create_message(
                        db,
                        UUID(str(conversation.id)),
                        "assistant",
                        _resume_ack_line("", "blocked"),
                        turn_id=turn_id,
                    )
        elif data.kind in ("option", "freeform", "group"):
            # No parked node → this run id was the display anchor (trigger
            # suggestion) or the interrupt already expired — the pick is the
            # user's say, carried by the generic continuation (same seat as
            # the no-run-id branch below).
            with bind_conversation_turn(
                conversation_id=conversation.id, turn_id=turn_id or message.id,
                project_id=conversation.project_id,
            ) as _usage_bind:
                follow_up, _run_id, bailed_run_ids, _settled = (
                    await _continue_chat_answer(
                        db, user_id, conversation, question, data, option_label,
                        suggestion_ref=_suggestion_ref_for(message, data),
                        on_delta=on_delta,
                        on_phase=on_phase,
                        on_tool_call=on_tool_call,
                        on_tool_ready=on_tool_ready,
                        on_interim_prose=on_interim_prose,
                        on_loop_event=on_loop_event,
                        on_activity=on_activity,
                        on_candidates=on_candidates,
                        on_row_append=on_row_append,
                        turn_id=turn_id,
                    )
                )
            await fold_conversation_usage(
                db,
                user_id=user_id,
                project_id=_usage_project_id,
                accrued=_usage_bind.accrued,
            )

    elif question.kind == "question" and data.kind in ("option", "freeform", "group"):
        # 续聊: the answer unblocks the conversation — the user's pick is
        # their say for the next turn, with the answered question in context.
        with bind_conversation_turn(
            conversation_id=conversation.id, turn_id=turn_id or message.id,
            project_id=conversation.project_id,
        ) as _usage_bind:
            follow_up, _run_id, bailed_run_ids, _extra = (
                await _continue_chat_answer(
                    db,
                    user_id,
                    conversation,
                    question,
                    data,
                    option_label,
                    suggestion_ref=_suggestion_ref_for(message, data),
                    on_delta=on_delta,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                    turn_id=turn_id,
                )
            )
        await fold_conversation_usage(
            db,
            user_id=user_id,
            project_id=_usage_project_id,
            accrued=_usage_bind.accrued,
        )

    elif question.kind == "question" and data.kind == "bail" and (question.slot is not None or question.items):
        # 默认路径 (提问策略③ / D2-C2): skipping a brief ask TAKES the default
        # path — the plan path resumes. A group preserves its explicitly
        # selected answers and fills only the remaining fields with defaults.
        project = await db.get(Project, conversation.project_id)
        if project is not None:
            if question.items:
                _backfill_brief_group(project, question, group_answers)
                await _apply_website_promo_group_defaults(db, project)
            if question.slot == "asset_role":
                # 判词④'s promised default, kept by code: skip = upload
                # order — first video the material, the next the exemplar
                # (the default_path copy's exact promise).
                await _settle_default_role_pins(db, project)
            # 输入耐久边界 (_continue_chat_answer's seam, the bail branch's
            # seat): the bail answer + the default pins commit BEFORE the
            # plan turn — the design beat's NOWAIT begin must never meet
            # this turn's own row lock, and the user's bail survives a
            # continuation failure.
            await db.commit()
            await db.refresh(project)
            recent = await list_conversation_messages(db, UUID(str(conversation.id)))
            with bind_conversation_turn(
                conversation_id=conversation.id, turn_id=turn_id or message.id,
                project_id=conversation.project_id,
            ) as _usage_bind:
                follow_up, _run_id, _answered, bailed_run_ids = await _plan_turn(
                    db,
                    user_id,
                    conversation,
                    project,
                    ChatRequest(
                        project_id=project.id,
                        message=(
                            "(The user skipped my question — take the default "
                            "path and draft the plan.)"
                        ),
                    ),
                    recent=recent,
                    on_delta=on_delta,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                    turn_id=turn_id,
                )
            await fold_conversation_usage(
                db,
                user_id=user_id,
                project_id=_usage_project_id,
                accrued=_usage_bind.accrued,
            )

    if defer_start_commit:
        # The outer Chat Turn's final opening-row fence owns the only commit.
        # Until then this Run/hold is invisible to workers and Stop can roll it back.
        await db.flush()
    else:
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
    skill: SkillReference | None = None,
    skill_ambiguity: list[str] | None = None,
    recent: list[Message] | None = None,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_interim_prose=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
    turn_id: UUID | None = None,
    group_answer_submitted: bool = False,
    authorized_media: Message | None = None,
) -> tuple[Message | None, UUID | None, Message | None, list[UUID]]:
    """Plan path (intent-surface-unification W1): build / refine / confirm
    the plan inside the chat loop — the ONLY intent surface.

    Entered for project-scope turns while a plan is pending (refine or
    prose confirmation) or before the project's first run (first turn / after
    a bail). Returns the assistant message (the docked/answered question row
    for draft/ask/start; None when the turn closes without a row — the
    degrade paths land their own shape), the started run
    id, the answered task-book question
    (for ChatResponse.answered_question), and cascade-bailed run ids. The
    caller owns the single Stop-fenced commit, including the Start branch.

    ADR-077 判词② (2026-09-14): the dispatch retired into the tool
    loop — this body is a shim; the turn lives in ``app/chat/plan_turn.py``
    (the intent router's terminal tools present_plan / ask_user / start_run /
    answer, guardrails inside the executions). Deferred import: the runner
    imports THIS module's machinery (the ask_user machinery, the docks, the
    gate texts).
    """
    from app.chat.plan_turn import run_plan_turn

    return await run_plan_turn(
        db,
        user_id,
        conversation,
        project,
        request,
        skill=skill,
        skill_ambiguity=skill_ambiguity,
        recent=recent,
        group_answer_submitted=group_answer_submitted,
        authorized_media=authorized_media,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_phase=on_phase,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_interim_prose=on_interim_prose,
        on_loop_event=on_loop_event,
        on_activity=on_activity,
        on_candidates=on_candidates,
        on_row_append=on_row_append,
        turn_id=turn_id,
    )


async def _propose_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation: Conversation,
    project: Project | None,
    text: str,
    mentions: list[ChatMention],
    recent: list[Message],
    skill: SkillReference | None = None,
    skill_ambiguity: list[str] | None = None,
    suggestion_ref: SuggestionRef | None = None,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_interim_prose=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
    turn_id: UUID | None = None,
) -> tuple[Message | None, UUID | None, list[UUID], Message | None]:
    """One assistant turn after the user input is settled (CHAT_ARCH §3).

    Shared by ``chat()`` and the choice-answer continuation in
    ``answer_question`` (the answer endpoint doubles as resume). Returns the
    assistant message (None when the turn closes without a row — the
    degrade paths land their own shape), the dispatched
    run id if any, the run ids whose parked
    interrupt was cascade-bailed, and the pending question this turn settled
    by judgment (ADR-053 R2). Flush-only — the caller commits.

    ADR-077 判词② (2026-09-14): the dispatch retired into the tool
    loop — this body is a shim; the turn lives in ``app/chat/propose_turn.py``
    (the chat intent agent's terminal tools propose_tasks / edit_output /
    revise_output / edit_graph / ask_user / answer + the iter-3 S2
    exploration verbs).
    Deferred import: the runner imports THIS module's machinery.
    """
    from app.chat.propose_turn import run_propose_turn

    return await run_propose_turn(
        db,
        user_id,
        conversation,
        project,
        text,
        mentions,
        recent,
        skill=skill,
        skill_ambiguity=skill_ambiguity,
        suggestion_ref=suggestion_ref,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_phase=on_phase,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_interim_prose=on_interim_prose,
        on_loop_event=on_loop_event,
        on_activity=on_activity,
        on_candidates=on_candidates,
        on_row_append=on_row_append,
        turn_id=turn_id,
    )


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
    skill: SkillReference | None = None
    skill_ambiguity: list[str] | None = None


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

    # Serialize opening admissions, including a manual send racing the Home
    # handoff. This transaction ends at the existing input-durability commit.
    from sqlalchemy import func

    await db.execute(select(func.pg_advisory_xact_lock(
        request.project_id.int % (1 << 63)
    )))
    conversation = await _get_or_create_project_conversation(
        db, user_id, request.project_id
    )
    conversation_id = UUID(str(conversation.id))
    if request.first_message:
        # The sequence counter also survives a zero-visible Stop retraction.
        # Allocate the opener's sequence in this transaction so an admission
        # failure before commit cannot consume the handoff.
        counter = await db.get(MessageSeqCounter, conversation_id)
        opening = await db.scalar(select(Message.id).where(
            Message.conversation_id == conversation_id, Message.role == "user"
        ).limit(1))
        if counter is not None or opening is not None:
            raise HTTPException(409, detail={"code": "chat.already_opened"})
        db.info.setdefault(_FRESH_CONVERSATIONS_INFO, set()).add(conversation_id)
    from app.chat.editor_recovery import recover_interrupted_edits
    await recover_interrupted_edits(db, conversation_id)
    # Worker-born speech and deterministic chrome inherit this locale owner;
    # plan/chat instead infer speech from user messages and history. None-safe:
    # outside a request there is nothing to stamp, and a worker path never
    # erases the owner.
    from app.ui_locale import current_ui_language  # deferred: request ctx

    _ui = current_ui_language()
    if _ui:
        conversation.ui_language = _ui
    # 环境能力位盖章 (ADR-118 §6 — ui_language owner 同律座): the request's
    # raw can-host-canvas bit is the conversation's ONE environment fact —
    # the worker-born delivery turn (run_trigger_turn) inherits it for
    # canvas_visible (app/chat/canvas_visibility.py). None-safe, last-wins:
    # an unreporting client never erases the known bit.
    if request.canvas_available is not None:
        conversation.canvas_available = request.canvas_available

    from app.skills.resolution import SkillResolutionError, resolve_chat_skill
    from app.skills.store import SkillNotFoundError

    prior_skill_references: list[SkillReference] | None = None
    inherited_skill: SkillReference | None = None
    inherited_binding = False
    if request.skill is None:
        previous_users = list((await db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
                Message.turn_state == "settled",
            )
            .order_by(Message.seq.desc().nullslast(), Message.created_at.desc())
            .limit(32)
        )).all())
        from pydantic import TypeAdapter

        previous_with_ambiguity = next(
            (row for row in previous_users if (row.intent or {}).get("skill_ambiguity")),
            None,
        )
        raw_prior = (
            (previous_with_ambiguity.intent or {}).get("skill_ambiguity")
            if previous_with_ambiguity is not None else None
        )
        if isinstance(raw_prior, list):
            try:
                prior_skill_references = TypeAdapter(
                    list[SkillReference]
                ).validate_python(raw_prior)
            except ValueError:
                prior_skill_references = None
        from app.models.tables import Composition, CompositionVersion

        saved_version = await db.scalar(
            select(CompositionVersion.id)
            .join(Composition, CompositionVersion.composition_id == Composition.id)
            .where(
                Composition.origin_project_id == conversation.project_id,
                Composition.owner_id == user_id,
            )
            .limit(1)
        )
        if saved_version is None:
            from app.chat.conversation_context import context_items

            active_draft = any(
                (item.get("candidate") or {}).get("active", True)
                and item.get("target_tool") == "design_video"
                and '"draft_id"' in str(item.get("text") or "")
                for item in context_items(conversation.context)
            )
            for index, previous_user in enumerate(previous_users):
                if index and not active_draft:
                    break
                intent = previous_user.intent or {}
                raw_skill = intent.get("skill")
                if raw_skill is None or intent.get("skill_binding") == "inherited":
                    continue
                try:
                    inherited_skill = TypeAdapter(SkillReference).validate_python(raw_skill)
                except ValueError:
                    inherited_skill = None
                break

    try:
        skill_resolution = await resolve_chat_skill(
            db,
            owner_id=user_id,
            reference=request.skill,
            message=request.message,
            prior_references=prior_skill_references,
        )
        if (
            request.skill is None
            and inherited_skill is not None
            and skill_resolution.reference is None
            and not skill_resolution.ambiguous
        ):
            inherited_binding = True
            skill_resolution = await resolve_chat_skill(
                db,
                owner_id=user_id,
                reference=inherited_skill,
                message=request.message,
            )
    except (SkillResolutionError, SkillNotFoundError) as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "skill.unavailable", "message": str(exc)},
        ) from None

    user_message = await _create_message(
        db,
        conversation_id,
        "user",
        request.message,
        attachments=[a.model_dump(mode="json") for a in request.attachments],
        mentions=[m.model_dump(mode="json") for m in request.mentions],
        intent=(
            {
                "skill": skill_resolution.reference.model_dump(mode="json"),
                **({"skill_binding": "inherited"} if inherited_binding else {}),
            }
            if skill_resolution.reference is not None
            else {
                "skill_ambiguity": [
                    option.reference.model_dump(mode="json")
                    for option in skill_resolution.ambiguous
                ]
            }
            if skill_resolution.ambiguous
            else None
        ),
        suggestion_ref=(
            request.suggestion_ref.model_dump(mode="json")
            if request.suggestion_ref is not None
            else None
        ),
        # focus_output 写退役 (ADR-058): pointing at a product is an @mention
        # now; old rows keep their stored focus_output (读容忍 — the history
        # replay still renders their gray prefix row), new rows never write it.
    )
    # Turn identity, first beat (交互完整性批 A): the user row owns the
    # turn's in-flight marker from HERE, and prepare's own commit below makes
    # it durable BEFORE the agent turn runs — input durability is never again
    # bound to the turn's outcome (the 2026-09-16 incident: a mid-turn death
    # rolled the user's words back with everything else, and the racing
    # trigger read an empty conversation). The turn's final commit stamps
    # 'settled'; failure stamps 'failed', explicit Stop settles atomically at
    # the client-visible frontier (cancelled/retracted).
    user_message.turn_state = "in_flight"

    project = await _load_project(db, UUID(str(conversation.project_id)))
    history = await list_conversation_messages(db, conversation_id)
    # Deterministic autoResume (zero LLM): while a question is pending,
    # the user's free text settles it ONLY on an unambiguous option hit
    # (letter / number / verbatim label — ADR-053: the "any text =
    # freeform answer" masking is retired; every other message is judged
    # by the intent router / chat intent agent in context, and only a
    # judged answer settles the row — an interjection leaves it pending
    # and the reply gets the reminder tail). A pending task_book
    # (unconfirmed plan) never resumes here: its answers are the dock's
    # Start and plan-path refinements below.
    answered_question: Message | None = None
    pending = await latest_pending_question(db, conversation_id)
    if pending is not None:
        pending_payload = QuestionPayload.model_validate(pending.question)
        if pending_payload.kind == "question":
            matched = _match_option(request.message, pending_payload.options)
            if matched is not None:
                pending.answer = AnswerPayload(
                    kind="option",
                    option_id=matched.id,
                    text=matched.label,
                    answered_at=datetime.now(UTC),
                ).model_dump(mode="json")
                answered_question = pending
                # The durable user row owns its turn; this explicit association
                # lets live and history suppress only its duplicate option bubble.
                user_message.intent = {
                    **(user_message.intent or {}),
                    "answered_question_id": str(pending.id),
                }
            if (
                answered_question is not None
                and pending_payload.slot is not None
                and project is not None
                and answered_question.workflow_run_id is None
            ):
                # ask 一等动作的 autoResume 回填 (ADR-052 B2 D2-C1): same
                # user-stated backfill as the answer endpoint — the plan
                # path dispatch below then re-judges on the enriched brief.
                _backfill_brief_slot(
                    project,
                    pending_payload.slot,
                    (pending.answer or {}).get("text") or request.message,
                )
            await db.flush()

    from app.chat.video_turn_seats import short_video_confirmation

    if not (request.attachments or request.mentions or request.skill):
        confirmation = await short_video_confirmation(
            db, project, conversation_id, request.message, pending,
        )
        if confirmation is not None:
            user_message.intent = {**(user_message.intent or {}), "video_confirmation": confirmation}

    interrupt_reply: Message | None = None
    plan_path = False
    parked_interrupt_run: WorkflowRun | None = None
    if answered_question is not None and answered_question.workflow_run_id is not None:
        # A run id alone is only a display anchor on trigger suggestions.
        # Match the answer endpoint: only a genuinely PARKED step takes the
        # interrupt wake; otherwise the user's words continue through chat.
        candidate_run = await _parked_interrupt_run(
            db, answered_question.workflow_run_id
        )
        if candidate_run is not None:
            parked_interrupt_run = candidate_run
    if parked_interrupt_run is not None:
        assert answered_question is not None
        # Interrupt autoResume (期 4): a typed answer to the docked direction
        # question takes the same dispatch as the answer endpoint — wake the
        # parked run. No LLM turn on top: the wake IS the continuation (the
        # step flow shows the run resuming), so the acknowledgment is a
        # deterministic line. R1 B3: a blocked arbitration (another run
        # holds the authority) speaks the parked line instead.
        from app.pipeline.orchestrator import resume_waiting_interrupt

        outcome = await resume_waiting_interrupt(
            db, parked_interrupt_run, answered_question.answer
        )
        decided = (answered_question.answer or {}).get("text") or (
            answered_question.answer or {}
        ).get("option_id") or ""
        interrupt_reply = await _create_message(
            db,
            conversation_id,
            "assistant",
            _resume_ack_line(decided, outcome),
            turn_id=user_message.id,
        )
    else:
        # Plan path dispatch (intent-surface-unification W1): this endpoint is
        # the ONLY intent surface. A turn goes to the plan path (plan
        # build / refine / confirm via the intent router) while a plan is
        # pending or before the project's first run; everything else goes to
        # the four-state proposer. (Conversations are project-scope only —
        # ADR-041 D8.)
        if project is not None:
            if is_pending_plan(pending):
                plan_path = True
            elif (
                answered_question is not None
                and isinstance(answered_question.question, dict)
                and answered_question.question.get("slot")
            ):
                # ask 一等动作的答复回 plan path (D2-C1): the backfill already
                # landed above — the plan path re-judges on the enriched
                # brief (draft the rooted plan, or ask the next slot).
                plan_path = True
            elif (
                not isinstance(project.pending_brief, dict)
                or project.pending_brief.get("intent") is None
            ):
                # A brief-only pending_brief row (an ask-turn write) keeps
                # the pre-run probe — the project is still in its plan phase.
                has_runs = (
                    await db.execute(
                        select(WorkflowRun.id)
                        .where(WorkflowRun.project_id == project.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                plan_path = has_runs is None

    # Input durability commit (交互完整性批 A): everything above is
    # deterministic and COMPLETE at this point — the conversation, the
    # durable user row (turn_state='in_flight'), a deterministic autoResume
    # settle, the interrupt wake. It commits NOW, before the agent turn:
    # entry-cap 4xx above still reject pre-persistence (nothing to roll
    # back), but from here on the request is received, provably. The agent
    # turn's own writes land in execute_chat_turn's commit.
    await db.commit()

    # 标记随这次 commit 死亡: the fresh-conversation mark's only purpose
    # was the counter row's FK on an uncommitted parent — this commit lands
    # both rows, so later allocations on this (still-open) session must take
    # the short-transaction path like every established conversation.
    # Leaving the mark would route the turn's own allocs in-transaction,
    # holding the counter row lock until turn end — and the activity
    # persister's fresh-session alloc then self-deadlocks against it
    # (PG's detector can't see the app-side await closing the cycle).
    db.info.get(_FRESH_CONVERSATIONS_INFO, set()).discard(conversation_id)

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
        skill=skill_resolution.reference,
        skill_ambiguity=[
            f"{option.name} v{option.version_number}"
            if option.version_number is not None
            else option.name
            for option in skill_resolution.ambiguous
        ] or None,
    )


class TurnStopped(Exception):
    """A Stop decision won before this transcript/final-commit write."""


# Dynamic lock ownership, scoped to one async Chat Turn. A nested Start holds
# the opening-row DB lock through the outer final commit; its independent
# transcript sessions must not re-acquire that lock from their own owner.
# Other requests (notably Stop) have a different context and still serialize
# on the database row. execute_chat_turn restores the previous value on exit.
_TURN_ROW_LOCKS_HELD: ContextVar[frozenset[UUID]] = ContextVar(
    "turn_row_locks_held", default=frozenset()
)


def _scope_turn_row_lock_ownership(fn):
    """Clear this turn's shared lock ownership on commit, rollback or error."""
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        inherited = _TURN_ROW_LOCKS_HELD.get()
        try:
            return await fn(*args, **kwargs)
        finally:
            _TURN_ROW_LOCKS_HELD.set(inherited)

    return wrapped


async def _lock_turn_for_transcript_write(
    db: AsyncSession,
    turn_id: UUID,
    *,
    require_in_flight: bool = False,
) -> Message:
    """Fence every independently committed turn-owned transcript write.

    Answer continuations may legitimately append to an already settled opening
    Turn, so only Stop is forbidden by default. Partial prose and the final
    commit additionally require the opening Turn to remain in flight.
    ``populate_existing`` is load-bearing: this session may have loaded the row
    before waiting for its lock, and the post-wait database state must win.
    When the outer nested-Start transaction already owns the fence, a fresh
    transcript session in that same async context reads without re-locking:
    its owner still excludes Stop, while a second lock request would wait on
    the owner itself and prevent the outer commit forever.
    """
    query = (
        select(Message)
        .where(Message.id == turn_id)
        .execution_options(populate_existing=True)
    )
    if turn_id not in _TURN_ROW_LOCKS_HELD.get():
        # FOR NO KEY UPDATE still serializes Stop, final commit and transcript
        # writers, but permits the FOR KEY SHARE check made by INSERTs whose
        # messages.turn_id references this opening row. Full FOR UPDATE makes
        # an independent transcript Session wait on its own outer Start.
        query = query.with_for_update(key_share=True)
    row = (await db.execute(query)).scalar_one_or_none()
    if (
        row is None
        or row.turn_state in {"cancelled", "retracted"}
        or bool((row.intent or {}).get("stop_requested_at"))
        or (require_in_flight and row.turn_state != "in_flight")
    ):
        raise TurnStopped(str(turn_id))
    return row


async def _lock_turn_for_final_commit(db: AsyncSession, turn_id: UUID) -> Message:
    return await _lock_turn_for_transcript_write(
        db, turn_id, require_in_flight=True
    )


async def persist_interim_prose(
    db: AsyncSession,
    conversation_id: UUID,
    turn_id: UUID,
    text: str,
) -> Message:
    """Persist one middle-of-Turn prose row and replace its trailing partial."""
    await _lock_turn_for_transcript_write(db, turn_id)
    await db.execute(
        delete(Message).where(
            Message.turn_id == turn_id,
            Message.intent["type"].astext == "partial",
        )
    )
    return await _create_message(
        db,
        conversation_id,
        "assistant",
        text,
        intent={"type": "interim_prose"},
        turn_id=turn_id,
    )


async def persist_partial_prose(
    db: AsyncSession,
    conversation_id: UUID,
    turn_id: UUID,
    text: str,
    *,
    message_id: UUID | None = None,
) -> Message:
    """Append an emitted delta to the Turn's one server-owned trailing row."""
    await _lock_turn_for_transcript_write(db, turn_id, require_in_flight=True)
    if message_id is None:
        return await _create_message(
            db,
            conversation_id,
            "assistant",
            text,
            intent={"type": "partial"},
            turn_id=turn_id,
        )
    message = await db.get(Message, message_id)
    if (
        message is None
        or message.turn_id != turn_id
        or (message.intent or {}).get("type") != "partial"
    ):
        raise TurnStopped(str(turn_id))
    message.content = (message.content or "") + text
    await db.flush()
    await db.refresh(message)
    return message


def _interim_prose_callback(
    db, conversation_id, on_interim_prose=None, turn_id: UUID | None = None
):
    """Persist interim prose before exposing its stable row identity on SSE."""
    async def _emit(text: str) -> None:
        if on_interim_prose is None:
            if turn_id is None:
                await _create_message(
                    db, conversation_id, "assistant", text,
                    intent={"type": "interim_prose"}, turn_id=turn_id,
                )
            else:
                await persist_interim_prose(db, conversation_id, turn_id, text)
            return

        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as interim_db:
            message = await persist_interim_prose(
                interim_db, conversation_id, turn_id, text
            )
            await interim_db.commit()
        result = on_interim_prose(
            text,
            message.created_at.isoformat(),
            str(message.id),
            message.seq,
        )
        if result is not None:
            await result

    return _emit


async def stop_turn_at_visible_frontier(
    db: AsyncSession,
    user_message_id: UUID,
    frontier: ChatTurnStopRequest,
) -> str:
    """Atomically settle Stop at the client's actually visible boundary."""
    row = (
        await db.execute(
            select(Message)
            .where(Message.id == user_message_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        return "retracted"
    if row.turn_state != "in_flight":
        # A missing state is terminal for Stop purposes: never abort or
        # retract a Turn whose authoritative state is not explicitly in flight.
        return row.turn_state or "failed"

    # Collect the complete set BEFORE deleting anything: the self-FK must never
    # detach a child and hide it from the retraction sweep.
    turn_rows = list((
        await db.execute(
            select(Message).where(
                or_(Message.id == user_message_id, Message.turn_id == user_message_id)
            )
        )
    ).scalars().all())
    assistant_rows = [message for message in turn_rows if message.id != user_message_id]
    by_id = {message.id: message for message in assistant_rows}

    visible_prefix: dict[UUID, int] = {}
    for item in frontier.prose:
        message = by_id.get(item.message_id)
        if message is None:
            continue
        count = min(item.visible_chars, len(message.content or ""))
        visible_prefix[message.id] = max(count, visible_prefix.get(message.id, 0))
    visible_activity = {
        message_id
        for message_id in frontier.activity_ids
        if (message := by_id.get(message_id)) is not None
        and (message.intent or {}).get("type") == ACTIVITY_ROW_TYPE
    }
    visible_structure = {
        message_id
        for message_id in frontier.structure_ids
        if (message := by_id.get(message_id)) is not None
        and (
            bool(message.blocks)
            or bool(message.question)
            or (message.intent or {}).get("type") == "candidates_log"
        )
    }
    visible_prose = {
        message_id
        for message_id, count in visible_prefix.items()
        if (by_id[message_id].content or "")[:count].strip()
    }

    from app.chat.conversation_context import discard_turn_context
    await discard_turn_context(db, row.conversation_id, user_message_id)

    media_rows = {m.id for m in assistant_rows if (m.intent or {}).get("editor_media")
                 and (m.workflow_run_id or (m.intent or {}).get("media_result"))}
    if media_rows:
        from app.pipeline.orchestrator import cancel_run
        project_id = await db.scalar(select(Conversation.project_id).where(Conversation.id == row.conversation_id))
        project = await db.get(Project, project_id, with_for_update=True)
        for message_id in media_rows:
            run_id = by_id[message_id].workflow_run_id
            if run_id is not None:
                run = await db.get(WorkflowRun, run_id, with_for_update=True, populate_existing=True)
                if run and run.project_id == project.id:
                    await cancel_run(db, run, project)
    members = {m.id for m in assistant_rows if ((m.intent or {}).get("frame") or {}).get("group_id")}
    committed = bool(members) or bool((row.intent or {}).get("editor_commits")) or bool(media_rows)
    if not committed and not visible_prose and not visible_activity and not visible_structure:
        await db.execute(
            delete(Message)
            .where(Message.id.in_([message.id for message in turn_rows]))
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        return "retracted"

    now = datetime.now(UTC).isoformat()
    keep_ids = visible_prose | visible_activity | visible_structure | media_rows | members
    delete_ids = [message.id for message in assistant_rows if message.id not in keep_ids]
    if delete_ids:
        await db.execute(
            delete(Message)
            .where(Message.id.in_(delete_ids))
            .execution_options(synchronize_session=False)
        )
    for message_id in keep_ids - media_rows:
        message = by_id[message_id]
        prefix = visible_prefix.get(message_id, 0)
        if message.content is not None:
            message.content = message.content[:prefix]
        if message_id not in visible_structure:
            message.blocks = []
            message.question = None
            message.answer = None
            message.suggestions = []
        if message_id in visible_activity or message_id in members:
            frame = dict((message.intent or {}).get("frame") or {})
            if frame.get("status") == "active":
                if message_id in members:
                    frame["call_state"] = "not_executed" if frame.get("call_state") == "queued" else "cancelled"
                frame.update({"status": "cancelled", "cancelled_at": now})
                message.intent = {"type": ACTIVITY_ROW_TYPE, "frame": frame}
    row.intent = {
        **(row.intent or {}),
        "stop_requested_at": now,
        "stop_visible": frontier.model_dump(mode="json"),
    }
    if committed:
        from app.chat.editor_recovery import report_committed_edits
        await report_committed_edits(db, row)
    row.turn_state = "cancelled"
    await db.commit()
    return "cancelled"


async def settle_interrupted_turn(
    user_message_id: UUID,
    conversation_id: UUID,
) -> str | None:
    """Idempotently clean up an unexpected disconnect.

    Stop has already been settled atomically by its control endpoint. This path
    never re-derives cancelled versus retracted from durable database content.
    """
    from app.models.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(Message, user_message_id, with_for_update=True)
            if row is None:
                return None
            if row.turn_state != "in_flight":
                return row.turn_state
            from app.chat.editor_recovery import report_committed_edits
            await report_committed_edits(db, row)
            row.turn_state = "failed"
            await db.commit()
            return "failed"
    except Exception as e:  # noqa: BLE001 — teardown is best-effort
        logger.warning(
            "turn_interrupted_settle_error",
            message_id=str(user_message_id),
            error=str(e),
        )
        return None


async def stamp_turn_failed(user_message_id) -> None:
    """Best-effort 'failed' stamp for a dead turn's durable user row (交互
    完整性批 A) — a FRESH session, because the turn's own is tearing down /
    already rolled back. Never raises: a missed stamp is covered by the
    admission gate's stale bound (an ancient in_flight row stops counting as
    alive), so this is honesty polish, not a correctness load-bearer.
    ``user_message_id`` must be captured pre-rollback (本地变量律 — the
    B2 fenced-tails MissingGreenlet lesson)."""
    from app.models.database import AsyncSessionLocal  # deferred: failure path

    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(Message, user_message_id, with_for_update=True)
            if row is not None and row.turn_state == "in_flight":
                from app.chat.editor_recovery import report_committed_edits

                await report_committed_edits(db, row)
                row.turn_state = "failed"
                await db.commit()
    except Exception as e:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            "turn_state_failed_stamp_error",
            message_id=str(user_message_id),
            error=str(e),
        )


async def persist_turn_failed_line(
    conversation_id,
    detail: str,
    turn_id: UUID | None = None,
) -> None:
    """Persist a failed turn's honest line as ONE assistant row (intent
    ``{"type": "turn_failed"}``) — the live grey meta row's durable twin, so
    a refresh keeps the failure's stage and its lawful next step instead of
    dropping them (法2 的穷举诚实行在回合失败座的同形). Best-effort, fresh
    session (the turn's own session is tearing down); never raises.
    ``conversation_id`` must be captured pre-rollback (本地变量律)."""
    from app.models.database import AsyncSessionLocal  # deferred: failure path

    if not detail.strip():
        return
    try:
        async with AsyncSessionLocal() as db:
            await _create_message(
                db,
                conversation_id,
                "assistant",
                detail,
                intent={"type": "turn_failed"},
                turn_id=turn_id,
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            "turn_failed_line_persist_error",
            conversation_id=str(conversation_id),
            error=str(e),
        )


@_scope_turn_row_lock_ownership
async def execute_chat_turn(
    db: AsyncSession,
    prepared: PreparedTurn,
    request: ChatRequest,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_interim_prose=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
) -> ChatResponse:
    """chat() phase 2: run the agent turn, commit once, assemble the response.

    ``on_delta`` (chat SSE) receives the prose channel's fragments — the
    reply itself now (ADR-077 判词②: speech left the action JSON; the
    typewriter law holds natively); ``on_reasoning`` receives reasoning
    fragments as a liveness signal; ``on_phase`` receives System Status
    labels at REAL macro-state switches — the film design span's
    capturing / storyboarding / storyboard_revision at real transitions,
    and None as the span's exit clear. Every other LLM window wears the
    base label "Thinking…" (2026-09-10 用户拍板) — a plain black-box
    window needs no alias, however long it runs.
    ``on_tool_call`` / ``on_tool_ready`` carry the structure frames: a tool
    call's name became known (the Activity beat's seat + the explicit phase
    clear) / a call's arguments validated (the
    question.preview seat — the retired ask-object watcher). The base label
    is "Thinking…" (2026-09-10 用户拍板). None (the JSON path, repair
    iterations, answer_question's continuation) keeps the one-shot calls.
    """
    if prepared.interrupt_reply is not None:
        assistant_message = prepared.interrupt_reply
        run_id = None
        bailed_run_ids: list[UUID] = []
    else:
        # 会话层计量 (ADR-117 D3): the turn-entry seam binds the usage
        # ledger — the canned interrupt reply needs no LLM (empty ledger,
        # zero rows), the agent branches meter through record_usage.
        with bind_conversation_turn(
            conversation_id=UUID(str(prepared.conversation.id)),
            turn_id=prepared.user_message.id,
            project_id=prepared.conversation.project_id,
        ) as _usage_bind:
            if prepared.plan_path:
                (
                    assistant_message,
                    run_id,
                    plan_answered,
                    bailed_run_ids,
                ) = await _plan_turn(
                    db,
                    prepared.user_id,
                    prepared.conversation,
                    prepared.project,
                    request,
                    skill=prepared.skill,
                    skill_ambiguity=prepared.skill_ambiguity,
                    recent=prepared.history,
                    on_delta=on_delta,
                    on_reasoning=on_reasoning,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                    turn_id=prepared.user_message.id,
                )
                if plan_answered is not None:
                    prepared.answered_question = plan_answered
            else:
                (
                    assistant_message,
                    run_id,
                    bailed_run_ids,
                    chat_settled,
                ) = await _propose_turn(
                    db,
                    prepared.user_id,
                    prepared.conversation,
                    prepared.project,
                    request.message,
                    request.mentions,
                    prepared.history,
                    skill=prepared.skill,
                    skill_ambiguity=prepared.skill_ambiguity,
                    suggestion_ref=request.suggestion_ref,
                    on_delta=on_delta,
                    on_reasoning=on_reasoning,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                    turn_id=prepared.user_message.id,
                )
                if chat_settled is not None:
                    # 插话判定结算 (ADR-053 R2): the agent judged this very
                    # message the pending question's answer — surface the
                    # settled row so the client's pill clears and the
                    # AnsweredQuestion block lands.
                    prepared.answered_question = chat_settled
        # The usage row rides the turn's own commit below (billing write
        # discipline); a zero-LLM turn (repair-loop canned replies aside)
        # writes nothing.
        await fold_conversation_usage(
            db,
            user_id=prepared.user_id,
            project_id=(
                UUID(str(prepared.project.id))
                if prepared.project is not None
                else None
            ),
            accrued=_usage_bind.accrued,
        )

    # Stop and settlement serialize on the opening row. If Stop won, raising
    # here rolls back every uncommitted assistant/run/hold write in this Turn.
    turn_row = await _lock_turn_for_final_commit(db, prepared.user_message.id)
    await db.execute(
        delete(Message).where(
            Message.turn_id == prepared.user_message.id,
            Message.intent["type"].astext == "partial",
        )
    )
    if prepared.answered_question is not None:
        # A typed reply already has its own transcript position.
        turn_row.intent = {
            **(turn_row.intent or {}),
            "answered_question_id": str(prepared.answered_question.id),
        }
    turn_row.turn_state = "settled"
    prepared.user_message.turn_state = "settled"
    await db.commit()
    await finalize_bailed_runs(bailed_run_ids)
    return ChatResponse(
        conversation_id=prepared.conversation_id,
        user_message=ChatMessageResponse.model_validate(prepared.user_message),
        # None = the turn closed without an assistant row (a degrade path
        # lands its own shape) — the SSE client closes the preview bubble.
        assistant_message=(
            ChatMessageResponse.model_validate(assistant_message)
            if assistant_message is not None
            else None
        ),
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
    the conversation, settle any pending question deterministically),
    then execute it (intent agent proposes, compile_graph adjudicates, one
    commit). The SSE path calls the two phases itself so prose deltas can
    stream between them.
    """
    prepared = await prepare_chat_turn(db, user_id, request)
    return await execute_chat_turn(db, prepared, request)


async def list_conversation_messages(
    db: AsyncSession,
    conversation_id: UUID,
) -> list[Message]:
    """Return messages in a conversation, oldest first — 渲染序 = seq 序
    (ADR-108 数组位置律): persisted array order IS the render order;
    created_at is display-only (NULL seq = pre-array legacy rows, backfilled
    by migration r8f1a3c5d7e9; nulls_last + created_at/id 兜底只护迁移窗口)."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.asc().nulls_last(), Message.created_at.asc(), Message.id.asc())
    )
    return list(result.scalars().all())


# ---- Activity row persistence through the ConversationBridge ----------------


async def record_asset_activity(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    *,
    status: str,
    name: str,
    count: int,
    total: int,
    ref: str,
    duration_ms: int | None,
    asset_type: str,
    at: str | None,
    turn_id: str | None,
) -> Message | None:
    conversation = await _get_or_create_project_conversation(db, user_id, project_id)
    if turn_id:
        existing = (
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.turn_id == UUID(turn_id),
                Message.intent["type"].astext == ACTIVITY_ROW_TYPE,
            )
            .order_by(Message.seq.desc())
            .limit(1)
        )
        return (await db.execute(existing)).scalar_one_or_none()

    activity_id = f"asset-reading:{ref}"
    dedup = select(Message.id).where(
        Message.conversation_id == conversation.id,
        Message.intent["type"].astext == ACTIVITY_ROW_TYPE,
        Message.intent["frame"]["activity_id"].astext == activity_id,
    )
    if (await db.execute(dedup.limit(1))).scalar_one_or_none() is not None:
        return None
    if status == "failed":
        key = "chat.material.readingFailed"
    elif total > 1:
        key = "chat.material.readingDoneProgress"
    else:
        key = "chat.material.readingDone"
    if asset_type in {"video", "audio"}:
        key = f"{key}_{asset_type}"
    frame = {
        "activity_id": activity_id,
        "kind": "read",
        "status": status,
        "key": key,
        "count": count,
        "total": total,
        "name": name,
        "at": at or datetime.now(UTC).isoformat(),
    }
    if duration_ms is not None:
        frame["duration_ms"] = duration_ms
    return await append_activity_row(db, conversation.id, frame)


# ---- 建议谱系 (ADR-099 §4): 点选 provenance 落地解算 -----------------------


async def _project_asset_ids(db: AsyncSession, project_id: UUID) -> list[str]:
    """The suggestion record's world snapshot (source_state.asset_ids): the
    project's current file assets — the material any suggestion born this
    turn was grounded against. The directed stale check re-reads these ids
    at pick time (deleted = the row is gone; failed = status says so)."""
    rows = (
        await db.execute(
            select(Asset.id).where(
                Asset.project_id == project_id,
                Asset.file_url.isnot(None),
            )
        )
    ).scalars().all()
    return [str(a) for a in rows]


async def stamp_suggestions(
    db: AsyncSession,
    message: Message,
    items,
    project_id: UUID | None,
) -> None:
    """Code-stamp an accepted terminal call's options onto its row (ADR-099
    §3/§4): the SAME commit point as the prose — the records land in the
    row's interaction block within the turn's one transaction, so a
    rejected iteration's options never existed and a suppressed answer
    drops them with its row. No-op on empty items (零 diff 律)."""
    if not items:
        return
    message.suggestions = build_suggestion_records(
        items,
        str(message.id),
        await _project_asset_ids(db, project_id) if project_id is not None else [],
    )
    await db.flush()


async def resolve_suggestion_note(
    db: AsyncSession,
    conversation_id: UUID,
    project_id: UUID | None,
    ref: SuggestionRef,
) -> str | None:
    """建议点选的落地解算 (ADR-099 §4): locate the source row's record,
    run the DIRECTED stale check (zero counters — every predicate reads
    already-persisted fields), and compose the LLM-facing provenance note.
    An unresolvable ref (a foreign/stale source_turn, a record that isn't
    there) reads as no note at all — the message processes as plain text,
    never an error and never a silent drop."""
    source = await db.get(Message, ref.source_turn)
    if source is None or UUID(str(source.conversation_id)) != conversation_id:
        return None
    record = next(
        (r for r in (source.suggestions or []) if r.get("id") == ref.suggestion_id),
        None,
    )
    if record is None:
        return None
    state = record.get("source_state") or {}
    asset_ids = [a for a in (state.get("asset_ids") or []) if isinstance(a, str)]
    assets_missing = assets_failed = False
    if asset_ids:
        parsed_ids = []
        for a in asset_ids:
            try:
                parsed_ids.append(UUID(a))
            except ValueError:
                continue
        rows = (
            await db.execute(select(Asset).where(Asset.id.in_(parsed_ids)))
        ).scalars().all()
        found = {str(a.id): a for a in rows}
        assets_missing = any(a not in found for a in asset_ids)
        assets_failed = any(
            found[a].processing_status == AssetStatus.FAILED
            for a in asset_ids
            if a in found
        )
    new_understanding = (
        await db.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.intent["type"].astext == "material_beat",
                Message.intent["beat"].astext == "understanding",
                Message.created_at > source.created_at,
            )
            .limit(1)
        )
    ).scalar_one_or_none() is not None
    plan_since = (
        await db.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.question["kind"].astext == "task_book",
                Message.created_at > source.created_at,
            )
            .limit(1)
        )
    ).scalar_one_or_none() is not None
    run_since = False
    if project_id is not None:
        run_since = (
            await db.execute(
                select(WorkflowRun.id)
                .where(
                    WorkflowRun.project_id == project_id,
                    WorkflowRun.created_at > source.created_at,
                )
                .limit(1)
            )
        ).scalar_one_or_none() is not None
    reasons = suggestion_stale_reasons(
        assets_missing=assets_missing,
        assets_failed=assets_failed,
        new_understanding=new_understanding,
        plan_or_run_since=plan_since or run_since,
    )
    return compose_suggestion_note(record.get("label") or "", reasons)


# ---- Activity row persistence (ADR-108 §2/§5 — transcript 数组化) ----------
#
# 每帧一行：a persistable activity frame lands as its OWN array row —
# appended at execute entry (read spans; the position = work start, after
# the interim_prose seat) or at born-terminal emission (repair terminals /
# explore milestones), then settled by an in-place UPDATE. The per-turn
# aggregate ``activity_log`` row is RETIRED (the replay no longer
# re-derives interleaving — array position carries it). All writes ride
# the route's fresh short sessions, so the rows survive the turn's
# outcome (诚实 transcript: failed/cancelled turns keep their work
# evidence) and never touch the turn's long transaction.
# draft/run spans still never persist (落定即退役 — the docked plan card /
# the run receipt is their settled evidence).

ACTIVITY_ROW_TYPE = "activity"
ACTIVITY_FORENSICS_TYPE = "activity_forensics"
# Legacy aggregate type — read only by the W5 migration script
# (scripts/migrate_activity_log_rows.py); never written anymore.
ACTIVITY_LOG_TYPE = "activity_log"


async def append_activity_row(
    db: AsyncSession,
    conversation_id: UUID,
    frame: dict[str, Any],
    *,
    turn_id: UUID | None = None,
) -> Message:
    """Append ONE activity row at its array position (open / born-terminal)."""
    if turn_id is not None:
        await _lock_turn_for_transcript_write(db, turn_id)
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        attachments=[],
        mentions=[],
        turn_id=turn_id,
        intent={"type": ACTIVITY_ROW_TYPE, "frame": frame},
        seq=await alloc_message_seq(conversation_id, db),
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


async def settle_activity_row(
    db: AsyncSession,
    message_id: UUID,
    frame: dict[str, Any],
) -> None:
    """原地 update (ADR-108 §2): the SAME row's frame gains the terminal
    status / done-key / duration_ms — the array position never moves."""
    message = await db.get(Message, message_id)
    if message is None:
        return
    if message.turn_id is not None:
        await _lock_turn_for_transcript_write(db, message.turn_id)
        await db.refresh(message, with_for_update=True)
    message.intent = {"type": ACTIVITY_ROW_TYPE, "frame": frame}
    await db.flush()


async def record_activity_forensics(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    ref: str,
    rejections: list[dict[str, Any]],
) -> Message | None:
    """The turn's rejection forensic ledger (rejection 取证批) as ONE
    never-rendered row (the client filters the type; W3 单路径渲染只认
    activity 行). Once-only per ``ref`` (the opening user row's id), both
    turn outcomes — a rejected attempt stays auditable even when the repair
    span itself was invisible and even when the turn failed."""
    if not rejections:
        return None
    dedup = select(Message.id).where(
        Message.conversation_id == conversation_id,
        Message.intent["type"].astext == ACTIVITY_FORENSICS_TYPE,
        Message.intent["ref"].astext == ref,
    )
    if (await db.execute(dedup.limit(1))).scalar_one_or_none() is not None:
        return None
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        attachments=[],
        mentions=[],
        intent={"type": ACTIVITY_FORENSICS_TYPE, "ref": ref, "rejections": rejections},
        seq=await alloc_message_seq(conversation_id, db),
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


# ---- Candidate surface persistence (Workspace 合同 v4.2 C8-c, 2026-09-26) ---
# The candidate surface's data chain is message-borne end to end: live it
# rides the ``assistant.candidates`` SSE frames; at turn settle the route
# persists the turn's emitted events as ONE row here, so a refresh / another
# device rebuilds the card (and its selection highlight) from the archive.
# No endpoint — the audit's 未覆盖 #1 stays closed.

CANDIDATES_LOG_TYPE = "candidates_log"


async def record_candidates_log(
    db: AsyncSession,
    conversation_id: UUID,
    events: list[dict[str, Any]],
    *,
    ref: str,
    turn_id: UUID | None = None,
) -> Message | None:
    """Persist one turn's candidate-surface events (set births + selection
    updates, in emission order) as a single message row — the same doctrine
    as activity-row persistence: once-only per ``ref``, completed path only,
    a failed turn persists nothing (the client rolls its live cards back)."""
    if not events:
        return None
    dedup = select(Message.id).where(
        Message.conversation_id == conversation_id,
        Message.intent["type"].astext == CANDIDATES_LOG_TYPE,
        Message.intent["ref"].astext == ref,
    )
    if (await db.execute(dedup.limit(1))).scalar_one_or_none() is not None:
        return None
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        attachments=[],
        mentions=[],
        turn_id=turn_id,
        intent={"type": CANDIDATES_LOG_TYPE, "ref": ref, "events": events},
        seq=await alloc_message_seq(conversation_id, db),
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message
