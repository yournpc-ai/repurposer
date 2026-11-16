"""Deterministic owner-scoped source identity shared by assets and Skill media."""
from __future__ import annotations

from uuid import UUID, uuid5


def source_snapshot_id(owner_id: UUID, anchor: UUID, kind: str, digest: str) -> UUID:
    return uuid5(
        uuid5(UUID(int=0), "repurposer-source-snapshot"),
        f"{owner_id}:{anchor}:{kind}:{digest}",
    )
