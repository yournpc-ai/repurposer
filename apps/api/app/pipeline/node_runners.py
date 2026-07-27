"""RunPlan node runners: one runner per node kind (RunPlan Phase 1/2).

Each runner is the direct transplant of a ``generation.py`` code path onto the
workflow_steps graph (docs/tasks/runplan-phase1-implementation.md §4 mapping
table). Signature is uniform: ``(db, run, node, project) -> list[UUID]`` — the
ids of the outputs rows the node produced (written to ``node.output_refs``).

What changed versus the retired orchestration:
- No run-context per-output status blob, no process lock — node rows are
  updated at row level by the orchestrator.
- The fabricated-plan targeted-revision path is gone: derivative regen runs a
  real ``director_plan`` node upstream (intentional micro behavior change).
- ``project.content_plan`` reuse is gone: Phase 2 splits the director into
  ``director_understand`` (material-scoped, reused across runs via asset hash)
  and ``director_plan`` (request-scoped storyboard, re-planned every run) —
  docs/tasks/director-two-step.md.
"""

import base64
import hashlib
import mimetypes
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import cast, delete, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.clip_agent import clip_agent
from app.skills.base import _MAX_CHARS_PER_TEXT
from app.skills.content_director import content_director_agent
from app.skills.persona import persona_agent
from app.skills.reviser import reviser_agent
from app.clients.minimax import MiniMaxError, minimax_client
from app.models.schemas import (
    AssetType,
    ClipMusic,
    ClipPayload,
    ClipSpec,
    CoverageReport,
    DerivativeType,
    GenerationContext,
    MaterialUnderstanding,
    MediaInput,
    RenderStatus,
    Segment,
    Storyboard,
    ToneSettings,
    validate_output_payload,
)
from app.models.database import AsyncSessionLocal
from app.models.tables import (
    Asset,
    BrandTemplate,
    Music,
    Output,
    WorkflowStep,
    Project,
    Speaker,
    WorkflowRun,
)
from app.memory.brand import (
    brand_from_template,
    music_from_plan,
    resolve_music_ref,
)
from app.pipeline.clip_spec import build_clip_spec, remove_range
from app.pipeline.derivative_dispatch import generate_derivative
from app.platform.project_context import (
    collect_asset_texts,
    resolve_speaker,
    speaker_context_from_row,
)
from app.tools.caption_translate import translate_caption_track
from app.tools.dubbing import synthesize_dub
from app.tools.filler import detect
from app.tools.storage import (
    download_to_temp,
    file_to_data_url,
    output_url,
    public_url,
    save_output,
    stream_url,
)

logger = structlog.get_logger()

KNOWN_OUTPUTS = ("clips", "post", "quotes", "article", "carousel")


async def _set_stage(node_id: UUID, stage: str) -> None:
    """Write the stepper's display-stage hint in its own session.

    This must NOT ride the runner session: that session stays open across LLM
    calls, and holding a row lock on ``workflow_steps`` (from a flushed spec
    update) deadlocks the metering session — ``record_usage`` updates the same
    row from inside ``minimax.generate`` while the runner awaits the response.
    Stage hints are display-only, so immediate independent commits are fine.
    """
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec, pg_array(["stage"]), func.to_jsonb(stage), True
                )
            )
        )
        await s.commit()


