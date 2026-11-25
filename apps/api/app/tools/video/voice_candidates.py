"""Permanent Voice-library candidates and ordinal selection.

Search emits message-borne ``voice_set`` candidates only so the user can audition
voices directly in Chat. A later turn resolves the persisted member, re-verifies
owner/scope visibility, and returns the authoritative ``voice_id`` for ``create_video``.
"""

from __future__ import annotations

import io
import math
from fractions import Fraction
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Project, Voice
from app.providers import storage


class VoiceCandidateError(RuntimeError):
    """A permanent Voice library candidate/selection cannot produce an honest result."""


def _probe_audio_duration_seconds(data: bytes) -> int:
    """Best-effort PyAV duration probe in whole seconds, falling back to 10."""
    try:
        import av

        with av.open(io.BytesIO(data), mode="r") as container:
            if not container.streams.audio:
                return 10
            stream = container.streams.audio[0]
            if stream.duration is not None and stream.time_base is not None:
                duration = float(Fraction(stream.duration) * Fraction(stream.time_base))
            elif container.duration is not None:
                duration = float(Fraction(container.duration, av.time_base))
            else:
                return 10
            if math.isfinite(duration) and duration >= 0.5:
                return max(1, int(round(duration)))
    except Exception:  # noqa: BLE001
        pass
    return 10


def _member_payload(voice: Voice, *, duration_s: int) -> dict[str, Any]:
    return {
        "start": 0,
        "end": duration_s,
        "excerpt": voice.name,
        "speaker": voice.name,
        "provider": "voice_library",
        "provider_id": str(voice.id),
        "voice_id": str(voice.id),
        "provider_voice_id": voice.provider_voice_id,
        "title": voice.name,
        "description": voice.description or "",
        "source_kind": voice.source_kind,
        "scope": voice.scope,
        "languages": list(voice.languages or []),
        "gender": voice.gender,
        "age_band": voice.age_band,
        "tone_tags": list(voice.tone_tags or []),
        "compatible_styles": list(voice.compatible_styles or []),
        "use_count": int(voice.use_count or 0),
        "duration_seconds": duration_s,
        "preview_url": f"/api/v1/voices/{voice.id}/audio",
    }


def _topic_label(
    *,
    language: str | None,
    style_preset: str | None,
    tone: str | None,
    query: str | None,
) -> str:
    parts = [
        part.strip()
        for part in (query, style_preset, tone, language)
        if isinstance(part, str) and part.strip()
    ]
    return " · ".join(parts) if parts else "Voice library"


