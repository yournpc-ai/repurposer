"""Background generation orchestration.

Runs the analyzer/script/linkedin/quote agents for a project according to the
requested ``outputs``, tracking progress on a :class:`WorkflowRun`. Designed to
run in a FastAPI ``BackgroundTask`` with its own database session.
"""

import mimetypes
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import delete, select

from app.agents.blog import blog_agent
from app.agents.carousel import carousel_agent
from app.agents.linkedin import linkedin_agent
from app.agents.planner import planner_agent
from app.agents.quote_card import quote_card_agent
from app.agents.summary import summary_agent
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetType,
    DerivativeType,
    MediaInput,
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
from app.services.storage import file_to_data_url, resolve_file_path, stream_url

logger = structlog.get_logger()

KNOWN_OUTPUTS = ("clips", "linkedin", "quote_cards", "carousel", "summary", "blog")

# Media snippets above these thresholds are not sent directly to the multimodal
# model; we rely on ASR transcripts / extracted text instead. Limits are
# conservative to avoid huge base64 payloads and model context blow-up.
_MAX_DIRECT_VIDEO_SECONDS = 300  # 5 minutes
_MAX_DIRECT_VIDEO_BYTES = 50 * 1024 * 1024  # 50 MB


def _file_size_bytes(path: Path | None) -> int | None:
    """Return file size in bytes, or None if path is missing/unreadable."""
    if path is None or not path.is_file():
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _media_input_for_image(file_url: str, caption: str | None = None):
    """Build a MediaInput for an image file URL, or None if unreadable."""
    path = resolve_file_path(file_url)
    if path is None:
        return None
    data_url = file_to_data_url(path)
    if data_url is None:
        return None
    from app.models.schemas import MediaInput, MediaInputType

    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    return MediaInput(
        type=MediaInputType.IMAGE,
        mime=mime,
        data_url=data_url,
        caption=caption,
    )


def _media_input_for_video(asset: Asset):
    """Build a MediaInput for a short video, or None if it exceeds safe limits."""
    if asset.type != AssetType.VIDEO or not asset.file_url:
        return None
    duration = asset.duration_seconds or 0
    if duration > _MAX_DIRECT_VIDEO_SECONDS:
        return None
    path = resolve_file_path(asset.file_url)
    size = _file_size_bytes(path)
    if size is None or size > _MAX_DIRECT_VIDEO_BYTES:
        return None
    data_url = file_to_data_url(path)
    if data_url is None:
        return None
    from app.models.schemas import MediaInput, MediaInputType

    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "video/mp4"
    return MediaInput(
        type=MediaInputType.VIDEO,
        mime=mime,
        data_url=data_url,
        caption="A short video clip from the talk. Use it together with the transcript.",
    )


def _collect_media_inputs(assets: list[Asset]) -> list[MediaInput]:
    """Collect multimodal inputs from image/slide/video assets.

    Returns a list of MediaInput objects. AUDIO is intentionally omitted because
    MiniMax M3's audio input support is undocumented; speech stays on the ASR
    transcript path.
    """
    inputs: list[MediaInput] = []
    for asset in assets:
        if asset.type == AssetType.IMAGE and asset.file_url:
            item = _media_input_for_image(str(asset.file_url))
            if item:
                inputs.append(item)
        elif asset.type == AssetType.SLIDES and asset.slide_pages:
            for idx, page_path in enumerate(asset.slide_pages, start=1):
                item = _media_input_for_image(
                    str(page_path),
                    caption=f"Slide {idx} from the talk deck.",
                )
                if item:
                    inputs.append(item)
        elif asset.type == AssetType.VIDEO:
            item = _media_input_for_video(asset)
            if item:
                inputs.append(item)
    return inputs


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
            speaker = None
            if project.speaker_id:
                result = await db.execute(
                    select(Speaker).where(
                        Speaker.id == project.speaker_id,
                        Speaker.user_id == project.user_id,
                    )
                )
                speaker = result.scalar_one_or_none()

            asset_rows = await db.execute(
                select(Asset).where(Asset.project_id == project.id)
            )
            assets = list(asset_rows.scalars().all())
            materials = [
                text
                for a in assets
                if (text := (a.extracted_text or a.transcript))
            ]
            media_inputs = _collect_media_inputs(assets)
            if not materials and not media_inputs:
                raise ValueError("No source material to analyze")
            logger.info(
                "generation_materials_collected",
                project_id=str(project.id),
                text_count=len(materials),
                media_count=len(media_inputs),
            )

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
                plans = await planner_agent.plan(
                    materials=materials,
                    media_inputs=media_inputs,
                    clip_count=clip_count,
                    event_name=project.event_name,
                    target_language=target_language,
                    instruction=instruction,
                    persona=persona.model_dump() if persona is not None else None,
                    tone_settings=tone_settings.model_dump()
                    if tone_settings is not None
                    else None,
                )
                # Bake the chosen brand template into each clip's render_spec so
                # the renderer/preview show it without DB access (see ADR-016).
                # Prefer the template the user selected at generate time; else the
                # most recent (the seeded default guarantees at least one exists).
                bt_id = ctx.get("brand_template_id")
                bt = None
                if bt_id:
                    try:
                        result = await db.execute(
                            select(BrandTemplate).where(
                                BrandTemplate.id == UUID(str(bt_id)),
                                BrandTemplate.user_id == project.user_id,
                            )
                        )
                        bt = result.scalar_one_or_none()
                    except (ValueError, TypeError):
                        bt = None
                if bt is None:
                    bt = (
                        await db.execute(
                            select(BrandTemplate)
                            .where(BrandTemplate.user_id == project.user_id)
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
                for plan in plans.clips[:clip_count]:
                    segment = plan.to_segment()
                    script = plan.to_script()
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
                    instruction=instruction,
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
                    instruction=instruction,
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
                    instruction=instruction,
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
                    instruction=instruction,
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
                    instruction=instruction,
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
