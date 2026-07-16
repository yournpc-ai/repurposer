"""Background generation orchestration.

Runs the content director, clip agent, and derivative agents for a project
according to the requested ``outputs``, tracking progress on a
:class:`WorkflowRun`. Designed to run in the worker process with its own
database session.

Per-output status is recorded in ``run.context["output_status"]`` so the
frontend can render skeletons for each requested output and surface isolated
failures without hiding successful outputs.
"""

import asyncio
import base64
import mimetypes
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
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
    SpeakerContext,
    ToneSettings,
    WorkflowStatus,
)
from app.models.tables import (
    Asset,
    BrandTemplate,
    Clip,
    Derivative,
    Music,
    Project,
    Speaker,
    WorkflowRun,
)
from app.services.brand import (
    brand_from_template,
    music_from_plan,
    resolve_music_ref,
)
from app.services.clip_spec import build_clip_spec
from app.services.derivative_dispatch import generate_derivative
from app.services.project_context import (
    collect_asset_texts,
    resolve_clip_for_revision,
    resolve_speaker,
    speaker_context_from_row,
)
from app.services.storage import (
    download_to_temp,
    file_to_data_url,
    output_url,
    save_output,
    stream_url,
)

logger = structlog.get_logger()

# Serializes concurrent updates to a single WorkflowRun's context so that
# parallel derivative tasks do not overwrite each other's output_status.
_run_context_lock = asyncio.Lock()

KNOWN_OUTPUTS = ("clips", "post", "quotes", "article", "carousel")

_OUTPUT_TO_DERIVATIVE_TYPE: dict[str, DerivativeType] = {
    "post": DerivativeType.POST,
    "quotes": DerivativeType.QUOTES,
    "article": DerivativeType.ARTICLE,
    "carousel": DerivativeType.CAROUSEL,
}

# Legacy output/derivative type names from before the video-first refactor.
# Kept as a runtime safety net for pending WorkflowRuns and old content_plan
# documents that may not have been rewritten by the migration.
_LEGACY_OUTPUT_NAMES: dict[str, str] = {
    "linkedin": "post",
    "linkedin_post": "post",
    "summary": "post",
    "quote_cards": "quotes",
    "quote_card": "quotes",
    "blog": "article",
}


def _normalize_output_name(output: str) -> str:
    """Map legacy output keys to the current output naming."""
    return _LEGACY_OUTPUT_NAMES.get(output, output)


