"""Persistent audio-playback references for ordinary Chat message blocks."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.tables import SourceSnapshot
from app.tools.video.media_analysis import read_report


async def audio_playback_blocks(db, run, project) -> list[dict[str, Any]]:
    preparations = [
        ("narration", (run.context or {}).get("narration_preparation")),
        ("music", (run.context or {}).get("music_preparation")),
    ]
    items = []
    for role, preparation in preparations:
        if not isinstance(preparation, dict):
            continue
        result = preparation.get("result") or {}
        snapshot_id = result.get("audio_snapshot_id") or (result.get("snapshot") or {}).get("snapshot_id")
        digest = result.get("audio_digest") or (result.get("snapshot") or {}).get("digest")
        if not snapshot_id or not digest:
            continue
        snapshot = await db.get(SourceSnapshot, UUID(str(snapshot_id)))
        if (
            snapshot is None
            or snapshot.owner_id != project.user_id
            or snapshot.origin_project_id != run.project_id
            or snapshot.kind != "audio"
            or snapshot.digest != digest
        ):
            continue
        analysis_ref = result.get("analysis_ref") or (snapshot.meta or {}).get("analysis_ref")
        if not analysis_ref:
            continue
        try:
            analysis = await read_report(analysis_ref)
        except (ValueError, OSError, KeyError):
            continue
        facts = analysis.get("media_facts") or {}
        waveform = facts.get("waveform") or {}
        peaks = waveform.get("peak") or []
        if (
            analysis.get("media_kind") != "audio"
            or (analysis.get("source_ref") or {}).get("digest") != digest
            or not (facts.get("decode") or {}).get("fully_decoded")
            or not peaks
        ):
            continue
        request = preparation.get("request") or {}
        items.append({
            "role": role,
            "snapshot_id": str(snapshot.id),
            "digest": snapshot.digest,
            "scene_id": result.get("scene_id"),
            "title": (
                str((result.get("music") or {}).get("title") or request.get("name") or "")
                if role == "music" else str(request.get("text") or "")
            ),
            "duration_seconds": (
                result.get("duration_seconds")
                or facts.get("decode", {}).get("duration_seconds")
            ),
            "peaks": peaks,
            "analysis_digest": analysis.get("report_digest"),
        })
    if not items:
        return []
    return [{
        "kind": "audio_playback",
        "project_id": str(run.project_id),
        "items": items,
    }]


__all__ = ["audio_playback_blocks"]
