"""Writer tools' shared node base (ADR-039 P2).

One body serves the four copy-writer nodes (post/quotes/carousel/article):
resolve the node's slot + language, load the director artifacts, call the
package's writer declaration, persist the output row. Each package's
``node.py`` declares a thin subclass (kind / output_type / slot_label /
``writer``) — the DerivativeType → writer map died with the outputs-registry
derivation. A schema rejection is answered by the harness's one bounded
repair round inside ``Agent.call`` (ADR-039 P3) — no blind retries here.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncio
import hashlib
import io
import structlog
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import MAX_CHARS_PER_TEXT, Agent
from app.agents.contexts import _generation_context
from app.memory.brand import brand_from_block, resolve_brand_block
from app.models.schemas import (
    ClipPayload,
    DerivativeType,
    GenerationContext,
    MaterialUnderstanding,
    QuoteFrame,
    RenderStatus,
    Storyboard,
    validate_derivative_content,
    validate_output_payload,
)
from app.models.tables import Asset, Output, Project, WorkflowRun, WorkflowStep
from app.pipeline.clip_spec import build_quote_card_spec, build_stacked_quote_card_spec
from app.pipeline.quote_card_stack import (
    ChainCaption,
    composite_chain_quote_card,
    composite_frame_card,
    extract_video_frames,
    pick_curated_frame,
)
from app.pipeline.edges import _load_director_outputs
from app.pipeline.graph import NODE_KINDS, NodeBase, estimate_mechanical, token_bounds
from app.pipeline.morph import _render_step_label
from app.pipeline.step_context import _count_words, _list_assets
from app.pipeline.step_display import (
    _fill_summary,
    _node_slot,
    _pop_spec_field,
    _set_stage,
    slot_tag,
    ui_lang_of,
)
from app.platform.project_context import collect_asset_texts, resolve_persona
from app.providers.storage import output_url, save_output, stream_url
from app.models.schemas import AssetType

logger = structlog.get_logger()

# Chain-card duration (RECIPES §4.6.2): the composite PNG holds for this long
# under the Ken-Burns zoom — one constant feeds both the ClipSpec's
# ``duration_s`` and the Output payload's ``duration``.
_QUOTE_CARD_CHAIN_DURATION_S = 6.0


def derivative_output_types() -> frozenset[str]:
    """Output types owned by the copy-writer nodes (node-derived — the retired
    ``_OUTPUT_TO_DERIVATIVE_TYPE`` map has no parallel home)."""
    return frozenset(
        n.output_type
        for n in NODE_KINDS.values()
        if isinstance(n, DerivativeWriterNode) and n.output_type
    )


class CopyWriterParams(BaseModel):
    """The four copy-writer tools' shared adjudication document (outputs-
    derive, ADR-043): the writers share one node body, so their params are
    one model — quotes/carousel subclass it to add ``count`` in their own
    packages. Field descriptions ARE the LLM's parameter documentation
    (injected into the intent prompt): write them as "when to use / what
    null means", not as type restatements. Multi-version requests are
    multi-task (an English and a German post = two write_post tasks, each
    with its own language)."""

    language: str = Field(
        description="ISO code this output is WRITTEN in (e.g. 'a German "
        "post' → 'de'). Infer from the request; default to the prompt's "
        "language when the user names none."
    )
    focus: str | None = Field(
        default=None,
        description="A short angle phrase when the user assigns this output "
        "a specific angle (e.g. 'the post should cover the pricing debate' "
        "→ 'pricing debate'). null = the director picks the angle.",
    )
    tone_override: str | None = Field(
        default=None,
        description="A short tone note when the user asks for a per-output "
        "tone (e.g. '帖子正式一点' → 'formal'). null = the persona's tone.",
    )


def derive_quote_alt_language(
    source_language: str | None, *candidates: str | None
) -> str | None:
    """quote-cards §2.3/D4: the SECOND caption language for bilingual mode.

    Candidates in priority order (user-named target → project/UI locale →
    run target_language); the first set value that differs from the source
    wins. None = no distinct alt exists → bilingual would print the same
    language twice → the caption gate is skipped (chat/service.py) and the
    run stamps ``source_only``.
    """
    src = (source_language or "").strip().lower()
    for cand in candidates:
        lang = (cand or "").strip().lower()
        if lang and lang != src:
            return lang
    return None


async def _project_source_language(
    db: AsyncSession, project: Project
) -> str | None:
    """The run's source language: the first AV asset's ASR-detected
    ``meta.language`` (the ASR processor stamps it), else a TRANSCRIPT
    asset's stamped ``meta.language`` (text processors don't stamp it yet —
    only assets created with an explicit language carry one), else the
    project's own language. None only when all are unset."""
    assets = await _list_assets(db, project.id)
    for a in assets:
        if a.type in (AssetType.VIDEO, AssetType.AUDIO, AssetType.TRANSCRIPT):
            lang = (a.meta or {}).get("language")
            if lang:
                return str(lang)
    return project.language or None


