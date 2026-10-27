"""Compile a CompositionVersion into a video-spec (VIDEO_PROJECT §11).

The spec is the immutable render input: JSON only, QUANTIZED integer frames,
resolved immutable source/font identities and per-file content digests. URL
absolutization remains the pipeline dispatch seam. TextParts and stagger are
expanded here, so the renderer never re-derives text identity or timing.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.editing.animation import derive_text_part_families, derive_text_parts
from app.editing.fonts import font_resources
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    CompositionContent,
    Easing,
    ImageObject,
    TextObject,
    WebObject,
)
from app.editing.timing import SOURCE_TIMEBASE, ticks_to_frames

SPEC_FORMAT = 1


class CompileError(ValueError):
    """Content that passed validation but cannot compile is a contract bug."""


def _quantize_frames(ticks: int, content: CompositionContent) -> int:
    settings = content.settings
    return ticks_to_frames(ticks, settings.timebase, settings.fps.num, settings.fps.den)


def _compile_easing(easing: Easing) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": easing.kind}
    if easing.params is not None:
        out["params"] = list(easing.params)
    return out


def _compile_animation(
    anim: Animation,
    content: CompositionContent,
    *,
    text_part_id: str | None = None,
    shift: int = 0,
) -> dict[str, Any]:
    keyframes: list[dict[str, Any]] = []
    seen_frames: set[int] = set()
    for kf in sorted(anim.keyframes, key=lambda item: item.at):
        at = _quantize_frames(kf.at + shift, content)
        if at in seen_frames:
            raise CompileError(f"animation {anim.animation_id}: keyframes collapse at frame {at}")
        seen_frames.add(at)
        keyframes.append(
            {
                "at": at,
                "value": list(kf.value) if isinstance(kf.value, tuple) else kf.value,
                "easing": _compile_easing(kf.easing),
            }
        )
    animation_id = (
        anim.animation_id if text_part_id is None else f"{anim.animation_id}:{text_part_id}"
    )
    return {
        "animation_id": animation_id,
        "target_object_id": anim.target_object_id,
        "target_text_part_id": text_part_id,
        "property": anim.property,
        "keyframes": keyframes,
    }


def _compile_animations(clip: Clip, content: CompositionContent) -> list[dict[str, Any]]:
    compiled: list[dict[str, Any]] = []
    for anim in clip.animations:
        if anim.text_part is None:
            compiled.append(_compile_animation(anim, content))
            continue
        if not isinstance(clip.object, TextObject):
            raise CompileError(f"animation {anim.animation_id}: TextPart target on non-text object")
        parts = {
            part.part_id: part for part in derive_text_parts(clip.object.text, anim.text_part.kind)
        }
        selected = [parts[part_id] for part_id in anim.text_part.part_ids]
        selected.sort(key=lambda part: part.text_range.start)
        for index, part in enumerate(selected):
            compiled.append(
                _compile_animation(
                    anim,
                    content,
                    text_part_id=part.part_id,
                    shift=index * anim.text_part.stagger,
                )
            )
    return compiled


def _compile_object(clip: Clip) -> dict[str, Any]:
    obj = clip.object
    if isinstance(obj, TextObject):
        kinds = {anim.text_part.kind for anim in clip.animations if anim.text_part is not None}
        return {
            "kind": "text",
            "object_id": obj.object_id,
            "text": obj.text,
            "layout": obj.layout.model_dump(mode="json"),
            "style": obj.style.model_dump(mode="json"),
            "transform": obj.transform.model_dump(mode="json"),
            "opacity": obj.opacity,
            "segmentation_version": obj.segmentation_version,
            "layout_version": obj.layout_version,
            "parts": [
                part.model_dump(mode="json") for part in derive_text_part_families(obj.text, kinds)
            ],
        }
    if isinstance(obj, ImageObject):
        return {
            "kind": "image",
            "object_id": obj.object_id,
            "layout": obj.layout.model_dump(mode="json"),
            "fit": obj.fit,
            "transform": obj.transform.model_dump(mode="json"),
            "opacity": obj.opacity,
        }
    if isinstance(obj, WebObject):
        return {
            "kind": "web",
            "object_id": obj.object_id,
            "view_id": obj.view_id,
            "layout": obj.layout.model_dump(mode="json"),
            "fit": obj.fit,
            "transform": obj.transform.model_dump(mode="json"),
            "opacity": obj.opacity,
        }
    if isinstance(obj, AudioObject):
        return {"kind": "audio", "object_id": obj.object_id, "gain_db": obj.gain_db}
    raise CompileError(f"unsupported object kind {obj.kind!r}")


def _compile_clip(
    clip: Clip, content: CompositionContent, snapshots: dict[UUID, dict]
) -> dict[str, Any]:
    settings = content.settings
    out: dict[str, Any] = {
        "clip_id": clip.clip_id,
        "start_frame": _quantize_frames(clip.range.start, content),
        "end_frame": _quantize_frames(clip.range.end, content),
        "scene_id": clip.scene_id,
        "source": None,
        "object": _compile_object(clip),
        "animations": _compile_animations(clip, content),
    }
    if clip.source is not None:
        facts = snapshots.get(clip.source.snapshot_id)
        if facts is None or facts["digest"] != clip.source.snapshot_digest:
            raise CompileError(
                f"clip {clip.clip_id}: source snapshot {clip.source.snapshot_id} "
                "is not resolved with a matching digest"
            )
        source: dict[str, Any] = {"url": facts["storage_key"], "digest": facts["digest"]}
        if isinstance(clip.object, WebObject):
            views = (facts.get("meta") or {}).get("views") or []
            view = next(
                (item for item in views if item.get("view_id") == clip.object.view_id), None
            )
            if view is None:
                raise CompileError(
                    f"clip {clip.clip_id}: unresolved web view {clip.object.view_id}"
                )
            source = {"url": view["storage_key"], "digest": view["digest"]}
        if clip.source.source_range is not None:
            source["start_frame"] = ticks_to_frames(
                clip.source.source_range.start,
                SOURCE_TIMEBASE,
                settings.fps.num,
                settings.fps.den,
            )
            source["end_frame"] = ticks_to_frames(
                clip.source.source_range.end,
                SOURCE_TIMEBASE,
                settings.fps.num,
                settings.fps.den,
            )
        out["source"] = source
    return out


def _compile_fonts(content: CompositionContent) -> list[dict[str, Any]]:
    resources: dict[tuple[str, str, int], dict[str, Any]] = {}
    for track in content.timeline.tracks:
        for clip in track.clips:
            if not isinstance(clip.object, TextObject):
                continue
            font = clip.object.style.font
            for resource in font_resources(font.font_id, font.digest, {clip.object.style.weight}):
                key = (resource["font_id"], resource["family"], resource["weight"])
                resources[key] = resource
    return [resources[key] for key in sorted(resources)]


def compile_video_spec(
    content: CompositionContent,
    snapshots: dict[UUID, dict],
    *,
    composition_id: UUID,
    version_id: UUID,
    content_digest: str,
) -> dict[str, Any]:
    """Compile validated content into the renderer-neutral spec dict."""
    settings = content.settings
    total_ticks = max(
        (clip.range.end for track in content.timeline.tracks for clip in track.clips),
        default=0,
    )
    if total_ticks <= 0:
        raise CompileError("nothing to render: the timeline has no clips")
    tracks = []
    for track in content.timeline.tracks:
        tracks.append(
            {
                "track_id": track.track_id,
                "kind": track.kind,
                "role": track.role,
                "order": track.order,
                "clips": [
                    _compile_clip(clip, content, snapshots)
                    for clip in sorted(track.clips, key=lambda item: item.range.start)
                ],
            }
        )
    return {
        "family": "video",
        "format": SPEC_FORMAT,
        "fps": {"num": settings.fps.num, "den": settings.fps.den},
        "width": settings.width,
        "height": settings.height,
        "background": settings.background,
        "sample_rate": settings.sample_rate,
        "duration_frames": _quantize_frames(total_ticks, content),
        "fonts": _compile_fonts(content),
        "tracks": tracks,
        "provenance": {
            "composition_id": str(composition_id),
            "composition_version_id": str(version_id),
            "content_digest": content_digest,
        },
    }
