"""Progressive project and conversation title derivation and refinement.

Separates project identity (brand / subject folder) from conversation intent
(concise task phrase), progressively refines titles as tool steps and turns
unfold (without waiting for a final video render), and strictly protects
user-edited titles via the persisted ``title_user_edited`` lock.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

DEFAULT_CONVERSATION_TITLES = frozenset({"", "Project chat", "New chat", "新对话"})
DEFAULT_PROJECT_TITLES = frozenset({"", "Untitled", "Untitled project", "未命名", "未命名项目"})

_URL_RE = re.compile(r"https?://[^\s<>\"'）)\]]+", re.IGNORECASE)
_GENERIC_SUBDOMAINS = frozenset(
    {"www", "app", "agent", "web", "m", "mobile", "beta", "docs", "staging", "dev", "api", "studio", "get", "try"}
)
_ZH_FILLER_RE = re.compile(
    r"^(?:请你?|麻烦你?|请?帮我(?:把|给)?|给我|帮我|我想(?:要)?(?:做|剪|生成|制作)?|我要(?:做|剪|制作)?|给|把)\s*"
)
_EN_FILLER_RE = re.compile(
    r"^(?:please\s+|can you\s+|could you\s+|help me\s+)?(?:create|make|generate|build|cut|edit)\s+(?:a|an|me\s+a|me\s+an|the)?\s*",
    re.IGNORECASE,
)
_LEADING_VERB_ZH_RE = re.compile(
    r"^(做|制作|生成|剪辑|剪|编写|写|创作|策划|设计|整理|分析|总结)(?:一?[支条个份部段篇张套次])?\s*"
)
_TRAILING_PUNCT_RE = re.compile(r"[\s,，。！？!?：:；;、]+$")
_WRAPPER_QUOTES_RE = re.compile(r"^[\s\"'“”‘’「」『』《》【】\[\]`*#\-]+|[\s\"'“”‘’「」『』《》【】\[\]`*]+$")
_RAW_URL_HINT_RE = re.compile(r"https?://", re.IGNORECASE)


class TitleSummaryPayload(BaseModel):
    """Structured LLM output for sidebar project + conversation naming."""

    project_title: str | None = None
    conversation_title: str | None = None


def _normalize_zh_task_phrase(text: str) -> str:
    """Keep natural action verbs for short nouns (e.g. '制作一个宣传片' -> '制作宣传片')
    while trimming filler quantifiers and redundant generic verbs on already-detailed phrases."""
    match = _LEADING_VERB_ZH_RE.match(text)
    if not match:
        return text
    verb = match.group(1)
    rest = text[match.end() :].strip()
    if not rest:
        return text
    # Already descriptive phrase (e.g. "30s 中文宣传片"): dropping generic "做/剪/生成" stays crisp.
    if len(rest) >= 6 and verb in {"做", "制作", "生成", "剪"}:
        return rest
    normalized_verb = {"做": "制作", "剪": "剪辑"}.get(verb, verb)
    return f"{normalized_verb}{rest}"


def _format_domain_brand(host: str) -> str:
    clean = host.strip().lower().split(":")[0]
    parts = [p for p in clean.split(".") if p]
    if not parts:
        return ""
    # Drop TLD (and common second-level TLDs like co.uk / com.cn)
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "edu", "gov"} and len(parts[-1]) == 2:
        core = parts[:-2]
    elif len(parts) >= 2:
        core = parts[:-1]
    else:
        core = parts
    # Skip generic host prefixes such as www / agent / app when a deeper stem exists
    while len(core) > 1 and core[0] in _GENERIC_SUBDOMAINS:
        core = core[1:]
    stem = core[-1] if core else parts[0]
    words = [w for w in re.split(r"[-_]+", stem) if w]
    if not words:
        return ""
    formatted = " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)
    return formatted


def extract_url_brand(text: str) -> str | None:
    """Return a readable brand name from the first URL in text, if any."""
    match = _URL_RE.search(text or "")
    if not match:
        return None
    parsed = urlparse(match.group(0))
    if not parsed.netloc:
        return None
    brand = _format_domain_brand(parsed.netloc)
    return brand or None


def _truncate(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def derive_project_title(text: str, *, max_len: int = 24, fallback: str = "Untitled") -> str:
    """Derive a clean subject/brand folder name from an opening prompt."""
    brand = extract_url_brand(text)
    if brand:
        return _truncate(brand, max_len)
    first_line = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    stripped = _URL_RE.sub(" ", first_line)
    stripped = _ZH_FILLER_RE.sub("", stripped)
    stripped = _EN_FILLER_RE.sub("", stripped)
    stripped = _LEADING_VERB_ZH_RE.sub("", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    stripped = _TRAILING_PUNCT_RE.sub("", stripped)
    if not stripped:
        return fallback
    return _truncate(stripped, max_len)


def derive_conversation_title(
    text: str,
    *,
    project_title: str | None = None,
    max_len: int = 24,
) -> str:
    """Derive a concise task-oriented conversation title without raw URLs or boilerplate."""
    first_line = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    if not first_line:
        return "Project chat"

    brand = extract_url_brand(first_line)
    cleaned = _URL_RE.sub(" ", first_line)
    cleaned = _ZH_FILLER_RE.sub("", cleaned)
    cleaned = _EN_FILLER_RE.sub("", cleaned)
    cleaned = _normalize_zh_task_phrase(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)

    proj_norm = (project_title or "").strip().lower()
    if brand and cleaned:
        # Only prepend brand when it is not already the parent project folder name
        if brand.lower() not in cleaned.lower() and brand.lower() != proj_norm:
            cleaned = f"{brand} {cleaned}"
    elif brand and not cleaned:
        cleaned = f"{brand} 宣传片" if any("\u4e00" <= ch <= "\u9fff" for ch in first_line) else f"{brand} promo"

    if proj_norm and cleaned.lower().startswith(proj_norm):
        remainder = cleaned[len(project_title or ""):].lstrip(" ·-:：—–")
        if len(remainder) >= 3:
            cleaned = remainder

    if not cleaned:
        return _truncate(first_line, max_len)
    return _truncate(cleaned, max_len)


def should_auto_upgrade_title(
    current_title: str | None,
    *,
    auto_title: str | None = None,
    user_edited: bool = False,
    is_project: bool = False,
) -> bool:
    """Return True only when the title is still system-derived and NOT manually edited."""
    if user_edited:
        return False
    cur = (current_title or "").strip()
    defaults = DEFAULT_PROJECT_TITLES if is_project else DEFAULT_CONVERSATION_TITLES
    if cur in defaults:
        return True
    if auto_title and cur == auto_title.strip():
        return True
    if _RAW_URL_HINT_RE.search(cur):
        return True
    return False


def clean_generated_title(
    raw: str | None,
    *,
    project_title: str | None = None,
    max_len: int = 24,
) -> str | None:
    """Sanitize a model- or composition-proposed title into a compact sidebar label."""
    if not raw:
        return None
    first_line = next((line.strip() for line in str(raw).splitlines() if line.strip()), "")
    if not first_line:
        return None
    cleaned = _URL_RE.sub(" ", first_line)
    cleaned = _WRAPPER_QUOTES_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)
    if not cleaned:
        return None
    proj = (project_title or "").strip()
    if proj and cleaned.lower().startswith(proj.lower()):
        remainder = cleaned[len(proj):].lstrip(" ·-:：—–")
        if len(remainder) >= 3:
            cleaned = remainder
    if len(cleaned) < 2:
        return None
    return _truncate(cleaned, max_len)


def refine_title_from_composition(
    composition_name: str | None,
    *,
    project_title: str | None = None,
    max_len: int = 24,
) -> str | None:
    """Turn a saved Composition name into a crisp conversation title (deduping project prefix)."""
    return clean_generated_title(composition_name, project_title=project_title, max_len=max_len)


def _prefers_zh_text(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def _collect_turn_evidence(
    messages: list[Any],
    *,
    page_readings: list[Any] | None = None,
) -> tuple[str, int]:
    """Build a compact evidence digest from user turns, executed tool steps, and assistant replies.

    Returns ``(digest_text, step_count)`` where ``step_count`` tracks conversational + tool progress
    so we know when meaningful new steps warrant one progressive title refinement.
    """
    lines: list[str] = []
    step_count = 0
    tool_steps: list[str] = []

    for msg in messages[-24:]:
        intent = msg.intent if isinstance(getattr(msg, "intent", None), dict) else {}
        if intent.get("type") == "activity":
            frame = intent.get("frame") if isinstance(intent.get("frame"), dict) else {}
            tool_name = str(frame.get("tool_name") or frame.get("key") or "").strip()
            detail = frame.get("detail")
            detail_str = ""
            if isinstance(detail, str):
                detail_str = detail.strip()[:120]
            elif isinstance(detail, dict):
                compact_parts = [
                    f"{k}={str(v)[:60]}"
                    for k, v in list(detail.items())[:3]
                    if v not in (None, "", [], {})
                ]
                detail_str = ", ".join(compact_parts)
            if tool_name:
                step_count += 1
                tool_steps.append(f"{tool_name}({detail_str})" if detail_str else tool_name)
            continue

        role = getattr(msg, "role", "")
        content = re.sub(r"\s+", " ", (getattr(msg, "content", None) or "").strip())
        if role == "user" and content:
            step_count += 1
            lines.append(f"User: {content[:320]}")
        elif role == "assistant" and content:
            lines.append(f"Assistant: {content[:260]}")

    if tool_steps:
        lines.append("Tools/Steps executed: " + "; ".join(tool_steps[-8:]))

    if page_readings:
        for reading in page_readings[:2]:
            url = str(getattr(reading, "url", "") or "").strip()
            snippet = re.sub(r"\s+", " ", str(getattr(reading, "text", "") or "").strip())[:220]
            if url or snippet:
                lines.append(f"Webpage ({url}): {snippet}")

    return "\n".join(lines)[:3200], step_count


async def summarize_titles_from_turn(
    evidence_text: str,
    *,
    ui_language: str | None = None,
    current_project_title: str | None = None,
    need_project_title: bool = False,
    llm_client: Any = None,
    timeout: float = 10.0,
) -> tuple[str | None, str | None]:
    """Generate concise ``(project_title, conversation_title)`` via the configured LLM."""
    if not evidence_text.strip():
        return None, None
    if llm_client is None:
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None, None
        try:
            from app.providers.llm import get_llm_client

            llm_client = get_llm_client()
        except Exception as exc:  # noqa: BLE001
            logger.warning("title_summary_client_unavailable", error=str(exc))
            return None, None

    is_zh = (ui_language or "").startswith("zh") or _prefers_zh_text(evidence_text)
    lang = "Chinese" if is_zh else "English"
    length_guide = "4-12 Chinese characters" if is_zh else "3-6 English words"
    proj_hint = (
        f'Existing project folder name: "{current_project_title}". '
        "Do NOT repeat the project name inside conversation_title when redundant. "
        if current_project_title and not need_project_title
        else ""
    )
    system_prompt = (
        f"You name video-creation projects and chat threads in a clean studio sidebar ({lang}). "
        f"{proj_hint}"
        "Based on the user's request, tool/step progress, webpage facts, and assistant direction, "
        "return strict JSON with keys project_title and conversation_title: "
        '{"project_title": "short brand or subject folder name (2-10 chars)", '
        f'"conversation_title": "natural action/task summary ({length_guide})"}}. '
        "Good Chinese conversation_title examples: 制作官网宣传片, 1126工作日报编写, 30秒科技感宣传片, 产品发布预告片剪辑. "
        "Avoid bare single nouns like 宣传片 or 视频; capture the action or creative angle concisely. "
        "Rules: NO raw URLs, NO filler words (like 帮我/给我/please), NO quotes, NO trailing punctuation."
    )
    try:
        parsed = await asyncio.wait_for(
            llm_client.generate(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": evidence_text},
                ],
                response_model=TitleSummaryPayload,
                temperature=0.2,
                thinking=False,
                timeout_s=timeout,
            ),
            timeout=timeout + 1.0,
        )
        proj_title = (
            clean_generated_title(parsed.project_title, max_len=24)
            if need_project_title
            else None
        )
        effective_proj = proj_title or current_project_title
        conv_title = clean_generated_title(
            parsed.conversation_title,
            project_title=effective_proj,
            max_len=24,
        )
        return proj_title, conv_title
    except Exception as exc:  # noqa: BLE001
        logger.warning("title_summary_llm_failed", error=str(exc))
        return None, None


async def maybe_refine_titles_after_turn(
    conversation_id: UUID,
    project_id: UUID | None = None,
    *,
    db: AsyncSession | None = None,
    llm_client: Any = None,
    timeout: float = 10.0,
) -> dict[str, str] | None:
    """Progressively refine conversation/project titles after a settled turn or tool steps.

    Runs even before any video output is rendered:
    - After turn 1 settles (``title_stage`` is None / ``"l0"``): upgrades to semantic ``"llm_initial"``
    - After meaningful tool/step progress (``step_count >= prev + 2``): refines once to ``"llm_refined"``
    - Never overwrites titles where ``title_user_edited`` is True or already named by a saved Composition.
    """
    from app.models.database import AsyncSessionLocal
    from app.models.tables import Conversation, Message, PageReading, Project

    async def _run(session: AsyncSession) -> dict[str, str] | None:
        conv = await session.get(Conversation, conversation_id)
        if conv is None or conv.project_id is None or conv.asset_id is not None:
            return None
        pid = project_id or conv.project_id
        proj = await session.get(Project, pid) if pid is not None else None

        ctx = dict(conv.context or {"schema_version": 1, "items": []})
        stage = ctx.get("title_stage")
        conv_user_edited = bool(conv.title_user_edited or ctx.get("title_user_edited"))
        proj_user_edited = bool(proj.title_user_edited) if proj is not None else True

        can_upgrade_conv = (
            not conv_user_edited
            and stage != "composition"
            and should_auto_upgrade_title(
                conv.title,
                auto_title=ctx.get("auto_title"),
                user_edited=conv_user_edited,
            )
        )
        can_upgrade_proj = (
            proj is not None
            and not proj_user_edited
            and (
                should_auto_upgrade_title(
                    proj.title,
                    auto_title=ctx.get("auto_project_title"),
                    user_edited=proj_user_edited,
                    is_project=True,
                )
                or stage in (None, "l0")
            )
        )
        if not can_upgrade_conv and not can_upgrade_proj:
            return None

        rows = list(
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.seq.asc().nullslast(), Message.created_at.asc())
            )
        )
        readings: list[Any] = []
        if pid is not None:
            readings = list(
                await session.scalars(
                    select(PageReading)
                    .where(PageReading.project_id == pid)
                    .order_by(PageReading.fetched_at.desc())
                    .limit(2)
                )
            )

        evidence, step_count = _collect_turn_evidence(rows, page_readings=readings)
        if not evidence:
            return None

        prev_steps = int(ctx.get("title_step_count") or 0)
        if stage == "llm_refined":
            return None
        if stage == "llm_initial" and step_count < prev_steps + 2:
            return None

        new_proj, new_conv = await summarize_titles_from_turn(
            evidence,
            ui_language=conv.ui_language,
            current_project_title=proj.title if proj is not None else None,
            need_project_title=can_upgrade_proj,
            llm_client=llm_client,
            timeout=timeout,
        )
        updated: dict[str, str] = {}
        if can_upgrade_proj and proj is not None and new_proj:
            proj.title = new_proj
            ctx["auto_project_title"] = new_proj
            updated["project_title"] = new_proj
        if can_upgrade_conv and new_conv:
            conv.title = new_conv
            ctx["auto_title"] = new_conv
            updated["conversation_title"] = new_conv

        if not updated:
            return None

        ctx["title_stage"] = "llm_refined" if stage == "llm_initial" else "llm_initial"
        ctx["title_step_count"] = step_count
        conv.context = ctx
        await session.commit()
        return updated

    try:
        if db is not None:
            return await _run(db)
        async with AsyncSessionLocal() as session:
            return await _run(session)
    except Exception as exc:  # noqa: BLE001 — progressive naming is strictly best-effort
        logger.debug(
            "progressive_title_refine_skipped",
            conversation_id=str(conversation_id),
            error=str(exc),
        )
        return None
