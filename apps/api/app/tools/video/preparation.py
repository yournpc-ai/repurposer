"""Application IO for pinned media and fonts; no Composition content writes.

Existing capture/storage owns bytes. Editing owns snapshot registration,
version bindings, validation and pure font descriptors.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from uuid import UUID, uuid5
from typing import Any

import av
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.fonts import FONT_FILES, font_storage_key
from app.editing.sources import register_snapshot
from app.editing.timing import SOURCE_TIMEBASE
from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset, Output, Project, SourceSnapshot, now_utc
from app.pipeline.music import AUDIO_EXT, music_file_path
from app.providers import storage

_FONT_ROOT = Path(__file__).resolve().parents[3] / "assets" / "fonts"

_SUFFIX = re.compile(r"^\.[a-z0-9]{1,8}$", re.IGNORECASE)

# The citation manifest's field order (title first — the page's own lead;
# links last — navigation chrome is the weakest citation).
_RESEARCH_FIELDS = ("title", "description", "h1", "h2", "h3", "paragraphs", "body", "buttons", "links")


def _research_lines(research: Any) -> list[dict[str, Any]]:
    """Freeze the capture's research manifest into citable lines (kind/text).
    Read-tolerant: a capture without research freezes an empty list (the
    design's grounding then fails honestly on having nothing to cite)."""
    if not isinstance(research, dict):
        return []
    kind_of = {
        "title": "title",
        "description": "description",
        "h1": "h1",
        "h2": "h2",
        "h3": "h3",
        "paragraphs": "paragraph",
        "body": "text",
        "buttons": "button",
        "links": "link",
    }
    lines: list[dict[str, Any]] = []
    for field_name in _RESEARCH_FIELDS:
        value = research.get(field_name)
        items = value if isinstance(value, list) else ([value] if value else [])
        for item in items:
            text = str(item or "").strip()
            if text:
                lines.append({"kind": kind_of[field_name], "text": text})
    return lines


def _round_half_up(value: Fraction) -> int:
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def _captured_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def store_source_bytes(data: bytes, suffix: str, content_type: str) -> tuple[str, str]:
    """Store bytes under their digest and verify a pre-existing object.

    This helper does not create an Asset or SourceSnapshot; fixture/asset
    preparation and the snapshot writers share the same immutable-key law.
    """
    if not _SUFFIX.fullmatch(suffix):
        raise ValueError(f"unsafe source suffix {suffix!r}")
    digest = hashlib.sha256(data).hexdigest()
    key = f"source-snapshots/{digest}{suffix.lower()}"
    if await storage.exists(key):
        existing = await storage.read(key)
        if hashlib.sha256(existing).hexdigest() != digest:
            raise ValueError(f"immutable source object {key} does not match its digest")
    else:
        await storage.save(key, data, content_type=content_type)
    return key, digest


async def _freeze_png(source_key: str) -> dict[str, Any]:
    """Copy one captured PNG to its immutable source identity and retain
    the actual pixel dimensions used by CSS-to-image mappings."""
    data = await storage.read(source_key)
    key, digest = await store_source_bytes(data, ".png", "image/png")
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG":
            raise ValueError(f"web capture {source_key} is not a PNG")
        width, height = image.size
    return {"storage_key": key, "digest": digest, "width": width, "height": height}


def align_cutout_png(data: bytes, paired_view: dict[str, Any], target_id: str) -> bytes:
    """Place real transparent target pixels in their frozen viewport, without scaling."""
    width, height = int(paired_view["width"]), int(paired_view["height"])
    target = next((e for e in paired_view.get("elements", []) if e.get("id") == target_id), None)
    if target is None:
        raise ValueError("cutout target is absent from its paired view")
    left = round((target["x"] - target["w"] / 2) * width)
    top = round((target["y"] - target["h"] / 2) * height)
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or "A" not in image.getbands():
            raise ValueError("cutout needs a real transparent PNG; recapture the target")
        expected = (round(target["w"] * width), round(target["h"] * height))
        if any(abs(a - b) > 2 for a, b in zip(image.size, expected)):
            raise ValueError("cutout pixels do not match the paired target dimensions")
        if left < 0 or top < 0 or left + image.width > width or top + image.height > height:
            raise ValueError("cutout target extends outside its frozen viewport")
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(image.convert("RGBA"), (left, top))
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


async def snapshot_web_cutout_canvas(db, *, owner_id, web_snapshot, view_id):
    """Prepare the fixed full-canvas image required by shared-camera Generators."""
    from app.editing.sources import register_web_view_snapshot
    raw = await register_web_view_snapshot(
        db, owner_id=owner_id, web_snapshot=web_snapshot, view_id=view_id,
    )
    if raw.meta.get("artifact_role") != "cutout":
        return raw
    paired = next((v for v in web_snapshot.meta.get("views", [])
                   if v.get("view_id") == raw.meta.get("paired_view_id")), None)
    if paired is None or not paired.get("state_id") or paired.get("state_id") != next(
        v.get("state_id") for v in web_snapshot.meta["views"] if v.get("view_id") == view_id
    ):
        raise ValueError("cutout and populated view must share a frozen state")
    data = await storage.read(raw.storage_key)
    if hashlib.sha256(data).hexdigest() != raw.digest:
        raise ValueError("cutout PNG differs from its frozen digest")
    canvas = align_cutout_png(data, paired, raw.meta["target_element_id"])
    key, digest = await store_source_bytes(canvas, ".png", "image/png")
    return await register_snapshot(
        db, owner_id=owner_id, asset=None, origin_project_id=raw.origin_project_id,
        kind="image", storage_key=key,
        digest=digest, duration_ticks=None, captured_at=web_snapshot.captured_at,
        identity=uuid5(raw.id, "full-canvas-v1:" + str(paired["view_id"])),
        meta={**raw.meta, "width": paired["width"], "height": paired["height"],
              "full_canvas": True, "cutout_snapshot_id": str(raw.id),
              "cutout_digest": raw.digest, "paired_view_digest": paired["digest"]},
    )


async def snapshot_web_generator_resources(
    db, *, owner_id, web_snapshot, issues=None, view_ids: set[str] | None = None,
):
    """Expose usable image resources for the selected views, or the whole capture."""
    from app.editing.sources import register_web_view_snapshot

    resources = []
    for view in (web_snapshot.meta or {}).get("views") or []:
        if view_ids is not None and view.get("view_id") not in view_ids:
            continue
        role = view.get("artifact_role") or "view"
        if role == "hero":
            continue
        try:
            snapshot = await (
                snapshot_web_cutout_canvas(
                    db, owner_id=owner_id, web_snapshot=web_snapshot, view_id=view["view_id"],
                )
                if role == "cutout" and view.get("transparent") is not False
                else register_web_view_snapshot(
                    db, owner_id=owner_id, web_snapshot=web_snapshot, view_id=view["view_id"],
                )
            )
            if canonical_resource(snapshot)["consumption"] == "generator_resource":
                resources.append(snapshot)
        except Exception as exc:
            if issues is not None and len(issues) < 64:
                issues.append({
                    key: value
                    for key, value in {
                        "state_id": view.get("state_id"), "output_id": view.get("output_id"),
                        "target_id": view.get("target_id"), "member_id": view.get("member_id"),
                        "error": f"fixed resource derivation failed: {str(exc)[:240]}",
                    }.items()
                    if value is not None
                })
    return resources


def frozen_source_lines(snapshot: SourceSnapshot) -> list[dict[str, Any]]:
    """Stable line identities for current and read-tolerant historical snapshots."""
    lines: list[dict[str, Any]] = []
    for index, raw in enumerate((snapshot.meta or {}).get("lines") or []):
        text = str(raw.get("text") or "")
        if not text:
            continue
        lines.append({
            **raw,
            "line_id": str(raw.get("line_id") or f"line_{index:04d}"),
            "text": text,
        })
    return lines


def resolve_frozen_line(snapshot: SourceSnapshot, line_id: str) -> dict[str, Any]:
    """Resolve exact source text, including leading zeroes, units and currency."""
    matches = [line for line in frozen_source_lines(snapshot) if line["line_id"] == line_id]
    if len(matches) != 1:
        raise ValueError(f"snapshot {snapshot.id} has no unique frozen line {line_id!r}")
    return matches[0]


def canonical_resource(snapshot: SourceSnapshot, *, target: Any = None) -> dict[str, Any]:
    """Compact default resource; a selected web target alone carries exact geometry."""
    meta = snapshot.meta or {}
    resource: dict[str, Any] = {
        "snapshot_id": str(snapshot.id),
        "kind": snapshot.kind,
        "digest": snapshot.digest,
        "duration_ticks": snapshot.duration_ticks,
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        "state": "frozen",
    }
    if snapshot.asset_id is not None:
        resource["asset_id"] = str(snapshot.asset_id)
    if snapshot.kind == "web":
        resource.update({
            "consumption": "web_object",
            "canonical_url": meta.get("canonical_url"),
            "capture_plan_digest": meta.get("capture_plan_digest"),
            "citable_lines": [
                {key: line.get(key) for key in ("line_id", "kind", "text") if line.get(key) is not None}
                for line in frozen_source_lines(snapshot)
            ],
            "views": [
                {
                    key: value
                    for key, value in {
                        "view_id": view.get("view_id"),
                        "heading": view.get("heading"),
                        "digest": view.get("digest"),
                        "storage_key": view.get("storage_key"),
                        "width": view.get("width"),
                        "height": view.get("height"),
                        "state_id": view.get("state_id"),
                        "output_id": view.get("output_id"),
                        "artifact_role": view.get("artifact_role") or "view",
                        "paired_view_id": view.get("paired_view_id"),
                        "target_id": view.get("target_id"),
                        "target_ids": view.get("target_ids"),
                        "target_element_id": view.get("target_element_id"),
                        "member_id": view.get("member_id"),
                        "transparent": view.get("transparent"),
                        "targets": [
                            {
                                key: element.get(key)
                                for key in ("id", "kind", "text", "label")
                                if element.get(key) is not None
                            }
                            for element in view.get("elements") or []
                        ],
                    }.items() if value is not None
                }
                for view in meta.get("views") or []
            ],
        })
        if target is not None:
            view_id = getattr(target, "view_id", None)
            element_id = getattr(target, "element_id", None)
            view = next(
                (
                    item
                    for item in meta.get("views") or []
                    if view_id is None or str(item.get("view_id")) == view_id
                ),
                None,
            )
            if view is None:
                raise ValueError(f"snapshot {snapshot.id} has no view {view_id!r}")
            if element_id is not None and not any(
                str(element.get("id")) == element_id for element in view.get("elements") or []
            ):
                raise ValueError(f"view {view.get('view_id')!r} has no element {element_id!r}")
            resource["selected_target"] = {
                "view_id": view.get("view_id"),
                "element_id": element_id,
                "view": view,
            }
        return resource
    resource.update({
        "width": meta.get("width") or (meta.get("media") or {}).get("width"),
        "height": meta.get("height") or (meta.get("media") or {}).get("height"),
        "origin": meta.get("origin"),
    })
    if snapshot.kind == "image" and meta.get("origin") == "web_view":
        role = str(meta.get("artifact_role") or "view")
        full_canvas = bool(meta.get("full_canvas"))
        raw_cutout = role in {"cutout", "hero"} and not full_canvas and meta.get("transparent") is not False
        resource.update({
            "consumption": "lineage_only" if raw_cutout else "generator_resource",
            "coordinate_space": (
                "raw_cutout_pixels" if raw_cutout
                else "full_canvas_pixels" if full_canvas
                else "captured_view_pixels"
            ),
            "state_id": meta.get("state_id"),
            "output_id": meta.get("output_id"),
            "artifact_role": meta.get("artifact_role"),
            "web_snapshot_id": meta.get("web_snapshot_id"),
            "view_id": meta.get("view_id"),
            "paired_view_id": meta.get("paired_view_id"),
            "target_id": meta.get("target_id"),
            "target_ids": meta.get("target_ids"),
            "target_element_id": meta.get("target_element_id"),
            "member_id": meta.get("member_id"),
            "transparent": meta.get("transparent"),
            "cutout_snapshot_id": meta.get("cutout_snapshot_id"),
            "cutout_digest": meta.get("cutout_digest"),
            "paired_view_digest": meta.get("paired_view_digest"),
        })
        if not raw_cutout:
            resource["fixed_resource"] = {
                "path": snapshot.storage_key,
                "snapshot_id": str(snapshot.id),
                "snapshot_digest": snapshot.digest,
                "content_type": meta.get("content_type") or "image/png",
            }
    else:
        resource["consumption"] = f"{snapshot.kind}_object"
    if snapshot.kind in {"audio", "video"} and snapshot.duration_ticks:
        # A full-source ClipSource is copy-ready just like fixed_resource for
        # Generator images. The model need not invent the required source_range
        # or confuse output ticks with the frozen source's own timebase.
        resource["clip_source"] = {
            "snapshot_id": str(snapshot.id),
            "snapshot_digest": snapshot.digest,
            "source_range": {"start": 0, "end": snapshot.duration_ticks},
        }
    return resource


async def snapshot_web_asset(db: AsyncSession, asset: Asset, *, owner_id: UUID) -> SourceSnapshot:
    """Freeze every captured view and the page manifest of a WEB_PAGE Asset.

    The manifest also freezes the capture's citable text lines (from
    ``meta.research``) — the design chain's grounding reads the SNAPSHOT,
    never a live page read (§9: the bound manifest is the design's world).
    """
    if asset.user_id != owner_id:
        raise PermissionError("web snapshot source belongs to another user")
    if asset.type != AssetType.WEB_PAGE:
        raise ValueError("web snapshots require a WEB_PAGE asset")
    source_meta = asset.meta or {}
    canonical_url = source_meta.get("capture_url")
    shots = source_meta.get("shots") or []
    if not isinstance(canonical_url, str) or not canonical_url or not shots:
        raise ValueError("web snapshot requires a canonical URL and captured views")

    captured_at = _captured_at(asset.created_at)
    views: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, shot in enumerate(shots):
        view_id = str(shot.get("view_id") or f"view-{index}")
        if not view_id or len(view_id) > 64 or view_id in seen_ids:
            raise ValueError(f"invalid or duplicate web view id {view_id!r}")
        seen_ids.add(view_id)
        source_key = shot.get("key")
        if not isinstance(source_key, str) or not source_key:
            raise ValueError(f"web view {view_id} has no captured image")
        frozen = await _freeze_png(source_key)
        elements: list[dict[str, Any]] = []
        for raw_element in shot.get("elements") or []:
            element = dict(raw_element)
            element.pop("image_width", None)
            element.pop("image_height", None)
            element_image_key = element.pop("image_key", None)
            if isinstance(element_image_key, str) and element_image_key:
                element_image = await _freeze_png(element_image_key)
                element["storage_key"] = element_image["storage_key"]
                element["digest"] = element_image["digest"]
                element["image_width"] = element_image["width"]
                element["image_height"] = element_image["height"]
            elements.append(element)
        view = {
            "view_id": view_id,
            "storage_key": frozen["storage_key"],
            "digest": frozen["digest"],
            "width": frozen["width"],
            "height": frozen["height"],
            "source_y": int(shot.get("y") or 0),
            "heading": str(shot.get("heading") or ""),
            "elements": elements,
            "device_scale_factor": float(shot.get("device_scale_factor") or 1.0),
        }
        for field_name in ("css_width", "css_height"):
            if shot.get(field_name) is not None:
                view[field_name] = int(shot[field_name])
        for field_name in (
            "state_id", "output_id", "artifact_role", "paired_view_id", "target_id",
            "target_ids", "target_element_id", "member_id", "transparent",
            "route", "actions", "page_height", "region_text",
            "region_text_truncated", "region_visually_truncated",
        ):
            if shot.get(field_name) is not None:
                view[field_name] = shot[field_name]
        views.append(view)

    research = source_meta.get("research")
    lines = _research_lines(research)
    seen_regions = {(line["kind"], line["text"]) for line in lines}
    for view in views:
        region_text = str(view.get("region_text") or "").strip()
        if view.get("artifact_role") != "view" or not region_text:
            continue
        key = ("selected_region", region_text)
        if key in seen_regions:
            continue
        seen_regions.add(key)
        lines.append({
            "kind": "selected_region",
            "text": region_text,
            "view_id": view["view_id"],
            "state_id": view.get("state_id"),
            "truncated": bool(view.get("region_text_truncated") or view.get("region_visually_truncated")),
        })
    for index, line in enumerate(lines):
        # Stable within this immutable manifest; source text is resolved by id
        # at authoring time instead of being transcribed by the model.
        line["line_id"] = f"line_{index:04d}"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "canonical_url": canonical_url,
        "captured_at": captured_at.isoformat(),
        "views": views,
        "lines": lines,
    }
    # Capture completeness is metadata, never a citable product line. Older
    # snapshots legitimately have no fact here; absence must stay unknown.
    if isinstance(research, dict) and isinstance(research.get("body_truncated"), bool):
        manifest["body_truncated"] = research["body_truncated"]
    source_page = source_meta.get("page")
    if isinstance(source_page, dict) and isinstance(source_page.get("key"), str):
        frozen_page = await _freeze_png(source_page["key"])
        manifest["page"] = {
            key: value for key, value in source_page.items() if key != "key"
        } | frozen_page
    origin = source_meta.get("origin")
    if origin is not None:
        manifest["origin"] = origin
    if isinstance(source_meta.get("capture_plan"), dict):
        manifest["capture_plan"] = source_meta["capture_plan"]
        manifest["capture_plan_digest"] = source_meta.get("capture_plan_digest")
        manifest["capture_warnings"] = list(source_meta.get("capture_warnings") or [])
        manifest["capture_issues"] = list(source_meta.get("capture_issues") or [])
        manifest["capture_issue_count"] = int(source_meta.get("capture_issue_count") or 0)
        manifest["capture_issues_truncated"] = bool(source_meta.get("capture_issues_truncated"))
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_key, manifest_digest = await store_source_bytes(
        manifest_bytes, ".json", "application/json"
    )
    return await register_snapshot(
        db,
        owner_id=owner_id,
        asset=asset,
        kind="web",
        storage_key=manifest_key,
        digest=manifest_digest,
        duration_ticks=None,
        meta=manifest,
        captured_at=captured_at,
    )


