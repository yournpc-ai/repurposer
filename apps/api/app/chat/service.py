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
- apply_edit_ops          → Operation Model (ADR-032): registry-validated ops
                            applied to the target output, journaled with
                            message lineage
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
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# The two chat agents no longer take calls HERE (the turn runners —
# app/chat/plan_turn.py / propose_turn.py — drive them through the tool
# loop); importing the declarations module keeps them registered in AGENTS
# at startup (the orchestrator's roster self-check walks it).
from app.chat.intent import chat_intent_agent as _chat_intent_agent  # noqa: F401
from app.chat.intent import intent_router as _intent_router  # noqa: F401
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
    EditOpsProposal,
    InferredIntent,
    Option,
    PendingPlan,
    ProjectStatus,
    QuestionPayload,
    QuestionProposal,
    PlanEstimate,
    TaskItem,
    TaskListProposal,
)
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    Persona,
    Project,
    WorkflowRun,
)
from app.operations.registry import OP_REGISTRY, validate_op
from app.operations.service import OpRejected
from app.pipeline.asset_processing import has_any_text_material, has_renderable_media
from app.pipeline.derivative_dispatch import (
    DerivativeWriterNode,
    _project_source_language,
    derive_quote_alt_language,
)
from app.pipeline.graph import MEDIA, NODE_KINDS
from app.platform.billing import CreditsInsufficientError
from app.platform.conversation_context import (
    find_conversation,
    get_project_prompt,
    is_pending_plan,
    latest_pending_question,
)
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
        return None# ---- brief (DIALOG_WORKFLOW §2.4, ADR-052 B2) --------------------------------

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
        Option(id=str(a.id), label=a.file_url.rsplit("/", 1)[-1]) for a in videos
    ]
    first_name = videos[0].file_url.rsplit("/", 1)[-1]
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
                if (name := v.file_url.rsplit("/", 1)[-1].lower())
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


# Caption mode for captioned-video runs (Phase 1, 2026-08-25, RECIPES §4.7):
# the chat path asks the user to pick bilingual / source_only / target_only
# when a `write_quotes` task is proposed without an explicit caption-mode
# hint. Three layers of detection, in priority order:
#
#  1. LLM-set on InferredIntent.caption_mode (the intent router recognises the
#     user's wording — "bilingual subtitles" / "中英双语字幕" — and sets it).
#  2. Code-level keyword scan on the user prompt (defence-in-depth: the LLM
#     may miss the phrasing, but a literal "bilingual"/"双语" is unambiguous).
#  3. Otherwise: dock an options question, the answer rides the QuestionProposal path.
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


