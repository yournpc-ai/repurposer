"""Local Music-library candidates and ordinal selection.

Search emits message-borne candidates only. A later turn resolves the persisted
member and returns its Music identity; prepare_video_materials freezes the selected source.
"""
from __future__ import annotations

import math
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Music, Project
from app.providers import storage


class MusicCandidateError(RuntimeError):
    """A local Music candidate/selection cannot produce an honest result."""


def _member_payload(track: Music, query: str) -> dict[str, Any] | None:
    duration = track.duration_seconds
    if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
        return None
    preview_url = storage.public_url(track.file_path)
    if not preview_url:
        return None
    meta = track.meta if isinstance(track.meta, dict) else {}
    author = meta.get("author")
    if not isinstance(author, str):
        author = track.attribution or ""
    member = {
        "start": 0,
        "end": duration,
        "excerpt": track.title,
        "speaker": None,
        "provider": "music_library",
        "provider_id": str(track.id),
        "music_id": str(track.id),
        "title": track.title,
        "author": author,
        "duration_seconds": duration,
        "source_url": track.source_url,
        "preview_url": preview_url,
        "license": track.license or "",
        "attribution": track.attribution or "",
        "query": query,
        "mood": track.mood,
        "scope": track.scope,
        "status": track.status,
        "tags": list(track.tags or []),
        "compatible_styles": list(track.compatible_styles or []),
        "instrumental": bool(track.instrumental),
        "bpm": meta.get("bpm"),
        "lufs": track.lufs,
        "use_count": int(track.use_count or 0),
    }
    digest = meta.get("content_sha256")
    if isinstance(digest, str) and len(digest) == 64:
        member["content_sha256"] = digest
    return member


async def show_music_candidate_set(
    db: AsyncSession,
    *,
    owner_id: UUID,
    query: str | None = None,
    style_preset: str | None = None,
    mood: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Return up to five playable library tracks; never create an Asset/version."""
    from app.pipeline.music import search_music_library  # deferred: pipeline weight

    normalized = (query or "").strip().lower()
    matches = await search_music_library(
        db,
        owner_id=owner_id,
        style_preset=style_preset,
        mood=mood,
        tags=tags,
        query=query,
        instrumental_only=False,
        limit=25,
    )
    members: list[dict[str, Any]] = []
    for track in matches:
        member = _member_payload(track, normalized)
        if member is None:
            continue
        try:
            object_exists = await storage.exists(track.file_path)
        except Exception as exc:
            raise MusicCandidateError("the Music library object store is unavailable") from exc
        if object_exists:
            members.append(member)
        if len(members) == 5:
            break
    topic_parts = [
        part.strip()
        for part in (query, style_preset, mood, *(tags or []))
        if isinstance(part, str) and part.strip()
    ]
    topic_label = " · ".join(topic_parts) if topic_parts else "Music library"
    if not members:
        if topic_parts:
            raise MusicCandidateError(
                f"no playable Music library tracks match {topic_label!r}"
            )
        raise MusicCandidateError("the Music library has no playable tracks with real durations")
    return {
        "kind": "music_set",
        "candidate_set_id": str(uuid4()),
        "topic": topic_label,
        "asset_id": None,
        "members": members,
    }


def resolve_music_candidate_member(
    events: list[dict[str, Any]],
    *,
    candidate_set_id: UUID,
    member_index: int,
) -> dict[str, Any]:
    """Resolve only a persisted local-library member, never caller media facts."""
    for event in events:
        if (
            event.get("kind") != "music_set"
            or event.get("candidate_set_id") != str(candidate_set_id)
        ):
            continue
        members = event.get("members")
        if not isinstance(members, list) or not 0 <= member_index < len(members):
            raise MusicCandidateError("the Music candidate member does not exist")
        member = members[member_index]
        if not isinstance(member, dict):
            raise MusicCandidateError("the Music candidate member is malformed")
        required_strings = (
            "provider",
            "provider_id",
            "music_id",
            "title",
            "author",
            "preview_url",
            "license",
            "attribution",
            "query",
        )
        if any(not isinstance(member.get(key), str) for key in required_strings):
            raise MusicCandidateError("the candidate is not a complete Music member")
        if not all(member.get(key) for key in ("provider_id", "music_id", "title", "preview_url")):
            raise MusicCandidateError("the Music candidate lacks a playable identity")
        if member["provider"] != "music_library" or member["provider_id"] != member["music_id"]:
            raise MusicCandidateError("the candidate is not a local Music library member")
        try:
            UUID(member["music_id"])
        except (ValueError, AttributeError) as exc:
            raise MusicCandidateError("the Music candidate has an invalid library id") from exc
        duration = member.get("duration_seconds")
        if (
            not isinstance(duration, int | float)
            or isinstance(duration, bool)
            or not math.isfinite(float(duration))
            or duration <= 0
        ):
            raise MusicCandidateError("the Music candidate has no real duration")
        if member.get("start") != 0 or member.get("end") != duration:
            raise MusicCandidateError("the Music candidate's display range differs from its duration")
        if member.get("source_url") is not None and not isinstance(member.get("source_url"), str):
            raise MusicCandidateError("the Music candidate has an invalid source URL")
        return dict(member)
    raise MusicCandidateError(
        "no persisted Music candidate set matches this id; choose a shown candidate in a later message"
    )


async def select_music_candidate(
    db: AsyncSession,
    *,
    project: Project,
    candidate_set_id: UUID,
    member_index: int,
) -> dict[str, Any]:
    """Resolve a previous turn's ordinal choice against the current accessible row."""
    from app.tools.video.sfx import persisted_candidate_events

    events = await persisted_candidate_events(
        db,
        project=project,
        candidate_set_id=candidate_set_id,
    )
    member = resolve_music_candidate_member(
        events,
        candidate_set_id=candidate_set_id,
        member_index=member_index,
    )
    music_id = UUID(member["music_id"])
    track = await db.get(Music, music_id)
    if track is None or track.status == "archived" or not (
        track.is_public or track.scope == "platform" or track.generated_by_user_id == project.user_id
    ):
        raise MusicCandidateError("the selected Music library piece is no longer accessible")
    if track.title != member["title"] or track.duration_seconds != member["duration_seconds"]:
        raise MusicCandidateError(
            "the selected Music library metadata changed; show fresh candidates before choosing"
        )
    current_meta = track.meta if isinstance(track.meta, dict) else {}
    current_digest = current_meta.get("content_sha256")
    if member.get("content_sha256") != current_digest:
        raise MusicCandidateError(
            "the selected Music library content identity changed; show fresh candidates before choosing"
        )
    return {
        "music_id": str(track.id),
        "title": track.title,
        "duration_seconds": track.duration_seconds,
        "content_sha256": current_digest,
    }