async def snapshot_narration_original(
    db: AsyncSession,
    project: Project,
    *,
    text: str,
    original: dict[str, Any],
    scene_id: str | None = None,
) -> tuple[Asset, SourceSnapshot]:
    """Register one already-fixed VideoNarration original as ordinary audio."""
    media = original["media"]
    query = select(Asset).where(
        Asset.user_id == project.user_id,
        Asset.project_id == project.id,
        Asset.type == AssetType.AUDIO,
        Asset.file_url == media["storage_key"],
    )
    if scene_id is not None:
        from app.tools.video.media_analysis import AUDIO_ANALYZER_SET_VERSION

        query = query.where(
            Asset.meta["origin"]["scene_id"].as_string() == scene_id,
            Asset.meta["origin"]["analysis_version"].as_string() == AUDIO_ANALYZER_SET_VERSION,
        )
    asset = await db.scalar(query)
    if asset is None:
        asset = Asset(
            user_id=project.user_id,
            project_id=project.id,
            type=AssetType.AUDIO,
            file_url=media["storage_key"],
            transcript=text,
            processing_status=AssetStatus.COMPLETED,
            duration_seconds=max(1, round(float(original["duration_s"]))),
            meta={"origin": {
                "video_narration_hash": original["content_hash"],
                **({"scene_id": scene_id} if scene_id is not None else {}),
                **({"analysis_version": AUDIO_ANALYZER_SET_VERSION} if scene_id is not None else {}),
            }},
            processed_at=now_utc(),
        )
        db.add(asset)
        await db.flush()
    snapshot = await snapshot_audio_asset(db, asset, owner_id=project.user_id, analyze=True)
    return asset, snapshot


