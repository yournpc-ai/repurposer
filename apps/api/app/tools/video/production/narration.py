"""Terminal facts for the single narration-only Run scope."""
from __future__ import annotations

from uuid import UUID

from app.editing.schemas import speech_text_digest
from app.editing.timing import SOURCE_TIMEBASE
from app.models.schemas import AssetType
from app.models.tables import Asset, NarrationAlignment, Project, SourceSnapshot


def has_narration_preparation_scope(run) -> bool:
    return isinstance((run.context or {}).get("narration_preparation"), dict)


async def narration_preparation_fact(db, run, steps) -> dict:
    """Re-read fixed audio, alignment and actual usage; never infer success."""
    preparation = (run.context or {}).get("narration_preparation") or {}
    request = preparation.get("request") or {}
    result = preparation.get("result") or {}
    if not request or not result:
        raise ValueError("narration preparation has no fixed result")
    step = next((item for item in steps if item.kind == "prepare_narration"), None)
    if step is None or step.status != "done" or step.output_refs:
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
        "usage_characters": expected_usage,
        "cache_hit": bool(result.get("cache_hit")),
    }
