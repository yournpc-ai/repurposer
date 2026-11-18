"""Source-frozen, multimodal BrandProfile preparation."""

from __future__ import annotations

import base64
import io
import json
import re
from collections import Counter
from typing import Any
from uuid import UUID

from PIL import Image
from sqlalchemy import select

from app.chat.readiness import (
    WEBSITE_BRAND_EXTRACTOR_VERSION,
    canonical_url,
    current_web_snapshots,
    urls_from_text,
)
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    BrandColor,
    BrandProfile,
    BrandSourceRef,
    Brief,
    canonical_json_hash,
)
from app.models.tables import Asset, SourceSnapshot
from app.tools.video.preparation import frozen_source_lines

EXTRACTOR_VERSION = WEBSITE_BRAND_EXTRACTOR_VERSION


class BrandEvidenceError(ValueError):
    pass


def _readable_views(snapshot: SourceSnapshot) -> list[dict[str, Any]]:
    return [
        view
        for view in (snapshot.meta or {}).get("views") or []
        if view.get("view_id")
        and view.get("storage_key")
        and view.get("digest")
        and int(view.get("width") or 0) > 0
        and int(view.get("height") or 0) > 0
        and str(view.get("artifact_role") or "view") in {"view", "full", "hero"}
    ]


async def _matching_web_snapshots(
    *, owner_id: UUID, project_id: UUID, user_text: str
) -> list[SourceSnapshot]:
    url_keys = {canonical_url(url) for url in urls_from_text(user_text)}
    if not url_keys:
        raise BrandEvidenceError("website brand analysis needs the user's source URL")
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.scalars(
                    select(SourceSnapshot)
                    .outerjoin(Asset, SourceSnapshot.asset_id == Asset.id)
                    .where(
                        SourceSnapshot.owner_id == owner_id,
                        SourceSnapshot.kind == "web",
                        (SourceSnapshot.origin_project_id == project_id)
                        | (Asset.project_id == project_id),
                    )
                    .order_by(SourceSnapshot.captured_at)
                )
            ).all()
        )
    matched = [
        snapshot
        for snapshot in rows
        if canonical_url(str((snapshot.meta or {}).get("canonical_url") or "")) in url_keys
    ]
    if not matched:
        raise BrandEvidenceError("the requested website has no frozen SourceSnapshot")
    return current_web_snapshots(matched)


def _source_ref(snapshot: SourceSnapshot, views: list[dict[str, Any]]) -> BrandSourceRef:
    lines = frozen_source_lines(snapshot)
    return BrandSourceRef(
        snapshot_id=str(snapshot.id),
        digest=snapshot.digest,
        view_ids=[str(views[0]["view_id"])] if views else [],
        line_ids=[str(line["line_id"]) for line in lines],
    )


def _css_confirmed(snapshot: SourceSnapshot) -> bool:
    meta = snapshot.meta or {}
    return bool(meta.get("css_facts") or meta.get("computed_styles"))


def _css_typography_confirmed(snapshot: SourceSnapshot) -> bool:
    facts = (snapshot.meta or {}).get("css_facts") or (snapshot.meta or {}).get("computed_styles")

    def contains_font_family(value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).lower().replace("_", "-")
                if normalized in {"font", "font-family"} and item:
                    return True
                if (
                    normalized in {"name", "property"}
                    and str(item).lower().replace("_", "-") in {"font", "font-family"}
                    and value.get("value")
                ):
                    return True
                if contains_font_family(item):
                    return True
        elif isinstance(value, list):
            return any(contains_font_family(item) for item in value)
        return False

    return contains_font_family(facts)


def _dominant_color_evidence(images: list[Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for media_index, item in enumerate(images, start=1):
        try:
            encoded = item.data_url.split(",", 1)[1]
            with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as source:
                source = source.convert("RGB")
                source.thumbnail((640, 640))
                counts = Counter(source.getdata())
        except (ValueError, OSError, base64.binascii.Error):
            continue
        total = sum(counts.values())
        if not total:
            continue
        saturated = [
            (color, count)
            for color, count in counts.items()
            if max(color) - min(color) >= 64
        ]
        saturated.sort(key=lambda item: item[1], reverse=True)
        selected = dict.fromkeys(
            [*counts.most_common(12), *saturated[:12]]
        )
        for (red, green, blue), count in selected:
            evidence.append({
                "media_index": media_index,
                "value": f"#{red:02X}{green:02X}{blue:02X}",
                "pixel_share": round(count / total, 4),
            })
    return evidence


def _measured_color(value: str, palette: list[dict[str, Any]]) -> str | None:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return None
    rgb = tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))

    def distance(item: dict[str, Any]) -> int:
        other = item["value"]
        other_rgb = tuple(int(other[index:index + 2], 16) for index in (1, 3, 5))
        return sum(
            (left - right) ** 2
            for left, right in zip(rgb, other_rgb, strict=True)
        )

    candidates = [item for item in palette if distance(item) <= 72**2]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["pixel_share"])["value"]


