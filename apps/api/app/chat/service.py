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

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.pipeline.lifecycle import ConfirmationNeed

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# The two chat agents no longer take calls HERE (the turn runners —
# app/chat/plan_turn.py / propose_turn.py — drive them through the tool
# loop); importing the declarations module keeps them registered in AGENTS
# at startup (the orchestrator's roster self-check walks it).
from app.chat.intent import chat_intent_agent as _chat_intent_agent  # noqa: F401
from app.chat.intent import intent_router as _intent_router  # noqa: F401
from app.chat.context import recent_history_within_budget
from app.chat.suggestions import (
    build_suggestion_records,
    compose_suggestion_note,
    suggestion_stale_reasons,
)
from app.chat.turn_tools import film_wiring_guard, strip_tool_echoes
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
    FilmStoryboard,
    InferredIntent,
    Option,
    PendingPlan,
    ProjectStatus,
    QuestionPayload,
    QuestionProposal,
    PlanEstimate,
    StartAnswerRequest,
    SuggestionRef,
    TaskItem,
)
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    MessageSeqCounter,
    Persona,
    Project,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.asset_processing import has_any_text_material, has_renderable_media
from app.pipeline.derivative_dispatch import (
    DerivativeWriterNode,
    project_source_language,
    derive_quote_alt_language,
)
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

_ASK_BACK_TEXT = (
    "I want to make sure I do the right thing — could you be more specific? "
    "For example: re-cut highlights, remove filler words, add music, "
    "or rewrite a post."
)


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


def _ask_content(ask: QuestionProposal) -> str:
    """The question row's content (ask 三分解剖 ①): the framing prose when
    the ask brings one. A TEXT ask (options empty — it never docks, 形态律
    ADR-053 R1) keeps its bare question IN the speech: the message IS the
    whole ask, prose + question; an options ask's question rides the dock's
    title (payload ②), so the content stays the prose alone."""
    prose = ask.prose.strip()
    if not prose:
        return ask.question
    if not ask.options:
        return f"{prose}\n\n{ask.question}"
    return prose


def _reminder_tail(text: str, question: str, default_path: str | None) -> str:
    """插话提醒尾 (ADR-053 R2): an interjection turn's reply ends with a
    code-composed reminder — the still-pending question plus its default
    path, in the turn's language (code-forced text, never the LLM's voice —
    the draft-from-persona declaration's doctrine)."""
    if _prefers_zh(text):
        tail = f"\n\n（还在等你的回答：{question}"
        tail += f"——{default_path}）" if default_path else "——一句话就行）"
        return tail
    tail = f"\n\n(Still waiting for your answer: {question}"
    tail += f" — {default_path})" if default_path else " — one short line is enough)"
    return tail


