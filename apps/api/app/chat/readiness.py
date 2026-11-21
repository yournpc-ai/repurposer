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
    brand_profile_ready: bool
    urls: list[str]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


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


def compute_source_readiness(
    *,
    user_text: str,
    source_text: str | None = None,
    assets: list[Any] | tuple[Any, ...] = (),
    snapshots: list[Any] | tuple[Any, ...] = (),
    creative_state: CreativeState | None = None,
    task_kind: str | None = None,
) -> SourceReadiness:
    """Read current facts only; no status is persisted and no IO is performed."""
    origin_text = source_text if source_text is not None else user_text
    kind = task_kind or infer_task_kind(origin_text)
    urls = urls_from_text(origin_text)
    url_keys = {canonical_url(url) for url in urls}
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
    return SourceReadiness(
        task_kind=kind,
        has_url=bool(urls),
        capture_pending=capture_pending,
        capture_failed=capture_failed,
        capture_ready=capture_ready,
        text_ready=text_ready,
        required_views_ready=required_views_ready,
        brand_profile_ready=brand_profile_ready,
        urls=urls,
    )


def creative_state_for_pending(pending: Any) -> CreativeState | None:
    if pending is None:
        return None
    return pending.creative_state or CreativeState(brief=pending.brief.model_copy(deep=True))


def creative_state_with_brief(state: CreativeState, brief: Brief) -> CreativeState:
    return seal_creative_state(state.model_copy(update={"brief": brief.model_copy(deep=True)}))
