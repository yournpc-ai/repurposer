"""Edit ops and the pure apply step of the content write door (§2.2).

``apply_ops`` is a PURE function: candidate in, candidate out, or an
``EditError`` — the store wraps it in the transaction, base_ref check,
whole-candidate validation and digest/CAS write. An op that cannot apply
kills the whole batch; nothing half-lands.

First-slice op vocabulary (whole-entity adds, field-replace patches — the
fixture/CRUD needs of this batch, not the full future grammar):

- set_settings            replace production settings
- bind_source             bind a snapshot into version.sources (the digest
                          is resolved from the snapshot row by the store and
                          pinned into the version)
- unbind_source           remove a binding (must be unreferenced)
- add_scene / update_scene / move_scene / remove_scene
- add_track / remove_track (remove requires an empty track — explicit clip
                          removal first, never a silent cascade)
- add_clip / update_clip / remove_clip

Patch semantics: update ops distinguish ABSENT from explicit ``null`` via
``model_fields_set`` — absent keeps the value, explicit null clears it (a
stale visual_description is worse than none, §14).

ID law (§4.2): update ops keep the entity id; new entities carry fresh ids
minted by the caller. ``duplicate_clip`` is the one copy helper — it re-ids
clip/object/animations and remaps the clip's INTERNAL animation targets;
scene speech references keep pointing at the original clip.
"""

from __future__ import annotations

import copy
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    Object,
    Scene,
    SourceBinding,
    SpeechObject,
    TimeRange,
    Track,
    VersionSettings,
)


class EditError(ValueError):
    """One op of the batch failed to apply; the whole batch is rejected."""


class SetSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_settings"]
    settings: VersionSettings


class BindSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["bind_source"]
    snapshot_id: UUID


class UnbindSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["unbind_source"]
    snapshot_id: UUID


class AddScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_scene"]
    scene: Scene


class UpdateScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_scene"]
    scene_id: str
    intent: str | None = None
    visual_description: str | None = None
    range: TimeRange | None = None


class RemoveScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_scene"]
    scene_id: str


class MoveScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["move_scene"]
    scene_id: str
    start: int = Field(ge=0)


class AddTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_track"]
    track: Track


class RemoveTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_track"]
    track_id: str


class AddClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_clip"]
    track_id: str
    clip: Clip


class UpdateClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_clip"]
    clip_id: str
    range: TimeRange | None = None
    # Absent = keep; explicit null = detach from the scene.
    scene_id: str | None = None
    source: ClipSource | None = None
    object: Object | None = None
    animations: list[Animation] | None = None


class RemoveClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_clip"]
    clip_id: str


Op = Annotated[
    SetSettings
    | BindSource
    | UnbindSource
    | AddScene
    | UpdateScene
    | MoveScene
    | RemoveScene
    | AddTrack
    | RemoveTrack
    | AddClip
    | UpdateClip
    | RemoveClip,
    Field(discriminator="op"),
]


def _find_track(content: CompositionContent, track_id: str) -> Track:
    for track in content.timeline.tracks:
        if track.track_id == track_id:
            return track
    raise EditError(f"track {track_id} does not exist")


def _find_clip(content: CompositionContent, clip_id: str) -> Clip:
    for track in content.timeline.tracks:
        for clip in track.clips:
            if clip.clip_id == clip_id:
                return clip
    raise EditError(f"clip {clip_id} does not exist")


def _find_scene(content: CompositionContent, scene_id: str) -> Scene:
    for scene in content.scenes:
        if scene.scene_id == scene_id:
            return scene
    raise EditError(f"scene {scene_id} does not exist")


def _invalidate_visual_description(content: CompositionContent, scene_id: str | None) -> None:
    """A deterministic visual change retires only the affected scene summary."""
    if scene_id is None:
        return
    scene = _find_scene(content, scene_id)
    scene.visual_description = None


