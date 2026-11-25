"""Owner-scoped NarrationAlignment storage, worker claiming and READY freezing."""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.alignment import (
    NARRATION_ALGORITHM,
    NARRATION_NORMALIZATION,
    NarrationPayload,
    alignment_content_digest,
    alignment_timing_digest,
)
from app.editing.schemas import speech_text_digest
from app.editing.timing import SOURCE_TIMEBASE

_LEASE_SECONDS = 3600


class AlignmentStoreError(ValueError):
    pass


def _session():
    from app.models.database import AsyncSessionLocal

    return AsyncSessionLocal()


def _digests(row, payload: NarrationPayload) -> tuple[str, str]:
    kwargs = {
        "text_digest": row.text_digest,
        "audio_digest": row.audio_digest,
        "algorithm": row.algorithm,
        "normalization_version": row.normalization_version,
        "provider": row.provider,
        "model": row.model,
    }
    return alignment_timing_digest(payload, **kwargs), alignment_content_digest(payload, **kwargs)


def alignment_read(row) -> dict[str, Any]:
    return {
        "alignment_id": str(row.id),
        "audio_snapshot_id": str(row.audio_snapshot_id),
        "status": row.status,
        "text": row.text,
        "text_digest": row.text_digest,
        "audio_digest": row.audio_digest,
        "algorithm": row.algorithm,
        "normalization_version": row.normalization_version,
        "provider": row.provider,
        "model": row.model,
        "source_timebase": row.source_timebase,
        "timing_digest": row.timing_digest,
        "content_digest": row.content_digest,
        "payload": row.payload,
        "error": row.error,
    }


async def get_alignment(db: AsyncSession, *, owner_id: UUID, alignment_id: UUID):
    from app.models.tables import NarrationAlignment

    row = await db.get(NarrationAlignment, alignment_id)
    if row is None or row.owner_id != owner_id:
        raise AlignmentStoreError("narration alignment is not accessible to this owner")
    return row


async def request_alignment(
    *, owner_id: UUID, audio_snapshot_id: UUID, text: str
) -> dict[str, Any]:
    from app.models.tables import NarrationAlignment, SourceSnapshot
    from app.config import settings

    if not text.strip():
        raise AlignmentStoreError("narration alignment needs the exact nonblank final script")
    text_digest = speech_text_digest(text)
    async with _session() as db:
        snapshot = await db.get(SourceSnapshot, audio_snapshot_id)
        if snapshot is None or snapshot.owner_id != owner_id or snapshot.kind != "audio":
            raise AlignmentStoreError("narration alignment needs an owned AUDIO SourceSnapshot")
        if snapshot.duration_ticks is None or snapshot.duration_ticks <= 0:
            raise AlignmentStoreError("the AUDIO SourceSnapshot has no real duration")
        values = {
            "owner_id": owner_id,
            "audio_snapshot_id": snapshot.id,
            "text": text,
            "text_digest": text_digest,
            "audio_digest": snapshot.digest,
            "algorithm": NARRATION_ALGORITHM,
            "normalization_version": NARRATION_NORMALIZATION,
            "provider": "faster-whisper",
            "model": settings.asr_model,
            "source_timebase": SOURCE_TIMEBASE,
            "payload": {},
            "status": "PENDING",
        }
        inserted = (
            await db.execute(
                pg_insert(NarrationAlignment)
                .values(**values)
                .on_conflict_do_nothing(
                    constraint="uq_narration_alignments_source_script_algorithm"
                )
                .returning(NarrationAlignment.id)
            )
        ).first()
        await db.commit()
        if inserted is not None:
            row = await db.get(NarrationAlignment, inserted[0])
        else:
            row = await db.scalar(
                select(NarrationAlignment).where(
                    NarrationAlignment.owner_id == owner_id,
                    NarrationAlignment.audio_snapshot_id == snapshot.id,
                    NarrationAlignment.text_digest == text_digest,
                    NarrationAlignment.algorithm == NARRATION_ALGORITHM,
                    NarrationAlignment.normalization_version == NARRATION_NORMALIZATION,
                    NarrationAlignment.provider == "faster-whisper",
                    NarrationAlignment.model == settings.asr_model,
                )
            )
        if row is None:
            raise AlignmentStoreError("narration alignment request could not be resolved")
        return alignment_read(row)


async def wait_for_alignment(
    *, owner_id: UUID, alignment_id: UUID, budget_seconds: float = 2.0
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, budget_seconds)
    while True:
        async with _session() as db:
            row = await get_alignment(db, owner_id=owner_id, alignment_id=alignment_id)
            read = alignment_read(row)
        if read["status"] in {"ALIGNED", "READY", "FAILED"} or time.monotonic() >= deadline:
            return read
        await asyncio.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


