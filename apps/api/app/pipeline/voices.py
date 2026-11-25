"""Permanent compounding voiceprint library service.

Manages platform curated voices and owner-scoped designed/cloned voices in the
``voices`` table, backed by immutable reference audio in object storage so
designed/cloned MiniMax voice IDs can auto-reclone seamlessly if expired.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Voice
from app.providers import storage
from app.providers import voice as voice_provider

logger = structlog.get_logger()

VOICE_SCOPES = ("platform", "user")
VOICE_STATUSES = ("ready", "curated", "archived")
VOICE_SOURCE_KINDS = ("minimax_stock", "minimax_design", "minimax_clone")


def voice_reference_key(voice_id: UUID) -> str:
    """Object storage key for a voiceprint's permanent reference/preview audio."""
    return f"voices/{voice_id}/reference.mp3"


def _visibility_clause(owner_id: UUID | None):
    platform_curated = and_(Voice.scope == "platform", Voice.status == "curated")
    if owner_id is None:
        return platform_curated
    owner_private = and_(
        Voice.owner_id == owner_id,
        Voice.status.in_(("ready", "curated")),
    )
    return or_(platform_curated, owner_private)


def _is_voice_visible(voice: Voice, owner_id: UUID | None) -> bool:
    if voice.status == "archived":
        return False
    if voice.scope == "platform" and voice.status == "curated":
        return True
    return owner_id is not None and voice.owner_id == owner_id


def _enforce_voice_privacy(*, source_kind: str, scope: str, owner_id: UUID | None) -> None:
    if source_kind not in VOICE_SOURCE_KINDS:
        raise ValueError(f"Unsupported voice source_kind: {source_kind!r}")
    if scope not in VOICE_SCOPES:
        raise ValueError(f"Unsupported voice scope: {scope!r}")
    if source_kind == "minimax_clone" and scope != "user":
        raise ValueError("Cloned voices (minimax_clone) must always remain scope='user'.")
    if scope == "user" and owner_id is None:
        raise ValueError("User-scoped voices require an owner_id.")


async def get_visible_voice(
    db: AsyncSession,
    *,
    voice_id: UUID,
    owner_id: UUID | None,
) -> Voice | None:
    """Return a Voice row iff it is visible to ``owner_id``."""
    row = await db.get(Voice, voice_id)
    if row is None or not _is_voice_visible(row, owner_id):
        return None
    return row


