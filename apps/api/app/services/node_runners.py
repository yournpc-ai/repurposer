"""RunPlan node runners: one runner per node kind (RunPlan Phase 1).

Each runner is the direct transplant of a ``generation.py`` code path onto the
plan_nodes graph (docs/tasks/runplan-phase1-implementation.md §4 mapping
table). Signature is uniform: ``(db, run, node, project) -> list[UUID]`` — the
ids of the outputs rows the node produced (written to ``node.output_refs``).

What changed versus the retired orchestration:
- No run-context ``output_status`` blob, no process lock — node rows are
  updated at row level by the orchestrator.
- The fabricated-plan targeted-revision path is gone: derivative regen runs a
  real ``director_plan`` node upstream (intentional micro behavior change).
- ``project.content_plan`` reuse is gone: the director plan is persisted as an
  internal ``outputs[type=content_plan]`` row per run (Phase 2 brings
  asset-hash reuse via director_understand).
"""

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
from app.models.schemas import (
    AssetType,
    ClipPayload,
    ContentPlan,
    DerivativeType,
    GenerationContext,
    MediaInput,
    RenderStatus,
    Segment,
    ToneSettings,
    validate_output_payload,
)
from app.models.tables import (
    Asset,
    BrandTemplate,
    Music,
    Output,
    PlanNode,
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

KNOWN_OUTPUTS = ("clips", "post", "quotes", "article", "carousel")

_OUTPUT_TO_DERIVATIVE_TYPE: dict[str, DerivativeType] = {
    "post": DerivativeType.POST,
    "quotes": DerivativeType.QUOTES,
    "article": DerivativeType.ARTICLE,
    "carousel": DerivativeType.CAROUSEL,
}

_DERIVATIVE_KIND_TO_TYPE: dict[str, DerivativeType] = {
    "post_gen": DerivativeType.POST,
    "quotes_gen": DerivativeType.QUOTES,
    "carousel_gen": DerivativeType.CAROUSEL,
    "article_gen": DerivativeType.ARTICLE,
}

# Media snippets above these thresholds are not sent directly to the multimodal
# model; we rely on ASR transcripts / extracted text instead. These limits are
# generous (10 min / 200 MB) because the agent layer now falls back to text-only
# automatically when a provider rejects or fails to process a media input, so
# the user still gets results from the transcript even for large files.
_MAX_DIRECT_VIDEO_SECONDS = 600  # 10 minutes
_MAX_DIRECT_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB


# ---------------------------------------------------------------------------
# Shared helpers (moved from generation.py)
# ---------------------------------------------------------------------------


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
    output_id: UUID,
    project: Project,
) -> str | None:
    """Generate and save a quote-card PNG; return the public URL or None on failure.

    The filename carries a timestamp so a regeneration never overwrites the
    object a browser may have cached under the previous URL.
    """
    return await _save_minimax_image(
        project,
        f"quote_{output_id}-{int(time.time())}.png",
        _quote_image_prompt(quote, attribution, project.event_name),
        "1:1",
        log_context={"output_id": str(output_id), "kind": "quote_card"},
    )


