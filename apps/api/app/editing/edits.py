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
- temporal_edit         generic stable-id target × move/trim/delete/time_map ×
                          ripple/source policy (legacy temporal ops route here too)
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
from fractions import Fraction
from typing import Annotated, Literal
from uuid import UUID
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    EditTarget,
    Object,
    Scene,
    SourceBinding,
    SourceCaptionDerivation,
    SpeechObject,
    TextObject,
    TimeRange,
    Track,
    Transition,
    VersionSettings,
)


class EditError(ValueError):
    """One op of the batch failed to apply; the whole batch is rejected."""


class TextAnimationTargetLost(EditError):
    """The replacement has too few text parts for the existing animation."""


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


class SetTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set_transition"]
    transition: Transition


class RemoveTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_transition"]
    transition_id: str


class SplitClip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["split_clip"]
    clip_id: str
    at: int = Field(gt=0)
    new_clip_id: str
    new_object_id: str


class TemporalEdit(BaseModel):
    """One target × operation × linkage/source-policy temporal edit.

    All coordinates are resolved against the SAME candidate version. ``start``
    and ``end`` are output ticks; ``offset`` is the exact rational ``b`` term
    of ``time_map(t′=a×t+b)`` in output ticks, quantized only with the final
    mapped coordinates.
    """

    model_config = ConfigDict(extra="forbid")

    op: Literal["temporal_edit"]
    action: Literal["move", "trim", "delete", "time_map"]
    target: EditTarget
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, gt=0)
    scale: float | None = Field(default=None, gt=0)
    offset: str = "0"
    ripple: Literal["none", "forward"] = "none"
    source_policy: Literal["crop_1x"] | None = None

    @model_validator(mode="after")
    def _operation_arguments(self) -> TemporalEdit:
        try:
            offset = Fraction(self.offset)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError("time_map offset must be an exact rational tick value") from exc
        if self.action == "move" and self.start is None:
            raise ValueError("move needs a target output start")
        if self.action == "trim" and (self.start is None or self.end is None):
            raise ValueError("trim needs an output subrange")
        if self.action == "time_map" and self.scale is None:
            raise ValueError("time_map needs a positive scale")
        if self.action != "trim" and self.end is not None:
            raise ValueError(f"{self.action} does not take an end")
        if self.action != "time_map" and (self.scale is not None or offset):
            raise ValueError("scale/offset belong only to time_map")
        if self.action not in {"move", "trim"} and self.start is not None:
            raise ValueError(f"{self.action} does not take a start")
        if self.action not in {"trim", "time_map"} and self.source_policy is not None:
            raise ValueError("source_policy belongs only to trim/time_map")
        return self


class ClipEntityWrite(BaseModel):
    """完整的 Clip 及其所属 Track 标识。CompositionContent 中 Clip 没有父指针，所以外层只用 track_id 指定位置；clip 本身与最终持久化的实体逐字节一致。"""

    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(min_length=1, max_length=64)
    clip: Clip


class EntityWrites(BaseModel):
    """Declarative whole-entity writes against one working Composition.

    There is no operation vocabulary or execution order in the payload. An
    existing stable id is updated, a fresh id is added, and the remove lists
    delete entities. The server applies one atomic batch and validates the
    complete resulting Composition.
    """

    model_config = ConfigDict(extra="forbid")

    scenes: list[Scene] = Field(default_factory=list, max_length=64)
    tracks: list[Track] = Field(default_factory=list, max_length=64)
    clips: list[ClipEntityWrite] = Field(default_factory=list, max_length=256)
    transitions: list[Transition] = Field(default_factory=list, max_length=64)
    remove_scene_ids: list[str] = Field(default_factory=list, max_length=64)
    remove_track_ids: list[str] = Field(default_factory=list, max_length=64)
    remove_clip_ids: list[str] = Field(default_factory=list, max_length=256)
    remove_transition_ids: list[str] = Field(default_factory=list, max_length=64)

    def has_changes(self) -> bool:
        return any(
            getattr(self, field)
            for field in (
                "scenes", "tracks", "clips", "transitions",
                "remove_scene_ids", "remove_track_ids", "remove_clip_ids",
                "remove_transition_ids",
            )
        )


def _entity_list(container: dict, key: str) -> list:
    value = container.get(key)
    if value is None:
        value = []
        container[key] = value
    if not isinstance(value, list):
        raise EditError(f"{key} must be an array before entity writes can apply")
    return value


