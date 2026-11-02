"""CC0 sound-effect candidates and fixed user audio assets.

Search only creates message-borne candidates. A later turn resolves the
persisted candidate set/member, rechecks the provider, and freezes the MP3
through the existing audio snapshot seam.
"""
from __future__ import annotations

import hashlib
import io
import math
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import av
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.timing import SOURCE_TIMEBASE
from app.models.schemas import AssetStatus, AssetType, ImportSfxArgs
from app.models.tables import Asset, Conversation, Message, Project, SourceSnapshot
from app.providers import storage
from app.providers.freesound import (
    FreesoundSound,
    download_mp3_preview,
    get_cc0_mp3,
    search_cc0_mp3,
    validate_mp3_preview_url,
)


class SfxError(RuntimeError):
    """An SFX search/import cannot produce an honest persisted result."""


def _member_payload(sound: FreesoundSound, query: str) -> dict[str, Any]:
    return {
        "start": 0,
        "end": sound.duration_seconds,
        "excerpt": sound.title,
        "speaker": None,
        "provider": "freesound",
        "provider_id": sound.provider_id,
        "title": sound.title,
        "author": sound.author,
        "duration_seconds": sound.duration_seconds,
        "source_url": sound.source_url,
        "preview_url": sound.preview_url,
        "license": sound.license,
        "attribution": sound.attribution,
        "query": query,
    }


async def search_sfx_candidates(query: str) -> dict[str, Any]:
    """Return the existing top-level candidate envelope, with audio member facts."""
    query = query.strip()
    if not query:
        raise SfxError("an SFX search needs a non-empty query")
    sounds = await search_cc0_mp3(query, limit=3)
    if not sounds:
        raise SfxError(f"no verified CC0 MP3 candidates found for {query!r}")
    return {
        "kind": "set",
        "candidate_set_id": str(uuid4()),
        "topic": query,
        "asset_id": None,
        "members": [_member_payload(sound, query) for sound in sounds],
    }


def resolve_candidate_member(
    events: list[dict[str, Any]],
    *,
    candidate_set_id: UUID,
    member_index: int,
) -> dict[str, Any]:
    """Resolve only a persisted audio member; no caller-supplied media facts."""
    for event in events:
        if (
            event.get("kind") != "set"
            or event.get("candidate_set_id") != str(candidate_set_id)
        ):
            continue
        members = event.get("members")
        if not isinstance(members, list) or not 0 <= member_index < len(members):
            raise SfxError("the SFX candidate member does not exist")
        member = members[member_index]
        if not isinstance(member, dict):
            raise SfxError("the SFX candidate member is malformed")
        required_strings = (
            "provider",
            "provider_id",
            "title",
            "author",
            "source_url",
            "preview_url",
            "license",
            "attribution",
            "query",
        )
        if any(not isinstance(member.get(key), str) or not member[key] for key in required_strings):
            raise SfxError("the candidate is not a complete SFX member")
        duration = member.get("duration_seconds")
        if (
            not isinstance(duration, int | float)
            or not math.isfinite(float(duration))
            or duration <= 0
        ):
            raise SfxError("the SFX candidate has no real duration")
        if member["provider"] != "freesound" or member["license"] != "CC0":
            raise SfxError("the candidate is not a verified Freesound CC0 member")
        if not member["provider_id"].isdigit():
            raise SfxError("the SFX candidate has an invalid provider id")
        validate_mp3_preview_url(member["preview_url"])
        if member.get("start") != 0 or member.get("end") != duration:
            raise SfxError("the SFX candidate's display range does not match its duration")
        return dict(member)
    raise SfxError(
        "no persisted SFX candidate set matches this id; choose a shown candidate in a later message"
    )


