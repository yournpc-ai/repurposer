"""Project Chat openings, question answers, native editor turns and durable transcript writes."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


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
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatTurnStopRequest,
    Option,
    ProjectBrief,
    PlanEstimate,
    QuestionPayload,
    QuestionProposal,
    SkillReference,
    SuggestionRef,
)
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    MessageFeedback,
    MessageSeqCounter,
    Output,
    Project,
    User,
    Composition,
    CompositionVersion,
)
from app.platform.billing import CreditsInsufficientError
from app.platform.configs import get_config
from app.platform.conversation_context import (
    latest_pending_question,
)
from app.platform.user_settings import read_confirmation_prefs

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


from app.chat.titles import (
    DEFAULT_CONVERSATION_TITLES as _DEFAULT_CONVERSATION_TITLES,
    derive_conversation_title,
    derive_project_title,
    should_auto_upgrade_title,
)


def _auto_conversation_title(
    text: str,
    *,
    project_title: str | None = None,
    max_len: int = 24,
) -> str:
    """Derive a concise readable title from the opening user message."""
    return derive_conversation_title(text, project_title=project_title, max_len=max_len)


async def resolve_project_conversation(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    conversation_id: UUID | None = None,
) -> Conversation:
    """Resolve an explicit project conversation (404 if foreign/missing) or the most recently active one."""
    if conversation_id is not None:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.project_id == project_id,
                Conversation.asset_id.is_(None),
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return conversation

    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.project_id == project_id,
            Conversation.asset_id.is_(None),
            Conversation.user_id == user_id,
        )
        .order_by(
            Conversation.updated_at.desc().nullslast(),
            Conversation.created_at.desc(),
            Conversation.id.desc(),
        )
        .limit(1)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(
            user_id=user_id,
            project_id=project_id,
            title="Project chat",
            updated_at=datetime.now(UTC),
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


async def _get_or_create_project_conversation(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
) -> Conversation:
    return await resolve_project_conversation(db, user_id, project_id)


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


async def _load_project(db: AsyncSession, project_id: UUID) -> Project | None:
    return await db.get(Project, project_id)


def _prefers_zh(text: str) -> bool:
    """Language heuristic for server-composed reply lines — the CJK check
    rides the user's own words (the turn's text), not a stored setting."""
    return any("一" <= ch <= "鿿" for ch in text)  # CJK Unified Ideographs


@dataclass(frozen=True)
class ConfirmationNeed:
    requires_confirmation: bool
    reason: str = ""
    quote_high: int | None = None
    unquotable: bool = False


def confirmation_need(
    *,
    execution: str,
    credits: str,
    quote_high: int | None,
    unquotable: bool,
    always_confirm_above: int,
) -> ConfirmationNeed:
    if unquotable:
        return ConfirmationNeed(True, "unquotable", quote_high, True)
    if quote_high is not None and quote_high > always_confirm_above:
        return ConfirmationNeed(True, "above_guardrail", quote_high)
    if credits == "ask" and (quote_high or 0) > 0:
        return ConfirmationNeed(True, "credits_pref", quote_high)
    if execution == "ask":
        return ConfirmationNeed(True, "execution_pref", quote_high)
    return ConfirmationNeed(False, "", quote_high, False)


async def resolve_confirmation_need(
    db: AsyncSession,
    user_id: UUID,
    estimate: PlanEstimate | None,
) -> ConfirmationNeed:
    """Apply the account approval preferences and spending limit to this tool quote."""
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
    )


# ---- user-stated brief --------------------------------

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
        ProjectBrief.model_validate(project.pending_brief)
        if isinstance(project.pending_brief, dict)
        else ProjectBrief()
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
    stored = ProjectBrief.model_validate(project.pending_brief or {})
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


# ---- 资产角色 (ADR-078 判词④): the role question + the pin settles -----------
#
# 判词④: source = the user's own material; reference/exemplar = the case whose
# craft the decompiler reverse-compiles. Disambiguation = the ask_user machine
# (slot="asset_role") or an @-mention; the pins are settled by CODE ONLY — the
# LLM frames the question but its options are built here (id = asset id), and
# the answer decodes by id, never by a guessed filename. reference 常驻可回读:
# The brief identifies the selected source and exemplar. A later mention may change them.


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
    """The ONE role-pin write (判词④): the ProjectBrief seats + the exemplar's
    warm fire (the skeleton materializes before any run asks; the claim gate
    holds the run until processing drains, and the processing-completion
    seat re-fires the warm for a still-processing exemplar). Both settle
    paths — the answer's pick and the bail's default — write through here,
    and nothing else does."""
    stored = (
        ProjectBrief.model_validate(project.pending_brief)
        if isinstance(project.pending_brief, dict)
        else ProjectBrief()
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


def _loop_incomplete_text(text: str, result) -> str:
    """An execution limit is not evidence that a requested capability is absent."""
    observations = getattr(result, "observations", [])
    rejections = getattr(result, "rejections", [])
    from app.chat.editor import WRITE_TOOLS

    video_tools = {"create_video", "instantiate_skill_blueprint", *WRITE_TOOLS}
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
        return "这个我现在还做不了。请描述要制作或修改的视频、或想咨询的问题。"
    return (
        "I can't do that yet. Try describing a video to create or edit, "
        "or a question to answer."
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
        intro = "下面的分镜已经保存。本轮后续操作未全部完成。"
        header = "| 镜头 | 时间 | 屏幕文字 | 画面与目的 |"
        divider = "| --- | --- | --- | --- |"
        footer = "请先查看这个已保存版本；未完成的调整仍需另行处理。"
    else:
        intro = (
            "The storyboard below is saved. The requested follow-up did not "
            "fully complete."
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
    text: str, *, version_saved: bool, video_read: dict | None = None,
    exported: bool = False, delivered: bool = False,
) -> str:
    """Honest close after the loop's Film rejection policy stops a retry.

    The two states are deliberately different: a failed correction must not
    erase the fact that an earlier version was saved this turn, while a
    failed first design must not claim that any new storyboard exists.
    """
    if delivered:
        return "已审阅的 MP4 已交付到本次对话。" if _prefers_zh(text) else "The reviewed MP4 is attached to this chat."
    if exported:
        return ("MP4 已导出，本轮未完成交付。" if _prefers_zh(text)
                else "The MP4 was exported. Delivery did not finish in this turn.")
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
) -> None:
    """Supersede outstanding questions in the conversation transaction."""
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
    for message in open_questions:
        message.answer = answer.model_dump(mode="json")


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
) -> Message:
    """Store the new question after closing any preceding unanswered question."""
    await _settle_open_questions(
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
    return message


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
    answered_message: Message | None = None,
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
    on_decision_committed=None,
    turn_id: UUID | None = None,
    run_id: str | None = None,
) -> Message | None:
    """Persist the user decision before continuing the project editor on the same opening."""
    project = await db.get(Project, conversation.project_id)
    say = (
        (data.text if data.kind == "freeform" else None)
        or option_label
        or (" · ".join(answer.text or answer.option_id or "" for answer in data.answers) if data.kind == "group" else "")
    )
    recent = await list_conversation_messages(db, UUID(str(conversation.id)))
    if project is not None:
        if question.items and data.kind in ("group", "bail"):
            _backfill_brief_group(project, question, answers=data.answers)
        elif question.slot == "asset_role":
            if data.kind == "bail":
                await _settle_default_role_pins(db, project)
            else:
                await _settle_role_answer(db, project, data, say)
        elif question.slot is not None and data.kind != "bail":
            _backfill_brief_slot(project, question.slot, say)
    # The user's decision survives model or transport failure.
    await db.commit()
    if on_decision_committed is not None and answered_message is not None:
        await db.refresh(answered_message)
        result = on_decision_committed(answered_message, run_id)
        if result is not None:
            await result
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    await db.refresh(project)
    if turn_id is not None:
        from sqlalchemy import func
        from app.chat.editor_recovery import editor_lock_key
        from app.models.database import AsyncSessionLocal

        # Hold the recovery lease throughout this continuation. Native tools
        # inspect the opening in their own short transactions.
        await db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn_id))))
        async with AsyncSessionLocal() as state_db:
            opening = await _lock_turn_for_transcript_write(state_db, turn_id)
            opening.turn_state = "in_flight"
            await state_db.commit()
    try:
        reply = say or "(The user skipped this question.)"
        opening = next((m for m in recent if m.id == turn_id and m.role == "user"), None)
        mentions = []
        attachments = []
        if opening is not None and data.kind in ("option", "freeform", "group"):
            # A dock selection resolves a detail of the persisted request. The option
            # label alone can look like an instruction to generate an entirely new asset.
            choice = next((o for o in question.options if data.kind == "option" and o.id == data.option_id), None)
            detail = f"\nSelected option description: {choice.description}" if choice and choice.description else ""
            reply = f"{opening.content}\n\nQuestion: {question.question}\nUser answer: {reply}{detail}"
            mentions = opening.mentions or []
            attachments = opening.attachments or []
        follow_up, _ = await _plan_turn(
            db, user_id, conversation, project,
            ChatRequest(project_id=project.id, message=reply, mentions=mentions,
                        attachments=attachments, suggestion_ref=suggestion_ref),
            group_answer_submitted=data.kind == "group", recent=recent, turn_id=turn_id, run_id=run_id,
            on_delta=on_delta, on_phase=on_phase, on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready, on_interim_prose=on_interim_prose,
            on_loop_event=on_loop_event, on_activity=on_activity,
            on_candidates=on_candidates, on_row_append=on_row_append,
        )
        if turn_id is not None:
            opening = await _lock_turn_for_final_commit(db, turn_id)
            opening.turn_state = "settled"
    except BaseException:
        await db.rollback()
        if turn_id is not None:
            await stamp_turn_failed(turn_id)
        raise
    return follow_up


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
    on_decision_committed=None,
    turn_id: UUID | None = None,
    run_id: str | None = None,
) -> tuple[Message, Message | None]:
    """Record one authorized answer and continue the original Chat opening."""
    media_receipt = await db.get(Message, message_id)
    if media_receipt is not None and (media_receipt.intent or {}).get("media_permission"):
        await _lock_turn_for_transcript_write(db, media_receipt.turn_id)

    # Serialize decisions on this question. The second writer sees the committed answer.
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
        if (message.answer or {}).get("text") == "superseded":
            raise HTTPException(
                status.HTTP_409_CONFLICT, {"code": "question.superseded"}
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "question.already_answered"}
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

        if data.kind not in ("option", "bail"):
            raise HTTPException(422, "Select Allow or Decline.")
        project = await db.get(Project, conversation.project_id)
        try:
            execution = await answer_media_permission(db, project, message, data.kind == "option" and data.option_id == "approve")
        except CreditsInsufficientError as exc:
            raise HTTPException(422, {"code": "credits.insufficient", "balance": exc.balance,
                                      "required": exc.required}) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if execution is not None:
            opening = await db.get(Message, turn_id)
            opening.turn_state = "in_flight"
            await db.commit()
            if on_decision_committed is not None:
                await db.refresh(message)
                res = on_decision_committed(message, run_id)
                if res is not None:
                    await res
            # Use the SSE activity writer's transaction throughout the continuation.
            # A worker that already claimed this opening will finish it for history.
            owns_continuation = await db.scalar(select(func.pg_try_advisory_xact_lock(editor_lock_key(turn_id))))
            execution = await wait_for_media_result(execution)
            if on_row_append:
                await on_row_append(execution)
            if owns_continuation:
                follow_up = await continue_media_turn(
                    db, project, execution, on_delta=on_delta, on_phase=on_phase,
                    on_tool_call=on_tool_call, on_tool_ready=on_tool_ready, on_interim_prose=on_interim_prose,
                    on_loop_event=on_loop_event, on_activity=on_activity, on_candidates=on_candidates,
                    on_row_append=on_row_append,
                )
    elif question.kind == "question" and (
        data.kind in ("option", "freeform", "group")
        or (data.kind == "bail" and (question.slot is not None or question.items))
    ):
        # 续聊: the answer unblocks the conversation — the user's pick is
        # their say for the next turn, with the answered question in context.
        with bind_conversation_turn(
            conversation_id=conversation.id, turn_id=turn_id or message.id,
            project_id=conversation.project_id,
        ) as _usage_bind:
            follow_up = (
                await _continue_chat_answer(
                    db,
                    user_id,
                    conversation,
                    question,
                    data,
                    option_label,
                    answered_message=message,
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
                    on_decision_committed=on_decision_committed,
                    turn_id=turn_id,
                    run_id=run_id,
                )
            )
        await fold_conversation_usage(
            db,
            user_id=user_id,
            project_id=_usage_project_id,
            accrued=_usage_bind.accrued,
        )

    await db.commit()
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
    run_id: str | None = None,
    group_answer_submitted: bool = False,
    authorized_media: Message | None = None,
    review_pinned_export: bool = False,
) -> tuple[Message | None, Message | None]:
    """Execute the native tool loop for an owned project opening."""
    from app.chat.plan_turn import run_plan_turn

    if skill is None and turn_id is not None:
        opening = next((row for row in recent or () if row.id == turn_id and row.role == "user"), None)
        reference = (opening.intent or {}).get("skill") if opening else None
        if reference:
            from pydantic import TypeAdapter
            from app.skills.resolution import resolve_chat_skill

            skill = await resolve_chat_skill(
                db, owner_id=user_id, reference=TypeAdapter(SkillReference).validate_python(reference),
            )

    return await run_plan_turn(
        db,
        user_id,
        conversation,
        project,
        request,
        skill=skill,
        recent=recent,
        group_answer_submitted=group_answer_submitted,
        authorized_media=authorized_media,
        review_pinned_export=review_pinned_export,
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
        run_id=run_id,
    )


@dataclass
class PreparedTurn:
    """Owned project and durable input committed before the native tool loop begins."""

    user_id: UUID
    conversation: Conversation
    conversation_id: UUID
    user_message: Message
    project: Project
    history: list[Message]
    answered_question: Message | None
    skill: SkillReference | None = None


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
    conversation = await resolve_project_conversation(
        db, user_id, request.project_id, request.conversation_id
    )
    conversation_id = UUID(str(conversation.id))
    project_row = await db.get(Project, request.project_id)
    conv_ctx = dict(conversation.context or {"schema_version": 1, "items": []})
    if (
        project_row is not None
        and request.message.strip()
        and should_auto_upgrade_title(
            project_row.title,
            auto_title=conv_ctx.get("auto_project_title"),
            user_edited=bool(project_row.title_user_edited),
            is_project=True,
        )
    ):
        derived_proj = derive_project_title(request.message, fallback=project_row.title or "Untitled")
        project_row.title = derived_proj
        conv_ctx["auto_project_title"] = derived_proj
    if (
        request.message.strip()
        and should_auto_upgrade_title(
            conversation.title,
            auto_title=conv_ctx.get("auto_title"),
            user_edited=bool(conversation.title_user_edited or conv_ctx.get("title_user_edited")),
        )
    ):
        next_title = _auto_conversation_title(
            request.message,
            project_title=project_row.title if project_row is not None else None,
        )
        conversation.title = next_title
        conv_ctx["auto_title"] = next_title
        conv_ctx.setdefault("title_stage", "l0")
    conversation.context = conv_ctx
    conversation.updated_at = datetime.now(UTC)
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
    from app.skills.resolution import SkillResolutionError, resolve_chat_skill
    from app.skills.store import SkillNotFoundError

    pending = await latest_pending_question(db, conversation_id)
    try:
        skill = await resolve_chat_skill(db, owner_id=user_id, reference=request.skill)
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
        intent={"skill": skill.model_dump(mode="json")} if skill is not None else None,
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
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    history = await list_conversation_messages(db, conversation_id)
    # Deterministic autoResume (zero LLM): while a question is pending,
    # the user's free text settles it ONLY on an unambiguous option hit
    # (letter / number / verbatim label — ADR-053: the "any text =
    # freeform answer" masking is retired; every other message is judged
    # by the intent router / chat intent agent in context, and only a
    # judged answer settles the row — an interjection leaves it pending
    # and the reply gets the reminder tail).
    answered_question: Message | None = None
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
        skill=skill,
    )


class TurnStopped(Exception):
    """A Stop decision won before this transcript/final-commit write."""


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
    """
    query = (
        select(Message)
        .where(Message.id == turn_id)
        .execution_options(populate_existing=True)
    )
    # NO KEY UPDATE serializes Stop and transcript writes, while permitting
    # foreign-key checks from inserts of this opening's child messages.
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
    *,
    run_id: str | None = None,
    rail_note: bool = False,
) -> Message:
    """Persist one middle-of-Turn prose row and replace its trailing partial."""
    await _lock_turn_for_transcript_write(db, turn_id)
    await db.execute(
        delete(Message).where(
            Message.turn_id == turn_id,
            Message.intent["type"].astext == "partial",
        )
    )
    intent: dict[str, Any] = {"type": "interim_prose"}
    if run_id:
        intent["run_id"] = run_id
    if rail_note:
        intent["rail_note"] = True
    return await _create_message(
        db,
        conversation_id,
        "assistant",
        text,
        intent=intent,
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
    db, conversation_id, on_interim_prose=None, turn_id: UUID | None = None, run_id: str | None = None
):
    """Persist interim prose before exposing its stable row identity on SSE.

    Option A single-rail invariant: only the FIRST interim prose of a Run
    lands as a visible opening ``stage_note`` above the work rail; any
    subsequent mid-run interim prose is born as ``rail_note`` directly inside
    the Run's single collapsible work rail (never flashes in main chat, never
    splits ``工作了 Xs`` into multiple fragments).
    """
    import inspect

    emitted_count = 0
    accepts_display_role = False
    if on_interim_prose is not None:
        try:
            sig = inspect.signature(on_interim_prose)
            accepts_display_role = (
                "display_role" in sig.parameters
                or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            )
        except (TypeError, ValueError):
            accepts_display_role = False

    async def _emit(text: str) -> None:
        nonlocal emitted_count
        rail_note = emitted_count > 0
        emitted_count += 1
        display_role = "rail_note" if rail_note else "stage_note"
        if turn_id is None:
            intent: dict[str, Any] = {"type": "interim_prose"}
            if run_id:
                intent["run_id"] = run_id
            if rail_note:
                intent["rail_note"] = True
            await _create_message(db, conversation_id, "assistant", text, intent=intent)
            return

        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as interim_db:
            message = await persist_interim_prose(
                interim_db, conversation_id, turn_id, text, run_id=run_id, rail_note=rail_note
            )
            await interim_db.commit()
        if on_interim_prose is None:
            return
        if accepts_display_role:
            result = on_interim_prose(
                text,
                message.created_at.isoformat(),
                str(message.id),
                message.seq,
                display_role=display_role,
            )
        else:
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
                 and ((m.intent or {}).get("media_job") or (m.intent or {}).get("export_job") or (m.intent or {}).get("media_result"))}
    for m in assistant_rows:
        permission = (m.intent or {}).get("media_permission")
        if permission and (m.intent.get("media_receipt_id") or permission.get("recovery_quote")):
            media_rows.add(m.id)
            if not m.answer and m.question:
                m.answer = AnswerPayload(kind="bail", text="Stopped", answered_at=datetime.now(UTC)).model_dump(mode="json")
                m.intent = {**m.intent, "media_result": {"status": "cancelled"}}
    deliveries = {m.id for m in assistant_rows if (m.intent or {}).get("reviewed_version") and (m.intent or {}).get("output_refs")}
    if media_rows:
        project_id = await db.scalar(select(Conversation.project_id).where(Conversation.id == row.conversation_id))
        project = await db.get(Project, project_id, with_for_update=True)
        for message_id in media_rows:
            if job_id := (by_id[message_id].intent or {}).get("export_job"):
                from app.pipeline.export_jobs import cancel_export
                await cancel_export(db, project, UUID(job_id))
            if job_id := (by_id[message_id].intent or {}).get("media_job"):
                from app.pipeline.media_jobs import cancel_media
                await cancel_media(db, project, UUID(job_id))
    members = {m.id for m in assistant_rows if ((m.intent or {}).get("frame") or {}).get("group_id")}
    committed = bool(members) or bool((row.intent or {}).get("editor_commits")) or bool(media_rows or deliveries)
    if not committed and not visible_prose and not visible_activity and not visible_structure:
        await db.execute(
            delete(Message)
            .where(Message.id.in_([message.id for message in turn_rows]))
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        return "retracted"

    now = datetime.now(UTC).isoformat()
    keep_ids = visible_prose | visible_activity | visible_structure | media_rows | members | deliveries
    delete_ids = [message.id for message in assistant_rows if message.id not in keep_ids]
    if delete_ids:
        await db.execute(
            delete(Message)
            .where(Message.id.in_(delete_ids))
            .execution_options(synchronize_session=False)
        )
    for message_id in keep_ids - media_rows - deliveries:
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


async def settle_interrupted_turn(user_message_id: UUID, conversation_id: UUID) -> str | None:
    state, _ = await settle_failed_chat_turn(user_message_id, conversation_id)
    return state


async def settle_failed_chat_turn(
    user_message_id: UUID, conversation_id: UUID, failure_detail: str | None = None,
) -> tuple[str | None, Message | None]:
    """Idempotently clean up an unexpected disconnect.

    Stop has already been settled atomically by its control endpoint. This path
    never re-derives cancelled versus retracted from durable database content.
    """
    from app.models.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(Message, user_message_id, with_for_update=True)
            if row is None or row.conversation_id != conversation_id:
                return None, None
            if row.turn_state != "in_flight":
                message = None
                if row.turn_state == "failed" and failure_detail is not None:
                    message = await db.scalar(select(Message).where(
                        Message.turn_id == row.id, Message.conversation_id == conversation_id,
                        Message.intent["type"].astext.in_(("editor_recovery", "turn_failed")),
                    ).order_by(Message.seq.desc()).limit(1))
                return row.turn_state, message
            from app.chat.editor_recovery import report_committed_edits
            message = await report_committed_edits(db, row, failure_detail=failure_detail)
            row.turn_state = "failed"
            await db.commit()
            return "failed", message
    except Exception as e:  # noqa: BLE001 — teardown is best-effort
        logger.warning(
            "turn_interrupted_settle_error",
            message_id=str(user_message_id),
            error=str(e),
        )
        return None, None


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


async def mark_turn_steps_failed(user_message_id: UUID) -> list[dict[str, str]] | None:
    """Mark any in-progress step on the opening turn row as failed so StepsPlanCard
    survives failures and refreshes with an honest visual failure marker."""
    from app.models.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(Message, user_message_id, with_for_update=True)
            if row is None:
                return None
            intent = dict(row.intent or {})
            steps = intent.get("steps")
            if not isinstance(steps, list) or not steps:
                return None
            updated = []
            changed = False
            for item in steps:
                if isinstance(item, dict) and item.get("status") == "in_progress":
                    updated.append({**item, "status": "failed"})
                    changed = True
                else:
                    updated.append(item)
            if not changed:
                return steps
            intent["steps"] = updated
            row.intent = intent
            await db.commit()
            return updated
    except Exception as e:  # noqa: BLE001 — best-effort on failure teardown
        logger.warning("mark_turn_steps_failed_error", turn_id=str(user_message_id), error=str(e))
        return None


async def persist_turn_failed_line(
    conversation_id,
    detail: str,
    turn_id: UUID | None = None,
    *,
    run_id: str | None = None,
    checkpoint: dict[str, Any] | None = None,
) -> Message | None:
    """Persist a failed turn's honest line as ONE assistant row (intent
    ``{"type": "turn_failed"}``) — the live failure checkpoint's durable twin, so
    a refresh keeps the failure's stage and its lawful next step instead of
    dropping them. Best-effort, fresh session; never raises."""
    from app.models.database import AsyncSessionLocal  # deferred: failure path

    if not detail.strip():
        return None
    try:
        async with AsyncSessionLocal() as db:
            intent: dict[str, Any] = {"type": "turn_failed"}
            if run_id:
                intent["run_id"] = run_id
            if checkpoint:
                intent["checkpoint"] = checkpoint
            row = await _create_message(
                db,
                conversation_id,
                "assistant",
                detail,
                intent=intent,
                turn_id=turn_id,
            )
            await db.commit()
            return row
    except Exception as e:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            "turn_failed_line_persist_error",
            conversation_id=str(conversation_id),
            error=str(e),
        )
        return None


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
    run_id: str | None = None,
) -> ChatResponse:
    """chat() phase 2: run the agent turn, commit once, assemble the response."""
    with bind_conversation_turn(
        conversation_id=prepared.conversation_id, turn_id=prepared.user_message.id,
        project_id=prepared.project.id,
    ) as usage:
        assistant_message, answered = await _plan_turn(
            db, prepared.user_id, prepared.conversation, prepared.project, request,
            skill=prepared.skill,
            recent=prepared.history, turn_id=prepared.user_message.id, run_id=run_id,
            on_delta=on_delta, on_reasoning=on_reasoning, on_phase=on_phase,
            on_tool_call=on_tool_call, on_tool_ready=on_tool_ready, on_interim_prose=on_interim_prose,
            on_loop_event=on_loop_event, on_activity=on_activity, on_candidates=on_candidates,
            on_row_append=on_row_append,
        )
        if answered is not None:
            prepared.answered_question = answered
    await fold_conversation_usage(
        db, user_id=prepared.user_id, project_id=prepared.project.id, accrued=usage.accrued,
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
    conv_row = await db.get(Conversation, prepared.conversation_id)
    if conv_row is not None:
        conv_row.updated_at = datetime.now(UTC)
    await db.commit()
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
    then execute the native tool calls against that opening. The SSE path calls the two phases itself so prose deltas can
    stream between them.
    """
    prepared = await prepare_chat_turn(db, user_id, request)
    from app.chat.routes import persistent_activity_hooks
    from app.pipeline.errors import user_error_line
    from app.providers.llm.base import LLMError
    from app.ui_locale import current_ui_language

    opening_id = prepared.user_message.id
    hooks, cancel_open = persistent_activity_hooks(db, prepared.conversation_id, opening_id)
    try:
        return await execute_chat_turn(db, prepared, request, **hooks)
    except LLMError as exc:
        # Release the turn transaction before inspecting separately committed edits.
        await db.rollback()
        opening = await db.get(Message, opening_id)
        if opening and (opening.intent or {}).get("editor_commits"):
            detail = user_error_line(exc, current_ui_language() or "en")
            _, message = await settle_failed_chat_turn(opening_id, prepared.conversation_id, detail)
            if message is not None:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, message.content) from exc
        raise
    finally:
        await cancel_open()


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

    # Never inject a turn_id-less asset-reading row into the middle of an
    # actively running turn — the turn already owns its capture_web /
    # prepare_video_materials activity row, and a NULL turn_id row would split
    # the persisted work fold on refresh.
    active_turn = (
        await db.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation.id,
                Message.turn_state == "in_flight",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if active_turn is not None:
        return None

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
    new_understanding = project_id is not None and await db.scalar(
        select(Output.id).where(Output.project_id == project_id, Output.type == "material_understanding",
                                Output.created_at > source.created_at).limit(1)
    ) is not None
    edited_since = project_id is not None and await db.scalar(
        select(CompositionVersion.id).join(Composition, Composition.id == CompositionVersion.composition_id)
        .where(Composition.origin_project_id == project_id, CompositionVersion.created_at > source.created_at)
        .limit(1)
    ) is not None
    reasons = suggestion_stale_reasons(
        assets_missing=assets_missing,
        assets_failed=assets_failed,
        new_understanding=new_understanding,
        edited_since=edited_since,
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


async def append_activity_row(
    db: AsyncSession,
    conversation_id: UUID,
    frame: dict[str, Any],
    *,
    turn_id: UUID | None = None,
    run_id: str | None = None,
) -> Message:
    """Append ONE activity row at its array position (open / born-terminal)."""
    if turn_id is not None:
        await _lock_turn_for_transcript_write(db, turn_id)
    intent: dict[str, Any] = {"type": ACTIVITY_ROW_TYPE, "frame": frame}
    if run_id:
        intent["run_id"] = run_id
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        attachments=[],
        mentions=[],
        turn_id=turn_id,
        intent=intent,
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
    existing_run_id = (message.intent or {}).get("run_id")
    intent: dict[str, Any] = {"type": ACTIVITY_ROW_TYPE, "frame": frame}
    if existing_run_id:
        intent["run_id"] = existing_run_id
    message.intent = intent
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


_INTERNAL_INTENT_TYPES = frozenset({
    ACTIVITY_ROW_TYPE,
    ACTIVITY_FORENSICS_TYPE,
    CANDIDATES_LOG_TYPE,
    "partial",
})


def _is_conversational_message(row: Message) -> bool:
    if row.role not in {"user", "assistant"}:
        return False
    intent = row.intent or {}
    if intent.get("type") in _INTERNAL_INTENT_TYPES:
        return False
    if "editor_media" in intent and not (row.content or "").strip():
        return False
    return bool((row.content or "").strip() or row.question)


def _deterministic_compact_summary(
    rows: list[Message],
    prior_summary: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Fast deterministic extractive summary used as baseline and offline/test fallback."""
    parts: list[str] = []
    decisions: list[str] = []
    if isinstance(prior_summary, dict) and prior_summary.get("summary"):
        parts.append(str(prior_summary["summary"]).strip()[:600])
        for item in prior_summary.get("key_decisions") or []:
            if isinstance(item, str) and item.strip() and item.strip() not in decisions:
                decisions.append(item.strip()[:160])

    user_snippets: list[str] = []
    assistant_snippets: list[str] = []
    for row in rows:
        text = re.sub(r"\s+", " ", (row.content or "").strip())
        if not text:
            continue
        snippet = text[:180] + ("…" if len(text) > 180 else "")
        if row.role == "user":
            user_snippets.append(snippet)
            if len(decisions) < 8:
                decisions.append(snippet[:140])
        else:
            assistant_snippets.append(snippet)

    if user_snippets:
        parts.append("User requests: " + " | ".join(user_snippets[-4:]))
    if assistant_snippets:
        parts.append("Assistant outcomes: " + " | ".join(assistant_snippets[-3:]))
    summary = "\n".join(p for p in parts if p).strip()
    if not summary:
        summary = "Conversation compacted with no prior messages."
    return summary[:1600], decisions[:8]


async def _try_llm_compact_summary(
    rows: list[Message],
    prior_summary: dict[str, Any] | None,
    ui_language: str | None,
) -> tuple[str, list[str]] | None:
    """Attempt a compact structured summary via the configured LLM, returning None on failure."""
    import asyncio
    import json
    import os

    if "PYTEST_CURRENT_TEST" in os.environ or not rows:
        return None
    try:
        from app.providers.llm import get_llm_client

        client = get_llm_client()
    except Exception:  # noqa: BLE001
        return None

    transcript_lines: list[str] = []
    if isinstance(prior_summary, dict) and prior_summary.get("summary"):
        transcript_lines.append(f"[Prior summary] {str(prior_summary['summary'])[:600]}")
    for row in rows[-40:]:
        text = re.sub(r"\s+", " ", (row.content or "").strip())
        if not text:
            continue
        transcript_lines.append(f"{row.role}: {text[:400]}")
    if not transcript_lines:
        return None
    lang_hint = "Chinese" if (ui_language or "").startswith("zh") or _prefers_zh("\n".join(transcript_lines)) else "English"
    system_prompt = (
        f"Summarize the conversation concisely in {lang_hint} for continuing video editing work. "
        "Return strict JSON only: {\"summary\": \"<=300 chars concise summary\", "
        "\"key_decisions\": [\"up to 6 concrete decisions/preferences\"]}."
    )
    try:
        raw = await asyncio.wait_for(
            client.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n".join(transcript_lines)[:8000]},
                ],
                temperature=0.2,
                max_tokens=500,
                thinking=False,
            ),
            timeout=15.0,
        )
        text = raw if isinstance(raw, str) else getattr(raw, "content", "") or ""
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        parsed = json.loads(match.group(0))
        summary = str(parsed.get("summary") or "").strip()
        raw_decisions = parsed.get("key_decisions") or []
        decisions = [
            str(item).strip()[:160]
            for item in raw_decisions
            if isinstance(item, str) and item.strip()
        ][:8]
        if summary:
            return summary[:1600], decisions
    except Exception:  # noqa: BLE001
        return None
    return None