def _normalize_content_plan_types(obj: object) -> object:
    """Recursively rewrite legacy derivative_type values in a content_plan dict."""
    if isinstance(obj, dict):
        return {
            k: (
                _normalize_output_name(v)
                if k == "derivative_type" and isinstance(v, str)
                else _normalize_content_plan_types(v)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_normalize_content_plan_types(item) for item in obj]
    return obj

# Media snippets above these thresholds are not sent directly to the multimodal
# model; we rely on ASR transcripts / extracted text instead. These limits are
# generous (10 min / 200 MB) because the agent layer now falls back to text-only
# automatically when a provider rejects or fails to process a media input, so
# the user still gets results from the transcript even for large files.
_MAX_DIRECT_VIDEO_SECONDS = 600  # 10 minutes
_MAX_DIRECT_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB


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


async def _save_minimax_image(
    project: Project,
    filename: str,
    prompt: str,
    aspect_ratio: str,
    *,
    log_context: dict[str, Any] | None = None,
) -> str | None:
    """Generate an image via MiniMax and save it to project storage.

    Returns the public URL or None on failure. Centralizes the repetitive
    generate_image / base64 decode / save_output / output_url flow so that
    quote cards, clip covers, and future image assets behave consistently.
    """
    log_ctx = log_context or {}
    try:
        images = await minimax_client.generate_image(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            response_format="base64",
        )
        if not images:
            return None
        image_bytes = base64.b64decode(images[0])
        relative_path = await save_output(
            project.id,
            project.user_id,
            filename,
            image_bytes,
        )
        return output_url(relative_path)
    except MiniMaxError as e:
        logger.warning("minimax_image_failed", error=str(e), **log_ctx)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("minimax_image_unexpected_error", error=str(e), **log_ctx)
        return None


async def _save_quote_card_image(
    quote: str,
    attribution: str,
    derivative_id: UUID,
    project: Project,
) -> str | None:
    """Generate and save a quote-card PNG; return the public URL or None on failure.

    The filename carries a timestamp so a regeneration never overwrites the
    object a browser may have cached under the previous URL.
    """
    return await _save_minimax_image(
        project,
        f"quote_{derivative_id}-{int(time.time())}.png",
        _quote_image_prompt(quote, attribution, project.event_name),
        "1:1",
        log_context={"derivative_id": str(derivative_id), "kind": "quote_card"},
    )


async def _generate_clip_cover_image(clip: Clip, project: Project) -> str | None:
    """Generate a vertical cover image for a clip on demand.

    Returns the public URL or None on failure. The image is intentionally
    generated only when requested by the UI to avoid paying image-generation
    costs for every clip.
    """
    prompt = (
        "A minimalist, elegant vertical cover image for a short knowledge video. "
        "Clean composition with subtle depth, professional typography-ready background, "
        "no text, no UI, no clutter. Suitable as a 9:16 video thumbnail. "
    )
    context_parts = [f"Topic: {clip.topic}"] if clip.topic else []
    if clip.title:
        context_parts.append(f"Title: {clip.title}")
    if context_parts:
        prompt += " ".join(context_parts)

    return await _save_minimax_image(
        project,
        f"cover_{clip.id}-{int(time.time())}.png",
        prompt,
        "9:16",
        log_context={"clip_id": str(clip.id), "kind": "clip_cover"},
    )


def _file_size_bytes(path: Path | None) -> int | None:
    """Return file size in bytes, or None if path is missing/unreadable."""
    if path is None or not path.is_file():
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


async def _media_input_for_image(file_url: str, caption: str | None = None):
    """Build a MediaInput for an image file URL, or None if unreadable."""
    path = await download_to_temp(file_url)
    if path is None:
        return None
    try:
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
    finally:
        path.unlink(missing_ok=True)


async def _media_input_for_video(asset: Asset):
    """Build a MediaInput for a short video, or None if it exceeds safe limits."""
    if asset.type != AssetType.VIDEO or not asset.file_url:
        return None
    duration = asset.duration_seconds or 0
    if duration > _MAX_DIRECT_VIDEO_SECONDS:
        return None

    path = await download_to_temp(asset.file_url)
    if path is None:
        return None
    try:
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
    finally:
        path.unlink(missing_ok=True)


async def collect_asset_media(assets: list[Asset]) -> list[MediaInput]:
    """Collect multimodal inputs from image/slide/video assets.

    Returns a list of MediaInput objects. AUDIO is intentionally omitted because
    MiniMax M3's audio input support is undocumented; speech stays on the ASR
    transcript path.
    """
    inputs: list[MediaInput] = []
    for asset in assets:
        if asset.type == AssetType.IMAGE and asset.file_url:
            item = await _media_input_for_image(str(asset.file_url))
            if item:
                inputs.append(item)
        elif asset.type == AssetType.SLIDES and asset.slide_pages:
            for idx, page_path in enumerate(asset.slide_pages, start=1):
                item = await _media_input_for_image(
                    str(page_path),
                    caption=f"Slide {idx} from the talk deck.",
                )
                if item:
                    inputs.append(item)
        elif asset.type == AssetType.VIDEO:
            item = await _media_input_for_video(asset)
            if item:
                inputs.append(item)
    return inputs


def _truncate(value: str | None, max_len: int) -> str | None:
    """Truncate a string to fit a SQL column, returning None for empty values."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[:max_len]


async def _resolve_or_create_speaker(
    db: AsyncSession,
    project: Project,
    asset_texts: list[str],
) -> Speaker | None:
    """Return the project's speaker, or auto-create one from source texts.

    The homepage no longer forces the user to pick/create a speaker. When a
    project has no speaker, we derive a default persona and content memory
    (voice/audience/guidelines/cta) from the transcript so the content director
    and clip agent receive style guidance.
    """
    if project.speaker_id:
        result = await db.execute(
            select(Speaker).where(
                Speaker.id == project.speaker_id,
                Speaker.user_id == project.user_id,
            )
        )
        return result.scalar_one_or_none()

    if not asset_texts:
        return None

    trimmed = [t[:20_000] for t in asset_texts if t and t.strip()]
    if not trimmed:
        return None

    try:
        memory = await persona_agent.generate(
            speaker_name=project.title or "Speaker",
            speaker_title=None,
            language=project.language or "en",
            asset_texts=trimmed,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "auto_speaker_extraction_failed",
            project_id=str(project.id),
            error=str(e),
        )
        return None

    speaker = Speaker(
        user_id=project.user_id,
        name=project.title or "Auto Speaker",
        title=None,
        language=project.language or "en",
        core_values=memory.core_values or [],
        favorite_metaphors=memory.favorite_metaphors or [],
        sentence_style=_truncate(memory.sentence_style, 255) or "",
        emotional_tone=memory.emotional_tone or "rational",
        typical_hooks=memory.typical_hooks or [],
        avoid_words=memory.avoid_words or [],
        voice=_truncate(memory.voice, 255),
        audience=_truncate(memory.audience, 255),
        guidelines=memory.guidelines,
        cta=_truncate(memory.cta, 512),
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


def _speaker_context(speaker: Speaker | None) -> SpeakerContext | None:
    """Build a SpeakerContext from a Speaker row for generation agents."""
    return speaker_context_from_row(speaker)


def _init_output_status(outputs: list[str]) -> dict[str, dict[str, Any]]:
    """Create the per-output tracking structure stored in run.context."""
    return {
        output: {"status": "pending", "progress": 0, "error": None}
        for output in outputs
    }


def _compute_progress(output_status: dict[str, dict[str, Any]]) -> int:
    """Calculate overall progress from per-output statuses."""
    if not output_status:
        return 100
    completed = sum(
        1 for s in output_status.values() if s.get("status") == "completed"
    )
    return int(completed / len(output_status) * 100)


def _first_active_output(
    output_status: dict[str, dict[str, Any]],
) -> str | None:
    """Return the first output still running/pending, or None if all done."""
    for output, status in output_status.items():
        if status.get("status") in ("running", "pending"):
            return output
    return None


async def _update_run_output_status(
    run_id: UUID,
    output_status_update: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]] | None:
    """Atomically merge per-output updates into the run context.

    Uses a module-level lock so parallel derivative tasks do not race when
    updating the shared ``output_status`` dict.

    Returns the merged output_status dict, or None if the run is missing.
    """
    async with _run_context_lock:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is None:
                return None
            ctx = run.context or {}
            output_status = ctx.get("output_status", {})
            for output, update in output_status_update.items():
                existing = output_status.get(output, {})
                existing.update(update)
                output_status[output] = existing
            ctx["output_status"] = output_status
            run.context = ctx
            run.progress = _compute_progress(output_status)
            active = _first_active_output(output_status)
            if active:
                run.current_step = active
            else:
                run.current_step = "done"
            await db.commit()
            return output_status


async def _run_targeted_revision(
    db: AsyncSession,
    run: WorkflowRun,
    project: Project,
    scope: str,
    target_id: UUID | None,
    operation: str,
    instruction: str | None,
) -> None:
    """Run a targeted revision/operation on a single clip or derivative."""
    if target_id is None:
        raise ValueError(f"target_id is required for scope={scope}")

    if scope in ("hook", "clip"):
        clip, source_segment = await resolve_clip_for_revision(
            db, target_id, project.id
        )
        speaker = await resolve_speaker(db, project)

        revised = await reviser_agent.revise_by_instruction(
            clip_hook=clip.hook,
            clip_duration=clip.duration,
            clip_title_options=clip.title_options or [],
            clip_music_mood=clip.music_mood,
            segment=source_segment,
            instruction=instruction or "Improve this clip",
            speaker=_speaker_context(speaker),
            scope=scope,
        )
        clip.hook = revised.hook
        clip.title_options = revised.title_options
        clip.music_mood = revised.music_mood
        clip.duration = revised.duration_seconds
        clip.workflow_run_id = run.id
        await db.commit()

        run.status = WorkflowStatus.COMPLETED
        run.current_step = "done"
        run.progress = 100
        await db.commit()
        return

    if scope == "render":
        clip = await db.get(Clip, target_id)
        if clip is None or clip.project_id != project.id:
            raise ValueError("Target clip not found")
        if not clip.render_spec:
            raise ValueError("Clip has no render_spec")

        clip.render_status = RenderStatus.PENDING
        clip.render_error = None
        clip.workflow_run_id = run.id
        await db.commit()

        run.status = WorkflowStatus.COMPLETED
        run.current_step = "done"
        run.progress = 100
        await db.commit()
        return

    if scope == "derivative":
        derivative = await db.get(Derivative, target_id)
        if derivative is None or derivative.project_id != project.id:
            raise ValueError("Target derivative not found")

        asset_texts = await collect_asset_texts(db, project.id)
        speaker = await resolve_speaker(db, project)
        target_language = run.context.get("target_language", derivative.language or "en")

        context = GenerationContext(
            speaker=_speaker_context(speaker),
            event_name=project.event_name,
            tone_settings=None,
            target_language=target_language,
            instruction=instruction,
        )
        if project.content_plan:
            normalized_plan = _normalize_content_plan_types(project.content_plan)
            content_plan = ContentPlan.model_validate(normalized_plan)
            if normalized_plan != project.content_plan:
                project.content_plan = normalized_plan
            # Ensure the requested derivative has guidance in the persisted plan.
            if not any(p.derivative_type == derivative.type for p in content_plan.derivatives):
                content_plan.derivatives.append(
                    DerivativePlan(
                        derivative_type=derivative.type,
                        focus="Regenerate this derivative faithfully to the source material",
                    )
                )
        else:
            content_plan = ContentPlan(
                core_thesis="Regenerate this derivative faithfully to the source material",
                derivatives=[
                    DerivativePlan(
                        derivative_type=derivative.type,
                        focus="Regenerate this derivative faithfully to the source material",
                    )
                ],
            )

        try:
            derivative.content = await generate_derivative(
                derivative_type=derivative.type,
                asset_texts=asset_texts,
                context=context,
                content_plan=content_plan,
            )
        except MiniMaxError as e:
            raise ValueError(f"Derivative generation failed: {e}") from e

        derivative.language = target_language
        derivative.status = "generated"
        derivative.updated_at = datetime.now(UTC)
        derivative.workflow_run_id = run.id
        await db.commit()

        run.status = WorkflowStatus.COMPLETED
        run.current_step = "done"
        run.progress = 100
        await db.commit()
        return

    # Fallback: scope not yet supported as a targeted operation.
    raise ValueError(f"Targeted scope not implemented: {scope}")


async def _generate_derivative_with_retry(
    derivative_type: DerivativeType,
    asset_texts: list[str],
    context: GenerationContext,
    content_plan: ContentPlan,
) -> dict:
    """Generate a derivative, retrying once on failure."""
    try:
        return await generate_derivative(
            derivative_type=derivative_type,
            asset_texts=asset_texts,
            context=context,
            content_plan=content_plan,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "derivative_auto_retry",
            derivative_type=derivative_type.value,
            error=str(e),
        )
        return await generate_derivative(
            derivative_type=derivative_type,
            asset_texts=asset_texts,
            context=context,
            content_plan=content_plan,
        )


async def _run_derivative_task(
    run_id: UUID,
    project_id: UUID,
    user_id: UUID,
    output: str,
    derivative_type: DerivativeType,
    asset_texts: list[str],
    generation_context: GenerationContext,
    content_plan: ContentPlan,
    target_language: str,
    event_name: str | None,
) -> None:
    """Generate and persist one derivative, updating per-output status.

    Each derivative task owns its database session so that generation agents can
    run concurrently. The shared run context update is serialized via an
    asyncio lock inside ``_update_run_output_status``.
    """

    await _update_run_output_status(
        run_id,
        {output: {"status": "running", "progress": 0, "error": None}},
    )

    try:
        content = await _generate_derivative_with_retry(
            derivative_type=derivative_type,
            asset_texts=asset_texts,
            context=generation_context,
            content_plan=content_plan,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(
            "derivative_failed_after_retry",
            run_id=str(run_id),
            output=output,
            derivative_type=derivative_type.value,
            error=str(e),
        )
        await _update_run_output_status(
            run_id,
            {output: {"status": "failed", "progress": 0, "error": str(e)}},
        )
        return

    async with AsyncSessionLocal() as db:
        derivative = Derivative(
            project_id=project_id,
            workflow_run_id=run_id,
            type=derivative_type,
            content=content,
            language=target_language,
        )
        db.add(derivative)
        await db.commit()

        # Quote cards get a generated PNG for the first quote.
        if derivative_type == DerivativeType.QUOTES:
            await db.refresh(derivative)
            project = await db.get(Project, project_id)
            quotes = content.get("quotes", []) if isinstance(content, dict) else []
            if quotes and project is not None:
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

    await _update_run_output_status(
        run_id,
        {output: {"status": "completed", "progress": 100, "error": None}},
    )


async def _run_clips_task(
    db: AsyncSession,
    run: WorkflowRun,
    project: Project,
    asset_texts: list[str],
    assets: list[Asset],
    generation_context: GenerationContext,
    content_plan: ContentPlan,
    clip_count: int,
    bt: BrandTemplate | None,
    brand_music_id: str | None,
) -> None:
    """Generate clips, with one auto-retry, and update per-output status."""
    await _update_run_output_status(
        run.id,
        {"clips": {"status": "running", "progress": 0, "error": None}},
    )

    # Render source selection (docs/VIDEO_EDITOR.md §4).
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

    try:
        music_rows = (
            await db.execute(
                select(Music)
                .where(Music.is_public.is_(True))
                .order_by(Music.created_at.desc())
            )
        ).scalars().all()
        music_pieces: list[dict[str, str]] = [
            {
                "id": str(m.id),
                "mood": str(m.mood),
                "title": str(m.title),
            }
            for m in music_rows
        ]

        plans = await clip_agent.generate(
            asset_texts=asset_texts,
            context=generation_context,
            content_plan=content_plan,
            asset_media=await collect_asset_media(assets),
            clip_count=clip_count,
            source_words=(
                (render_source.meta or {}).get("words")
                if render_source is not None
                else None
            ),
            music_pieces=music_pieces,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("clip_agent_auto_retry", error=str(e))
        try:
            music_rows = (
                await db.execute(
                    select(Music)
                    .where(Music.is_public.is_(True))
                    .order_by(Music.created_at.desc())
                )
            ).scalars().all()
            music_pieces = [
                {
                    "id": str(m.id),
                    "mood": str(m.mood),
                    "title": str(m.title),
                }
                for m in music_rows
            ]
            plans = await clip_agent.generate(
                asset_texts=asset_texts,
                context=generation_context,
                content_plan=content_plan,
                asset_media=await collect_asset_media(assets),
                clip_count=clip_count,
                source_words=(
                    (render_source.meta or {}).get("words")
                    if render_source is not None
                    else None
                ),
                music_pieces=music_pieces,
            )
        except Exception as e2:  # noqa: BLE001
            logger.error(
                "clip_agent_failed_after_retry",
                run_id=str(run.id),
                error=str(e2),
            )
            await _update_run_output_status(
                run.id,
                {"clips": {"status": "failed", "progress": 0, "error": str(e2)}},
            )
            return

    brand = brand_from_template(bt.config) if bt is not None else None
    brand_ref = bt.id if bt is not None else None
    cfg = (bt.config or {}) if bt is not None else {}
    aspect = str(cfg.get("aspect", "9:16"))
    cap_pos = cfg.get("captionPosition")
    cap_style_raw = cfg.get("captionStylePreset")
    cap_style = cap_style_raw if isinstance(cap_style_raw, str) else "clean-bottom"
    ttl_pos = cfg.get("titlePosition")
    ttl_size_raw = cfg.get("titleSize")
    ttl_size = int(ttl_size_raw) if isinstance(ttl_size_raw, (int, float)) else None
    ttl_enabled_raw = cfg.get("titleEnabled")
    ttl_enabled = True if ttl_enabled_raw is None else bool(ttl_enabled_raw)

    for plan in plans.clips[:clip_count]:
        segment = plan.to_segment()
        music = await music_from_plan(db, plan, bt.config if bt else None)
        # Clip agent decides whether burned-in captions make sense for this segment;
        # the brand template only supplies the default.
        brand_caption_enabled = brand.caption_enabled if brand is not None else True
        caption_enabled = (
            plan.caption_enabled
            if getattr(plan, "caption_enabled", None) is not None
            else brand_caption_enabled
        )
        spec = (
            build_clip_spec(
                render_source,
                segment,
                generation_context.target_language,
                kind=render_kind,
                aspect=aspect,
                caption_position=cap_pos,
                caption_enabled=caption_enabled,
                caption_style_preset=cap_style,
                title_size=ttl_size,
                title_position=ttl_pos,
                title_enabled=ttl_enabled,
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
            workflow_run_id=run.id,
            hook=plan.hook,
            title_options=plan.title_options or ([plan.title] if plan.title else []),
            music_mood=plan.music_mood,
            duration=plan.duration_seconds,
            language=generation_context.target_language,
            source_segment=segment.model_dump(),
            render_spec=spec.model_dump(mode="json") if spec else None,
            render_status=RenderStatus.PENDING if spec else None,
            title=plan.title or None,
            description=plan.description or None,
            hashtags=plan.hashtags or None,
            topic=plan.topic or None,
            start_time=plan.start_seconds,
            end_time=plan.end_seconds,
        )
        db.add(clip)
    await db.commit()

    await _update_run_output_status(
        run.id,
        {"clips": {"status": "completed", "progress": 100, "error": None}},
    )


async def _delete_prior_outputs(
    db: AsyncSession,
    project_id: UUID,
    outputs: list[str],
    requested_derivative_types: list[DerivativeType],
) -> None:
    """Idempotency: clear prior outputs for the requested types."""
    if "clips" in outputs:
        await db.execute(delete(Clip).where(Clip.project_id == project_id))
    for derivative_type in requested_derivative_types:
        await db.execute(
            delete(Derivative).where(
                Derivative.project_id == project_id,
                Derivative.type == derivative_type,
            )
        )
    await db.commit()


async def run_generation(run_id: UUID) -> None:
    """Execute a queued generation run. Never raises — failures land on the run."""
    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, run_id)
        if run is None:
            logger.warning("generation_run_missing", run_id=str(run_id))
            return

        try:
            ctx = run.context or {}
            outputs = [
                _normalize_output_name(o)
                for o in ctx.get("outputs", ["clips"])
                if _normalize_output_name(o) in KNOWN_OUTPUTS
            ]
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

            run.status = WorkflowStatus.RUNNING
            run.progress = 0
            run.current_step = "analyze"
            run.context = {**ctx, "output_status": _init_output_status(outputs)}
            await db.commit()

            project = await db.get(Project, run.project_id)
            if project is None:
                raise ValueError("Project not found")

            if scope != "full":
                await _run_targeted_revision(
                    db, run, project, scope, target_id, operation, instruction
                )
                return

            asset_texts = await collect_asset_texts(db, project.id)
            asset_rows = await db.execute(
                select(Asset).where(Asset.project_id == project.id)
            )
            assets = list(asset_rows.scalars().all())
            asset_media = collect_asset_media(assets)
            if not asset_texts and not asset_media:
                raise ValueError("No source material to analyze")
            logger.info(
                "generation_asset_inputs_collected",
                project_id=str(project.id),
                text_count=len(asset_texts),
                media_count=len(asset_media),
            )

            speaker = await _resolve_or_create_speaker(db, project, asset_texts)

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

            brand_music_id: str | None = None
            if bt is not None:
                bt_cfg: dict[str, Any] = bt.config or {}
                brand_piece = await resolve_music_ref(
                    db, bt_cfg.get("musicId") or bt_cfg.get("musicMood")
                )
                brand_music_id = str(brand_piece.id) if brand_piece is not None else None

            generation_context = GenerationContext(
                speaker=_speaker_context(speaker),
                event_name=project.event_name,
                tone_settings=tone_settings,
                target_language=target_language,
                instruction=instruction,
                brand_music_id=brand_music_id,
            )

            run.current_step = "plan"
            await db.commit()

            requested_derivative_types = [
                _OUTPUT_TO_DERIVATIVE_TYPE[o]
                for o in outputs
                if o in _OUTPUT_TO_DERIVATIVE_TYPE
            ]

            # Reuse a persisted plan when available (simple V1 reuse); otherwise
            # run the Content Director once and persist the result.
            if project.content_plan:
                normalized_plan = _normalize_content_plan_types(project.content_plan)
                content_plan = ContentPlan.model_validate(normalized_plan)
                if normalized_plan != project.content_plan:
                    project.content_plan = normalized_plan
                logger.info(
                    "content_plan_reused",
                    project_id=str(project.id),
                )
            else:
                content_plan = await content_director_agent.plan(
                    asset_texts=asset_texts,
                    context=generation_context,
                    asset_media=asset_media,
                    requested_derivatives=requested_derivative_types,
                )
                project.content_plan = content_plan.model_dump(mode="json")
                await db.commit()

            run.current_step = "prepare"
            await db.commit()

            # Clear prior outputs for requested types.
            await _delete_prior_outputs(
                db, project.id, outputs, requested_derivative_types
            )

            # Run clips first (when requested). They are independent of derivatives.
            if "clips" in outputs:
                await _run_clips_task(
                    db,
                    run,
                    project,
                    asset_texts,
                    assets,
                    generation_context,
                    content_plan,
                    clip_count,
                    bt,
                    brand_music_id,
                )

            # Run all requested derivatives concurrently.
            derivative_outputs = [
                output for output in outputs if output in _OUTPUT_TO_DERIVATIVE_TYPE
            ]
            if derivative_outputs:
                await asyncio.gather(
                    *[
                        _run_derivative_task(
                            run_id=run.id,
                            project_id=project.id,
                            user_id=project.user_id,
                            output=output,
                            derivative_type=_OUTPUT_TO_DERIVATIVE_TYPE[output],
                            asset_texts=asset_texts,
                            generation_context=generation_context,
                            content_plan=content_plan,
                            target_language=target_language,
                            event_name=project.event_name,
                        )
                        for output in derivative_outputs
                    ]
                )

            # Refresh run state after parallel work and finalize.
            await db.refresh(run)
            output_status = (run.context or {}).get("output_status", {})
            failed_outputs = [
                o for o, s in output_status.items() if s.get("status") == "failed"
            ]

            if failed_outputs and len(failed_outputs) == len(output_status):
                # All outputs failed: mark run failed.
                run.status = WorkflowStatus.FAILED
                run.error = "All outputs failed"
                run.current_step = "done"
                run.progress = 100
            else:
                run.status = WorkflowStatus.COMPLETED
                run.error = None
                run.current_step = "done"
                run.progress = 100
                project.status = ProjectStatus.REVIEW
                project.updated_at = datetime.now(UTC)

            await db.commit()
            logger.info(
                "generation_completed",
                run_id=str(run_id),
                outputs=outputs,
                failed=failed_outputs,
            )
        except Exception as e:  # noqa: BLE001 — record any failure on the run
            logger.error("generation_failed", run_id=str(run_id), error=str(e))
            run.status = WorkflowStatus.FAILED
            run.error = str(e)
            await db.commit()