def _upsert_raw(items: list, entity: dict, id_key: str) -> None:
    entity_id = entity[id_key]
    for index, current in enumerate(items):
        if isinstance(current, dict) and current.get(id_key) == entity_id:
            items[index] = copy.deepcopy(entity)
            return
    items.append(copy.deepcopy(entity))


def _reject_duplicate_ids(writes: EntityWrites) -> None:
    groups = (
        ("scene", [item.scene_id for item in writes.scenes], writes.remove_scene_ids),
        ("track", [item.track_id for item in writes.tracks], writes.remove_track_ids),
        ("clip", [item.clip.clip_id for item in writes.clips], writes.remove_clip_ids),
        ("transition", [item.transition_id for item in writes.transitions], writes.remove_transition_ids),
    )
    for kind, ids, removals in groups:
        if len(ids) != len(set(ids)):
            raise EditError(f"a {kind} may be written only once per batch")
        if len(removals) != len(set(removals)):
            raise EditError(f"a {kind} may be removed only once per batch")
        if set(ids) & set(removals):
            raise EditError(f"a {kind} cannot be written and removed in the same batch")
    track_clip_ids = [
        clip.clip_id for track in writes.tracks for clip in track.clips
    ]
    if len(track_clip_ids) != len(set(track_clip_ids)):
        raise EditError("a Clip may appear in only one complete Track write per batch")
    track_clips = set(track_clip_ids)
    clip_writes = {item.clip.clip_id for item in writes.clips}
    if track_clips & clip_writes:
        raise EditError("a Clip in a complete Track write cannot also be written separately")
    if track_clips & set(writes.remove_clip_ids):
        raise EditError("a Clip in a complete Track write cannot also be removed separately")
    if set(writes.remove_track_ids) & {item.track_id for item in writes.clips}:
        raise EditError("a Clip cannot be written into a Track removed by the same batch")