async def search_voices(
    db: AsyncSession,
    *,
    owner_id: UUID | None,
    pacing: str | None = None,
    language: str | None = None,
    style_preset: str | None = None,
    tone: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> list[Voice]:
    """Search permanent voices visible to ``owner_id``, ranked reuse-first."""
    from app.catalog.audio_search import search_audio
    return await search_audio(db,Voice,owner_id,query=query,style=style_preset,limit=limit,
                              language=language,tone=tone,pacing=pacing)


def _select_curated_stock_voice(
    *,
    languages: list[str],
    gender: str | None,
    prompt: str,
    tone_tags: list[str] | None,
    compatible_styles: list[str] | None,
) -> str:
    """Choose the best live MiniMax ``speech-2.6-hd`` system voice when ``/voice_design`` is gated."""
    langs = [str(item).strip().lower() for item in (languages or []) if str(item).strip()]
    primary_lang = langs[0] if langs else "en"
    text = " ".join(
        [
            prompt or "",
            gender or "",
            " ".join(tone_tags or []),
            " ".join(compatible_styles or []),
        ]
    ).lower()
    is_female = (gender or "").strip().lower() == "female" or any(
        tok in text for tok in ("female", "woman", "lady", "女声", "女性")
    )
    if primary_lang.startswith("zh"):
        if is_female:
            return "Chinese (Mandarin)_News_Anchor"
        if any(tok in text for tok in ("energetic", "vox_editorial", "tech", "launch", "现代", "青年", "发布", "活力")):
            return "male-qn-jingying-jingpin"
        return "Chinese (Mandarin)_Male_Announcer"
    if is_female:
        if any(tok in text for tok in ("british", "bbc", "documentary", "science", "swiss_paper", "editorial", "nature")):
            return "English_Graceful_Lady"
        return "English_CalmWoman"
    if any(tok in text for tok in ("british", "baritone", "institutional", "institutional_dark", "boardroom", "deep", "authoritative")):
        return "English_Deep-VoicedGentleman"
    return "English_Trustworthy_Man"


async def design_and_save_voice(
    db: AsyncSession,
    *,
    owner_id: UUID | None,
    name: str,
    prompt: str,
    preview_text: str,
    languages: list[str],
    tone_tags: list[str] | None = None,
    compatible_styles: list[str] | None = None,
    gender: str | None = None,
    age_band: str | None = None,
    scope: str = "user",
    status: str = "ready",
    description: str | None = None,
    voice_id: str | None = None,
) -> Voice:
    """Design a new MiniMax voiceprint, persist reference audio to storage, and save a Voice row.

    Calls MiniMax ``/voice_design`` first; if the configured API plan does not
    entitle ``/voice_design`` (e.g. code 2061), cleanly matches a live MiniMax
    ``speech-2.6-hd`` stock voice, synthesizes the real preview MP3 via
    ``/t2a_v2``, and persists it honestly as ``source_kind='minimax_stock'``.
    """
    _enforce_voice_privacy(source_kind="minimax_design", scope=scope, owner_id=owner_id)
    if status not in VOICE_STATUSES:
        raise ValueError(f"Unsupported voice status: {status!r}")
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Voice name must not be empty.")
    clean_langs = [str(lang).strip().lower() for lang in (languages or []) if str(lang).strip()] or ["en"]

    source_kind = "minimax_design"
    extra_meta: dict[str, Any] = {}
    try:
        result = await asyncio.to_thread(
            voice_provider.design_voice,
            prompt,
            preview_text,
            voice_id=voice_id,
        )
        provider_vid = result.voice_id
        preview_bytes = result.trial_audio
        trace_id = result.trace_id
    except voice_provider.VoiceError as exc:
        if not voice_provider.is_voice_design_unsupported_error(exc):
            raise
        matched_vid = _select_curated_stock_voice(
            languages=clean_langs,
            gender=gender,
            prompt=prompt,
            tone_tags=tone_tags,
            compatible_styles=compatible_styles,
        )
        logger.warning(
            "voice_design_plan_unsupported_falling_back_to_stock",
            reason=str(exc),
            matched_voice_id=matched_vid,
        )
        t2a = await asyncio.to_thread(
            voice_provider.synthesize_preview_mp3,
            preview_text.strip(),
            matched_vid,
            clean_langs[0],
        )
        source_kind = "minimax_stock"
        provider_vid = matched_vid
        preview_bytes = t2a.audio
        trace_id = t2a.trace_id
        extra_meta = {
            "fallback_from": "minimax_design",
            "fallback_reason": str(exc),
            "tts_model": voice_provider.tts_model(),
        }

    row_id = uuid4()
    ref_key = voice_reference_key(row_id)
    await storage.save(ref_key, preview_bytes, content_type="audio/mpeg")

    row = Voice(
        id=row_id,
        owner_id=owner_id if scope == "user" else None,
        scope=scope,
        status=status,
        source_kind=source_kind,
        name=clean_name[:160],
        description=(description.strip() if description else None),
        design_prompt=prompt.strip(),
        languages=clean_langs,
        gender=(gender.strip().lower() if gender else None),
        age_band=(age_band.strip().lower() if age_band else None),
        tone_tags=[str(t).strip().lower() for t in (tone_tags or []) if str(t).strip()],
        compatible_styles=[str(s).strip() for s in (compatible_styles or []) if str(s).strip()],
        provider="minimax",
        provider_voice_id=provider_vid,
        reference_audio_key=ref_key,
        preview_audio_key=ref_key,
        use_count=0,
        is_favorite=False,
        meta={
            "trace_id": trace_id,
            "preview_text": preview_text.strip(),
            "audio_bytes": len(preview_bytes),
            **extra_meta,
        },
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info(
        "voice_designed_and_saved",
        voice_id=str(row.id),
        provider_voice_id=row.provider_voice_id,
        owner_id=str(owner_id) if owner_id else None,
        scope=scope,
    )
    return row


async def create_cloned_voice(
    db: AsyncSession,
    *,
    owner_id: UUID,
    name: str,
    provider_voice_id: str,
    reference_audio_key: str,
    languages: list[str],
    scope: str = "user",
    description: str | None = None,
    tone_tags: list[str] | None = None,
    compatible_styles: list[str] | None = None,
    gender: str | None = None,
    age_band: str | None = None,
    preview_audio_key: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Voice:
    """Persist a cloned voice row while enforcing the privacy invariant (scope='user' only)."""
    _enforce_voice_privacy(source_kind="minimax_clone", scope=scope, owner_id=owner_id)
    row = Voice(
        id=uuid4(),
        owner_id=owner_id,
        scope="user",
        status="ready",
        source_kind="minimax_clone",
        name=name.strip()[:160],
        description=(description.strip() if description else None),
        design_prompt=None,
        languages=[str(l).strip().lower() for l in (languages or []) if str(l).strip()] or ["en"],
        gender=(gender.strip().lower() if gender else None),
        age_band=(age_band.strip().lower() if age_band else None),
        tone_tags=[str(t).strip().lower() for t in (tone_tags or []) if str(t).strip()],
        compatible_styles=[str(s).strip() for s in (compatible_styles or []) if str(s).strip()],
        provider="minimax",
        provider_voice_id=provider_voice_id,
        reference_audio_key=reference_audio_key,
        preview_audio_key=preview_audio_key or reference_audio_key,
        use_count=0,
        is_favorite=False,
        meta=dict(meta or {}),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def resolve_voice_id(
    db: AsyncSession,
    *,
    voice_ref: str,
    owner_id: UUID | None,
    increment_use: bool = True,
) -> tuple[str, Voice | None]:
    """Resolve a ``Voice.id`` UUID, ``provider_voice_id``, or stock voice ID.

    Enforces owner/scope visibility on library rows and optionally increments
    ``use_count`` when a library voice is matched.
    """
    ref = (voice_ref or "").strip()
    if not ref:
        raise ValueError("voice_ref must not be empty.")

    parsed_uuid: UUID | None = None
    try:
        parsed_uuid = UUID(ref)
    except ValueError:
        parsed_uuid = None

    matched: Voice | None = None
    if parsed_uuid is not None:
        row = await db.get(Voice, parsed_uuid)
        if row is None or not _is_voice_visible(row, owner_id):
            raise ValueError(f"Voice {ref} is not available to this user.")
        matched = row
    else:
        matched = await db.scalar(
            select(Voice)
            .where(Voice.provider_voice_id == ref, _visibility_clause(owner_id))
            .order_by(Voice.is_favorite.desc(), Voice.use_count.desc())
            .limit(1)
        )

    if matched is not None:
        if increment_use:
            matched.use_count = int(matched.use_count or 0) + 1
            await db.flush()
        return matched.provider_voice_id, matched

    return ref, None


async def synthesize_with_voice_resilience(
    db: AsyncSession | None,
    *,
    text: str,
    voice_ref: str,
    language: str = "en",
    speed: float = 1.0,
    owner_id: UUID | None = None,
    voice_row: Voice | None = None,
) -> tuple[voice_provider.T2AResult, str]:
    """Run MiniMax T2A synthesis with transparent auto-reclone fallback if a voice expired.

    If MiniMax reports that a designed/cloned ``provider_voice_id`` expired or is missing
    AND the matching ``Voice`` row has ``reference_audio_key`` backed up in object storage,
    automatically downloads the reference audio, calls ``clone_voice()``, persists the fresh
    ``provider_voice_id`` onto the ``Voice`` row, and retries synthesis once.
    """
    provider_voice_id = voice_ref
    resolved_row = voice_row
    if resolved_row is None and db is not None:
        provider_voice_id, resolved_row = await resolve_voice_id(
            db, voice_ref=voice_ref, owner_id=owner_id, increment_use=False
        )
    elif resolved_row is not None:
        provider_voice_id = resolved_row.provider_voice_id

    try:
        result = await asyncio.to_thread(
            voice_provider.synthesize_detailed,
            text,
            provider_voice_id,
            language,
            speed,
        )
        return result, provider_voice_id
    except voice_provider.VoiceError as exc:
        if (
            not voice_provider.is_voice_expired_error(exc)
            or resolved_row is None
            or not resolved_row.reference_audio_key
        ):
            raise
        logger.warning(
            "voice_expired_auto_reclone_start",
            voice_id=str(resolved_row.id),
            expired_provider_voice_id=provider_voice_id,
            reference_audio_key=resolved_row.reference_audio_key,
        )
        ref_bytes = await storage.read(resolved_row.reference_audio_key)
        suffix = Path(resolved_row.reference_audio_key).suffix or ".mp3"
        fd, tmp_name = tempfile.mkstemp(suffix=suffix)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(ref_bytes)
            new_voice_id = await asyncio.to_thread(voice_provider.clone_voice, tmp_path)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        if not new_voice_id:
            raise voice_provider.VoiceError(
                "Auto-reclone failed to obtain a replacement provider voice_id"
            ) from exc

        old_voice_id = resolved_row.provider_voice_id
        resolved_row.provider_voice_id = new_voice_id
        resolved_row.meta = {
            **(resolved_row.meta or {}),
            "recloned_from": old_voice_id,
        }
        if db is not None:
            await db.commit()
            await db.refresh(resolved_row)
        logger.info(
            "voice_expired_auto_reclone_succeeded",
            voice_id=str(resolved_row.id),
            old_provider_voice_id=old_voice_id,
            new_provider_voice_id=new_voice_id,
        )
        retried = await asyncio.to_thread(
            voice_provider.synthesize_detailed,
            text,
            new_voice_id,
            language,
            speed,
        )
        return retried, new_voice_id


__all__ = [
    "VOICE_SCOPES",
    "VOICE_SOURCE_KINDS",
    "VOICE_STATUSES",
    "create_cloned_voice",
    "design_and_save_voice",
    "get_visible_voice",
    "resolve_voice_id",
    "search_voices",
    "synthesize_with_voice_resilience",
    "voice_reference_key",
]