def _chain_captions(
    chain: list[dict[str, Any]], caption_mode: str | None
) -> list[ChainCaption]:
    """Chain entries → caption blocks (D5 双译本收窄, 2026-08-28).

    The secondary line is ALWAYS ``quote_alt`` (the translator's product)
    and only in bilingual mode; the writer's own ``quote`` is hook/metadata
    and never a second on-screen translation. target_only promotes the alt
    translation to the single primary line (fallback: the source line).
    """
    captions: list[ChainCaption] = []
    for q in chain:
        src = (q.get("quote_source") or q.get("quote") or "").strip()
        alt = (q.get("quote_alt") or "").strip() or None
        if caption_mode == "target_only":
            captions.append(ChainCaption(primary=alt or src))
        elif caption_mode == "bilingual":
            captions.append(ChainCaption(primary=src, secondary=alt))
        else:  # source_only / undecided
            captions.append(ChainCaption(primary=src))
    return captions


def _entry_span(q: dict[str, Any]) -> tuple[float, float] | None:
    """The entry's video span for curated-frame picking: its snapped
    [source_start, source_end], else a ±2s window around a valid
    ``frame_at``. None = no usable time-bind (never clamped to 0.0)."""
    try:
        start = q.get("source_start")
        end = q.get("source_end")
        if start is not None and end is not None and float(end) > float(start):
            return float(start), float(end)
        frame_at = q.get("frame_at")
        if frame_at is not None and float(frame_at) >= 0:
            return max(0.0, float(frame_at) - 2.0), float(frame_at) + 2.0
    except (TypeError, ValueError):
        pass
    return None


def _entry_frame_at(q: dict[str, Any]) -> float | None:
    """The entry's frame-grab timecode; invalid/missing → None (the entry
    renders frame-less — invalid values are SKIPPED, never clamped to 0.0,
    D15)."""
    try:
        frame_at = q.get("frame_at")
        if frame_at is not None and float(frame_at) >= 0:
            return float(frame_at)
    except (TypeError, ValueError):
        pass
    return None


async def _download_bytes(url: str | None) -> bytes | None:
    """Stream a storage URL to bytes; any failure → None (graceful degrade —
    the chain still renders text/photo/dark paths)."""
    if not url:
        return None
    import httpx  # local — heavy import only on this path

    try:
        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.get(url, follow_redirects=True)
            return r.content if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _open_image(data: bytes) -> Any | None:
    """bytes → a loaded PIL Image; None on any decode failure."""
    from PIL import Image  # local — CPU section only

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def _compose_chain_pngs(
    *,
    video_bytes: bytes | None,
    image_bytes: list[bytes],
    chain: list[dict[str, Any]],
    captions: list[ChainCaption],
    speaker_form: bool,
    attribution: str | None,
) -> tuple[list[bytes], bytes]:
    """CPU section (runs in a thread): curated frame + per-entry frame-card
    PNGs + the form A/B composite PNG (D15).

    Curated frame = YuNet best-face pick inside the FIRST entry's span
    (``pick_curated_frame``); photo path → the first image; else None →
    the composite's form B dark branch. Per-entry frames: valid
    ``frame_at`` grabs only (invalid skipped, never clamped); photo path
    cycles the uploaded images; else None → that entry's frame card
    renders dark.
    """
    curated = None
    if video_bytes:
        span = _entry_span(chain[0])
        if span:
            curated = pick_curated_frame(video_bytes, span[0], span[1])
    photos = [img for img in (_open_image(b) for b in image_bytes) if img is not None]
    if curated is None and photos:
        curated = photos[0]

    entry_frames: list[Any] = []
    if video_bytes:
        times = [_entry_frame_at(q) for q in chain]
        valid = [t for t in times if t is not None]
        grabbed: list[Any] = []
        if valid:
            try:
                grabbed = extract_video_frames(video_bytes, valid)
            except Exception:  # noqa: BLE001
                grabbed = []
        it = iter(grabbed)
        entry_frames = [next(it, None) if t is not None else None for t in times]
    elif photos:
        entry_frames = [photos[i % len(photos)] for i in range(len(chain))]
    else:
        entry_frames = [None] * len(chain)

    frame_pngs = [
        composite_frame_card(frame=frame, caption=cap, attribution=attribution)
        for frame, cap in zip(entry_frames, captions, strict=True)
    ]
    composite_png = composite_chain_quote_card(
        chain=captions,
        curated_frame=curated,
        speaker_form=speaker_form,
        attribution=attribution,
    )
    return frame_pngs, composite_png