async def compact_conversation_context(
    db: AsyncSession,
    conversation: Conversation,
) -> dict[str, Any]:
    """Compact settled messages in a conversation into Conversation.context['compact_summary']."""
    all_rows = await list_conversation_messages(db, UUID(str(conversation.id)))
    latest_seq = max((int(row.seq) for row in all_rows if row.seq is not None), default=0)
    prior_ctx = dict(conversation.context or {"schema_version": 1, "items": []})
    prior_summary = prior_ctx.get("compact_summary")
    prior_seq = 0
    if isinstance(prior_summary, dict):
        try:
            prior_seq = int(prior_summary.get("compacted_through_seq") or 0)
        except (TypeError, ValueError):
            prior_seq = 0

    delta_rows = [
        row
        for row in all_rows
        if _is_conversational_message(row) and (row.seq or 0) > prior_seq
    ]
    total_conv_messages = sum(1 for row in all_rows if _is_conversational_message(row))

    llm_result = await _try_llm_compact_summary(delta_rows, prior_summary, conversation.ui_language)
    if llm_result is not None:
        summary, key_decisions = llm_result
    else:
        summary, key_decisions = _deterministic_compact_summary(delta_rows, prior_summary)

    now = datetime.now(UTC)
    compact_record: dict[str, Any] = {
        "summary": summary,
        "key_decisions": key_decisions,
        "compacted_through_seq": latest_seq,
        "compacted_at": now.isoformat(),
        "message_count": total_conv_messages,
    }
    conversation.context = {**prior_ctx, "compact_summary": compact_record}
    conversation.updated_at = now
    await db.commit()
    await db.refresh(conversation)
    return compact_record