async def _set_summary(node_id: UUID, summary: str) -> None:
    """Write the quantified one-liner (spec.summary) — same independent-session
    jsonb_set discipline as ``_set_stage`` (never Python read-modify-write)."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec, pg_array(["summary"]), func.to_jsonb(summary), True
                )
            )
        )
        await s.commit()


async def _fill_summary(node_id: UUID, kind: str, **params: object) -> None:
    """Fill spec.summary from the registry's summary_template for ``kind``.

    Templates fill numbers, never LLM-polished prose (CHAT_ARCH §8)."""
    from app.pipeline.registry import SKILL_REGISTRY  # deferred: import cycle

    template = next(
        (e.summary_template for e in SKILL_REGISTRY.values() if e.node_kind == kind),
        None,
    )
    if not template:
        return
    try:
        await _set_summary(node_id, template.format(**params))
    except KeyError:
        logger.warning("summary_template_params_missing", kind=kind, params=list(params))


def _count_words(value: object) -> int:
    """Whitespace token count over every string in a payload (display-only)."""
    if isinstance(value, str):
        return len(value.split())
    if isinstance(value, dict):
        return sum(_count_words(v) for v in value.values())
    if isinstance(value, list):
        return sum(_count_words(v) for v in value)
    return 0

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


async def _upstream_by_kind(
    db: AsyncSession, node: WorkflowStep, kind: str
) -> WorkflowStep:
    """Find this node's direct upstream step of the given kind.

    Upstreams are matched by kind, never by position — the full-run prelude
    fans out (persona_bootstrap ∥ director_understand), so input order is not
    a stable contract.
    """
    for upstream_id in node.inputs or []:
        upstream = await db.get(WorkflowStep, UUID(str(upstream_id)))
        if upstream is not None and upstream.kind == kind:
            return upstream
    raise ValueError(f"Node {node.id} ({node.kind}) has no upstream {kind} node")


async def _load_understanding(
    db: AsyncSession, node: WorkflowStep
) -> MaterialUnderstanding:
    """Load the MaterialUnderstanding from this node's upstream
    director_understand node (its output row may be a reused earlier one)."""
    understand = await _upstream_by_kind(db, node, "director_understand")
    if not understand.output_refs:
        raise ValueError("Upstream director_understand node has no output")
    row = await db.get(Output, UUID(str(understand.output_refs[0])))
    if row is None or row.type != "material_understanding":
        raise ValueError("material_understanding output not found")
    return MaterialUnderstanding.model_validate(row.payload)


async def _load_director_outputs(
    db: AsyncSession, node: WorkflowStep
) -> tuple[MaterialUnderstanding, Storyboard]:
    """Load both director artifacts for an executor node (two upstream hops):
    the storyboard from director_plan, the understanding from its upstream."""
    plan_node = await _upstream_by_kind(db, node, "director_plan")
    understanding = await _load_understanding(db, plan_node)
    if not plan_node.output_refs:
        raise ValueError("Upstream director_plan node has no storyboard output")
    row = await db.get(Output, UUID(str(plan_node.output_refs[0])))
    if row is None or row.type != "storyboard":
        raise ValueError("storyboard output not found")
    return understanding, Storyboard.model_validate(row.payload)


def _asset_digest(asset_texts: list[str], assets: list[Asset]) -> str:
    """Content hash of the understanding's exact inputs.

    Texts are trimmed to the same window the prompt sees (a change beyond the
    trim window does not alter the LLM input, so it must not invalidate).
    Media identity = file_url (unique storage path per upload); ``words`` meta
    is not an understanding input and stays out of the hash.
    """
    h = hashlib.sha256()
    for text in asset_texts:
        if text and text.strip():
            h.update(text[:_MAX_CHARS_PER_TEXT].encode("utf-8"))
            h.update(b"\x00")
    for asset in sorted(assets, key=lambda a: str(a.id)):
        descriptor = (
            f"{asset.id}|{asset.type}|{asset.file_url}|{len(asset.slide_pages or [])}"
        )
        h.update(descriptor.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _compute_coverage(
    storyboard: Storyboard, understanding: MaterialUnderstanding
) -> CoverageReport:
    """Derive argument → slot accountability from valid argument_ids.

    Unknown ids (the LLM may invent them) are dropped in place first. The
    report is informational — never a gate (gating belongs to Phase 3 verify).
    """
    valid_ids = {a.id for a in understanding.key_arguments}
    assignments: dict[str, list[str]] = {}
    for slot in storyboard.slots:
        slot.argument_ids = [i for i in slot.argument_ids if i in valid_ids]
        for arg_id in slot.argument_ids:
            assignments.setdefault(arg_id, []).append(slot.slot)
    collisions = [
        f"{arg_id} → {', '.join(slots)}"
        for arg_id, slots in assignments.items()
        if len(slots) > 1
    ]
    unused = [a.id for a in understanding.key_arguments if a.id not in assignments]
    return CoverageReport(
        assignments=assignments, unused_arguments=unused, collisions=collisions
    )


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
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
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
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
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


def _source_language(project: Project, assets: list[Asset]) -> str:
    """Language tag for the understanding row: the source material's language."""
    for asset in assets:
        lang = (asset.meta or {}).get("language")
        if lang:
            return str(lang)
    return project.language or "en"


