"""Draft-bound programmatic Music preparation on the existing Run machinery."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from app.editing.timing import (
    SOURCE_TIMEBASE,
    quantize_ticks,
)
from app.models.database import AsyncSessionLocal
from app.models.ids import source_snapshot_id
from app.models.schemas import VideoDraftRef
from app.models.tables import Music, SourceSnapshot
from app.providers import storage
from app.tools.music.score import (
    ScoreSpec,
    ScoreSpecDraft,
    authored_beat_grid,
    build_score_spec,
    synthesize_score,
)
from app.tools.video.narration_draft import assert_narration_ready_for_score
from app.tools.video.preparation import store_source_bytes

_MUSIC_MANIFEST_PREFIX = "programmatic-music"


class MusicPreparationError(ValueError):
    pass


class PrepareMusicArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_ref: VideoDraftRef
    name: str = Field(min_length=1, max_length=255)
    score: ScoreSpecDraft
    pending_disposition: Literal["answer", "skip", "none"] = "none"
    _working_draft: dict[str, Any] | None = PrivateAttr(default=None)

    def bind_working_draft(self, value: dict[str, Any]) -> None:
        from copy import deepcopy

        self._working_draft = deepcopy(value)


def score_for_current_draft(draft: dict[str, Any], creative: ScoreSpecDraft) -> ScoreSpec:
    assert_narration_ready_for_score(draft)
    return build_score_spec(creative, draft)


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
                    "run_id": execution_id,
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
        "execution": {"run_id": execution_id, "provider": "local_numpy"},
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


def has_music_preparation_scope(run) -> bool:
    return isinstance((run.context or {}).get("music_preparation"), dict)


async def music_preparation_fact(db, run, steps) -> dict[str, Any]:
    preparation = (run.context or {}).get("music_preparation") or {}
    result = preparation.get("result") or {}
    if not preparation.get("score_spec") or not result:
        raise ValueError("music preparation has no fixed result")
    step = next((item for item in steps if item.kind == "prepare_music"), None)
    if step is None or step.status != "done" or step.output_refs:
        raise ValueError("music preparation did not settle as an Output-free step")
    score = ScoreSpec.model_validate(preparation["score_spec"])
    result_score = ScoreSpec.model_validate(result.get("score_spec") or {})
    if result_score != score or result.get("score_digest") != score.score_digest:
        raise ValueError("music result differs from its authorized ScoreSpec")
    snapshot = await db.get(SourceSnapshot, UUID(str(result["snapshot"]["snapshot_id"])))
    music = await db.get(Music, UUID(str(result["music"]["music_id"])))
    if (
        snapshot is None or music is None
        or snapshot.digest != result["snapshot"]["digest"]
        or snapshot.origin_project_id != run.project_id
        or music.generated_by_user_id != snapshot.owner_id
        or music.is_public
        or snapshot.duration_ticks != result.get("duration_ticks")
        or snapshot.duration_ticks != score.duration_ticks
    ):
        raise ValueError("music preparation media identity is inconsistent")
    from app.tools.video.media_analysis import read_report

    analysis = await read_report(result["analysis_ref"])
    if (
        analysis.get("media_kind") != "audio"
        or analysis.get("analysis_scope") != "full"
        or (analysis.get("source_ref") or {}).get("digest") != snapshot.digest
        or not ((analysis.get("media_facts") or {}).get("decode") or {}).get("fully_decoded")
    ):
        raise ValueError("music audio analysis is not trustworthy")
    return {
        "music_id": str(music.id),
        "snapshot_id": str(snapshot.id),
        "snapshot_digest": snapshot.digest,
        "score_digest": score.score_digest,
        "duration_seconds": result["duration_seconds"],
        "analysis_ref": result["analysis_ref"],
        "cache_hit": bool(result.get("cache_hit")),
        "usage": result.get("usage") or {},
    }


__all__ = [
    "MusicPreparationError",
    "PrepareMusicArgs",
    "cached_music_preparation",
    "has_music_preparation_scope",
    "music_preparation_fact",
    "prepare_programmatic_music",
    "score_for_current_draft",
]
