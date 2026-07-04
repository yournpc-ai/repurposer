"""Background generation orchestration.

Runs the analyzer/script/linkedin/quote agents for a project according to the
requested ``outputs``, tracking progress on a :class:`WorkflowRun`. Designed to
run in a FastAPI ``BackgroundTask`` with its own database session.
"""

import base64
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.clip_agent import clip_agent
from app.agents.content_director import content_director_agent
from app.agents.persona import persona_agent
from app.agents.reviser import reviser_agent
from app.clients.minimax import MiniMaxError, minimax_client
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetType,
    ContentPlan,
    DerivativePlan,
    DerivativeType,
    GenerationContext,
    MediaInput,
    ProjectStatus,
    RenderStatus,
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
from app.services.brand import (
    brand_from_template,
    content_strategy_from_template,
    music_from_mood,
    music_from_template,
)
from app.services.clip_spec import build_clip_spec
from app.services.derivative_dispatch import generate_derivative
from app.services.messages import (
    add_result_refs,
    append_message_marker,
    update_message_meta,
)
from app.services.project_context import (
    collect_materials,
    resolve_clip_for_revision,
    resolve_speaker_and_persona,
)
from app.services.storage import (
    file_to_data_url,
    output_url,
    resolve_file_path,
    save_output,
    stream_url,
)

logger = structlog.get_logger()

def _quote_image_prompt(quote: str, attribution: str, event_name: str | None = None) -> str:
    """Build a visual prompt for MiniMax image-01 to illustrate a quote card."""
    base = (
        "A minimalist, elegant quote card design for social media. "
        "Clean typography centered on a subtle gradient background. "
        "The card prominently displays an inspiring quote. "
        "Modern, professional, no clutter, high contrast readable text. "
    )
    quote_ctx = f'Quote: "{quote}" — {attribution}'
    event_ctx = f" Event context: {event_name}." if event_name else ""
    return base + quote_ctx + event_ctx


async def _save_quote_card_image(
    quote: str,
    attribution: str,
    derivative_id: UUID,
    project: Project,
) -> str | None:
    """Generate and save a quote-card PNG; return the public URL or None on failure."""
    try:
        images = await minimax_client.generate_image(
            prompt=_quote_image_prompt(quote, attribution, project.event_name),
            aspect_ratio="1:1",
            response_format="base64",
        )
        if not images:
            return None
        image_bytes = base64.b64decode(images[0])
        relative_path = await save_output(
            project.id,
            project.user_id,
            f"quote_{derivative_id}.png",
            image_bytes,
        )
        return output_url(relative_path)
    except MiniMaxError as e:
        logger.warning("quote_card_image_failed", error=str(e))
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("quote_card_image_unexpected_error", error=str(e))
        return None

KNOWN_OUTPUTS = ("clips", "linkedin", "quote_cards", "carousel", "summary", "blog")

_OUTPUT_TO_DERIVATIVE_TYPE: dict[str, DerivativeType] = {
    "linkedin": DerivativeType.LINKEDIN_POST,
    "quote_cards": DerivativeType.QUOTE_CARD,
    "carousel": DerivativeType.CAROUSEL,
    "summary": DerivativeType.SUMMARY,
    "blog": DerivativeType.BLOG,
}

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


async def _resolve_or_create_speaker(
    db: AsyncSession,
    project: Project,
    materials: list[str],
) -> Speaker | None:
    """Return the project's speaker, or auto-create one from materials.

    The homepage no longer forces the user to pick/create a speaker. When a
    project has no speaker, we derive a default persona from the transcript so
    the planner still receives style guidance.
    """
    if project.speaker_id:
        result = await db.execute(
            select(Speaker).where(
                Speaker.id == project.speaker_id,
                Speaker.user_id == project.user_id,
            )
        )
        return result.scalar_one_or_none()

    if not materials:
        return None

    trimmed = [m[:20_000] for m in materials if m and m.strip()]
    if not trimmed:
        return None

    try:
        persona = await persona_agent.generate(
            speaker_name=project.title or "Speaker",
            speaker_title=None,
            language=project.language or "en",
            materials=trimmed,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "auto_persona_generation_failed",
            project_id=str(project.id),
            error=str(e),
        )
        return None

    speaker = Speaker(
        user_id=project.user_id,
        name=project.title or "Auto Speaker",
        title=None,
        language=project.language or "en",
        persona=persona.model_dump(),
    )
    db.add(speaker)
    await db.commit()
    await db.refresh(speaker)

    project.speaker_id = speaker.id
    await db.commit()

    logger.info(
        "auto_created_speaker",
        project_id=str(project.id),
        speaker_id=str(speaker.id),
    )
    return speaker


