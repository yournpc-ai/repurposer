"""Idempotent demo project seeding.

The demo project lets first-time visitors see a fully populated results page
without uploading their own media. It reuses the default user and a fixed
project UUID so it can be safely re-run on every app startup.

Media files are expected at:
  assets/demo/uploads/projects/{DEMO_PROJECT_ID}/demo_talk.mp4
  assets/demo/outputs/projects/{DEMO_PROJECT_ID}/clip_1.mp4
  assets/demo/outputs/projects/{DEMO_PROJECT_ID}/clip_2.mp4
  assets/demo/outputs/projects/{DEMO_PROJECT_ID}/clip_3.mp4
  assets/demo/outputs/projects/{DEMO_PROJECT_ID}/quote_1.png
  assets/demo/outputs/projects/{DEMO_PROJECT_ID}/quote_2.png

The seed function creates placeholder quote-card PNGs from the app logo if they
do not already exist. Demo video files must be supplied manually (see README).
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select

from app.dependencies.auth import DEFAULT_USER_ID
from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType, DerivativeType, MessageRole, ProjectStatus
from app.models.tables import Asset, BrandTemplate, Clip, Derivative, Message, Project, Speaker, User
from app.services.brand import DEFAULT_BRAND_CONFIG
from app.services.storage import get_project_output_dir, get_project_upload_dir, output_url, stream_url

logger = structlog.get_logger()

DEMO_PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
DEMO_SPEAKER_ID = UUID("22222222-2222-2222-2222-222222222222")
DEMO_BRAND_TEMPLATE_ID = UUID("33333333-3333-3333-3333-333333333333")

DEMO_USER_MESSAGE = (
    "Turn this AI ethics keynote into a LinkedIn post, quote cards, "
    "a multi-language summary, and three short clips."
)

DEMO_LINKEDIN_POST = {
    "content": (
        "AI ethics is not just about regulation—it's about designing systems that "
        "respect human agency from day one.\n\n"
        "Three questions every research team should ask before shipping:\n"
        "1. Who is harmed if this model fails silently?\n"
        "2. Can affected people contest the decision?\n"
        "3. Have we documented the trade-offs in plain language?\n\n"
        "The best technical work embeds accountability by default."
    ),
    "hashtags": ["#AIEthics", "#ResponsibleAI", "#ResearchLeadership"],
}

DEMO_SUMMARY = {
    "tldr": (
        "This keynote argues that AI ethics should be treated as a first-class "
        "engineering constraint, not a post-hoc compliance check."
    ),
    "key_points": [
        "Regulation is necessary but insufficient for trustworthy systems.",
        "Human agency and contestability must be designed in from the start.",
        "Documentation of trade-offs should be written for non-technical audiences.",
        "Research teams benefit from treating ethics as a creative constraint.",
    ],
    "full": (
        "The speaker opens by contrasting two historical framings of technology "
        "risk: reactive regulation after harm, and proactive design that embeds "
        "values. The talk argues that contemporary AI systems are too complex and "
        "too consequential for the former.\n\n"
        "Instead, the speaker proposes three operational principles for research "
        "teams: identify silent-failure harms, build contestability into model "
        "outputs, and document trade-offs in plain language. Each principle is "
        "illustrated with concrete examples from public-sector deployments.\n\n"
        "The closing call to action invites institutions to publish lightweight "
        "ethics impact statements alongside technical papers, turning accountability "
        "into a reproducible habit rather than a one-off review."
    ),
}

DEMO_QUOTES = [
    {
        "quote": "AI ethics is not a compliance checkbox. It is a design constraint.",
        "attribution": "Dr. Elena Rossi",
    },
    {
        "quote": "The hardest failures are the ones that make no sound.",
        "attribution": "Dr. Elena Rossi",
    },
]

DEMO_CLIPS = [
    {
        "hook": "AI ethics is not just about regulation",
        "duration": 37,
        "title_options": ["Regulation is not enough", "Design ethics in"],
        "music_mood": "calm",
    },
    {
        "hook": "Who is harmed if this model fails silently?",
        "duration": 52,
        "title_options": ["Silent failures", "Ask this before shipping"],
        "music_mood": "calm",
    },
    {
        "hook": "The best technical work embeds accountability",
        "duration": 28,
        "title_options": ["Accountability by default", "Engineer for agency"],
        "music_mood": "calm",
    },
]


def _demo_paths() -> tuple[Path, Path]:
    """Return upload and output directories for the demo project."""
    from app.config import settings

    upload_dir = get_project_upload_dir(DEMO_PROJECT_ID, "demo")
    output_dir = get_project_output_dir(DEMO_PROJECT_ID, "demo")
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir, output_dir


def _ensure_quote_placeholders(output_dir: Path) -> None:
    """Copy the web app logo as a placeholder quote-card PNG if none exists."""
    repo_root = Path(__file__).resolve().parents[3]
    logo_path = repo_root / "apps" / "web" / "public" / "logo512.png"
    for idx in range(1, len(DEMO_QUOTES) + 1):
        target = output_dir / f"quote_{idx}.png"
        if not target.exists() and logo_path.exists():
            target.write_bytes(logo_path.read_bytes())


async def seed_demo_project() -> None:
    """Create the demo project and its data if it does not already exist."""
    async with AsyncSessionLocal() as db:
        user = await db.get(User, UUID(DEFAULT_USER_ID))
        if user is None:
            logger.warning("demo_seed_default_user_missing")
            return

        existing = await db.get(Project, DEMO_PROJECT_ID)
        if existing is not None:
            logger.debug("demo_project_already_seeded")
            return

        upload_dir, output_dir = _demo_paths()
        _ensure_quote_placeholders(output_dir)

        # Demo speaker.
        speaker = Speaker(
            id=DEMO_SPEAKER_ID,
            user_id=user.id,
            name="Dr. Elena Rossi",
            title="Professor of AI Ethics, University of Geneva",
            language="en",
            persona={
                "core_values": ["accountability", "human agency", "clarity"],
                "sentence_style": "concise, declarative, academic but accessible",
                "emotional_tone": "rational",
                "typical_hooks": [
                    "AI ethics is not just about regulation",
                    "The hardest failures are silent",
                ],
                "avoid_words": ["leverage", "synergy", "disrupt"],
            },
        )
        db.add(speaker)

        # Demo brand template.
        brand_config = dict(DEFAULT_BRAND_CONFIG)
        brand_config["cta"] = "Read the full keynote →"
        brand_template = BrandTemplate(
            id=DEMO_BRAND_TEMPLATE_ID,
            user_id=user.id,
            name="Demo Brand",
            config=brand_config,
        )
        db.add(brand_template)

        # Demo project.
        project = Project(
            id=DEMO_PROJECT_ID,
            user_id=user.id,
            speaker_id=DEMO_SPEAKER_ID,
            title="Example: AI Ethics Keynote",
            event_name="AI Ethics Summit 2026",
            language="en",
            status=ProjectStatus.COMPLETED,
            tone_snapshot={
                "academic_vs_casual": 0.7,
                "rational_vs_passionate": 0.6,
                "concise_vs_detailed": 0.5,
                "audience": "academic",
            },
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(project)

        # Demo upload asset.
        demo_video_rel = "demo/uploads/projects/11111111-1111-1111-1111-111111111111/demo_talk.mp4"
        asset = Asset(
            user_id=user.id,
            project_id=DEMO_PROJECT_ID,
            type=AssetType.VIDEO,
            file_url=demo_video_rel,
            processing_status=AssetStatus.COMPLETED,
            duration_seconds=480,
            processed_at=datetime.now(UTC),
        )
        db.add(asset)

        # Demo clips.
        for idx, clip_data in enumerate(DEMO_CLIPS, start=1):
            video_rel = f"demo/outputs/projects/{DEMO_PROJECT_ID}/clip_{idx}.mp4"
            clip = Clip(
                project_id=DEMO_PROJECT_ID,
                hook=clip_data["hook"],
                script={
                    "hook": clip_data["hook"],
                    "duration_seconds": clip_data["duration"],
                    "shots": [],
                    "title_options": clip_data["title_options"],
                    "music_mood": clip_data["music_mood"],
                },
                title_options=clip_data["title_options"],
                music_mood=clip_data["music_mood"],
                status="generated",
                video_url=output_url(video_rel),
                duration=clip_data["duration"],
                language="en",
                render_spec={
                    "source": {
                        "asset_id": str(asset.id),
                        "kind": "video",
                        "url": stream_url(demo_video_rel),
                    },
                    "aspect": "9:16",
                    "segments": [],
                    "caption_track": [],
                    "caption_style_preset": "clean-bottom",
                },
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(clip)

        # Demo derivatives.
        derivative_rows = [
            Derivative(
                project_id=DEMO_PROJECT_ID,
                type=DerivativeType.LINKEDIN_POST,
                content=DEMO_LINKEDIN_POST,
                language="en",
                status="generated",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            Derivative(
                project_id=DEMO_PROJECT_ID,
                type=DerivativeType.SUMMARY,
                content=DEMO_SUMMARY,
                language="en",
                status="generated",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ]
        for idx, quote in enumerate(DEMO_QUOTES, start=1):
            image_rel = f"demo/outputs/projects/{DEMO_PROJECT_ID}/quote_{idx}.png"
            derivative_rows.append(
                Derivative(
                    project_id=DEMO_PROJECT_ID,
                    type=DerivativeType.QUOTE_CARD,
                    content={"quotes": [quote]},
                    language="en",
                    image_url=output_url(image_rel),
                    status="generated",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
        for derivative in derivative_rows:
            db.add(derivative)

        # Demo messages.
        user_message = Message(
            project_id=DEMO_PROJECT_ID,
            role=MessageRole.USER,
            content=DEMO_USER_MESSAGE,
            created_at=datetime.now(UTC),
        )
        db.add(user_message)

        assistant_message = Message(
            project_id=DEMO_PROJECT_ID,
            role=MessageRole.ASSISTANT,
            content="Here are the repurposed assets from your keynote.",
            meta={
                "status": "completed",
                "results": {
                    "clip_ids": [],
                    "derivative_ids": [],
                },
            },
            created_at=datetime.now(UTC),
        )
        db.add(assistant_message)

        await db.commit()
        logger.info("demo_project_seeded", project_id=str(DEMO_PROJECT_ID))
