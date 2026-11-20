"""Pure website-promo evidence and Brief readiness projection."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.models.schemas import (
    Brief,
    BriefQuestionItem,
    BriefSlot,
    BriefSlotSource,
    CreativeState,
    seal_creative_state,
)

WEBSITE_PROMO_REQUIRED_SLOTS = (
    "production_direction",
    "target_seconds",
    "narration_language",
    "subtitle_languages",
    "aspect",
)

_URL_RE = re.compile(r"https?://[^\s<>\"'）】]+", re.IGNORECASE)
_PROMO_RE = re.compile(
    r"宣传片|宣传视频|品牌片|官网片|brand\s+(?:video|film)|promo(?:tional)?(?:\s+video|\s+film)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceReadiness:
    task_kind: str
    has_url: bool
    capture_pending: bool
    capture_failed: bool
    capture_ready: bool
    text_ready: bool
    required_views_ready: bool
    brief_missing_slots: list[str]
    brand_profile_ready: bool
    draft_present: bool
    required_next_action: str | None
    urls: list[str]
    brief: Brief

    @property
    def brief_ready(self) -> bool:
        return not self.brief_missing_slots

    def model_dump(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("brief")
        payload["brief_ready"] = self.brief_ready
        return payload


def urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:!?，。；！？")
        if url not in urls:
            urls.append(url)
    return urls


def canonical_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().rstrip("/").lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def infer_task_kind(user_text: str) -> str:
    return (
        "website_promo" if urls_from_text(user_text) and _PROMO_RE.search(user_text) else "generic"
    )


def settled_website_question(messages, turn_id) -> bool:
    """Both submitting and skipping settle the questionnaire for this turn."""
    return turn_id is not None and any(
        message.turn_id == turn_id and (message.question or {}).get("group_digest")
        and (message.answer or {}).get("kind") in {"group", "bail"}
        and any(item.get("slot") in WEBSITE_PROMO_REQUIRED_SLOTS
                for item in message.question.get("items") or [])
        for message in messages or ()
    )


def _put(brief: Brief, slot: str, value: Any) -> None:
    setattr(brief, slot, BriefSlot(value=value, source=BriefSlotSource.USER_STATED))


def resolve_legacy_direction(brief: Brief) -> None:
    """Promote a complete legacy choice only on an active authoring Brief."""
    if brief.production_direction.value or not (brief.purpose.value and brief.narrative_mode.value):
        return
    sources = {brief.purpose.source, brief.narrative_mode.source}
    source = BriefSlotSource.USER_STATED
    if BriefSlotSource.DEFAULT in sources:
        source = BriefSlotSource.DEFAULT
    elif BriefSlotSource.INFERRED in sources:
        source = BriefSlotSource.INFERRED
    brief.production_direction = BriefSlot(
        value=" · ".join(dict.fromkeys((brief.purpose.value, brief.narrative_mode.value))),
        source=source,
    )


def direction_with_known_details(brief: Brief, direction: str) -> str:
    """Preserve the known half when a custom answer completes a partial legacy Brief."""
    details = stated_direction_inputs(brief)
    if brief.production_direction.value or len(details) != 1:
        return direction
    known = next(iter(details.values()))
    return direction if known.casefold() in direction.casefold() else f"{known} · {direction}"


def stated_direction_inputs(brief: Brief) -> dict[str, str]:
    return {
        name: slot.value for name in ("purpose", "narrative_mode")
        if (slot := getattr(brief, name)).value and slot.source == BriefSlotSource.USER_STATED
    }


def brief_with_user_constraints(user_text: str, stored: Brief | None = None) -> Brief:
    """Merge literal website-promo constraints into the existing Brief slots."""
    brief = (stored or Brief()).model_copy(deep=True)
    text = _URL_RE.sub(" ", user_text or "").strip()
    if not _PROMO_RE.search(text):
        resolve_legacy_direction(brief)
        return brief
    if re.search(
        r"官网(?:首页|首屏|宣传片|片)|(?:发布在|放在|用在|用于|投放在)\s*(?:品牌)?官网"
        r"|\b(?:on (?:our |the |this )?(?:website|homepage)|homepage (?:hero|film|promo|video))\b",
        text, re.IGNORECASE,
    ):
        _put(brief, "purpose", "website")
    seconds = re.search(r"(?<!\d)(\d{1,3})\s*(?:秒|seconds?|secs?)(?![\dA-Za-z])", text, re.IGNORECASE)
    if seconds:
        _put(brief, "target_seconds", int(seconds.group(1)))
    aspect = re.search(r"(?<!\d)(16:9|9:16|1:1)(?!\d)", text)
    if aspect:
        _put(brief, "aspect", aspect.group(1))
    has_mission = bool(re.search(r"使命|mission", text, re.IGNORECASE))
    has_tech = bool(re.search(r"科技|tech(?:nology)?", text, re.IGNORECASE))
    if has_mission and has_tech:
        _put(brief, "narrative_mode", "mission_tech")
        _put(brief, "tone", "international_tech_mission")
    elif has_mission:
        _put(brief, "narrative_mode", "mission")
    elif re.search(r"产品证据|product\s+evidence", text, re.IGNORECASE):
        _put(brief, "narrative_mode", "product_evidence")
    elif re.search(r"知识讲解|explainer", text, re.IGNORECASE):
        _put(brief, "narrative_mode", "knowledge_explainer")
    if re.search(
        r"英文(?:配音|旁白)|英语(?:配音|旁白)|english\s+(?:narration|voice(?:over)?)",
        text,
        re.IGNORECASE,
    ):
        _put(brief, "narration_language", "en")
    elif re.search(
        r"中文(?:配音|旁白)|chinese\s+(?:narration|voice(?:over)?)", text, re.IGNORECASE
    ):
        _put(brief, "narration_language", "zh")
    subtitle_languages: list[str] = []
    if re.search(r"英文字幕|english\s+subtitles?", text, re.IGNORECASE):
        subtitle_languages.append("en")
    if re.search(r"中文字幕|chinese\s+subtitles?", text, re.IGNORECASE):
        subtitle_languages.append("zh")
    if re.search(r"帧|fps|配乐|bgm|music|电子|electronic|[一二两三四五六七八九十\d]\s*幕|\bscenes?\b", text, re.I):
        if not any(item.value == user_text for item in brief.constraints):
            brief.constraints.append(BriefSlot(value=user_text, source=BriefSlotSource.USER_STATED))
    if subtitle_languages:
        _put(brief, "subtitle_languages", subtitle_languages)
    resolve_legacy_direction(brief)
    return brief


def _value(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def _meta(item: Any) -> dict[str, Any]:
    return _value(item, "meta", {}) or {}


def _status(item: Any) -> str:
    status = _value(item, "status", _value(item, "processing_status", ""))
    return str(getattr(status, "value", status)).lower()


def _line_facts(snapshot: Any) -> list[dict[str, Any]]:
    lines = _value(snapshot, "citable_lines") or _meta(snapshot).get("lines") or []
    return [
        line for line in lines if isinstance(line, dict) and str(line.get("text") or "").strip()
    ]


def _readable_views(snapshot: Any) -> list[dict[str, Any]]:
    views = _value(snapshot, "views") or _meta(snapshot).get("views") or []
    return [
        view
        for view in views
        if isinstance(view, dict)
        and view.get("view_id")
        and view.get("storage_key")
        and view.get("digest")
        and int(view.get("width") or 0) > 0
        and int(view.get("height") or 0) > 0
        and str(view.get("artifact_role") or "view") in {"view", "full", "hero"}
    ]


WEBSITE_BRAND_EXTRACTOR_VERSION = "website-brand-v1"


def _snapshot_identity(snapshot: Any) -> tuple[str, str]:
    return (
        str(_value(snapshot, "snapshot_id", _value(snapshot, "id", ""))),
        str(_value(snapshot, "digest") or ""),
    )


def current_web_snapshots(snapshots: list[Any] | tuple[Any, ...]) -> list[Any]:
    """Select one immutable snapshot per page, never mixing capture versions."""
    latest: dict[str, tuple[int, Any]] = {}
    for index, snapshot in enumerate(snapshots):
        if _value(snapshot, "kind") != "web":
            continue
        raw_url = _value(snapshot, "canonical_url") or _meta(snapshot).get("canonical_url")
        identity = (
            canonical_url(str(raw_url)) if raw_url else f"id:{_snapshot_identity(snapshot)[0]}"
        )
        captured_at = str(_value(snapshot, "captured_at", "") or "")
        previous = latest.get(identity)
        if previous is None or captured_at >= str(_value(previous[1], "captured_at", "") or ""):
            latest[identity] = (index, snapshot)
    return [item[1] for item in sorted(latest.values(), key=lambda item: item[0])]


def website_promo_evidence_language(
    snapshots: list[Any] | tuple[Any, ...], *, fallback: str = "en"
) -> str:
    text = " ".join(
        str(line.get("text") or "")
        for snapshot in snapshots
        for line in _line_facts(snapshot)
    )
    latin = len(re.findall(r"[A-Za-z]", text))
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    if latin >= cjk and latin:
        return "en"
    if cjk:
        return "zh"
    return fallback


def website_promo_default_brief(
    stored: Brief,
    snapshots: list[Any] | tuple[Any, ...] = (),
    *,
    fallback_language: str = "en",
) -> Brief:
    """Fill only missing fields after a group skip; user answers keep precedence."""
    brief = stored.model_copy(deep=True)
    language = website_promo_evidence_language(snapshots, fallback=fallback_language)
    values = {
        "target_seconds": 30,
        "narration_language": language,
        "subtitle_languages": [language],
        "aspect": "16:9",
    }
    for slot, value in values.items():
        if not getattr(brief, slot).value:
            setattr(brief, slot, BriefSlot(value=value, source=BriefSlotSource.DEFAULT))
    resolve_legacy_direction(brief)
    if not brief.production_direction.value:
        brief.production_direction = BriefSlot(
            value=f"{brief.purpose.value or 'website'} · {brief.narrative_mode.value or 'product_evidence'}",
            source=BriefSlotSource.DEFAULT,
        )
    if not brief.tone.value:
        brief.tone = BriefSlot(value="minimal_tech", source=BriefSlotSource.DEFAULT)
    return brief


def compute_source_readiness(
    *,
    user_text: str,
    source_text: str | None = None,
    assets: list[Any] | tuple[Any, ...] = (),
    snapshots: list[Any] | tuple[Any, ...] = (),
    creative_state: CreativeState | None = None,
    draft_present: bool = False,
    question_settled: bool = False,
    task_kind: str | None = None,
) -> SourceReadiness:
    """Read current facts only; no status is persisted and no IO is performed."""
    origin_text = source_text if source_text is not None else user_text
    kind = task_kind or infer_task_kind(origin_text)
    urls = urls_from_text(origin_text)
    url_keys = {canonical_url(url) for url in urls}
    stored_brief = creative_state.brief if creative_state is not None else Brief()
    brief = (
        brief_with_user_constraints(user_text, stored_brief)
        if kind == "website_promo"
        else stored_brief
    )

    matched_assets = []
    for asset in assets:
        asset_type = str(
            getattr(
                _value(asset, "type", _value(asset, "kind", "")),
                "value",
                _value(asset, "type", _value(asset, "kind", "")),
            )
        ).lower()
        if asset_type not in {"web_page", "website", "web"} and _value(asset, "kind") != "asset":
            continue
        url = _value(asset, "url") or _meta(asset).get("capture_url")
        if url and canonical_url(str(url)) in url_keys:
            matched_assets.append(asset)

    matched_snapshot_ids = {
        str(_value(asset, "text_snapshot_id"))
        for asset in matched_assets
        if _value(asset, "text_snapshot_id")
    }
    candidates = []
    for snapshot in snapshots:
        if _value(snapshot, "kind") != "web":
            continue
        url = _value(snapshot, "canonical_url") or _meta(snapshot).get("canonical_url")
        snapshot_id = _snapshot_identity(snapshot)[0]
        if (
            (url and canonical_url(str(url)) in url_keys)
            or snapshot_id in matched_snapshot_ids
        ):
            candidates.append(snapshot)
    matched_snapshots = current_web_snapshots(candidates)

    text_ready = bool(matched_snapshots) and all(
        _line_facts(snapshot) for snapshot in matched_snapshots
    )
    required_views_ready = bool(matched_snapshots) and all(
        _readable_views(snapshot) for snapshot in matched_snapshots
    )
    evidence_ready = text_ready and required_views_ready
    capture_ready = evidence_ready or any(
        _status(asset) == "completed"
        and bool(_meta(asset).get("research"))
        and bool(_meta(asset).get("shots") or _value(asset, "captured_view_count"))
        for asset in matched_assets
    )
    capture_failed = not capture_ready and any(
        _status(asset) == "failed" for asset in matched_assets
    )
    capture_pending = not capture_ready and not capture_failed

    missing = [slot for slot in WEBSITE_PROMO_REQUIRED_SLOTS if not getattr(brief, slot).value]
    source_identities = {_snapshot_identity(snapshot) for snapshot in matched_snapshots}
    profile = creative_state.brand_profile if creative_state is not None else None
    profile_identities = (
        {(str(ref.snapshot_id), str(ref.digest)) for ref in profile.source_refs}
        if profile is not None
        else set()
    )
    brand_profile_ready = bool(
        evidence_ready
        and profile is not None
        and profile.content_digest
        and profile.extractor_version == WEBSITE_BRAND_EXTRACTOR_VERSION
        and source_identities
        and source_identities <= profile_identities
    )
    if kind != "website_promo":
        required_next = None
    elif capture_failed:
        required_next = "answer"
    elif not evidence_ready:
        required_next = "prepare_video_materials"
    elif not brand_profile_ready:
        required_next = "analyze_brand"
    elif missing and not question_settled and (
        not draft_present or infer_task_kind(user_text) == "website_promo"
    ):
        required_next = "ask_user"
    else:
        required_next = "design_video"
    return SourceReadiness(
        task_kind=kind,
        has_url=bool(urls),
        capture_pending=capture_pending,
        capture_failed=capture_failed,
        capture_ready=capture_ready,
        text_ready=text_ready,
        required_views_ready=required_views_ready,
        brief_missing_slots=missing,
        brand_profile_ready=brand_profile_ready,
        draft_present=draft_present,
        required_next_action=required_next,
        urls=urls,
        brief=brief,
    )


def render_readiness_context(readiness: SourceReadiness) -> str:
    lines = [
        f"当前路径：{readiness.task_kind}",
        "当前准备状态：",
        f"- 含 URL：{str(readiness.has_url).lower()}",
        *(f"- URL: {url}" for url in readiness.urls),
        f"- 等待采集：{str(readiness.capture_pending).lower()}",
        f"- 采集失败：{str(readiness.capture_failed).lower()}",
        f"- 采集已就绪：{str(readiness.capture_ready).lower()}",
        f"- 正文已就绪：{str(readiness.text_ready).lower()}",
        f"- 所需视图已就绪：{str(readiness.required_views_ready).lower()}",
        f"- 品牌档案已就绪：{str(readiness.brand_profile_ready).lower()}",
        f"- Brief 已就绪：{str(readiness.brief_ready).lower()}",
        "- Brief 缺失字段：[" + ", ".join(readiness.brief_missing_slots) + "]",
        f"- 已有草稿：{str(readiness.draft_present).lower()}",
    ]
    return "\n".join(lines)


def _valid_option_value(slot: str, value: Any) -> bool:
    language = r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*"
    if slot == "target_seconds":
        return value > 0
    if slot == "aspect":
        return value in ("16:9", "9:16", "1:1")
    if slot == "narration_language":
        return isinstance(value, str) and bool(re.fullmatch(language, value))
    if slot == "subtitle_languages":
        return isinstance(value, list) and bool(value) and all(
            isinstance(code, str) and re.fullmatch(language, code) for code in value
        )
    return isinstance(value, str) and bool(value.strip())


def website_promo_question_items(items: list[BriefQuestionItem], brief: Brief) -> list[BriefQuestionItem]:
    """Validate the selected clarification fields against the current Brief."""
    from app.models.schemas import missing_brief_question_items

    brief = brief.model_copy(deep=True)
    resolve_legacy_direction(brief)
    expected = [
        slot for slot in WEBSITE_PROMO_REQUIRED_SLOTS if not getattr(brief, slot).value
    ]
    if not expected:
        raise ValueError("every required Brief field is already present; continue without a clarification")
    if not items:
        raise ValueError(
            "website promo clarification needs one items group covering the current missing fields: "
            + ", ".join(expected)
        )
    group = missing_brief_question_items(items, brief)
    actual = [item.slot for item in group]
    if set(actual) != set(expected):
        raise ValueError(
            "include every missing field once in the same questionnaire: "
            + ", ".join(expected)
        )
    for item in group:
        if not 1 <= len(item.options) <= 3:
            raise ValueError(f"{item.slot} needs 1-3 options")
        for option in item.options:
            if not _valid_option_value(item.slot, option.value):
                raise ValueError(f"{item.slot} needs a valid value for each option")
    return group


def creative_state_for_pending(pending: Any) -> CreativeState | None:
    if pending is None:
        return None
    return pending.creative_state or CreativeState(brief=pending.brief.model_copy(deep=True))


def creative_state_with_brief(state: CreativeState, brief: Brief) -> CreativeState:
    return seal_creative_state(state.model_copy(update={"brief": brief.model_copy(deep=True)}))