def _estimate_tail(
    text: str, estimate: PlanEstimate | None, *, reason: str = ""
) -> str:
    """Dock echo 的估价尾行 (ADR-111 §2 — 确认 dock 卡面退役后总估价的新家;
    BILLING §2.1 披露义务不变: capture 前估价必须可见): a code-composed
    whisper appended to the plan's dock echo — the total range plus the
    hold/settle semantics, in the turn's language (code-forced text, never
    the LLM's voice — the reminder tail's doctrine; 真实数字 = 世界自证,
    ADR-058 的合法二源). A deferred (None) quote says so honestly — never
    a fabricated number. The per-task half stays on the canvas's draft
    nodes (逐节点估价, ADR-057 K5).

    ``reason`` (ADR-117 §4) = the dock's stamped ConfirmationNeed reason.
    The held clauses key on it — the auto regime's guardrail/unquotable
    trip: the echo's spoken close announced the start (the model speaks
    before the quote exists), but the dock waits for the priced beat, so
    the tail carries the honest correction. ``above_guardrail`` names the
    high side (the threshold itself is ops-internal, never shown);
    ``unquotable`` leads with the deferred-pricing truth EVEN when a
    partial range exists (a NULL per-task with quotable siblings — the
    pill's deferred label and the tail must say one thing);
    ``unmet_condition`` (7276ef13 ③) says the requested change never
    landed and the dock therefore waits — confirming starts the STANDING
    (unfixed) version, so the tail states the choice honestly.
    ``copy_drift`` (7276ef13 定点收尾②) says the published version's copy
    drifted from what the user can verify (the drift note above names the
    clauses) — confirming accepts the drifted copy, so the tail names the
    two honest outs (accept / restore the original). The prefs
    family (execution_pref / credits_pref) keeps the standard
    estimate-only shape: there the model's own closing question IS the
    confirmation ask."""
    zh = _prefers_zh(text)
    if estimate is not None:
        low, high = estimate.total
        if reason == "copy_drift":
            if zh:
                return (
                    f"\n\n（估价 {low}–{high} 积分——注意：这版的文案与你提供的原文"
                    "有出入（见上文标注）；确认即按这版开始，或说一句恢复原文。"
                    "开始时按上限预扣，按实际用量结算，失败的步骤不收费，剩余退回）"
                )
            return (
                f"\n\n(Estimated {low}–{high} credits — note: this "
                "version's copy differs from the text you gave (marked "
                "above); confirming starts THIS version, or say the word "
                "and I'll restore your original. On start the high end is "
                "held; you're charged only for what actually runs, failed "
                "steps are free, and the remainder is returned.)"
            )
        if reason == "unmet_condition":
            if zh:
                return (
                    f"\n\n（估价 {low}–{high} 积分——注意：你刚才要的修改没能落实，"
                    "当前仍是修改前的版本；确认即按这个版本开始，或先说一句继续改。"
                    "开始时按上限预扣，按实际用量结算，失败的步骤不收费，剩余退回）"
                )
            return (
                f"\n\n(Estimated {low}–{high} credits — note: the change "
                "you asked for did not land, so this is still the "
                "pre-change version; confirming starts THIS version, or "
                "say the word and I'll keep fixing. On start the high end "
                "is held; you're charged only for what actually runs, "
                "failed steps are free, and the remainder is returned.)"
            )
        if reason == "unquotable":
            if zh:
                return (
                    f"\n\n（估价 {low}–{high} 积分起——含暂无法提前估价的步骤，"
                    "确认后才开始：按上限预扣，按实际用量结算，"
                    "失败的步骤不收费，剩余退回）"
                )
            return (
                f"\n\n(From {low}–{high} credits — some steps can't be "
                "quoted up front, so the work starts once you confirm: the "
                "high end is held, you're charged only for what actually "
                "runs, failed steps are free, and the remainder is "
                "returned.)"
            )
        if reason == "above_guardrail":
            if zh:
                return (
                    f"\n\n（估价 {low}–{high} 积分——金额较高，确认后才开始："
                    "按上限预扣，按实际用量结算，失败的步骤不收费，剩余退回）"
                )
            return (
                f"\n\n(Estimated {low}–{high} credits — on the high side, "
                "so the work starts once you confirm: the high end is held, "
                "you're charged only for what actually runs, failed steps "
                "are free, and the remainder is returned.)"
            )
        if zh:
            return (
                f"\n\n（估价 {low}–{high} 积分——开始时按上限预扣，"
                "按实际用量结算，失败的步骤不收费，剩余退回）"
            )
        return (
            f"\n\n(Estimated {low}–{high} credits — on start the high end "
            "is held; you're charged only for what actually runs, failed "
            "steps are free, and the remainder is returned.)"
        )
    if reason in ("above_guardrail", "unquotable"):
        if zh:
            return (
                "\n\n（估价随运行确定——这个方案无法提前估价，确认后才开始；"
                "开始后才计费，失败的步骤不收费）"
            )
        return (
            "\n\n(Credits are priced when the run starts — this plan can't "
            "be quoted up front, so it starts once you confirm; billing "
            "begins only when you start, and failed steps are free.)"
        )
    if reason == "unmet_condition":
        if zh:
            return (
                "\n\n（注意：你刚才要的修改没能落实，当前仍是修改前的版本；"
                "确认即按这个版本开始，或先说一句继续改。开始后才计费，"
                "失败的步骤不收费）"
            )
        return (
            "\n\n(Note: the change you asked for did not land, so this is "
            "still the pre-change version; confirming starts THIS version, "
            "or say the word and I'll keep fixing. Billing begins only "
            "when you start, and failed steps are free.)"
        )
    if reason == "copy_drift":
        if zh:
            return (
                "\n\n（注意：这版的文案与你提供的原文有出入（见上文标注）；"
                "确认即按这版开始，或说一句恢复原文。开始后才计费，"
                "失败的步骤不收费）"
            )
        return (
            "\n\n(Note: this version's copy differs from the text you "
            "gave (marked above); confirming starts THIS version, or say "
            "the word and I'll restore your original. Billing begins only "
            "when you start, and failed steps are free.)"
        )
    if zh:
        return "\n\n（估价随运行确定——开始后才计费，失败的步骤不收费）"
    return (
        "\n\n(Credits are priced when the run starts — billing begins only "
        "when you start, and failed steps are free.)"
    )


def _auto_start_rejected_line(detail: dict[str, Any] | None) -> str:
    """The auto 道's birthplace-422 honesty line (ADR-117 §2): the
    presentation-time start failed AFTER the echo's work-start beat spoke,
    and no pill / grey row / toast carries it (the ask 道's client-side
    surfacing never fires on this path) — so the reason lands as a
    code-composed tail on the dock row's content (the estimate tail's
    lawful seat: code-forced text, real numbers from the 422 detail, never
    the LLM's voice). ``credits.insufficient`` names the two numbers
    (BILLING §5 文案纪律: factual, no top-up CTA — the purchase entry is
    W11); every other 422 gets the generic retry line (a retry through
    the ask 道 surfaces the full reason there). Language = the request's
    ui locale (the wallet route's same seat)."""
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



# Final Hardening B1 (2026-09-24): ``_edit_op_items`` / ``_validate_edit_ops``
# retired with the raw-ops chat verb ``apply_edit_ops`` — the Agent's only
# edit entry is ``edit_output`` (ADR-090); the REST operations door keeps
# its own validation in ``app.operations.service``.


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
        seq=await alloc_message_seq(conversation_id, db),
    )
    db.add(message)
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
    caption_mode: str | None = None,
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

    film_guard = film_wiring_guard(tasks=tasks)
    if film_guard is not None:
        raise ValueError(film_guard)
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
                caption_mode=caption_mode,
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