async def _build_quote_chain_artifacts(
    project: Project,
    *,
    chain: list[dict[str, Any]],
    captions: list[ChainCaption],
    needs_speaker_frame: bool,
    attribution: str | None,
    source_video: Asset | None,
    images: list[Asset],
    target_language: str,
    brand: Any,
    brand_ref: Any,
    duration_s: float = _QUOTE_CARD_CHAIN_DURATION_S,
) -> tuple[list[str], str | None, Any | None, str | None]:
    """Chain materializer (§2.2 + §2.6, 2026-08-28).

    Produces the chain's three artifact families:

    1. N frame-card PNGs (one per entry: its frame + its caption block)
       → uploaded to project storage, URLs returned in order.
    2. The form A/B composite PNG → uploaded, URL returned.
    3. The motion clip-spec (Ken-Burns zoom on the composite) — ONLY
       when an anchor asset exists (video else first photo; a pure-text
       chain gets no MP4 — the composite card IS the product, the MP4
       is never the main promise).

    Returns ``(frame_card_urls, composite_url, spec_or_None, error)`` —
    graceful-degrade: composite failure → ``(urls, None, None, reason)``.
    All user products go through ``save_output`` project scope (D3:
    never the demo/ display reserve).
    """
    if not chain:
        return [], None, None, "chain: empty"

    video_bytes = await _download_bytes(
        stream_url(source_video.file_url) if source_video and source_video.file_url else None
    )
    image_bytes: list[bytes] = []
    if not video_bytes:
        for asset in images[:4]:  # cap downloads — the path cycles them anyway
            data = await _download_bytes(
                stream_url(asset.file_url) if asset.file_url else None
            )
            if data:
                image_bytes.append(data)

    try:
        frame_pngs, composite_png = await asyncio.to_thread(
            _compose_chain_pngs,
            video_bytes=video_bytes,
            image_bytes=image_bytes,
            chain=chain,
            captions=captions,
            speaker_form=needs_speaker_frame,
            attribution=attribution,
        )
    except Exception as exc:  # noqa: BLE001
        return [], None, None, f"chain: compose failed ({type(exc).__name__}: {exc})"

    frame_urls: list[str] = []
    for i, png in enumerate(frame_pngs):
        digest = hashlib.md5(png).hexdigest()[:8]
        try:
            key = await save_output(
                project.id, project.user_id, f"quote-frame-{digest}.png", png
            )
        except Exception as exc:  # noqa: BLE001
            return frame_urls, None, None, (
                f"chain: frame {i} upload failed ({type(exc).__name__}: {exc})"
            )
        url = output_url(key)
        if not url:
            return frame_urls, None, None, "chain: output_url returned None"
        frame_urls.append(url)

    digest = hashlib.md5(composite_png).hexdigest()[:8]
    try:
        key = await save_output(
            project.id, project.user_id, f"quote-chain-{digest}.png", composite_png
        )
    except Exception as exc:  # noqa: BLE001
        return frame_urls, None, None, (
            f"chain: composite upload failed ({type(exc).__name__}: {exc})"
        )
    composite_url = output_url(key)
    if not composite_url:
        return frame_urls, None, None, "chain: output_url returned None"

    anchor_asset = source_video or (images[0] if images else None)
    spec = None
    if anchor_asset is not None:
        spec = build_stacked_quote_card_spec(
            composite_image_url=composite_url,
            asset_id=anchor_asset.id,
            duration_s=duration_s,
            target_language=target_language,
            brand=brand,
            brand_ref=brand_ref,
        )
    return frame_urls, composite_url, spec, None


def _add_render_step(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    node: WorkflowStep,
    output_id: UUID,
    label: str | None,
) -> None:
    """Render fan-out: the render worker picks the output row by
    ``render_status=PENDING``; the WorkflowStep is the UI progress mirror
    (mirrors select_clips's contract verbatim)."""
    db.add(
        WorkflowStep(
            run_id=run.id,
            kind="render",
            status="pending",
            seq=int(node.seq) + 1,
            inputs=[str(node.id)],
            spec={
                "output_id": str(output_id),
                **({"summary": label} if label else {}),
            },
        )
    )