async def generate_clip_cover_image(
    output_id: UUID,
    project: Project,
    *,
    topic: str | None = None,
    title: str | None = None,
) -> str | None:
    """Generate a vertical cover image for a clip output on demand.

    Returns the public URL or None on failure. The image is intentionally
    generated only when requested by the UI to avoid paying image-generation
    costs for every clip. (Public helper — the outputs router calls it.)
    """
    prompt = (
        "A minimalist, elegant vertical cover image for a short knowledge video. "
        "Clean composition with subtle depth, professional typography-ready background, "
        "no text, no UI, no clutter. Suitable as a 9:16 video thumbnail. "
    )
    context_parts = []
    if topic:
        context_parts.append(f"Topic: {topic}")
    if title:
        context_parts.append(f"Title: {title}")
    if context_parts:
        prompt += " ".join(context_parts)

    return await _save_minimax_image(
        project,
        f"cover_{output_id}-{int(time.time())}.png",
        prompt,
        "9:16",
        log_context={"output_id": str(output_id), "kind": "clip_cover"},
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
        from app.models.schemas import MediaInputType

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
        from app.models.schemas import MediaInputType

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


async def _list_assets(db: AsyncSession, project_id: UUID) -> list[Asset]:
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    return list(result.scalars().all())


def _generation_context(
    run: WorkflowRun,
    project: Project,
    speaker: Speaker | None,
    *,
    brand_music_id: str | None = None,
) -> GenerationContext:
    """Assemble the GenerationContext from the run's task book (context)."""
    ctx = run.context or {}
    tone_raw = ctx.get("tone_settings")
    return GenerationContext(
        speaker=speaker_context_from_row(speaker),
        event_name=project.event_name,
        tone_settings=ToneSettings.model_validate(tone_raw) if tone_raw else None,
        target_language=ctx.get("target_language", "en"),
        instruction=ctx.get("instruction"),
        brand_music_id=brand_music_id,
    )


async def _load_content_plan(db: AsyncSession, node: PlanNode) -> ContentPlan:
    """Load the ContentPlan produced by this node's upstream director node."""
    if not node.inputs:
        raise ValueError(f"Node {node.id} ({node.kind}) has no upstream director node")
    director = await db.get(PlanNode, UUID(str(node.inputs[0])))
    if director is None or not director.output_refs:
        raise ValueError("Upstream director_plan node has no content_plan output")
    plan_output = await db.get(Output, UUID(str(director.output_refs[0])))
    if plan_output is None or plan_output.type != "content_plan":
        raise ValueError("content_plan output not found")
    return ContentPlan.model_validate(plan_output.payload)


async def _resolve_brand(
    db: AsyncSession,
    run: WorkflowRun,
    project: Project,
) -> tuple[BrandTemplate | None, str | None]:
    """Resolve the brand template for this run + its default music piece id."""
    ctx = run.context or {}
    bt = None
    bt_id = ctx.get("brand_template_id")
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
    return bt, brand_music_id


# ---------------------------------------------------------------------------
# Node runners
# ---------------------------------------------------------------------------


async def run_preprocess(
    db: AsyncSession, run: WorkflowRun, node: PlanNode, project: Project
) -> list[UUID]:
    """Validate source material exists (texts or media), like the old inline check."""
    asset_texts = await collect_asset_texts(db, project.id)
    assets = await _list_assets(db, project.id)
    has_media = any(a.file_url for a in assets)
    if not asset_texts and not has_media:
        raise ValueError("No source material to analyze")
    logger.info(
        "generation_asset_inputs_collected",
        project_id=str(project.id),
        text_count=len(asset_texts),
        media_asset_count=sum(1 for a in assets if a.file_url),
    )
    return []


async def run_persona_bootstrap(
    db: AsyncSession, run: WorkflowRun, node: PlanNode, project: Project
) -> list[UUID]:
    """Return the project's speaker, or auto-create one from source texts.

    Moved verbatim out of run_generation: the homepage no longer forces the
    user to pick/create a speaker, so the first run derives a default persona
    from the transcript. Now addressable + metered as its own node.
    """
    if project.speaker_id:
        return []

    asset_texts = await collect_asset_texts(db, project.id)
    trimmed = [t[:20_000] for t in asset_texts if t and t.strip()]
    if not trimmed:
        return []

    try:
        memory = await persona_agent.generate(
            speaker_name=project.title or "Speaker",
            speaker_title=None,
            language=project.language or "en",
            asset_texts=trimmed,
        )
    except Exception as e:  # noqa: BLE001 — persona bootstrap never fails the run
        logger.warning(
            "auto_speaker_extraction_failed",
            project_id=str(project.id),
            error=str(e),
        )
        return []

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
    await db.flush()

    project.speaker_id = speaker.id
    await db.flush()

    logger.info(
        "auto_created_speaker",
        project_id=str(project.id),
        speaker_id=str(speaker.id),
    )
    return []


async def run_director_plan(
    db: AsyncSession, run: WorkflowRun, node: PlanNode, project: Project
) -> list[UUID]:
    """Run the Content Director once and persist the plan as an internal output.

    Phase 1: every run plans fresh (the project.content_plan blob is gone).
    The plan is an internal outputs row (type=content_plan) so downstream
    nodes read it through the lineage graph, and Phase 2 can hang asset-hash
    reuse on the same mechanism.
    """
    ctx = run.context or {}
    outputs = [o for o in ctx.get("outputs", []) if o in KNOWN_OUTPUTS]
    requested_derivative_types = [
        _OUTPUT_TO_DERIVATIVE_TYPE[o] for o in outputs if o in _OUTPUT_TO_DERIVATIVE_TYPE
    ]
    # Targeted derivative runs: the director plans only for the target type.
    target_type = node.spec.get("target_type")
    if target_type in _OUTPUT_TO_DERIVATIVE_TYPE:
        requested_derivative_types = [_OUTPUT_TO_DERIVATIVE_TYPE[target_type]]

    asset_texts = await collect_asset_texts(db, project.id)
    assets = await _list_assets(db, project.id)
    asset_media = await collect_asset_media(assets)
    speaker = await resolve_speaker(db, project)
    generation_context = _generation_context(run, project, speaker)

    content_plan = await content_director_agent.plan(
        asset_texts=asset_texts,
        context=generation_context,
        asset_media=asset_media,
        requested_derivatives=requested_derivative_types or None,
    )

    plan_output = Output(
        project_id=project.id,
        plan_node_id=node.id,
        type="content_plan",
        language=ctx.get("target_language", "en"),
        provenance="generated",
        payload=content_plan.model_dump(mode="json"),
    )
    db.add(plan_output)
    await db.flush()
    return [plan_output.id]


async def run_clips_pipeline(
    db: AsyncSession, run: WorkflowRun, node: PlanNode, project: Project
) -> list[UUID]:
    """Select segments + write scripts + build render specs (composite node).

    Phase 1 keeps selection and script fused in one clip-agent call (Phase 2
    splits selection/script into separate nodes). Also fans out one render
    node per produced clip (claimed via outputs.render_status, D2).
    """
    ctx = run.context or {}
    clip_count = int(ctx.get("clip_count", 3))
    target_language = ctx.get("target_language", "en")

    node.spec = {**(node.spec or {}), "stage": "selecting_segments"}
    await db.flush()

    asset_texts = await collect_asset_texts(db, project.id)
    assets = await _list_assets(db, project.id)
    speaker = await resolve_speaker(db, project)
    bt, brand_music_id = await _resolve_brand(db, run, project)
    generation_context = _generation_context(
        run, project, speaker, brand_music_id=brand_music_id
    )
    content_plan = await _load_content_plan(db, node)

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

    async def _load_music_pieces() -> list[dict[str, str]]:
        music_rows = (
            await db.execute(
                select(Music)
                .where(Music.is_public.is_(True))
                .order_by(Music.created_at.desc())
            )
        ).scalars().all()
        return [
            {"id": str(m.id), "mood": str(m.mood), "title": str(m.title)}
            for m in music_rows
        ]

    try:
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
            music_pieces=await _load_music_pieces(),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("clip_agent_auto_retry", error=str(e))
        try:
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
                music_pieces=await _load_music_pieces(),
            )
        except Exception as e2:  # noqa: BLE001
            logger.error(
                "clip_agent_failed_after_retry",
                run_id=str(run.id),
                error=str(e2),
            )
            raise

    node.spec = {**(node.spec or {}), "stage": "building_specs"}
    await db.flush()

    # Idempotency: clear this project's prior clip outputs before writing new
    # ones (same semantics as the retired _delete_prior_outputs). Pending
    # render nodes pointing at the deleted rows are cancelled (skipped).
    from sqlalchemy import bindparam, text as _text

    prior_clip_ids = (
        await db.execute(
            select(Output.id).where(
                Output.project_id == project.id, Output.type == "clip"
            )
        )
    ).scalars().all()
    if prior_clip_ids:
        await db.execute(
            _text(
                "UPDATE plan_nodes SET status = 'skipped', updated_at = now() "
                "WHERE kind = 'render' AND status = 'pending' "
                "AND spec->>'output_id' IN :oids"
            ).bindparams(bindparam("oids", expanding=True)),
            {"oids": [str(oid) for oid in prior_clip_ids]},
        )
        await db.execute(
            delete(Output).where(Output.id.in_(prior_clip_ids))
        )

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

    output_ids: list[UUID] = []
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
        output = Output(
            project_id=project.id,
            plan_node_id=node.id,
            type="clip",
            language=target_language,
            provenance="real",
            payload=ClipPayload(
                hook=plan.hook,
                title_options=plan.title_options or ([plan.title] if plan.title else []),
                music_mood=plan.music_mood,
                duration=plan.duration_seconds,
            ).model_dump(mode="json"),
            source_ref={
                "segment": segment.model_dump(mode="json"),
                "start_seconds": plan.start_seconds,
                "end_seconds": plan.end_seconds,
                "asset_id": str(render_source.id) if render_source is not None else None,
            },
            render_spec=spec.model_dump(mode="json") if spec else None,
            render_status=RenderStatus.PENDING if spec else None,
            publishing={
                "title": plan.title or None,
                "description": plan.description or None,
                "hashtags": plan.hashtags or None,
                "topic": plan.topic or None,
            },
        )
        db.add(output)
        await db.flush()
        output_ids.append(output.id)

    # Render fan-out (D2): one render node per clip with a render spec. These
    # nodes are NOT claimed via the node claim — the render worker claims the
    # output row (render_status=PENDING) and mirrors terminal state back here.
    max_seq = int(node.seq)
    for idx, output_id in enumerate(output_ids, start=1):
        db.add(
            PlanNode(
                run_id=run.id,
                kind="render",
                status="pending",
                seq=max_seq + idx,
                inputs=[str(node.id)],
                spec={"output_id": str(output_id)},
            )
        )
    await db.flush()

    return output_ids


