"""Scene-bound narration preparation facts and model-directed draft retiming."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.chat.conversation_context import context_items
from app.editing.schemas import CompositionContent, SpeechObject, speech_text_digest
from app.editing.timing import (
    SOURCE_TIMEBASE,
    frames_to_ticks,
    seconds_to_ticks,
    source_ticks_to_output_ticks,
    ticks_to_frames,
)
from app.models.schemas import VideoDraftRef
from app.models.tables import Conversation


class NarrationDraftError(ValueError):
    pass


class SceneNarrationUpdate(BaseModel):
    """One model decision about one Scene; mechanical facts stay server-owned."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    text: str | None = Field(default=None, min_length=1, max_length=9000)
    voice_id: str | None = Field(default=None, min_length=1, max_length=255)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    target_duration_seconds: float | None = Field(default=None, gt=0, le=118, allow_inf_nan=False)
    alignment_id: UUID | None = None

    @model_validator(mode="after")
    def _bounded_change(self) -> SceneNarrationUpdate:
        if not any((
            self.text is not None,
            self.voice_id is not None,
            self.language is not None,
            self.target_duration_seconds is not None,
            self.alignment_id is not None,
        )):
            raise ValueError("narration_update needs a script, voice, timing or alignment decision")
        if self.alignment_id is not None and any((
            self.text is not None,
            self.voice_id is not None,
            self.language is not None,
        )):
            raise ValueError("changed narration needs a new original and alignment, not an old alignment_id")
        return self


async def recover_current_draft(db, project, reference: VideoDraftRef) -> dict[str, Any]:
    conversations = list((await db.scalars(select(Conversation).where(
        Conversation.project_id == project.id,
        Conversation.user_id == project.user_id,
    ))).all())
    for conversation in conversations:
        for item in reversed(context_items(conversation.context)):
            candidate = item.get("candidate") or {}
            if candidate.get("candidate_id") != reference.draft_id:
                continue
            if (
                candidate.get("active", True) is False
                or candidate.get("target_tool") != "design_video"
                or candidate.get("candidate_digest") != reference.draft_digest
            ):
                raise NarrationDraftError("draft_ref is stale or inactive")
            draft = item.get("executed_arguments") or item.get("arguments")
            if not isinstance(draft, dict) or not isinstance(draft.get("content"), dict):
                raise NarrationDraftError("the working draft is not recoverable")
            return deepcopy(draft)
    raise NarrationDraftError("the working draft is not recoverable")


def _speech_clip(content: CompositionContent, scene_id: str):
    matches = [
        clip
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.scene_id == scene_id
        and isinstance(clip.object, SpeechObject)
        and clip.object.alignment is None
    ]
    if len(matches) != 1:
        raise NarrationDraftError(f"Scene {scene_id} needs exactly one pending narration clip")
    return matches[0]


def scene_narration_request(draft: dict[str, Any], scene_id: str) -> dict[str, str]:
    content = CompositionContent.model_validate(draft.get("content") or {})
    speech = _speech_clip(content, scene_id).object
    assert isinstance(speech, SpeechObject)
    if not speech.voice_id or not speech.language:
        raise NarrationDraftError(f"Scene {scene_id} has no complete narration voice and language")
    return {
        "text": speech.text,
        "voice_id": speech.voice_id,
        "language": speech.language,
    }


def current_narration_facts(draft: dict[str, Any]) -> list[dict[str, Any]]:
    content = draft.get("content") or {}
    current = {
        scene_id: speech_text_digest(scene_narration_request(draft, scene_id)["text"])
        for scene_id in [scene.get("scene_id") for scene in content.get("scenes") or []]
        if any(
            clip.get("scene_id") == scene_id
            and (clip.get("object") or {}).get("kind") == "speech"
            and (clip.get("object") or {}).get("alignment") is None
            for track in (content.get("timeline") or {}).get("tracks") or []
            for clip in track.get("clips") or []
        )
    }
    return [
        deepcopy(item)
        for item in (draft.get("design") or {}).get("narrations") or []
        if current.get(item.get("scene_id")) == item.get("text_digest")
    ]