async def _materialize_quote_card_outputs(
    *,
    db: AsyncSession,
    run: WorkflowRun,
    node: WorkflowStep,
    project: Project,
    persona,
    quotes: list[dict],
    target_language: str,
    source_language: str | None,
    caption_mode: str | None,
    quote_alt_language: str | None = None,
    needs_speaker_frame: bool = False,
    core_idea: str | None = None,
) -> list[UUID]:
    """Quote-cards → quote_frame image Outputs + optional motion clip (§2.2).

    叠卡 = 金句卡本体 (v3, ADR-048 第 7 条) + 帧卡 Output 化 (P2,
    2026-08-28): a chain of N≥2 entries materializes as

    - N frame-card ``quote_frame`` Outputs (one per entry: its frame +
      its caption block, ``files.image``) — independently shareable;
    - ONE composite ``quote_frame`` Output (the form A/B cascade PNG)
      whose ``source_ref.parents`` names the frame cards — the canvas
      draws the N→1 lineage off ``parents``;
    - ONE motion ``clip`` Output (Ken-Burns MP4 on the composite) as a
      CHILD of the composite (``parents=[composite_id]``) — only when an
      anchor asset exists (video else photo); never the main promise.

    N=1 keeps the single video card via ``build_quote_card_spec`` when a
    source video exists; otherwise a single frame card (photo or dark
    text-only — the no-video paths no longer drop the dish).

    Returns the list of new Output ids. The composite IS the dish: when
    it fails the whole chain drops (``quote_card_chain_drop`` warning,
    empty list) — frame cards without their stack are orphan strips and
    are never served standalone, so no partial family is materialized.
    """
    assets = await _list_assets(db, project.id)
    source_video: Asset | None = next(
        (
            a for a in assets
            if a.type == AssetType.VIDEO
            and a.file_url
            and (a.meta or {}).get("words")
        ),
        None,
    )
    images: list[Asset] = [
        a for a in assets if a.type == AssetType.IMAGE and a.file_url
    ]
    if source_video is None:
        logger.info(
            "quote_card_no_video_source",
            project_id=str(project.id),
            workflow_step_id=str(node.id),
            images=len(images),
        )

    # Source language: prefer the explicit arg (chat may have stamped it on
    # run.context), else the ASR-detected language on the source asset's
    # meta block, else the project's default language.
    resolved_source_lang = source_language
    if not resolved_source_lang and source_video is not None:
        resolved_source_lang = (source_video.meta or {}).get("language")
    if not resolved_source_lang:
        resolved_source_lang = project.language or "en"

    brand_cfg, _ = await resolve_brand_block(db, persona)
    brand = brand_from_block(brand_cfg)
    brand_ref = persona.id if persona is not None else None
    # Quote cards share the caption catalog with talking-head clips (RENDERING
    # §3 / RECIPES §3) — preset + position come from the persona's brand
    # block, same path select_clips uses (clip_spec never overrides persona
    # choice). The persona skin can opt into "stacking" for the bilingual
    # layout or "clean-bottom" for the simple single-line look.
    cap_style_raw = brand_cfg.get("captionStylePreset")
    cap_style = cap_style_raw if isinstance(cap_style_raw, str) else "clean-bottom"
    cap_pos = brand_cfg.get("captionPosition")
    # Music mood rides the persona skin block (its default is "calm" — the
    # system default skin's value, never a per-call-site hardcode).
    music_mood = str(brand_cfg.get("musicMood") or "calm")

    created_ids: list[UUID] = []
    # Localized label via the runtime registry (matches select_clips / morph
    # paths — the label follows the run's pinned UI language). None when no
    # render_cls is registered or no project is attached (spec["summary"]
    # becomes optional in that case).
    label = await _render_step_label(db, run)

    if not quotes:
        return []

    # ----- 叠卡本体 (chain length >= 2, §2.2 frame cards + composite) ----
    if len(quotes) >= 2:
        captions = _chain_captions(quotes, caption_mode)
        anchor = quotes[0]
        attribution = str(anchor.get("attribution") or "") or None
        frame_urls, composite_url, spec, err = await _build_quote_chain_artifacts(
            project,
            chain=quotes,
            captions=captions,
            needs_speaker_frame=needs_speaker_frame,
            attribution=attribution,
            source_video=source_video,
            images=images,
            target_language=target_language,
            brand=brand,
            brand_ref=brand_ref,
        )
        if composite_url is None:
            logger.warning(
                "quote_card_chain_drop",
                project_id=str(project.id),
                workflow_step_id=str(node.id),
                reason=err,
            )
            await db.flush()
            return []

        # N frame-card Outputs — the composite's named parents.
        frame_ids: list[UUID] = []
        for i, (q, url) in enumerate(zip(quotes, frame_urls, strict=True)):
            frame_output = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="quote_frame",
                language=target_language,
                provenance="real",
                payload=QuoteFrame(
                    quote=captions[i].primary,
                    attribution=str(q.get("attribution") or ""),
                    aspect="9:16",
                ).model_dump(mode="json"),
                files={"image": url},
                source_ref={
                    "quote_frame": True,
                    "quote_index": i,
                    "quotable_line_id": q.get("quotable_line_id"),
                    **(
                        {"asset_id": str(source_video.id)}
                        if source_video is not None
                        else {}
                    ),
                },
            )
            db.add(frame_output)
            await db.flush()
            frame_ids.append(frame_output.id)
            created_ids.append(frame_output.id)

        # The composite — one image Output, parents = the frame cards.
        composite_output = Output(
            project_id=project.id,
            workflow_step_id=node.id,
            type="quote_frame",
            language=target_language,
            provenance="real",
            payload=QuoteFrame(
                quote=str(core_idea or anchor.get("quote") or ""),
                attribution=str(anchor.get("attribution") or ""),
                aspect="9:16",
            ).model_dump(mode="json"),
            files={"image": composite_url},
            source_ref={
                "quote_card": True,
                "quote_chain": True,
                "chain_length": len(quotes),
                "needs_speaker_frame": needs_speaker_frame,
                "parents": [str(fid) for fid in frame_ids],
                "quotable_line_ids": [q.get("quotable_line_id") for q in quotes],
                "core_idea": core_idea,
                **(
                    {"asset_id": str(source_video.id)}
                    if source_video is not None
                    else {}
                ),
            },
        )
        db.add(composite_output)
        await db.flush()
        created_ids.append(composite_output.id)

        # The motion MP4 — a CHILD of the composite, never the main
        # promise. Only when an anchor asset exists (a pure-text chain
        # ships the cards alone).
        if spec is not None:
            clip_output = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="clip",
                language=target_language,
                provenance="real",
                payload=ClipPayload(
                    hook=str(anchor.get("quote", "")),
                    title_options=(
                        [str(anchor.get("attribution", ""))]
                        if anchor.get("attribution")
                        else []
                    ),
                    music_mood=music_mood,
                    duration=int(_QUOTE_CARD_CHAIN_DURATION_S),
                ).model_dump(mode="json"),
                source_ref={
                    "quote_card": True,
                    "quote_chain": True,
                    "chain_length": len(quotes),
                    "parents": [str(composite_output.id)],
                    **(
                        {"asset_id": str(source_video.id)}
                        if source_video is not None
                        else {}
                    ),
                },
                render_spec=spec.model_dump(mode="json"),
                render_status=RenderStatus.PENDING,
            )
            db.add(clip_output)
            await db.flush()
            created_ids.append(clip_output.id)

            _add_render_step(
                db, run=run, node=node, output_id=clip_output.id, label=label
            )
            await db.flush()
        return created_ids

    # ----- N=1: the same dish as a single card -------------------------
    quote = quotes[0]
    if source_video is not None:
        spec = build_quote_card_spec(
            source_video,
            quote,
            target_language=target_language,
            source_language=str(resolved_source_lang),
            caption_mode=caption_mode,
            brand=brand,
            brand_ref=brand_ref,
            aspect="9:16",
            caption_style_preset=cap_style,
            caption_position=cap_pos,
            alt_language=quote_alt_language,
        )
        # spec=None = the quote lacks a time-bind — fall through to the
        # frame card below instead of dropping the dish.
        if spec is not None:
            spec_dict = spec.model_dump(mode="json")
            clip_output = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="clip",
                language=target_language,
                # Real — the kept video span IS the user's real footage. The
                # caption text overlay is text, not synthesized visual; matches
                # select_clips's provenance="real" semantics (slice-of-real).
                provenance="real",
                payload=ClipPayload(
                    hook=str(quote.get("quote", "")),
                    title_options=[str(quote.get("attribution", ""))] if quote.get("attribution") else [],
                    music_mood=music_mood,
                    duration=int((quote.get("source_end") or 0) - (quote.get("source_start") or 0)),
                ).model_dump(mode="json"),
                source_ref={
                    "quote_card": True,
                    # 0-based chain position — the N≥2 frame cards write
                    # their enumerate index; N=1 is position 0 of its chain
                    # of one (2026-08-29 基址统一: future per-quote
                    # refinement addresses by this field, one base only).
                    "quote_index": 0,
                    "asset_id": str(source_video.id),
                    "start_seconds": quote.get("source_start"),
                    "end_seconds": quote.get("source_end"),
                    "quotable_line_id": quote.get("quotable_line_id"),
                },
                render_spec=spec_dict,
                render_status=RenderStatus.PENDING,
            )
            db.add(clip_output)
            await db.flush()
            created_ids.append(clip_output.id)

            _add_render_step(
                db, run=run, node=node, output_id=clip_output.id, label=label
            )
            await db.flush()
            return created_ids

    # N=1 without a usable spec — one frame card. Frame priority mirrors
    # the chain path (2026-08-29 N=1/N≥2 对齐): the quote's own ``frame_at``
    # grab from the source video first, then the project's photos, else the
    # dark text-only card. 纯文稿路径不再掉卡 (P2 宽槽, 2026-08-28).
    captions = _chain_captions([quote], caption_mode)
    frame_img = None
    frame_from_video = False
    if source_video is not None:
        at = _entry_frame_at(quote)
        if at is not None:
            video_bytes = await _download_bytes(
                stream_url(source_video.file_url) if source_video.file_url else None
            )
            if video_bytes:
                try:
                    grabbed = await asyncio.to_thread(
                        extract_video_frames, video_bytes, [at]
                    )
                    frame_img = grabbed[0] if grabbed else None
                    frame_from_video = frame_img is not None
                except Exception:  # noqa: BLE001
                    frame_img = None  # photo / dark fallbacks absorb the hole
    if frame_img is None:
        photo_bytes = await _download_bytes(
            stream_url(images[0].file_url) if images else None
        )
        frame_img = _open_image(photo_bytes) if photo_bytes else None
    png = await asyncio.to_thread(
        composite_frame_card,
        frame=frame_img,
        caption=captions[0],
        attribution=str(quote.get("attribution") or "") or None,
    )
    digest = hashlib.md5(png).hexdigest()[:8]
    try:
        key = await save_output(
            project.id, project.user_id, f"quote-frame-{digest}.png", png
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "quote_card_frame_drop",
            project_id=str(project.id),
            workflow_step_id=str(node.id),
            reason=f"upload failed ({type(exc).__name__}: {exc})",
        )
        return []
    url = output_url(key)
    if not url:
        return []
    frame_output = Output(
        project_id=project.id,
        workflow_step_id=node.id,
        type="quote_frame",
        language=target_language,
        provenance="real",
        payload=QuoteFrame(
            quote=captions[0].primary,
            attribution=str(quote.get("attribution") or ""),
            aspect="9:16",
        ).model_dump(mode="json"),
        files={"image": url},
        source_ref={
            "quote_frame": True,
            # 0-based — same addressing contract as the chain family above.
            "quote_index": 0,
            "quotable_line_id": quote.get("quotable_line_id"),
            # Lineage parity with the chain frames (they always carry it).
            **({"asset_id": str(source_video.id)} if frame_from_video else {}),
        },
    )
    db.add(frame_output)
    await db.flush()
    created_ids.append(frame_output.id)
    return created_ids


