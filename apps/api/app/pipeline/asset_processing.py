"""Asset processing dispatch.

A worker hands a claimed asset to :func:`process_asset`, which runs the
processor chain registered for the asset's type and writes the terminal state
(``COMPLETED`` with its outputs, or ``FAILED`` with an error). This module is
the single seam where heavier processors plug in:

- EVERY type -> content hash first (``meta.content_sha256`` — the
  content-addressing key for cross-project understanding reuse, 期 1 前移)
- VIDEO -> ASR (faster-whisper: transcript + word timestamps) -> speaker_map
  (ADR-045: form gate + mouth-energy attribution, the asset-level
  who-speaks-when fact) -> prosody (产物质量线期 1: F0/energy per-word stats,
  emphasis peaks, filler regions — the acoustic half of the beat map)
- AUDIO -> ASR -> prosody (speaker_map stays video-only: its signal is visual)
- IMAGE -> visual_anchors (期 1: deterministic faces / subject box / safe
  area — the original image itself still feeds the agents)
- SLIDES -> per-page render + OCR (future; today plain PDF text)

A type maps to an ORDERED chain of processors (ADR-045 D4's "第二处理器"
shape): each processor receives the asset and the accumulated prior result
and returns its own delta; deltas merge shallowly (``meta`` dicts combine,
scalar fields take the last non-None value).
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset
from app.pipeline.extraction import extract_text, render_pdf_pages_and_upload
from app.pipeline.graph import media_missing
from app.pipeline.prosody import prosody_processor
from app.pipeline.speaker_map import speaker_map_processor
from app.pipeline.visual_anchors import visual_anchors_processor
from app.providers.storage import download_to_temp, get_project_output_dir

logger = structlog.get_logger()


@dataclass
class ProcessResult:
    """What a processor produces; applied to the asset by :func:`process_asset`."""

    extracted_text: str | None = None
    transcript: str | None = None
    duration_seconds: int | None = None
    slide_pages: list[str] | None = None  # object storage keys to rendered PDF pages
    meta: dict[str, Any] = field(default_factory=dict)

    def merge(self, delta: "ProcessResult") -> "ProcessResult":
        """Fold a processor's delta into the accumulated result."""
        if delta.extracted_text is not None:
            self.extracted_text = delta.extracted_text
        if delta.transcript is not None:
            self.transcript = delta.transcript
        if delta.duration_seconds is not None:
            self.duration_seconds = delta.duration_seconds
        if delta.slide_pages is not None:
            self.slide_pages = delta.slide_pages
        self.meta.update(delta.meta)
        return self


# A processor turns an asset into a ProcessResult delta (or an empty one for
# media types with no processor yet). ``prior`` is the accumulated result of
# the processors before it in the chain (empty for the first).
Processor = Callable[[Asset, ProcessResult], Awaitable[ProcessResult]]

# Strong refs for fire-and-forget warm tasks (the worker's node-task set is
# the same pattern — a bare create_task can be GC'd mid-flight).
_warm_tasks: set[asyncio.Task] = set()


async def has_renderable_media(db: AsyncSession, project_id: UUID) -> bool:
    """Whether the project has a renderable media source (file-backed).

    The predicate's single home is the MEDIA birthplace requirement
    (``graph.media_missing``); this helper keeps the project_id-shaped call
    the chat plan path uses for the clips-needs-media clarification reason.
    """
    return not await media_missing(db, project_id)


async def has_any_text_material(db: AsyncSession, project_id: UUID) -> bool:
    """Whether the project has any text-yielding source — transcript /
    past_material / media with extracted text / ASR'd word axis (2026-08-24).

    Sibling of ``has_renderable_media``: the chat plan path's
    ``text_without_material`` reason rides this predicate (the prior
    ``requires=(TRANSCRIPT,)`` gate hard-422ed legitimate "I have nothing,
    write me a post" requests). Mirrors ``_TranscriptRequirement.missing``
    in ``graph.py`` — kept as a parallel helper so the chat layer doesn't
    re-import the graph predicate just to check it.
    """
    result = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project_id,
            or_(
                Asset.transcript.isnot(None),
                Asset.extracted_text.isnot(None),
                Asset.meta["words"].isnot(None),
            ),
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return True
    # Words-in-waiting: a text-typed asset with bytes or a media-typed
    # asset with bytes will yield words at extraction / preprocess — they
    # count as material under the soft signal.
    derivable = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project_id,
            Asset.type.in_(
                [
                    AssetType.TRANSCRIPT,
                    AssetType.PAST_MATERIAL,
                    AssetType.VIDEO,
                    AssetType.AUDIO,
                ]
            ),
            Asset.file_url.isnot(None),
        )
        .limit(1)
    )
    return derivable.scalar_one_or_none() is not None


async def _content_hash_processor(asset: Asset, _prior: ProcessResult) -> ProcessResult:
    """Stamp ``meta.content_sha256`` — the content-addressing key the
    understanding digest (v3) builds on, so a user's second upload of the
    same bytes reuses the existing understanding with zero LLM (期 1 前移).

    File bytes when there is a file, the carried text otherwise. Hash
    failures degrade to absence (the digest falls back to per-upload
    identity) — never an asset failure.
    """
    h = hashlib.sha256()
    if asset.file_url:
        path = await download_to_temp(asset.file_url)
        if path is None:
            return ProcessResult()
        try:
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
        finally:
            path.unlink(missing_ok=True)
    else:
        text = (asset.extracted_text or asset.transcript) or ""
        if not text.strip():
            return ProcessResult()
        h.update(text.encode("utf-8"))
    return ProcessResult(meta={"content_sha256": h.hexdigest()})


