"""Occupancy and fixed-original storage for video narration.

One user/content row owns the speed-1.0 synthesis. A pre-submit row prevents
concurrent paid calls; a confirmed audio row can resume subtitle download
without another TTS request. All writes use independent short sessions so a
Run rollback cannot erase a confirmed provider result.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.editing.schemas import SpeechObject
from app.tools.video.narration import (
    NARRATION_ALIGNMENT,
    narration_alignment_digest,
    narration_content_hash,
    narration_synth_config,
)
from app.tools.video.preparation import store_source_bytes

_LEASE_S = 600.0
_WAIT_POLL_S = 2.0
_WAIT_BUDGET_S = _LEASE_S + 120.0


class NarrationStoreError(ValueError):
    pass


class NarrationOutcomeUnknown(NarrationStoreError):
    user_key = "provider_narration_outcome_unknown"


def _session():
    from app.models.database import AsyncSessionLocal

    return AsyncSessionLocal()


def _identity(user_id: UUID, speech: SpeechObject) -> tuple[str, str, str]:
    config = narration_synth_config()
    content_hash, config_hash = narration_content_hash(
        text=speech.text,
        voice_id=speech.voice_id,
        language=speech.language,
        config=config,
    )
    return content_hash, config_hash, " ".join(speech.text.split())


async def _row(user_id: UUID, content_hash: str):
    from app.models.tables import VideoNarration

    async with _session() as db:
        return await db.scalar(
            select(VideoNarration).where(
                VideoNarration.user_id == user_id,
                VideoNarration.content_hash == content_hash,
            )
        )


def _alignment_digest(text: str, cues: list[dict]) -> str:
    return narration_alignment_digest(text, cues)


async def _fixed_original(row) -> dict:
    from app.providers import storage

    if not row.storage_key or not row.audio_digest or not isinstance(row.subtitles, list):
        raise NarrationStoreError("fixed narration row lacks audio or alignment facts")
    data = await storage.read(row.storage_key)
    if hashlib.sha256(data).hexdigest() != row.audio_digest:
        raise NarrationStoreError("fixed narration bytes do not match their stored digest")
    if _alignment_digest(row.text, row.subtitles) != row.alignment_digest:
        raise NarrationStoreError("fixed narration alignment does not match its digest")
    return {
        "content_hash": row.content_hash,
        "normalized_text": row.text,
        "media": {
            "storage_key": row.storage_key,
            "digest": row.audio_digest,
            "mime_type": "audio/mpeg",
        },
        "duration_s": float(row.duration_s),
        "cues": row.subtitles,
        "alignment": NARRATION_ALIGNMENT,
        "alignment_digest": row.alignment_digest,
        "usage_characters": row.usage_characters,
        "trace_id": row.trace_id,
        "speed": 1.0,
        "cache_hit": True,
    }


async def peek_original(user_id: UUID, speech: SpeechObject) -> dict | None:
    """Read-only quote/cache probe; never claims or synthesizes."""
    content_hash, _, _ = _identity(user_id, speech)
    row = await _row(user_id, content_hash)
    if row is None or row.status != "done":
        return None
    return await _fixed_original(row)


async def resolve_original(
    user_id: UUID, speech: SpeechObject, *, execution_id: str
) -> dict:
    """Resolve a fixed original, a resumable alignment, or a new occupancy."""
    from app.models.tables import VideoNarration

    content_hash, config_hash, normalized = _identity(user_id, speech)
    owner_token = f"{execution_id}:original"
    deadline = time.monotonic() + _WAIT_BUDGET_S
    while True:
        row = await _row(user_id, content_hash)
        if row is None:
            async with _session() as db:
                inserted = (
                    await db.execute(
                        pg_insert(VideoNarration)
                        .values(
                            user_id=user_id,
                            content_hash=content_hash,
                            voice_id=speech.voice_id,
                            language=speech.language,
                            config_hash=config_hash,
                            text=normalized,
                            status="synthesizing",
                            owner_token=owner_token,
                            lease_expires_at=datetime.now(UTC) + timedelta(seconds=_LEASE_S),
                        )
                        .on_conflict_do_nothing(index_elements=["user_id", "content_hash"])
                        .returning(VideoNarration.id)
                    )
                ).first()
                await db.commit()
            if inserted is not None:
                return {
                    "state": "needs_audio",
                    "content_hash": content_hash,
                    "normalized_text": normalized,
                    "owner_token": owner_token,
                }
            continue
        if row.status == "done":
            return {"state": "done", "original": await _fixed_original(row)}
        if row.status == "unknown":
            raise NarrationOutcomeUnknown(
                "An earlier narration request may have executed, but no fixed audio is available; "
                "automatic recovery will not submit it again"
            )
        if row.owner_token == owner_token:
            if row.status == "aligning" and row.storage_key and row.audio_digest:
                return {
                    "state": "needs_alignment",
                    "content_hash": content_hash,
                    "normalized_text": normalized,
                    "owner_token": owner_token,
                    "audio": {
                        "media": {
                            "storage_key": row.storage_key,
                            "digest": row.audio_digest,
                            "mime_type": "audio/mpeg",
                        },
                        "duration_s": float(row.duration_s),
                        "subtitle_file": row.subtitle_file,
                        "usage_characters": row.usage_characters,
                        "trace_id": row.trace_id,
                    },
                }
            raise NarrationOutcomeUnknown(
                "This execution's narration request has no confirmed fixed audio; "
                "recovery will not submit it again"
            )
        if time.monotonic() > deadline:
            raise NarrationStoreError("narration occupancy wait budget exhausted")
        lease = row.lease_expires_at
        expired = not isinstance(lease, datetime) or lease <= datetime.now(UTC)
        if expired:
            if row.status == "aligning" and row.storage_key:
                # Only a fixed-audio alignment may be taken over without replaying TTS.
                async with _session() as db:
                    result = await db.execute(
                        update(VideoNarration)
                        .where(
                            VideoNarration.id == row.id,
                            VideoNarration.status == "aligning",
                            VideoNarration.lease_expires_at < datetime.now(UTC),
                        )
                        .values(
                            owner_token=owner_token,
                            lease_expires_at=datetime.now(UTC) + timedelta(seconds=_LEASE_S),
                        )
                    )
                    await db.commit()
                if (result.rowcount or 0) == 1:
                    continue
            raise NarrationOutcomeUnknown(
                "An expired narration occupancy has no recoverable fixed result; "
                "recovery will not replay its provider request"
            )
        await asyncio.sleep(_WAIT_POLL_S)


async def complete_audio(
    user_id: UUID,
    speech: SpeechObject,
    *,
    execution_id: str,
    audio: bytes,
    duration_s: float,
    subtitle_file: str | None,
    usage_characters: int,
    trace_id: str | None,
) -> dict:
    """Fix confirmed audio before subtitle retrieval; no second POST on resume."""
    from app.models.tables import VideoNarration

    content_hash, _, _ = _identity(user_id, speech)
    key, digest = await store_source_bytes(audio, ".mp3", "audio/mpeg")
    owner_token = f"{execution_id}:original"
    async with _session() as db:
        result = await db.execute(
            update(VideoNarration)
            .where(
                VideoNarration.user_id == user_id,
                VideoNarration.content_hash == content_hash,
                VideoNarration.owner_token == owner_token,
                VideoNarration.status == "synthesizing",
            )
            .values(
                status="aligning",
                storage_key=key,
                audio_digest=digest,
                duration_s=duration_s,
                subtitle_file=subtitle_file,
                usage_characters=usage_characters,
                trace_id=trace_id,
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=_LEASE_S),
                error=None,
            )
        )
        await db.commit()
    if (result.rowcount or 0) != 1:
        raise NarrationStoreError("narration audio finalize lost its occupancy")
    return {
        "media": {"storage_key": key, "digest": digest, "mime_type": "audio/mpeg"},
        "duration_s": duration_s,
        "subtitle_file": subtitle_file,
        "usage_characters": usage_characters,
        "trace_id": trace_id,
    }


async def complete_alignment(
    user_id: UUID,
    speech: SpeechObject,
    *,
    execution_id: str,
    cues: list[dict],
) -> dict:
    from app.models.tables import VideoNarration

    content_hash, _, normalized = _identity(user_id, speech)
    digest = _alignment_digest(normalized, cues)
    async with _session() as db:
        result = await db.execute(
            update(VideoNarration)
            .where(
                VideoNarration.user_id == user_id,
                VideoNarration.content_hash == content_hash,
                VideoNarration.owner_token == f"{execution_id}:original",
                VideoNarration.status == "aligning",
            )
            .values(
                status="done",
                subtitles=cues,
                alignment_digest=digest,
                owner_token=None,
                lease_expires_at=None,
                error=None,
            )
        )
        await db.commit()
    if (result.rowcount or 0) != 1:
        raise NarrationStoreError("narration alignment finalize lost its occupancy")
    row = await _row(user_id, content_hash)
    return await _fixed_original(row)


async def mark_outcome_unknown(
    user_id: UUID, speech: SpeechObject, *, execution_id: str, error: str
) -> None:
    """Record an uncertain POST outcome; recovery must fail closed."""
    from app.models.tables import VideoNarration

    content_hash, _, _ = _identity(user_id, speech)
    async with _session() as db:
        await db.execute(
            update(VideoNarration)
            .where(
                VideoNarration.user_id == user_id,
                VideoNarration.content_hash == content_hash,
                VideoNarration.owner_token == f"{execution_id}:original",
                VideoNarration.status == "synthesizing",
            )
            .values(status="unknown", error=error[:2000], lease_expires_at=None)
        )
        await db.commit()


async def cancel_unsubmitted(
    user_id: UUID, speech: SpeechObject, *, execution_id: str
) -> None:
    """Release a fresh occupancy when the pinned budget rejects before any POST."""
    from app.models.tables import VideoNarration

    content_hash, _, _ = _identity(user_id, speech)
    async with _session() as db:
        await db.execute(
            delete(VideoNarration).where(
                VideoNarration.user_id == user_id,
                VideoNarration.content_hash == content_hash,
                VideoNarration.owner_token == f"{execution_id}:original",
                VideoNarration.status == "synthesizing",
            )
        )
        await db.commit()