def _validate_mp3_bytes(data: bytes) -> None:
    if not data:
        raise SfxError("the downloaded MP3 preview is empty")
    container = None
    try:
        container = av.open(io.BytesIO(data), mode="r")
        if not container.streams.audio:
            raise SfxError("the downloaded preview has no audio stream")
        stream = container.streams.audio[0]
        codec_name = stream.codec_context.name
        if codec_name not in {"mp3", "mp3float"}:
            raise SfxError(
                f"the downloaded preview has codec {codec_name!r}; expected an MP3 audio stream"
            )
        decoded = next(container.decode(stream), None)
        if not decoded:
            raise SfxError("the MP3 preview has no decodable audio frames")
    except SfxError:
        raise
    except (av.AVError, IndexError, StopIteration) as exc:
        raise SfxError("the downloaded MP3 preview cannot be decoded") from exc
    finally:
        if container is not None:
            container.close()


def _import_facts(asset: Asset, snapshot: SourceSnapshot) -> dict[str, Any]:
    return {
        "asset_id": str(asset.id),
        "snapshot_id": str(snapshot.id),
        "snapshot_digest": snapshot.digest,
        "duration_seconds": (snapshot.duration_ticks or 0) / SOURCE_TIMEBASE,
        "title": asset.title,
        "origin": (asset.meta or {}).get("origin"),
    }


async def _persisted_candidate_events(
    db: AsyncSession,
    *,
    project: Project,
    candidate_set_id: UUID,
) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(Message)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.project_id == project.id,
                    Conversation.user_id == project.user_id,
                    Message.intent["type"].astext == "candidates_log",
                    Message.intent["events"].astext.contains(str(candidate_set_id)),
                )
                .order_by(Message.seq.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        event
        for row in rows
        for event in ((row.intent or {}).get("events") or [])
        if isinstance(event, dict)
    ]


def _sfx_asset_id(project: Project, args: ImportSfxArgs) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"sfx:{project.user_id}:{project.id}:{args.candidate_set_id}:{args.member_index}",
    )


def _sfx_storage_key(project: Project, asset_id: UUID) -> str:
    return f"{project.user_id}/uploads/projects/{project.id}/sfx-{asset_id}.mp3"


def _origin_matches(
    origin: Any,
    *,
    args: ImportSfxArgs,
    member: dict[str, Any],
) -> bool:
    return isinstance(origin, dict) and all((
        origin.get("kind") == "sfx",
        origin.get("provider") == "freesound",
        origin.get("provider_id") == member["provider_id"],
        origin.get("candidate_set_id") == str(args.candidate_set_id),
        origin.get("member_index") == args.member_index,
        origin.get("query") == member["query"],
        origin.get("source_url") == member["source_url"],
        origin.get("license") == "CC0",
    ))


async def _verified_existing_import(
    db: AsyncSession,
    *,
    project: Project,
    args: ImportSfxArgs,
    member: dict[str, Any],
    expected_digest: str | None = None,
) -> dict[str, Any] | None:
    """Read an idempotent winner only after proving its complete identity."""
    asset_id = _sfx_asset_id(project, args)
    existing = await db.get(Asset, asset_id, populate_existing=True)
    if existing is None:
        return None
    meta = existing.meta if isinstance(existing.meta, dict) else {}
    origin = meta.get("origin")
    if (
        existing.user_id != project.user_id
        or existing.project_id != project.id
        or existing.type != AssetType.AUDIO
        or existing.processing_status != AssetStatus.COMPLETED
        or existing.file_url != _sfx_storage_key(project, asset_id)
        or not _origin_matches(origin, args=args, member=member)
    ):
        raise SfxError("the deterministic SFX asset identity is occupied by different facts")
    try:
        data = await storage.read(existing.file_url)
    except Exception as exc:
        raise SfxError("the existing SFX asset bytes cannot be verified") from exc
    actual_digest = hashlib.sha256(data).hexdigest()
    if (
        meta.get("content_sha256") != actual_digest
        or (expected_digest is not None and actual_digest != expected_digest)
    ):
        raise SfxError("the existing SFX asset does not match the expected content digest")
    snapshot = await db.scalar(
        select(SourceSnapshot)
        .where(
            SourceSnapshot.asset_id == existing.id,
            SourceSnapshot.owner_id == project.user_id,
            SourceSnapshot.kind == "audio",
            SourceSnapshot.digest == actual_digest,
        )
        .execution_options(populate_existing=True)
        .limit(1)
    )
    snapshot_meta = snapshot.meta if snapshot is not None and isinstance(snapshot.meta, dict) else {}
    if (
        snapshot is None
        or snapshot.storage_key != f"source-snapshots/{actual_digest}.mp3"
        or not snapshot.duration_ticks
        or not _origin_matches(
            snapshot_meta.get("origin"),
            args=args,
            member=member,
        )
    ):
        raise SfxError("the existing SFX asset has no matching frozen source snapshot")
    return _import_facts(existing, snapshot)