def _apply_one(content: CompositionContent, op: Op, bound_digests: dict[UUID, str]) -> None:
    """Apply one op in place. ``bound_digests`` maps snapshot_id → digest as
    resolved from the snapshot rows by the store (the version pins THAT
    digest, never a caller-supplied one)."""
    if isinstance(op, SetSettings):
        if content.settings != op.settings:
            for scene in content.scenes:
                scene.visual_description = None
        content.settings = op.settings
    elif isinstance(op, BindSource):
        if op.snapshot_id not in bound_digests:
            raise EditError(f"snapshot {op.snapshot_id} does not exist")
        if any(b.snapshot_id == op.snapshot_id for b in content.sources):
            raise EditError(f"snapshot {op.snapshot_id} is already bound")
        content.sources.append(
            SourceBinding(snapshot_id=op.snapshot_id, snapshot_digest=bound_digests[op.snapshot_id])
        )
    elif isinstance(op, UnbindSource):
        referenced = any(
            c.source is not None and c.source.snapshot_id == op.snapshot_id
            for t in content.timeline.tracks
            for c in t.clips
        )
        if referenced:
            raise EditError(f"snapshot {op.snapshot_id} is still referenced by a clip")
        before = len(content.sources)
        content.sources = [b for b in content.sources if b.snapshot_id != op.snapshot_id]
        if len(content.sources) == before:
            raise EditError(f"snapshot {op.snapshot_id} is not bound")
    elif isinstance(op, AddScene):
        content.scenes.append(copy.deepcopy(op.scene))
    elif isinstance(op, UpdateScene):
        scene = _find_scene(content, op.scene_id)
        if "intent" in op.model_fields_set:
            scene.intent = op.intent or ""
        if "visual_description" in op.model_fields_set:
            scene.visual_description = op.visual_description
        if "range" in op.model_fields_set and op.range is not None:
            if op.range != scene.range and any(
                c.scene_id == scene.scene_id for t in content.timeline.tracks for c in t.clips
            ):
                raise EditError("scene has clips: use move_scene; resizing populated scenes is unsupported")
            scene.range = op.range
    elif isinstance(op, MoveScene):
        scene = _find_scene(content, op.scene_id)
        delta = op.start - scene.range.start
        scene.range = TimeRange(start=op.start, end=scene.range.end + delta)
        for track in content.timeline.tracks:
            for clip in track.clips:
                if clip.scene_id == op.scene_id:
                    if clip.range.start + delta < 0:
                        raise EditError("moving the scene would put a clip before output time zero")
                    clip.range = TimeRange(
                        start=clip.range.start + delta, end=clip.range.end + delta,
                    )
        # Clip-local animations and source windows remain unchanged. The
        # store validates overlaps/ranges before the whole batch can land.
    elif isinstance(op, RemoveScene):
        _find_scene(content, op.scene_id)
        removed_ids = {
            clip.clip_id for track in content.timeline.tracks for clip in track.clips
            if clip.scene_id == op.scene_id
        }
        content.scenes = [s for s in content.scenes if s.scene_id != op.scene_id]
        for track in content.timeline.tracks:
            track.clips = [clip for clip in track.clips if clip.clip_id not in removed_ids]
        for scene in content.scenes:
            scene.speech_clip_ids = [ref for ref in scene.speech_clip_ids if ref not in removed_ids]
    elif isinstance(op, AddTrack):
        for clip in op.track.clips:
            _invalidate_visual_description(content, clip.scene_id)
        content.timeline.tracks.append(copy.deepcopy(op.track))
    elif isinstance(op, RemoveTrack):
        track = _find_track(content, op.track_id)
        if track.clips:
            raise EditError(
                f"track {op.track_id} still holds {len(track.clips)} clips — remove them first"
            )
        content.timeline.tracks = [
            t for t in content.timeline.tracks if t.track_id != op.track_id
        ]
    elif isinstance(op, AddClip):
        _invalidate_visual_description(content, op.clip.scene_id)
        _find_track(content, op.track_id).clips.append(copy.deepcopy(op.clip))
    elif isinstance(op, UpdateClip):
        clip = _find_clip(content, op.clip_id)
        old_scene_id = clip.scene_id
        audio_only = isinstance(clip.object, (AudioObject, SpeechObject)) and (
            op.object is None or isinstance(op.object, (AudioObject, SpeechObject))
        )
        if not audio_only and op.model_fields_set & {"range", "scene_id", "source", "object", "animations"}:
            _invalidate_visual_description(content, old_scene_id)
        if "range" in op.model_fields_set and op.range is not None:
            clip.range = op.range
        if "scene_id" in op.model_fields_set:
            clip.scene_id = op.scene_id
        if "source" in op.model_fields_set:
            clip.source = op.source
        if "object" in op.model_fields_set and op.object is not None:
            clip.object = op.object
        if "animations" in op.model_fields_set:
            clip.animations = list(op.animations or [])
        if "scene_id" in op.model_fields_set and clip.scene_id != old_scene_id:
            _invalidate_visual_description(content, clip.scene_id)
    elif isinstance(op, RemoveClip):
        clip = _find_clip(content, op.clip_id)
        _invalidate_visual_description(content, clip.scene_id)
        for track in content.timeline.tracks:
            track.clips = [c for c in track.clips if c.clip_id != op.clip_id]
        # Scene speech references to the removed clip die with it — a
        # dangling reference is never left behind.
        for scene in content.scenes:
            if op.clip_id in scene.speech_clip_ids:
                scene.speech_clip_ids = [
                    r for r in scene.speech_clip_ids if r != op.clip_id
                ]
    else:  # pragma: no cover — the Op union is exhaustive
        raise EditError(f"unknown op {type(op).__name__}")


def apply_ops(
    content: CompositionContent,
    ops: list[Op],
    bound_digests: dict[UUID, str],
) -> CompositionContent:
    """Apply the whole batch to a DEEP copy; any failure → EditError and the
    input is untouched (the store discards the candidate)."""
    candidate = copy.deepcopy(content)
    for op in ops:
        _apply_one(candidate, op, bound_digests)
    return candidate


def duplicate_clip(
    content: CompositionContent,
    clip_id: str,
    *,
    new_clip_id: str,
    new_object_id: str,
    new_animation_ids: list[str],
    new_range: TimeRange | None = None,
) -> Clip:
    """Copy a clip with ALL internal ids re-minted and internal animation
    targets remapped (§4.2 copy law). The copy shares the same snapshot
    binding (source media is never duplicated). Scene speech references stay
    on the ORIGINAL clip. The copy is returned, not inserted — the caller
    adds it via add_clip so the batch stays one atomic write."""
    original = _find_clip(content, clip_id)
    if len(new_animation_ids) != len(original.animations):
        raise EditError("new_animation_ids must cover every animation of the clip")
    clone = copy.deepcopy(original)
    clone.clip_id = new_clip_id
    clone.object.object_id = new_object_id
    for anim, new_id in zip(clone.animations, new_animation_ids):
        anim.animation_id = new_id
        anim.target_object_id = new_object_id
    if new_range is not None:
        clone.range = new_range
    return clone
