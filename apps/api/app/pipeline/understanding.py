"""Material analysis shared by asset processing and native Chat reads."""

from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import understand
from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType, MaterialUnderstanding
from app.models.tables import Output, Project
from app.pipeline.assets import asset_text_content
from app.pipeline.beat_map import build_source_blocks, image_refs_from_assets, word_axis_from_assets
from app.pipeline.step_context import _source_language, asset_digest, collect_asset_media, list_assets

logger = structlog.get_logger()


async def find_reusable_understanding(
    db: AsyncSession, project: Project, digest: str
) -> Output | None:
    """Find an existing material analysis for this owner's exact asset digest."""
    rows = (
        (
            await db.execute(
                select(Output)
                .join(Project, Output.project_id == Project.id)
                .where(
                    Project.user_id == project.user_id,
                    Output.type == "material_understanding",
                )
                .order_by(Output.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if (row.source_ref or {}).get("asset_hash") == digest:
            return row
    return None


async def _materialize_understanding(
    project: Project, assets: list
) -> MaterialUnderstanding:
    """Collect the source evidence for one material analysis."""
    asset_media = await collect_asset_media(assets)
    return await understand.call(
        source_blocks=build_source_blocks(assets),
        asset_media=asset_media,
        word_axis=word_axis_from_assets(assets),
        image_refs=image_refs_from_assets(assets),
    )


def _understandable(assets: list) -> bool:
    """The warm's digestibility gate — at least one asset carries text or
    media worth understanding. Shared with the lazy self-heal guard so it
    never fires a warm that would no-op on the same fact."""
    asset_texts = [t for a in assets if (t := asset_text_content(a))]
    has_media = any(
        (a.type == AssetType.IMAGE and a.file_url)
        or (a.type == AssetType.SLIDES and a.slide_pages)
        or (a.type == AssetType.VIDEO and a.file_url)
        for a in assets
    )
    return bool(asset_texts or has_media)


async def warm_understanding(project_id: UUID) -> None:
    """Materialize the analysis once, including concurrent asset and Chat reads."""
    try:
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, project_id)
            if project is None:
                return
            assets = await list_assets(db, project_id)
            if not assets or any(
                a.processing_status != AssetStatus.COMPLETED for a in assets
            ):
                return  # a later asset's completion re-triggers the warm
            if not _understandable(assets):
                return
            digest = asset_digest(assets)
            identity = f"material-understanding:{project.user_id}:{digest}"
            await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(identity, 0))))
            if await find_reusable_understanding(db, project, digest) is not None:
                logger.info("understanding_warm_reuse_hit", project_id=str(project_id))
            else:
                understanding = await _materialize_understanding(project, assets)
                row = Output(
                    project_id=project.id,
                    type="material_understanding",
                    language=_source_language(project, assets),
                    provenance="generated",
                    payload=understanding.model_dump(mode="json"),
                    source_ref={"asset_hash": digest, "warmed": True},
                )
                db.add(row)
                try:
                    await db.commit()
                except IntegrityError:
                    # 唯一索引收口 (migration n4d7e0a3b6c9, 2026-09-28): a
                    # concurrent warm (the worker's completion seat vs the
                    # API's lazy seat) landed the same digest first — the
                    # race loser IS a reuse-hit discovered late.
                    await db.rollback()
                    logger.info(
                        "understanding_warm_race_lost", project_id=str(project_id)
                    )
                else:
                    logger.info(
                        "understanding_warmed",
                        project_id=str(project_id),
                        arguments=len(understanding.key_arguments),
                        quotes=len(understanding.quotable_lines),
                        beats=len(understanding.topic_boundaries),
                    )
    except Exception as e:  # noqa: BLE001 — warm is best-effort, the run path pays later
        logger.warning(
            "understanding_warm_failed", project_id=str(project_id), error=str(e)
        )
