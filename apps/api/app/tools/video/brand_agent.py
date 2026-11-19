"""Bounded multimodal brand extraction on the shared Agent harness."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.base import Agent, AssembleResult
from app.models.schemas import (
    BrandAsset,
    BrandClaim,
    BrandColor,
    BrandCreativeDirection,
    BrandTagline,
    BrandTypography,
)


def _raw(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value if isinstance(value, dict) else {}


def _refs(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    refs: list[str] = []
    for item in items:
        if isinstance(item, str):
            refs.append(item)
        elif isinstance(item, dict):
            for key in ("line_ids", "view_ids"):
                refs.extend(_refs(item.get(key)))
    return list(dict.fromkeys(ref for ref in refs if ref))


def _kind(value: Any) -> str:
    normalized = str(value or "").lower()
    if normalized in {"fact", "source", "source_fact", "confirmed"}:
        return "fact"
    return "inferred"


def _claim(item: Any) -> dict[str, Any]:
    raw = _raw(item)
    basis = raw.get("basis") if isinstance(raw.get("basis"), dict) else {}
    return {
        "text": (
            raw.get("claim") or raw.get("text") or raw.get("positioning")
            or raw.get("summary") or basis.get("text") or ""
        ),
        "line_ids": _refs(
            raw.get("line_ids") or raw.get("citations") or basis.get("line_ids")
        ),
        "kind": _kind(raw.get("kind") or raw.get("source_type")),
    }


def _tagline(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"text": item, "line_ids": []}
    raw = _raw(item)
    return {
        "text": raw.get("text") or raw.get("tagline") or raw.get("value") or "",
        "line_ids": _refs(raw.get("line_ids") or raw.get("citations")),
    }


def _color(item: Any) -> dict[str, Any]:
    raw = _raw(item)
    source = (
        raw.get("source")
        if raw.get("source") in {"css", "dom", "visual", "user"}
        else "visual"
    )
    confidence = "confirmed" if raw.get("confidence") == "confirmed" else "inferred"
    return {
        "value": raw.get("value") or raw.get("hex") or "",
        "role": raw.get("role") or raw.get("name") or raw.get("usage") or "",
        "source": source,
        "confidence": confidence,
        "source_refs": _refs(
            raw.get("source_refs") or raw.get("line_ids") or raw.get("view_ids")
            or raw.get("citations")
        ),
    }


def _typography(item: Any) -> dict[str, Any]:
    raw = _raw(item)
    source = (
        raw.get("source")
        if raw.get("source") in {"css", "dom", "visual", "user"}
        else "visual"
    )
    confidence = "confirmed" if raw.get("confidence") == "confirmed" else "inferred"
    return {
        "candidate": raw.get("candidate") or raw.get("font") or raw.get("name") or "",
        "weight": str(raw.get("weight") or ""),
        "source": source,
        "confidence": confidence,
        "source_refs": _refs(
            raw.get("source_refs") or raw.get("line_ids") or raw.get("view_ids")
            or raw.get("citations")
        ),
    }


def _asset(item: Any) -> dict[str, Any]:
    raw = _raw(item)
    ref = raw.get("ref") or raw.get("asset") or raw.get("name") or raw.get("id") or ""
    descriptor = f"{raw.get('kind') or raw.get('type') or ''} {ref}".lower()
    if "wordmark" in descriptor:
        kind = "wordmark"
        ref = ref or "wordmark"
    elif "logo" in descriptor:
        kind = "logo"
        ref = ref or "logo"
    elif "icon" in descriptor:
        kind = "icon"
        ref = ref or "icon"
    else:
        kind = "other"
    return {
        "kind": kind,
        "ref": ref,
        "source_refs": _refs(
            raw.get("source_refs") or raw.get("line_ids") or raw.get("view_ids")
            or raw.get("citations")
        ),
    }


def _direction(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"summary": value, "provenance": "inferred"}
    raw = _raw(value)
    return {
        "summary": raw.get("summary") or raw.get("interpretation") or raw.get("direction") or "",
        "media_preferences": raw.get("media_preferences") or [],
        "avoid": raw.get("avoid") or [],
        "provenance": "inferred",
    }


def _strings(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            text = item.get("item") or item.get("issue") or item.get("text") or item.get("claim")
            if text:
                result.append(str(text))
    return result


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [] if value is None else [value]


class BrandProfileExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_provider_dialects(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {}
        raw_positioning = value.get("positioning")
        raw_claims = value.get("positioning_and_claims")
        if raw_claims is None and isinstance(raw_positioning, list):
            raw_claims = raw_positioning
        if raw_claims is None:
            raw_claims = value.get("claims")
        claims = [_claim(item) for item in _list(raw_claims)]
        positioning = raw_positioning if isinstance(raw_positioning, str) else ""
        if not positioning and claims:
            positioning = claims[0]["text"]
        return {
            "positioning": positioning,
            "claims": claims,
            "taglines": [_tagline(item) for item in _list(value.get("taglines"))],
            "colors": [_color(item) for item in _list(value.get("colors"))],
            "typography": [
                _typography(item)
                for item in _list(value.get("typography") or value.get("typography_candidates"))
            ],
            "brand_assets": [
                _asset(item)
                for item in _list(
                    value.get("brand_assets")
                    or value.get("logo_wordmark_icon_assets")
                    or value.get("assets")
                )
            ],
            "creative_direction": _direction(value.get("creative_direction")),
            "unknowns": _strings(value.get("unknowns") or []),
            "conflicts": _strings(value.get("conflicts") or []),
        }

    positioning: str = ""
    claims: list[BrandClaim] = Field(default_factory=list)
    taglines: list[BrandTagline] = Field(default_factory=list)
    colors: list[BrandColor] = Field(default_factory=list)
    typography: list[BrandTypography] = Field(default_factory=list)
    brand_assets: list[BrandAsset] = Field(default_factory=list)
    creative_direction: BrandCreativeDirection = Field(default_factory=BrandCreativeDirection)
    unknowns: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


def _assemble_brand_profile(
    *, brief_json: str, evidence_json: str, images: list | None = None
) -> AssembleResult:
    return {"brief_json": brief_json, "evidence_json": evidence_json}, list(images or [])


brand_profile_agent: Agent[BrandProfileExtraction] = Agent(
    name="website_brand_profile",
    prompt="video/brand_profile.j2",
    schema=BrandProfileExtraction,
    system=(
        "你负责分析品牌证据。每个事实陈述都要有可引用的原文行和实际附上的页面图片作依据。区分来源事实、视觉推断及未知信息。"
        "逐字保留引用的品牌宣言，不得只凭像素认定 CSS 字体。只输出有效 JSON。"
    ),
    temperature=0.2,
    assemble=_assemble_brand_profile,
    media_text_fallback=False,
    stream=False,
    timeout_s=180,
)


__all__ = ["BrandProfileExtraction", "brand_profile_agent"]
