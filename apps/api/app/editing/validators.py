"""Whole-candidate validation for CompositionContent (VIDEO_PROJECT §2.2).

The write door applies the full op batch and then validates the COMPLETE
candidate here — one seat for identity, reference, time and layout law.
Pure: snapshot facts arrive as plain data (the store resolves the rows), so
this module never touches the DB.
"""

from __future__ import annotations

import re
from uuid import UUID

from app.editing.animation import derive_text_parts
from app.editing.fonts import LAYOUT_VERSION, SEGMENTATION_VERSION, font_resources
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    CompositionContent,
    GeneratorObject,
    ImageObject,
    MotionBlockObject,
    ShapeObject,
    SourceCaptionDerivation,
    SpeechObject,
    TextObject,
    TimeRange,
    VideoObject,
    WebObject,
    speech_text_digest,
)
from app.editing.timing import source_ticks_to_output_ticks, ticks_to_frames

SnapshotFacts = dict[UUID, dict]


class ValidationProblems(list[str]):
    """Messages stay backward-compatible; indexed metadata feeds correction."""

    def __init__(self):
        super().__init__()
        self.issues: dict[int, dict] = {}


class ContentValidationError(ValueError):
    """The candidate version breaks content law; the batch never lands."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        metadata = getattr(problems, "issues", {})
        self.issues = []
        for index, problem in enumerate(self.problems):
            issue = dict(metadata.get(index, {}))
            issue.setdefault("loc", [])
            issue.setdefault("type", "content_validation")
            issue.setdefault("msg", problem)
            self.issues.append(issue)
        super().__init__("; ".join(self.problems))


def _fail(
    problems: list[str],
    msg: str,
    *,
    entity: dict | None = None,
    relation: str | None = None,
    field_path: list[str | int] | None = None,
    operation_path: list[str | int] | None = None,
) -> None:
    index = len(problems)
    problems.append(msg)
    if isinstance(problems, ValidationProblems) and (
        entity or relation or field_path or operation_path
    ):
        problems.issues[index] = {
            "loc": [], "type": relation or "content_validation", "msg": msg,
            **({"relation": relation} if relation else {}),
            **({"entity": entity} if entity else {}),
            **({"field_path": field_path} if field_path else {}),
            **({"operation_path": operation_path} if operation_path else {}),
        }


def _validate_capture_snapshot(snapshot_id: UUID, facts: dict, problems: list[str]) -> None:
    """Validate every captured view without requiring failed peers to exist."""
    del snapshot_id
    meta = facts.get("meta") or {}
    plan = meta.get("capture_plan") or {}
    views = meta.get("views") or []
    by_id = {str(view.get("view_id")): view for view in views}
    states = {str(state.get("state_id")): state for state in plan.get("states") or []}
    artifacts = list(plan.get("artifacts") or [])
    for view in views:
        view_id = str(view.get("view_id"))
        matches = [
            artifact for artifact in artifacts
            if (
                str(artifact.get("artifact_id") or "") == view_id
                or (
                    artifact.get("output_id") is not None
                    and artifact.get("output_id") == view.get("output_id")
                )
            )
            and artifact.get("state_id") == view.get("state_id")
            and artifact.get("role") == view.get("artifact_role")
        ]
        if len(matches) != 1:
            _fail(problems, f"web view {view_id}: captured output has no unique plan lineage")
            continue
        artifact = matches[0]
        if view.get("paired_view_id") != artifact.get("paired_view_id"):
            _fail(problems, f"web view {view_id}: paired view differs from its plan")
        if not view.get("storage_key") or not re.fullmatch(r"[0-9a-f]{64}", str(view.get("digest") or "")):
            _fail(problems, f"web view {view_id}: captured output lacks immutable bytes/digest")
        state = states.get(str(view.get("state_id") or ""))
        if state is None or view.get("actions") != state.get("actions"):
            _fail(problems, f"web view {view_id}: route/action provenance does not match its state")
        if not view.get("route") or not isinstance(view.get("page_height"), int):
            _fail(problems, f"web view {view_id}: route or post-state page height is absent")
        target_id = view.get("target_element_id")
        if target_id:
            target = next((e for e in view.get("elements") or [] if str(e.get("id")) == str(target_id)), None)
            if target is None:
                _fail(problems, f"web view {view_id}: selected element {target_id} is absent")
            elif not target.get("css_box") or not target.get("pixel_box"):
                _fail(problems, f"web view {view_id}: selected element lacks post-state CSS/pixel boxes")
            if not isinstance(view.get("region_text"), str) or not isinstance(view.get("region_text_truncated"), bool):
                _fail(problems, f"web view {view_id}: selected region text/truncation fact is absent")
        pair_id = view.get("paired_view_id")
        if not pair_id:
            continue
        pair = by_id.get(str(pair_id))
        if pair is None:
            continue
        if view.get("route") != pair.get("route") or view.get("source_y") != pair.get("source_y"):
            _fail(problems, f"web view {view_id}: paired views differ in route or measured scroll")
        if (view.get("css_width"), view.get("css_height")) != (pair.get("css_width"), pair.get("css_height")):
            _fail(problems, f"web view {view_id}: paired views differ in CSS viewport")
        if view.get("artifact_role") in {"blank_plate", "cutout"}:
            if view.get("state_id") != pair.get("state_id"):
                _fail(problems, f"web view {view_id}: plate/cutout pair crosses states")
            if view.get("device_scale_factor") != pair.get("device_scale_factor"):
                _fail(problems, f"web view {view_id}: plate/cutout pair crosses capture scales")
            if target_id:
                own = next((e for e in view.get("elements") or [] if str(e.get("id")) == str(target_id)), None)
                other = next((e for e in pair.get("elements") or [] if str(e.get("id")) == str(target_id)), None)
                if own and other and (own.get("css_box") != other.get("css_box") or own.get("full_css_box") != other.get("full_css_box")):
                    _fail(problems, f"web view {view_id}: plate/cutout coordinates differ from the populated view")


def _validate_component_source(obj: GeneratorObject, clip_id: str, problems: list[str]) -> None:
    # Python owns source size/schema, declared parameters, output and basic
    # structure only. TSX syntax/capability diagnostics belong to the single
    # controlled runner; matching words across JSX text or comments here is
    # neither correct validation nor a security boundary.
    if obj.project is not None:
        # The complete schema, file digests, imports and resource identities are
        # pinned before this whole-candidate check; TS capability diagnostics
        # remain owned by the controlled runner.
        return
    code = obj.code or ""
    if not re.search(r"\bexport\s+default\b", code):
        _fail(problems, f"clip {clip_id}: remotion-project needs a default component export")
    for key, value in obj.parameters.items():
        if isinstance(value, str) and re.search(r"https?://|\bdata:", value, re.IGNORECASE):
            _fail(problems, f"clip {clip_id}: component parameter {key!r} is not a fixed resource")


def _validate_clip_source(
    clip: Clip, content: CompositionContent, snapshots: SnapshotFacts, problems: list[str]
) -> None:
    obj = clip.object
    src = clip.source
    if isinstance(obj, GeneratorObject):
        if src is not None:
            _fail(problems, f"clip {clip.clip_id}: generator sources are prepared, not bound media")
        if obj.producer in {"draw-2d", "remotion-project"}:
            expected_ticks = obj.output.duration_frames * content.settings.timebase // obj.output.fps
            if (
                expected_ticks * obj.output.fps != obj.output.duration_frames * content.settings.timebase
                or expected_ticks != clip.range.duration
            ):
                _fail(
                    problems,
                    f"clip {clip.clip_id}: program output frames/fps must exactly match its output window",
                )
            if obj.producer == "remotion-project":
                _validate_component_source(obj, clip.clip_id, problems)
                if obj.project is not None:
                    for resource in obj.project.resources:
                        binding = next(
                            (b for b in content.sources if b.snapshot_id == resource.snapshot_id), None
                        )
                        facts = snapshots.get(resource.snapshot_id)
                        if (
                            binding is None
                            or binding.snapshot_digest != resource.snapshot_digest
                            or facts is None
                            or facts.get("digest") != resource.snapshot_digest
                            or facts.get("kind") != "image"
                        ):
                            _fail(
                                problems,
                                f"clip {clip.clip_id}: resource {resource.path!r} lacks its exact bound image snapshot",
                            )
        return
    if isinstance(obj, MotionBlockObject):
        if src is not None:
            _fail(problems, f"clip {clip.clip_id}: motion_block objects bind images via resources, not clip.source")
        for resource in obj.resources:
            binding = next(
                (b for b in content.sources if b.snapshot_id == resource.snapshot_id), None
            )
            facts = snapshots.get(resource.snapshot_id)
            if (
                binding is None
                or binding.snapshot_digest != resource.snapshot_digest
                or facts is None
                or facts.get("digest") != resource.snapshot_digest
                or facts.get("kind") != "image"
            ):
                _fail(
                    problems,
                    f"clip {clip.clip_id}: motion_block resource {resource.path!r} lacks its exact bound image snapshot",
                )
        return
    if isinstance(obj, (TextObject, ShapeObject)):
        if src is not None:
            _fail(problems, f"clip {clip.clip_id}: {obj.kind} objects take no media source")
        if isinstance(obj, ShapeObject):
            return
        if obj.segmentation_version != SEGMENTATION_VERSION:
            _fail(problems, f"clip {clip.clip_id}: unsupported text segmentation version")
        if obj.layout_version != LAYOUT_VERSION:
            _fail(problems, f"clip {clip.clip_id}: unsupported text layout version")
        try:
            font_resources(obj.style.font.font_id, obj.style.font.digest, {obj.style.weight})
        except ValueError as exc:
            _fail(problems, f"clip {clip.clip_id}: {exc}")
        return
    if isinstance(obj, SpeechObject):
        if obj.alignment is None:
            if src is not None:
                _fail(problems, f"clip {clip.clip_id}: pending speech has no bound media source")
            return
        if src is None:
            _fail(problems, f"clip {clip.clip_id}: source-aligned speech requires its audio snapshot")
            return
        if (
            src.snapshot_id != obj.alignment.audio_snapshot_id
            or src.snapshot_digest != obj.alignment.audio_digest
        ):
            _fail(problems, f"clip {clip.clip_id}: speech alignment and audio snapshot differ")
    if src is None:
        _fail(problems, f"clip {clip.clip_id}: {obj.kind} objects require a source")
        return

    binding = next((b for b in content.sources if b.snapshot_id == src.snapshot_id), None)
    if binding is None:
        _fail(
            problems,
            f"clip {clip.clip_id}: source snapshot {src.snapshot_id} is not bound in this version",
        )
        return
    if binding.snapshot_digest != src.snapshot_digest:
        _fail(problems, f"clip {clip.clip_id}: source digest does not match the version binding")

    facts = snapshots.get(src.snapshot_id)
    if facts is None:
        _fail(problems, f"clip {clip.clip_id}: source snapshot {src.snapshot_id} does not exist")
        return
    if facts["digest"] != src.snapshot_digest:
        _fail(problems, f"clip {clip.clip_id}: source digest does not match the snapshot row")

    if isinstance(obj, (ImageObject, WebObject)):
        expected_kind = "web" if isinstance(obj, WebObject) else "image"
        if facts["kind"] != expected_kind:
            _fail(
                problems,
                f"clip {clip.clip_id}: {expected_kind} object bound to a {facts['kind']} snapshot",
            )
        if src.source_range is not None:
            _fail(problems, f"clip {clip.clip_id}: static sources must not carry source_range")
        if isinstance(obj, WebObject):
            views = (facts.get("meta") or {}).get("views") or []
            view = next((item for item in views if item.get("view_id") == obj.view_id), None)
            if view is None:
                _fail(
                    problems,
                    f"clip {clip.clip_id}: web view {obj.view_id} is absent "
                    "from the bound snapshot",
                )
            elif not view.get("storage_key") or len(str(view.get("digest", ""))) != 64:
                _fail(
                    problems, f"clip {clip.clip_id}: web view {obj.view_id} lacks immutable bytes"
                )
        return

    if isinstance(obj, (AudioObject, VideoObject)) or (
        isinstance(obj, SpeechObject) and obj.alignment is not None
    ):
        expected_kind = "video" if isinstance(obj, VideoObject) else "audio"
        if facts["kind"] != expected_kind:
            _fail(
                problems,
                f"clip {clip.clip_id}: {expected_kind} object bound to a {facts['kind']} snapshot",
            )
        if src.source_range is None:
            _fail(problems, f"clip {clip.clip_id}: {expected_kind} sources require a source_range",
                  entity={"clip_id": clip.clip_id}, field_path=["source", "source_range"])
            return
        duration = facts.get("duration_ticks")
        if duration is None:
            _fail(problems, f"clip {clip.clip_id}: source snapshot has no probed duration")
            return
        if src.source_range.end > duration:
            _fail(
                problems,
                f"clip {clip.clip_id}: source_range ends past the source's real duration "
                f"({src.source_range.end} > {duration} source ticks) — a 1× clip may not "
                "invent source media",
            )
        if isinstance(obj, SpeechObject):
            # Aligned clips and their word anchors quantize absolute source
            # positions before subtracting; use that same Clip-local window.
            source_len = source_ticks_to_output_ticks(
                src.source_range.end, content.settings.timebase
            ) - source_ticks_to_output_ticks(
                src.source_range.start, content.settings.timebase
            )
        else:
            source_len = source_ticks_to_output_ticks(
                src.source_range.duration, content.settings.timebase
            )
        if source_len != clip.range.duration:
            _fail(
                problems,
                f"clip {clip.clip_id}: source window ({source_len} ticks) and output window "
                f"({clip.range.duration} ticks) differ — only 1× mapping is supported; source uses SOURCE_TIMEBASE=90000 ticks/s",
                entity={"clip_id": clip.clip_id}, field_path=["source", "source_range"],
            )


def _quantized_keys_have_collisions(
    anim: Animation, content: CompositionContent, shift: int
) -> bool:
    settings = content.settings
    frames = [
        ticks_to_frames(kf.at + shift, settings.timebase, settings.fps.num, settings.fps.den)
        for kf in anim.keyframes
    ]
    return len(frames) != len(set(frames))


def _validate_animation(
    clip: Clip,
    anim: Animation,
    content: CompositionContent,
    problems: list[str],
    *,
    animation_index: int,
) -> None:
    obj = clip.object
    clip_ticks = clip.range.duration
    if anim.target_object_id != obj.object_id:
        _fail(
            problems,
            f"animation {anim.animation_id}: target {anim.target_object_id} is not an object "
            f"of its owning clip {clip.clip_id} (cross-clip targets never resolve)",
        )
    if anim.property == "audio.gain" and not isinstance(obj, (AudioObject, SpeechObject, VideoObject)):
        _fail(problems, f"animation {anim.animation_id}: audio.gain on a non-audio object")
    if anim.property == "path.reveal":
        if not isinstance(obj, ShapeObject) or obj.shape != "path" or not obj.path:
            _fail(
                problems,
                f"animation {anim.animation_id}: path.reveal requires a path shape with non-empty path data",
            )
        if anim.text_part is not None or anim.narration_anchor is not None:
            _fail(
                problems,
                f"animation {anim.animation_id}: path.reveal accepts only whole-object targets",
            )
    if anim.property in {
        "filter.blur", "text.letter_spacing", "text.color", "text.stroke_color",
        "text.weight", "text.stroke_width",
    } and not isinstance(obj, TextObject):
        _fail(problems, f"animation {anim.animation_id}: {anim.property} on a non-text object")
    if anim.property != "audio.gain" and isinstance(obj, (AudioObject, SpeechObject)):
        _fail(problems, f"animation {anim.animation_id}: visual property on an audio object")
    if anim.narration_anchor is not None:
        anchor = anim.narration_anchor
        caption = obj.caption if isinstance(obj, TextObject) else None
        if (
            caption is None
            or caption.state != "derived"
            or caption.narration_alignment_id != anchor.alignment_id
            or caption.narration_content_digest != anchor.content_digest
            or caption.speech_object_id != anchor.speech_object_id
        ):
            _fail(
                problems,
                f"animation {anim.animation_id}: narration anchor provenance does not match its derived caption",
            )
        if anim.text_part is None or anim.property not in {
            "transform.scale", "transform.position", "opacity", "filter.blur",
            "text.color", "text.stroke_color", "text.weight", "text.stroke_width",
        }:
            _fail(
                problems,
                f"animation {anim.animation_id}: narration anchors require a supported TextPart animation",
            )

    seen_at: set[int] = set()
    for keyframe_index, kf in enumerate(anim.keyframes):
        if kf.at in seen_at:
            _fail(problems, f"animation {anim.animation_id}: duplicate keyframe at {kf.at}")
        seen_at.add(kf.at)
        if kf.at > clip_ticks:
            _fail(
                problems,
                f"animation {anim.animation_id}: keyframe at {kf.at} is past the clip's "
                f"local duration ({clip_ticks})",
                entity={"clip_id": clip.clip_id, "animation_id": anim.animation_id},
                field_path=[
                    "animations", animation_index, "keyframes", keyframe_index, "at",
                ],
            )
        if anim.property == "transform.position":
            if not isinstance(kf.value, tuple):
                _fail(problems, f"animation {anim.animation_id}: transform.position needs [x, y]")
        elif anim.property in {"text.color", "text.stroke_color"}:
            if not isinstance(kf.value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", kf.value) is None:
                _fail(problems, f"animation {anim.animation_id}: {anim.property} needs #RRGGBB")
        else:
            if not isinstance(kf.value, (int, float)) or isinstance(kf.value, bool):
                _fail(problems, f"animation {anim.animation_id}: {anim.property} needs a scalar")
            elif anim.property == "opacity" and not 0 <= kf.value <= 1:
                _fail(problems, f"animation {anim.animation_id}: opacity out of [0, 1]")
            elif anim.property == "path.reveal" and not 0 <= kf.value <= 1:
                _fail(problems, f"animation {anim.animation_id}: path.reveal out of [0, 1]")
            elif anim.property == "transform.scale" and not 0 < kf.value <= 10:
                _fail(problems, f"animation {anim.animation_id}: scale out of (0, 10]")
            elif anim.property == "audio.gain" and not 0 <= kf.value <= 4:
                _fail(problems, f"animation {anim.animation_id}: gain out of [0, 4]")
            elif anim.property == "filter.blur" and not 0 <= kf.value <= 100:
                _fail(problems, f"animation {anim.animation_id}: blur out of [0, 100] px")
            elif anim.property == "text.letter_spacing" and not -0.2 <= kf.value <= 0.5:
                _fail(
                    problems,
                    f"animation {anim.animation_id}: letter spacing out of [-0.2, 0.5] em",
                )
            elif anim.property == "text.weight" and (
                int(kf.value) != kf.value or int(kf.value) not in {400, 500, 600, 700, 800, 900}
            ):
                _fail(problems, f"animation {anim.animation_id}: unsupported text weight")
            elif anim.property == "text.stroke_width" and not 0 <= kf.value <= 64:
                _fail(problems, f"animation {anim.animation_id}: text stroke width out of [0, 64]")
        if (
            anim.property in {"text.color", "text.stroke_color", "text.weight", "text.stroke_width"}
            and kf is not anim.keyframes[-1]
            and kf.easing.kind != "hold"
        ):
            _fail(problems, f"animation {anim.animation_id}: {anim.property} supports hold segments only")

    shifts = [0]
    if anim.text_part is not None:
        if not isinstance(obj, TextObject):
            _fail(problems, f"animation {anim.animation_id}: TextPart target on a non-text object")
            return
        target = anim.text_part
        if len(target.part_ids) != len(set(target.part_ids)):
            _fail(problems, f"animation {anim.animation_id}: duplicate TextPart target")
        parts = {part.part_id: part for part in derive_text_parts(obj.text, target.kind)}
        selected = [parts.get(part_id) for part_id in target.part_ids]
        missing = [part_id for part_id, part in zip(target.part_ids, selected) if part is None]
        if missing:
            _fail(
                problems,
                f"animation {anim.animation_id}: TextPart target(s) {missing} do not match the "
                "current text; re-target explicitly instead of remapping by index",
            )
            return
        ordered = sorted(
            (part for part in selected if part is not None), key=lambda p: p.text_range.start
        )
        shifts = [index * target.stagger for index in range(len(ordered))]
        for shift in shifts:
            if anim.keyframes and max(kf.at for kf in anim.keyframes) + shift > clip_ticks:
                _fail(
                    problems,
                    f"animation {anim.animation_id}: staggered keyframes exceed the clip window",
                )
    for shift in shifts:
        if _quantized_keys_have_collisions(anim, content, shift):
            _fail(
                problems,
                f"animation {anim.animation_id}: distinct keyframes collapse onto one output frame",
            )


def validate_content(content: CompositionContent, snapshots: SnapshotFacts) -> None:
    """Validate the COMPLETE candidate; raise ContentValidationError listing
    every violation found (one honest report, not the first failure)."""
    problems: list[str] = ValidationProblems()

    for binding in content.sources:
        facts = snapshots.get(binding.snapshot_id)
        if facts and facts.get("kind") == "web" and (facts.get("meta") or {}).get("capture_plan"):
            _validate_capture_snapshot(binding.snapshot_id, facts, problems)

    for label, ids in (
        ("snapshot", [str(b.snapshot_id) for b in content.sources]),
        ("scene", [s.scene_id for s in content.scenes]),
        ("track", [t.track_id for t in content.timeline.tracks]),
        ("clip", [c.clip_id for t in content.timeline.tracks for c in t.clips]),
        ("object", [c.object.object_id for t in content.timeline.tracks for c in t.clips]),
        (
            "animation",
            [
                a.animation_id
                for t in content.timeline.tracks
                for c in t.clips
                for a in c.animations
            ],
        ),
    ):
        dupes = {item for item in ids if ids.count(item) > 1}
        if dupes:
            _fail(problems, f"duplicate {label} ids: {sorted(dupes)}")

    if not content.timeline.tracks:
        _fail(problems, "a version needs at least one track")

    total_ticks = 0
    scene_ids = {scene.scene_id for scene in content.scenes}
    clips_by_id: dict[str, Clip] = {}

    for track in content.timeline.tracks:
        seen_orders = [item.order for item in content.timeline.tracks if item.kind == track.kind]
        if seen_orders.count(track.order) > 1:
            _fail(
                problems,
                f"track {track.track_id}: {track.kind} order {track.order} is not unique",
            )
        ordered = sorted(track.clips, key=lambda clip: (clip.range.start, clip.range.end))
        for previous, following in zip(ordered, ordered[1:]):
            if following.range.start < previous.range.end:
                _fail(
                    problems,
                    f"track {track.track_id}: clips {previous.clip_id} and {following.clip_id} "
                    "overlap on one track",
                    entity={
                        "track_id": track.track_id,
                        "clip_ids": [previous.clip_id, following.clip_id],
                        "clip_id": following.clip_id,
                    },
                    relation="same_track_overlap",
                    operation_path=["track_id"],
                )
        for clip in track.clips:
            clips_by_id[clip.clip_id] = clip
            total_ticks = max(total_ticks, clip.range.end)
            if track.kind == "audio" and not isinstance(clip.object, (AudioObject, SpeechObject)):
                _fail(problems, f"clip {clip.clip_id}: non-audio object on an audio track")
            if track.kind == "visual" and isinstance(clip.object, (AudioObject, SpeechObject)):
                _fail(problems, f"clip {clip.clip_id}: audio object on a visual track")
            if isinstance(clip.object, SpeechObject) and track.role != "dialogue":
                _fail(problems, f"clip {clip.clip_id}: speech requires a dialogue track")
            if isinstance(clip.object, TextObject) and clip.object.caption is not None:
                if track.kind != "visual" or track.role != "caption":
                    _fail(problems, f"clip {clip.clip_id}: derived captions require a visual caption track")
            if clip.scene_id is not None and clip.scene_id not in scene_ids:
                _fail(problems, f"clip {clip.clip_id}: scene {clip.scene_id} does not exist")
            _validate_clip_source(clip, content, snapshots, problems)
            part_kinds = {
                anim.text_part.kind for anim in clip.animations if anim.text_part is not None
            }
            if "word" in part_kinds and "grapheme" in part_kinds:
                _fail(
                    problems,
                    f"clip {clip.clip_id}: mixed word + grapheme TextPart hierarchy is unsupported",
                )
            seen_targets: set[tuple[str, str | None]] = set()
            for animation_index, anim in enumerate(clip.animations):
                part_ids = anim.text_part.part_ids if anim.text_part is not None else [None]
                for part_id in part_ids:
                    key = (anim.property, part_id)
                    if key in seen_targets:
                        _fail(
                            problems,
                            f"clip {clip.clip_id}: overlapping animations on "
                            f"{anim.target_object_id}.{anim.property} for TextPart {part_id}",
                        )
                    seen_targets.add(key)
                _validate_animation(
                    clip, anim, content, problems, animation_index=animation_index
                )

    speech_clips = {
        clip.object.object_id: clip
        for clip in clips_by_id.values()
        if isinstance(clip.object, SpeechObject)
    }
    for clip in clips_by_id.values():
        if not isinstance(clip.object, TextObject) or clip.object.caption is None:
            continue
        derivation = clip.object.caption
        if isinstance(derivation, SourceCaptionDerivation):
            fact = snapshots.get(derivation.snapshot_id) or {}
            if fact.get("kind") not in {"video", "audio"} or fact.get("digest") != derivation.snapshot_digest:
                _fail(problems, f"clip {clip.clip_id}: source caption identity is invalid")
                continue
            source_clip = next(
                (
                    candidate for candidate in clips_by_id.values()
                    if candidate.scene_id == clip.scene_id
                    and isinstance(candidate.object, (VideoObject, AudioObject))
                    and candidate.source is not None
                    and candidate.source.snapshot_id == derivation.snapshot_id
                ),
                None,
            )
            if source_clip is None or source_clip.source.source_range is None:
                _fail(problems, f"clip {clip.clip_id}: ASR caption has no source video window")
                continue
            source_range = source_clip.source.source_range
            if (
                derivation.source_range.start < source_range.start
                or derivation.source_range.end > source_range.end
            ):
                _fail(problems, f"clip {clip.clip_id}: ASR caption escapes its source video window")
            expected_start = source_clip.range.start + source_ticks_to_output_ticks(
                derivation.source_range.start - source_range.start,
                content.settings.timebase,
            )
            expected_end = source_clip.range.start + source_ticks_to_output_ticks(
                derivation.source_range.end - source_range.start,
                content.settings.timebase,
            )
            if clip.range != TimeRange(start=expected_start, end=expected_end):
                _fail(problems, f"clip {clip.clip_id}: ASR caption output time differs from its source window")
            if derivation.state == "derived" and derivation.source_text_digest != speech_text_digest(clip.object.text):
                _fail(problems, f"clip {clip.clip_id}: derived source caption has stale text identity")
            if fact.get("kind") == "audio" and derivation.alignment != "faster-whisper-source-v1" and (
                derivation.narration_alignment_id is None or derivation.narration_content_digest is None
            ):
                _fail(problems, f"clip {clip.clip_id}: narration caption lacks alignment provenance")
            continue
        speech_clip = speech_clips.get(derivation.speech_object_id)
        if speech_clip is None:
            _fail(problems, f"clip {clip.clip_id}: caption speech source does not exist")
            continue
        if clip.scene_id != speech_clip.scene_id:
            _fail(problems, f"clip {clip.clip_id}: caption and speech must belong to the same scene")
        if derivation.state == "derived" and derivation.text_start is None and clip.range != speech_clip.range:
            _fail(problems, f"clip {clip.clip_id}: derived sentence caption must share its speech window")
        speech = speech_clip.object
        assert isinstance(speech, SpeechObject)
        if derivation.alignment == "faster-whisper-script-v1":
            if (
                speech.alignment is None
                or derivation.narration_alignment_id != speech.alignment.alignment_id
                or derivation.narration_content_digest != speech.alignment.content_digest
            ):
                _fail(problems, f"clip {clip.clip_id}: caption and speech alignment provenance differ")
        elif speech.alignment is not None:
            _fail(problems, f"clip {clip.clip_id}: source-aligned speech has a TTS caption derivation")
        if derivation.state == "derived":
            if derivation.source_text_digest != speech_text_digest(speech.text):
                _fail(problems, f"clip {clip.clip_id}: derived caption has stale speech text identity")
            if derivation.text_start is None:
                primary_line = clip.object.text.split("\n", 1)[0]
                if clip.object.text != speech.text and primary_line != speech.text:
                    _fail(problems, f"clip {clip.clip_id}: derived caption does not match its speech text")
            else:
                text_end = derivation.text_end
                expected_span = (
                    speech.text[derivation.text_start:text_end]
                    if text_end is not None and text_end <= len(speech.text)
                    else None
                )
                primary_line = clip.object.text.split("\n", 1)[0]
                if (
                    derivation.alignment != "faster-whisper-script-v1"
                    or expected_span is None
                    or (clip.object.text != expected_span and primary_line != expected_span)
                ):
                    _fail(problems, f"clip {clip.clip_id}: caption phrase does not match its exact speech span")
                if clip.range.start < speech_clip.range.start or clip.range.end > speech_clip.range.end:
                    _fail(problems, f"clip {clip.clip_id}: caption phrase escapes its speech window")

    for scene in content.scenes:
        if total_ticks and scene.range.end > total_ticks:
            _fail(
                problems,
                f"scene {scene.scene_id}: range ends past the timeline's last clip",
            )
        for ref in scene.speech_clip_ids:
            speech_clip = clips_by_id.get(ref)
            if speech_clip is None:
                _fail(problems, f"scene {scene.scene_id}: speech clip {ref} does not exist")
            elif not isinstance(speech_clip.object, SpeechObject):
                _fail(problems, f"scene {scene.scene_id}: clip {ref} is not a SpeechClip")
            elif speech_clip.scene_id != scene.scene_id:
                _fail(problems, f"scene {scene.scene_id}: speech clip {ref} belongs to another scene")
            elif (
                speech_clip.range.start < scene.range.start
                or speech_clip.range.end > scene.range.end
            ):
                _fail(problems, f"scene {scene.scene_id}: speech clip {ref} escapes the reviewed scene window")

    if content.timeline.transitions:
        from app.editing.transitions import transition_windows
        try:
            transition_windows(content, snapshots)
        except ValueError as exc:
            _fail(problems, str(exc))
    if total_ticks == 0:
        _fail(problems, "a version needs at least one clip")
    if problems:
        raise ContentValidationError(problems)