def _frame_duration(content: CompositionContent, seconds: float | int) -> tuple[int, int]:
    settings = content.settings
    ticks = seconds_to_ticks(seconds, settings.timebase)
    frames = ticks_to_frames(ticks, settings.timebase, settings.fps.num, settings.fps.den)
    return frames, frames_to_ticks(frames, settings.timebase, settings.fps.num, settings.fps.den)


def _retime_scene(content: CompositionContent, scene_id: str, target_ticks: int) -> None:
    scenes = sorted(content.scenes, key=lambda scene: scene.range.start)
    index = next((i for i, scene in enumerate(scenes) if scene.scene_id == scene_id), None)
    if index is None:
        raise NarrationDraftError(f"Scene {scene_id} does not exist in the current draft")
    target = scenes[index]
    old_end = target.range.end
    target.range.end = target.range.start + target_ticks
    delta = target.range.end - old_end
    for following in scenes[index + 1:]:
        following.range.start += delta
        following.range.end += delta
    for track in content.timeline.tracks:
        for clip in track.clips:
            if clip.scene_id == scene_id and clip.range.end == old_end:
                clip.range.end += delta
            elif clip.scene_id in {scene.scene_id for scene in scenes[index + 1:]}:
                clip.range.start += delta
                clip.range.end += delta
    dialogue = sorted(
        (
            clip
            for track in content.timeline.tracks
            if track.kind == "audio" and track.role == "dialogue"
            for clip in track.clips
        ),
        key=lambda clip: clip.range.start,
    )
    if any(current.range.start < previous.range.end for previous, current in zip(dialogue, dialogue[1:])):
        raise NarrationDraftError("retiming would overlap dialogue clips")


def _analysis_fact(snapshot) -> dict[str, Any]:
    reference = (snapshot.meta or {}).get("analysis_ref")
    if not isinstance(reference, dict) or not reference.get("digest"):
        raise NarrationDraftError("the narration Snapshot has no audio MediaAnalysisReport")
    return reference


