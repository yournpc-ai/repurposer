"""Background generation orchestration.

Runs the analyzer/script/linkedin/quote agents for a project according to the
requested ``outputs``, tracking progress on a :class:`WorkflowRun`. Designed to
run in a FastAPI ``BackgroundTask`` with its own database session.
"""

from uuid import UUID

import structlog
from sqlalchemy import delete, select

from app.agents.analyzer import analyzer_agent
from app.agents.blog import blog_agent
from app.agents.carousel import carousel_agent
from app.agents.linkedin import linkedin_agent
from app.agents.quote_card import quote_card_agent
from app.agents.script import script_agent
from app.agents.summary import summary_agent
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetType,
    DerivativeType,
    ProjectStatus,
    SpeakerPersona,
    ToneSettings,
    WorkflowStatus,
)
from app.models.tables import (
    Asset,
    BrandTemplate,
    Clip,
    Derivative,
    Project,
    Speaker,
    WorkflowRun,
)
from app.services.brand import brand_from_template, music_from_mood, music_from_template
from app.services.clip_spec import build_clip_spec
from app.services.storage import stream_url

logger = structlog.get_logger()

KNOWN_OUTPUTS = ("clips", "linkedin", "quote_cards", "carousel", "summary", "blog")


async def run_generation(run_id: UUID) -> None:
    """Execute a queued generation run. Never raises — failures land on the run."""
    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, run_id)
        if run is None:
            logger.warning("generation_run_missing", run_id=str(run_id))
            return

        try:
            ctx = run.context or {}
            outputs = [o for o in ctx.get("outputs", ["clips"]) if o in KNOWN_OUTPUTS]
            if not outputs:
                outputs = ["clips"]
            clip_count = int(ctx.get("clip_count", 3))
            target_language = ctx.get("target_language", "en")
            instruction = ctx.get("instruction")
            tone_raw = ctx.get("tone_settings")
            tone_settings = ToneSettings.model_validate(tone_raw) if tone_raw else None

            run.status = WorkflowStatus.RUNNING
            run.progress = 0
            run.current_step = "loading"
            await db.commit()

            project = await db.get(Project, run.project_id)
            if project is None:
                raise ValueError("Project not found")
            speaker = (
                await db.get(Speaker, project.speaker_id)
                if project.speaker_id
                else None
            )

            asset_rows = await db.execute(
                select(Asset).where(Asset.project_id == project.id)
            )
            assets = list(asset_rows.scalars().all())
            materials = [
                text
                for a in assets
                if (text := (a.extracted_text or a.transcript))
            ]
            if not materials:
                raise ValueError("No source material to analyze")

            # Render source selection (docs/VIDEO_EDITOR.md §4), in priority:
            #   1. on-camera VIDEO (with ASR words)      -> video clip
            #   2. else speech AUDIO (with ASR words)    -> stills audiogram
            #   3. else any backing visual (slides/image) -> stills, no audio
            # None of the above -> clips carry no render_spec (text assets only).
            # Backing visuals = rendered slide-deck pages first (the talk's own
            # narrative), then uploaded photos.
            def _has_words(a: Asset) -> bool:
                return bool(a.file_url and (a.meta or {}).get("words"))

            slide_page_urls = [
                u
                for a in assets
                if a.type == AssetType.SLIDES
                for p in (a.slide_pages or [])
                if (u := stream_url(p))
            ]
            image_urls = [
                u
                for a in assets
                if a.type == AssetType.IMAGE and (u := stream_url(a.file_url))
            ]
            still_images = slide_page_urls + image_urls
            source_video = next(
                (a for a in assets if a.type == AssetType.VIDEO and _has_words(a)),
                None,
            )
            source_audio = next(
                (a for a in assets if a.type == AssetType.AUDIO and _has_words(a)),
                None,
            )
            first_visual = next(
                (
                    a
                    for a in assets
                    if a.type in (AssetType.SLIDES, AssetType.IMAGE) and a.file_url
                ),
                None,
            )
            if source_video is not None:
                render_source, render_kind = source_video, "video"
            elif source_audio is not None:
                render_source, render_kind = source_audio, "stills"
            elif first_visual is not None and still_images:
                render_source, render_kind = first_visual, "stills"
            else:
                render_source, render_kind = None, "video"

            persona = (
                SpeakerPersona.model_validate(speaker.persona)
                if speaker is not None and speaker.persona
                else None
            )

            # Idempotency: clear prior outputs for the requested types so reruns
            # replace rather than accumulate.
            if "clips" in outputs:
                await db.execute(delete(Clip).where(Clip.project_id == project.id))
            if "linkedin" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.LINKEDIN_POST,
                    )
                )
            if "quote_cards" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.QUOTE_CARD,
                    )
                )
            if "carousel" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.CAROUSEL,
                    )
                )
            if "summary" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.SUMMARY,
                    )
                )
            if "blog" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.BLOG,
                    )
                )
            await db.commit()

            total = len(outputs)
            done = 0

            if "clips" in outputs:
                run.current_step = "clips"
                await db.commit()
                analysis = await analyzer_agent.analyze(
                    materials=materials,
                    clip_count=clip_count,
                    event_name=project.event_name,
                    target_language=target_language,
                    instruction=instruction,
                )
                # Bake the chosen brand template into each clip's render_spec so
                # the renderer/preview show it without DB access (see ADR-016).
                # Prefer the template the user selected at generate time; else the
                # most recent (the seeded default guarantees at least one exists).
                bt_id = ctx.get("brand_template_id")
                bt = None
                if bt_id:
                    try:
                        bt = await db.get(BrandTemplate, UUID(str(bt_id)))
                    except (ValueError, TypeError):
                        bt = None
                if bt is None:
                    bt = (
                        await db.execute(
                            select(BrandTemplate)
                            .order_by(BrandTemplate.created_at.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                brand = brand_from_template(bt.config) if bt is not None else None
                brand_ref = bt.id if bt is not None else None
                cfg = (bt.config or {}) if bt is not None else {}
                aspect = str(cfg.get("aspect", "9:16"))
                # Normalized {x,y} points (or None -> renderer default).
                cap_pos = cfg.get("captionPosition")
                ttl_pos = cfg.get("titlePosition")
                ttl_size_raw = cfg.get("titleSize")
                ttl_size = int(ttl_size_raw) if isinstance(ttl_size_raw, (int, float)) else None
                for segment in analysis.segments[:clip_count]:
                    script = await script_agent.generate(
                        segment=segment,
                        persona=persona,
                        tone_settings=tone_settings,
                        target_audience=analysis.target_audience,
                        target_language=target_language,
                        instruction=instruction,
                    )
                    # Music: a brand template (if any) is the source of truth —
                    # respect it fully, including an explicit "off". With no
                    # template, fall back to the clip's own mood suggestion so a
                    # generated clip still carries music (track file permitting).
                    music = (
                        music_from_template(bt.config)
                        if bt is not None
                        else music_from_mood(script.music_mood)
                    )
                    # render_spec = the actual render contract (None for
                    # text-only projects). script stays as the AI suggestion.
                    spec = (
                        build_clip_spec(
                            render_source,
                            segment,
                            target_language,
                            kind=render_kind,
                            aspect=aspect,
                            caption_position=cap_pos,
                            title_size=ttl_size,
                            title_position=ttl_pos,
                            image_urls=still_images if render_kind == "stills" else None,
                            brand=brand,
                            music=music,
                            brand_ref=brand_ref,
                        )
                        if render_source is not None
                        else None
                    )
                    db.add(
                        Clip(
                            project_id=project.id,
                            hook=script.hook,
                            script=script.model_dump(),
                            title_options=script.title_options,
                            music_mood=script.music_mood,
                            duration=script.duration_seconds,
                            language=target_language,
                            source_segment=segment.model_dump(),
                            render_spec=spec.model_dump(mode="json") if spec else None,
                        )
                    )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "linkedin" in outputs:
                run.current_step = "linkedin"
                await db.commit()
                post = await linkedin_agent.generate(
                    materials=materials,
                    persona=persona,
                    event_name=project.event_name,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.LINKEDIN_POST,
                        content=post.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "quote_cards" in outputs:
                run.current_step = "quote_cards"
                await db.commit()
                result = await quote_card_agent.generate(
                    materials=materials,
                    speaker_name=speaker.name if speaker is not None else "",
                    speaker_title=speaker.title if speaker is not None else "",
                    event_name=project.event_name,
                    count=3,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.QUOTE_CARD,
                        content=result.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "carousel" in outputs:
                run.current_step = "carousel"
                await db.commit()
                carousel = await carousel_agent.generate(
                    materials=materials,
                    speaker_name=speaker.name if speaker is not None else "",
                    speaker_title=speaker.title if speaker is not None else "",
                    event_name=project.event_name,
                    count=6,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.CAROUSEL,
                        content=carousel.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "summary" in outputs:
                run.current_step = "summary"
                await db.commit()
                summary = await summary_agent.generate(
                    materials=materials,
                    persona=persona,
                    event_name=project.event_name,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.SUMMARY,
                        content=summary.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "blog" in outputs:
                run.current_step = "blog"
                await db.commit()
                blog = await blog_agent.generate(
                    materials=materials,
                    persona=persona,
                    event_name=project.event_name,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.BLOG,
                        content=blog.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            run.status = WorkflowStatus.COMPLETED
            run.current_step = "done"
            run.progress = 100
            if project is not None:
                project.status = ProjectStatus.REVIEW
            await db.commit()
            logger.info("generation_completed", run_id=str(run_id), outputs=outputs)
        except Exception as e:  # noqa: BLE001 — record any failure on the run
            logger.error("generation_failed", run_id=str(run_id), error=str(e))
            run.status = WorkflowStatus.FAILED
            run.error = str(e)
            await db.commit()
