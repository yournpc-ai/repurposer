"""Bounded high-level revisions expanded into ordinary edit operations."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.editing.edits import (
    AddClip,
    AddTrack,
    BindSource,
    Op,
    RemoveClip,
    TextAnimationTargetLost,
    replace_text_ops,
)
from app.editing.schemas import (
    CompositionContent,
    EditTarget,
    ImageObject,
    LayoutBox,
    SourceCaptionDerivation,
    TextObject,
    TimeRange,
    VideoObject,
)
from app.editing.timing import output_ticks_to_source_ticks, seconds_to_ticks


class RevisionInputError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        loc: list[str | int] | None = None,
        kind: str = "revision_input",
        issues: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.issues = issues or [{"loc": loc or [], "type": kind, "msg": message}]


class RevisionTargetAmbiguityError(RevisionInputError):
    def __init__(self, message: str, *, candidates: list[dict[str, Any]]):
        super().__init__(message, kind="target_ambiguous")
        self.candidates = candidates


class SetTextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["set_text"]
    clip_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Exact current Text Clip id; omit when the user's target is ambiguous "
            "so the server can return candidates."
        ),
    )
    text: str = Field(min_length=1, max_length=9000)


class ApplyPresetAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["apply_preset"]
    clip_id: str = Field(min_length=1, max_length=64)
    preset_id: str = Field(min_length=1, max_length=64)


class AddMediaOverlayAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["add_media_overlay"]
    source_id: UUID
    scene_id: str | None = Field(default=None, min_length=1, max_length=64)
    scope: Literal["window", "whole_scene"] = Field(
        default="window",
        description="whole_scene uses the saved Scene's exact range and needs no seconds.",
    )
    start_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    duration_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    position: Literal["top_left", "top_right", "bottom_left", "bottom_right"]
    width_ratio: float = Field(gt=0.05, le=1.0, allow_inf_nan=False)
    margin_px: float = Field(ge=0, le=512, allow_inf_nan=False)
    motion: Literal["none", "fade_in"]

    @model_validator(mode="after")
    def _window(self) -> AddMediaOverlayAction:
        if self.scope == "whole_scene" and any(
            value is not None
            for value in (self.start_seconds, self.end_seconds, self.duration_seconds)
        ):
            raise ValueError("whole_scene does not accept start, end or duration seconds")
        if (
            self.end_seconds is not None
            and self.start_seconds is not None
            and self.end_seconds <= self.start_seconds
        ):
            raise ValueError("end_seconds must be after start_seconds")
        return self


class AddNarrationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["add_narration"]
    source_id: UUID = Field(description="Frozen audio SourceSnapshot from prepare_narration")
    alignment_id: UUID = Field(description="READY NarrationAlignment for this exact audio")
    scene_id: str | None = Field(
        default=None,
        description="Scene receiving the narration and aligned captions; omit only when one Scene exists",
    )


class RemoveClipAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["remove_clip"]
    clip_id: str = Field(min_length=1, max_length=64)


RevisionAction = Annotated[
    SetTextAction
    | ApplyPresetAction
    | AddMediaOverlayAction
    | AddNarrationAction
    | RemoveClipAction,
    Field(discriminator="action"),
]


def _keyframe(at: int, value: Any, *, bezier: bool = False) -> dict[str, Any]:
    return {
        "at": at,
        "value": value,
        "easing": {"kind": "cubic_bezier", "params": [0.16, 1.0, 0.3, 1.0]}
        if bezier
        else {"kind": "linear", "params": None},
    }


def _opacity(animation_id: str, object_id: str, duration: int) -> dict[str, Any]:
    from app.editing.timing import frames_to_ticks

    return {
        "animation_id": animation_id,
        "target_object_id": object_id,
        "text_part": None,
        "property": "opacity",
        "keyframes": [
            _keyframe(0, 0.0),
            _keyframe(min(frames_to_ticks(15, 90000, 30, 1), duration), 1.0, bezier=True),
        ],
    }


def _clip_locations(content: CompositionContent, clip_id: str) -> list[tuple[Any, Any]]:
    return [
        (track, clip)
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.clip_id == clip_id
    ]


def _one_clip(content: CompositionContent, clip_id: str | None) -> tuple[Any, Any]:
    matches = (
        _clip_locations(content, clip_id)
        if clip_id is not None
        else [
            (track, clip)
            for track in content.timeline.tracks
            for clip in track.clips
            if isinstance(clip.object, TextObject) and clip.object.caption is None
        ]
    )
    if len(matches) != 1:
        candidates = [
            {
                "clip_id": clip.clip_id,
                "scene_id": clip.scene_id,
                "track_id": track.track_id,
                "text": clip.object.text if isinstance(clip.object, TextObject) else None,
            }
            for track, clip in matches
        ]
        if len(matches) > 1:
            raise RevisionTargetAmbiguityError(
                "clip target is not specified"
                if clip_id is None
                else f"clip target {clip_id!r} is not unique",
                candidates=candidates,
            )
        raise RevisionInputError(
            f"clip {clip_id!r} does not exist in the base version",
            loc=["action", "clip_id"],
            kind="target_not_found",
        )
    return matches[0]


def set_text_ops(content: CompositionContent, action: SetTextAction) -> list[Op]:
    _, clip = _one_clip(content, action.clip_id)
    if not isinstance(clip.object, TextObject) or (
        clip.object.caption is not None
        and not isinstance(clip.object.caption, SourceCaptionDerivation)
    ):
        raise RevisionInputError(
            "set_text supports native Text Clips and upload-ASR captions",
            loc=["action", "clip_id"],
            kind="unsupported_target",
        )
    try:
        if isinstance(clip.object.caption, SourceCaptionDerivation):
            clip = clip.model_copy(update={
                "object": clip.object.model_copy(update={
                    "caption": clip.object.caption.model_copy(update={"state": "independent"})
                })
            })
        return replace_text_ops(clip, action.text)
    except TextAnimationTargetLost as exc:
        raise RevisionInputError(
            str(exc),
            loc=["action", "text"],
            kind="animation_target_lost",
        ) from exc






def _confirmed_overlay_scenes(content: CompositionContent, user_text: str) -> list[Any]:
    text = user_text.lower()
    ordinals = [
        ("first", "opening", "开场", "第一镜", "第一幕", "第一段"),
        ("second", "第二镜", "第二幕", "第二段"),
        ("third", "第三镜", "第三幕", "第三段"),
        ("fourth", "第四镜", "第四幕", "第四段"),
        ("fifth", "第五镜", "第五幕", "第五段"),
        ("sixth", "第六镜", "第六幕", "第六段"),
    ]
    confirmed = []
    for index, scene in enumerate(sorted(content.scenes, key=lambda item: item.range.start)):
        terms = ordinals[index] if index < len(ordinals) else ()
        if scene.scene_id.lower() in text or any(
            term in text
            if term.startswith(("第", "开"))
            else f"{term} scene" in text or f"{term} shot" in text
            or term == "opening" and term in text
            for term in terms
        ):
            confirmed.append(scene)
    return confirmed


def _bind_overlay_request(
    content: CompositionContent,
    action: AddMediaOverlayAction,
    request_context: dict[str, Any] | None,
) -> AddMediaOverlayAction:
    if request_context is None:
        return action
    text = str(request_context.get("user_text") or "")
    confirmed = _confirmed_overlay_scenes(content, text)
    update = {}
    if action.scene_id is None and len(confirmed) == 1:
        update["scene_id"] = confirmed[0].scene_id
    if (
        action.scope == "window"
        and all(value is None for value in (action.start_seconds, action.end_seconds, action.duration_seconds))
        and any(term in text.lower() for term in ("整个", "整幕", "全幕", "whole", "entire"))
    ):
        update["scope"] = "whole_scene"
    return action.model_copy(update=update) if update else action


def _assert_overlay_scope_confirmed(
    content: CompositionContent,
    action: AddMediaOverlayAction,
    scene: Any,
    candidates: list[dict[str, Any]],
    request_context: dict[str, Any] | None,
) -> None:
    if request_context is None:
        return
    text = str(request_context.get("user_text") or "")
    if scene not in _confirmed_overlay_scenes(content, text):
        raise RevisionTargetAmbiguityError(
            "overlay Scene is not confirmed by the user's request or earlier explicit answer",
            candidates=candidates,
        )
    if action.scope == "whole_scene" and not any(
        term in text.lower() for term in ("整个", "整幕", "全幕", "whole", "entire")
    ):
        raise RevisionTargetAmbiguityError(
            "whole_scene needs the user's explicit whole-Scene choice or a numeric window",
            candidates=candidates,
        )
    if action.scope == "window" and not any(character.isdigit() for character in text):
        raise RevisionTargetAmbiguityError(
            "overlay time window is not uniquely specified; ask for an absolute start/end, "
            "an unambiguous start plus duration, or the whole Scene",
            candidates=candidates,
        )


def _add_overlay(
    content: CompositionContent,
    action: AddMediaOverlayAction,
    fact: dict[str, Any] | None,
    request_context: dict[str, Any] | None = None,
) -> list[Op]:
    if fact is None or not fact.get("storage_key"):
        raise RevisionInputError(
            "overlay source is missing or not prepared",
            loc=["action", "source_id"],
            kind="source_not_ready",
        )
    if fact.get("kind") not in {"video", "image"}:
        raise RevisionInputError(
            "overlay source must be a prepared image or video snapshot",
            loc=["action", "source_id"],
            kind="source_kind",
        )
    action = _bind_overlay_request(content, action, request_context)
    candidates = [
        {
            "scene_id": scene.scene_id,
            "start_seconds": scene.range.start / content.settings.timebase,
            "end_seconds": scene.range.end / content.settings.timebase,
        }
        for scene in sorted(content.scenes, key=lambda item: item.range.start)
    ]
    if action.scene_id is None:
        raise RevisionTargetAmbiguityError(
            "overlay Scene is not uniquely specified; ask the user which Scene to use",
            candidates=candidates,
        )
    scene = next((item for item in content.scenes if item.scene_id == action.scene_id), None)
    if scene is None:
        raise RevisionInputError(
            "overlay scene does not exist in the base version",
            loc=["action", "scene_id"],
            kind="target_not_found",
        )
    _assert_overlay_scope_confirmed(content, action, scene, candidates, request_context)
    if action.scope == "whole_scene":
        start, end = scene.range.start, scene.range.end
    else:
        has_end = action.end_seconds is not None
        has_duration = action.duration_seconds is not None
        if action.start_seconds is None or has_end == has_duration:
            raise RevisionTargetAmbiguityError(
                "overlay time window is not uniquely specified; ask for an absolute start/end, "
                "an unambiguous start plus duration, or the whole Scene",
                candidates=candidates,
            )
        start = seconds_to_ticks(action.start_seconds, content.settings.timebase)
        end = (
            seconds_to_ticks(action.end_seconds, content.settings.timebase)
            if action.end_seconds is not None
            else start + seconds_to_ticks(action.duration_seconds, content.settings.timebase)
        )
    if start < scene.range.start or end > scene.range.end:
        raise RevisionInputError(
            "overlay time window must stay inside its target Scene",
            loc=["action", "start_seconds"],
            kind="time_out_of_bounds",
        )
    track_id, clip_id, object_id = _stable_overlay_ids(action)
    existing_track = next(
        (track for track in content.timeline.tracks if track.track_id == track_id), None
    )
    if _clip_locations(content, clip_id):
        raise RevisionInputError(
            "this exact overlay already exists in the base version", kind="duplicate_overlay"
        )
    source_range = None
    if fact["kind"] == "video":
        source_duration = output_ticks_to_source_ticks(end - start, content.settings.timebase)
        if source_duration > (fact.get("duration_ticks") or 0):
            raise RevisionInputError(
                "overlay window exceeds the source video's real duration",
                loc=["action", "end_seconds"],
                kind="source_too_short",
            )
        source_range = TimeRange(start=0, end=source_duration)
    layout = _overlay_layout(content, action, fact)
    obj = (
        VideoObject(kind="video", object_id=object_id, layout=layout, fit="contain")
        if fact["kind"] == "video"
        else ImageObject(kind="image", object_id=object_id, layout=layout, fit="contain")
    )
    animations = (
        [_opacity(f"anm_{clip_id}_fade", object_id, end - start)]
        if action.motion == "fade_in"
        else []
    )
    order = (
        existing_track.order
        if existing_track is not None
        else (
            max(
                (track.order for track in content.timeline.tracks if track.kind == "visual"),
                default=-1,
            )
            + 1
        )
    )
    ops: list[Op] = []
    if action.source_id not in {binding.snapshot_id for binding in content.sources}:
        ops.append(BindSource(op="bind_source", snapshot_id=action.source_id))
    if existing_track is None:
        ops.append(
            AddTrack.model_validate(
                {
                    "op": "add_track",
                    "track": {
                        "track_id": track_id,
                        "kind": "visual",
                        "role": "effect",
                        "order": order,
                        "clips": [],
                    },
                }
            )
        )
    ops.append(
        AddClip.model_validate(
            {
                "op": "add_clip",
                "track_id": track_id,
                "clip": {
                    "clip_id": clip_id,
                    "range": {"start": start, "end": end},
                    "scene_id": scene.scene_id,
                    "source": {
                        "snapshot_id": str(action.source_id),
                        "snapshot_digest": fact["digest"],
                        "source_range": source_range.model_dump(mode="json")
                        if source_range
                        else None,
                    },
                    "object": obj.model_dump(mode="json"),
                    "animations": animations,
                },
            }
        )
    )
    return ops


def _add_narration(
    content: CompositionContent,
    action: AddNarrationAction,
    fact: dict[str, Any] | None,
    alignment: Any,
) -> list[Op]:
    if fact is None or fact.get("kind") != "audio" or not fact.get("storage_key"):
        raise RevisionInputError(
            "narration source is not a prepared audio snapshot",
            loc=["action", "source_id"], kind="source_not_ready",
        )
    scene = next((item for item in content.scenes if item.scene_id == action.scene_id), None)
    if scene is None and action.scene_id is None and len(content.scenes) == 1:
        scene = content.scenes[0]
    if scene is None:
        candidates = [{"scene_id": item.scene_id} for item in content.scenes]
        if action.scene_id is None:
            raise RevisionTargetAmbiguityError(
                "narration Scene is not uniquely specified", candidates=candidates,
            )
        raise RevisionInputError(
            "narration scene does not exist in the base version",
            loc=["action", "scene_id"], kind="target_not_found",
        )
    from app.editing.narration_audio import narration_audio_ops

    try:
        return narration_audio_ops(
            content,
            scene_id=scene.scene_id,
            snapshot_id=action.source_id,
            snapshot_digest=fact["digest"],
            alignment=alignment,
        )
    except ValueError as exc:
        raise RevisionInputError(
            str(exc), loc=["action", "alignment_id"], kind="source_not_ready",
        ) from exc


def _overlay_layout(
    content: CompositionContent, action: AddMediaOverlayAction, fact: dict[str, Any]
) -> LayoutBox:
    media = fact.get("meta") or {}
    dimensions = media.get("media") or media
    width, height = dimensions.get("width"), dimensions.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise RevisionInputError(
            "overlay source lacks probed pixel dimensions",
            loc=["action", "source_id"],
            kind="source_not_ready",
        )
    box_width = content.settings.width * action.width_ratio
    box_height = box_width * height / width
    available_height = content.settings.height - 2 * action.margin_px
    if box_height > available_height:
        raise RevisionInputError(
            "width_ratio and source aspect do not fit inside the canvas margins",
            loc=["action", "width_ratio"],
            kind="layout_out_of_bounds",
        )
    x = (
        action.margin_px
        if action.position.endswith("left")
        else content.settings.width - action.margin_px - box_width
    )
    y = (
        action.margin_px
        if action.position.startswith("top")
        else content.settings.height - action.margin_px - box_height
    )
    return LayoutBox(x=x, y=y, width=box_width, height=box_height)


def _stable_overlay_ids(action: AddMediaOverlayAction) -> tuple[str, str, str]:
    digest = hashlib.sha256(action.model_dump_json().encode("utf-8")).hexdigest()[:12]
    return f"trk_overlay_{digest}", f"clp_overlay_{digest}", f"obj_overlay_{digest}"


def expand_revision_action(
    action: RevisionAction,
    content: CompositionContent,
    *,
    facts: dict[UUID, dict[str, Any]],
    request_context: dict[str, Any] | None = None,
    narration_alignment: Any = None,
) -> list[Op]:
    from app.editing.presets import expand_preset_at_target

    if isinstance(action, SetTextAction):
        return set_text_ops(content, action)
    if isinstance(action, ApplyPresetAction):
        _one_clip(content, action.clip_id)
        return expand_preset_at_target(
            action.preset_id, content, EditTarget(kind="clip", id=action.clip_id)
        )
    if isinstance(action, AddMediaOverlayAction):
        return _add_overlay(content, action, facts.get(action.source_id), request_context)
    if isinstance(action, AddNarrationAction):
        return _add_narration(content, action, facts.get(action.source_id), narration_alignment)
    _one_clip(content, action.clip_id)
    if sum(len(track.clips) for track in content.timeline.tracks) == 1:
        raise RevisionInputError(
            "remove_clip cannot remove the version's only Clip",
            loc=["action", "clip_id"],
            kind="unsupported_action",
        )
    return [RemoveClip(op="remove_clip", clip_id=action.clip_id)]


__all__ = [
    "AddMediaOverlayAction",
    "AddNarrationAction",
    "ApplyPresetAction",
    "RemoveClipAction",
    "RevisionAction",
    "RevisionInputError",
    "RevisionTargetAmbiguityError",
    "SetTextAction",
    "expand_revision_action",
    "set_text_ops",
]