async def _snapshot_audio_bytes(
    db: AsyncSession,
    *,
    owner_id: UUID,
    data: bytes,
    suffix: str,
    origin: dict[str, Any] | None,
    captured_at: datetime,
    asset: Asset | None = None,
    identity: UUID | None = None,
    analyze: bool = False,
) -> SourceSnapshot:
    content_type = "audio/wav" if suffix == ".wav" else "audio/mpeg"
    key, digest = await store_source_bytes(data, suffix, content_type)
    container = av.open(io.BytesIO(data), mode="r")
    try:
        stream = container.streams.audio[0]
        if stream.duration is not None and stream.time_base is not None:
            duration = Fraction(stream.duration) * Fraction(stream.time_base)
        elif container.duration is not None:
            duration = Fraction(container.duration, av.time_base)
        else:
            raise ValueError("audio source has no decodable duration")
        duration_ticks = _round_half_up(duration * SOURCE_TIMEBASE)
        media = {"sample_rate": int(stream.rate), "channels": int(stream.channels)}
    finally:
        container.close()

    meta: dict[str, Any] = {"media": media}
    if origin is not None:
        meta["origin"] = origin
    if analyze:
        from app.models.ids import source_snapshot_id
        from app.tools.video.media_analysis import analyze_audio_bytes, store_media_analysis

        anchor = asset.id if asset is not None else identity
        if anchor is None:
            raise ValueError("analyzed audio needs a stable snapshot identity")
        snapshot_id = source_snapshot_id(owner_id, anchor, "audio", digest)
        report = await asyncio.to_thread(
            analyze_audio_bytes,
            data,
            snapshot_id=str(snapshot_id),
            source_digest=digest,
        )
        meta["analysis_ref"] = await store_media_analysis(report)
        decode = report.media_facts["decode"]
        duration_ticks = _round_half_up(
            Fraction(decode["sample_count"], report.media_facts["sample_rate"]) * SOURCE_TIMEBASE
        )
        media = {
            "sample_rate": report.media_facts["sample_rate"],
            "channels": report.media_facts["channels"],
        }
        meta["media"] = media
    return await register_snapshot(
        db,
        owner_id=owner_id,
        asset=asset,
        identity=identity,
        kind="audio",
        storage_key=key,
        digest=digest,
        duration_ticks=duration_ticks,
        meta=meta,
        captured_at=captured_at,
    )


