"""Aligned narration expansion for native Composition scenes and captions."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import TypeAdapter

from app.editing.alignment import NarrationPayload
from app.editing.animation import derive_text_parts
from app.editing.audio import MusicBed, instantiate_music_bed
from app.editing.edits import Op, apply_ops
from app.editing.presets import expand_preset
from app.editing.schemas import GENERATOR_FPS, CompositionContent, NarrationAlignmentRef
from app.editing.timing import seconds_to_ticks, source_ticks_to_output_ticks

_OP_BATCH = TypeAdapter(list[Op])
_EASE_OUT = (0.16, 1.0, 0.3, 1.0)


class TemplateError(ValueError):
    pass


def _ease(kind: str) -> dict[str, Any]:
    if kind == "linear":
        return {"kind": "linear", "params": None}
    if kind == "hold":
        return {"kind": "hold", "params": None}
    return {"kind": "cubic_bezier", "params": list(_EASE_OUT)}


def _kf(at: int, value: Any, easing: str = "linear") -> dict[str, Any]:
    return {"at": at, "value": value, "easing": _ease(easing)}


_MG_FONT_SIZES = {"medium": 64, "large": 96, "hero": 140}


def _mg_animations(
    enter: str,
    *,
    object_id: str,
    text: str,
    clip_ticks: int,
    timebase: int,
    prefix: str,
) -> list[dict[str, Any]]:
    """The MG entrance vocabulary (bounded presets, code-expanded — TextPart
    targets derive from the clip's own text)."""
    def t(seconds: float) -> int:
        return seconds_to_ticks(seconds, timebase)

    if enter == "fade":
        return [
            {
                "animation_id": f"{prefix}_opacity",
                "target_object_id": object_id,
                "text_part": None,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(t(0.6), clip_ticks), 1.0)],
            }
        ]
    if enter == "rise":
        return [
            {
                "animation_id": f"{prefix}_opacity",
                "target_object_id": object_id,
                "text_part": None,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(t(0.5), clip_ticks), 1.0)],
            },
            {
                "animation_id": f"{prefix}_position",
                "target_object_id": object_id,
                "text_part": None,
                "property": "transform.position",
                "keyframes": [_kf(0, [0.0, 64.0]), _kf(min(t(0.9), clip_ticks), [0.0, 0.0], "ease")],
            },
        ]
    if enter in ("lines", "words", "graphemes"):
        kind: Literal["line", "word", "grapheme"]
        if enter == "lines":
            kind, stagger_s, dur_s = "line", 0.45, 0.8
        elif enter == "words":
            kind, stagger_s, dur_s = "word", 0.14, 0.3
        else:
            kind, stagger_s, dur_s = "grapheme", 0.06, 0.24
        parts = derive_text_parts(text, kind)
        target = {
            "kind": kind,
            "part_ids": [part.part_id for part in parts],
            "stagger": t(stagger_s),
        }
        return [
            {
                "animation_id": f"{prefix}_{kind}_opacity",
                "target_object_id": object_id,
                "text_part": target,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(t(dur_s), clip_ticks), 1.0)],
            }
        ]
    raise TemplateError(f"unknown MG entrance {enter!r}")


def _mg_shape_animations(
    motion: str, *, object_id: str, clip_ticks: int, timebase: int, prefix: str
) -> list[dict[str, Any]]:
    at = min(seconds_to_ticks(0.8, timebase), clip_ticks)

    def animation(property_name: str, values: list[Any]) -> dict[str, Any]:
        return {
            "animation_id": f"{prefix}_{property_name.replace('.', '_')}",
            "target_object_id": object_id,
            "text_part": None,
            "property": property_name,
            "keyframes": [
                _kf(0, values[0]),
                _kf(at, values[1], "ease"),
            ],
        }

    if motion == "fade":
        return [animation("opacity", [0.0, 1.0])]
    if motion == "rise":
        return [animation("transform.position", [[0.0, 80.0], [0.0, 0.0]])]
    if motion == "scale":
        return [animation("transform.scale", [0.2, 1.0])]
    if motion == "rotate":
        return [animation("transform.rotation", [0.0, 90.0])]
    raise TemplateError(f"unknown shape motion {motion!r}")




