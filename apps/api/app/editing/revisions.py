"""Direct revision Ops expanded into the ordinary editing algebra."""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.editing.animation import derive_text_parts
from app.editing.edits import (
    AddClip,
    AddTrack,
    BindSource,
    Op,
    RemoveClip,
    SetSettings,
    SetTrackOrder,
    SetTransition,
    UpdateClip,
    TextAnimationTargetLost,
    apply_ops,
    replace_text_ops,
)
from app.editing.schemas import (
    Animation,
    AudioObject,
    CaptionDerivation,
    Clip,
    CompositionContent,
    Easing,
    EditTarget,
    ImageObject,
    Keyframe,
    LayoutBox,
    MotionBlockObject,
    SourceCaptionDerivation,
    SpeechObject,
    TextObject,
    TextPartTarget,
    TextShadow,
    TextStroke,
    TextStyle,
    TimeRange,
    Track,
    VideoObject,
    speech_text_digest,
)
from app.editing.styles import (
    INHERITABLE_BLOCK_STYLE_KEYS,
    BackdropStyle,
    CompositionStyle,
    StylePresetId,
    contrast_ratio,
    resolve_style_tokens,
)
from app.editing.caption_timing import is_cjk_char
from app.editing.text_presets import (
    KARAOKE_ACTIVE_SCALE,
    KARAOKE_DEFAULT_HIGHLIGHT_COLOR,
    TEXT_STYLE_PRESETS,
    TextBackgroundMode,
    TextStylePresetId,
    default_caption_text_style,
    resolve_text_preset_token,
    text_style_from_token,
    text_style_updates_from_token,
)
from app.editing.timing import (
    frames_to_ticks,
    output_ticks_to_source_ticks,
    seconds_to_ticks,
    ticks_to_frames,
)


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
    alignment_id: UUID = Field(description="与该音频精确对应且状态为 ALIGNED 或 READY 的 NarrationAlignment。")
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


_MOTION_FLOAT_KEYS = frozenset({
    "cut_interval_s",
    "start_s",
    "end_s",
    "at_s",
    "reveal_at_s",
    "click_at_s",
    "highlight_at_s",
    "x",
    "y",
    "width",
    "height",
    "start_x",
    "start_y",
    "zoom_scale",
    "focus_x",
    "focus_y",
    "target_x",
    "target_y",
    "click_at_ratio",
    "entrance_duration_s",
    "exit_duration_s",
    "stagger_s",
    "scroll_from_y",
    "scroll_to_y",
})
_MOTION_INT_KEYS = frozenset({
    "active_step",
    "highlight_index",
    "highlight_line",
    "points",
    "resource_index",
    "columns",
    "rows",
})
_MOTION_STR_KEYS = frozenset({"step_label", "badge", "tag", "number"})


