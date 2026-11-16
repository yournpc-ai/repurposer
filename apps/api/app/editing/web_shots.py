"""Expand frozen multi-state web views into ordinary scenes and edit ops.

This is the first CapturePlan consumer. It adds no Object kind and no renderer
branch: selected focus uses the existing camera math, before/after uses the
existing crossfade, and plate/cutout uses ordinary native animations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.editing.grounding import camera_keyframes, resolve_focus
from app.editing.timing import seconds_to_ticks


@dataclass(frozen=True)
class ViewFact:
    snapshot_id: UUID
    snapshot_digest: str
    view_id: str
    width: int
    height: int
    elements: list[dict[str, Any]]
    heading: str
    page: int
    state_id: str | None = None
    artifact_role: str | None = None
    paired_view_id: str | None = None
    target_id: str | None = None
    target_element_id: str | None = None
    route: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    source_y: int = 0
    css_width: int | None = None
    css_height: int | None = None
    device_scale_factor: float = 1.0
    region_text: str | None = None
    region_text_truncated: bool | None = None
    region_visually_truncated: bool | None = None
    source_url: str | None = None


def _view(views: list[Any], state_id: str, role: str) -> Any:
    matches = [
        view for view in views
        if view.state_id == state_id and (view.artifact_role or "view") == role
    ]
    if len(matches) != 1:
        raise ValueError(f"CapturePlan needs exactly one {state_id}/{role} view")
    return matches[0]


def _keyframe(at: int, value: Any, easing: str = "linear") -> dict[str, Any]:
    ease: dict[str, Any] = {"kind": easing, "params": None}
    if easing == "cubic_bezier":
        ease = {"kind": easing, "params": [0.16, 1.0, 0.3, 1.0]}
    return {"at": at, "value": value, "easing": ease}


def _animation(animation_id: str, object_id: str, prop: str, keyframes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "animation_id": animation_id,
        "target_object_id": object_id,
        "text_part": None,
        "property": prop,
        "keyframes": keyframes,
    }


def _source(view: Any) -> dict[str, Any]:
    return {
        "snapshot_id": str(view.snapshot_id),
        "snapshot_digest": view.snapshot_digest,
        "source_range": None,
    }


def _object(view: Any, object_id: str, layout: dict[str, Any], fit: str = "cover") -> dict[str, Any]:
    return {
        "kind": "web",
        "object_id": object_id,
        "view_id": view.view_id,
        "layout": layout,
        "fit": fit,
        "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
        "opacity": 1.0,
    }


def _cutout_layout(
    plate: Any,
    canvas: tuple[int, int],
    *,
    plate_layout: dict[str, float] | None = None,
    plate_fit: str = "cover",
) -> dict[str, float]:
    """Map the frozen target box through the plate's actual destination box.

    A paired cutout contains only the target pixels. It must inherit the
    plate's cover/contain scale and crop offsets; stretching it to the plate's
    whole layout would magnify the element into an unrelated close-up.
    """
    target_id = plate.target_element_id
    target = next((element for element in plate.elements if str(element.get("id")) == target_id), None)
    if target is None:
        raise ValueError("the blank plate's frozen target element is absent")
    left = float(target["x"]) - float(target["w"]) / 2
    top = float(target["y"]) - float(target["h"]) / 2
    if min(left, top, float(target["w"]), float(target["h"])) <= 0:
        raise ValueError("the plate/cutout target has no positive visible box")
    destination = plate_layout or {
        "x": 0.0, "y": 0.0, "width": float(canvas[0]), "height": float(canvas[1]),
    }
    scale_x = float(destination["width"]) / plate.width
    scale_y = float(destination["height"]) / plate.height
    scale = (max if plate_fit == "cover" else min)(scale_x, scale_y)
    offset_x = float(destination["x"]) + (float(destination["width"]) - plate.width * scale) / 2
    offset_y = float(destination["y"]) + (float(destination["height"]) - plate.height * scale) / 2
    return {
        "x": offset_x + left * plate.width * scale,
        "y": offset_y + top * plate.height * scale,
        "width": float(target["w"]) * plate.width * scale,
        "height": float(target["h"]) * plate.height * scale,
    }


def insert_capture_shot_ops(
    ops: list[dict[str, Any]],
    views: list[Any],
    *,
    canvas: tuple[int, int],
    timebase: int,
    fps_num: int,
    fps_den: int,
) -> int:
    """Insert the three real-state scenes before the launch film's end card.

    Returns the added output ticks so the existing music bed is built against
    the real final duration. All source/layout references are resolved here;
    missing required artifacts fail the whole design before the write door.
    """
    selected = _view(views, "selected", "view")
    before = _view(views, "before", "view")
    after = _view(views, "after", "view")
    plate = _view(views, "selected", "blank_plate")
    cutout = _view(views, "selected", "cutout")
    snapshots = {view.snapshot_id for view in (selected, before, after, plate, cutout)}
    if len(snapshots) != 1:
        raise ValueError("the three CapturePlan shots must share one web SourceSnapshot")
    if after.paired_view_id != before.view_id:
        raise ValueError("after-view must be paired with before-view")
    if plate.paired_view_id != selected.view_id or cutout.paired_view_id != selected.view_id:
        raise ValueError("plate and cutout must be paired with selected-view")
    if len({before.source_y, after.source_y}) != 1:
        raise ValueError("before/after views must retain the same measured scroll position")
    if len({(before.width, before.height), (after.width, after.height)}) != 1:
        raise ValueError("before/after views must have the same captured viewport pixels")
    target_ids = {selected.target_element_id, plate.target_element_id, cutout.target_element_id}
    if len(target_ids) != 1 or None in target_ids:
        raise ValueError("selected, plate and cutout must reference the same frozen element")
    for view in (selected, plate, cutout):
        if not any(str(element.get("id")) == view.target_element_id for element in view.elements):
            raise ValueError(f"view {view.view_id} lacks its selected element {view.target_element_id}")

    end_scene = next(
        (op for op in ops if op["op"] == "add_scene" and op["scene"]["scene_id"] == "scn_end"),
        None,
    )
    if end_scene is None:
        raise ValueError("the CapturePlan consumer needs its end scene")
    insert_at = int(end_scene["scene"]["range"]["start"])
    frame_ticks = seconds_to_ticks(fps_den / fps_num, timebase)

    def duration(seconds: float) -> int:
        return max(round(seconds_to_ticks(seconds, timebase) / frame_ticks), 1) * frame_ticks

    selected_ticks, before_ticks, after_ticks, plate_ticks = map(duration, (4.0, 3.0, 3.0, 4.0))
    added = selected_ticks + before_ticks + after_ticks + plate_ticks
    for op in ops:
        if op["op"] == "add_scene" and op["scene"]["scene_id"] == "scn_end":
            op["scene"]["range"]["start"] += added
            op["scene"]["range"]["end"] += added
        elif op["op"] == "add_clip" and op["clip"].get("scene_id") == "scn_end":
            op["clip"]["range"]["start"] += added
            op["clip"]["range"]["end"] += added
    # Move the end scene and its clips together: the write door requires every
    # Clip's Scene to exist at the moment the Clip op is applied.
    end_clip_ops = [
        op for op in ops if op["op"] == "add_clip" and op["clip"].get("scene_id") == "scn_end"
    ]
    ops.remove(end_scene)
    for op in end_clip_ops:
        ops.remove(op)

    snapshot_id = selected.snapshot_id
    if not any(op["op"] == "bind_source" and op.get("snapshot_id") == str(snapshot_id) for op in ops):
        ops.append({"op": "bind_source", "snapshot_id": str(snapshot_id)})
    if not any(op["op"] == "add_track" and op["track"]["track_id"] == "trk_web_cutout" for op in ops):
        ops.append({"op": "add_track", "track": {
            "track_id": "trk_web_cutout", "kind": "visual", "role": "main", "order": 99, "clips": [],
        }})

    full_layout = {"x": 0.0, "y": 0.0, "width": float(canvas[0]), "height": float(canvas[1])}
    cursor = insert_at

    def scene(key: str, ticks: int, intent: str, visual: str) -> tuple[str, int, int]:
        nonlocal cursor
        scene_id = f"scn_capture_{key}"
        start, end = cursor, cursor + ticks
        ops.append({"op": "add_scene", "scene": {
            "scene_id": scene_id,
            "range": {"start": start, "end": end},
            "intent": intent,
            "visual_description": visual,
            "speech_clip_ids": [],
        }})
        cursor = end
        return scene_id, start, end

    def clip(scene_id: str, start: int, end: int, key: str, view: Any, *,
             animations: list[dict[str, Any]] | None = None, layout: dict[str, Any] | None = None,
             track_id: str = "trk_web") -> str:
        clip_id = f"clp_capture_{key}"
        object_id = f"obj_capture_{key}"
        ops.append({"op": "add_clip", "track_id": track_id, "clip": {
            "clip_id": clip_id,
            "range": {"start": start, "end": end},
            "scene_id": scene_id,
            "source": _source(view),
            "object": _object(view, object_id, layout or full_layout),
            "animations": animations or [],
        }})
        return clip_id

    scene_id, start, end = scene(
        "selected", selected_ticks,
        "Focus the real selected webpage state",
        "The captured selected state pushes toward its measured subject element.",
    )
    focus = resolve_focus(selected.elements, selected.target_element_id)
    zoom, positions = camera_keyframes(
        focus, view_width=selected.width, view_height=selected.height,
        canvas_width=canvas[0], canvas_height=canvas[1], clip_ticks=selected_ticks,
        arrival_frac=0.45,
    )
    clip(scene_id, start, end, "selected", selected, animations=[
        _animation("anm_capture_selected_scale", "obj_capture_selected", "transform.scale", [
            _keyframe(0, 1.08), _keyframe(positions[1][0], zoom, "cubic_bezier"),
            _keyframe(selected_ticks, round(min(zoom * 1.01, 2.05), 3)),
        ]),
        _animation("anm_capture_selected_position", "obj_capture_selected", "transform.position", [
            _keyframe(at, [float(value[0]), float(value[1])], "cubic_bezier" if index == 1 else "linear")
            for index, (at, value) in enumerate(positions)
        ]),
    ])

    before_scene, before_start, before_end = scene(
        "before", before_ticks, "Show the genuine state before interaction",
        "The frozen populated view before the control is activated.",
    )
    before_clip = clip(before_scene, before_start, before_end, "before", before)
    after_scene, after_start, after_end = scene(
        "after", after_ticks, "Reveal the genuine state after interaction",
        "The independently recaptured and re-measured view after the real control action.",
    )
    after_clip = clip(after_scene, after_start, after_end, "after", after)
    ops.append({"op": "set_transition", "transition": {
        "transition_id": "trs_capture_before_after",
        "from_clip_id": before_clip,
        "to_clip_id": after_clip,
        "kind": "crossfade",
        "duration": seconds_to_ticks(0.6, timebase),
        "alignment": "center",
    }})

    plate_scene, plate_start, plate_end = scene(
        "plate", plate_ticks, "Rebuild the selected element over its real blank plate",
        "The visibility-hidden plate stays aligned while the matching real cutout enters.",
    )
    clip(plate_scene, plate_start, plate_end, "plate", plate)
    entrance = min(seconds_to_ticks(0.8, timebase), plate_ticks)
    clip(
        plate_scene, plate_start, plate_end, "cutout", cutout,
        layout=_cutout_layout(plate, canvas), track_id="trk_web_cutout",
        animations=[
            _animation("anm_capture_cutout_opacity", "obj_capture_cutout", "opacity", [
                _keyframe(0, 0.0), _keyframe(entrance, 1.0, "cubic_bezier"),
            ]),
            _animation("anm_capture_cutout_position", "obj_capture_cutout", "transform.position", [
                _keyframe(0, [0.0, 36.0]), _keyframe(entrance, [0.0, 0.0], "cubic_bezier"),
            ]),
            _animation("anm_capture_cutout_scale", "obj_capture_cutout", "transform.scale", [
                _keyframe(0, 0.94), _keyframe(entrance, 1.0, "cubic_bezier"),
            ]),
        ],
    )
    ops.append(end_scene)
    ops.extend(end_clip_ops)
    return added