async def _sweep_stale_derivative_outputs(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    node: WorkflowStep,
    project: Project,
    derivative_type: DerivativeType,
) -> None:
    """Idempotency sweep, sibling-safe (per-slot fan-out).

    Same-type outputs produced by THIS run's same-kind nodes are their own
    slots' products — only prior products (other runs' steps, step-less
    rows, or THIS step's own prior attempt — a verify bounce re-runs the
    same WorkflowStep row, and its products are stale by definition) are
    cleared. Two sibling write_post nodes can therefore never delete each
    other's output.

    quote-cards §2.2 byproducts (frame cards + the motion clip) die with
    their producer: a quotes re-run replaces the whole family. Scope =
    rows produced by write_quotes steps OUTSIDE this run, plus THIS step's
    own prior attempt (without the same-step clause, bounced families
    stacked on the canvas, 2026-08-28 root-fix). select_clips' own clip
    rows are never touched (their workflow_step_id belongs to a different
    kind). Exercised LLM-free by scripts/accept_quote_card_family.py §7.
    """
    sibling_step_ids = (
        select(WorkflowStep.id)
        .where(WorkflowStep.run_id == run.id, WorkflowStep.kind == node.kind)
        .scalar_subquery()
    )
    await db.execute(
        delete(Output).where(
            Output.project_id == project.id,
            Output.type == derivative_type.value,
            or_(
                Output.workflow_step_id.is_(None),
                Output.workflow_step_id == node.id,
                Output.workflow_step_id.notin_(sibling_step_ids),
            ),
        )
    )
    if derivative_type == DerivativeType.QUOTES:
        quotes_step_ids = (
            select(WorkflowStep.id)
            .where(WorkflowStep.kind == "write_quotes")
            .scalar_subquery()
        )
        await db.execute(
            delete(Output).where(
                Output.project_id == project.id,
                Output.type.in_(["quote_frame", "clip"]),
                Output.workflow_step_id.in_(quotes_step_ids),
                or_(
                    Output.workflow_step_id == node.id,
                    Output.workflow_step_id.notin_(sibling_step_ids),
                ),
            )
        )


