"""Programmatic music preparation on the existing Run machinery."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5


from app.editing.timing import (
    SOURCE_TIMEBASE,
    quantize_ticks,
)
from app.models.database import AsyncSessionLocal
from app.models.ids import source_snapshot_id
from app.models.tables import Music, SourceSnapshot
from app.providers import storage
from app.tools.music.score import (
    ScoreSpec,
    authored_beat_grid,
    synthesize_score,
)
from app.tools.video.preparation import store_source_bytes

_MUSIC_MANIFEST_PREFIX = "programmatic-music"


class MusicPreparationError(ValueError):
    pass


def _manifest_key(owner_id: UUID, project_id: UUID, score_digest: str) -> str:
    from app.tools.video.media_analysis import AUDIO_ANALYZER_SET_VERSION

    return (
        f"{_MUSIC_MANIFEST_PREFIX}/{owner_id}/{project_id}/{score_digest}/"
        f"{AUDIO_ANALYZER_SET_VERSION}.json"
    )


async def _write_manifest(key: str, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if await storage.exists(key):
        existing = await storage.read(key)
        if hashlib.sha256(existing).hexdigest() != hashlib.sha256(encoded).hexdigest():
            raise MusicPreparationError("a fixed music manifest cannot be overwritten")
    else:
        await storage.save(key, encoded, content_type="application/json")


async def cached_music_preparation(
    *, owner_id: UUID, project_id: UUID, score: ScoreSpec
) -> dict[str, Any] | None:
    key = _manifest_key(owner_id, project_id, score.score_digest)
    if not await storage.exists(key):
        return None
    try:
        manifest = json.loads(await storage.read(key))
    except (ValueError, json.JSONDecodeError) as exc:
        raise MusicPreparationError("the music preparation manifest is unreadable") from exc
    if (
        manifest.get("state") != "fixed"
        or manifest.get("score_digest") != score.score_digest
        or manifest.get("score_spec") != score.model_dump(mode="json")
    ):
        raise MusicPreparationError("music cache identity does not match its fixed ScoreSpec")
    score_ref = manifest.get("score_spec_ref") or {}
    stored_score = await storage.read(score_ref["storage_key"])
    if (
        hashlib.sha256(stored_score).hexdigest() != score_ref.get("digest")
        or json.loads(stored_score) != manifest["score_spec"]
    ):
        raise MusicPreparationError("stored ScoreSpec bytes differ from their fixed reference")
    async with AsyncSessionLocal() as db:
        music = await db.get(Music, UUID(str((manifest.get("music") or {}).get("music_id"))))
        snapshot = await db.get(SourceSnapshot, UUID(str((manifest.get("snapshot") or {}).get("snapshot_id"))))
    if (
        music is None or snapshot is None
        or music.generated_by_user_id != owner_id or music.is_public
        or snapshot.owner_id != owner_id or snapshot.origin_project_id != project_id
        or snapshot.kind != "audio" or snapshot.digest != (manifest.get("media") or {}).get("digest")
    ):
        raise MusicPreparationError("music cache rows failed owner or identity validation")
    data = await storage.read(snapshot.storage_key)
    if hashlib.sha256(data).hexdigest() != snapshot.digest:
        raise MusicPreparationError("fixed music bytes do not match their Snapshot digest")
    from app.tools.video.media_analysis import read_report

    analysis = await read_report(manifest["analysis_ref"])
    if (
        analysis.get("media_kind") != "audio"
        or analysis.get("analysis_scope") != "full"
        or (analysis.get("source_ref") or {}).get("digest") != snapshot.digest
        or not ((analysis.get("media_facts") or {}).get("decode") or {}).get("fully_decoded")
    ):
        raise MusicPreparationError("cached music analysis is not trustworthy")
    if manifest.get("beat_grid") != authored_beat_grid(score):
        raise MusicPreparationError("cached music BeatGrid differs from its ScoreSpec")
    return {**manifest, "analysis": analysis, "cache_hit": True}


async def prepare_programmatic_music(
    *,
    project,
    score: ScoreSpec,
    name: str,
    execution_id: str,
) -> dict[str, Any]:
    cached = await cached_music_preparation(
        owner_id=project.user_id, project_id=project.id, score=score
    )
    if cached is not None:
        return cached
    data = await asyncio.to_thread(synthesize_score, score)
    digest = hashlib.sha256(data).hexdigest()
    music_id = uuid5(
        NAMESPACE_URL, f"programmatic-music:{project.user_id}:{project.id}:{score.score_digest}"
    )
    from app.tools.video.media_analysis import (
        AUDIO_ANALYZER_SET_VERSION,
        analyze_audio_bytes,
        store_media_analysis,
    )

    identity = uuid5(
        music_id, f"programmatic-score-audio-v1:{digest}:{AUDIO_ANALYZER_SET_VERSION}"
    )
    snapshot_id = source_snapshot_id(project.user_id, identity, "audio", digest)

    report = await asyncio.to_thread(
        analyze_audio_bytes,
        data,
        snapshot_id=str(snapshot_id),
        source_digest=digest,
    )
    if not report.media_facts["decode"]["fully_decoded"]:
        raise MusicPreparationError("the synthesized score is not fully decodable")
    analysis_ref = await store_media_analysis(report)
    score_key, score_digest = await store_source_bytes(
        score.model_dump_json().encode("utf-8"), ".json", "application/json"
    )
    score_ref = {"storage_key": score_key, "digest": score_digest}
    music_key = f"music/{music_id}.wav"
    if await storage.exists(music_key):
        if hashlib.sha256(await storage.read(music_key)).hexdigest() != digest:
            raise MusicPreparationError("deterministic Music object identity collision")
    else:
        await storage.save(music_key, data, content_type="audio/wav")
    snapshot_key, snapshot_digest = await store_source_bytes(data, ".wav", "audio/wav")
    if snapshot_digest != digest:
        raise MusicPreparationError("music Snapshot digest differs from synthesized bytes")
    beat_grid = authored_beat_grid(score)
    duration_ticks = quantize_ticks(
        Fraction(
            report.media_facts["decode"]["sample_count"],
            report.media_facts["sample_rate"],
        ) * SOURCE_TIMEBASE
    )
    actual_seconds = report.media_facts["decode"]["duration_seconds"]
    async with AsyncSessionLocal() as db:
        music = await db.get(Music, music_id)
        if music is None:
            music = Music(
                id=music_id,
                mood=f"score-{music_id.hex[:24]}",
                title=name,
                ext="wav",
                file_path=music_key,
                size_bytes=len(data),
                duration_seconds=max(1, round(actual_seconds)),
                prompt=None,
                model=score.synth_version,
                generation_id=execution_id,
                is_public=False,
                generated_by_user_id=project.user_id,
                meta={
                    "content_sha256": digest,
                    "origin": "programmatic_score",
                    "score_digest": score.score_digest,
                    "score_spec_ref": score_ref,
                    "synth_version": score.synth_version,
                    "beat_grid": beat_grid,
                    "analysis_ref": analysis_ref,
                },
            )
            db.add(music)
        elif (
            music.generated_by_user_id != project.user_id
            or music.is_public
            or music.file_path != music_key
            or (music.meta or {}).get("content_sha256") != digest
            or (music.meta or {}).get("score_digest") != score.score_digest
        ):
            raise MusicPreparationError("an existing Music row has a conflicting score identity")
        from app.editing.sources import register_snapshot

        snapshot = await register_snapshot(
            db,
            owner_id=project.user_id,
            asset=None,
            identity=identity,
            origin_project_id=project.id,
            kind="audio",
            storage_key=snapshot_key,
            digest=snapshot_digest,
            duration_ticks=duration_ticks,
            captured_at=datetime.now(UTC),
            meta={
                "media": {
                    "sample_rate": report.media_facts["sample_rate"],
                    "channels": report.media_facts["channels"],
                },
                "origin": {
                    "kind": "programmatic_score",
                    "media_job_id": execution_id,
                    "synth_version": score.synth_version,
                },
                "music": {"music_id": str(music_id), "title": name},
                "score_digest": score.score_digest,
                "score_spec_ref": score_ref,
                "beat_grid": beat_grid,
                "analysis_ref": analysis_ref,
            },
        )
        await db.commit()
    manifest = {
        "schema_version": 1,
        "state": "fixed",
        "execution": {"media_job_id": execution_id, "provider": "local_numpy"},
        "score_digest": score.score_digest,
        "score_spec": score.model_dump(mode="json"),
        "score_spec_ref": score_ref,
        "music": {"music_id": str(music_id), "title": name, "is_public": False},
        "snapshot": {"snapshot_id": str(snapshot.id), "digest": snapshot.digest},
        "media": {
            "storage_key": snapshot_key,
            "digest": snapshot.digest,
            "mime_type": "audio/wav",
            "size_bytes": len(data),
        },
        "duration_ticks": duration_ticks,
        "duration_seconds": actual_seconds,
        "beat_grid": beat_grid,
        "analysis_ref": analysis_ref,
        "usage": {
            "provider": "local_numpy",
            "synth_samples": report.media_facts["decode"]["sample_count"],
            "music_pieces": 0,
        },
    }
    await _write_manifest(
        _manifest_key(project.user_id, project.id, score.score_digest), manifest
    )
    return {
        **manifest,
        "analysis": report.model_dump(mode="json"),
        "cache_hit": False,
    }


async def prepare_minimax_music(
    *,
    project,
    args,
    execution_id: str,
) -> dict[str, Any]:
    """Generate instrumental BGM via MiniMax ``/music_generation`` and save into the permanent library."""
    from app.pipeline.music import (
        USER_MODEL,
        create_music_from_generation,
        generate_music as generate_minimax_music,
    )
    from app.tools.video.media_analysis import analyze_audio_bytes, store_media_analysis
    from app.tools.video.preparation import snapshot_music_track

    prompt = (args.prompt or f"Instrumental {args.style.replace('_', ' ')} background music, {args.bpm} BPM, clean modern production, no vocals").strip()
    generated = await generate_minimax_music(
        prompt,
        model=USER_MODEL,
        is_instrumental=True,
    )
    async with AsyncSessionLocal() as db:
        music = await create_music_from_generation(
            db,
            prompt=prompt,
            generated=generated,
            mood=args.mood or args.style.replace("_", "-"),
            title=args.name,
            user_id=project.user_id,
            is_public=False,
            tags=list(args.tags or []) or [args.style.replace("_", "-")],
            compatible_styles=list(args.compatible_styles or []),
            scope="user",
            status="ready",
            instrumental=True,
        )
        snapshot = await snapshot_music_track(db, music, owner_id=project.user_id)
        if snapshot.origin_project_id is None:
            snapshot.origin_project_id = project.id
        report = await asyncio.to_thread(
            analyze_audio_bytes,
            generated.audio_bytes,
            snapshot_id=str(snapshot.id),
            source_digest=snapshot.digest,
        )
        analysis_ref = await store_media_analysis(report)
        snapshot.meta = {**(snapshot.meta or {}), "analysis_ref": analysis_ref}
        music.meta = {**(music.meta or {}), "analysis_ref": analysis_ref}
        await db.commit()
        await db.refresh(music)
        await db.refresh(snapshot)

    actual_seconds = report.media_facts["decode"]["duration_seconds"]
    beat_grid = (music.meta or {}).get("beat_grid") or (
        {"bpm": music.meta.get("bpm"), "beats": music.meta.get("beats"), "origin": "estimated"}
        if isinstance(music.meta, dict) and music.meta.get("bpm") is not None
        else None
    )
    return {
        "schema_version": 1,
        "state": "fixed",
        "execution": {"media_job_id": execution_id, "provider": "minimax"},
        "music": {
            "music_id": str(music.id),
            "title": music.title,
            "mood": music.mood,
            "tags": list(music.tags or []),
            "compatible_styles": list(music.compatible_styles or []),
            "lufs": music.lufs,
            "is_public": bool(music.is_public),
        },
        "snapshot": {"snapshot_id": str(snapshot.id), "digest": snapshot.digest},
        "media": {
            "storage_key": snapshot.storage_key,
            "digest": snapshot.digest,
            "mime_type": "audio/mpeg",
            "size_bytes": len(generated.audio_bytes),
        },
        "duration_ticks": snapshot.duration_ticks,
        "duration_seconds": actual_seconds,
        "beat_grid": beat_grid,
        "analysis_ref": analysis_ref,
        "analysis": report.model_dump(mode="json"),
        "cache_hit": False,
    }


__all__ = [
    "MusicPreparationError",
    "cached_music_preparation",
    "prepare_minimax_music",
    "prepare_programmatic_music",
]