async def _extract_text_processor(asset: Asset, _prior: ProcessResult) -> ProcessResult:
    """Extract text from a document-like asset (txt/md/pdf)."""
    if not asset.file_url:
        return ProcessResult()
    return ProcessResult(extracted_text=await extract_text(asset.file_url))


async def _slides_processor(asset: Asset, _prior: ProcessResult) -> ProcessResult:
    """Slides: render PDF pages to images for stills backing.

    The generation agents (content director / clip agent) read slide images
    directly, so we no longer extract OCR text here. Keep the page renders so
    they can be used as visual backing for stills/audiogram clips.
    """
    if not asset.file_url:
        return ProcessResult()
    slide_pages: list[str] | None = None
    if asset.file_url.lower().endswith(".pdf"):
        prefix = f"{get_project_output_dir(asset.project_id, asset.user_id)}/slides-{asset.id}"
        pages = await render_pdf_pages_and_upload(asset.file_url, prefix)
        slide_pages = pages or None
    return ProcessResult(slide_pages=slide_pages)


async def _asr_processor(asset: Asset, _prior: ProcessResult) -> ProcessResult:
    """Transcribe a video/audio asset to text + word-level timestamps."""
    path = await download_to_temp(asset.file_url)
    if path is None:
        return ProcessResult()

    from app.providers.asr import transcribe  # lazy: heavy model deps

    try:
        # Transcription is CPU-bound; run it in a thread so the async event loop
        # stays responsive (worker concurrency).
        result = await asyncio.to_thread(transcribe, path)
        duration = result.get("duration")
        return ProcessResult(
            transcript=result["transcript"],
            duration_seconds=int(duration) if duration else None,
            meta={"words": result["words"], "language": result["language"]},
        )
    finally:
        path.unlink(missing_ok=True)


async def _noop_processor(asset: Asset, _prior: ProcessResult) -> ProcessResult:
    """Placeholder for types with no text/transcript processor.

    IMAGE assets are consumed directly by the generation agents as raw media,
    so no preprocessing is needed here. VOICE_SAMPLE is only used for voice
    cloning.
    """
    return ProcessResult()


PROCESSORS: dict[AssetType, list[Processor]] = {
    # Every chain opens with the content hash (the understanding digest's
    # addressing key — cheap, uniform, degrade-on-error).
    AssetType.TRANSCRIPT: [_content_hash_processor, _extract_text_processor],
    AssetType.PAST_MATERIAL: [_content_hash_processor, _extract_text_processor],
    AssetType.SLIDES: [_content_hash_processor, _slides_processor],  # PDF page renders only
    # speaker_map is VIDEO's second processor (ADR-045 D4); AUDIO stays
    # ASR-only for it — the attribution signal is visual. prosody is the
    # third/second for VIDEO/AUDIO (its signal is audio — both carry one).
    AssetType.VIDEO: [_content_hash_processor, _asr_processor, speaker_map_processor, prosody_processor],
    AssetType.AUDIO: [_content_hash_processor, _asr_processor, prosody_processor],
    AssetType.VOICE_SAMPLE: [_content_hash_processor, _noop_processor],
    # IMAGE: content hash + deterministic visual anchors (faces / subject /
    # safe area, 期 1); the agents still consume the original image itself.
    AssetType.IMAGE: [_content_hash_processor, visual_anchors_processor],
}


async def process_asset(asset_id: UUID) -> None:
    """Run the registered processor for an asset and persist its terminal state.

    Assumes the asset has already been claimed (flipped to PROCESSING). On
    success writes the processor outputs + COMPLETED; on any error writes FAILED
    with the message. Uses its own session — safe to call from the worker.
    """
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, asset_id)
        if asset is None:
            logger.warning("process_asset_missing", asset_id=str(asset_id))
            return

        try:
            chain = PROCESSORS.get(asset.type, [_noop_processor])
            result = ProcessResult()
            for processor in chain:
                result.merge(await processor(asset, result))
            if result.extracted_text is not None:
                asset.extracted_text = result.extracted_text
            if result.transcript is not None:
                asset.transcript = result.transcript
            if result.duration_seconds is not None:
                asset.duration_seconds = result.duration_seconds
            if result.slide_pages is not None:
                asset.slide_pages = result.slide_pages
            if result.meta:
                asset.meta = result.meta
            asset.processed_at = datetime.now(UTC)
            asset.processing_status = AssetStatus.COMPLETED
            asset.processing_error = None
            await db.commit()
            logger.info(
                "asset_processed",
                asset_id=str(asset_id),
                type=asset.type.value,
                chars=len((result.transcript or result.extracted_text) or ""),
            )
            # 期 1 素材理解前移: once the whole project set is COMPLETED, the
            # understanding materializes before any run asks (the warm itself
            # re-checks set completeness). Fire-and-forget so the tick moves
            # on; persona-bound assets (project_id=None) never warm.
            if asset.project_id is not None:
                from app.pipeline.node_runners import (
                    warm_understanding,  # deferred: runtime-only edge
                )

                task = asyncio.create_task(warm_understanding(asset.project_id))
                _warm_tasks.add(task)
                task.add_done_callback(_warm_tasks.discard)
        except Exception as e:  # noqa: BLE001 — record any failure on the row
            logger.error("asset_processing_failed", asset_id=str(asset_id), error=str(e))
            asset.processing_status = AssetStatus.FAILED
            asset.processing_error = str(e)
            await db.commit()