async def run_director_understand(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Director step 1: material-scoped understanding, reused across runs.

    The reuse predicate is the asset hash stored on the output row's
    ``source_ref`` — media downloads and the (expensive, multimodal) LLM call
    only happen when the hash misses. A reuse returns the earlier row's id, so
    no duplicate understanding rows accumulate and the node costs nothing.
    """
    asset_texts = await collect_asset_texts(db, project.id)
    assets = await _list_assets(db, project.id)
    digest = _asset_digest(asset_texts, assets)

    latest = (
        await db.execute(
            select(Output)
            .where(
                Output.project_id == project.id,
                Output.type == "material_understanding",
            )
            .order_by(Output.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and (latest.source_ref or {}).get("asset_hash") == digest:
        try:
            cached = MaterialUnderstanding.model_validate(latest.payload)
        except Exception:  # noqa: BLE001 — stale shape: fall through, regenerate
            logger.warning(
                "understanding_reuse_payload_invalid", output_id=str(latest.id)
            )
        else:
            await _set_summary(
                node.id,
                f"Reused understanding · {len(cached.key_arguments)} arguments",
            )
            logger.info(
                "director_understand_reused",
                project_id=str(project.id),
                output_id=str(latest.id),
            )
            return [latest.id]

    asset_media = await collect_asset_media(assets)
    understanding = await content_director_agent.understand(
        asset_texts=asset_texts,
        asset_media=asset_media,
    )

    row = Output(
        project_id=project.id,
        workflow_step_id=node.id,
        type="material_understanding",
        language=_source_language(project, assets),
        provenance="generated",
        payload=understanding.model_dump(mode="json"),
        source_ref={"asset_hash": digest},
    )
    db.add(row)
    await db.flush()
    await _set_summary(
        node.id,
        f"Understood {len(understanding.key_arguments)} arguments · "
        f"{len(understanding.quote_candidates)} quotes",
    )
    return [row.id]


async def run_director_plan(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Director step 2: request-scoped storyboard, re-planned every run.

    Reads ONLY the upstream understanding (self-sufficiency contract) plus the
    task book and speaker/tone context; coverage accountability is computed by
    code and persisted with the storyboard.
    """
    ctx = run.context or {}
    understanding = await _load_understanding(db, node)

    outputs = [o for o in ctx.get("outputs", []) if o in KNOWN_OUTPUTS]
    # Targeted derivative runs: the storyboard plans only for the target type.
    target_type = node.spec.get("target_type")
    if target_type in _OUTPUT_TO_DERIVATIVE_TYPE:
        outputs = [target_type]
    task_book = {
        "outputs": outputs or ["clips"],
        "clip_count": int(ctx.get("clip_count", 3)),
    }

    speaker = await resolve_speaker(db, project)
    generation_context = _generation_context(run, project, speaker)

    storyboard = await content_director_agent.plan(
        understanding=understanding,
        context=generation_context,
        task_book=task_book,
    )
    storyboard.coverage = _compute_coverage(storyboard, understanding)

    row = Output(
        project_id=project.id,
        workflow_step_id=node.id,
        type="storyboard",
        language=ctx.get("target_language", "en"),
        provenance="generated",
        payload=storyboard.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    await _set_summary(
        node.id,
        f"Planned {len(storyboard.slots)} slots · "
        f"{len(storyboard.coverage.unused_arguments)} arguments unused",
    )
    return [row.id]


async def run_clips_pipeline(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Select segments + write scripts + build render specs (composite node).

    Phase 1 keeps selection and script fused in one clip-agent call (Phase 2
    splits selection/script into separate nodes). Also fans out one render
    node per produced clip (claimed via outputs.render_status, D2).
    """
    ctx = run.context or {}
    clip_count = int(ctx.get("clip_count", 3))
    target_language = ctx.get("target_language", "en")

    await _set_stage(node.id, "selecting_segments")

    asset_texts = await collect_asset_texts(db, project.id)
    assets = await _list_assets(db, project.id)
    speaker = await resolve_speaker(db, project)
    bt, brand_music_id = await _resolve_brand(db, run, project)
    generation_context = _generation_context(
        run, project, speaker, brand_music_id=brand_music_id
    )
    understanding, storyboard = await _load_director_outputs(db, node)

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
            understanding=understanding,
            storyboard=storyboard,
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
                understanding=understanding,
                storyboard=storyboard,
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

    await _set_stage(node.id, "building_specs")

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
                "UPDATE workflow_steps SET status = 'skipped', updated_at = now() "
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
            workflow_step_id=node.id,
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
            score={
                "value": plan.recommendation_score,
                "reason": plan.score_reason or None,
            },
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
            WorkflowStep(
                run_id=run.id,
                kind="render",
                status="pending",
                seq=max_seq + idx,
                inputs=[str(node.id)],
                spec={"output_id": str(output_id)},
            )
        )
    await db.flush()

    await _fill_summary(
        node.id,
        "clips_pipeline",
        n=len(output_ids),
        total_seconds=sum(
            int(plan.duration_seconds or 0) for plan in plans.clips[:clip_count]
        ),
    )

    return output_ids


async def _generate_derivative_with_retry(
    derivative_type: DerivativeType,
    asset_texts: list[str],
    context: GenerationContext,
    understanding: MaterialUnderstanding,
    storyboard: Storyboard,
) -> dict:
    """Generate a derivative, retrying once on failure (preserved behavior)."""
    try:
        return await generate_derivative(
            derivative_type=derivative_type,
            asset_texts=asset_texts,
            context=context,
            understanding=understanding,
            storyboard=storyboard,
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
            understanding=understanding,
            storyboard=storyboard,
        )


async def run_derivative_gen(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Generate one derivative output (post/quotes/carousel/article).

    With ``spec.target_id`` set this is a targeted regeneration: the existing
    row is updated in place (its storyboard now comes from a real upstream
    director_plan node — the fabricated-plan path is gone).
    """
    derivative_type = _DERIVATIVE_KIND_TO_TYPE[node.kind]
    ctx = run.context or {}
    target_id = node.spec.get("target_id")
    target_language = node.spec.get("target_language") or ctx.get("target_language", "en")

    await _set_stage(node.id, "writing_copy")

    asset_texts = await collect_asset_texts(db, project.id)
    speaker = await resolve_speaker(db, project)
    generation_context = _generation_context(run, project, speaker)
    generation_context.target_language = target_language
    understanding, storyboard = await _load_director_outputs(db, node)

    content = await _generate_derivative_with_retry(
        derivative_type=derivative_type,
        asset_texts=asset_texts,
        context=generation_context,
        understanding=understanding,
        storyboard=storyboard,
    )

    if target_id:
        output = await db.get(Output, UUID(str(target_id)))
        if output is None or output.project_id != project.id:
            raise ValueError("Target output not found")
        output.payload = validate_output_payload(output.type, content)
        output.language = target_language
        output.status = "generated"
        output.updated_at = datetime.now(UTC)
        output.workflow_step_id = node.id
        await db.flush()
        await _fill_summary(node.id, node.kind, word_count=_count_words(content))
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
        workflow_step_id=node.id,
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
            await _set_stage(node.id, "generating_image")
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

    await _fill_summary(node.id, node.kind, word_count=_count_words(content))
    return [output.id]


async def run_script_revision(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
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
    if revised.recommendation_score is not None:
        output.score = {
            "value": revised.recommendation_score,
            "reason": revised.score_reason or (output.score or {}).get("reason"),
        }
    output.updated_at = datetime.now(UTC)
    output.workflow_step_id = node.id
    await db.flush()
    await _fill_summary(node.id, "script", scope=node.spec.get("scope", "clip"))
    return [output.id]


async def run_render_request(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
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


# ---- modifier skills (deterministic, act on existing clips) ----------------


async def _target_clips(
    db: AsyncSession, node: WorkflowStep, project: Project
) -> list[Output]:
    """Clips a modifier step acts on: the upstream steps' output_refs (same
    run — e.g. a clips_pipeline or a previous modifier in the chain), else the
    project's existing renderable clips."""
    clip_ids: list[UUID] = []
    if node.inputs:
        upstream = list(
            (
                await db.execute(
                    select(WorkflowStep).where(
                        WorkflowStep.id.in_([UUID(str(i)) for i in node.inputs])
                    )
                )
            )
            .scalars()
            .all()
        )
        for step in upstream:
            clip_ids.extend(UUID(str(ref)) for ref in (step.output_refs or []))
    if clip_ids:
        clips = list(
            (
                await db.execute(
                    select(Output).where(Output.id.in_(clip_ids), Output.type == "clip")
                )
            )
            .scalars()
            .all()
        )
    else:
        clips = list(
            (
                await db.execute(
                    select(Output).where(
                        Output.project_id == project.id,
                        Output.type == "clip",
                        Output.render_spec.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    return [c for c in clips if c.render_spec]


async def _fan_out_renders(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, output_ids: list[UUID]
) -> None:
    """One render step per touched output (same shape as the clips fan-out):
    claimed via outputs.render_status, terminal state mirrored back."""
    max_seq = int(
        (
            await db.execute(
                select(func.max(WorkflowStep.seq)).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        or node.seq
    )
    for idx, output_id in enumerate(output_ids, start=1):
        db.add(
            WorkflowStep(
                run_id=run.id,
                kind="render",
                status="pending",
                seq=max_seq + idx,
                inputs=[str(node.id)],
                spec={"output_id": str(output_id)},
            )
        )
    await db.flush()


async def _record_target_output_ids(node_id: UUID, output_ids: list[UUID]) -> None:
    """Record the cross-run DAG edge (which outputs this step consumed) on the
    step's spec — jsonb_set in its own session, same discipline as _set_stage."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec,
                    pg_array(["target_output_ids"]),
                    cast([str(oid) for oid in output_ids], JSONB),
                    True,
                )
            )
        )
        await s.commit()


async def run_remove_filler(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Remove filler words + repeated takes from existing clips, then re-render.

    Deterministic (tools/filler.detect + clip_spec.remove_range); never touches
    the source media — cuts land as hidden segments in the render_spec.
    """
    await _set_stage(node.id, "removing_fillers")
    clips = await _target_clips(db, node, project)
    if not clips:
        await _set_summary(node.id, "No clips to clean")
        return []

    total_fillers = 0
    total_repeats = 0
    touched: list[UUID] = []
    for output in clips:
        spec = ClipSpec.model_validate(output.render_spec)
        asset_id = spec.source.asset_id or (output.source_ref or {}).get("asset_id")
        asset = await db.get(Asset, UUID(str(asset_id))) if asset_id else None
        words = (asset.meta or {}).get("words") if asset else None
        if not words:
            continue
        language = (asset.meta or {}).get("language") or output.language or "en"
        report = detect(words, language)

        new_spec = spec
        applied_fillers = 0
        applied_repeats = 0
        for start, end in report.ranges:
            if not any(
                not s.hidden and s.start < end and start < s.end
                for s in new_spec.segments
            ):
                continue
            new_spec = remove_range(new_spec, start, end)
            if (start, end) in report.repeat_ranges:
                applied_repeats += 1
            else:
                applied_fillers += 1
        if new_spec is spec:
            continue

        output.render_spec = new_spec.model_dump(mode="json")
        output.render_status = RenderStatus.PENDING
        output.render_error = None
        output.updated_at = datetime.now(UTC)
        await db.flush()
        touched.append(output.id)
        total_fillers += applied_fillers
        total_repeats += applied_repeats

    if not touched:
        await _set_summary(node.id, "No fillers found")
        return []

    await _fan_out_renders(db, run, node, touched)
    await _record_target_output_ids(node.id, touched)
    await _fill_summary(
        node.id,
        "remove_filler",
        filler_count=total_fillers,
        repeat_count=total_repeats,
    )
    return touched


async def run_add_music(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Score existing clips with a music bed, then re-render.

    Resolution order (all by code, never the LLM): music_id → mood → brand
    default → "calm". A mood with no matching track fails the step with a
    clear error (CHAT_ARCH §10: the conversation offers alternatives).
    """
    await _set_stage(node.id, "adding_music")
    clips = await _target_clips(db, node, project)
    if not clips:
        await _set_summary(node.id, "No clips to score")
        return []

    mood = node.spec.get("mood")
    music_id = node.spec.get("music_id")
    gain_db = node.spec.get("gain_db")

    # Resolution order (all by code, never the LLM): music_id → mood → brand
    # default → "calm"; each unresolvable ref falls through to the next. Only
    # a fully unresolvable chain fails the step (CHAT_ARCH §10: clear error).
    brand_default: Any = None
    if not music_id and not mood and project.speaker_id is not None:
        bt = (
            await db.execute(
                select(BrandTemplate).where(BrandTemplate.user_id == project.user_id)
            )
        ).scalars().first()
        brand_default = (
            (bt.config or {}).get("musicId") or (bt.config or {}).get("musicMood")
            if bt
            else None
        )

    track = None
    for ref in (music_id, mood, brand_default, "calm"):
        if not ref:
            continue
        track = await resolve_music_ref(db, ref)
        if track is not None:
            break
    if track is None:
        raise ValueError(f"No music track found for mood '{mood}'")

    music = ClipMusic(
        music_id=str(track.id),
        url=public_url(track.file_path),
        enabled=True,
        gain_db=float(gain_db) if gain_db is not None else -18.0,
    )
    touched: list[UUID] = []
    for output in clips:
        spec = ClipSpec.model_validate(output.render_spec)
        output.render_spec = spec.model_copy(update={"music": music}).model_dump(mode="json")
        output.render_status = RenderStatus.PENDING
        output.render_error = None
        output.updated_at = datetime.now(UTC)
        await db.flush()
        touched.append(output.id)

    await _fan_out_renders(db, run, node, touched)
    await _record_target_output_ids(node.id, touched)
    await _fill_summary(node.id, "add_music", mood=track.mood or mood or "calm")
    return touched


async def _modifier_target_clips(
    db: AsyncSession, node: WorkflowStep, project: Project
) -> list[Output]:
    """Target resolution for modifier steps: an explicit
    ``spec.target_output_id`` (asset-scoped chat) wins; otherwise fall back to
    the upstream/project clips (``_target_clips``)."""
    target_id = (node.spec or {}).get("target_output_id")
    if target_id:
        clips = list(
            (
                await db.execute(
                    select(Output).where(
                        Output.id == UUID(str(target_id)),
                        Output.project_id == project.id,
                        Output.type == "clip",
                    )
                )
            )
            .scalars()
            .all()
        )
        return [c for c in clips if c.render_spec]
    return await _target_clips(db, node, project)


async def run_translate_clip(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Translate existing clips' caption tracks into the target language, then
    re-render (modifier step — acts on existing clips, not a generation)."""
    lang = (node.spec or {}).get("target_language")
    if not lang:
        raise ValueError("target_language is required for translate_clip")
    await _set_stage(node.id, "translating_captions")
    clips = await _modifier_target_clips(db, node, project)
    if not clips:
        await _set_summary(node.id, "No clips to translate")
        return []

    touched: list[UUID] = []
    for output in clips:
        spec = output.render_spec
        track = (spec or {}).get("caption_track") or []
        if not track:
            continue
        new_track = await translate_caption_track(track, lang)
        output.render_spec = {**spec, "caption_track": new_track, "target_language": lang}
        output.render_status = RenderStatus.PENDING
        output.render_error = None
        output.updated_at = datetime.now(UTC)
        await db.flush()
        touched.append(output.id)

    if not touched:
        await _set_summary(node.id, "No captions to translate")
        return []
    await _fan_out_renders(db, run, node, touched)
    await _record_target_output_ids(node.id, touched)
    await _fill_summary(node.id, "translate_clip", n=len(touched), lang=lang)
    return touched


async def run_dub_clip(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Dub existing clips with the speaker's cloned voice (tools/dubbing.py),
    then re-render (modifier step)."""
    lang = (node.spec or {}).get("target_language") or "en"
    await _set_stage(node.id, "dubbing")
    clips = await _modifier_target_clips(db, node, project)
    if not clips:
        await _set_summary(node.id, "No clips to dub")
        return []

    touched: list[UUID] = []
    for output in clips:
        try:
            new_spec = await synthesize_dub(db, output, project, lang)
        except HTTPException as e:
            # Per-clip skip (no captions / no sample usable for this one);
            # a fully unresolvable batch fails the step below.
            logger.info("dub_clip skip output %s: %s", output.id, e.detail)
            continue
        output.render_spec = new_spec
        output.render_status = RenderStatus.PENDING
        output.render_error = None
        output.updated_at = datetime.now(UTC)
        await db.flush()
        touched.append(output.id)

    if not touched:
        raise ValueError("No clips could be dubbed (missing captions or voice sample)")
    await _fan_out_renders(db, run, node, touched)
    await _record_target_output_ids(node.id, touched)
    await _fill_summary(node.id, "dub", n=len(touched), lang=lang)
    return touched

STEP_RUNNERS = {
    "preprocess": run_preprocess,
    "persona_bootstrap": run_persona_bootstrap,
    "director_understand": run_director_understand,
    "director_plan": run_director_plan,
    "clips_pipeline": run_clips_pipeline,
    "post_gen": run_derivative_gen,
    "quotes_gen": run_derivative_gen,
    "carousel_gen": run_derivative_gen,
    "article_gen": run_derivative_gen,
    "script": run_script_revision,
    "render": run_render_request,
    "remove_filler": run_remove_filler,
    "add_music": run_add_music,
    "translate_clip": run_translate_clip,
    "dub": run_dub_clip,
}

