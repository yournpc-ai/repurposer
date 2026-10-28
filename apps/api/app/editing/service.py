"""Shared application service for the video content chain (B2).

design / revise / read share ONE seat — the chat plan path and the propose
path both land here; neither carries its own compose/patch copy. Everything
content-side still passes the single write door (``apply_composition_edits``):
this module translates the LLM-facing revision vocabulary into write-door
ops, computes the system change set, and shapes the canonical read.

The design orchestration's IO half (capture, snapshot freezing, the director
LLM call) lives in ``app/tools/video/design.py`` — gate 6a keeps this module
on models+editing imports only; what arrives here is already prepared.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.edits import (
    AddClip,
    AddTrack,
    apply_ops,
    EditError,
    MoveScene,
    Op,
    RemoveClip,
    RemoveScene,
    RemoveTrack,
    SetSettings,
    UnbindSource,
    UpdateClip,
    UpdateScene,
)
from app.editing.schemas import (
    Animation,
    Clip,
    ClipSource,
    CompositionContent,
    Easing,
    GeneratorObject,
    Keyframe,
    LayoutBox,
    ShapeObject,
    SpeechObject,
    TextObject,
    TextStyle,
    TimeRange,
    Track,
    VideoObject,
    WebObject,
    speech_text_digest,
)
from app.editing.store import (
    apply_composition_edits,
    content_of,
    get_video_version,
    snapshot_facts,
)
from app.editing.grounding import resolve_focus
from app.editing.storyboard import storyboard_payload
from app.editing.templates import ClipBlueprint, ViewFact, _camera_animations
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks
from app.models.schemas import (
    ReviseVideoArgs,
    VideoEditAddText,
    VideoEditBackground,
    VideoEditFocusWeb,
    VideoEditMoveScene,
    VideoEditRemoveClip,
    VideoEditRemoveScene,
    VideoEditSyncCaptions,
    VideoEditUpdateAnimation,
    VideoEditUpdateGenerator,
    VideoEditUpdateShape,
    VideoEditUpdateSpeech,
    VideoEditUpdateText,
    VideoEditUpdateVideo,
    canonical_json_hash,
)
from app.models.tables import Composition, CompositionVersion


class VideoServiceError(ValueError):
    """A revision/design rejection whose text is model-facing feedback."""


def presentation_digest_of(payload: dict[str, Any]) -> str:
    """The presented content's identity (§2.3): the canonical storyboard
    payload's hash — the receipt proves THIS table was presented for THIS
    version."""
    return canonical_json_hash(payload)


def version_read_dict(
    composition: Composition, version: CompositionVersion, payload: dict[str, Any]
) -> dict[str, Any]:
    """The version read/presentation facts (one shape for the tool
    observation, the receipt and the DTO route)."""
    return {
        "composition_id": str(composition.id),
        "composition_name": composition.name,
        "composition_version_id": str(version.id),
        "version": version.version,
        "content_digest": version.content_digest,
        "base_ref": {
            "composition_id": str(composition.id),
            "composition_version_id": str(version.id),
            "content_digest": version.content_digest,
        },
        "presentation_digest": presentation_digest_of(payload),
        "storyboard": payload,
    }


async def video_version_read(
    db: AsyncSession,
    *,
    owner_id: UUID,
    version_id: UUID | None = None,
    composition_id: UUID | None = None,
    output_id: UUID | None = None,
) -> dict[str, Any]:
    """The explicit version read face (§2.2) with its canonical storyboard."""
    if output_id is not None:
        from app.models.tables import Output, Project
        output = await db.get(Output, output_id)
        project = await db.get(Project, output.project_id) if output else None
        if (project is None or project.user_id != owner_id
                or output.composition_version_id is None):
            raise VideoServiceError("This output has no accessible editable video version")
        version_id = output.composition_version_id
    composition, version = await get_video_version(
        db, owner_id=owner_id, version_id=version_id, composition_id=composition_id
    )
    content = content_of(version)
    facts = await snapshot_facts(db, {b.snapshot_id for b in content.sources})
    payload = storyboard_payload(
        content,
        composition_id=composition.id,
        version_id=version.id,
        version=version.version,
        content_digest=version.content_digest,
        source_facts=facts,
    )
    read = version_read_dict(composition, version, payload)
    read["is_current"] = composition.current_version_id == version.id
    read["current_version_id"] = str(composition.current_version_id)
    return read


# ---------------------------------------------------------------------------
# Revision: LLM-facing ops → write-door ops
# ---------------------------------------------------------------------------

# Code-owned default layouts for added text, by track role (canvas-relative;
# the design template's own placements stay the template's).
_ADD_TEXT_LAYOUT = {
    "title": {"x": 160.0, "y": 340.0, "width": 1600.0, "height": 340.0},
    "caption": {"x": 260.0, "y": 920.0, "width": 1400.0, "height": 110.0},
}
_ADD_TEXT_SIZE = {
    "title": {"small": 48, "medium": 96, "large": 140},
    "caption": {"small": 28, "medium": 36, "large": 48},
}
_EASE_OUT = (0.16, 1.0, 0.3, 1.0)


def _find_clip(content: CompositionContent, clip_id: str) -> Clip:
    for track in content.timeline.tracks:
        for clip in track.clips:
            if clip.clip_id == clip_id:
                return clip
    raise VideoServiceError(f"clip {clip_id!r} does not exist in the base version")


def _find_scene(content: CompositionContent, scene_id: str):
    for scene in content.scenes:
        if scene.scene_id == scene_id:
            return scene
    raise VideoServiceError(f"scene {scene_id!r} does not exist in the base version")


def _updated_text_clip(clip: Clip, obj: TextObject) -> Op:
    """Persist text and retarget only animations that covered the whole old text."""
    if obj.text != clip.object.text:
        from app.editing.animation import derive_text_parts
        animations = []
        for anim in clip.animations:
            target = anim.text_part
            if target is not None and set(target.part_ids) == {
                p.part_id for p in derive_text_parts(clip.object.text, target.kind)
            }:
                target = target.model_copy(update={"part_ids": [
                    p.part_id for p in derive_text_parts(obj.text, target.kind)
                ]})
                anim = anim.model_copy(update={"text_part": target})
            animations.append(anim)
        return UpdateClip(op="update_clip", clip_id=clip.clip_id, object=obj, animations=animations)
    return UpdateClip(op="update_clip", clip_id=clip.clip_id, object=obj)


def _translate_update_text(content: CompositionContent, op: VideoEditUpdateText) -> Op:
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, TextObject):
        raise VideoServiceError(
            f"clip {op.clip_id!r} is a {clip.object.kind} clip, not text — "
            "only text clips take update_text"
        )
    obj = clip.object.model_copy(deep=True)
    if op.text is not None:
        obj.text = op.text
    if op.font_size is not None:
        obj.style.font_size = op.font_size
    if op.color is not None:
        obj.style.color = op.color
    if "background" in op.model_fields_set:
        obj.style.background = op.background  # explicit null clears the chip
    if op.align is not None:
        obj.style.align = op.align
    if op.weight is not None:
        obj.style.weight = op.weight
    if op.text is not None and op.text != clip.object.text and obj.caption is not None:
        obj.caption.state = "independent"
    return _updated_text_clip(clip, obj)


def _linked_caption_clips(content: CompositionContent, speech_object_id: str) -> list[Clip]:
    return [
        clip
        for track in content.timeline.tracks
        for clip in track.clips
        if isinstance(clip.object, TextObject)
        and clip.object.caption is not None
        and clip.object.caption.speech_object_id == speech_object_id
    ]


def _translate_update_speech(content: CompositionContent, op: VideoEditUpdateSpeech) -> list[Op]:
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, SpeechObject):
        raise VideoServiceError("update_speech only targets a SpeechClip")
    if not (set(op.model_fields_set) - {"op", "clip_id"}):
        raise VideoServiceError("update_speech needs at least one changed field")
    speech = clip.object.model_copy(deep=True)
    for field in ("text", "voice_id", "language", "gain_db"):
        value = getattr(op, field)
        if value is not None:
            setattr(speech, field, value)
    ops: list[Op] = [UpdateClip(op="update_clip", clip_id=clip.clip_id, object=speech)]
    for caption_clip in _linked_caption_clips(content, speech.object_id):
        caption = caption_clip.object
        assert isinstance(caption, TextObject) and caption.caption is not None
        if caption.caption.state != "derived":
            continue
        revised = caption.model_copy(deep=True)
        revised.text = speech.text
        revised.caption.source_text_digest = speech_text_digest(speech.text)
        ops.append(_updated_text_clip(caption_clip, revised))
    return ops


def _translate_sync_captions(content: CompositionContent, op: VideoEditSyncCaptions) -> list[Op]:
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, SpeechObject):
        raise VideoServiceError("sync_captions targets the SpeechClip whose captions should refresh")
    linked = _linked_caption_clips(content, clip.object.object_id)
    if not linked:
        raise VideoServiceError(f"speech clip {op.clip_id!r} has no linked captions")
    ops: list[Op] = []
    for caption_clip in linked:
        caption = caption_clip.object
        assert isinstance(caption, TextObject) and caption.caption is not None
        revised = caption.model_copy(deep=True)
        revised.text = clip.object.text
        revised.caption.source_text_digest = speech_text_digest(clip.object.text)
        revised.caption.state = "derived"
        ops.append(_updated_text_clip(caption_clip, revised))
    return ops


def _translate_add_text(content: CompositionContent, op: VideoEditAddText, token: str | None = None) -> list[Op]:
    scene = _find_scene(content, op.scene_id)
    timebase = content.settings.timebase
    start = scene.range.start + (
        seconds_to_ticks(op.at_seconds, timebase) if op.at_seconds is not None else 0
    )
    end = (
        start + seconds_to_ticks(op.duration_seconds, timebase)
        if op.duration_seconds is not None
        else scene.range.end
    )
    if end > scene.range.end or end <= start:
        raise VideoServiceError(
            f"the added text must stay inside scene {op.scene_id}'s window "
            f"({scene.range.start / timebase:.2f}s–{scene.range.end / timebase:.2f}s)"
        )
    token = token or uuid4().hex[:8]
    clip_id, object_id = f"clp_rev_{token}", f"obj_rev_{token}"
    fade = min(seconds_to_ticks(0.4, timebase), (end - start) // 2)
    animations = (
        [
            Animation(
                animation_id=f"anm_rev_{token}",
                target_object_id=object_id,
                property="opacity",
                keyframes=[
                    Keyframe(at=0, value=0.0),
                    Keyframe(at=fade, value=1.0),
                ],
            )
        ]
        if fade > 0
        else []
    )
    style = TextStyle(
        font_size=_ADD_TEXT_SIZE[op.track][op.size],
        color=op.color or "#F8FAFC",
        background="#111827" if op.track == "caption" else None,
        weight=700 if op.track == "title" else 600,
        align=op.align,
    )
    clip = Clip(
        clip_id=clip_id,
        range=TimeRange(start=start, end=end),
        scene_id=op.scene_id,
        source=None,
        object=TextObject(
            kind="text",
            object_id=object_id,
            text=op.text,
            layout=LayoutBox.model_validate(_ADD_TEXT_LAYOUT[op.track]),
            style=style,
        ),
        animations=animations,
    )
    for track in content.timeline.tracks:
        if track.kind == "visual" and track.role == op.track and all(
            c.range.end <= start or c.range.start >= end for c in track.clips
        ):
            return [AddClip(op="add_clip", track_id=track.track_id, clip=clip)]
    # An overlay needs its own track, never a weakened overlap validator.
    track_id = f"trk_rev_{token}"
    order = max((t.order for t in content.timeline.tracks if t.kind == "visual"), default=-1) + 1
    return [
        AddTrack(op="add_track", track=Track(
            track_id=track_id, kind="visual", role=op.track, order=order,
        )),
        AddClip(op="add_clip", track_id=track_id, clip=clip),
    ]


def _translate_remove_clip(content: CompositionContent, op: VideoEditRemoveClip) -> Op:
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, TextObject):
        raise VideoServiceError(
            f"clip {op.clip_id!r} is a {clip.object.kind} clip — removing "
            "media clips one by one is not supported yet (remove_scene takes "
            "a whole scene)"
        )
    return RemoveClip(op="remove_clip", clip_id=op.clip_id)


def _translate_update_video(content: CompositionContent, op: VideoEditUpdateVideo) -> Op:
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, VideoObject):
        raise VideoServiceError(
            f"clip {op.clip_id!r} is a {clip.object.kind} clip, not video — "
            "update_video only targets real video objects"
        )
    changed = set(op.model_fields_set) - {"op", "clip_id"}
    if not changed:
        raise VideoServiceError("update_video needs at least one changed field")
    obj = clip.object.model_copy(deep=True)
    for field in ("x", "y", "width", "height"):
        value = getattr(op, field)
        if value is not None:
            setattr(obj.layout, field, value)
    if op.scale is not None:
        obj.transform.scale = op.scale
    if op.fit is not None:
        obj.fit = op.fit
    if op.gain_db is not None:
        obj.gain_db = op.gain_db
    if op.muted is not None:
        obj.muted = op.muted

    kwargs: dict[str, Any] = {"op": "update_clip", "clip_id": op.clip_id, "object": obj}
    if changed & {"snapshot_id", "source_start_seconds", "source_end_seconds"}:
        if clip.source is None or clip.source.source_range is None:
            raise VideoServiceError("the video clip has no editable source window")
        snapshot_id = op.snapshot_id or clip.source.snapshot_id
        binding = next((b for b in content.sources if b.snapshot_id == snapshot_id), None)
        if binding is None:
            raise VideoServiceError(
                "the requested snapshot is not bound to this version; add it through design first"
            )
        start_seconds = (
            op.source_start_seconds
            if op.source_start_seconds is not None
            else clip.source.source_range.start / SOURCE_TIMEBASE
        )
        end_seconds = (
            op.source_end_seconds
            if op.source_end_seconds is not None
            else clip.source.source_range.end / SOURCE_TIMEBASE
        )
        source_range = TimeRange(
            start=seconds_to_ticks(start_seconds, SOURCE_TIMEBASE),
            end=seconds_to_ticks(end_seconds, SOURCE_TIMEBASE),
        )
        if source_range.duration != clip.range.duration:
            raise VideoServiceError(
                "a targeted source-window change keeps the current output duration; "
                "choose a segment of the same length so the other layers stay unchanged"
            )
        kwargs["source"] = ClipSource(
            snapshot_id=snapshot_id,
            snapshot_digest=binding.snapshot_digest,
            source_range=source_range,
        )
    return UpdateClip.model_validate(kwargs)


def _translate_update_shape(content: CompositionContent, op: VideoEditUpdateShape) -> Op:
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, ShapeObject):
        raise VideoServiceError(
            f"clip {op.clip_id!r} is a {clip.object.kind} clip, not a native shape"
        )
    changed = set(op.model_fields_set) - {"op", "clip_id"}
    if not changed:
        raise VideoServiceError("update_shape needs at least one changed field")
    obj = clip.object.model_copy(deep=True)
    for field in (
        "shape", "fill", "stroke", "stroke_width", "corner_radius", "path", "opacity",
    ):
        if field in op.model_fields_set:
            setattr(obj, field, getattr(op, field))
    for field in ("x", "y", "width", "height"):
        value = getattr(op, field)
        if value is not None:
            setattr(obj.layout, field, value)
    if op.scale is not None:
        obj.transform.scale = op.scale
    if op.rotation is not None:
        obj.transform.rotation = op.rotation
    obj = ShapeObject.model_validate(obj.model_dump(mode="json"))
    return UpdateClip(op="update_clip", clip_id=op.clip_id, object=obj)


def _translate_update_generator(content: CompositionContent, op: VideoEditUpdateGenerator) -> Op:
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, GeneratorObject):
        raise VideoServiceError(
            f"clip {op.clip_id!r} is a {clip.object.kind} clip, not a GeneratorObject"
        )
    changed = set(op.model_fields_set) - {"op", "clip_id"}
    if not changed:
        raise VideoServiceError("update_generator needs changed code, prompt, parameters or external layout")
    obj = clip.object.model_copy(deep=True)
    if op.code is not None:
        obj.code = op.code
    if op.prompt is not None:
        obj.prompt = op.prompt
    if op.parameters is not None:
        obj.parameters = op.parameters
    for field in ("x", "y", "width", "height"):
        value = getattr(op, field)
        if value is not None:
            setattr(obj.layout, field, value)
    if op.scale is not None:
        obj.transform.scale = op.scale
    if op.fit is not None:
        obj.fit = op.fit
    if op.opacity is not None:
        obj.opacity = op.opacity
    obj = GeneratorObject.model_validate(obj.model_dump(mode="json"))
    return UpdateClip(op="update_clip", clip_id=op.clip_id, object=obj)


def _translate_update_animation(
    content: CompositionContent, op: VideoEditUpdateAnimation
) -> Op:
    for track in content.timeline.tracks:
        for clip in track.clips:
            for anim in clip.animations:
                if anim.animation_id != op.animation_id:
                    continue
                keyframes: list[Keyframe] = []
                for kf in op.keyframes:
                    value: float | tuple[float, float]
                    if isinstance(kf.value, list):
                        if anim.property != "transform.position" or len(kf.value) != 2:
                            raise VideoServiceError(
                                f"animation {op.animation_id} ({anim.property}) takes "
                                "a scalar value — [x, y] pairs belong to transform.position"
                            )
                        value = (float(kf.value[0]), float(kf.value[1]))
                    else:
                        if anim.property == "transform.position":
                            raise VideoServiceError(
                                f"animation {op.animation_id} positions take [x, y] pairs"
                            )
                        value = float(kf.value)
                    easing = Easing(kind="cubic_bezier", params=_EASE_OUT) if kf.easing == "ease_out" else Easing(kind=kf.easing)
                    keyframes.append(
                        Keyframe(
                            at=seconds_to_ticks(kf.at_seconds, content.settings.timebase),
                            value=value,
                            easing=easing,
                        )
                    )
                animations = [
                    a.model_copy(update={"keyframes": keyframes}) if a is anim else a
                    for a in clip.animations
                ]
                return UpdateClip(op="update_clip", clip_id=clip.clip_id, animations=animations)
    raise VideoServiceError(
        f"animation {op.animation_id!r} does not exist in the base version"
    )


def _translate_focus_web(
    content: CompositionContent,
    op: VideoEditFocusWeb,
    snapshots: dict[UUID, dict[str, Any]],
) -> Op:
    """Resolve a frozen webpage element into the template's camera animations.

    Only the target WebObject's scale/position animations change. Its source,
    view, layout, timing and every unrelated animation stay byte-identical.
    """
    clip = _find_clip(content, op.clip_id)
    if not isinstance(clip.object, WebObject) or clip.source is None:
        raise VideoServiceError(f"clip {op.clip_id!r} is not a sourced webpage clip")
    facts = snapshots.get(clip.source.snapshot_id)
    if facts is None or facts["digest"] != clip.source.snapshot_digest:
        raise VideoServiceError(f"clip {op.clip_id!r} has no resolved bound webpage snapshot")
    view = next(
        (
            item
            for item in (facts.get("meta") or {}).get("views") or []
            if item.get("view_id") == clip.object.view_id
        ),
        None,
    )
    if view is None:
        raise VideoServiceError(
            f"clip {op.clip_id!r} has no frozen view {clip.object.view_id!r}"
        )
    try:
        focus = resolve_focus(view.get("elements") or [], op.element_id)
    except ValueError as exc:
        raise VideoServiceError(str(exc)) from exc

    old_scale = next(
        (
            animation
            for animation in clip.animations
            if animation.target_object_id == clip.object.object_id
            and animation.property == "transform.scale"
        ),
        None,
    )
    old_position = next(
        (
            animation
            for animation in clip.animations
            if animation.target_object_id == clip.object.object_id
            and animation.property == "transform.position"
        ),
        None,
    )
    start_scale = 1.08
    if old_scale and old_scale.keyframes and isinstance(old_scale.keyframes[0].value, float | int):
        start_scale = float(old_scale.keyframes[0].value)
    clip_ticks = clip.range.duration
    arrival_frac = 0.45
    if old_position and len(old_position.keyframes) > 1:
        arrival_frac = old_position.keyframes[1].at / clip_ticks
    blueprint = ClipBlueprint(
        track="visual",
        preset="camera",
        preset_params={"start_scale": start_scale, "arrival_frac": arrival_frac},
    )
    view_fact = ViewFact(
        snapshot_id=clip.source.snapshot_id,
        snapshot_digest=clip.source.snapshot_digest,
        view_id=clip.object.view_id,
        width=int(view["width"]),
        height=int(view["height"]),
        elements=view.get("elements") or [],
        heading=str(view.get("heading") or ""),
        page=0,
    )
    fresh = [
        Animation.model_validate(item)
        for item in _camera_animations(
            blueprint,
            object_id=clip.object.object_id,
            view=view_fact,
            focus=focus,
            clip_ticks=clip_ticks,
            canvas=(content.settings.width, content.settings.height),
            animation_prefix=f"{clip.clip_id}_camera",
        )
    ]
    fresh_by_property = {animation.property: animation for animation in fresh}
    replaced: set[str] = set()
    animations: list[Animation] = []
    for existing in clip.animations:
        replacement = fresh_by_property.get(existing.property)
        if existing.target_object_id == clip.object.object_id and replacement is not None:
            animations.append(replacement.model_copy(update={"animation_id": existing.animation_id}))
            replaced.add(existing.property)
        else:
            animations.append(existing)
    animations.extend(
        animation for animation in fresh if animation.property not in replaced
    )
    return UpdateClip(op="update_clip", clip_id=clip.clip_id, animations=animations)


def translate_revision(
    content: CompositionContent,
    args: ReviseVideoArgs,
    *,
    request_id: str | None = None,
    snapshots: dict[UUID, dict[str, Any]] | None = None,
) -> list[Op]:
    """The LLM-facing revision vocabulary → the write door's op batch. Any
    failure rejects the WHOLE batch with a model-readable reason."""
    ops: list[Op] = []
    for index, edit in enumerate(args.edits):
        current = apply_ops(content, ops, {})
        if isinstance(edit, VideoEditUpdateText):
            ops.append(_translate_update_text(current, edit))
        elif isinstance(edit, VideoEditUpdateSpeech):
            ops.extend(_translate_update_speech(current, edit))
        elif isinstance(edit, VideoEditSyncCaptions):
            ops.extend(_translate_sync_captions(current, edit))
        elif isinstance(edit, VideoEditAddText):
            token = uuid5(NAMESPACE_URL, f"video-text:{request_id}:{index}").hex if request_id else None
            ops.extend(_translate_add_text(current, edit, token))
        elif isinstance(edit, VideoEditRemoveClip):
            ops.append(_translate_remove_clip(current, edit))
        elif isinstance(edit, VideoEditUpdateVideo):
            ops.append(_translate_update_video(current, edit))
        elif isinstance(edit, VideoEditFocusWeb):
            if snapshots is None:
                raise VideoServiceError("focus_web needs the base version's resolved snapshots")
            ops.append(_translate_focus_web(current, edit, snapshots))
        elif isinstance(edit, VideoEditUpdateShape):
            ops.append(_translate_update_shape(current, edit))
        elif isinstance(edit, VideoEditUpdateGenerator):
            ops.append(_translate_update_generator(current, edit))
        elif isinstance(edit, VideoEditUpdateAnimation):
            ops.append(_translate_update_animation(current, edit))
        elif isinstance(edit, VideoEditMoveScene):
            _find_scene(current, edit.scene_id)
            ops.append(
                MoveScene(op="move_scene",
                    scene_id=edit.scene_id,
                    start=seconds_to_ticks(edit.start_seconds, content.settings.timebase),
                )
            )
        elif isinstance(edit, VideoEditRemoveScene):
            _find_scene(current, edit.scene_id)
            ops.append(RemoveScene(op="remove_scene", scene_id=edit.scene_id))
        elif isinstance(edit, VideoEditBackground):
            settings = current.settings.model_copy(update={"background": edit.color})
            ops.append(SetSettings(op="set_settings", settings=settings))
        else:  # pragma: no cover — the union is exhaustive
            raise VideoServiceError(f"unknown edit op {type(edit).__name__}")
    # The revision's fresh visual summaries land AFTER the content ops in the
    # same batch — the door's own invalidation clears the stale description
    # first, this then sets the scene's current picture (§3.2 rule 3).
    for item in args.visual_descriptions or []:
        scene_id = str(item.get("scene_id") or "")
        text = str(item.get("text") or "").strip()
        if not scene_id or not text:
            raise VideoServiceError("visual_descriptions entries need scene_id + text")
        _find_scene(content, scene_id)
        ops.append(UpdateScene(op="update_scene", scene_id=scene_id, visual_description=text))
    return ops


async def revise_video(
    db: AsyncSession,
    *,
    owner_id: UUID,
    args: ReviseVideoArgs,
    request_id: str | None = None,
    prepare_candidate: Callable[[CompositionContent], Awaitable[Any]] | None = None,
) -> dict[str, Any]:
    """The targeted-revision seat (B2): explicit base_ref → translated op
    batch → the write door → the new version's canonical read + the
    system-computed change set. The caller supplies a DEDICATED session —
    the write door commits; a chat turn's own transaction never rides it.

    Rejections (stale base, unknown handles, validator problems) raise —
    the turn seats map them to model-facing repair feedback verbatim.
    """
    composition, base_version = await get_video_version(
        db,
        owner_id=owner_id,
        version_id=args.base_ref.composition_version_id,
    )
    if composition.id != args.base_ref.composition_id:
        raise VideoServiceError(
            "base_ref's composition_id does not match the version's work — "
            "re-read the version with get_video_version and echo its base_ref"
        )
    base_content = content_of(base_version)
    facts = await snapshot_facts(db, {b.snapshot_id for b in base_content.sources})
    ops = translate_revision(
        base_content, args, request_id=request_id, snapshots=facts
    )
    if prepare_candidate is not None:
        # The tools layer may execute a bounded preflight (Generator preview)
        # against the pure candidate; only the write door below persists it.
        candidate = apply_ops(base_content, ops, {})
        await prepare_candidate(candidate)
    _, version, replayed = await apply_composition_edits(
        db,
        owner_id=owner_id,
        composition_id=composition.id,
        base_version_id=base_version.id,
        base_digest=args.base_ref.content_digest,
        ops=ops,
        request_id=request_id,
    )
    new_content = content_of(version)
    facts = await snapshot_facts(db, {b.snapshot_id for b in new_content.sources})
    payload = storyboard_payload(
        new_content,
        composition_id=composition.id,
        version_id=version.id,
        version=version.version,
        content_digest=version.content_digest,
        source_facts=facts,
    )
    read = version_read_dict(composition, version, payload)
    read["change_set"] = compute_change_set(base_content, new_content)
    read["previous_version_ref"] = args.base_ref.model_dump(mode="json")
    read["replayed"] = replayed
    return read


# ---------------------------------------------------------------------------
# Change set (system-computed, never model-reported — §2.2)
# ---------------------------------------------------------------------------

def compute_change_set(
    base: CompositionContent, new: CompositionContent
) -> dict[str, Any]:
    """The honest delta between two saved versions: scene adds/removals/
    moves, clip adds/removals/updates with the changed fields named."""
    base_scenes = {s.scene_id: s for s in base.scenes}
    new_scenes = {s.scene_id: s for s in new.scenes}
    base_clips = {
        c.clip_id: c for t in base.timeline.tracks for c in t.clips
    }
    new_clips = {c.clip_id: c for t in new.timeline.tracks for c in t.clips}

    def clip_changes(before: Clip, after: Clip) -> list[str]:
        changes: list[str] = []
        if before.range != after.range:
            changes.append("range")
        if before.object.model_dump(mode="json") != after.object.model_dump(mode="json"):
            changes.append("object")
        if [a.model_dump(mode="json") for a in before.animations] != [
            a.model_dump(mode="json") for a in after.animations
        ]:
            changes.append("animations")
        if before.scene_id != after.scene_id:
            changes.append("scene_id")
        if before.source != after.source:
            changes.append("source")
        return changes

    return {
        "settings": {
            key: {"before": before, "after": new.settings.model_dump(mode="json")[key]}
            for key, before in base.settings.model_dump(mode="json").items()
            if before != new.settings.model_dump(mode="json")[key]
        },
        "scenes": {
            "added": [sid for sid in new_scenes if sid not in base_scenes],
            "removed": [sid for sid in base_scenes if sid not in new_scenes],
            "moved": [
                {
                    "scene_id": sid,
                    "from_seconds": base_scenes[sid].range.start / base.settings.timebase,
                    "to_seconds": new_scenes[sid].range.start / new.settings.timebase,
                }
                for sid in new_scenes.keys() & base_scenes.keys()
                if new_scenes[sid].range != base_scenes[sid].range
            ],
        },
        "clips": {
            "added": [
                {"clip_id": cid, "kind": new_clips[cid].object.kind}
                for cid in new_clips
                if cid not in base_clips
            ],
            "removed": [cid for cid in base_clips if cid not in new_clips],
            "updated": [
                {"clip_id": cid, "changes": clip_changes(base_clips[cid], new_clips[cid])}
                for cid in new_clips.keys() & base_clips.keys()
                if clip_changes(base_clips[cid], new_clips[cid])
            ],
        },
    }


# ---------------------------------------------------------------------------
# Redraft: rebuild batch (an open direction change produces a child version
# whose content is re-designed whole — the batch replaces everything through
# the same atomic door, never a bypass)
# ---------------------------------------------------------------------------


def redraft_batch(base: CompositionContent, fresh_ops: list[Op]) -> list[Op]:
    """Prepend the teardown the fresh design needs: unassigned clips out,
    every scene removed (its content cascades), tracks removed, source
    bindings reconciled (unused out; already-bound never re-bound)."""
    from app.editing.edits import BindSource, SetSettings  # same package

    removals: list[Op] = []
    for track in base.timeline.tracks:
        for clip in track.clips:
            if clip.scene_id is None:
                removals.append(RemoveClip(op="remove_clip", clip_id=clip.clip_id))
    for scene in base.scenes:
        removals.append(RemoveScene(op="remove_scene", scene_id=scene.scene_id))
    for track in base.timeline.tracks:
        removals.append(RemoveTrack(op="remove_track", track_id=track.track_id))

    bound = {b.snapshot_id for b in base.sources}
    used = {
        op.clip.source.snapshot_id
        for op in fresh_ops
        if isinstance(op, AddClip) and op.clip.source is not None
    }
    for snapshot_id in bound - used:
        removals.append(UnbindSource(op="unbind_source", snapshot_id=snapshot_id))

    out: list[Op] = list(removals)
    for op in fresh_ops:
        if isinstance(op, BindSource) and op.snapshot_id in bound:
            continue  # still bound from the base — the pinned digest stands
        out.append(op)
    if not any(isinstance(op, SetSettings) for op in out):
        out.insert(len(removals), SetSettings(op="set_settings", settings=base.settings))
    return out


# ---------------------------------------------------------------------------
# The model-facing fact sheet: the canonical payload rendered as compact
# text (the loop's observation; the USER's table is the structured card —
# the model introduces it, never re-transcribes it)
# ---------------------------------------------------------------------------


def format_storyboard_text(read: dict[str, Any]) -> str:
    """Compact, complete, deterministic: every scene's window, intent,
    picture summary, exact on-screen text, and the ids a revision names."""
    payload = read["storyboard"]
    import json

    lines: list[str] = [
        f"Composition {read['composition_id']} “{read['composition_name'] or 'untitled'}” — "
        f"version {read['version']} (id {read['composition_version_id']}).",
        "base_ref for any revision: "
        + json.dumps(read["base_ref"], ensure_ascii=False, sort_keys=True),
        f"Canvas {payload['settings']['width']}x{payload['settings']['height']} "
        f"@ {payload['settings']['fps']:g}fps, {payload['duration_seconds']:.1f}s total.",
    ]
    if read.get("is_current") is False:
        lines.append(
            "This output pins an OLDER version. Current version_id="
            + read["current_version_id"]
            + "; read current and clarify which version to continue; never overwrite silently."
        )
    for scene in payload["scenes"]:
        rng = scene["range_seconds"]
        lines.append(
            f"\n#{scene['number']} {scene['scene_id']} [{rng['start']:.2f}s–{rng['end']:.2f}s]"
            + (f" — {scene['intent']}" if scene.get("intent") else "")
        )
        if scene.get("visual_description"):
            lines.append(f"  picture: {scene['visual_description']}")
        for clip in scene["clips"]:
            desc = f"  clip {clip['clip_id']} ({clip['object_kind']}, {clip['track_role']})"
            if clip.get("text") is not None:
                style = clip.get("style") or {}
                desc += f" text={clip['text']!r} (size {style.get('font_size')}, {style.get('color')})"
            if clip.get("view_id") is not None:
                view = clip.get("view") or {}
                desc += f" view={clip['view_id']} {view.get('heading') or ''}".rstrip()
            if clip.get("source_range_seconds") is not None:
                source_range = clip["source_range_seconds"]
                desc += f" source={source_range['start']:.2f}s–{source_range['end']:.2f}s"
            if clip.get("layout") is not None:
                box = clip["layout"]
                desc += (
                    f" layout=({box['x']:g},{box['y']:g},{box['width']:g},{box['height']:g})"
                )
            if clip["object_kind"] == "video":
                desc += f" fit={clip.get('fit')} gain={clip.get('gain_db')}dB muted={clip.get('muted')}"
            if clip["object_kind"] == "speech":
                desc += (
                    f" voice={clip.get('voice_id')} language={clip.get('language')} "
                    f"provider={clip.get('provider')} model={clip.get('model')} gain={clip.get('gain_db')}dB"
                )
            if clip.get("caption") is not None:
                desc += f" caption_state={clip['caption'].get('state')}"
            if clip["object_kind"] == "shape":
                desc += (
                    f" shape={clip.get('shape')} fill={clip.get('fill')} "
                    f"stroke={clip.get('stroke')} opacity={clip.get('opacity')}"
                )
                if clip.get("path"):
                    desc += f" path={clip['path']!r}"
            if clip["object_kind"] == "generator":
                desc += (
                    f" runtime={clip.get('runtime')} digest={clip.get('program_digest')} "
                    f"output={json.dumps(clip.get('output'), sort_keys=True)} "
                    f"parameters={json.dumps(clip.get('parameters'), ensure_ascii=False, sort_keys=True)}"
                )
                lines.append(desc)
                if clip.get("runtime") == "image-v1":
                    lines.append(
                        f"    IMAGE REQUEST provider={clip.get('provider')} model={clip.get('model')} "
                        "(change prompt with update_generator; internal pixels are not native objects):"
                    )
                    lines.append(str(clip.get("prompt") or ""))
                else:
                    lines.append("    PROGRAM SOURCE (rewrite with update_generator; never a preset id):")
                    lines.append(str(clip.get("code") or ""))
                desc = None
            if desc is not None:
                lines.append(desc)
            for anim in clip["animations"]:
                kfs = ", ".join(
                    f"{kf['at_seconds']:.2f}s→{kf['value']}" for kf in anim["keyframes"]
                )
                part = f" per {anim['text_part']}" if anim.get("text_part") else ""
                lines.append(
                    f"    anim {anim['animation_id']} {anim['property']}{part}: {kfs}"
                )
    for clip in payload["unassigned_clips"]:
        lines.append(
            f"\nglobal clip {clip['clip_id']} ({clip['object_kind']}, {clip['track_role']})"
        )
    speech_clips = [
        clip
        for scene in payload["scenes"]
        for clip in scene["clips"]
        if clip["object_kind"] == "speech"
    ]
    if speech_clips:
        lines.append(
            "\nNarration: reviewed SpeechObjects above; actual audio and sentence-aligned "
            "captions are prepared only by authorized production inside each fixed clip window."
        )
    else:
        lines.append("\nNarration: off.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The presentation receipt (§2.3 — the generic confirmation state's video
# slice) and its carry across PendingPlan rewrites
# ---------------------------------------------------------------------------


def video_carry_state(stored: Any) -> dict[str, Any]:
    """The video presentation receipt preserved verbatim across a PendingPlan
    rewrite (the film_carry_state sibling): a dock/ask/degrade write never
    drops which version was presented where."""
    return {
        "video_presentation": (
            getattr(stored, "video_presentation", None) if stored is not None else None
        )
    }


def video_presentation_receipt(
    read: dict[str, Any], *, review_hold: bool | None = None
) -> dict[str, Any]:
    """The receipt stamped when a version's canonical storyboard is handed
    to the loop; ``presented_message_id`` fills in when the presenting row
    actually persists (the finish beat's stamp)."""
    return {
        "composition_id": read["composition_id"],
        "composition_version_id": read["composition_version_id"],
        "version": read["version"],
        "content_digest": read["content_digest"],
        "presentation_digest": read["presentation_digest"],
        "presented_message_id": None,
        "review_hold": review_hold,
    }


def storyboard_block(read: dict[str, Any]) -> dict[str, Any]:
    """The message block the StoryboardCard resolves (§10: a reference, not
    the payload — the component reads the server DTO)."""
    return {
        "kind": "video_storyboard",
        "composition_id": read["composition_id"],
        "composition_version_id": read["composition_version_id"],
        "version": read["version"],
        "content_digest": read["content_digest"],
        "presentation_digest": read["presentation_digest"],
    }


__all__ = [
    "EditError",
    "VideoServiceError",
    "apply_composition_edits",
    "compute_change_set",
    "presentation_digest_of",
    "redraft_batch",
    "storyboard_block",
    "translate_revision",
    "video_carry_state",
    "video_presentation_receipt",
    "video_version_read",
    "version_read_dict",
]