async def ready_alignment(
    db: AsyncSession, *, owner_id: UUID, alignment_id: UUID
):
    from app.models.tables import SourceSnapshot

    row = await get_alignment(db, owner_id=owner_id, alignment_id=alignment_id)
    if row.status not in {"ALIGNED", "READY"} or not row.content_digest:
        raise AlignmentStoreError("a CompositionVersion can reference only a fixed narration alignment")
    payload = NarrationPayload.model_validate(row.payload)
    timing_digest, content_digest = _digests(row, payload)
    if timing_digest != row.timing_digest or content_digest != row.content_digest:
        raise AlignmentStoreError("READY narration alignment digest validation failed")
    snapshot = await db.get(SourceSnapshot, row.audio_snapshot_id)
    if (
        snapshot is None
        or snapshot.owner_id != owner_id
        or snapshot.kind != "audio"
        or snapshot.digest != row.audio_digest
        or snapshot.duration_ticks != payload.duration_ticks
    ):
        raise AlignmentStoreError("READY narration audio snapshot does not match its frozen facts")
    if row.status == "READY" and any(sentence.status != "aligned" for sentence in payload.sentences):
        raise AlignmentStoreError("READY narration has an unreviewed sentence")
    return row, snapshot, payload


async def claim_pending_alignment(db: AsyncSession) -> tuple[UUID, UUID] | None:
    from app.models.tables import NarrationAlignment

    row = await db.scalar(
        select(NarrationAlignment)
        .where(
            NarrationAlignment.status == "PENDING",
            or_(
                NarrationAlignment.lease_expires_at.is_(None),
                NarrationAlignment.lease_expires_at <= datetime.now(UTC),
            ),
        )
        .order_by(NarrationAlignment.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if row is None:
        return None
    token = uuid4()
    row.status = "PROCESSING"
    row.claim_token = token
    row.lease_expires_at = datetime.now(UTC) + timedelta(seconds=_LEASE_SECONDS)
    row.error = None
    await db.commit()
    return row.id, token


async def reap_stale_alignments(db: AsyncSession) -> None:
    from app.models.tables import NarrationAlignment

    await db.execute(
        update(NarrationAlignment)
        .where(
            NarrationAlignment.status == "PROCESSING",
            NarrationAlignment.lease_expires_at <= datetime.now(UTC),
        )
        .values(status="PENDING", claim_token=None, lease_expires_at=None, error=None)
    )
    await db.commit()


async def _fail(alignment_id: UUID, claim_token: UUID, error: str) -> None:
    from app.models.tables import NarrationAlignment

    async with _session() as db:
        await db.execute(
            update(NarrationAlignment)
            .where(
                NarrationAlignment.id == alignment_id,
                NarrationAlignment.status == "PROCESSING",
                NarrationAlignment.claim_token == claim_token,
            )
            .values(
                status="FAILED",
                error=error[:2000],
                claim_token=None,
                lease_expires_at=None,
            )
        )
        await db.commit()


async def process_narration_alignment(alignment_id: UUID, claim_token: UUID) -> None:
    from app.config import settings
    from app.models.tables import NarrationAlignment, SourceSnapshot
    from app.providers import storage
    from app.providers.asr import transcribe
    from app.tools.video.narration_alignment import align_narration

    try:
        async with _session() as db:
            row = await db.get(NarrationAlignment, alignment_id)
            if (
                row is None
                or row.status != "PROCESSING"
                or row.claim_token != claim_token
            ):
                return
            if row.provider != "faster-whisper" or row.model != settings.asr_model:
                raise AlignmentStoreError(
                    "claimed narration alignment's pinned ASR provider/model is not active; "
                    "request a new alignment with the current model"
                )
            snapshot = await db.get(SourceSnapshot, row.audio_snapshot_id)
            if (
                snapshot is None
                or snapshot.owner_id != row.owner_id
                or snapshot.kind != "audio"
                or snapshot.digest != row.audio_digest
                or snapshot.duration_ticks is None
            ):
                raise AlignmentStoreError("claimed narration audio snapshot failed owner/digest validation")
            text = row.text
            duration_ticks = snapshot.duration_ticks
            storage_key = snapshot.storage_key

        data = await storage.read(storage_key)
        import hashlib
        if hashlib.sha256(data).hexdigest() != row.audio_digest:
            raise AlignmentStoreError("stored narration bytes do not match the AUDIO snapshot digest")

        import tempfile
        suffix = Path(storage_key).suffix or ".audio"
        with tempfile.NamedTemporaryFile(suffix=suffix) as temporary:
            temporary.write(data)
            temporary.flush()
            asr = await asyncio.to_thread(transcribe, Path(temporary.name))
        payload = align_narration(text=text, asr=asr, duration_ticks=duration_ticks)
        timing_digest, content_digest = _digests(row, payload)
        async with _session() as db:
            result = await db.execute(
                update(NarrationAlignment)
                .where(
                    NarrationAlignment.id == alignment_id,
                    NarrationAlignment.status == "PROCESSING",
                    NarrationAlignment.claim_token == claim_token,
                )
                .values(
                    payload=payload.model_dump(mode="json"),
                    timing_digest=timing_digest,
                    content_digest=content_digest,
                    status="READY" if all(s.status == "aligned" for s in payload.sentences) else "ALIGNED",
                    claim_token=None,
                    lease_expires_at=None,
                    error=None,
                )
            )
            await db.commit()
        if (result.rowcount or 0) != 1:
            raise AlignmentStoreError("narration alignment terminal write lost its claim")
    except Exception as exc:
        await _fail(alignment_id, claim_token, str(exc))
