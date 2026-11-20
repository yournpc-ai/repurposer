"""Deliver measured project audio to the ordinary Chat transcript."""

from __future__ import annotations

import hashlib
import math
from typing import Any
from uuid import UUID


from app.models.tables import SourceSnapshot
from app.providers import storage
from app.tools.video.media_analysis import read_report


class PlaybackUnavailable(ValueError):
    pass


async def _measured_audio(db, project, result: dict):
    snapshot_ref = result.get("snapshot") or {}
    snapshot_id = result.get("audio_snapshot_id") or snapshot_ref.get("snapshot_id")
    digest = result.get("audio_digest") or snapshot_ref.get("digest")
    try:
        identity = UUID(str(snapshot_id))
    except ValueError as exc:
        raise PlaybackUnavailable("missing audio snapshot") from exc
    snapshot = await db.get(SourceSnapshot, identity)
    if (
        snapshot is None or snapshot.owner_id != project.user_id
        or snapshot.origin_project_id != project.id or snapshot.kind != "audio"
        or snapshot.digest != digest
    ):
        raise PlaybackUnavailable("audio snapshot identity mismatch")
    reference = (snapshot.meta or {}).get("analysis_ref")
    if not isinstance(reference, dict) or not reference or result.get("analysis_ref", reference) != reference:
        raise PlaybackUnavailable("missing or stale audio analysis")
    try:
        report = await read_report(reference)
        audio = await storage.read(snapshot.storage_key)
    except (ValueError, KeyError) as exc:
        raise PlaybackUnavailable("audio or analysis cannot be read") from exc
    if hashlib.sha256(audio).hexdigest() != digest:
        raise PlaybackUnavailable("stored audio differs from the measured snapshot")
    source = report.get("source_ref") or {}
    facts = report.get("media_facts") or {}
    decode = facts.get("decode") or {}
    duration = decode.get("duration_seconds")
    if (
        report.get("analysis_scope") != "full" or report.get("media_kind") != "audio"
        or source.get("digest") != digest or source.get("snapshot_id") != str(snapshot.id)
        or not decode.get("fully_decoded") or not isinstance(duration, (int, float))
        or not math.isfinite(duration) or duration <= 0
    ):
        raise PlaybackUnavailable("incomplete audio measurements")
    return {"snapshot_id": str(snapshot.id), "digest": digest, "duration_seconds": duration}, report


async def playback_item(db, project, role: str, result: dict, request: dict) -> dict:
    measured, report = await _measured_audio(db, project, result)
    return _playback_item(measured, report, role, result, request)


def _playback_item(measured: dict, report: dict, role: str, result: dict, request: dict) -> dict:
    waveform = report["media_facts"].get("waveform") or {}
    peaks = waveform.get("peak")
    if (
        waveform.get("source") != "full_decoded_pcm" or not isinstance(peaks, list)
        or not peaks or len(peaks) != waveform.get("bucket_count")
        or any(not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 for p in peaks)
    ):
        raise PlaybackUnavailable("incomplete waveform")
    return {
        **measured,
        "role": role, "scene_id": result.get("scene_id") or request.get("scene_id"),
        "title": ((result.get("music") or {}).get("title") or request.get("name") or "")
        if role == "music" else request.get("text") or result.get("text") or "",
        "peaks": peaks, "analysis_digest": report["report_digest"],
    }


def audio_preparation(run):
    for role in ("narration", "music"):
        preparation = (run.context or {}).get(f"{role}_preparation")
        if isinstance(preparation, dict):
            return role, preparation
    return None


async def audio_playback_blocks(db, run, project) -> list[dict[str, Any]]:
    audio = audio_preparation(run)
    if audio is None:
        return []
    role, preparation = audio
    try:
        items = [await playback_item(db, project, role, part.get("result") or {}, part.get("request") or {})
                 for part in preparation.get("scenes") or [preparation]]
    except PlaybackUnavailable:
        return []
    return [{"kind": "audio_playback", "project_id": str(project.id), "items": items}]