async def snapshot_image_asset(db: AsyncSession, asset: Asset, *, owner_id: UUID) -> SourceSnapshot:
    """Freeze an IMAGE Asset's real bytes and pixel dimensions."""
    if asset.user_id != owner_id:
        raise PermissionError("image snapshot source belongs to another user")
    if asset.type != AssetType.IMAGE or not asset.file_url:
        raise ValueError("image snapshots require an IMAGE asset with stored bytes")
    data = await storage.read(asset.file_url)
    with Image.open(io.BytesIO(data)) as image:
        image_format = image.format
        width, height = image.size
        image.verify()
    suffix_by_format = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
    suffix = suffix_by_format.get(image_format or "")
    if suffix is None:
        raise ValueError("image snapshots support PNG, JPEG and WebP bytes")
    content_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image_format or ""]
    key, digest = await store_source_bytes(data, suffix, content_type)
    meta: dict[str, Any] = {
        "title": asset.display_name,
        "width": width,
        "height": height,
    }
    origin = (asset.meta or {}).get("origin")
    if origin is not None:
        meta["origin"] = origin
    return await register_snapshot(
        db,
        owner_id=owner_id,
        asset=asset,
        kind="image",
        storage_key=key,
        digest=digest,
        duration_ticks=None,
        meta=meta,
        captured_at=_captured_at(asset.created_at),
    )


