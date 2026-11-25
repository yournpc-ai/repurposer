"""Resolve a permanent recording through the editing source registry."""

from uuid import uuid5

from sqlalchemy import select

from app.catalog.search import visible
from app.editing.sources import register_snapshot
from app.editing.timing import SOURCE_TIMEBASE
from app.models.tables import SoundEffect


async def freeze_library_sfx(db, project, slug):
    row = await db.scalar(
        select(SoundEffect)
        .where(
            visible(SoundEffect, project.user_id),
            SoundEffect.engine_kind == "sample",
            SoundEffect.slug == slug,
        )
        .with_for_update()
    )
    if not row or not (row.storage_key and row.content_sha256 and row.duration_ms):
        raise ValueError("Select a visible, ready sample from search_sfx_library.")
    return await register_snapshot(
        db,
        owner_id=project.user_id,
        origin_project_id=project.id,
        asset=None,
        identity=uuid5(project.id, str(row.id)),
        kind="audio",
        storage_key=row.storage_key,
        digest=row.content_sha256,
        duration_ticks=round(row.duration_ms * SOURCE_TIMEBASE / 1000),
        captured_at=row.created_at,
        meta={"origin": {"kind": "library_sfx", "slug": row.slug}},
    )