async def _run_targeted_revision(
    db: AsyncSession,
    run: WorkflowRun,
    project: Project,
    scope: str,
    target_id: UUID | None,
    operation: str,
    instruction: str | None,
    message_id: UUID | None,
) -> None:
    """Run a targeted revision/operation on a single clip or derivative.

    Updates the assistant message with progress and result references.
    """
    if target_id is None:
        raise ValueError(f"target_id is required for scope={scope}")

    if scope in ("hook", "clip"):
        clip, current_script, source_segment = await resolve_clip_for_revision(
            db, target_id, project.id
        )
        speaker, persona = await resolve_speaker_and_persona(db, project)

        if message_id:
            await update_message_meta(db, message_id, status="running", current_step=scope)
            await append_message_marker(
                db, message_id, f"Revising {scope}...", "status"
            )

        revised = await reviser_agent.revise_by_instruction(
            script=current_script,
            segment=source_segment,
            instruction=instruction or "Improve this clip",
            persona=persona,
            scope=scope,
        )
        clip.script = revised.model_dump()
        clip.hook = revised.hook
        clip.title_options = revised.title_options
        clip.music_mood = revised.music_mood
        clip.duration = revised.duration_seconds
        await db.commit()

        run.status = WorkflowStatus.COMPLETED
        run.current_step = "done"
        run.progress = 100
        await db.commit()

        if message_id:
            await add_result_refs(db, message_id, clip_ids=[clip.id])
            await update_message_meta(
                db, message_id, status="completed", progress=100, current_step="done"
            )
            await append_message_marker(db, message_id, f"{scope.title()} revised", "status")
        return

    if scope == "render":
        clip = await db.get(Clip, target_id)
        if clip is None or clip.project_id != project.id:
            raise ValueError("Target clip not found")
        if not clip.render_spec:
            raise ValueError("Clip has no render_spec")

        clip.render_status = RenderStatus.PENDING
        clip.render_error = None
        await db.commit()

        run.status = WorkflowStatus.COMPLETED
        run.current_step = "done"
        run.progress = 100
        await db.commit()

        if message_id:
            await add_result_refs(db, message_id, clip_ids=[clip.id])
            await update_message_meta(
                db, message_id, status="completed", progress=100, current_step="done"
            )
            await append_message_marker(
                db, message_id, "Video render queued", "status"
            )
        return

    # Fallback: scope not yet supported as a targeted operation.
    raise ValueError(f"Targeted scope not implemented: {scope}")


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
            scope = ctx.get("scope", "full")
            operation = ctx.get("operation", "regenerate")
            target_id: UUID | None = None
            raw_target_id = ctx.get("target_id")
            if raw_target_id:
                try:
                    target_id = UUID(str(raw_target_id))
                except (ValueError, TypeError):
                    target_id = None
            message_id: UUID | None = None
            raw_message_id = ctx.get("assistant_message_id")
            if raw_message_id:
                try:
                    message_id = UUID(str(raw_message_id))
                except (ValueError, TypeError):
                    message_id = None

            run.status = WorkflowStatus.RUNNING
            run.progress = 0
            run.current_step = "loading"
            await db.commit()

            if message_id:
                await update_message_meta(
                    db,
                    message_id,
                    status="running",
                    progress=0,
                    current_step="loading",
                )
                await append_message_marker(
                    db,
                    message_id,
                    "Starting generation...",
                    "status",
                )

            project = await db.get(Project, run.project_id)
            if project is None:
                raise ValueError("Project not found")

            if scope != "full":
                await _run_targeted_revision(
                    db, run, project, scope, target_id, operation, instruction, message_id
                )
                return

            materials = await collect_materials(db, project.id)
            asset_rows = await db.execute(
                select(Asset).where(Asset.project_id == project.id)
            )
            assets = list(asset_rows.scalars().all())
            media_inputs = _collect_media_inputs(assets)
            if not materials and not media_inputs:
                raise ValueError("No source material to analyze")
            logger.info(
                "generation_materials_collected",
                project_id=str(project.id),
                text_count=len(materials),
                media_count=len(media_inputs),
            )

            # Resolve the project's speaker. If none is assigned, generate a
            # default persona from the materials so the planner still has style
            # guidance. This keeps the homepage UI free of speaker selection.
            speaker = await _resolve_or_create_speaker(db, project, materials)

            # Resolve the brand template early so the planner can use its content
            # strategy (voice/audience/cta/guidelines) when selecting segments.
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
            content_strategy = content_strategy_from_template(bt.config if bt else None)

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

            # Assemble the shared generation context once. All agents receive this
            # same object so that speaker style, brand voice, tone, and user
            # instruction are applied consistently across every output.
            generation_context = GenerationContext(
                speaker_name=speaker.name if speaker else None,
                speaker_title=speaker.title if speaker else None,
                event_name=project.event_name,
                persona=persona,
                tone_settings=tone_settings,
                brand_strategy=content_strategy,
                target_language=target_language,
                instruction=instruction,
            )

            requested_derivative_types = [
                _OUTPUT_TO_DERIVATIVE_TYPE[o]
                for o in outputs
                if o in _OUTPUT_TO_DERIVATIVE_TYPE
            ]

            # Run the Content Director before any generation so that every agent
            # works from the same core thesis, themes, and per-output focus.
            # current_step remains "loading" during planning to preserve the
            # legacy step sequence for frontend polling.
            if message_id:
                await append_message_marker(
                    db, message_id, "Planning content...", "status"
                )
            content_plan: ContentPlan = await content_director_agent.plan(
                materials=materials,
                context=generation_context,
                media_inputs=media_inputs,
                requested_derivatives=requested_derivative_types,
            )

            # Idempotency: clear prior outputs for the requested types so reruns
            # replace rather than accumulate.
            if "clips" in outputs:
                await db.execute(delete(Clip).where(Clip.project_id == project.id))
            if DerivativeType.LINKEDIN_POST in requested_derivative_types:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.LINKEDIN_POST,
                    )
                )
            if DerivativeType.QUOTE_CARD in requested_derivative_types:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.QUOTE_CARD,
                    )
                )
            if DerivativeType.CAROUSEL in requested_derivative_types:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.CAROUSEL,
                    )
                )
            if DerivativeType.SUMMARY in requested_derivative_types:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.SUMMARY,
                    )
                )
            if DerivativeType.BLOG in requested_derivative_types:
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
                if message_id:
                    await update_message_meta(
                        db, message_id, current_step="clips"
                    )
                    await append_message_marker(
                        db, message_id, "Generating clips...", "status"
                    )
                plans = await clip_agent.generate(
                    materials=materials,
                    context=generation_context,
                    content_plan=content_plan,
                    media_inputs=media_inputs,
                    clip_count=clip_count,
                )
                # Bake the chosen brand template into each clip's render_spec so
                # the renderer/preview show it without DB access (see ADR-016).
                brand = brand_from_template(bt.config) if bt is not None else None
                brand_ref = bt.id if bt is not None else None
                cfg = (bt.config or {}) if bt is not None else {}
                aspect = str(cfg.get("aspect", "9:16"))
                # Normalized {x,y} points (or None -> renderer default).
                cap_pos = cfg.get("captionPosition")
                ttl_pos = cfg.get("titlePosition")
                ttl_size_raw = cfg.get("titleSize")
                ttl_size = int(ttl_size_raw) if isinstance(ttl_size_raw, (int, float)) else None
                clip_ids: list[UUID] = []
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
                    clip = Clip(
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
                    db.add(clip)
                    clip_ids.append(clip.id)
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()
                if message_id:
                    await add_result_refs(db, message_id, clip_ids=clip_ids)
                    await update_message_meta(
                        db, message_id, progress=run.progress
                    )
                    await append_message_marker(
                        db, message_id, f"Generated {len(clip_ids)} clips", "status"
                    )

            # Generate each requested derivative in the original output order,
            # preserving the legacy current_step values and progress tracking.
            derivative_step_labels: dict[str, str] = {
                "linkedin": "LinkedIn post",
                "quote_cards": "quote cards",
                "carousel": "carousel",
                "summary": "summary",
                "blog": "blog post",
            }
            for output in outputs:
                if output == "clips":
                    continue
                derivative_type = _OUTPUT_TO_DERIVATIVE_TYPE.get(output)
                if derivative_type is None:
                    continue

                derivative_plan = next(
                    (p for p in content_plan.derivatives if p.derivative_type == derivative_type),
                    None,
                )
                if derivative_plan is None:
                    logger.warning(
                        "missing_derivative_plan",
                        output=output,
                        derivative_type=derivative_type.value,
                    )
                    derivative_plan = DerivativePlan(derivative_type=derivative_type)

                run.current_step = output
                await db.commit()
                label = derivative_step_labels.get(output, output)
                if message_id:
                    await update_message_meta(db, message_id, current_step=output)
                    await append_message_marker(
                        db, message_id, f"Generating {label}...", "status"
                    )

                content = await generate_derivative(
                    derivative_type=derivative_type,
                    materials=materials,
                    context=generation_context,
                    content_plan=content_plan,
                )
                derivative = Derivative(
                    project_id=project.id,
                    type=derivative_type,
                    content=content,
                    language=target_language,
                )
                db.add(derivative)
                await db.commit()

                # Quote cards get a generated PNG for the first quote.
                if derivative_type == DerivativeType.QUOTE_CARD:
                    await db.refresh(derivative)
                    quotes = content.get("quotes", []) if isinstance(content, dict) else []
                    if quotes:
                        first_quote = quotes[0]
                        image_url = await _save_quote_card_image(
                            quote=first_quote.get("quote", ""),
                            attribution=first_quote.get("attribution", ""),
                            derivative_id=derivative.id,
                            project=project,
                        )
                        if image_url:
                            derivative.image_url = image_url
                            await db.commit()

                done += 1
                run.progress = int(done / total * 100)
                await db.commit()
                if message_id:
                    await add_result_refs(db, message_id, derivative_ids=[derivative.id])
                    await update_message_meta(db, message_id, progress=run.progress)
                    await append_message_marker(
                        db, message_id, f"{label.title()} ready", "status"
                    )

            run.status = WorkflowStatus.COMPLETED
            run.current_step = "done"
            run.progress = 100
            if project is not None:
                project.status = ProjectStatus.REVIEW
                project.updated_at = datetime.now(UTC)
            await db.commit()
            if message_id:
                await update_message_meta(
                    db, message_id, status="completed", progress=100, current_step="done"
                )
                await append_message_marker(db, message_id, "All done!", "status")
            logger.info("generation_completed", run_id=str(run_id), outputs=outputs)
        except Exception as e:  # noqa: BLE001 — record any failure on the run
            logger.error("generation_failed", run_id=str(run_id), error=str(e))
            run.status = WorkflowStatus.FAILED
            run.error = str(e)
            await db.commit()
            if message_id:
                await update_message_meta(
                    db, message_id, status="failed", error=str(e)
                )
                await append_message_marker(
                    db, message_id, f"Generation failed: {e}", "error"
                )