def _coerce_motion_value(block_id: str, key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _coerce_motion_value(block_id, k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [
            {k: _coerce_motion_value(block_id, k, v) for k, v in item.items()}
            if isinstance(item, dict)
            else item
            for item in value
        ]
    if key in _MOTION_FLOAT_KEYS and isinstance(value, str):
        try:
            num = float(value.strip())
            if num == num and abs(num) != float("inf"):
                return num
        except ValueError:
            pass
    if key == "value" and block_id == "data_chart" and isinstance(value, str):
        try:
            num = float(value.strip())
            if num == num and abs(num) != float("inf"):
                return num
        except ValueError:
            pass
    if key == "value" and block_id == "metric_grid" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if key in _MOTION_INT_KEYS and isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    if key in _MOTION_STR_KEYS and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if key in {"dim_left", "count_up", "show_backdrop"} and isinstance(value, str):
        low = value.strip().lower()
        if low == "true":
            return True
        if low == "false":
            return False
    return value


def coerce_motion_block_props(block_id: str, props: dict[str, Any]) -> dict[str, Any]:
    """Coerce benign LLM JSON-typing artifacts (e.g. '1.5' -> 1.5, step_label=1 -> '1') inside untyped props dicts."""
    if not isinstance(props, dict):
        return props
    return {k: _coerce_motion_value(block_id, k, v) for k, v in props.items()}


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

    props = coerce_motion_block_props(block_id, props)

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
        fit="cover" if block_id != "kinetic_title" else "contain",
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


def build_audio_gain_animation(
    *,
    object_id: str,
    clip_start_ticks: int,
    clip_end_ticks: int,
    timebase: int,
    fps_num: int,
    fps_den: int,
    fade_in_seconds: float | None = None,
    fade_out_seconds: float | None = None,
    duck_windows: list[dict[str, float]] | None = None,
) -> dict[str, Any] | None:
    """Build one frame-safe piecewise linear `audio.gain` Animation dict.

    Evaluates fade-in, fade-out, and optional timeline-second ducking windows
    at deduplicated integer-frame breakpoints so keyframes never collapse on
    quantization and always stay inside [0.0, 1.0].
    """
    from app.editing.timing import frames_to_ticks, ticks_to_frames

    dur_ticks = clip_end_ticks - clip_start_ticks
    if dur_ticks <= 0:
        return None
    fade_in_ticks = seconds_to_ticks(fade_in_seconds, timebase) if fade_in_seconds and fade_in_seconds > 0 else 0
    fade_out_ticks = seconds_to_ticks(fade_out_seconds, timebase) if fade_out_seconds and fade_out_seconds > 0 else 0
    fade_in_ticks = min(fade_in_ticks, dur_ticks)
    fade_out_ticks = min(fade_out_ticks, dur_ticks)

    ducks: list[tuple[int, int, int, float]] = []
    for win in duck_windows or []:
        s_abs = seconds_to_ticks(float(win["start_seconds"]), timebase)
        e_abs = seconds_to_ticks(float(win["end_seconds"]), timebase)
        s_loc = max(0, min(dur_ticks, s_abs - clip_start_ticks))
        e_loc = max(0, min(dur_ticks, e_abs - clip_start_ticks))
        if e_loc <= s_loc:
            continue
        ramp = max(1, seconds_to_ticks(float(win.get("ramp_seconds", 0.25)), timebase))
        mult = max(0.0, min(1.0, 10.0 ** (float(win.get("duck_db", -6.0)) / 20.0)))
        ducks.append((s_loc, e_loc, ramp, mult))

    if fade_in_ticks == 0 and fade_out_ticks == 0 and not ducks:
        return None

    raw_points: set[int] = {0, dur_ticks}
    if fade_in_ticks > 0:
        raw_points.add(fade_in_ticks)
    if fade_out_ticks > 0:
        raw_points.add(max(0, dur_ticks - fade_out_ticks))
    for s_loc, e_loc, ramp, _ in ducks:
        raw_points.update({
            max(0, s_loc - ramp),
            s_loc,
            e_loc,
            min(dur_ticks, e_loc + ramp),
        })

    def eval_envelope(t: int) -> float:
        g = 1.0
        if fade_in_ticks > 0 and t < fade_in_ticks:
            g *= max(0.0, min(1.0, t / fade_in_ticks))
        if fade_out_ticks > 0 and t > dur_ticks - fade_out_ticks:
            rem = dur_ticks - t
            g *= max(0.0, min(1.0, rem / fade_out_ticks))
        if ducks:
            duck_mult = 1.0
            for s_loc, e_loc, ramp, mult in ducks:
                if s_loc <= t <= e_loc:
                    local = mult
                elif s_loc - ramp < t < s_loc:
                    u = (t - (s_loc - ramp)) / ramp
                    local = 1.0 + (mult - 1.0) * u
                elif e_loc < t < e_loc + ramp:
                    u = (t - e_loc) / ramp
                    local = mult + (1.0 - mult) * u
                else:
                    local = 1.0
                if local < duck_mult:
                    duck_mult = local
            g *= duck_mult
        return round(max(0.0, min(1.0, g)), 4)

    # Snap breakpoints to unique quantized frames inside [0, dur_ticks]
    by_frame: dict[int, int] = {}
    max_frame = ticks_to_frames(dur_ticks, timebase, fps_num, fps_den)
    for t in sorted(raw_points):
        f = max(0, min(max_frame, ticks_to_frames(t, timebase, fps_num, fps_den)))
        tick = 0 if f == 0 else (dur_ticks if f == max_frame else min(dur_ticks, frames_to_ticks(f, timebase, fps_num, fps_den)))
        by_frame[f] = tick

    keyframes = [
        {
            "at": by_frame[f],
            "value": eval_envelope(by_frame[f]),
            "easing": {"kind": "linear", "params": None},
        }
        for f in sorted(by_frame)
    ]
    if len(keyframes) < 2:
        return None
    return {
        "animation_id": f"anim_gain_{object_id[:48]}",
        "target_object_id": object_id,
        "text_part": None,
        "property": "audio.gain",
        "keyframes": keyframes,
    }


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


def set_composition_style_ops(
    content: CompositionContent,
    *,
    preset_id: StylePresetId,
    accent_color: str | None = None,
    canvas_bg: str | None = None,
    backdrop_style: BackdropStyle | None = None,
    theme: Literal["dark", "light"] | None = None,
    override_block_styles: bool = True,
    update_captions: bool = True,
    update_transitions: bool = False,
) -> tuple[list[Op], dict[str, Any]]:
    """Build atomic edit ops to apply a first-class CompositionStyle.

    Guardrails:
    - Never touches any audio track (``track.kind == "audio"``).
    - Never mutates ``independent`` captions or non-caption TextObjects; only
      updates ``derived`` captions when ``update_captions=True``.
    - When ``override_block_styles=True``, strips inheritable style overrides on
      MotionBlockObjects so all acts inherit ``settings.style`` uniformly.
    """
    new_style = CompositionStyle(
        preset_id=preset_id,
        accent_color=accent_color,
        canvas_bg=canvas_bg,
        backdrop_style=backdrop_style,
        theme=theme,
    )
    tokens = resolve_style_tokens(new_style)
    ops: list[Op] = []

    new_settings = content.settings.model_copy(
        update={"style": new_style, "background": tokens["canvas_bg"]}
    )
    if new_settings != content.settings:
        ops.append(SetSettings(op="set_settings", settings=new_settings))

    blocks_updated = 0
    blocks_preserved = 0
    captions_updated = 0
    independent_captions_preserved = 0
    title_texts_contrast_adapted = 0
    transitions_updated = 0

    cap_token = tokens["caption_style"]
    cap_updates = text_style_updates_from_token(cap_token)

    for track in content.timeline.tracks:
        if track.kind != "visual":
            # Audio decoupling law: never touch dialogue, music, or effect audio tracks.
            continue
        for clip in track.clips:
            obj = clip.object
            if isinstance(obj, MotionBlockObject):
                strip_keys = INHERITABLE_BLOCK_STYLE_KEYS.get(obj.block_id, ())
                has_local = any(k in obj.props for k in strip_keys)
                if override_block_styles and has_local:
                    cleaned_props = {k: v for k, v in obj.props.items() if k not in strip_keys}
                    updated_obj = MotionBlockObject.model_validate(
                        {**obj.model_dump(mode="json"), "props": cleaned_props}
                    )
                    if updated_obj != obj:
                        ops.append(UpdateClip(op="update_clip", clip_id=clip.clip_id, object=updated_obj))
                        blocks_updated += 1
                elif not override_block_styles and has_local:
                    blocks_preserved += 1
            elif isinstance(obj, TextObject):
                if obj.caption is None:
                    # Preserve readable or surface-backed titles; adapt only unbacked low-contrast titles.
                    if (
                        obj.style.background is None
                        and contrast_ratio(obj.style.color, tokens["canvas_bg"]) < 3.0
                    ):
                        adapted_color = (
                            tokens["ink"]
                            if (obj.style.weight >= 700 or obj.style.font_size >= 48)
                            else tokens["secondary_ink"]
                        )
                        updated_text_style = obj.style.model_copy(update={"color": adapted_color})
                        if updated_text_style != obj.style:
                            updated_obj = obj.model_copy(update={"style": updated_text_style})
                            ops.append(UpdateClip(op="update_clip", clip_id=clip.clip_id, object=updated_obj))
                            title_texts_contrast_adapted += 1
                    continue
                if obj.caption.state == "independent":
                    independent_captions_preserved += 1
                    continue
                if update_captions and obj.caption.state == "derived":
                    updated_text_style = obj.style.model_copy(update=cap_updates)
                    if updated_text_style != obj.style:
                        updated_obj = obj.model_copy(update={"style": updated_text_style})
                        ops.append(UpdateClip(op="update_clip", clip_id=clip.clip_id, object=updated_obj))
                        captions_updated += 1

    if update_transitions:
        target_kind = tokens["default_transition"]
        for trn in content.timeline.transitions:
            if trn.kind != target_kind:
                ops.append(
                    SetTransition(
                        op="set_transition",
                        transition=trn.model_copy(update={"kind": target_kind}),
                    )
                )
                transitions_updated += 1

    summary: dict[str, Any] = {
        "style": new_style.model_dump(mode="json"),
        "preset_id": new_style.preset_id,
        "canvas_bg": tokens["canvas_bg"],
        "theme": tokens["theme"],
        "backdrop_style": tokens["backdrop_style"],
        "accent": tokens["accent"],
        "blocks_updated": blocks_updated,
        "blocks_preserved": blocks_preserved,
        "captions_updated": captions_updated,
        "independent_captions_preserved": independent_captions_preserved,
        "title_texts_contrast_adapted": title_texts_contrast_adapted,
        "transitions_updated": transitions_updated,
    }
    return ops, summary


def apply_composition_style(
    content: CompositionContent,
    *,
    preset_id: StylePresetId,
    accent_color: str | None = None,
    canvas_bg: str | None = None,
    backdrop_style: BackdropStyle | None = None,
    theme: Literal["dark", "light"] | None = None,
    override_block_styles: bool = True,
    update_captions: bool = True,
    update_transitions: bool = False,
) -> tuple[CompositionContent, dict[str, Any]]:
    """Pure deterministic composition style transformation returning (new_content, summary)."""
    ops, summary = set_composition_style_ops(
        content,
        preset_id=preset_id,
        accent_color=accent_color,
        canvas_bg=canvas_bg,
        backdrop_style=backdrop_style,
        theme=theme,
        override_block_styles=override_block_styles,
        update_captions=update_captions,
        update_transitions=update_transitions,
    )
    updated = apply_ops(content, ops, {}) if ops else content.model_copy(deep=True)
    return updated, summary


TextPosition = Literal[
    "bottom",
    "top",
    "center",
    "bottom_left",
    "top_left",
    "bottom_right",
    "top_right",
]


def text_safe_layout(
    width: int,
    height: int,
    position: TextPosition,
    *,
    role: Literal["title", "caption"] = "title",
) -> LayoutBox:
    """Compute a broadcast-safe LayoutBox for a native text or caption clip."""
    mx = float(round(width * 0.08))
    mb = float(round(height * 0.055))
    mt = float(round(height * 0.065))

    if position in ("bottom", "top", "center"):
        box_w = float(max(120, width - 2 * int(mx)))
        box_h = float(max(130, round(height * (0.16 if role == "caption" else 0.18))))
        if position == "bottom":
            y = float(max(0.0, height - mb - box_h))
        elif position == "top":
            y = mt
        else:
            y = float(max(0.0, (height - box_h) / 2.0))
        return LayoutBox(x=mx, y=y, width=box_w, height=box_h)

    corner_w = float(max(160, round(width * 0.44)))
    corner_h = float(max(110, round(height * 0.12)))
    x = mx if position.endswith("left") else float(max(0.0, width - mx - corner_w))
    y = mt if position.startswith("top") else float(max(0.0, height - mb - corner_h))
    return LayoutBox(x=x, y=y, width=corner_w, height=corner_h)


def _default_position(
    role: Literal["title", "caption"], preset_id: TextStylePresetId | None
) -> TextPosition:
    if preset_id == "lower_third_tag":
        return "bottom_left"
    if role == "caption":
        return "bottom"
    return "center"


def _default_align_for_position(position: TextPosition) -> Literal["left", "center", "right"]:
    if position.endswith("left"):
        return "left"
    if position.endswith("right"):
        return "right"
    return "center"


def _default_font_size(
    width: int, role: Literal["title", "caption"], preset_id: TextStylePresetId | None
) -> int:
    if preset_id == "lower_third_tag":
        return max(24, round(width * 32 / 1920))
    if preset_id == "editorial_callout":
        return max(26, round(width * 36 / 1920))
    if role == "caption":
        return max(28, round(width * 40 / 1920))
    return max(36, round(width * 56 / 1920))


def _pick_or_create_text_track(
    content: CompositionContent,
    *,
    role: Literal["title", "caption"],
    ranges: list[TimeRange],
    preferred_prefix: str | None = None,
) -> tuple[str, list[Op]]:
    """Find a non-overlapping visual track for ``role``, or create one preserving main < title < caption."""
    visual_tracks = [t for t in content.timeline.tracks if t.kind == "visual"]

    def overlaps_any(track: Track) -> bool:
        return any(
            c.range.start < r.end and r.start < c.range.end
            for c in track.clips
            for r in ranges
        )

    candidates = sorted(
        (t for t in visual_tracks if t.role == role),
        key=lambda t: t.order,
    )
    reusable = next((t for t in candidates if not overlaps_any(t)), None)
    if reusable is not None:
        return reusable.track_id, []

    prefix = preferred_prefix or (f"trk_{role}")
    existing_ids = {t.track_id for t in content.timeline.tracks}
    track_id = prefix
    suffix = 2
    while track_id in existing_ids:
        track_id = f"{prefix}_{suffix}"
        suffix += 1

    ops: list[Op] = []
    if role == "caption":
        desired_order = max((t.order for t in visual_tracks), default=-1) + 1
    else:
        above_roles = {"caption"}
        below = [t for t in visual_tracks if t.role not in above_roles]
        above = sorted((t for t in visual_tracks if t.role in above_roles), key=lambda t: t.order)
        desired_order = max((t.order for t in below), default=-1) + 1
        to_bump = sorted(
            (t for t in visual_tracks if t.order >= desired_order),
            key=lambda t: t.order,
            reverse=True,
        )
        if any(t.role not in above_roles for t in to_bump):
            if above:
                min_above = min(t.order for t in above)
                non_above_below_min = [
                    t for t in visual_tracks if t.role not in above_roles and t.order < min_above
                ]
                desired_order = max((t.order for t in non_above_below_min), default=-1) + 1
                to_bump = sorted(
                    (t for t in visual_tracks if t.order >= desired_order),
                    key=lambda t: t.order,
                    reverse=True,
                )
            else:
                desired_order = max((t.order for t in visual_tracks), default=-1) + 1
                to_bump = []
        for track in to_bump:
            ops.append(SetTrackOrder(op="set_track_order", track_id=track.track_id, order=track.order + 1))

    ops.append(
        AddTrack(
            op="add_track",
            track=Track(track_id=track_id, kind="visual", role=role, order=desired_order, clips=[]),
        )
    )
    return track_id, ops


def _resolve_text_style_for_insert(
    content: CompositionContent,
    *,
    role: Literal["title", "caption"],
    position: TextPosition,
    preset_id: TextStylePresetId | None = None,
    font_size: int | None = None,
    color: str | None = None,
    background: str | None = None,
    background_mode: TextBackgroundMode | None = None,
    background_opacity: float | None = None,
    align: Literal["left", "center", "right"] | None = None,
    secondary_line_scale: float | None = None,
) -> TextStyle:
    eff_size = font_size if font_size is not None else _default_font_size(
        content.settings.width, role, preset_id
    )
    eff_align = align if align is not None else _default_align_for_position(position)
    style_tokens = (
        resolve_style_tokens(content.settings.style)
        if content.settings.style is not None
        else None
    )

    if preset_id is not None:
        token = resolve_text_preset_token(preset_id, style_tokens)
        style = text_style_from_token(
            token, font_size=eff_size, align=eff_align, line_height=1.3
        )
    elif role == "caption":
        style = default_caption_text_style(
            content.settings, font_size=eff_size, align=eff_align, line_height=1.3
        )
    else:
        fallback_id: TextStylePresetId = (
            "minimal_light"
            if style_tokens is not None and style_tokens["theme"] == "light"
            else "clean_broadcast"
        )
        style = text_style_from_token(
            TEXT_STYLE_PRESETS[fallback_id],
            font_size=eff_size,
            align=eff_align,
            line_height=1.25,
        )

    updates: dict[str, Any] = {}
    if color is not None:
        updates["color"] = color.upper()
    if background is not None:
        updates["background"] = background.upper()
    if background_mode is not None:
        updates["background_mode"] = background_mode
    if background_opacity is not None:
        updates["background_opacity"] = background_opacity
    if secondary_line_scale is not None:
        updates["secondary_line_scale"] = secondary_line_scale
    if updates:
        style = style.model_copy(update=updates)
    if (
        background is not None
        and background_mode is None
        and style.background_mode == "box"
    ):
        pill_updates: dict[str, Any] = {"background_mode": "pill"}
        if style.background_padding == (0.0, 0.0):
            pill_updates["background_padding"] = (20.0, 10.0)
        if style.background_radius == 0.0:
            pill_updates["background_radius"] = 10.0
        if background_opacity is None and style.background_opacity == 1.0:
            pill_updates["background_opacity"] = 0.78
        style = style.model_copy(update=pill_updates)
    if background_mode in ("pill", "line") and style.background_padding == (0.0, 0.0):
        default_pad = (20.0, 10.0) if background_mode == "pill" else (20.0, 8.0)
        default_rad = 10.0 if background_mode == "pill" else 4.0
        style = style.model_copy(
            update={
                "background_padding": default_pad,
                "background_radius": style.background_radius or default_rad,
            }
        )
    return style


def _has_cjk(text: str) -> bool:
    return any(is_cjk_char(ch) for ch in text)


def _is_punct_or_space(text: str) -> bool:
    return bool(text) and all(unicodedata.category(ch)[0] in {"P", "S", "Z"} for ch in text)


def _karaoke_tokens(
    text: str,
    *,
    force_words: bool = False,
) -> tuple[Literal["word", "grapheme"], list[tuple[list[str], int]]]:
    """Segment text into deterministic (part_ids, char_weight) karaoke groups."""
    word_parts = derive_text_parts(text, "word")
    lexical_words = [part for part in word_parts if not _is_punct_or_space(part.text)]
    use_cjk_chunks = (
        not force_words
        and (
            (len(lexical_words) == 1 and len(lexical_words[0].text) > 2 and _has_cjk(lexical_words[0].text))
            or (
                bool(lexical_words)
                and any(len(part.text) >= 5 and _has_cjk(part.text) for part in lexical_words)
            )
        )
    )
    if use_cjk_chunks:
        graphemes = [
            part
            for part in derive_text_parts(text, "grapheme")
            if part.text.strip() and not _is_punct_or_space(part.text)
        ]
        chunks: list[tuple[list[str], int]] = []
        idx = 0
        while idx < len(graphemes):
            first = graphemes[idx]
            if (
                idx + 1 < len(graphemes)
                and graphemes[idx + 1].layout_range == first.layout_range
                and _has_cjk(first.text)
                and _has_cjk(graphemes[idx + 1].text)
            ):
                pair = [first, graphemes[idx + 1]]
                chunks.append(([p.part_id for p in pair], 2))
                idx += 2
            else:
                chunks.append(([first.part_id], 1))
                idx += 1
        if chunks:
            return "grapheme", chunks

    chosen = lexical_words or word_parts
    return "word", [([part.part_id], max(1, len(part.text))) for part in chosen]


def _build_karaoke_animations(
    content: CompositionContent,
    clip: Clip,
    *,
    base_color: str,
    highlight_color: str,
    word_timings: list[tuple[float, float]] | list[dict[str, Any]] | None = None,
) -> list[Animation]:
    """Generate deterministic word/grapheme TextPart karaoke highlight & pop animations."""
    obj = clip.object
    if not isinstance(obj, TextObject):
        return []
    settings = content.settings
    clip_ticks = clip.range.duration
    timebase = settings.timebase
    fps_num, fps_den = settings.fps.num, settings.fps.den
    total_frames = ticks_to_frames(clip_ticks, timebase, fps_num, fps_den)
    if total_frames < 2:
        return []

    part_kind: Literal["word", "grapheme"]
    tokens: list[tuple[list[str], int]]
    frame_ranges: list[tuple[int, int]] = []

    # When measured word timings include character spans (e.g. from NarrationAlignment),
    # align directly to exact word or grapheme TextParts even for unspaced CJK text.
    span_matched = False
    if word_timings and all(
        isinstance(item, dict) and "text_start" in item and "text_end" in item
        for item in word_timings
    ):
        word_parts = [p for p in derive_text_parts(obj.text, "word") if not _is_punct_or_space(p.text)]
        if len(word_parts) == len(word_timings):
            part_kind = "word"
            tokens = [([p.part_id], max(1, len(p.text))) for p in word_parts]
            for item in word_timings:
                sf = max(0, min(total_frames - 1, round(float(item["start_s"]) * fps_num / fps_den)))
                ef = max(sf + 1, min(total_frames, round(float(item["end_s"]) * fps_num / fps_den)))
                frame_ranges.append((sf, ef))
            span_matched = True
        else:
            graphemes = [
                p for p in derive_text_parts(obj.text, "grapheme")
                if p.text.strip() and not _is_punct_or_space(p.text)
            ]
            matched_tokens: list[tuple[list[str], int]] = []
            matched_ranges: list[tuple[int, int]] = []
            used_ids: set[str] = set()
            for item in word_timings:
                ts, te = int(item["text_start"]), int(item["text_end"])
                ids = [
                    g.part_id for g in graphemes
                    if g.text_range.start >= ts and g.text_range.end <= te and g.part_id not in used_ids
                ]
                if not ids:
                    continue
                used_ids.update(ids)
                sf = max(0, min(total_frames - 1, round(float(item["start_s"]) * fps_num / fps_den)))
                ef = max(sf + 1, min(total_frames, round(float(item["end_s"]) * fps_num / fps_den)))
                matched_tokens.append((ids, len(ids)))
                matched_ranges.append((sf, ef))
            if matched_tokens:
                part_kind = "grapheme"
                tokens = matched_tokens
                frame_ranges = matched_ranges
                span_matched = True

    if not span_matched:
        part_kind, tokens = _karaoke_tokens(obj.text, force_words=False)
        if not tokens:
            return []
        if word_timings is not None and len(word_timings) == len(tokens):
            for item in word_timings:
                if isinstance(item, dict):
                    s_sec, e_sec = float(item["start_s"]), float(item["end_s"])
                else:
                    s_sec, e_sec = float(item[0]), float(item[1])
                sf = max(0, min(total_frames - 1, round(s_sec * fps_num / fps_den)))
                ef = max(sf + 1, min(total_frames, round(e_sec * fps_num / fps_den)))
                frame_ranges.append((sf, ef))
        else:
            # Also try exact lexical word match if word_timings matches lexical words directly
            word_kind, word_tokens = _karaoke_tokens(obj.text, force_words=True)
            if word_timings is not None and len(word_timings) == len(word_tokens):
                part_kind, tokens = word_kind, word_tokens
                for item in word_timings:
                    if isinstance(item, dict):
                        s_sec, e_sec = float(item["start_s"]), float(item["end_s"])
                    else:
                        s_sec, e_sec = float(item[0]), float(item[1])
                    sf = max(0, min(total_frames - 1, round(s_sec * fps_num / fps_den)))
                    ef = max(sf + 1, min(total_frames, round(e_sec * fps_num / fps_den)))
                    frame_ranges.append((sf, ef))
            else:
                total_weight = sum(weight for _, weight in tokens)
                acc_weight = 0
                prev_end = 0
                n_tokens = len(tokens)
                for idx, (_, weight) in enumerate(tokens):
                    if prev_end >= total_frames:
                        break
                    sf = prev_end
                    if idx == n_tokens - 1:
                        ef = total_frames
                    else:
                        acc_weight += weight
                        remaining = n_tokens - 1 - idx
                        target = round(total_frames * acc_weight / total_weight)
                        max_end = max(sf + 1, total_frames - remaining)
                        ef = min(total_frames, max(sf + 1, min(max_end, target)))
                    if sf < ef <= total_frames:
                        frame_ranges.append((sf, ef))
                        prev_end = ef

    if not tokens or not frame_ranges:
        return []

    def frame_to_tick(frame_idx: int) -> int:
        return min(clip_ticks, max(0, frames_to_ticks(frame_idx, timebase, fps_num, fps_den)))

    clip_hash = hashlib.sha256(clip.clip_id.encode("utf-8")).hexdigest()[:8]
    animations: list[Animation] = []
    pop_in = Easing(kind="cubic_bezier", params=(0.16, 1.0, 0.3, 1.0))
    pop_out = Easing(kind="cubic_bezier", params=(0.4, 0.0, 0.2, 1.0))
    hold = Easing(kind="hold")
    linear = Easing(kind="linear")

    def dedup_keyframes(raw: list[tuple[int, Any, Easing]]) -> list[Keyframe]:
        out: list[Keyframe] = []
        seen_ticks: set[int] = set()
        seen_frames: set[int] = set()
        for f_idx, val, easing in raw:
            tick = frame_to_tick(f_idx)
            q_frame = ticks_to_frames(tick, timebase, fps_num, fps_den)
            if tick in seen_ticks or q_frame in seen_frames:
                continue
            seen_ticks.add(tick)
            seen_frames.add(q_frame)
            out.append(Keyframe(at=tick, value=val, easing=easing))
        return out

    for idx, ((part_ids, _), (sf, ef)) in enumerate(zip(tokens, frame_ranges)):
        target = TextPartTarget(kind=part_kind, part_ids=part_ids, stagger=0)

        color_raw: list[tuple[int, Any, Easing]] = []
        if sf == 0:
            color_raw.append((0, highlight_color, hold))
            if ef < total_frames:
                color_raw.append((ef, base_color, hold))
        else:
            color_raw.append((0, base_color, hold))
            color_raw.append((sf, highlight_color, hold))
            if ef < total_frames:
                color_raw.append((ef, base_color, hold))
        color_kfs = dedup_keyframes(color_raw)
        if color_kfs:
            animations.append(
                Animation(
                    animation_id=f"karaoke_color_{clip_hash}_{idx}",
                    target_object_id=obj.object_id,
                    text_part=target,
                    property="text.color",
                    keyframes=color_kfs,
                )
            )

        span = ef - sf
        if span >= 2:
            peak = sf + (2 if span >= 5 else 1)
            release = ef - 1 if ef - 1 > peak else peak
            scale_raw: list[tuple[int, Any, Easing]] = []
            if sf > 0:
                scale_raw.append((0, 1.0, hold))
            scale_raw.append((sf, 1.0, pop_in))
            if release > peak:
                scale_raw.append((peak, KARAOKE_ACTIVE_SCALE, hold))
                scale_raw.append((release, KARAOKE_ACTIVE_SCALE, pop_out))
            else:
                scale_raw.append((peak, KARAOKE_ACTIVE_SCALE, pop_out))
            scale_raw.append((ef, 1.0, linear))
            scale_kfs = dedup_keyframes(scale_raw)
            if len(scale_kfs) >= 2:
                animations.append(
                    Animation(
                        animation_id=f"karaoke_scale_{clip_hash}_{idx}",
                        target_object_id=obj.object_id,
                        text_part=target,
                        property="transform.scale",
                        keyframes=scale_kfs,
                    )
                )

    return animations


def _extract_karaoke_highlight_color(clip: Clip, base_color: str) -> str | None:
    for anim in clip.animations:
        if anim.animation_id.startswith("karaoke_color_") and anim.property == "text.color":
            for kf in anim.keyframes:
                if isinstance(kf.value, str) and kf.value.upper() != base_color.upper():
                    return kf.value.upper()
    return None


def insert_text_ops(
    content: CompositionContent,
    *,
    text: str,
    start: int,
    end: int,
    clip_id: str,
    object_id: str,
    scene_id: str | None = None,
    role: Literal["title", "caption"] = "title",
    position: TextPosition | None = None,
    preset_id: TextStylePresetId | None = None,
    font_size: int | None = None,
    color: str | None = None,
    highlight_color: str | None = None,
    background: str | None = None,
    background_mode: TextBackgroundMode | None = None,
    background_opacity: float | None = None,
    align: Literal["left", "center", "right"] | None = None,
    secondary_line_scale: float | None = None,
    word_timings: list[tuple[float, float]] | list[dict[str, Any]] | None = None,
) -> tuple[list[Op], dict[str, Any]]:
    """Build atomic edit ops to insert a direct native TextObject clip."""
    eff_position = position if position is not None else _default_position(role, preset_id)
    layout = text_safe_layout(
        content.settings.width, content.settings.height, eff_position, role=role
    )
    style = _resolve_text_style_for_insert(
        content,
        role=role,
        position=eff_position,
        preset_id=preset_id,
        font_size=font_size,
        color=color,
        background=background,
        background_mode=background_mode,
        background_opacity=background_opacity,
        align=align,
        secondary_line_scale=secondary_line_scale,
    )
    clip = Clip(
        clip_id=clip_id,
        range=TimeRange(start=start, end=end),
        scene_id=scene_id,
        source=None,
        object=TextObject(
            kind="text",
            object_id=object_id,
            text=text,
            layout=layout,
            style=style,
        ),
        animations=[],
    )
    karaoke_active = False
    if preset_id == "karaoke_focus":
        style_tokens = (
            resolve_style_tokens(content.settings.style)
            if content.settings.style is not None
            else None
        )
        eff_highlight = (
            highlight_color.upper()
            if highlight_color is not None
            else (style_tokens["accent"] if style_tokens is not None else KARAOKE_DEFAULT_HIGHLIGHT_COLOR)
        )
        karaoke_anims = _build_karaoke_animations(
            content,
            clip,
            base_color=style.color,
            highlight_color=eff_highlight,
            word_timings=word_timings,
        )
        clip = clip.model_copy(update={"animations": karaoke_anims})
        karaoke_active = bool(karaoke_anims)

    track_id, ops = _pick_or_create_text_track(
        content, role=role, ranges=[clip.range], preferred_prefix=f"trk_{role}"
    )
    ops.append(AddClip(op="add_clip", track_id=track_id, clip=clip))
    summary: dict[str, Any] = {
        "mode": "direct",
        "role": role,
        "track_id": track_id,
        "clip_ids": [clip.clip_id],
        "clips_inserted": 1,
        "position": eff_position,
        "preset_id": preset_id,
        "karaoke_active": karaoke_active,
    }
    return ops, summary


def insert_aligned_captions_ops(
    content: CompositionContent,
    *,
    audio_clip: Clip,
    cues: list[dict[str, Any]],
    id_prefix: str,
    position: TextPosition | None = None,
    preset_id: TextStylePresetId | None = None,
    font_size: int | None = None,
    color: str | None = None,
    highlight_color: str | None = None,
    background: str | None = None,
    background_mode: TextBackgroundMode | None = None,
    background_opacity: float | None = None,
    align: Literal["left", "center", "right"] | None = None,
    secondary_line_scale: float | None = None,
) -> tuple[list[Op], dict[str, Any]]:
    """Build atomic edit ops to insert a full derived caption track from aligned audio/speech cues."""
    if not cues:
        raise RevisionInputError(
            f"Audio clip {audio_clip.clip_id!r} has no caption cues within its timeline window.",
            loc=["from_audio_clip_id"],
            kind="target_not_found",
        )
    eff_position = position if position is not None else _default_position("caption", preset_id)
    layout = text_safe_layout(
        content.settings.width, content.settings.height, eff_position, role="caption"
    )
    style = _resolve_text_style_for_insert(
        content,
        role="caption",
        position=eff_position,
        preset_id=preset_id,
        font_size=font_size,
        color=color,
        background=background,
        background_mode=background_mode,
        background_opacity=background_opacity,
        align=align,
        secondary_line_scale=secondary_line_scale,
    )
    style_tokens = (
        resolve_style_tokens(content.settings.style)
        if content.settings.style is not None
        else None
    )
    eff_highlight = (
        highlight_color.upper()
        if highlight_color is not None
        else (style_tokens["accent"] if style_tokens is not None else KARAOKE_DEFAULT_HIGHLIGHT_COLOR)
    )

    clips: list[Clip] = []
    karaoke_count = 0
    for idx, cue in enumerate(cues, start=1):
        clip_id = f"clp_cap_{id_prefix}_{idx}"
        object_id = f"obj_cap_{id_prefix}_{idx}"
        clip_range = TimeRange(start=int(cue["output_start"]), end=int(cue["output_end"]))
        caption_obj = cue["caption"]
        clip = Clip(
            clip_id=clip_id,
            range=clip_range,
            scene_id=audio_clip.scene_id,
            source=None,
            object=TextObject(
                kind="text",
                object_id=object_id,
                text=str(cue["text"]),
                layout=layout.model_copy(deep=True),
                style=style.model_copy(deep=True),
                caption=caption_obj,
            ),
            animations=[],
        )
        if preset_id == "karaoke_focus":
            anims = _build_karaoke_animations(
                content,
                clip,
                base_color=style.color,
                highlight_color=eff_highlight,
                word_timings=cue.get("word_timings"),
            )
            clip = clip.model_copy(update={"animations": anims})
            if anims:
                karaoke_count += 1
        clips.append(clip)

    track_id, ops = _pick_or_create_text_track(
        content,
        role="caption",
        ranges=[c.range for c in clips],
        preferred_prefix=f"trk_caption_{id_prefix}",
    )
    ops.extend(AddClip(op="add_clip", track_id=track_id, clip=clip) for clip in clips)
    summary: dict[str, Any] = {
        "mode": "from_audio_clip",
        "from_audio_clip_id": audio_clip.clip_id,
        "role": "caption",
        "track_id": track_id,
        "clip_ids": [c.clip_id for c in clips],
        "clips_inserted": len(clips),
        "position": eff_position,
        "preset_id": preset_id,
        "karaoke_clips": karaoke_count,
    }
    return ops, summary


def edit_text_ops(
    content: CompositionContent,
    *,
    scope: Literal["clip", "track", "all_derived_captions"],
    clip_id: str | None = None,
    track_id: str | None = None,
    text: str | None = None,
    keep_derived: bool = False,
    preset_id: TextStylePresetId | None = None,
    color: str | None = None,
    highlight_color: str | None = None,
    font_size: int | None = None,
    background: str | None = None,
    clear_background: bool = False,
    background_mode: TextBackgroundMode | None = None,
    background_opacity: float | None = None,
    align: Literal["left", "center", "right"] | None = None,
    secondary_line_scale: float | None = None,
    position: TextPosition | None = None,
    word_timings: list[tuple[float, float]] | list[dict[str, Any]] | None = None,
) -> tuple[list[Op], dict[str, Any]]:
    """Build atomic edit ops to update text content, style, preset, or position.

    Guardrails:
    - Never touches any audio track (``track.kind == "audio"``).
    - With ``scope="all_derived_captions"``, strictly skips ``independent``
      captions and non-caption text clips.
    - ``text`` edits are restricted to ``scope="clip"``; editing text on a
      ``derived`` caption promotes it to ``independent`` unless ``keep_derived=True``.
    - Applying ``karaoke_focus`` replaces any prior ``karaoke_*`` TextPart
      animations with fresh deterministic keyframes; switching to any other
      preset strips prior ``karaoke_*`` animations; editing ``text`` on an
      active karaoke clip rebuilds its ``karaoke_*`` animations cleanly.
    """
    if text is not None and scope != "clip":
        raise RevisionInputError(
            "Editing text content requires scope='clip'.",
            loc=["text"],
            kind="revision_input",
        )
    if clear_background and background is not None:
        raise RevisionInputError(
            "Provide either background or clear_background=True, not both.",
            loc=["clear_background"],
            kind="revision_input",
        )
    has_change = any(
        v is not None
        for v in (
            text,
            preset_id,
            color,
            highlight_color,
            font_size,
            background,
            background_mode,
            background_opacity,
            align,
            secondary_line_scale,
            position,
        )
    ) or clear_background
    if not has_change:
        raise RevisionInputError(
            "Provide text, preset_id, position, clear_background, or at least one style override.",
            kind="revision_input",
        )

    targets: list[tuple[Track, Clip]] = []
    independent_captions_preserved = 0
    non_caption_text_preserved = 0

    if scope == "clip":
        if not clip_id:
            raise RevisionInputError("scope='clip' requires clip_id.", loc=["clip_id"])
        matches = _clip_locations(content, clip_id)
        if not matches:
            raise RevisionInputError(
                f"clip {clip_id!r} does not exist in the base version",
                loc=["clip_id"],
                kind="target_not_found",
            )
        track, clip = matches[0]
        if track.kind != "visual" or not isinstance(clip.object, TextObject):
            raise RevisionInputError(
                "edit_text targets visual TextObject clips only.",
                loc=["clip_id"],
                kind="unsupported_target",
            )
        targets.append((track, clip))
    elif scope == "track":
        if not track_id:
            raise RevisionInputError("scope='track' requires track_id.", loc=["track_id"])
        track = next((t for t in content.timeline.tracks if t.track_id == track_id), None)
        if track is None:
            raise RevisionInputError(
                f"track {track_id!r} does not exist in the base version",
                loc=["track_id"],
                kind="target_not_found",
            )
        if track.kind != "visual":
            raise RevisionInputError(
                "edit_text never operates on audio tracks.",
                loc=["track_id"],
                kind="unsupported_target",
            )
        targets.extend((track, c) for c in track.clips if isinstance(c.object, TextObject))
        if not targets:
            raise RevisionInputError(
                f"track {track_id!r} has no TextObject clips to edit.",
                loc=["track_id"],
                kind="target_not_found",
            )
    elif scope == "all_derived_captions":
        for track in content.timeline.tracks:
            if track.kind != "visual":
                continue
            for clip in track.clips:
                obj = clip.object
                if not isinstance(obj, TextObject):
                    continue
                if obj.caption is None:
                    non_caption_text_preserved += 1
                    continue
                if obj.caption.state == "independent":
                    independent_captions_preserved += 1
                    continue
                if obj.caption.state == "derived":
                    targets.append((track, clip))
        if not targets:
            raise RevisionInputError(
                "No derived caption clips found to edit.",
                loc=["scope"],
                kind="target_not_found",
            )
    else:
        raise RevisionInputError(f"Unsupported scope {scope!r}.", loc=["scope"])

    style_tokens = (
        resolve_style_tokens(content.settings.style)
        if content.settings.style is not None
        else None
    )

    ops: list[Op] = []
    updated_clip_ids: list[str] = []
    karaoke_clips_updated = 0
    karaoke_clips_cleared = 0
    text_updated = False
    promoted_independent = 0

    for track, clip in targets:
        obj = clip.object
        assert isinstance(obj, TextObject)
        obj_updates: dict[str, Any] = {}
        new_text = obj.text
        text_changed = False

        if text is not None and text != obj.text:
            new_text = text
            text_changed = True
            obj_updates["text"] = new_text
            if obj.caption is not None:
                if keep_derived and obj.caption.state == "derived":
                    if isinstance(obj.caption, SourceCaptionDerivation):
                        obj_updates["caption"] = obj.caption.model_copy(
                            update={"source_text_digest": speech_text_digest(new_text)}
                        )
                    # CaptionDerivation keeps state="derived" (validated against primary line).
                elif not keep_derived and obj.caption.state == "derived":
                    obj_updates["caption"] = obj.caption.model_copy(update={"state": "independent"})
                    promoted_independent += 1

        if position is not None:
            role_for_layout: Literal["title", "caption"] = (
                "caption" if track.role == "caption" or obj.caption is not None else "title"
            )
            new_layout = text_safe_layout(
                content.settings.width, content.settings.height, position, role=role_for_layout
            )
            obj_updates["layout"] = new_layout
            if obj.transform.x != 0.0 or obj.transform.y != 0.0:
                obj_updates["transform"] = obj.transform.model_copy(update={"x": 0.0, "y": 0.0})

        style_updates: dict[str, Any] = {}
        if preset_id is not None:
            token = resolve_text_preset_token(preset_id, style_tokens)
            style_updates.update(text_style_updates_from_token(token))

        if clear_background:
            style_updates.update(
                {
                    "background": None,
                    "background_mode": "box",
                    "background_opacity": 1.0,
                    "background_padding": (0.0, 0.0),
                    "background_radius": 0.0,
                    "border": None,
                }
            )
        if color is not None:
            style_updates["color"] = color.upper()
        if font_size is not None:
            style_updates["font_size"] = font_size
        if background is not None:
            style_updates["background"] = background.upper()
        if background_mode is not None:
            style_updates["background_mode"] = background_mode
        if background_opacity is not None:
            style_updates["background_opacity"] = background_opacity
        if align is not None:
            style_updates["align"] = align
        if secondary_line_scale is not None:
            style_updates["secondary_line_scale"] = secondary_line_scale

        new_style = obj.style.model_copy(update=style_updates) if style_updates else obj.style
        if (
            not clear_background
            and background is not None
            and (background_mode is None or (scope == "all_derived_captions" and background_mode == "box"))
            and new_style.background_mode == "box"
            and (track.role == "caption" or obj.caption is not None or obj.style.background_mode == "box")
        ):
            pill_updates: dict[str, Any] = {"background_mode": "pill"}
            if new_style.background_padding == (0.0, 0.0):
                pill_updates["background_padding"] = (20.0, 10.0)
            if new_style.background_radius == 0.0:
                pill_updates["background_radius"] = 10.0
            if background_opacity is None and new_style.background_opacity == 1.0:
                pill_updates["background_opacity"] = 0.78
            new_style = new_style.model_copy(update=pill_updates)
        if (
            not clear_background
            and background_mode in ("pill", "line")
            and new_style.background_padding == (0.0, 0.0)
        ):
            default_pad = (20.0, 10.0) if background_mode == "pill" else (20.0, 8.0)
            default_rad = 10.0 if background_mode == "pill" else 4.0
            new_style = new_style.model_copy(
                update={
                    "background_padding": default_pad,
                    "background_radius": new_style.background_radius or default_rad,
                }
            )
        if new_style != obj.style:
            obj_updates["style"] = new_style

        updated_obj = obj.model_copy(update=obj_updates) if obj_updates else obj
        working_clip = clip.model_copy(update={"object": updated_obj})

        had_karaoke = any(a.animation_id.startswith("karaoke_") for a in clip.animations)
        kept_anims = [a for a in clip.animations if not a.animation_id.startswith("karaoke_")]
        new_animations = list(clip.animations)

        if text_changed and any(a.text_part is not None for a in kept_anims):
            # Remap any non-karaoke TextPart animations safely via replace_text_ops.
            try:
                remapped = replace_text_ops(
                    clip.model_copy(update={"animations": kept_anims}), new_text
                )
                if remapped and isinstance(remapped[0], UpdateClip) and remapped[0].animations is not None:
                    kept_anims = list(remapped[0].animations)
            except TextAnimationTargetLost as exc:
                raise RevisionInputError(
                    str(exc), loc=["text"], kind="animation_target_lost"
                ) from exc
            new_animations = list(kept_anims)

        if preset_id == "karaoke_focus":
            eff_highlight = (
                highlight_color.upper()
                if highlight_color is not None
                else (style_tokens["accent"] if style_tokens is not None else KARAOKE_DEFAULT_HIGHLIGHT_COLOR)
            )
            karaoke_anims = _build_karaoke_animations(
                content,
                working_clip,
                base_color=new_style.color,
                highlight_color=eff_highlight,
                word_timings=word_timings,
            )
            new_animations = kept_anims + karaoke_anims
            karaoke_clips_updated += 1
        elif preset_id is not None and had_karaoke:
            new_animations = kept_anims
            karaoke_clips_cleared += 1
        elif preset_id is None and had_karaoke and (highlight_color is not None or text_changed or color is not None):
            prev_hl = _extract_karaoke_highlight_color(clip, obj.style.color)
            eff_highlight = (
                highlight_color.upper()
                if highlight_color is not None
                else (
                    prev_hl
                    or (style_tokens["accent"] if style_tokens is not None else KARAOKE_DEFAULT_HIGHLIGHT_COLOR)
                )
            )
            karaoke_anims = _build_karaoke_animations(
                content,
                working_clip,
                base_color=new_style.color,
                highlight_color=eff_highlight,
                word_timings=word_timings,
            )
            new_animations = kept_anims + karaoke_anims
            karaoke_clips_updated += 1

        if updated_obj != obj or new_animations != clip.animations:
            ops.append(
                UpdateClip(
                    op="update_clip",
                    clip_id=clip.clip_id,
                    object=updated_obj,
                    animations=new_animations,
                )
            )
            updated_clip_ids.append(clip.clip_id)
            if text_changed:
                text_updated = True

    summary: dict[str, Any] = {
        "scope": scope,
        "preset_id": preset_id,
        "position": position,
        "text_updated": text_updated,
        "clips_updated": len(updated_clip_ids),
        "updated_clip_ids": updated_clip_ids,
        "independent_captions_preserved": independent_captions_preserved,
        "non_caption_text_preserved": non_caption_text_preserved,
        "promoted_independent": promoted_independent,
        "karaoke_clips_updated": karaoke_clips_updated,
        "karaoke_clips_cleared": karaoke_clips_cleared,
    }
    return ops, summary


def edit_text(
    content: CompositionContent,
    **kwargs: Any,
) -> tuple[CompositionContent, dict[str, Any]]:
    """Pure deterministic text/caption edit transformation returning (new_content, summary)."""
    ops, summary = edit_text_ops(content, **kwargs)
    updated = apply_ops(content, ops, {}) if ops else content.model_copy(deep=True)
    return updated, summary


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
    "TextPosition",
    "apply_composition_style",
    "edit_text",
    "edit_text_ops",
    "expand_revision_op",
    "insert_aligned_captions_ops",
    "insert_text_ops",
    "set_composition_style_ops",
    "set_narration_ops",
    "set_text_ops",
    "text_safe_layout",
]