def _build_caption_mode_question(text: str) -> QuestionProposal:
    """The caption-mode options question — bilingual is the canonical default
    (matches the recipe's example prompt and the reference images). The
    option_id prefix `caption_mode_` is a handshake the answer path uses to
    recover the choice (caption_mode_bilingual → Literal "bilingual")."""
    zh = _prefers_zh(text)
    if zh:
        return QuestionProposal(
            type="ask",
            question="字幕模式？",
            options=[
                Option(id="caption_mode_bilingual", label="双语字幕（推荐）"),
                Option(id="caption_mode_source_only", label="只保留源语言"),
                Option(id="caption_mode_target_only", label="只保留目标语言"),
            ],
            allow_freeform=False,
        )
    return QuestionProposal(
        type="ask",
        question="Caption mode?",
        options=[
            Option(id="caption_mode_bilingual", label="Bilingual (recommended)"),
            Option(id="caption_mode_source_only", label="Source language only"),
            Option(id="caption_mode_target_only", label="Target language only"),
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
    """The answered caption mode stashed on the pending brief, if any.

    The answer fast path writes it onto ``pending_brief.intent.caption_mode``
    and every consumption site (plan-turn overwrite, propose-turn run) must
    INHERIT it — a fresh call's ``caption_mode=None`` is "not mentioned
    this turn", never "the user retracted the answer".
    """
    pending = project.pending_brief if isinstance(project.pending_brief, dict) else None
    if not pending:
        return None
    intent = pending.get("intent") or {}
    mode = intent.get("caption_mode")
    return str(mode) if mode else None


def _has_resolved_caption_mode(project: Project) -> bool:
    """A caption-mode question was already answered and the answer is
    reflected in the stored pending_brief — the next plan turn re-uses it
    instead of re-docking the question (the user has spoken). Mirrors the
    pending_brief's role for the plan (CHAT_ARCH §3)."""
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


def _is_caption_mode_question(question: QuestionPayload) -> bool:
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
      - bare ``InferredIntent`` from ``_plan_turn`` (intent_router path; first
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
        # _plan_turn path: bare InferredIntent (the intent router's payload)
        try:
            return InferredIntent.model_validate(stashed)
        except Exception:  # noqa: BLE001
            return None
    return None


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
    interrupt was cascade-bailed by the supersede (finalized by the caller
    after its commit). Flush-only.
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
    _message, bailed_run_ids = await _dock_question(
        db,
        conversation_id,
        content,
        QuestionPayload(
            kind="task_book",
            reasons=reasons or [],
            brief=brief,
            estimate_credits=estimate,
            derived=derived or [],
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
        # 全文卡律 (判词④): the plan doc's face = the intent's own plan
        # prose (intent.answer) — never the deterministic condensed
        # composition (blind to transform chains).
        await stamp_draft_graph(
            db, project, intent.tasks, current_ui_language(), intent.answer
        )
    except (ToolRejected, ValueError):
        logger.warning(
            "draft_graph_stamp_failed",
            project_id=str(project.id),
            exc_info=True,
        )
        await clear_draft_graph(db, UUID(str(project.id)))
    return bailed_run_ids


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


async def answer_question(
    db: AsyncSession,
    user_id: UUID,
    message_id: UUID,
    data: AnswerRequest,
    on_delta=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_loop_event=None,
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
                           rides into the next intent turn (the answered
                           question is in context), the follow-up reply
                           comes back here.
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
        raise HTTPException(status.HTTP_409_CONFLICT, "Question already answered")
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

    # Caption-mode fast path (Phase 1, 2026-08-25, RECIPES §4.7): the question
    # is one of ours when every option_id starts with ``caption_mode_``. The
    # user picked a mode, so we re-stitch the stashed intent (a TaskListProposal
    # from _propose_turn, or a bare InferredIntent from _plan_turn's first
    # turn) into an InferredIntent + PendingPlan and dock a task_book
    # question — the user then confirms with Start like any normal generation.
    # Skipping _propose_turn here is intentional: the LLM would re-derive the
    # task list from the option label alone, which is the brittle 续聊 path.
    if (
        question.kind == "question"
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
                    # (intent → PendingPlan → TaskSpec → run.context) —
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
                    # The brief rides along verbatim — the caption answer
                    # is not a plan turn; no merge, just preservation.
                    preserved_brief = (
                        Brief.model_validate(project.pending_brief["brief"])
                        if isinstance(project.pending_brief, dict)
                        and isinstance(project.pending_brief.get("brief"), dict)
                        else Brief()
                    )
                    project.pending_brief = PendingPlan(
                        prompt=prompt_text,
                        intent=replay_intent,
                        brief=preserved_brief,
                        reasons=await _compute_plan_reasons(db, project, replay_intent),
                        persona_id=(
                            project.pending_brief.get("persona_id")
                            if isinstance(project.pending_brief, dict)
                            else None
                        ),
                        derived=[],
                    ).model_dump(mode="json")
                    # sync_plan_question docks a task_book question; its
                    # bailed_run_ids are the cascade-bailed run interrupts (none
                    # here, but the contract is the same).
                    bailed_run_ids = await sync_plan_question(
                        db, user_id, project, replay_intent, prompt_text,
                        reasons=project.pending_brief["reasons"],
                        brief=preserved_brief,
                        echo=replay_intent.answer,
                        estimate=await _safe_task_estimate(
                            db, project, replay_intent.tasks
                        ),
                    )
                    follow_up = await latest_pending_question(db, UUID(str(conversation.id)))
                    # Skip the 续聊 fallback below — the plan question is
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
                # Same prose law as the dock (判词④): the confirmed intent's
                # own answer is the face (a panel-edited chain keeps the
                # docked prose — the edits ride the tasks, not the summary).
                await stamp_draft_graph(
                    db, project, tasks, current_ui_language(), intent.answer
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

    elif question.kind == "question" and message.workflow_run_id is not None:
        # Direction interrupt (期 4): workflow_run_id is the dispatch
        # marker. The answer resumes the parked run — spec.answer written,
        # node back to pending, run back to RUNNING, the worker re-executes
        # the thin node. Bail is a graceful exit: node done (spec.bailed),
        # downstream cascade-skipped, run settles COMPLETED — never failed.
        # R1 B3: the resume arbitrates the project's execution authority —
        # while another run holds it the answer parks (再挂) and the user
        # hears the honest one-liner, never silence.
        run = await db.get(WorkflowRun, message.workflow_run_id)
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

    elif question.kind == "question" and data.kind in ("option", "freeform"):
        # 续聊: the answer unblocks the conversation — the user's pick is
        # their say for the next turn, with the answered question in context.
        project = await db.get(Project, conversation.project_id)
        say = (data.text if data.kind == "freeform" else None) or option_label or ""
        history = await list_conversation_messages(db, UUID(str(conversation.id)))
        if question.slot == "asset_role" and project is not None:
            # 资产角色消歧的答复落 pin (ADR-078 判词④): the pins settle by
            # CODE (the option id IS the asset id — _settle_role_answer),
            # never a brief backfill — asset_role has no Brief seat, and the
            # generic backfill would setattr-crash on it. The plan path then
            # resumes on the pinned plan, same shape as the brief branch.
            await _settle_role_answer(db, project, data, say)
            follow_up, _run_id, _answered, bailed_run_ids = await _plan_turn(
                db,
                user_id,
                conversation,
                project,
                ChatRequest(project_id=project.id, message=say),
                recent=history[-5:],
                on_delta=on_delta,
                on_phase=on_phase,
                on_tool_call=on_tool_call,
                on_tool_ready=on_tool_ready,
                on_loop_event=on_loop_event,
            )
        elif question.slot is not None and project is not None:
            # ask 一等动作的答复回填 (ADR-052 B2 D2-C1): the brief slot takes
            # the answer user-stated, then the plan path resumes on the
            # enriched brief — draft the (now-rooted) plan or ask the next
            # deciding slot. The answer text rides as the turn's message so
            # the router sees it as the user's own words.
            _backfill_brief_slot(project, question.slot, say)
            follow_up, _run_id, _answered, bailed_run_ids = await _plan_turn(
                db,
                user_id,
                conversation,
                project,
                ChatRequest(project_id=project.id, message=say),
                recent=history[-5:],
                on_delta=on_delta,
                on_phase=on_phase,
                on_tool_call=on_tool_call,
                on_tool_ready=on_tool_ready,
                on_loop_event=on_loop_event,
            )
        else:
            # 选项语法统一律 (ADR-081): trigger suggestion questions land
            # here — the picked label is the user's say. Dispatch by the
            # project's run state (the same probe prepare_chat_turn runs):
            # a PRE-FIRST-RUN pick (the understanding-warmed dock) must
            # draft a PLAN — falling into the proposal path would answer a
            # "make me X" pick with proposal tools instead of a plan.
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
                follow_up, _run_id, _answered, bailed_run_ids = await _plan_turn(
                    db,
                    user_id,
                    conversation,
                    project,
                    ChatRequest(project_id=project.id, message=say),
                    recent=history[-5:],
                    on_delta=on_delta,
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_loop_event=on_loop_event,
                )
            else:
                follow_up, _run_id, bailed_run_ids, _settled = await _propose_turn(
                    db, user_id, conversation, project, say, [], history[-6:],
                    on_delta=on_delta,
                    # I-PFA-06 parity (Batch B 验收修复): the chat-path
                    # continuation needs the phase pipe too — without it
                    # composing stays silent on this branch and a stale
                    # label could linger until the envelope (the exact gap
                    # 交互完整性批 C closed on the main paths).
                    on_phase=on_phase,
                    on_tool_call=on_tool_call,
                    on_tool_ready=on_tool_ready,
                    on_loop_event=on_loop_event,
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
            history = await list_conversation_messages(db, UUID(str(conversation.id)))
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
                recent=history[-5:],
                on_delta=on_delta,
                on_phase=on_phase,
                on_tool_call=on_tool_call,
                on_tool_ready=on_tool_ready,
                on_loop_event=on_loop_event,
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
) -> tuple[Message, UUID | None, Message | None, list[UUID]]:
    """Plan path (intent-surface-unification W1): build / refine / confirm
    the plan inside the chat loop — the ONLY intent surface.

    Entered for project-scope turns while a plan is pending (refine or
    prose confirmation) or before the project's first run (first turn / after
    a bail). Returns the assistant message (the docked/answered question row
    for draft/ask/start), the started run id, the answered task-book question
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
    )


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
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
    on_loop_event=None,
) -> tuple[Message, UUID | None, list[UUID], Message | None]:
    """One assistant turn after the user input is settled (CHAT_ARCH §3).

    Shared by ``chat()`` and the choice-answer continuation in
    ``answer_question`` (the answer endpoint doubles as resume). Returns the
    assistant message, the dispatched run id if any, the run ids whose parked
    interrupt was cascade-bailed, and the pending question this turn settled
    by judgment (ADR-053 R2). Flush-only — the caller commits.

    ADR-077 判词② (2026-09-14): the dispatch retired into the tool
    loop — this body is a shim; the turn lives in ``app/chat/propose_turn.py``
    (the chat intent agent's terminal tools propose_tasks / apply_edit_ops /
    edit_graph / ask_user / answer). Deferred import: the runner imports THIS
    module's machinery.
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
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_phase=on_phase,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_checkpoint=on_checkpoint,
        on_loop_event=on_loop_event,
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

    user_message = await _create_message(
        db,
        conversation_id,
        "user",
        request.message,
        attachments=[a.model_dump(mode="json") for a in request.attachments],
        mentions=[m.model_dump(mode="json") for m in request.mentions],
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
    if answered_question is not None and answered_question.workflow_run_id is not None:
        # Interrupt autoResume (期 4): a typed answer to the docked direction
        # question takes the same dispatch as the answer endpoint — wake the
        # parked run. No LLM turn on top: the wake IS the continuation (the
        # step flow shows the run resuming), so the acknowledgment is a
        # deterministic line. R1 B3: a blocked arbitration (another run
        # holds the authority) speaks the parked line instead.
        from app.pipeline.orchestrator import resume_waiting_interrupt

        outcome = "idle"
        run = await db.get(WorkflowRun, answered_question.workflow_run_id)
        if run is not None:
            outcome = await resume_waiting_interrupt(db, run, answered_question.answer)
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
        await _create_message(
            db,
            conversation_id,
            "assistant",
            text,
            intent={"type": "checkpoint"},
        )
        if on_checkpoint is not None:
            result = on_checkpoint(text)
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
) -> ChatResponse:
    """chat() phase 2: run the agent turn, commit once, assemble the response.

    ``on_delta`` (chat SSE) receives the prose channel's fragments — the
    reply itself now (ADR-077 判词②: speech left the action JSON; the
    typewriter law holds natively); ``on_reasoning`` receives reasoning
    fragments as a liveness signal; ``on_phase`` receives System Status
    labels at REAL macro-state switches — the read→think takeover =
    "composing" (the sole survivor after Phase 3 Batch B retired every
    stand-in: ③ drafting/inspecting/repairing, ⑤ creating_run after the
    B4 CDP dead-window forensics).
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
    elif prepared.plan_path:
        # The intent router's context excludes this turn's own message (already
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
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_checkpoint=on_checkpoint,
            on_loop_event=on_loop_event,
        )
        if plan_answered is not None:
            prepared.answered_question = plan_answered
    else:
        assistant_message, run_id, bailed_run_ids, chat_settled = await _propose_turn(
            db,
            prepared.user_id,
            prepared.conversation,
            prepared.project,
            request.message,
            request.mentions,
            prepared.history[-6:],
            on_delta=on_delta,
            on_reasoning=on_reasoning,
            on_phase=on_phase,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_checkpoint=on_checkpoint,
            on_loop_event=on_loop_event,
        )
        if chat_settled is not None:
            # 插话判定结算 (ADR-053 R2): the agent judged this very message
            # the pending question's answer — surface the settled row so
            # the client's pill clears and the AnsweredQuestion block lands.
            prepared.answered_question = chat_settled

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
    """Return messages in a conversation, oldest first."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())