def apply_entity_writes_raw(content: dict, writes: EntityWrites) -> dict:
    """Apply complete final entities to raw working JSON without field patches.

    Raw input is intentional: even a first draft with schema errors remains
    correctable at entity granularity. Structural errors in the containers
    themselves fail closed; no malformed parent is silently discarded.
    """
    if not isinstance(content, dict):
        raise EditError("the working Composition must be a JSON object")
    _reject_duplicate_ids(writes)
    candidate = copy.deepcopy(content)
    scenes = _entity_list(candidate, "scenes")
    timeline = candidate.get("timeline")
    if timeline is None:
        timeline = {}
        candidate["timeline"] = timeline
    if not isinstance(timeline, dict):
        raise EditError("timeline must be an object before entity writes can apply")
    tracks = _entity_list(timeline, "tracks")
    transitions = _entity_list(timeline, "transitions")

    def clip_location(clip_id: str) -> tuple[dict, dict] | None:
        for track in tracks:
            if not isinstance(track, dict):
                continue
            for clip in track.get("clips") or []:
                if isinstance(clip, dict) and clip.get("clip_id") == clip_id:
                    return track, clip
        return None

    affected_scenes: set[str] = set()
    for track in writes.tracks:
        affected_scenes.update(
            str(clip.scene_id) for clip in track.clips if clip.scene_id is not None
        )
        for clip in track.clips:
            old_clip = clip_location(clip.clip_id)
            if old_clip is not None and old_clip[1].get("scene_id") is not None:
                affected_scenes.add(str(old_clip[1]["scene_id"]))
        old = next((item for item in tracks if isinstance(item, dict) and item.get("track_id") == track.track_id), None)
        if old is not None:
            affected_scenes.update(
                str(clip.get("scene_id")) for clip in old.get("clips") or []
                if isinstance(clip, dict) and clip.get("scene_id") is not None
            )
    for item in writes.clips:
        if item.clip.scene_id is not None:
            affected_scenes.add(item.clip.scene_id)
        old = clip_location(item.clip.clip_id)
        if old is not None and old[1].get("scene_id") is not None:
            affected_scenes.add(str(old[1]["scene_id"]))
    for clip_id in writes.remove_clip_ids:
        old = clip_location(clip_id)
        if old is not None and old[1].get("scene_id") is not None:
            affected_scenes.add(str(old[1]["scene_id"]))

    for track in tracks:
        if not isinstance(track, dict) or track.get("track_id") not in set(writes.remove_track_ids):
            continue
        affected_scenes.update(
            str(clip.get("scene_id")) for clip in track.get("clips") or []
            if isinstance(clip, dict) and clip.get("scene_id") is not None
        )
    for transition in transitions:
        if not isinstance(transition, dict) or transition.get("transition_id") not in set(writes.remove_transition_ids):
            continue
        for clip_id in (transition.get("from_clip_id"), transition.get("to_clip_id")):
            location = clip_location(str(clip_id)) if clip_id is not None else None
            if location is not None and location[1].get("scene_id") is not None:
                affected_scenes.add(str(location[1]["scene_id"]))

    remove_transitions = set(writes.remove_transition_ids)
    transitions[:] = [
        item for item in transitions
        if not isinstance(item, dict) or item.get("transition_id") not in remove_transitions
    ]
    remove_clips = set(writes.remove_clip_ids)
    for track in tracks:
        if not isinstance(track, dict):
            continue
        clips = track.get("clips")
        if isinstance(clips, list):
            clips[:] = [
                clip for clip in clips
                if not isinstance(clip, dict) or clip.get("clip_id") not in remove_clips
            ]
    remove_tracks = set(writes.remove_track_ids)
    tracks[:] = [
        track for track in tracks
        if not isinstance(track, dict) or track.get("track_id") not in remove_tracks
    ]
    remove_scenes = set(writes.remove_scene_ids)
    scenes[:] = [
        scene for scene in scenes
        if not isinstance(scene, dict) or scene.get("scene_id") not in remove_scenes
    ]

    # A complete Track owns its complete Clip list. Contained stable ids move
    # globally, rather than leaving a second copy in their previous Track.
    track_clips = {
        clip.clip_id for track in writes.tracks for clip in track.clips
    }
    for existing in tracks:
        if not isinstance(existing, dict):
            continue
        clips = existing.get("clips")
        if isinstance(clips, list):
            clips[:] = [
                clip for clip in clips
                if not isinstance(clip, dict) or clip.get("clip_id") not in track_clips
            ]
    for track in writes.tracks:
        _upsert_raw(tracks, track.model_dump(mode="json"), "track_id")
    for item in writes.clips:
        target = next(
            (track for track in tracks if isinstance(track, dict) and track.get("track_id") == item.track_id),
            None,
        )
        if target is None:
            raise EditError(f"track {item.track_id} does not exist")
        target_clips = _entity_list(target, "clips")
        for track in tracks:
            if not isinstance(track, dict):
                continue
            clips = track.get("clips")
            if isinstance(clips, list):
                clips[:] = [
                    clip for clip in clips
                    if not isinstance(clip, dict) or clip.get("clip_id") != item.clip.clip_id
                ]
        target_clips.append(item.clip.model_dump(mode="json"))
    for transition in writes.transitions:
        _upsert_raw(transitions, transition.model_dump(mode="json"), "transition_id")
        for clip_id in (transition.from_clip_id, transition.to_clip_id):
            location = clip_location(clip_id)
            if location is not None and location[1].get("scene_id") is not None:
                affected_scenes.add(str(location[1]["scene_id"]))

    for scene in scenes:
        if isinstance(scene, dict) and scene.get("scene_id") in affected_scenes:
            scene["visual_description"] = None
    # A complete Scene write is applied last so its fresh visual_description
    # wins over deterministic invalidation in the same atomic batch.
    for scene in writes.scenes:
        _upsert_raw(scenes, scene.model_dump(mode="json"), "scene_id")
    return candidate


def apply_entity_writes(
    content: CompositionContent,
    writes: EntityWrites,
) -> CompositionContent:
    return CompositionContent.model_validate(
        apply_entity_writes_raw(content.model_dump(mode="json"), writes)
    )


