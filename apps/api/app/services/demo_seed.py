"""Idempotent demo project seeding using the real generation pipeline.

The demo project lets first-time visitors see a fully populated results page
without uploading their own media. It reuses the default user and a fixed
project UUID so it can be safely re-run on every app startup.

On first run the seed:
  1. Creates a demo speaker, brand template, project and video asset.
  2. Runs ASR on ``assets/demo/uploads/projects/{uuid}/demo_talk.mp4``.
  3. Seeds the original prompt into a project-scoped chat session.
  4. Runs the same ``run_generation`` orchestrator the worker uses to create
     clips, a social post, quote cards, a carousel, and an article.
  5. Renders each clip through the Remotion render service so the results page
     is immediately playable.

Subsequent startups are no-ops unless the outputs were deleted, in which case
the seed regenerates them.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select

from app.dependencies.auth import DEFAULT_USER_ID
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetStatus,
    AssetType,
    ProjectStatus,
    WorkflowStatus,
)
from app.models.tables import (
    Asset,
    BrandTemplate,
    Clip,
    Derivative,
    Project,
    Speaker,
    User,
    WorkflowRun,
)
from app.services.asset_processing import process_asset
from app.services.brand import DEFAULT_BRAND_CONFIG
from app.services.chat import seed_project_prompt
from app.services.generation import run_generation
from app.services.storage import (
    get_project_output_dir,
    get_project_upload_dir,
)

logger = structlog.get_logger()

DEMO_PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
DEMO_SPEAKER_ID = UUID("22222222-2222-2222-2222-222222222222")
DEMO_BRAND_TEMPLATE_ID = UUID("33333333-3333-3333-3333-333333333333")

DEMO_USER_MESSAGE = (
    "Turn this resilience talk into three short vertical clips, a social post, "
    "quote cards, and an article."
)


def _demo_paths() -> tuple[str, str]:
    """Return upload and output prefixes for the demo project."""
    upload_prefix = get_project_upload_dir(DEMO_PROJECT_ID, "demo")
    output_prefix = get_project_output_dir(DEMO_PROJECT_ID, "demo")
    return upload_prefix, output_prefix


async def _get_or_create_demo_user(db) -> User | None:
    user = await db.get(User, UUID(DEFAULT_USER_ID))
    if user is None:
        logger.warning("demo_seed_default_user_missing")
    return user


async def _get_or_create_demo_speaker(db, user_id: UUID) -> Speaker:
    speaker = await db.get(Speaker, DEMO_SPEAKER_ID)
    if speaker is None:
        speaker = Speaker(
            id=DEMO_SPEAKER_ID,
            user_id=user_id,
            name="Alex Morgan",
            title="Leadership Coach & Resilience Speaker",
            language="en",
            core_values=["resilience", "clarity", "decisive action"],
            sentence_style="direct, conversational, story-driven",
            emotional_tone="passionate",
            typical_hooks=[
                "How hard can it be?",
                "Move on, keep moving",
            ],
            avoid_words=["leverage", "synergy", "disrupt"],
        )
        db.add(speaker)
        await db.flush()
    return speaker


async def _get_or_create_demo_brand(db, user_id: UUID) -> BrandTemplate:
    brand = await db.get(BrandTemplate, DEMO_BRAND_TEMPLATE_ID)
    if brand is None:
        brand_config = dict(DEFAULT_BRAND_CONFIG)
        brand = BrandTemplate(
            id=DEMO_BRAND_TEMPLATE_ID,
            user_id=user_id,
            name="Demo Brand",
            config=brand_config,
        )
        db.add(brand)
        await db.flush()
    return brand


async def _get_or_create_demo_project(db, user_id: UUID, speaker_id: UUID) -> Project:
    project = await db.get(Project, DEMO_PROJECT_ID)
    if project is None:
        project = Project(
            id=DEMO_PROJECT_ID,
            user_id=user_id,
            speaker_id=speaker_id,
            title="Example: Resilience Talk",
            event_name="Resilience Summit 2026",
            language="en",
            status=ProjectStatus.DRAFT,
            tone_snapshot={
                "academic_vs_casual": 0.3,
                "rational_vs_passionate": 0.6,
                "concise_vs_detailed": 0.5,
                "audience": "industry",
            },
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(project)
        await db.flush()
    return project


async def _get_or_create_demo_asset(db, user_id: UUID, project_id: UUID) -> Asset:
    result = await db.execute(
        select(Asset).where(
            Asset.project_id == DEMO_PROJECT_ID,
            Asset.type == AssetType.VIDEO,
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        demo_video_rel = "demo/uploads/demo_talk.mp4"
        asset = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.VIDEO,
            file_url=demo_video_rel,
            processing_status=AssetStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        db.add(asset)
        await db.flush()
    return asset


async def _count_clips(db) -> int:
    return await db.scalar(
        select(func.count()).where(Clip.project_id == DEMO_PROJECT_ID)
    ) or 0


async def _count_derivatives(db) -> int:
    return await db.scalar(
        select(func.count()).where(Derivative.project_id == DEMO_PROJECT_ID)
    ) or 0


async def seed_demo_project() -> None:
    """Create or refresh the demo project using the real generation pipeline."""
    async with AsyncSessionLocal() as db:
        user = await _get_or_create_demo_user(db)
        if user is None:
            return

        existing_project = await db.get(Project, DEMO_PROJECT_ID)
        if existing_project is not None:
            clip_count = await _count_clips(db)
            derivative_count = await _count_derivatives(db)
            if clip_count > 0 and derivative_count > 0:
                logger.debug(
                    "demo_project_already_seeded",
                    clips=clip_count,
                    derivatives=derivative_count,
                )
                return
            logger.info(
                "demo_project_partial_seed",
                clips=clip_count,
                derivatives=derivative_count,
            )

        _demo_paths()

        speaker = await _get_or_create_demo_speaker(db, user.id)
        brand = await _get_or_create_demo_brand(db, user.id)
        project = await _get_or_create_demo_project(db, user.id, speaker.id)
        asset = await _get_or_create_demo_asset(db, user.id, project.id)

        # Run ASR if the demo video has not been processed yet. This is the same
        # processor the worker calls for any uploaded video.
        if asset.processing_status != AssetStatus.COMPLETED:
            logger.info("demo_asset_processing", asset_id=str(asset.id))
            asset.processing_status = AssetStatus.PENDING
            await db.commit()
            await process_asset(asset.id)
            # process_asset uses its own session; refresh to read transcript/meta.
            await db.refresh(asset)
            if asset.processing_status != AssetStatus.COMPLETED:
                logger.error(
                    "demo_asset_processing_failed",
                    status=asset.processing_status.value,
                    error=asset.processing_error,
                )
                return

        # Use the language detected by ASR as the generation target language so
        # outputs match the spoken content. Fallback to English if unavailable.
        target_language = (asset.meta or {}).get("language", "en") or "en"
        logger.info(
            "demo_target_language",
            language=target_language,
            duration=asset.duration_seconds,
        )

        # Persist the original prompt just like a real user request would.
        await seed_project_prompt(db, user.id, DEMO_PROJECT_ID, DEMO_USER_MESSAGE)

        clip_count = await _count_clips(db)
        derivative_count = await _count_derivatives(db)

        if clip_count == 0 or derivative_count == 0:
            # Queue and immediately run the real generation orchestrator.
            run = WorkflowRun(
                project_id=DEMO_PROJECT_ID,
                status=WorkflowStatus.PENDING,
                current_step="queued",
                progress=0,
                context={
                    "outputs": ["clips", "post", "quotes", "carousel", "article"],
                    "clip_count": 3,
                    "target_language": target_language,
                    "brand_template_id": str(brand.id),
                    "instruction": DEMO_USER_MESSAGE,
                    "scope": "full",
                    "target_id": None,
                    "operation": "generate",
                    "tone_settings": None,
                },
            )
            db.add(run)
            project.status = ProjectStatus.PROCESSING
            await db.commit()
            await db.refresh(run)

            logger.info("demo_generation_started", run_id=str(run.id))
            await run_generation(run.id)

            # Refresh the run to check success (run_generation uses its own session).
            await db.refresh(run)
            if run.status != WorkflowStatus.COMPLETED:
                logger.error(
                    "demo_generation_failed",
                    run_id=str(run.id),
                    status=run.status.value,
                    error=run.error,
                )
                return

        # Demo clips are queued for rendering automatically by the generation
        # orchestrator (render_status=PENDING). The worker will render them in
        # the background so startup is not blocked waiting for Remotion/Chromium.

        # Log final state.
        final_clips = await _count_clips(db)
        final_derivatives = await _count_derivatives(db)
        logger.info(
            "demo_project_seeded",
            project_id=str(DEMO_PROJECT_ID),
            clips=final_clips,
            derivatives=final_derivatives,
        )