async def snapshot_audio_asset(
    db: AsyncSession, asset: Asset, *, owner_id: UUID, analyze: bool = False
) -> SourceSnapshot:
    """Freeze an AUDIO Asset and probe its real source-time duration."""
    if asset.user_id != owner_id:
        raise PermissionError("audio snapshot source belongs to another user")
    if asset.type != AssetType.AUDIO or not asset.file_url:
        raise ValueError("audio snapshots require an AUDIO asset with stored bytes")
    return await _snapshot_audio_bytes(
        db,
        owner_id=owner_id,
        data=await storage.read(asset.file_url),
        suffix=Path(asset.file_url).suffix.lower() or ".audio",
        origin=(asset.meta or {}).get("origin"),
        captured_at=_captured_at(asset.created_at),
        asset=asset,
        analyze=analyze,
    )


async def snapshot_fixed_audio(
    db: AsyncSession,
    *,
    owner_id: UUID,
    storage_key: str,
    digest: str,
    origin: dict[str, Any],
) -> SourceSnapshot:
    """Reuse one code-declared, license-cleared platform sound without a new Asset."""
    if origin.get("kind") != "sfx" or origin.get("license") != "CC0":
        raise ValueError("fixed audio requires a declared CC0 SFX origin")
    data = await storage.read(storage_key)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("fixed audio bytes do not match their declared digest")
    return await _snapshot_audio_bytes(
        db,
        owner_id=owner_id,
        data=data,
        suffix=Path(storage_key).suffix.lower(),
        origin=origin,
        captured_at=now_utc(),
        identity=uuid5(UUID(int=0), f"fixed-audio:{digest}"),
    )


