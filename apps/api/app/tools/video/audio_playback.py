"""Deliver measured project audio to the ordinary Chat transcript."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Literal
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import func, select

from app.models.schemas import VideoDraftRef, canonical_json_hash
from app.models.tables import Message, SourceSnapshot
from app.providers import storage
from app.tools.video.media_analysis import read_report


class PlaybackUnavailable(ValueError):
    pass


class ScoreDraftUnavailable(PlaybackUnavailable):
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
    except (ValueError, OSError, KeyError, BotoCoreError, ClientError) as exc:
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


def playback_key(opening_id: str, draft_id: str, role: str, scene_id: str | None,
                 snapshot_id: str, digest: str) -> str:
    return canonical_json_hash({
        "opening_id": opening_id, "draft_id": draft_id, "role": role,
        "scene_id": scene_id, "snapshot_id": snapshot_id, "digest": digest,
    })


async def record_run_audio(
    db, project, conversation_id, journey, role, preparation, *, trigger_intent, run_id, existing_message=None,
):
    parts = preparation.get("scenes")
    if not parts:
        return await record_prepared_audio(
            db, project, conversation_id, journey, role,
            preparation.get("result") or {}, preparation.get("request") or {},
            trigger_intent=trigger_intent, run_id=run_id, existing_message=existing_message,
        )
    from app.chat.service import _create_message

    intent = dict(trigger_intent)
    state, speech = "active", ""
    try:
        items = []
        for part in parts:
            measured, _ = await _measured_audio(db, project, part["result"])
            items.append({"role": role, "scene_id": part["request"]["scene_id"], **measured})
        intent.update(prepared_audio_items=items, presentation="media_progress")
    except PlaybackUnavailable:
        state = "blocked"
        speech = ("音频文件未通过校验，已暂停音频准备。" if str(project.language or "").startswith("zh")
                  else "Audio preparation paused because the recording could not be verified.")
    intent["media_journey"] = {**journey, "state": state}
    if existing_message is not None:
        existing_message.intent, existing_message.content = intent, speech
        return existing_message
    return await _create_message(db, conversation_id, "assistant", speech, intent=intent,
                                 workflow_run_id=run_id, turn_id=UUID(journey["opening_id"]))


async def record_prepared_audio(
    db, project, conversation_id, journey, role: Literal["narration", "music"],
    result: dict, request: dict, *, trigger_intent=None, run_id=None,
    existing_message=None, working_draft=None,
) -> Message:
    from app.chat.service import _create_message
    from app.tools.video.narration_draft import recover_current_draft

    zh = str(project.language or "").startswith("zh")
    state = "complete" if role == "music" else "active"
    intent = dict(trigger_intent or {})
    try:
        draft_id = (request.get("draft_ref") or {}).get("draft_id")
        if not draft_id:
            raise PlaybackUnavailable("missing draft identity")
        if role == "music":
            from app.chat.media_journey import audio_timing_issue
            try:
                draft = working_draft
                if draft is None:
                    draft = await recover_current_draft(db, project, VideoDraftRef.model_validate(request["draft_ref"]))
                if audio_timing_issue(draft):
                    raise ValueError("missing current narration timing")
            except (ValueError, KeyError) as exc:
                raise ScoreDraftUnavailable("score does not have current narration timing") from exc
        measured, _ = await _measured_audio(db, project, result)
        scene_id = result.get("scene_id") or request.get("scene_id")
        if role == "narration" and not scene_id:
            raise PlaybackUnavailable("missing narration scene")
        key = playback_key(
            journey["opening_id"], draft_id, role,
            scene_id, measured["snapshot_id"], measured["digest"],
        )
        # A cache observation and a Run settlement can land concurrently.
        # Serialize this one semantic use, without locking the conversation.
        lock = int.from_bytes(bytes.fromhex(key)[:8], "big", signed=True)
        await db.execute(select(func.pg_advisory_xact_lock(lock)))
        previous = await db.scalar(select(Message).where(
            Message.conversation_id == conversation_id,
            Message.intent["audio_playback_key"].as_string() == key,
        ).limit(1))
        if previous is not None and run_id is None:
            return previous
        intent["audio_playback_key"] = key  # Matches receipts written by older workers.
        intent["prepared_audio"] = {"role": role, "scene_id": scene_id, **measured}
        speech = ("配乐已准备好。" if zh else "The score is ready.") if role == "music" else ""
        if role == "narration":
            intent["presentation"] = "media_progress"
    except ScoreDraftUnavailable:
        state = "blocked"
        speech = "当前分镜的旁白时序尚未对齐，配乐准备已暂停。" if zh else (
            "Music preparation paused because the narration timing could not be verified."
        )
    except PlaybackUnavailable:
        state = "blocked"
        speech = "音频文件未通过校验，已暂停音频准备。" if zh else (
            "Audio preparation paused because the recording could not be verified."
        )

    intent["media_journey"] = {"opening_id": journey["opening_id"], "state": state}
    if existing_message is not None:
        existing_message.intent = intent
        existing_message.content = speech
        existing_message.blocks = [
            block for block in existing_message.blocks or [] if block.get("kind") != "audio_playback"
        ]
        return existing_message
    return await _create_message(
        db, conversation_id, "assistant", speech, intent=intent,
        workflow_run_id=run_id, turn_id=UUID(journey["opening_id"]),
    )