async def upsert_message_feedback(
    db: AsyncSession,
    user_id: UUID,
    message_id: UUID,
    *,
    rating: str | None,
    reason: str | None = None,
    tags: list[str] | None = None,
) -> MessageFeedback | None:
    """Create/update or delete per-user evaluation feedback with a frozen context snapshot."""
    message = await db.get(Message, message_id)
    conversation = (
        await db.get(Conversation, message.conversation_id)
        if message is not None
        else None
    )
    if message is None or conversation is None or conversation.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if message.role != "assistant":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Feedback is only supported on assistant messages.",
        )

    if rating is None:
        await db.execute(
            delete(MessageFeedback).where(
                MessageFeedback.message_id == message_id,
                MessageFeedback.user_id == user_id,
            )
        )
        await db.commit()
        return None

    # Resolve opening user message for this turn
    opening: Message | None = None
    if message.turn_id is not None:
        opening = await db.get(Message, message.turn_id)
    if opening is None:
        opening = await db.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.role == "user",
                Message.seq < (message.seq or 0),
            )
            .order_by(Message.seq.desc())
            .limit(1)
        )

    msg_intent = dict(message.intent or {})
    eval_meta = dict(msg_intent.get("eval_meta") or {})

    # Collect turn tool trace (activities + forensics)
    activities: list[dict[str, Any]] = []
    forensics: list[dict[str, Any]] = []
    trace_turn_id = message.turn_id or (opening.id if opening is not None else None)
    if trace_turn_id is not None:
        turn_rows = list(
            await db.scalars(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    or_(
                        Message.turn_id == trace_turn_id,
                        Message.intent["ref"].astext == str(trace_turn_id),
                    ),
                )
                .order_by(Message.seq.asc().nulls_last(), Message.created_at.asc())
            )
        )
        for row in turn_rows:
            row_intent = row.intent or {}
            row_type = row_intent.get("type")
            if row_type == ACTIVITY_ROW_TYPE:
                frame = row_intent.get("frame") or {}
                activities.append(
                    {
                        "key": frame.get("key"),
                        "detail": frame.get("detail"),
                        "status": frame.get("status"),
                        "duration_ms": frame.get("duration_ms"),
                        "receipt": frame.get("receipt"),
                    }
                )
            elif row_type == ACTIVITY_FORENSICS_TYPE:
                forensics.extend(row_intent.get("rejections") or [])

    # Resolve composition_ref snapshot
    composition_ref: dict[str, Any] | None = None
    comp_id_raw = eval_meta.get("composition_id")
    ver_id_raw = eval_meta.get("composition_version_id")
    if not ver_id_raw:
        for block in message.blocks or []:
            if isinstance(block, dict) and block.get("composition_version_id"):
                ver_id_raw = block.get("composition_version_id")
                comp_id_raw = comp_id_raw or block.get("composition_id")
                break
    version_row: CompositionVersion | None = None
    if ver_id_raw:
        try:
            version_row = await db.get(CompositionVersion, UUID(str(ver_id_raw)))
        except ValueError:
            version_row = None
    if version_row is None and conversation.project_id is not None:
        comp_row = await db.scalar(
            select(Composition)
            .where(
                Composition.origin_project_id == conversation.project_id,
                Composition.owner_id == user_id,
            )
            .order_by(Composition.created_at.desc())
            .limit(1)
        )
        if comp_row is not None and comp_row.current_version_id is not None:
            version_row = await db.get(CompositionVersion, comp_row.current_version_id)
    if version_row is not None:
        composition_ref = {
            "composition_id": str(version_row.composition_id),
            "version_id": str(version_row.id),
            "version_number": version_row.version,
            "style_preset": ((version_row.settings or {}).get("style") or {}).get("preset_id"),
        }
    elif comp_id_raw or ver_id_raw:
        composition_ref = {
            "composition_id": str(comp_id_raw) if comp_id_raw else None,
            "version_id": str(ver_id_raw) if ver_id_raw else None,
            "version_number": None,
            "style_preset": None,
        }

    opening_intent = (opening.intent or {}) if opening is not None else {}
    context_snapshot: dict[str, Any] = {
        "user_prompt": (
            {
                "message_id": str(opening.id),
                "content": opening.content or "",
                "mentions": opening.mentions or [],
                "attachments": opening.attachments or [],
                "skill_reference": opening_intent.get("skill") or eval_meta.get("skill_reference"),
            }
            if opening is not None
            else None
        ),
        "assistant_reply": {
            "message_id": str(message.id),
            "content": message.content or "",
            "blocks": message.blocks or [],
            "steps": msg_intent.get("steps"),
        },
        "prompt_meta": {
            "model_name": eval_meta.get("model_name"),
            "system_prompt_sha256": eval_meta.get("system_prompt_sha256"),
            "interaction_policy_version": (
                eval_meta.get("interaction_policy_version")
                or msg_intent.get("interaction_policy_version")
                or INTERACTION_POLICY_VERSION
            ),
            "assembled_context_excerpt": eval_meta.get("assembled_context_excerpt"),
        },
        "tool_trace": {
            "activities": activities,
            "forensics": forensics,
        },
        "composition_ref": composition_ref,
        "compact_summary": (conversation.context or {}).get("compact_summary"),
    }

    clean_tags = [t.strip()[:48] for t in (tags or []) if isinstance(t, str) and t.strip()][:10]
    clean_reason = reason.strip() if isinstance(reason, str) and reason.strip() else None
    now = datetime.now(UTC)

    stmt = (
        pg_insert(MessageFeedback)
        .values(
            user_id=user_id,
            project_id=conversation.project_id,
            conversation_id=conversation.id,
            message_id=message.id,
            turn_id=opening.id if opening is not None else message.turn_id,
            rating=rating,
            reason=clean_reason,
            tags=clean_tags,
            context_snapshot=context_snapshot,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_message_feedback_msg_user",
            set_={
                "rating": rating,
                "reason": clean_reason,
                "tags": clean_tags,
                "context_snapshot": context_snapshot,
                "updated_at": now,
            },
        )
        .returning(MessageFeedback.id)
    )
    feedback_id = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return await db.get(MessageFeedback, feedback_id)