async def import_sfx_candidate(
    db: AsyncSession,
    *,
    project: Project,
    args: ImportSfxArgs,
) -> dict[str, Any]:
    """Recheck, download, store and snapshot one previously persisted candidate.

    Asset + snapshot share one SAVEPOINT. A concurrent deterministic winner
    rolls back only that unit, then is read back and fully verified; unrelated
    database failures are never retried or hidden by the idempotent path.
    """
    events = await _persisted_candidate_events(
        db,
        project=project,
        candidate_set_id=args.candidate_set_id,
    )
    member = resolve_candidate_member(
        events,
        candidate_set_id=args.candidate_set_id,
        member_index=args.member_index,
    )
    sound = await get_cc0_mp3(member["provider_id"])
    if sound.provider_id != member["provider_id"] or sound.source_url != member["source_url"]:
        raise SfxError("the provider's current source identity differs from the persisted candidate")
    asset_id = _sfx_asset_id(project, args)
    try:
        existing = await _verified_existing_import(
            db, project=project, args=args, member=member
        )
        if existing is not None:
            return existing

        data = await download_mp3_preview(sound)
        _validate_mp3_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        storage_key = _sfx_storage_key(project, asset_id)
        await storage.save(storage_key, data, content_type="audio/mpeg")
        retrieved_at = datetime.now(UTC)
        origin = {
            "kind": "sfx",
            "provider": "freesound",
            "provider_id": sound.provider_id,
            "candidate_set_id": str(args.candidate_set_id),
            "member_index": args.member_index,
            "query": member["query"],
            "title": sound.title,
            "author": sound.author,
            "source_url": sound.source_url,
            "preview_url": sound.preview_url,
            "license": sound.license,
            "attribution": sound.attribution,
            "retrieved_at": retrieved_at.isoformat(),
        }
        try:
            async with db.begin_nested():
                asset = Asset(
                    id=asset_id,
                    user_id=project.user_id,
                    project_id=project.id,
                    type=AssetType.AUDIO,
                    file_url=storage_key,
                    title=sound.title[:255],
                    processing_status=AssetStatus.COMPLETED,
                    processed_at=retrieved_at,
                    meta={
                        "content_sha256": digest,
                        "content_type": "audio/mpeg",
                        "size_bytes": len(data),
                        "origin": origin,
                    },
                )
                db.add(asset)
                await db.flush()
                from app.tools.video.preparation import snapshot_audio_asset

                snapshot = await snapshot_audio_asset(db, asset, owner_id=project.user_id)
                asset.duration_seconds = round(
                    (snapshot.duration_ticks or 0) / SOURCE_TIMEBASE
                )
                facts = _import_facts(asset, snapshot)
        except IntegrityError:
            # SAVEPOINT rollback has expired the local ORM objects. Use only
            # captured scalars, then prove the committed winner is our exact
            # deterministic Asset AND SourceSnapshot before treating it as replay.
            facts = await _verified_existing_import(
                db,
                project=project,
                args=args,
                member=member,
                expected_digest=digest,
            )
            if facts is None:
                raise
        await db.commit()
        return facts
    except Exception:
        await db.rollback()
        raise
