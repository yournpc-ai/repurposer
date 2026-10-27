"""Owner-scoped immutable SourceSnapshot registration; no storage/provider IO.

The application preparation seam supplies pinned bytes/manifest facts.
Composition bindings are still written only by apply_composition_edits.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Asset, SourceSnapshot


def _snapshot_id(owner_id: UUID, asset_id: UUID, kind: str, digest: str) -> UUID:
    return uuid5(
        uuid5(UUID(int=0), "repurposer-source-snapshot"),
        f"{owner_id}:{asset_id}:{kind}:{digest}",
    )


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
) -> SourceSnapshot:
    """Register one immutable snapshot. ``asset`` is the provenance anchor
    for user assets; platform-owned sources (the default music catalog)
    carry ``asset=None`` and a stable ``identity`` for id derivation
    instead (the catalog piece's own id)."""
    if asset is not None and asset.user_id != owner_id:
        raise PermissionError("snapshot source belongs to another user")
    anchor = asset.id if asset is not None else identity
    if anchor is None:
        raise ValueError("an asset-less snapshot requires a stable identity")
    snapshot_id = _snapshot_id(owner_id, anchor, kind, digest)
    existing = await db.get(SourceSnapshot, snapshot_id)
    if existing is not None:
        expected = (
            existing.owner_id == owner_id
            and existing.asset_id == (asset.id if asset is not None else None)
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


