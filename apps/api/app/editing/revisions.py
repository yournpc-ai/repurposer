"""Direct revision Ops expanded into the ordinary editing algebra."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.editing.edits import (
    AddClip,
    AddTrack,
    BindSource,
    Op,
    RemoveClip,
    UpdateClip,
    TextAnimationTargetLost,
    replace_text_ops,
)
from app.editing.schemas import (
    AudioObject,
    CompositionContent,
    EditTarget,
    ImageObject,
    LayoutBox,
    SourceCaptionDerivation,
    SpeechObject,
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


class SetTextOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_text"]
    clip_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "当前文字 Clip 的确切 ID。若用户指向不明确则省略，以便服务端返回候选。"
        ),
    )
    text: str = Field(min_length=1, max_length=9000)


class ApplyPresetOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["apply_preset"]
    clip_id: str = Field(min_length=1, max_length=64)
    preset_id: str = Field(min_length=1, max_length=64)


class AddNarrationOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_narration"]
    source_id: UUID = Field(description="来自 prepare_narration 的固定音频 SourceSnapshot。")
    alignment_id: UUID = Field(description="与该音频精确对应且状态为 READY 的 NarrationAlignment。")
    scene_id: str | None = Field(
        default=None,
        description="接收旁白和对齐字幕的 Scene，仅在作品只有一个场景时可省略。",
    )


class AddAudioEffectOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_audio_effect"]
    source_id: UUID = Field(description="已准备的音频 SourceSnapshot，例如已导入的 CC0 音效。")
    scene_id: str | None = Field(
        default=None,
        description="接收音效的 Scene，仅在作品只有一个场景时可省略。",
    )
    start_seconds: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="目标 Scene 内的绝对成片起始秒数。",
    )
    source_start_seconds: float = Field(
        default=0,
        ge=0,
        allow_inf_nan=False,
        description="可选，在源音频内开始裁切的秒数。",
    )
    duration_seconds: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="可选，按 1 倍速计算的源/成片时长。省略则使用余下的源音频。",
    )
    gain_db: float = Field(default=0.0, ge=-60, le=12)


class SetNarrationOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_narration"]
    clip_id: str | None = Field(
        default=None,
        description="待处理 Speech Clip 的确切 ID。仅有一个待处理语音片段时可省略。",
    )
    text: str = Field(min_length=1, max_length=9000)


class RemoveClipOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_clip"]
    clip_id: str = Field(min_length=1, max_length=64)


RevisionOp = Annotated[
    SetTextOp
    | ApplyPresetOp
    | AddNarrationOp
    | AddAudioEffectOp
    | SetNarrationOp
    | RemoveClipOp,
    Field(discriminator="op"),
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


def set_text_ops(content: CompositionContent, action: SetTextOp) -> list[Op]:
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






def set_narration_ops(content: CompositionContent, action: SetNarrationOp) -> list[Op]:
    matches = (
        _clip_locations(content, action.clip_id)
        if action.clip_id is not None
        else [
            (track, clip)
            for track in content.timeline.tracks
            for clip in track.clips
            if isinstance(clip.object, SpeechObject) and clip.object.alignment is None
        ]
    )
    if len(matches) != 1:
        candidates = [
            {
                "clip_id": clip.clip_id,
                "scene_id": clip.scene_id,
                "track_id": track.track_id,
                "text": clip.object.text if isinstance(clip.object, SpeechObject) else None,
            }
            for track, clip in matches
        ]
        if len(matches) > 1:
            raise RevisionTargetAmbiguityError(
                "narration clip target is not specified",
                candidates=candidates,
            )
        raise RevisionInputError(
            f"narration clip {action.clip_id!r} does not exist in the base version",
            loc=["action", "clip_id"],
            kind="target_not_found",
        )
    _, clip = matches[0]
    if not isinstance(clip.object, SpeechObject) or clip.object.alignment is not None:
        raise RevisionInputError(
            "set_narration supports pending Speech Clips only; source-aligned narration is immutable",
            loc=["action", "clip_id"],
            kind="unsupported_target",
        )
    if clip.object.text == action.text:
        return []
    return [UpdateClip(
        op="update_clip",
        clip_id=clip.clip_id,
        object=clip.object.model_copy(update={"text": action.text}),
    )]


def fixed_visual_ops(content: CompositionContent, fact: dict[str, Any], *, source_id: UUID,
                     identity: str, scene_id: str | None, start: int, end: int, position: str,
                     width_ratio: float, margin_px: float, fade_in: bool = False) -> list[Op]:
    track_id = f"trk_overlay_{identity}"
    clip_id = f"clp_overlay_{identity}"
    object_id = f"obj_overlay_{identity}"
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
    layout = _overlay_layout(content, fact, position, width_ratio, margin_px)
    obj = (
        VideoObject(kind="video", object_id=object_id, layout=layout, fit="contain")
        if fact["kind"] == "video"
        else ImageObject(kind="image", object_id=object_id, layout=layout, fit="contain")
    )
    animations = (
        [_opacity(f"anm_{clip_id}_fade", object_id, end - start)]
        if fade_in
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
    if source_id not in {binding.snapshot_id for binding in content.sources}:
        ops.append(BindSource(op="bind_source", snapshot_id=source_id))
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
                    "scene_id": scene_id,
                    "source": {
                        "snapshot_id": str(source_id),
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


def _add_audio_effect(
    content: CompositionContent,
    action: AddAudioEffectOp,
    fact: dict[str, Any] | None,
) -> list[Op]:
    if (
        fact is None
        or fact.get("kind") != "audio"
        or not fact.get("storage_key")
        or not fact.get("duration_ticks")
    ):
        raise RevisionInputError(
            "audio effect source is not a prepared audio snapshot with real duration",
            loc=["action", "source_id"],
            kind="source_not_ready",
        )
    scene = next((item for item in content.scenes if item.scene_id == action.scene_id), None)
    if scene is None and action.scene_id is None and len(content.scenes) == 1:
        scene = content.scenes[0]
    if scene is None:
        candidates = [{"scene_id": item.scene_id} for item in content.scenes]
        if action.scene_id is None:
            raise RevisionTargetAmbiguityError(
                "audio effect Scene is not uniquely specified", candidates=candidates,
            )
        raise RevisionInputError(
            "audio effect scene does not exist in the base version",
            loc=["action", "scene_id"],
            kind="target_not_found",
        )
    source_start = seconds_to_ticks(action.source_start_seconds, content.settings.timebase)
    available = fact["duration_ticks"] - source_start
    duration = (
        seconds_to_ticks(action.duration_seconds, content.settings.timebase)
        if action.duration_seconds is not None
        else available
    )
    if duration <= 0 or duration > available:
        raise RevisionInputError(
            "audio effect window exceeds the source audio's real duration",
            loc=["action", "duration_seconds"],
            kind="source_too_short",
        )
    start = seconds_to_ticks(action.start_seconds, content.settings.timebase)
    end = start + duration
    if start < scene.range.start or end > scene.range.end:
        raise RevisionInputError(
            "audio effect time window must stay inside its target Scene",
            loc=["action", "start_seconds"],
            kind="time_out_of_bounds",
        )
    track_id = "trk_audio_effect"
    digest = hashlib.sha256(action.model_dump_json().encode("utf-8")).hexdigest()[:12]
    clip_id = f"clp_audio_effect_{digest}"
    if _clip_locations(content, clip_id):
        raise RevisionInputError(
            "this exact audio effect already exists in the base version",
            kind="duplicate_audio_effect",
        )
    return fixed_audio_ops(
        content, source_id=action.source_id, source_digest=fact["digest"], track_id=track_id,
        role="effect", clip_id=clip_id, object_id=f"obj_audio_effect_{digest}", scene_id=scene.scene_id,
        start=start, end=end, source_start=source_start,
        source_end=source_start + output_ticks_to_source_ticks(duration, content.settings.timebase),
        gain_db=action.gain_db,
    )


def motion_block_ops(
    content: CompositionContent,
    *,
    block_id: str,
    props: dict[str, Any],
    resources: list[dict[str, Any]],
    clip_id: str,
    object_id: str,
    scene_id: str | None,
    start: int,
    end: int,
) -> list[Op]:
    """Place a native MotionBlockObject on a non-colliding visual track below captions."""
    from app.editing.edits import SetTrackOrder
    from app.editing.schemas import LayoutBox, MotionBlockObject, RemotionResource

    role = "title" if block_id == "kinetic_title" else "main"
    prefix = f"trk_mg_{role}"

    def overlaps(track) -> bool:
        return any(c.range.start < end and start < c.range.end for c in track.clips)

    visual_tracks = [t for t in content.timeline.tracks if t.kind == "visual"]
    candidate_tracks = sorted(
        (t for t in visual_tracks if t.role == role and t.track_id.startswith(prefix)),
        key=lambda t: t.order,
    )
    target_track = next((t for t in candidate_tracks if not overlaps(t)), None)

    ops: list[Op] = []
    bound = {binding.snapshot_id for binding in content.sources}
    typed_resources = [RemotionResource.model_validate(r) for r in resources]
    for r in typed_resources:
        if r.snapshot_id not in bound:
            ops.append(BindSource(op="bind_source", snapshot_id=r.snapshot_id))
            bound.add(r.snapshot_id)

    if target_track is not None:
        track_id = target_track.track_id
    else:
        existing_ids = {t.track_id for t in content.timeline.tracks}
        track_id = prefix
        suffix = 2
        while track_id in existing_ids:
            track_id = f"{prefix}_{suffix}"
            suffix += 1

        # Keep Z-order deterministic: main < title < caption.
        if role == "main":
            above_roles = {"title", "caption"}
        else:
            above_roles = {"caption"}
        below = [t for t in visual_tracks if t.role not in above_roles]
        above = sorted((t for t in visual_tracks if t.role in above_roles), key=lambda t: t.order)
        desired_order = max((t.order for t in below), default=-1) + 1
        # Bump any visual tracks at or above desired_order that belong above this layer
        # (including title/caption tracks) so track orders stay strictly unique.
        to_bump = sorted(
            (t for t in visual_tracks if t.order >= desired_order),
            key=lambda t: t.order,
            reverse=True,
        )
        # Only bump tracks that belong in above_roles; if another same/lower track already
        # sits at desired_order, step past it.
        if any(t.role not in above_roles for t in to_bump):
            if above:
                min_above = min(t.order for t in above)
                non_above_below_min = [t for t in visual_tracks if t.role not in above_roles and t.order < min_above]
                desired_order = max((t.order for t in non_above_below_min), default=-1) + 1
                to_bump = sorted(
                    (t for t in visual_tracks if t.order >= desired_order),
                    key=lambda t: t.order,
                    reverse=True,
                )
            else:
                desired_order = max((t.order for t in visual_tracks), default=-1) + 1
                to_bump = []
        for t in to_bump:
            ops.append(SetTrackOrder(op="set_track_order", track_id=t.track_id, order=t.order + 1))

        ops.append(
            AddTrack(
                op="add_track",
                track={
                    "track_id": track_id,
                    "kind": "visual",
                    "role": role,
                    "order": desired_order,
                    "clips": [],
                },
            )
        )

    obj = MotionBlockObject(
        kind="motion_block",
        object_id=object_id,
        block_id=block_id,
        block_version=1,
        props=props,
        resources=typed_resources,
        layout=LayoutBox(
            x=0,
            y=0,
            width=content.settings.width,
            height=content.settings.height,
        ),
        fit="cover" if block_id == "product_showcase" else "contain",
    )
    ops.append(
        AddClip(
            op="add_clip",
            track_id=track_id,
            clip={
                "clip_id": clip_id,
                "range": {"start": start, "end": end},
                "scene_id": scene_id,
                "source": None,
                "object": obj.model_dump(mode="json"),
                "animations": [],
            },
        )
    )
    return ops


def fixed_audio_ops(content, *, source_id, source_digest, track_id, role, clip_id, object_id,
                    scene_id, start, end, source_start, source_end, gain_db):
    ops: list[Op] = []
    if source_id not in {binding.snapshot_id for binding in content.sources}:
        ops.append(BindSource(op="bind_source", snapshot_id=source_id))
    if not any(track.track_id == track_id for track in content.timeline.tracks):
        ops.append(AddTrack(
            op="add_track",
            track={
                "track_id": track_id,
                "kind": "audio",
                "role": role,
                "order": max(
                    (track.order for track in content.timeline.tracks if track.kind == "audio"),
                    default=-1,
                ) + 1,
                "clips": [],
            },
        ))
    ops.append(AddClip(
        op="add_clip",
        track_id=track_id,
        clip={
            "clip_id": clip_id,
            "range": {"start": start, "end": end},
            "scene_id": scene_id,
            "source": {
                "snapshot_id": str(source_id),
                "snapshot_digest": source_digest,
                "source_range": {
                    "start": source_start,
                    "end": source_end,
                },
            },
            "object": AudioObject(
                kind="audio",
                object_id=object_id,
                gain_db=gain_db,
            ).model_dump(mode="json"),
            "animations": [],
        },
    ))
    return ops


def _add_narration(
    content: CompositionContent,
    action: AddNarrationOp,
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
    content: CompositionContent, fact: dict[str, Any], position: str, width_ratio: float, margin_px: float
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
    box_width = content.settings.width * width_ratio
    box_height = box_width * height / width
    available_height = content.settings.height - 2 * margin_px
    if box_height > available_height or box_width > content.settings.width - 2 * margin_px:
        raise RevisionInputError(
            "width_ratio and source aspect do not fit inside the canvas margins",
            loc=["action", "width_ratio"],
            kind="layout_out_of_bounds",
        )
    x = (
        margin_px
        if position.endswith("left")
        else content.settings.width - margin_px - box_width
    )
    y = (
        margin_px
        if position.startswith("top")
        else content.settings.height - margin_px - box_height
    )
    return LayoutBox(x=x, y=y, width=box_width, height=box_height)


def expand_revision_op(
    operation: RevisionOp,
    content: CompositionContent,
    *,
    facts: dict[UUID, dict[str, Any]],
    narration_alignment: Any = None,
) -> list[Op]:
    from app.editing.presets import expand_preset_at_target

    if isinstance(operation, SetTextOp):
        return set_text_ops(content, operation)
    if isinstance(operation, SetNarrationOp):
        return set_narration_ops(content, operation)
    if isinstance(operation, ApplyPresetOp):
        _one_clip(content, operation.clip_id)
        return expand_preset_at_target(
            operation.preset_id, content, EditTarget(kind="clip", id=operation.clip_id)
        )
    if isinstance(operation, AddNarrationOp):
        return _add_narration(content, operation, facts.get(operation.source_id), narration_alignment)
    if isinstance(operation, AddAudioEffectOp):
        return _add_audio_effect(content, operation, facts.get(operation.source_id))
    _one_clip(content, operation.clip_id)
    if sum(len(track.clips) for track in content.timeline.tracks) == 1:
        raise RevisionInputError(
            "remove_clip cannot remove the version's only Clip",
            loc=["ops", "clip_id"],
            kind="unsupported_op",
        )
    return [RemoveClip(op="remove_clip", clip_id=operation.clip_id)]


__all__ = [
    "AddAudioEffectOp",
    "AddNarrationOp",
    "ApplyPresetOp",
    "RemoveClipOp",
    "RevisionOp",
    "RevisionInputError",
    "RevisionTargetAmbiguityError",
    "SetNarrationOp",
    "SetTextOp",
    "expand_revision_op",
    "set_narration_ops",
    "set_text_ops",
]
