"""Pure website-promo evidence and Brief readiness projection."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.models.schemas import (
    Brief,
    BriefSlot,
    BriefSlotSource,
    CreativeState,
    seal_creative_state,
)

WEBSITE_PROMO_REQUIRED_SLOTS = (
    "purpose",
    "target_seconds",
    "narrative_mode",
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


def _put(brief: Brief, slot: str, value: Any) -> None:
    setattr(brief, slot, BriefSlot(value=value, source=BriefSlotSource.USER_STATED))


def brief_with_user_constraints(user_text: str, stored: Brief | None = None) -> Brief:
    """Merge literal website-promo constraints into the existing Brief slots."""
    brief = (stored or Brief()).model_copy(deep=True)
    text = user_text or ""
    if not _PROMO_RE.search(text):
        return brief
    if re.search(r"官网|website", text, re.IGNORECASE):
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
    if subtitle_languages:
        _put(brief, "subtitle_languages", subtitle_languages)
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
        "purpose": "website",
        "target_seconds": 30,
        "narrative_mode": "product_evidence",
        "narration_language": language,
        "subtitle_languages": [language],
        "aspect": "16:9",
    }
    for slot, value in values.items():
        if not getattr(brief, slot).value:
            setattr(brief, slot, BriefSlot(value=value, source=BriefSlotSource.DEFAULT))
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
    elif missing:
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
        f"CURRENT ROUTE: {readiness.task_kind}",
        "CURRENT READINESS:",
        f"- Has URL: {str(readiness.has_url).lower()}",
        *(f"- URL: {url}" for url in readiness.urls),
        f"- Capture pending: {str(readiness.capture_pending).lower()}",
        f"- Capture failed: {str(readiness.capture_failed).lower()}",
        f"- Capture ready: {str(readiness.capture_ready).lower()}",
        f"- Text ready: {str(readiness.text_ready).lower()}",
        f"- Required views ready: {str(readiness.required_views_ready).lower()}",
        f"- Brand profile ready: {str(readiness.brand_profile_ready).lower()}",
        f"- Brief ready: {str(readiness.brief_ready).lower()}",
        "- Brief missing slots: [" + ", ".join(readiness.brief_missing_slots) + "]",
        f"- Draft present: {str(readiness.draft_present).lower()}",
    ]
    return "\n".join(lines)


def _narration_option_is_packaged(label: str) -> bool:
    normalized = label.casefold()
    return any(marker in normalized for marker in (
        "+", "双语", "bilingual", "字幕", "subtitle", "/", "、", "&", " and ",
    ))


def website_promo_question_items(items: list[Any], brief: Brief) -> list[Any]:
    """Validate one complete clarification group against the current Brief."""
    from app.models.schemas import missing_brief_question_items

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
    if len(actual) != len(expected) or set(actual) != set(expected):
        raise ValueError(
            "the clarification group must cover exactly the current missing fields: "
            + ", ".join(expected)
        )
    for item in group:
        option_ids = [option.id for option in item.options]
        if len(option_ids) > 3 or len(option_ids) != len(set(option_ids)):
            raise ValueError(f"{item.slot} needs unique options within the 1-3 bound")
        if any(option_id not in {"1", "2", "3"} for option_id in option_ids):
            raise ValueError(f"{item.slot} options use numeric ids 1-3")
        if item.slot == "narration_language" and any(
            _narration_option_is_packaged(option.label) for option in item.options
        ):
            raise ValueError(
                "narration_language accepts exactly one spoken language per Scene; "
                "do not offer bilingual or subtitle-packaged options"
            )
    return group


def creative_state_for_pending(pending: Any) -> CreativeState | None:
    if pending is None:
        return None
    return pending.creative_state or CreativeState(brief=pending.brief.model_copy(deep=True))


def creative_state_with_brief(state: CreativeState, brief: Brief) -> CreativeState:
    return seal_creative_state(state.model_copy(update={"brief": brief.model_copy(deep=True)}))
