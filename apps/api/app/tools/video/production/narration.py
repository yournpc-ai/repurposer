"""Verified terminal facts for narration-only Runs."""
from __future__ import annotations

from uuid import UUID

from app.editing.schemas import speech_text_digest
from app.editing.timing import SOURCE_TIMEBASE
from app.models.schemas import AssetType
from app.models.tables import Asset, NarrationAlignment, Project, SourceSnapshot


def has_narration_preparation_scope(run) -> bool:
    return isinstance((run.context or {}).get("narration_preparation"), dict)


async def narration_preparation_facts(db, run, steps) -> list[dict]:
    """Re-read fixed audio, alignment and actual usage; never infer success."""
    preparation = (run.context or {}).get("narration_preparation") or {}
    parts = preparation.get("scenes") or [preparation]
    nodes = sorted((s for s in steps if s.kind == "prepare_narration"), key=lambda s: getattr(s, "seq", 0))
    if len(nodes) != len(parts):
        raise ValueError("narration settlement is incomplete")
    return [await _scene_fact(db, run, step, part) for step, part in zip(nodes, parts, strict=True)]


async def _scene_fact(db, run, step, preparation) -> dict:
    request = preparation.get("request") or {}
    result = preparation.get("result") or {}
    if not request or not result:
        raise ValueError("narration preparation has no fixed result")
    scene = request.get("scene_id")
    if scene and (scene != result.get("scene_id") or scene != (step.spec or {}).get("scene_id")):
        raise ValueError("narration preparation scene identity is inconsistent")
    if step.status != "done" or step.output_refs:
        raise ValueError("narration preparation did not settle as an Output-free step")

    project = await db.get(Project, run.project_id)
    asset = await db.get(Asset, UUID(str(result.get("asset_id"))))
    snapshot = await db.get(SourceSnapshot, UUID(str(result.get("audio_snapshot_id"))))
    alignment = await db.get(NarrationAlignment, UUID(str(result.get("alignment_id"))))
    if project is None or asset is None or snapshot is None or alignment is None:
        raise ValueError("narration preparation facts are missing")
    if (
        asset.user_id != project.user_id
        or asset.project_id != project.id
        or asset.type != AssetType.AUDIO
        or snapshot.owner_id != project.user_id
        or snapshot.asset_id != asset.id
        or snapshot.kind != "audio"
        or snapshot.digest != result.get("audio_digest")
        or snapshot.duration_ticks is None
    ):
        raise ValueError("narration preparation audio identity is inconsistent")
    if (
        alignment.owner_id != project.user_id
        or alignment.audio_snapshot_id != snapshot.id
        or alignment.audio_digest != snapshot.digest
        or alignment.text_digest != speech_text_digest(str(request.get("text") or ""))
        or alignment.status not in {"PENDING", "PROCESSING", "ALIGNED", "READY", "FAILED"}
    ):
        raise ValueError("narration preparation alignment identity is inconsistent")

    analysis_ref = result.get("analysis_ref") or (snapshot.meta or {}).get("analysis_ref")
    if result.get("scene_id") is not None and not analysis_ref:
        raise ValueError("scene narration has no fixed audio analysis")
    analysis = None
    if analysis_ref:
        from app.tools.video.media_analysis import read_report

        analysis = await read_report(analysis_ref)
        if (
            analysis.get("media_kind") != "audio"
            or analysis.get("analysis_scope") != "full"
            or (analysis.get("source_ref") or {}).get("digest") != snapshot.digest
            or not ((analysis.get("media_facts") or {}).get("decode") or {}).get("fully_decoded")
        ):
            raise ValueError("scene narration audio analysis is not trustworthy")
    expected_usage = int(result.get("usage_characters") or 0)
    actual_usage = (step.cost or {}).get("units", {}).get("tts_chars", 0)
    if float(actual_usage or 0) != float(expected_usage):
        raise ValueError("narration preparation TTS usage does not match its settled step")
    return {
        "asset_id": str(asset.id),
        "audio_snapshot_id": str(snapshot.id),
        "audio_digest": snapshot.digest,
        "duration_seconds": snapshot.duration_ticks / SOURCE_TIMEBASE,
        "alignment_id": str(alignment.id),
        "alignment_status": alignment.status,
        "scene_id": result.get("scene_id"),
        "draft_ref": result.get("draft_ref"),
        "analysis_ref": result.get("analysis_ref") or (snapshot.meta or {}).get("analysis_ref"),
        "usage_characters": expected_usage,
        "cache_hit": bool(result.get("cache_hit")),
    }