async def _generate_derivative_with_retry(
    derivative_type: DerivativeType,
    asset_texts: list[str],
    context: GenerationContext,
    content_plan: ContentPlan,
) -> dict:
    """Generate a derivative, retrying once on failure (preserved behavior)."""
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


async def run_derivative_gen(
    db: AsyncSession, run: WorkflowRun, node: PlanNode, project: Project
) -> list[UUID]:
    """Generate one derivative output (post/quotes/carousel/article).

    With ``spec.target_id`` set this is a targeted regeneration: the existing
    row is updated in place (its content_plan now comes from a real upstream
    director_plan node — the fabricated-plan path is gone).
    """
    derivative_type = _DERIVATIVE_KIND_TO_TYPE[node.kind]
    ctx = run.context or {}
    target_id = node.spec.get("target_id")
    target_language = node.spec.get("target_language") or ctx.get("target_language", "en")

    node.spec = {**(node.spec or {}), "stage": "writing_copy"}
    await db.flush()

    asset_texts = await collect_asset_texts(db, project.id)
    speaker = await resolve_speaker(db, project)
    generation_context = _generation_context(run, project, speaker)
    generation_context.target_language = target_language
    content_plan = await _load_content_plan(db, node)

    content = await _generate_derivative_with_retry(
        derivative_type=derivative_type,
        asset_texts=asset_texts,
        context=generation_context,
        content_plan=content_plan,
    )

    if target_id:
        output = await db.get(Output, UUID(str(target_id)))
        if output is None or output.project_id != project.id:
            raise ValueError("Target output not found")
        output.payload = validate_output_payload(output.type, content)
        output.language = target_language
        output.status = "generated"
        output.updated_at = datetime.now(UTC)
        output.plan_node_id = node.id
        await db.flush()
        return [output.id]

    # Idempotency: clear prior outputs of this type for the project.
    await db.execute(
        delete(Output).where(
            Output.project_id == project.id,
            Output.type == derivative_type.value,
        )
    )

    output = Output(
        project_id=project.id,
        plan_node_id=node.id,
        type=derivative_type.value,
        language=target_language,
        provenance="generated",
        payload=validate_output_payload(derivative_type.value, content),
    )
    db.add(output)
    await db.flush()

    # Quote cards get a generated PNG for the first quote.
    if derivative_type == DerivativeType.QUOTES:
        quotes = content.get("quotes", []) if isinstance(content, dict) else []
        if quotes:
            node.spec = {**(node.spec or {}), "stage": "generating_image"}
            await db.flush()
            first_quote = quotes[0]
            image_url = await _save_quote_card_image(
                quote=first_quote.get("quote", ""),
                attribution=first_quote.get("attribution", ""),
                output_id=output.id,
                project=project,
            )
            if image_url:
                output.files = {**(output.files or {}), "image": image_url}
                await db.flush()

    return [output.id]