Op = Annotated[
    SetSettings
    | TemporalEdit
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
    | RemoveClip
    | SplitClip
    | SetTransition
    | RemoveTransition,
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


def replace_text_ops(clip: Clip, text: str) -> list[Op]:
    """Replace one native Text Clip while preserving its animation targets."""
    if not isinstance(clip.object, TextObject) or (
        clip.object.caption is not None
        and not isinstance(clip.object.caption, SourceCaptionDerivation)
    ):
        raise EditError("set_text supports native Text Clips and upload-ASR captions")
    if clip.object.text == text:
        return []
    from app.editing.animation import derive_text_parts

    animations = copy.deepcopy(clip.animations)
    for animation in animations:
        target = animation.text_part
        if target is None:
            continue
        previous = derive_text_parts(clip.object.text, target.kind)
        following = derive_text_parts(text, target.kind)
        positions = {part.part_id: index for index, part in enumerate(previous)}
        indexes = [positions.get(part_id) for part_id in target.part_ids]
        if any(index is None or index >= len(following) for index in indexes):
            raise TextAnimationTargetLost(
                "the new text no longer contains the animated text parts; "
                "apply a preset after changing it"
            )
        animation.text_part = target.model_copy(
            update={"part_ids": [following[index].part_id for index in indexes]}
        )
    return [
        UpdateClip(
            op="update_clip",
            clip_id=clip.clip_id,
            object=clip.object.model_copy(update={"text": text}),
            animations=animations,
        )
    ]



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


def _apply_temporal_in_place(content: CompositionContent, op: TemporalEdit) -> None:
    """Route legacy and generic temporal ops through the same pure candidate."""
    from app.editing.temporal import apply_temporal_edit

    updated = apply_temporal_edit(content, op)
    content.settings = updated.settings
    content.sources = updated.sources
    content.scenes = updated.scenes
    content.timeline = updated.timeline


def _apply_one(content: CompositionContent, op: Op, bound_digests: dict[UUID, str]) -> None:
    """Apply one op in place. ``bound_digests`` maps snapshot_id → digest as
    resolved from the snapshot rows by the store (the version pins THAT
    digest, never a caller-supplied one)."""
    if isinstance(op, TemporalEdit):
        _apply_temporal_in_place(content, op)
    elif isinstance(op, SetSettings):
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
            members = [
                clip for track in content.timeline.tracks for clip in track.clips
                if clip.scene_id == scene.scene_id
            ]
            if any(
                clip.range.start < op.range.start or clip.range.end > op.range.end
                for clip in members
            ):
                raise EditError("a populated Scene's new range must contain every owning Clip")
            scene.range = op.range
    elif isinstance(op, MoveScene):
        _apply_temporal_in_place(content, TemporalEdit(
            op="temporal_edit", action="move",
            target=EditTarget(kind="scene", id=op.scene_id), start=op.start,
        ))
    elif isinstance(op, RemoveScene):
        _apply_temporal_in_place(content, TemporalEdit(
            op="temporal_edit", action="delete",
            target=EditTarget(kind="scene", id=op.scene_id),
        ))
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
    elif isinstance(op, SetTransition):
        content.timeline.transitions = [t for t in content.timeline.transitions
                                       if t.transition_id != op.transition.transition_id]
        content.timeline.transitions.append(copy.deepcopy(op.transition))
        for clip_id in (op.transition.from_clip_id, op.transition.to_clip_id):
            _invalidate_visual_description(content, _find_clip(content, clip_id).scene_id)
    elif isinstance(op, RemoveTransition):
        content.timeline.transitions = [t for t in content.timeline.transitions if t.transition_id != op.transition_id]
    elif isinstance(op, SplitClip):
        from app.editing.temporal import resolve_temporal_target, slice_clip

        target = _find_clip(content, op.clip_id)
        resolved = resolve_temporal_target(
            content, EditTarget(kind="clip", id=target.clip_id), action="split"
        )
        members = [target] + [
            clip for track in content.timeline.tracks for clip in track.clips
            if clip.clip_id != target.clip_id and clip.clip_id in resolved.clip_ids
        ]
        for clip in members:
            _invalidate_visual_description(content, clip.scene_id)
            left = slice_clip(content, clip, TimeRange(start=clip.range.start, end=op.at))
            right = slice_clip(content, clip, TimeRange(start=op.at, end=clip.range.end))
            token = uuid5(NAMESPACE_URL, f"split:{op.new_clip_id}:{clip.clip_id}").hex
            right.clip_id = op.new_clip_id if clip is target else f"clp_{token}"
            right.object.object_id = op.new_object_id if clip is target else f"obj_{token}"
            for animation in right.animations:
                animation.animation_id = uuid5(NAMESPACE_URL, f"split:{token}:{animation.animation_id}").hex
                animation.target_object_id = right.object.object_id
            if clip.linked_group_id:
                right.linked_group_id = uuid5(NAMESPACE_URL, f"split-group:{op.new_clip_id}").hex
            clip.range, clip.source, clip.animations = left.range, left.source, left.animations
            track = next(track for track in content.timeline.tracks if clip in track.clips)
            track.clips.append(right)
            for transition in content.timeline.transitions:
                if transition.from_clip_id == clip.clip_id:
                    transition.from_clip_id = right.clip_id
    elif isinstance(op, RemoveClip):
        _apply_temporal_in_place(content, TemporalEdit(
            op="temporal_edit", action="delete",
            target=EditTarget(kind="clip", id=op.clip_id),
        ))
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