async def show_voice_candidate_set(
    db: AsyncSession,
    *,
    owner_id: UUID,
    language: str | None = None,
    style_preset: str | None = None,
    tone: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Return up to five playable permanent voices visible to ``owner_id``."""
    from app.pipeline.voices import search_voices

    matches = await search_voices(
        db,
        owner_id=owner_id,
        language=language,
        style_preset=style_preset,
        tone=tone,
        query=query,
        limit=20,
    )
    playable: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []

    for voice in matches:
        audio_key = voice.preview_audio_key or voice.reference_audio_key
        meta = voice.meta if isinstance(voice.meta, dict) else {}
        meta_dur = meta.get("duration_seconds")
        duration_s = (
            max(1, int(round(float(meta_dur))))
            if isinstance(meta_dur, (int, float))
            and not isinstance(meta_dur, bool)
            and math.isfinite(float(meta_dur))
            and float(meta_dur) >= 0.5
            else None
        )
        has_stored_audio = False
        if audio_key:
            try:
                has_stored_audio = await storage.exists(audio_key)
            except Exception:  # noqa: BLE001
                has_stored_audio = False

        if has_stored_audio and audio_key:
            if duration_s is None:
                try:
                    raw_bytes = await storage.read(audio_key)
                    duration_s = _probe_audio_duration_seconds(raw_bytes)
                except Exception:  # noqa: BLE001
                    duration_s = 10
            playable.append(_member_payload(voice, duration_s=duration_s))
            if len(playable) == 5:
                break
        elif len(fallback) < 5:
            fallback.append(_member_payload(voice, duration_s=duration_s or 10))

    members = playable if playable else fallback[:5]
    topic = _topic_label(
        language=language, style_preset=style_preset, tone=tone, query=query
    )
    if not members:
        if any(v and str(v).strip() for v in (language, style_preset, tone, query)):
            raise VoiceCandidateError(
                f"no playable Voice library voices match {topic!r}"
            )
        raise VoiceCandidateError("the Voice library has no playable voices yet")

    return {
        "kind": "voice_set",
        "candidate_set_id": str(uuid4()),
        "topic": topic,
        "asset_id": None,
        "members": members,
    }


def resolve_voice_candidate_member(
    events: list[dict[str, Any]],
    *,
    candidate_set_id: UUID,
    member_index: int,
) -> dict[str, Any]:
    """Resolve only a persisted permanent Voice library member from ``candidates_log``."""
    for event in events:
        if (
            event.get("kind") != "voice_set"
            or event.get("candidate_set_id") != str(candidate_set_id)
        ):
            continue
        members = event.get("members")
        if not isinstance(members, list) or not 0 <= member_index < len(members):
            raise VoiceCandidateError("the Voice candidate member does not exist")
        member = members[member_index]
        if not isinstance(member, dict):
            raise VoiceCandidateError("the Voice candidate member is malformed")
        required_strings = (
            "provider",
            "provider_id",
            "voice_id",
            "provider_voice_id",
            "title",
            "preview_url",
        )
        if any(not isinstance(member.get(key), str) or not member.get(key) for key in required_strings):
            raise VoiceCandidateError("the candidate is not a complete Voice member")
        if member["provider"] != "voice_library" or member["provider_id"] != member["voice_id"]:
            raise VoiceCandidateError("the candidate is not a permanent Voice library member")
        try:
            UUID(member["voice_id"])
        except (ValueError, AttributeError) as exc:
            raise VoiceCandidateError("the Voice candidate has an invalid library id") from exc
        return dict(member)
    raise VoiceCandidateError(
        "no persisted Voice candidate set matches this id; choose a shown candidate in a later message"
    )


async def select_voice_candidate(
    db: AsyncSession,
    *,
    owner_id: UUID,
    events: list[dict[str, Any]] | None = None,
    project: Project | None = None,
    candidate_set_id: UUID,
    member_index: int,
) -> dict[str, Any]:
    """Resolve a persisted ``voice_set`` ordinal choice and verify visibility via ``get_visible_voice``."""
    from app.pipeline.voices import get_visible_voice

    resolved_events = events
    if resolved_events is None:
        if project is None:
            raise VoiceCandidateError("cannot resolve Voice candidate without events or project")
        from app.tools.video.sfx import persisted_candidate_events

        resolved_events = await persisted_candidate_events(
            db,
            project=project,
            candidate_set_id=candidate_set_id,
        )

    member = resolve_voice_candidate_member(
        resolved_events,
        candidate_set_id=candidate_set_id,
        member_index=member_index,
    )
    voice_uuid = UUID(member["voice_id"])
    voice = await get_visible_voice(db, voice_id=voice_uuid, owner_id=owner_id)
    if voice is None:
        raise VoiceCandidateError("the selected Voice library entry is no longer accessible")

    duration_s = member.get("duration_seconds") or member.get("end") or 10
    return {
        "voice_id": str(voice.id),
        "provider_voice_id": voice.provider_voice_id,
        "name": voice.name,
        "title": voice.name,
        "description": voice.description or "",
        "source_kind": voice.source_kind,
        "scope": voice.scope,
        "languages": list(voice.languages or []),
        "gender": voice.gender,
        "age_band": voice.age_band,
        "tone_tags": list(voice.tone_tags or []),
        "compatible_styles": list(voice.compatible_styles or []),
        "use_count": int(voice.use_count or 0),
        "duration_seconds": duration_s,
        "preview_url": f"/api/v1/voices/{voice.id}/audio",
    }


__all__ = [
    "VoiceCandidateError",
    "resolve_voice_candidate_member",
    "select_voice_candidate",
    "show_voice_candidate_set",
]
