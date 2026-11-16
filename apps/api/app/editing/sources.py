"""Owner-scoped immutable SourceSnapshot registration; no storage/provider IO.

The application preparation seam supplies pinned bytes/manifest facts.
Composition bindings are still written only by apply_composition_edits.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ids import source_snapshot_id
from app.models.tables import Asset, SourceSnapshot


async def register_snapshot(
    db: AsyncSession,
    *,
    owner_id: UUID,
    asset: Asset | None,
    kind: str,
    storage_key: str,
    digest: str,
    duration_ticks: int | None,
    meta: dict[str, Any],
    captured_at: datetime,
    identity: UUID | None = None,
    origin_project_id: UUID | None = None,
) -> SourceSnapshot:
    """Register one immutable snapshot. ``asset`` is the provenance anchor
    for user assets; platform-owned sources (the default music catalog)
    carry ``asset=None`` and a stable ``identity`` for id derivation
    instead (the catalog piece's own id)."""
    if asset is not None and asset.user_id != owner_id:
        raise PermissionError("snapshot source belongs to another user")
    project_id = origin_project_id or (asset.project_id if asset is not None else None)
    anchor = asset.id if asset is not None else identity
    if anchor is None:
        raise ValueError("an asset-less snapshot requires a stable identity")
    snapshot_id = source_snapshot_id(owner_id, anchor, kind, digest)
    existing = await db.get(SourceSnapshot, snapshot_id)
    if existing is not None:
        expected = (
            existing.owner_id == owner_id
            and existing.asset_id == (asset.id if asset is not None else None)
            # Asset-less library media may be reused in another Chat by the
            # same owner. Birth provenance is not an access boundary; bytes,
            # metadata and owner still have to match exactly.
            and (asset is None or existing.origin_project_id in {None, project_id})
            and existing.kind == kind
            and existing.storage_key == storage_key
            and existing.digest == digest
            and existing.duration_ticks == duration_ticks
            and existing.meta == meta
        )
        if not expected:
            raise ValueError(f"source snapshot identity collision at {snapshot_id}")
        return existing
    row = SourceSnapshot(
        id=snapshot_id,
        owner_id=owner_id,
        asset_id=asset.id if asset is not None else None,
        origin_project_id=project_id,
        kind=kind,
        storage_key=storage_key,
        digest=digest,
        duration_ticks=duration_ticks,
        meta=meta,
        captured_at=captured_at,
    )
    db.add(row)
    await db.flush()
    return row


async def register_web_view_snapshot(
    db: AsyncSession,
    *,
    owner_id: UUID,
    web_snapshot: SourceSnapshot,
    view_id: str,
) -> SourceSnapshot:
    """Register one captured PNG view as an ordinary owner-scoped image.

    The view is resolved from the web snapshot itself; its existing storage key
    and byte digest are reused without storage IO, recapture or a second Asset.
    """
    if web_snapshot.owner_id != owner_id:
        raise PermissionError("web snapshot source belongs to another user")
    if web_snapshot.kind != "web":
        raise ValueError("web-view derivatives require a web SourceSnapshot")
    matches = [
        view for view in (web_snapshot.meta or {}).get("views") or []
        if view.get("view_id") == view_id
    ]
    if len(matches) != 1:
        raise ValueError(f"web snapshot must contain exactly one view {view_id!r}")
    view = matches[0]
    storage_key = view.get("storage_key")
    digest = view.get("digest")
    if not isinstance(storage_key, str) or not storage_key.strip():
        raise ValueError(f"web view {view_id!r} lacks immutable PNG storage")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"web view {view_id!r} lacks its exact PNG digest")
    dimensions = {}
    for key in ("width", "height"):
        value = view.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"web view {view_id!r} lacks positive pixel dimensions")
        dimensions[key] = value
    content_type = view.get("content_type") or "image/png"
    if content_type != "image/png":
        raise ValueError(f"web view {view_id!r} is not a captured PNG")
    meta = {
        "origin": "web_view",
        "web_snapshot_id": str(web_snapshot.id),
        "view_id": view_id,
        "state_id": view.get("state_id"),
        "output_id": view.get("output_id"),
        "artifact_role": view.get("artifact_role") or "view",
        "paired_view_id": view.get("paired_view_id"),
        "target_id": view.get("target_id"),
        "target_ids": view.get("target_ids"),
        "target_element_id": view.get("target_element_id"),
        "member_id": view.get("member_id"),
        "transparent": view.get("transparent"),
        "content_type": content_type,
        **dimensions,
    }
    if view.get("device_scale_factor") is not None:
        meta["device_scale_factor"] = view["device_scale_factor"]
    identity = uuid5(
        UUID(int=0),
        f"web-view:{web_snapshot.id}:{view_id}:{digest}",
    )
    return await register_snapshot(
        db,
        owner_id=owner_id,
        asset=None,
        origin_project_id=web_snapshot.origin_project_id,
        identity=identity,
        kind="image",
        storage_key=storage_key,
        digest=digest,
        duration_ticks=None,
        meta=meta,
        captured_at=web_snapshot.captured_at,
    )