async def snapshot_video_asset(db: AsyncSession, asset: Asset, *, owner_id: UUID) -> SourceSnapshot:
    """Freeze real video bytes, dimensions, duration and available ASR facts."""
    if asset.user_id != owner_id:
        raise PermissionError("video snapshot source belongs to another user")
    if asset.type != AssetType.VIDEO or not asset.file_url:
        raise ValueError("video snapshots require a VIDEO asset with stored bytes")
    source_meta = asset.meta or {}
    meta: dict[str, Any] = {
        "title": asset.display_name,
        "transcript": asset.transcript,
        "words": source_meta.get("words") or [],
        "language": source_meta.get("language"),
    }
    origin = source_meta.get("origin")
    if origin is not None:
        meta["origin"] = origin
    return await _snapshot_video_bytes(
        db,
        owner_id=owner_id,
        storage_key=asset.file_url,
        asset=asset,
        meta=meta,
        captured_at=_captured_at(asset.created_at),
    )


async def snapshot_video_output(db: AsyncSession, output: Output, *, owner_id: UUID) -> SourceSnapshot:
    """Use a delivered Output as material without targeting its Composition.

    Editing the original work remains the separate @output revision path.
    """
    project = await db.get(Project, output.project_id)
    if project is None or project.user_id != owner_id:
        raise PermissionError("video output belongs to another user")
    storage_key = (output.files or {}).get("video")
    if not isinstance(storage_key, str) or not storage_key:
        raise ValueError("video output has no delivered video bytes")
    return await _snapshot_video_bytes(
        db,
        owner_id=owner_id,
        storage_key=storage_key,
        asset=None,
        identity=output.id,
        meta={"title": (output.payload or {}).get("name"), "origin": {"output_id": str(output.id)}},
        captured_at=_captured_at(output.created_at),
    )


