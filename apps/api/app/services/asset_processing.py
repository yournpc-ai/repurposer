"""Asset processing dispatch.

A worker hands a claimed asset to :func:`process_asset`, which runs the
processor registered for the asset's type and writes the terminal state
(``COMPLETED`` with its outputs, or ``FAILED`` with an error). This module is
the single seam where heavier processors plug in:

- VIDEO / AUDIO  -> ASR (faster-whisper), producing transcript + word timestamps
- SLIDES         -> per-page render + OCR (future; today plain PDF text)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset
from app.services.extraction import extract_text
from app.services.storage import resolve_file_path

logger = structlog.get_logger()


@dataclass
class ProcessResult:
    """What a processor produces; applied to the asset by :func:`process_asset`."""

    extracted_text: str | None = None
    transcript: str | None = None
    duration_seconds: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# A processor turns an asset into a ProcessResult (or an empty one for media
# types with no processor yet).
Processor = Callable[[Asset], ProcessResult]


def _extract_text_processor(asset: Asset) -> ProcessResult:
    """Extract text from a document-like asset (txt/md/pdf)."""
    if not asset.file_url:
        return ProcessResult()
    return ProcessResult(extracted_text=extract_text(asset.file_url))


def _asr_processor(asset: Asset) -> ProcessResult:
    """Transcribe a video/audio asset to text + word-level timestamps."""
    path = resolve_file_path(asset.file_url)
    if path is None or not path.is_file():
        return ProcessResult()

    from app.services.asr import transcribe  # lazy: heavy model deps

    result = transcribe(path)
    duration = result.get("duration")
    return ProcessResult(
        transcript=result["transcript"],
        duration_seconds=int(duration) if duration else None,
        meta={"words": result["words"], "language": result["language"]},
    )


def _noop_processor(asset: Asset) -> ProcessResult:
    """Placeholder for types with no processor yet (voice samples, images)."""
    return ProcessResult()


PROCESSORS: dict[AssetType, Processor] = {
    AssetType.TRANSCRIPT: _extract_text_processor,
    AssetType.PAST_MATERIAL: _extract_text_processor,
    AssetType.SLIDES: _extract_text_processor,  # PDF text for now; OCR later
    AssetType.VIDEO: _asr_processor,
    AssetType.AUDIO: _asr_processor,
    AssetType.VOICE_SAMPLE: _noop_processor,
    AssetType.IMAGE: _noop_processor,
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
            processor = PROCESSORS.get(asset.type, _noop_processor)
            result = processor(asset)
            if result.extracted_text is not None:
                asset.extracted_text = result.extracted_text
            if result.transcript is not None:
                asset.transcript = result.transcript
            if result.duration_seconds is not None:
                asset.duration_seconds = result.duration_seconds
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
        except Exception as e:  # noqa: BLE001 — record any failure on the row
            logger.error("asset_processing_failed", asset_id=str(asset_id), error=str(e))
            asset.processing_status = AssetStatus.FAILED
            asset.processing_error = str(e)
            await db.commit()