def _film_gate_facts(
    tasks: list,
    pending: PendingPlan | None,
    question: dict | None,
) -> "FilmGateFacts | None":
    """The Start gate's film conjuncts (ADR-129), computed once per start
    attempt from the confirmed chain + the stored pending plan + the docked
    question's stamp. None = the chain carries no film (the gate's film
    conjuncts stay dark).

    Draft-match law: the dock's stamped token/version must agree with the
    ACTIVE draft, and token equality never short-circuits the rest — the
    effective chain's canonical launch_film params, the version number, the
    board's content digest and the execution snapshot digest all compare.
    A panel edit therefore fails closed for an explicit re-dock instead of
    executing old storyboard content under new levers. Pre-version rows keep
    the fingerprint fallback (读容忍)."""
    from app.pipeline.lifecycle import FilmGateFacts  # deferred: chat → pipeline
    from app.tools.film.storyboard import (  # deferred
        film_draft_inflight_live,
        film_first_draft_unpresented,
        film_start_draft_match,
    )

    if not any(getattr(t, "tool", None) == "launch_film" for t in tasks):
        return None
    has_draft = pending is not None and isinstance(pending.film_storyboard, dict)
    hold = bool(pending.film_review_hold) if pending is not None else False
    inflight = (
        film_draft_inflight_live(pending.film_draft_inflight)
        if pending is not None
        else False
    )
    match = (
        film_start_draft_match(
            pending,
            tasks,
            (pending.prompt if pending is not None else None) or None,
            (question or {}).get("film_draft_token"),
            (question or {}).get("film_storyboard_version"),
        )
        if pending is not None
        else False
    )
    return FilmGateFacts(
        film_chain=True,
        has_active_draft=has_draft,
        draft_match=match,
        review_hold=hold,
        first_draft_unpresented=film_first_draft_unpresented(pending),
        draft_inflight=inflight,
    )


# ---- brief (DIALOG_WORKFLOW §2.4, ADR-052 B2) --------------------------------

_SOURCE_RANK: dict[BriefSlotSource, int] = {
    BriefSlotSource.DEFAULT: 0,
    BriefSlotSource.INFERRED: 1,
    BriefSlotSource.USER_STATED: 2,
}

_BRIEF_SCALAR_SLOTS = ("topic", "audience", "tone", "material_state")


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
    setattr(
        update,
        slot,
        BriefSlot(value=value, source=BriefSlotSource.USER_STATED),
    )
    stored.brief = merge_brief(update, stored.brief)
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
    if exemplar is not None and exemplar.processing_status == AssetStatus.COMPLETED:
        from app.pipeline.decompile import (  # deferred: pipeline edge
            fire_warm_craft_skeleton,
        )

        fire_warm_craft_skeleton(UUID(str(project.id)), UUID(str(exemplar.id)))


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


# Caption mode for captioned-video runs (RECIPES §4.7, ADR-099 §8 default
# absorption): a parameter a default can carry, so it never blocks the user
# with a question. Derivation funnel, in priority order:
#
#  1. LLM-set on InferredIntent.caption_mode (the intent router recognises the
#     user's wording — "bilingual subtitles" / "中英双语字幕" — and sets it).
#  2. Code-level keyword scan on the user prompt (defence-in-depth: the LLM
#     may miss the phrasing, but a literal "bilingual"/"双语" is unambiguous).
#  3. The previous dock's value, inherited across refinement turns that don't
#     re-mention it.
#  4. source_only — stamped only when a distinct second language makes the
#     choice real; the plan card then shows it as a visible, changeable fact.
#     With no distinct alt language nothing is stamped (bilingual would print
#     one language twice — there is no choice to show, and the run narrows
#     bilingual → source_only on its own at dispatch).
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


def _detect_caption_mode(prompt: str) -> str | None:
    """Code-level keyword scan — the LLM may set caption_mode too, but a
    literal "bilingual"/"双语" is unambiguous so the funnel never derives
    past it. Source/target-only stays LLM-only: their reading is genuinely
    ambiguous without knowing the source language."""
    text = (prompt or "").lower()
    if any(kw in text for kw in _CAPTION_MODE_KEYWORDS_BILINGUAL):
        return "bilingual"
    return None


async def _caption_choice_is_meaningful(
    db: AsyncSession, project: Project, tasks: list
) -> bool:
    """Is there a DISTINCT second language to offer?

    Bilingual/target-only only make sense when an alt language exists that
    differs from the source material's language. Derivation order (same as
    the run-time path): the task's own target language (user-named) → the
    project/UI locale. When every candidate equals the source there is no
    choice to show — the funnel stamps nothing and the run narrows
    bilingual → source_only on its own at dispatch.
    """
    source = await project_source_language(db, project)
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


def _resolved_caption_mode(project: Project) -> str | None:
    """The caption mode the previous dock stamped, if any.

    A refinement turn's fresh call arrives with ``caption_mode=None`` unless
    the user re-mentions it — None means "not mentioned this turn", never
    "retracted". The stored ``pending_brief.intent.caption_mode`` is the
    inherit source the funnel consults before defaulting, and every dock
    inherits it the same way (a follow-up "改成 5 张" never drops the mode).
    """
    pending = project.pending_brief if isinstance(project.pending_brief, dict) else None
    if not pending:
        return None
    intent = pending.get("intent") or {}
    mode = intent.get("caption_mode")
    return str(mode) if mode else None


async def _derive_chat_caption_mode(
    db: AsyncSession, project: Project, tasks: list, text: str
) -> str | None:
    """The caption-mode funnel for a caption-bearing chain: fresh keyword >
    the previous dock's value > source_only when the choice is real (a
    distinct second language exists). Returns None for chains without a
    caption-bearing task — and for caption chains with no distinct alt
    language, where nothing is stamped because there is nothing to choose.

    Registry-native chain check (DerivativeWriterNode), no parallel "which
    tools need subtitles" list."""
    if not any(
        isinstance(NODE_KINDS.get(t.tool), DerivativeWriterNode)
        and t.tool == "write_quotes"
        for t in tasks
    ):
        return None
    mode = _detect_caption_mode(text) or _resolved_caption_mode(project)
    if mode is None and await _caption_choice_is_meaningful(db, project, tasks):
        mode = "source_only"
    return mode