async def _snapshot_video_bytes(
    db: AsyncSession,
    *,
    owner_id: UUID,
    storage_key: str,
    asset: Asset | None,
    meta: dict[str, Any],
    captured_at: datetime,
    identity: UUID | None = None,
) -> SourceSnapshot:
    data = await storage.read(storage_key)
    suffix = Path(storage_key).suffix.lower() or ".mp4"
    content_type = "video/quicktime" if suffix == ".mov" else "video/mp4"
    key, digest = await store_source_bytes(data, suffix, content_type)

    container = av.open(io.BytesIO(data), mode="r")
    try:
        if not container.streams.video:
            raise ValueError("video source has no video stream")
        stream = container.streams.video[0]
        if stream.duration is not None and stream.time_base is not None:
            duration = Fraction(stream.duration) * Fraction(stream.time_base)
        elif container.duration is not None:
            duration = Fraction(container.duration, av.time_base)
        else:
            raise ValueError("video source has no decodable duration")
        duration_ticks = _round_half_up(duration * SOURCE_TIMEBASE)
        width = int(stream.codec_context.width or 0)
        height = int(stream.codec_context.height or 0)
        if duration_ticks <= 0 or width <= 0 or height <= 0:
            raise ValueError("video source has invalid media dimensions or duration")
        media = {
            "width": width,
            "height": height,
            "has_audio": bool(container.streams.audio),
        }
    finally:
        container.close()

    return await register_snapshot(
        db,
        owner_id=owner_id,
        asset=asset,
        identity=identity,
        kind="video",
        storage_key=key,
        digest=digest,
        duration_ticks=duration_ticks,
        meta={**meta, "media": media},
        captured_at=captured_at,
    )