def instantiate_aligned_narration(
    direction: Any,
    *,
    payload: NarrationPayload,
    alignment: NarrationAlignmentRef,
    snapshot: Any,
    aspect: str = "16:9",
    background: str | None = None,
    music_bed: MusicBed | None = None,
) -> list[dict[str, Any]]:
    """READY sentence facts → native titles, fixed source audio and word anchors."""
    canvas = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    timebase = 90000
    background = background or direction.background or "#0B1020"
    sentence_by_id = {sentence.sentence_id: sentence for sentence in payload.sentences}
    groups = [
        [sentence_by_id[sentence_id] for sentence_id in scene.sentence_ids]
        for scene in direction.scenes
    ]
    total_ticks = source_ticks_to_output_ticks(payload.duration_ticks, timebase)
    ops: list[dict[str, Any]] = [
        {
            "op": "set_settings",
            "settings": {
                "width": canvas[0], "height": canvas[1],
                "fps": {"num": 30, "den": 1}, "timebase": timebase,
                "sample_rate": 48000, "channels": 2, "background": background,
            },
        },
        {"op": "bind_source", "snapshot_id": str(snapshot.id)},
        {
            "op": "add_track",
            "track": {"track_id": "trk_title", "kind": "visual", "role": "title", "order": 0, "clips": []},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_dialogue", "kind": "audio", "role": "dialogue", "order": 1 if music_bed is not None else 0, "clips": []},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_caption", "kind": "visual", "role": "caption", "order": 1, "clips": []},
        },
    ]
    shape_lanes = max((len(scene.shapes) for scene in direction.scenes), default=0)
    if shape_lanes:
        ops[2]["track"]["order"] = shape_lanes
        ops[4]["track"]["order"] = shape_lanes + 1
        for lane in range(1, shape_lanes + 1):
            ops.insert(
                2 + lane,
                {
                    "op": "add_track",
                    "track": {
                        "track_id": "trk_shape" if lane == 1 else f"trk_shape_{lane}",
                        "kind": "visual", "role": "effect", "order": lane - 1, "clips": [],
                    },
                },
            )

    if any(scene.generator is not None for scene in direction.scenes):
        for op in ops:
            if op["op"] == "add_track" and op["track"]["kind"] == "visual":
                op["track"]["order"] += 1
        ops.insert(2, {
            "op": "add_track",
            "track": {
                "track_id": "trk_aligned_generator", "kind": "visual", "role": "main",
                "order": 0, "clips": [],
            },
        })

    for index, (scene, sentences) in enumerate(zip(direction.scenes, groups, strict=True), start=1):
        scene_id = f"scn_aligned_{index}"
        scene_start = 0 if index == 1 else source_ticks_to_output_ticks(sentences[0].start_tick, timebase)
        scene_end = (
            source_ticks_to_output_ticks(groups[index][0].start_tick, timebase)
            if index < len(groups)
            else total_ticks
        )
        if scene_end <= scene_start:
            raise TemplateError(f"aligned scene {scene_id} has no positive output window")
        speech_clip_ids = [f"clp_aligned_{sentence.sentence_id}_speech" for sentence in sentences]
        ops.append({
            "op": "add_scene",
            "scene": {
                "scene_id": scene_id,
                "range": {"start": scene_start, "end": scene_end},
                "intent": scene.intent,
                "visual_description": scene.visual_description,
                "speech_clip_ids": speech_clip_ids,
            },
        })
        text = "\n".join(line.strip() for line in scene.lines if line.strip())
        font_size = _MG_FONT_SIZES[scene.size]
        block_height = max(len(scene.lines), 1) * font_size * 1.15
        object_id = f"obj_aligned_{index}"
        ops.append({
            "op": "add_clip",
            "track_id": "trk_title",
            "clip": {
                "clip_id": f"clp_aligned_{index}",
                "range": {"start": scene_start, "end": scene_end},
                "scene_id": scene_id,
                "source": None,
                "object": {
                    "kind": "text", "object_id": object_id, "text": text,
                    "layout": {
                        "x": 120.0,
                        "y": max(120.0, (canvas[1] - block_height) / 2),
                        "width": float(canvas[0] - 240), "height": block_height * 1.25,
                    },
                    "style": {
                        "font_size": font_size, "color": scene.color or "#F8FAFC",
                        "background": None, "weight": 700, "align": scene.align, "line_height": 1.15,
                    },
                    "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                    "opacity": 1.0,
                },
                "animations": _mg_animations(
                    scene.enter, object_id=object_id, text=text,
                    clip_ticks=scene_end - scene_start, timebase=timebase,
                    prefix=f"anm_aligned_{index}",
                ) + ([{
                    "animation_id": f"anm_aligned_{index}_drift",
                    "target_object_id": object_id, "text_part": None,
                    "property": "transform.scale",
                    "keyframes": [
                        _kf(0, 1.0 if scene.drift == "push_in" else 1.035),
                        _kf(scene_end - scene_start, 1.035 if scene.drift == "push_in" else 1.0),
                    ],
                }] if scene.drift != "none" else []),
            },
        })

        if scene.generator is not None:
            generator_object_id = f"obj_aligned_{index}_generator"
            duration_frames = (scene_end - scene_start) * GENERATOR_FPS // timebase
            if duration_frames < 1:
                raise TemplateError(f"aligned scene {scene_id} is too short for its Generator")
            generator_end = scene_start + duration_frames * (timebase // GENERATOR_FPS)
            generator = scene.generator
            source_fields: dict[str, Any]
            if generator.producer == "remotion-project":
                assert generator.project is not None
                source_fields = {
                    "producer": "remotion-project",
                    "project": generator.project.model_dump(mode="json"),
                    "parameters": {},
                }
            else:
                assert generator.code is not None
                source_fields = {
                    "producer": "draw-2d",
                    "code": generator.code,
                    "parameters": generator.parameters,
                }
            ops.append({
                "op": "add_clip",
                "track_id": "trk_aligned_generator",
                "clip": {
                    "clip_id": f"clp_aligned_{index}_generator",
                    "range": {"start": scene_start, "end": generator_end},
                    "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "generator", "object_id": generator_object_id,
                        **source_fields,
                        "output": {
                            "width": canvas[0], "height": canvas[1],
                            "fps": GENERATOR_FPS,
                            "duration_frames": duration_frames,
                            "background": background,
                        },
                        "layout": {
                            "x": 0.0, "y": 0.0,
                            "width": float(canvas[0]), "height": float(canvas[1]),
                        },
                        "fit": "cover",
                        "transform": {
                            "x": 0.0, "y": 0.0, "scale": 1.0,
                            "rotation": 0.0, "origin": "center",
                        },
                        "opacity": 1.0,
                    },
                    "animations": [],
                },
            })

        for sentence in sentences:
            start = source_ticks_to_output_ticks(sentence.start_tick, timebase)
            end = source_ticks_to_output_ticks(sentence.end_tick, timebase)
            speech_object_id = f"obj_aligned_{sentence.sentence_id}_speech"
            source = {
                "snapshot_id": str(snapshot.id), "snapshot_digest": snapshot.digest,
                "source_range": {"start": sentence.start_tick, "end": sentence.end_tick},
            }
            ops.append({
                "op": "add_clip", "track_id": "trk_dialogue",
                "clip": {
                    "clip_id": f"clp_aligned_{sentence.sentence_id}_speech",
                    "range": {"start": start, "end": end}, "scene_id": scene_id,
                    "source": source,
                    "object": {
                        "kind": "speech", "object_id": speech_object_id, "text": sentence.text,
                        "provider": None, "model": None, "voice_id": None,
                        "language": direction.language or "und", "gain_db": 0.0,
                        "alignment": alignment.model_dump(mode="json"),
                    },
                    "animations": [],
                },
            })

        for shape_index, shape in enumerate(scene.shapes, start=1):
            shape_object_id = f"obj_aligned_{index}_shape_{shape_index}"
            ops.append({
                "op": "add_clip",
                "track_id": "trk_shape" if shape_index == 1 else f"trk_shape_{shape_index}",
                "clip": {
                    "clip_id": f"clp_aligned_{index}_shape_{shape_index}",
                    "range": {"start": scene_start, "end": scene_end}, "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "shape", "object_id": shape_object_id,
                        "shape": shape.shape,
                        "layout": {
                            "x": shape.x * canvas[0], "y": shape.y * canvas[1],
                            "width": shape.width * canvas[0], "height": shape.height * canvas[1],
                        },
                        "fill": shape.fill, "stroke": None, "stroke_width": 0.0,
                        "corner_radius": shape.corner_radius if shape.shape == "rect" else 0.0,
                        "path": None,
                        "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                        "opacity": shape.opacity,
                    },
                    "animations": _mg_shape_animations(
                        shape.motion, object_id=shape_object_id,
                        clip_ticks=scene_end - scene_start, timebase=timebase,
                        prefix=f"anm_aligned_{index}_shape_{shape_index}",
                    ),
                },
            })
    bound = {snapshot.id: snapshot.digest}
    candidate = apply_ops(
        CompositionContent(settings={"width": canvas[0], "height": canvas[1]}),
        _OP_BATCH.validate_python(ops),
        bound,
    )
    caption_ops = expand_preset("caption-phrases", candidate, {
        "payload": payload,
        "alignment": alignment,
        "cue": "sentence",
    })
    ops.extend(op.model_dump(mode="json", exclude_unset=True) for op in caption_ops)
    candidate = apply_ops(candidate, caption_ops, bound)
    for sentence in payload.sentences:
        semantics = sentence.semantics
        for word_id in (semantics.emphasis_word_ids if semantics is not None else []):
            impact_ops = expand_preset("text-impact", candidate, {
                "narration": {
                    "payload": payload,
                    "alignment": alignment,
                    "word_id": word_id,
                },
            })
            ops.extend(op.model_dump(mode="json", exclude_unset=True) for op in impact_ops)
            candidate = apply_ops(candidate, impact_ops, bound)
    if music_bed is not None:
        ops.extend(instantiate_music_bed(music_bed, total_ticks=total_ticks, timebase=timebase))
    return ops