async def _compute_plan_reasons(
    db: AsyncSession,
    project: Project,
    intent: InferredIntent,
) -> list[str]:
    """Re-derive the soft-signal reasons for a docked plan (Phase 1
    answer path needs this — the caption_mode replay rebuilds the
    PendingPlan from the stashed intent and the reasons computed in
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
    ``_compute_plan_reasons`` and the plan path's carve-out can both
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
    serialized guard — a zombie plan confirmed later gets the clean
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


def _design_no_progress_text(text: str, *, version_saved: bool) -> str:
    """Honest close after the loop's Film rejection policy stops a retry.

    The two states are deliberately different: a failed correction must not
    erase the fact that an earlier version was saved this turn, while a
    failed first design must not claim that any new storyboard exists.
    """
    if _prefers_zh(text):
        if version_saved:
            return (
                "这次后续调整没有完成，我已停止重复尝试。最近保存的分镜版本"
                "和已有成片都保留，本次没有开始新的制作。请再发一次，我会"
                "从最近保存的版本继续。"
            )
        return (
            "这次调整没有完成，我没有保存新的分镜，也没有开始制作。我已停止"
            "重复尝试；此前保存的内容不会被这次失败覆盖。请再发一次，我会"
            "重新尝试。"
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
        "start production, and I stopped the repeated attempts. Previously "
        "saved work is unchanged. Send the request again and I'll retry."
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
    storyboard_echo: bool = False,
    film_draft_token: str | None = None,
    film_storyboard_version: int | None = None,
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
    face, never a machine digest line). ``storyboard_echo`` marks a film
    dock whose echo content carries the code-rendered storyboard markdown —
    on refresh the pending row's content replays as a flow message while
    the dock revives separately. ``film_draft_token`` (ADR-129) stamps the
    presented storyboard draft's per-version token into the payload — the
    Start gate compares it against the active draft's token and refuses a
    dock that presents an older design. ``film_storyboard_version`` stamps
    the explicit revision number alongside it. Returns the run ids whose
    parked interrupt was cascade-bailed by the supersede (finalized by the
    caller after its commit). Flush-only.
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
            storyboard_echo=storyboard_echo,
            film_draft_token=film_draft_token,
            film_storyboard_version=film_storyboard_version,
        ),
        intent=intent.model_dump(mode="json"),
    )
    # Draft graph (ADR-057 K5 — 图先展示后运行): the docked chain stamps the
    # canvas's preview as DRAFT nodes through the birthplace's own compile
    # (same fill keys → Start fills them in place). A chain the birthplace
    # would reject degrades exactly like the quote-less dock (the derived
    # preview's posture): the plan docks, the stale preview tears down, and
    # Start 422s for real.
    from app.pipeline.graph_fill import (  # deferred: import cycle
        clear_draft_graph,
        stamp_draft_graph,
    )
    from app.ui_locale import current_ui_language  # deferred: request ctx

    try:
        await stamp_draft_graph(
            db, project, intent.tasks, current_ui_language()
        )
    except (ToolRejected, ValueError):
        logger.warning(
            "draft_graph_stamp_failed",
            project_id=str(project.id),
            exc_info=True,
        )
        await clear_draft_graph(db, UUID(str(project.id)))
    return bailed_run_ids


async def _auto_start_docked_plan(
    db: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    project: Project,
) -> tuple[Message, UUID] | None:
    """ADR-117 §2 授权前移 — the auto regime's presentation-time start.

    ADR-139: the auto 道 waives the approval beat, it never manufactures
    the production request — a dock born from a message without production
    intent carries the ``awaiting_production`` stamp and waits here like
    any confirm-owing dock (the Start pill stays as the standing offer).

    Called right after a plan docks. The dock's presentation-time stamp
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
        film=_film_gate_facts(
            list(intent.tasks) if intent is not None else [],
            (
                PendingPlan.model_validate(project.pending_brief)
                if isinstance(project.pending_brief, dict)
                else None
            ),
            (
                pending_question.question
                if isinstance(pending_question.question, dict)
                else None
            ),
        ),
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
        answered, _follow_up = await answer_question(
            db,
            user_id,
            UUID(str(pending_question.id)),
            StartAnswerRequest(kind="start"),
            # The run births on standing authorization (ADR-117 §2) — the
            # snapshot records the channel, not an explicit gesture.
            confirmed_via="auto",
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
            # never fires here — so the reason lands as a code-composed
            # tail on the dock row's content (the estimate tail's lawful
            # seat: persisted, so live envelope and replay read it alike;
            # intent.answer stays clean — a future re-dock's echo must not
            # ghost this moment-in-time fact).
            line = _auto_start_rejected_line(
                exc.detail if isinstance(exc.detail, dict) else None
            )
            base = (pending_question.content or "").rstrip()
            pending_question.content = (base + line) if base else line.lstrip()
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
    on_checkpoint=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
) -> tuple[Message | None, UUID | None, list[UUID], Any]:
    """The generic question-answer 续聊 continuation: the user's pick is
    their say for the next turn, and the turn's inference message carries
    the answered question's bare text as a factual frame (作答语境帧 —
    the QA link survives settlement).
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
    say = (data.text if data.kind == "freeform" else None) or option_label or ""
    # 作答语境帧 (assembly): nothing on this path persists a user row —
    # the QA archive is the record — so the turn's inference message
    # carries the one disambiguating world fact the bare say lacks:
    # WHICH open question it answers. Stripped of it, "就加一个中文字幕
    # 吧" reads as a fresh standalone ask and the additive misreading
    # opens ("add subtitles TO the earlier recommendation"). A factual
    # frame, never a behavioral instruction — the model does the language
    # understanding (the typed-answer path always had this: its pending
    # block carries the bare question; the endpoint path lost it at
    # settlement).
    bare_q = (question.question or "").strip()
    turn_say = (
        f'{say}\n(This message answers your open question: "{bare_q}")'
        if bare_q
        else say
    )
    history = await list_conversation_messages(db, UUID(str(conversation.id)))
    # 滑动窗口装配 (ADR-117 D4): the scattered fixed-count slices converge
    # on the one budget predicate — world state never rides this window.
    recent = await recent_history_within_budget(db, history)
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
    if project is not None and question.slot == "asset_role":
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
            ChatRequest(project_id=project.id, message=turn_say),
            recent=recent,
            on_delta=on_delta,
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_checkpoint=on_checkpoint,
            on_loop_event=on_loop_event,
            on_activity=on_activity,
            on_candidates=on_candidates,
            on_row_append=on_row_append,
        )
        return follow_up, run_id, bailed, answered
    if question.slot is not None and project is not None:
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
            ChatRequest(project_id=project.id, message=turn_say),
            recent=recent,
            on_delta=on_delta,
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_checkpoint=on_checkpoint,
            on_loop_event=on_loop_event,
            on_activity=on_activity,
            on_candidates=on_candidates,
            on_row_append=on_row_append,
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
                project_id=project.id, message=turn_say, suggestion_ref=suggestion_ref
            ),
            recent=recent,
            on_delta=on_delta,
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_checkpoint=on_checkpoint,
            on_loop_event=on_loop_event,
            on_activity=on_activity,
            on_candidates=on_candidates,
            on_row_append=on_row_append,
        )
        return follow_up, run_id, bailed, answered
    follow_up, run_id, bailed, settled = await _propose_turn(
        db, user_id, conversation, project, turn_say, [], recent,
        suggestion_ref=suggestion_ref,
        on_delta=on_delta,
        # I-PFA-06 parity (Batch B 验收修复): the chat-path continuation
        # needs the phase pipe too — a film design span on this branch
        # reports its System Status labels through it (and clears them at
        # the span's exit).
        on_phase=on_phase,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_checkpoint=on_checkpoint,
        on_loop_event=on_loop_event,
        on_activity=on_activity,
        on_candidates=on_candidates,
        on_row_append=on_row_append,
    )
    return follow_up, run_id, bailed, settled


async def answer_question(
    db: AsyncSession,
    user_id: UUID,
    message_id: UUID,
    data: AnswerRequest,
    on_delta=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
    confirmed_via: str = "dock_pill",
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
    # paid runs off one plan. The second waiter re-reads post-commit and
    # hits the 409 below.
    message = await db.get(Message, message_id, with_for_update=True)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
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

    message.answer = AnswerPayload(
        kind=data.kind,
        option_id=data.option_id if data.kind == "option" else None,
        # The answered question shows the option's human label, not its bare id.
        text=(data.text if data.kind == "freeform" else None) or option_label,
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

    if question.kind == "task_book":
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
            # draft graph goes with it (K5 — asset nodes stay: they are the
            # project's inputs, never the plan's).
            project.pending_brief = None
            from app.pipeline.graph_fill import clear_draft_graph  # deferred

            await clear_draft_graph(db, UUID(str(project.id)))
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
            # caption_mode is intent metadata the review panel never edits —
            # a panel-submitted intent without it (client-side normalize may
            # strip fields it doesn't know) says "not mentioned", never
            # "retracted". Inherit the answered mode from the stored pending
            # intent (2026-08-29 — the same doctrine as the plan-turn
            # overwrite fix; without it, answer→Start via the PANEL dropped
            # the mode even though answer→Start via prose kept it).
            if (
                intent is not None
                and intent.caption_mode is None
                and pending is not None
                and pending.intent is not None
                and pending.intent.caption_mode is not None
            ):
                intent = intent.model_copy(
                    update={"caption_mode": pending.intent.caption_mode}
                )
            tasks = list(intent.tasks) if intent is not None else []
            # D3 (Phase 4 B6): the Start seat enforces the SAME four-
            # conjunction lifecycle truth the client reads (门禁三) — "the
            # button is disabled" is the first line, never the only one.
            # The structural guards (no pending plan / empty chain) and the
            # projection verdict (material / adjudication / prerequisite /
            # active conflicting run) all surface as machine-readable codes
            # before paid create_run, never as disguised business errors.
            from app.pipeline.lifecycle import (  # deferred: chat → pipeline
                evaluate_start_gate,               # only, one-directional
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
                film=_film_gate_facts(tasks, pending, message.question),
            )
            if gate is not None:
                detail: dict[str, Any] = {"code": gate.code}
                if gate.blockers:
                    detail["blockers"] = list(gate.blockers)
                raise HTTPException(gate.http_status, detail)
            # The confirmed chain's draft twin must mirror what Start
            # actually runs (K5): the review panel's hand edits (data.intent)
            # may diverge from the last docked stamp — re-sync idempotently
            # (a no-op when unchanged). A chain the birthplace would reject
            # tears the preview down; create_run then 422s as today.
            from app.pipeline.graph_fill import (  # deferred: import cycle
                clear_draft_graph,
                stamp_draft_graph,
            )

            try:
                await stamp_draft_graph(
                    db, project, tasks, current_ui_language()
                )
            except (ToolRejected, ValueError):
                await clear_draft_graph(db, UUID(str(project.id)))
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
                from app.tools.video.production import latest_video_approval
                run = await create_run(
                    db,
                    project,
                    TaskSpec(
                        tasks=tasks,
                        video_authorized_by=await latest_video_approval(db, project),
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
                        scope="full",
                        # Caption mode rides the run context verbatim from
                        # the InferredIntent — the chat path's caption-mode
                        # question stores it on the intent (RECIPES §4.7).
                        caption_mode=intent.caption_mode,
                        # 资产角色 pins (ADR-078 判词④): settled on the
                        # PendingPlan by the role question / the mention,
                        # riding TaskSpec → run.context verbatim. The panel
                        # never edits them (it edits the intent only), so
                        # the stored pending's pins are the confirmed ones.
                        source_asset_id=pending.source_asset_id,
                        exemplar_asset_id=pending.exemplar_asset_id,
                        # The router's fresh naming of the plan (ADR-058) —
                        # the receipt title and completion line read it.
                        name=intent.name or None,
                    ),
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
            project.status = ProjectStatus.PROCESSING
            # The plan is confirmed now — drop the unconfirmed copy.
            project.pending_brief = None
            message.workflow_run_id = run.id
            # Confirmed Scope Snapshot (iter-2 ④, ADR-089 §4 R20 — 销
            # P0-①): the immutable record of WHAT was confirmed at the paid
            # boundary — the reading layer as docked, the exact chain the
            # run was born with, the quote shown at confirm time, and the
            # settings that governed the authorization (ADR-117 — standing
            # authorization is only auditable against its frozen basis).
            # Stamped post-birthplace so a rejected Start never leaves a
            # snapshot.
            from app.pipeline.scope_compile import (  # deferred: pipeline edge
                build_confirmed_scope,
            )

            _scope_user = await db.get(User, user_id)
            _scope_execution, _scope_credits = read_confirmation_prefs(
                _scope_user.settings if _scope_user is not None else None
            )
            run.context = {
                **(run.context or {}),
                "confirmed_scope": build_confirmed_scope(
                    confirmation_id=str(message.id),
                    confirmed_at=datetime.now(UTC).isoformat(),
                    confirmed_via=confirmed_via,
                    plans=list(pending.plans) if pending is not None else [],
                    tasks=tasks,
                    quote=(message.question or {}).get("estimate_credits"),
                    plan_task_map=(
                        pending.plan_task_map if pending is not None else None
                    ),
                    settings={
                        "confirm_execution": _scope_execution,
                        "confirm_credits": _scope_credits,
                        "billing.always_confirm_above": await get_config(
                            db, "billing.always_confirm_above"
                        ),
                    },
                ),
            }
            # prepared_storyboard + the versioned film state (ADR-129): a
            # film chain born from a dock runs the storyboard the user SAW —
            # the stored PendingPlan's dump is the shown truth (世界自证:
            # what they saw is what runs). Validated here before stamping;
            # the worker consumes it STRICTLY — a stale prepared board
            # fails the run with a redesign request, never a silent
            # re-orchestration. The version / content digest / execution
            # snapshot / draft token stamp alongside: 呈现稿 digest = run
            # context digest = render spec digest, one truth. Absent (a
            # draft that never stood at dock time) → the birth orchestrates
            # fresh, by design.
            if any(t.tool == "launch_film" for t in tasks):
                prepared_storyboard = (
                    pending.film_storyboard if pending is not None else None
                )
                if isinstance(prepared_storyboard, dict):
                    try:
                        FilmStoryboard.model_validate(prepared_storyboard)
                    except (ValueError, TypeError):
                        prepared_storyboard = None
                    if prepared_storyboard is not None:
                        from app.tools.film.edits import (  # deferred: tool seam
                            film_music_retime_of,
                        )

                        run.context = {
                            **(run.context or {}),
                            "prepared_storyboard": prepared_storyboard,
                            "film_storyboard_version": (
                                pending.film_storyboard_version
                                if pending is not None
                                else None
                            ),
                            "film_storyboard_content_digest": (
                                pending.film_storyboard_content_digest
                                if pending is not None
                                else None
                            ),
                            "film_storyboard_params": (
                                pending.film_storyboard_params
                                if pending is not None
                                else None
                            ),
                            "film_storyboard_fingerprint": (
                                pending.film_storyboard_fingerprint
                                if pending is not None
                                else None
                            ),
                            "film_execution": (
                                pending.film_storyboard_execution
                                if pending is not None
                                else None
                            ),
                            "film_draft_token": (
                                pending.film_draft_token
                                if pending is not None
                                else None
                            ),
                            # The version envelope (compose|patch|variant +
                            # the base version) — provenance recovery reads
                            # it back through the same keys.
                            "film_created_via": (
                                pending.film_created_via
                                if pending is not None
                                else None
                            ),
                            "film_base_version": (
                                pending.film_base_version
                                if pending is not None
                                else None
                            ),
                            # The surviving set_music retime instruction
                            # (keep_cut|recut — ADR-137): projected as the
                            # instruction's PROVENANCE (and the
                            # half-written-envelope tripwire: keep_cut
                            # without frames fails closed).
                            # ``film_kept_frames`` = the version's frozen
                            # cut (版本状态 — frozen at patch time by a
                            # keep_cut swap, or inherited by a
                            # timeline-preserving edit): the run's frame
                            # seat consumes it fail-closed whenever
                            # present; None = allocate + snap to the bed's
                            # grid as usual.
                            "film_music_retime": film_music_retime_of(pending),
                            "film_kept_frames": (
                                pending.film_kept_frames
                                if pending is not None
                                else None
                            ),
                            # The frozen cut's other half (冻结场内切点):
                            # the reveal words' landing beats — the run
                            # consumes them fail-closed whenever the kept
                            # cut covers a reveal scene.
                            "film_kept_reveal_onsets": (
                                pending.film_kept_reveal_onsets
                                if pending is not None
                                else None
                            ),
                        }
            # E3 双态写者 (first half, iter-3 S1): the confirmed package's
            # plan rows settle ready/revised → compiled IN THE SAME
            # TRANSACTION as the snapshot stamp — the artifact state machine
            # and the paid execution never diverge. Router-drafted docks
            # carry no plans → the call is a no-op.
            from app.pipeline.exploration_store import (  # deferred: pipeline edge
                mark_compiled,
            )

            await mark_compiled(
                db,
                project,
                plan_ids=[
                    UUID(str(p["plan_id"]))
                    for p in (pending.plans if pending is not None else [])
                    if p.get("plan_id")
                ],
            )

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
                    )
        elif data.kind in ("option", "freeform"):
            # No parked node → this run id was the display anchor (trigger
            # suggestion) or the interrupt already expired — the pick is the
            # user's say, carried by the generic continuation (same seat as
            # the no-run-id branch below).
            with bind_conversation_turn() as _usage_bind:
                follow_up, _run_id, bailed_run_ids, _settled = (
                    await _continue_chat_answer(
                        db, user_id, conversation, question, data, option_label,
                        suggestion_ref=_suggestion_ref_for(message, data),
                        on_delta=on_delta,
                        on_phase=on_phase,
                        on_tool_call=on_tool_call,
                        on_tool_ready=on_tool_ready,
                        on_checkpoint=on_checkpoint,
                        on_loop_event=on_loop_event,
                        on_activity=on_activity,
                        on_candidates=on_candidates,
                        on_row_append=on_row_append,
                    )
                )
            await fold_conversation_usage(
                db,
                user_id=user_id,
                project_id=_usage_project_id,
                accrued=_usage_bind.accrued,
            )

    elif question.kind == "question" and data.kind in ("option", "freeform"):
        # 续聊: the answer unblocks the conversation — the user's pick is
        # their say for the next turn, with the answered question in context.
        with bind_conversation_turn() as _usage_bind:
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
                    on_checkpoint=on_checkpoint,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                )
            )
        await fold_conversation_usage(
            db,
            user_id=user_id,
            project_id=_usage_project_id,
            accrued=_usage_bind.accrued,
        )

    elif question.kind == "question" and data.kind == "bail" and question.slot is not None:
        # 默认路径 (提问策略③ / D2-C2): skipping a brief ask TAKES the default
        # path — the plan path resumes and the 出书门槛 docks the
        # draft-from-persona plan (the asked roll already bounds the loop).
        # Nothing backfills; the stand-in line only feeds the inference (it
        # is never persisted as a user message).
        project = await db.get(Project, conversation.project_id)
        if project is not None:
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
            history = await list_conversation_messages(db, UUID(str(conversation.id)))
            # 滑动窗口装配 (ADR-117 D4): one budget predicate, never a
            # fixed-count slice.
            recent = await recent_history_within_budget(db, history)
            with bind_conversation_turn() as _usage_bind:
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
                    on_checkpoint=on_checkpoint,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
                )
            await fold_conversation_usage(
                db,
                user_id=user_id,
                project_id=_usage_project_id,
                accrued=_usage_bind.accrued,
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
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
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
    caller commits — except the start branch, where answer_question commits.

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
        recent=recent,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_phase=on_phase,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_checkpoint=on_checkpoint,
        on_loop_event=on_loop_event,
        on_activity=on_activity,
        on_candidates=on_candidates,
        on_row_append=on_row_append,
    )


async def _propose_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation: Conversation,
    project: Project | None,
    text: str,
    mentions: list[ChatMention],
    recent: list[Message],
    suggestion_ref: SuggestionRef | None = None,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
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
        suggestion_ref=suggestion_ref,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_phase=on_phase,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_checkpoint=on_checkpoint,
        on_loop_event=on_loop_event,
        on_activity=on_activity,
        on_candidates=on_candidates,
        on_row_append=on_row_append,
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
    # 界面语言 owner 盖章（ADR-080 单一叙事者律）: the request's locale is
    # the conversation's ONE speech-language fact — every assistant writer
    # (this turn's reply AND the worker-born trigger) inherits it instead of
    # deriving its own. None-safe: outside a request there is nothing to
    # stamp, and a worker path never erases the owner.
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

    user_message = await _create_message(
        db,
        conversation_id,
        "user",
        request.message,
        attachments=[a.model_dump(mode="json") for a in request.attachments],
        mentions=[m.model_dump(mode="json") for m in request.mentions],
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
    # 'settled'; failure/cancel paths stamp 'failed' best-effort.
    user_message.turn_state = "in_flight"

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
    )


def _checkpoint_callback(db, conversation_id, on_checkpoint=None):
    """The checkpoint channel's turn-runner seat (ADR-085 判词 2/4): the loop
    emits a checkpoint's full prose; the runner persists it as its OWN
    message row — ``intent={"type": "checkpoint"}`` keeps the semantic type
    explicit (never mixed with the settled assistant message: replay renders
    it as a progress bubble, future context may filter on the marker) —
    flush-only, the turn's one commit lands it; then the SSE hook forwards
    the text live. The loop writes nothing (零副作用往返 holds — this hook
    is the runner's, not the loop's). A failed turn rolls the rows back with
    everything else, and the client's turn.failed path drops the bubbles."""
    async def _emit(text: str) -> None:
        message = await _create_message(
            db,
            conversation_id,
            "assistant",
            text,
            intent={"type": "checkpoint"},
        )
        if on_checkpoint is not None:
            # 服务端钟锚定 (ADR-108 数组位置律): forward the row's own
            # created_at so the live bubble carries the same server stamp
            # the persisted array row does — live and replay read one
            # clock. Ordering itself comes from the row's seq, never from
            # this stamp.
            result = on_checkpoint(text, message.created_at.isoformat())
            if result is not None:
                await result

    return _emit


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
            row = await db.get(Message, user_message_id)
            if row is not None and row.turn_state == "in_flight":
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
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            "turn_failed_line_persist_error",
            conversation_id=str(conversation_id),
            error=str(e),
        )