async def snapshot_music_track(db: AsyncSession, track: Any, *, owner_id: UUID) -> SourceSnapshot:
    """Freeze a music-library piece as an audio SourceSnapshot.

    The catalog's bytes already live in object storage under
    ``music/{id}.mp3``; the snapshot re-stores them under the immutable
    content-addressed key (idempotent) so a version pins BYTES, never a
    mutable library row. A persisted ``meta.content_sha256`` must match the
    actual bytes; the freshly computed ``SourceSnapshot.digest`` remains the
    authoritative identity. The snapshot carries no Asset anchor — the Music
    row's id is the stable identity (platform-owned source).
    """
    source_key = track.file_path or music_file_path(track.id)
    data = await storage.read(source_key)
    track_meta = track.meta or {}
    expected_digest = track_meta.get("content_sha256")
    actual_digest = hashlib.sha256(data).hexdigest()
    if expected_digest is not None and actual_digest != expected_digest:
        raise ValueError(f"music {track.id} bytes do not match meta.content_sha256")
    suffix = Path(source_key).suffix.lower() or f".{AUDIO_EXT}"
    content_type = "audio/wav" if suffix == ".wav" else "audio/mpeg"
    key, digest = await store_source_bytes(data, suffix, content_type)

    container = av.open(io.BytesIO(data), mode="r")
    try:
        stream = container.streams.audio[0]
        if stream.duration is not None and stream.time_base is not None:
            duration = Fraction(stream.duration) * Fraction(stream.time_base)
        elif container.duration is not None:
            duration = Fraction(container.duration, av.time_base)
        else:
            raise ValueError("music source has no decodable duration")
        duration_ticks = _round_half_up(duration * SOURCE_TIMEBASE)
        media = {"sample_rate": int(stream.rate), "channels": int(stream.channels)}
    finally:
        container.close()

    beat_grid = track_meta.get("beat_grid") or {
        key: track_meta.get(key) for key in ("bpm", "beats")
    }
    if beat_grid.get("beats") and not beat_grid.get("origin"):
        beat_grid = {**beat_grid, "origin": "estimated"}
    meta = {
        "media": media,
        "music": {"music_id": str(track.id), "title": track.title},
        "beat_grid": beat_grid,
    }
    for field in ("score_digest", "score_spec_ref", "analysis_ref"):
        if track_meta.get(field) is not None:
            meta[field] = track_meta[field]
    return await register_snapshot(
        db,
        owner_id=owner_id,
        asset=None,
        identity=uuid5(track.id, "music-beat-grid-v1:" + hashlib.sha256(
            json.dumps(track_meta, sort_keys=True).encode()).hexdigest()),
        kind="audio",
        storage_key=key,
        digest=digest,
        duration_ticks=duration_ticks,
        meta=meta,
        captured_at=_captured_at(getattr(track, "created_at", None)),
    )


async def ensure_font_resources() -> dict[str, int]:
    """Publish the repo-pinned font bytes for local/manual production drills.

    This is storage preparation, not a Composition write. Existing objects are
    left untouched; the renderer still re-hashes them at execution time.
    """
    reused_count = 0
    for item in FONT_FILES:
        data = (_FONT_ROOT / str(item["filename"])).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != item["digest"]:
            raise ValueError(f"pinned font {item['filename']} has unexpected digest {digest}")
        key = font_storage_key(str(item["filename"]), digest)
        if await storage.exists(key):
            reused_count += 1
        else:
            await storage.save(key, data, content_type="font/otf")
    return {"item_count": len(FONT_FILES), "reused_count": reused_count}