async def run_script_revision(
    db: AsyncSession, run: WorkflowRun, node: PlanNode, project: Project
) -> list[UUID]:
    """Targeted hook/clip revision via the reviser agent (small topology)."""
    target_id = node.spec.get("target_id")
    if not target_id:
        raise ValueError("target_id is required for script revision")

    output = await db.get(Output, UUID(str(target_id)))
    if output is None or output.project_id != project.id or output.type != "clip":
        raise ValueError("Target clip not found")
    if not output.source_ref or not output.source_ref.get("segment"):
        raise ValueError("Clip has no source segment to revise from")

    segment = Segment.model_validate(output.source_ref["segment"])
    speaker = await resolve_speaker(db, project)
    payload = ClipPayload.model_validate(output.payload)

    revised = await reviser_agent.revise_by_instruction(
        clip_hook=payload.hook,
        clip_duration=payload.duration,
        clip_title_options=payload.title_options or [],
        clip_music_mood=payload.music_mood,
        segment=segment,
        instruction=node.spec.get("instruction") or "Improve this clip",
        speaker=speaker_context_from_row(speaker),
        scope=node.spec.get("scope", "clip"),
    )
    output.payload = ClipPayload(
        hook=revised.hook,
        title_options=revised.title_options,
        music_mood=revised.music_mood,
        duration=revised.duration_seconds,
    ).model_dump(mode="json")
    output.updated_at = datetime.now(UTC)
    output.plan_node_id = node.id
    await db.flush()
    return [output.id]


async def run_render_request(
    db: AsyncSession, run: WorkflowRun, node: PlanNode, project: Project
) -> list[UUID]:
    """Targeted re-render: flip render_status back to PENDING (scope=render).

    The render chain (outputs.render_status claim) picks it up and mirrors
    terminal state back onto this node — the runner only enqueues.
    """
    target_id = node.spec.get("target_id")
    if not target_id:
        raise ValueError("target_id is required for render")

    output = await db.get(Output, UUID(str(target_id)))
    if output is None or output.project_id != project.id:
        raise ValueError("Target clip not found")
    if not output.render_spec:
        raise ValueError("Clip has no render_spec")

    output.render_status = RenderStatus.PENDING
    output.render_error = None
    await db.flush()
    return []


NODE_RUNNERS = {
    "preprocess": run_preprocess,
    "persona_bootstrap": run_persona_bootstrap,
    "director_plan": run_director_plan,
    "clips_pipeline": run_clips_pipeline,
    "post_gen": run_derivative_gen,
    "quotes_gen": run_derivative_gen,
    "carousel_gen": run_derivative_gen,
    "article_gen": run_derivative_gen,
    "script": run_script_revision,
    "render": run_render_request,
}