async def execute_chat_turn(
    db: AsyncSession,
    prepared: PreparedTurn,
    request: ChatRequest,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
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
        with bind_conversation_turn() as _usage_bind:
            if prepared.plan_path:
                # The intent router's context excludes this turn's own message
                # (already the prompt being judged); the latest rounds before
                # it are the disambiguating conversation (G-7) — budget-
                # windowed by the one predicate (ADR-117 D4).
                recent = await recent_history_within_budget(
                    db,
                    [m for m in prepared.history if m.id != prepared.user_message.id],
                )
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
                    recent=recent,
                    on_delta=on_delta,
                    on_reasoning=on_reasoning,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_checkpoint=on_checkpoint,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
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
                    await recent_history_within_budget(db, prepared.history),
                    suggestion_ref=request.suggestion_ref,
                    on_delta=on_delta,
                    on_reasoning=on_reasoning,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_checkpoint=on_checkpoint,
                    on_loop_event=on_loop_event,
                    on_activity=on_activity,
                    on_candidates=on_candidates,
                    on_row_append=on_row_append,
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

    # The turn's outcome stamp rides the SAME commit as its writes (交互
    # 完整性批 A): in_flight → settled is atomic with the assistant row /
    # the dock / the run — "message received" and "turn converged" stay two
    # distinct, individually truthful facts (the minimal turn contract).
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


# ---- Material beats (2026-09-24 用户拍板) ---------------------------------
#
# The dock's material rows ("正在阅读 X…" / "正在理解素材内容…") were
# frontend-synthesized and DIED on refresh — the settled gray row the live
# surface showed simply vanished from the rebuilt history. The fix is a
# plain message row: the pipeline records one settled row per beat through
# the ConversationBridge (ADR-087 — pipeline never writes messages directly),
# and the history replay maps it back onto the same ActivityRow component.
# Beats are BORN SETTLED (completed/failed) — the live active row stays the
# dock's synthesized now-line; only the durable settled form rides the wire.

MATERIAL_BEAT_TYPE = "material_beat"


async def record_material_beat(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    beat: str,
    *,
    status: str = "completed",
    name: str | None = None,
    count: int | None = None,
    total: int | None = None,
    ref: str | None = None,
    duration_ms: int | None = None,
    asset_type: str | None = None,
    at: str | None = None,
) -> Message | None:
    """Persist one settled material beat as a message row (once-only per
    (beat, ref) — the warm's re-materialization race and the worker's
    retries collapse onto the first landed row, same doctrine as the
    trigger dump's ``_already_spoke``).

    ``beat``: "reading" (an asset's processing drained — ref = asset id,
    ``name`` = the asset's display name, ``count``/``total`` = the project
    set's drain progress, ``duration_ms`` = the user-perceived reading span
    upload→processed, so the settled row can whisper "· 41s" like every
    other settled activity row) | "understanding" (the warm materialized —
    ref = the asset digest, ``count`` = the asset count). Returns None when
    the beat already landed (dedup) so callers stay fire-and-forget.

    ``asset_type`` (批「动词」2026-09-27): the reading beat carries the
    asset's type so the replay forks the verb (watch/listen/read) — absent
    on rows predating the fork, the replay's read tolerance falls to the
    base key. ``at`` overrides the row's birth stamp for the fold's clock —
    absent on beats whose span starts at landing (reading/understanding)."""
    conversation = await _get_or_create_project_conversation(db, user_id, project_id)
    dedup = select(Message.id).where(
        Message.conversation_id == conversation.id,
        Message.intent["type"].astext == MATERIAL_BEAT_TYPE,
        Message.intent["beat"].astext == beat,
    )
    if ref is not None:
        dedup = dedup.where(Message.intent["ref"].astext == ref)
    if (await db.execute(dedup.limit(1))).scalar_one_or_none() is not None:
        return None
    intent: dict[str, Any] = {"type": MATERIAL_BEAT_TYPE, "beat": beat, "status": status}
    if name is not None:
        intent["name"] = name
    if count is not None:
        intent["count"] = count
    if total is not None:
        intent["total"] = total
    if ref is not None:
        intent["ref"] = ref
    if duration_ms is not None:
        intent["duration_ms"] = duration_ms
    if asset_type is not None:
        intent["asset_type"] = asset_type
    if at is not None:
        intent["at"] = at
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="",
        attachments=[],
        mentions=[],
        intent=intent,
        seq=await alloc_message_seq(UUID(str(conversation.id)), db),
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


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
                Message.intent["type"].astext == MATERIAL_BEAT_TYPE,
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
# the checkpoint seat) or at born-terminal emission (repair terminals /
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
) -> Message:
    """Append ONE activity row at its array position (open / born-terminal)."""
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        attachments=[],
        mentions=[],
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
) -> Message | None:
    """Persist one turn's candidate-surface events (set births + selection
    updates, in emission order) as a single message row — the same doctrine
    as ``record_activity_log``: once-only per ``ref``, completed path only,
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
        intent={"type": CANDIDATES_LOG_TYPE, "ref": ref, "events": events},
        seq=await alloc_message_seq(conversation_id, db),
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message