def _add_missing_accents(
    extraction: Any, palette: list[dict[str, Any]]
) -> None:
    for item in palette:
        value = item["value"]
        rgb = tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
        if max(rgb) - min(rgb) < 64:
            continue
        if any(
            _measured_color(color.value, [item]) == value
            for color in extraction.colors
        ):
            continue
        extraction.colors.append(BrandColor(
            value=value,
            role="accent",
            source="visual",
            confidence="inferred",
        ))


def build_brand_profile(
    extraction: Any,
    *,
    snapshots: list[SourceSnapshot],
    source_refs: list[BrandSourceRef],
    color_evidence: list[dict[str, Any]] | None = None,
) -> BrandProfile:
    """Server-owned identity and evidence checks around the model's extraction."""
    extraction = extraction.model_copy(deep=True)
    lines_by_id = {
        str(line["line_id"]): str(line["text"])
        for snapshot in snapshots
        for line in frozen_source_lines(snapshot)
    }
    for tagline in extraction.taglines:
        cited = [line_id for line_id in tagline.line_ids if line_id in lines_by_id]
        tagline.line_ids = cited
        if len(cited) == 1:
            tagline.text = lines_by_id[cited[0]]
    for claim in extraction.claims:
        claim.line_ids = [line_id for line_id in claim.line_ids if line_id in lines_by_id]
        if claim.kind == "fact" and not claim.line_ids:
            claim.kind = "inferred"
    for snapshot in snapshots:
        if _css_confirmed(snapshot):
            continue
        for color in extraction.colors:
            if color.source in {"css", "dom"}:
                color.source = "visual"
                color.confidence = "inferred"
    if not any(_css_typography_confirmed(snapshot) for snapshot in snapshots):
        for typography in extraction.typography:
            typography.source = "visual"
            typography.confidence = "inferred"
    for typography in extraction.typography:
        if typography.source == "visual" and typography.confidence == "inferred":
            candidate = typography.candidate.strip()
            if candidate and not candidate.lower().startswith(
                ("接近", "similar to", "approximately")
            ):
                typography.candidate = f"接近 {candidate}"
    if color_evidence:
        for color in extraction.colors:
            if color.source == "visual":
                measured = _measured_color(color.value, color_evidence)
                if measured is not None:
                    color.value = measured
        _add_missing_accents(extraction, color_evidence)
    payload = {
        "schema_version": 1,
        "source_refs": [ref.model_dump(mode="json") for ref in source_refs],
        "extractor_version": EXTRACTOR_VERSION,
        **extraction.model_dump(mode="json"),
    }
    return BrandProfile(
        **payload,
        content_digest=canonical_json_hash(payload),
    )


async def analyze_brand(
    *, owner_id: UUID, project_id: UUID, user_text: str, brief: Brief
) -> tuple[BrandProfile, dict[str, Any]]:
    """Read real text and PNG bytes; never persist or mutate the raw snapshots."""
    snapshots = await _matching_web_snapshots(
        owner_id=owner_id, project_id=project_id, user_text=user_text
    )
    for snapshot in snapshots:
        if not frozen_source_lines(snapshot):
            raise BrandEvidenceError("the website snapshot has no citable body lines")
        if not _readable_views(snapshot):
            raise BrandEvidenceError("the website snapshot has no readable required PNG view")
    from app.tools.video.design import _view_facts, _view_media_inputs

    omitted: list[dict[str, str]] = []
    images = await _view_media_inputs(snapshots, _view_facts(snapshots), omitted=omitted)
    if not images:
        raise BrandEvidenceError(
            "the required PNG bytes could not be read; no BrandProfile was formed"
        )
    source_refs = [_source_ref(snapshot, _readable_views(snapshot)) for snapshot in snapshots]
    color_evidence = _dominant_color_evidence(images)
    evidence = {
        "source_refs": [ref.model_dump(mode="json") for ref in source_refs],
        "pages": [
            {
                "snapshot_id": str(snapshot.id),
                "canonical_url": (snapshot.meta or {}).get("canonical_url"),
                "citable_lines": frozen_source_lines(snapshot),
                "views": [
                    {
                        key: view.get(key)
                        for key in (
                            "view_id",
                            "heading",
                            "width",
                            "height",
                            "artifact_role",
                            "elements",
                        )
                        if view.get(key) is not None
                    }
                    for view in _readable_views(snapshot)
                ],
                **(
                    {
                        "css_facts": (snapshot.meta or {}).get("css_facts")
                        or (snapshot.meta or {}).get("computed_styles")
                    }
                    if _css_confirmed(snapshot)
                    else {}
                ),
            }
            for snapshot in snapshots
        ],
        "dominant_color_evidence": color_evidence,
    }
    from app.tools.video.brand_agent import brand_profile_agent

    extraction = await brand_profile_agent.call(
        brief_json=json.dumps(brief.model_dump(mode="json"), ensure_ascii=False),
        evidence_json=json.dumps(evidence, ensure_ascii=False),
        images=images,
    )
    profile = build_brand_profile(
        extraction,
        snapshots=snapshots,
        source_refs=source_refs,
        color_evidence=color_evidence,
    )
    return profile, {
        "brand_profile": profile.model_dump(mode="json"),
        "media_files": len(images),
        "citable_line_count": sum(len(frozen_source_lines(snapshot)) for snapshot in snapshots),
        "source_snapshots_unchanged": True,
    }