class DerivativeWriterNode(NodeBase):
    """Shared body for the four copy-writer nodes; each package declares a
    thin subclass with its own ``writer`` (the tool-private agent)."""

    writer: Agent
    needs_director = True
    # 2026-08-24 lift: copy-writers (write_post / write_quotes /
    # write_carousel / write_article) draft from the user prompt + persona
    # style alone when no source material is attached — the prior
    # ``(TRANSCRIPT,)`` gate hard-422ed "I have no material, write me a
    # post" requests, which was hostile to the common "just topic X" case.
    # The gate moves to the prompt layer: PlanAgent recognizes the
    # no-material case and tells the user (in echo prose + soft reason)
    # that the draft comes from prompt + persona; if material shows up
    # later, the next turn re-docks a richer book. needs_director stays
    # True so the director's persona/style hand-off survives the empty
    # material_excerpt path.
    requires = ()
    produces_outputs = True
    # Per-writer quotation declarations (P4): completion bounds grounded in
    # the output schema's size class; ``images_per_run`` = exact image
    # generations (the quote card's 1, skipped on targeted regeneration).
    completion_bounds: tuple[int, int] = (400, 1500)
    images_per_run: int = 0

    @property
    def derivative_type(self) -> DerivativeType:
        """The DerivativeType IS the output type (N-32 single source)."""
        return DerivativeType(self.output_type)

    def estimate(self, ctx: dict) -> dict | None:
        """One writer call: prompt = trimmed asset texts + understanding /
        storyboard / persona context overhead; completion per the writer's
        size class."""
        chars = min(ctx["text_chars"], MAX_CHARS_PER_TEXT * ctx["text_count"])
        prompt = token_bounds(chars)
        prompt[0] += 800
        prompt[1] += 3000
        units: dict[str, float] = {}
        if self.images_per_run and not (ctx["spec"] or {}).get("target_id"):
            units["images"] = float(self.images_per_run)
        return estimate_mechanical(
            units, prompt=prompt, completion=list(self.completion_bounds)
        )

    async def _generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        understanding: MaterialUnderstanding,
        storyboard: Storyboard,
        feedback: str | None = None,
    ) -> dict:
        """Generate a single derivative via the package's writer declaration.

        Returns the agent's generated content as a plain dict. Callers are
        responsible for persisting it. ``feedback`` (期 3 质检打回) rides the
        funnel's repair echo — the writer sees the failed checks verbatim.
        """
        result = await self.writer.call(
            asset_texts=asset_texts,
            context=context,
            understanding=understanding,
            storyboard=storyboard,
            repair_feedback=feedback,
        )
        return validate_derivative_content(self.derivative_type, result.model_dump())

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Generate one derivative output (post/quotes/carousel/article).

        With ``spec.target_id`` set this is a targeted regeneration: the existing
        row is updated in place (its storyboard now comes from a real upstream
        director_plan node — the fabricated-plan path is gone).
        """
        derivative_type = self.derivative_type
        ctx = run.context or {}
        # 质检打回 (期 3): a bounced round's feedback rides the spec exactly
        # once — pop it so a later targeted regen never eats stale feedback.
        # The row write goes through _pop_spec_field's own session (D9,
        # 2026-08-28): an ORM assignment here would dirty the Session-2 node,
        # and the next autoflush would lock this row for the rest of the run
        # — deadlocking this runner's own display writers.
        spec = dict(node.spec or {})
        feedback = spec.pop("feedback", None)
        if feedback is not None:
            await _pop_spec_field(node.id, "feedback")
        slot = _node_slot(node, ctx, derivative_type.value)
        target_id = node.spec.get("target_id")
        # Language resolves per slot first, then the node's targeted language,
        # then the task-book language.
        target_language = (
            (slot.language if slot else None)
            or node.spec.get("target_language")
            or ctx.get("target_language", "en")
        )

        await _set_stage(node.id, "writing_copy")

        asset_texts = await collect_asset_texts(db, project.id)
        persona = await resolve_persona(db, project)
        generation_context = _generation_context(run, project, persona)
        generation_context.target_language = target_language
        # 2026-08-25 Phase 2: caption_mode rides run.context verbatim —
        # write_quotes (Phase 2 / RECIPES §4.6.2) reads it to know whether
        # to call the translator for quote_alt. None for chains that don't
        # produce captions (write_post / write_carousel / write_article).
        generation_context.caption_mode = ctx.get("caption_mode")
        # quote-cards §2.3/D4 (2026-08-28): resolve the run's language pair
        # once — the translator (quotes enrich) reads quote_alt_language,
        # the materializer reads source_language, and the bilingual →
        # source_only narrowing (no distinct alt language exists) is
        # stamped HERE so every downstream consumer agrees.
        if derivative_type == DerivativeType.QUOTES:
            resolved_source = ctx.get("source_language") or await _project_source_language(
                db, project
            )
            alt_language = derive_quote_alt_language(
                resolved_source,
                target_language,
                project.language,
                ctx.get("target_language"),
            )
            generation_context.source_language = resolved_source
            generation_context.quote_alt_language = alt_language
            if generation_context.caption_mode == "bilingual" and alt_language is None:
                generation_context.caption_mode = "source_only"
        understanding, storyboard = await _load_director_outputs(db, node)

        # Narrow the storyboard to THIS slot: same-type sibling slots (e.g. an
        # English and a German post) are addressed by the slot's ordinal, which
        # compile_graph and director_plan both derive from the canonical order.
        same_type = [s for s in storyboard.slots if s.slot == derivative_type.value]
        if same_type:
            slot_index = int((node.spec or {}).get("slot_index") or 0)
            my_slot = same_type[min(slot_index, len(same_type) - 1)]
            storyboard = storyboard.model_copy(update={"slots": [my_slot]})

        content = await self._generate(
            asset_texts=asset_texts,
            context=generation_context,
            understanding=understanding,
            storyboard=storyboard,
            feedback=feedback,
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
            await _fill_summary(
                node.id, self.kind, tag=slot_tag(slot),
                ui_language=ui_lang_of(run, project), word_count=_count_words(content),
            )
            return [output.id]

        # Idempotency, sibling-safe (per-slot fan-out): only prior products
        # (other runs' steps, step-less rows, or THIS step's own prior
        # attempt — a verify bounce re-runs the same WorkflowStep row) are
        # cleared; sibling same-kind nodes never delete each other's output.
        await _sweep_stale_derivative_outputs(
            db, run=run, node=node, project=project, derivative_type=derivative_type
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

        # Quote cards: build a 9:16 clip-spec per quote and persist it as a
        # sibling "clip" Output so the render worker (PENDING claim) picks it
        # up. 叠卡 = 卡本体 (v3): the chain materializes as ONE composite
        # cascade PNG; a chain of 1 builds the single video card
        # (RECIPES §4.6.2).
        if derivative_type == DerivativeType.QUOTES:
            quotes = content.get("quotes", []) if isinstance(content, dict) else []
            if quotes:
                await _set_stage(node.id, "building_specs")
                # The writer's verdict on whether the cascade needs a speaker
                # frame on top, plus the core-idea thesis sentence that drove
                # the chain selection. Both ride on the writer content —
                # never re-derive.
                needs_speaker_frame = bool(
                    (content.get("needs_speaker_frame") if isinstance(content, dict) else False)
                )
                await _materialize_quote_card_outputs(
                    db=db,
                    run=run,
                    node=node,
                    project=project,
                    persona=persona,
                    quotes=quotes,
                    target_language=target_language,
                    source_language=generation_context.source_language,
                    caption_mode=generation_context.caption_mode,
                    quote_alt_language=generation_context.quote_alt_language,
                    needs_speaker_frame=needs_speaker_frame,
                    core_idea=(
                        content.get("core_idea") if isinstance(content, dict) else None
                    ),
                )

        await _fill_summary(
            node.id, self.kind, tag=slot_tag(slot),
            ui_language=ui_lang_of(run, project), word_count=_count_words(content),
        )
        return [output.id]