async def update_scene_narration(
    db,
    *,
    owner_id: UUID,
    project_id: UUID,
    draft: dict[str, Any],
    update: SceneNarrationUpdate,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Apply only the model's target-Scene decision and derive all timing/cues."""
    from app.tools.video.alignment_store import ready_alignment
    from app.tools.video.media_analysis import read_report

    content = CompositionContent.model_validate(deepcopy(draft.get("content") or {}))
    speech_clip = _speech_clip(content, update.scene_id)
    speech = speech_clip.object
    assert isinstance(speech, SpeechObject)
    script_changed = any((
        update.text is not None,
        update.voice_id is not None,
        update.language is not None,
    ))
    if script_changed:
        revised = speech.model_copy(update={
            key: value
            for key, value in {
                "text": update.text,
                "voice_id": update.voice_id,
                "language": update.language,
            }.items()
            if value is not None
        })
        speech_clip.object = revised
        if update.target_duration_seconds is not None:
            _, ticks = _frame_duration(content, update.target_duration_seconds)
            _retime_scene(content, update.scene_id, ticks)
        return content.model_dump(mode="json"), None

    alignment_id = update.alignment_id
    if alignment_id is None:
        existing = next(
            (item for item in current_narration_facts(draft) if item.get("scene_id") == update.scene_id),
            None,
        )
        if existing is not None:
            alignment_id = UUID(str((existing.get("alignment") or {}).get("alignment_id")))
    if alignment_id is None:
        raise NarrationDraftError("prepare a READY alignment before confirming or retiming this Scene")
    alignment, snapshot, payload = await ready_alignment(
        db, owner_id=owner_id, alignment_id=alignment_id
    )
    if snapshot.origin_project_id != project_id:
        raise NarrationDraftError("the narration Snapshot belongs to another project")
    if alignment.text_digest != speech_text_digest(speech.text):
        raise NarrationDraftError("the READY alignment does not match this Scene's current script")
    analysis_ref = _analysis_fact(snapshot)
    analysis = await read_report(analysis_ref)
    if (
        analysis.get("media_kind") != "audio"
        or analysis.get("analysis_scope") != "full"
        or (analysis.get("source_ref") or {}).get("digest") != snapshot.digest
        or not ((analysis.get("media_facts") or {}).get("decode") or {}).get("fully_decoded")
    ):
        raise NarrationDraftError("the narration audio analysis is not trustworthy")

    scene = next(scene for scene in content.scenes if scene.scene_id == update.scene_id)
    required_ticks = source_ticks_to_output_ticks(payload.duration_ticks, content.settings.timebase)
    required_frames = math_ceil_fraction(
        Fraction(required_ticks, content.settings.timebase)
        * Fraction(content.settings.fps.num, content.settings.fps.den)
    )
    target_seconds = update.target_duration_seconds
    target_frames, target_ticks = _frame_duration(
        content,
        target_seconds if target_seconds is not None else scene.range.duration / content.settings.timebase,
    )
    if target_frames < required_frames or target_ticks < required_ticks:
        actual = payload.duration_ticks / SOURCE_TIMEBASE
        raise NarrationDraftError(
            f"Scene {update.scene_id} needs at least {actual:.3f}s for complete narration; "
            "change its script or target duration instead of trimming or speeding all narration"
        )
    _retime_scene(content, update.scene_id, target_ticks)
    scene = next(scene for scene in content.scenes if scene.scene_id == update.scene_id)
    cues = []
    for sentence in payload.sentences:
        start = scene.range.start + source_ticks_to_output_ticks(
            sentence.start_tick, content.settings.timebase
        )
        end = scene.range.start + source_ticks_to_output_ticks(
            sentence.end_tick, content.settings.timebase
        )
        if end <= start or end > scene.range.end:
            raise NarrationDraftError("a narration cue escapes its real audio window")
        cues.append({
            "cue_id": f"cue_{update.scene_id}_{sentence.sentence_id}",
            "sentence_id": sentence.sentence_id,
            "text": sentence.text,
            "text_range": {"start": sentence.text_start, "end": sentence.text_end},
            "source_range": {"start": sentence.start_tick, "end": sentence.end_tick},
            "output_range": {"start": start, "end": end},
        })
    fact = {
        "scene_id": update.scene_id,
        "text_digest": speech_text_digest(speech.text),
        "snapshot": {"snapshot_id": str(snapshot.id), "digest": snapshot.digest},
        "alignment": {
            "alignment_id": str(alignment.id),
            "content_digest": alignment.content_digest,
            "status": alignment.status,
        },
        "actual_duration_seconds": payload.duration_ticks / SOURCE_TIMEBASE,
        "source_duration_ticks": payload.duration_ticks,
        "source_timebase": payload.source_timebase,
        "target_duration_seconds": target_ticks / content.settings.timebase,
        "scene_range": scene.range.model_dump(mode="json"),
        "cues": cues,
        "analysis_ref": analysis_ref,
        "analysis": analysis,
    }
    return content.model_dump(mode="json"), fact


def math_ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def assert_narration_ready_for_score(draft: dict[str, Any]) -> None:
    content = CompositionContent.model_validate(draft.get("content") or {})
    facts = {item["scene_id"]: item for item in current_narration_facts(draft)}
    for scene in content.scenes:
        if not any(
            isinstance(clip.object, SpeechObject) and clip.object.alignment is None
            for track in content.timeline.tracks
            for clip in track.clips
            if clip.scene_id == scene.scene_id
        ):
            continue
        _speech_clip(content, scene.scene_id)
        fact = facts.get(scene.scene_id)
        if fact is None or (fact.get("alignment") or {}).get("status") != "READY":
            raise NarrationDraftError(f"Scene {scene.scene_id} has no READY narration fact")
        if int(fact["source_duration_ticks"]) <= 0 or not fact.get("cues"):
            raise NarrationDraftError(f"Scene {scene.scene_id} has no complete narration cues")
        required = source_ticks_to_output_ticks(
            int(fact["source_duration_ticks"]), content.settings.timebase
        )
        if scene.range.duration < required:
            raise NarrationDraftError(f"Scene {scene.scene_id} would truncate narration")


__all__ = [
    "NarrationDraftError",
    "SceneNarrationUpdate",
    "assert_narration_ready_for_score",
    "current_narration_facts",
    "recover_current_draft",
    "scene_narration_request",
    "update_scene_narration",
]
