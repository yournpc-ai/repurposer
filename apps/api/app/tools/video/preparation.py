"""Application IO for pinned media and fonts; no Composition content writes.

Existing capture/storage owns bytes. Editing owns snapshot registration,
version bindings, validation and pure font descriptors.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from uuid import UUID
from typing import Any

import av
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.fonts import FONT_FILES, font_storage_key
from app.editing.sources import register_snapshot
from app.editing.timing import SOURCE_TIMEBASE
from app.models.schemas import AssetType
from app.models.tables import Asset, SourceSnapshot
from app.providers import storage

_FONT_ROOT = Path(__file__).resolve().parents[3] / "assets" / "fonts"

_SUFFIX = re.compile(r"^\.[a-z0-9]{1,8}$", re.IGNORECASE)


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


async def snapshot_web_asset(db: AsyncSession, asset: Asset, *, owner_id: UUID) -> SourceSnapshot:
    """Freeze every captured view and the page manifest of a WEB_PAGE Asset."""
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
        data = await storage.read(source_key)
        key, digest = await store_source_bytes(data, ".png", "image/png")
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG":
                raise ValueError(f"web view {view_id} is not a PNG capture")
            width, height = image.size
        views.append(
            {
                "view_id": view_id,
                "storage_key": key,
                "digest": digest,
                "width": width,
                "height": height,
                "source_y": int(shot.get("y") or 0),
                "heading": str(shot.get("heading") or ""),
                "elements": shot.get("elements") or [],
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "canonical_url": canonical_url,
        "captured_at": captured_at.isoformat(),
        "views": views,
    }
    origin = source_meta.get("origin")
    if origin is not None:
        manifest["origin"] = origin
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


async def snapshot_audio_asset(db: AsyncSession, asset: Asset, *, owner_id: UUID) -> SourceSnapshot:
    """Freeze an AUDIO Asset and probe its real source-time duration."""
    if asset.user_id != owner_id:
        raise PermissionError("audio snapshot source belongs to another user")
    if asset.type != AssetType.AUDIO or not asset.file_url:
        raise ValueError("audio snapshots require an AUDIO asset with stored bytes")
    data = await storage.read(asset.file_url)
    suffix = Path(asset.file_url).suffix.lower() or ".audio"
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

    origin = (asset.meta or {}).get("origin")
    meta: dict[str, Any] = {"media": media}
    if origin is not None:
        meta["origin"] = origin
    return await register_snapshot(
        db,
        owner_id=owner_id,
        asset=asset,
        kind="audio",
        storage_key=key,
        digest=digest,
        duration_ticks=duration_ticks,
        meta=meta,
        captured_at=_captured_at(asset.created_at),
    )


async def ensure_font_resources() -> None:
    """Publish the repo-pinned font bytes for local/manual production drills.

    This is storage preparation, not a Composition write. Existing objects are
    left untouched; the renderer still re-hashes them at execution time.
    """
    for item in FONT_FILES:
        data = (_FONT_ROOT / str(item["filename"])).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != item["digest"]:
            raise ValueError(f"pinned font {item['filename']} has unexpected digest {digest}")
        key = font_storage_key(str(item["filename"]), digest)
        if not await storage.exists(key):
            await storage.save(key, data, content_type="font/otf")
