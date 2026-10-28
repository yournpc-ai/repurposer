"""Compile a CompositionVersion into a video-spec (VIDEO_PROJECT §11).

The spec is the immutable render input: JSON only, QUANTIZED integer frames,
resolved immutable source/font identities and per-file content digests. URL
absolutization remains the pipeline dispatch seam. TextParts and stagger are
expanded here, so the renderer never re-derives text identity or timing.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction
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
    GeneratorObject,
    ImageObject,
    ShapeObject,
    SpeechObject,
    TextObject,
    VideoObject,
    WebObject,
    speech_text_digest,
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
    if isinstance(obj, ShapeObject):
        return {
            "kind": "shape",
            "object_id": obj.object_id,
            "shape": obj.shape,
            "layout": obj.layout.model_dump(mode="json"),
            "fill": obj.fill,
            "stroke": obj.stroke,
            "stroke_width": obj.stroke_width,
            "corner_radius": obj.corner_radius,
            "path": obj.path,
            "transform": obj.transform.model_dump(mode="json"),
            "opacity": obj.opacity,
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
    if isinstance(obj, VideoObject):
        return {
            "kind": "video",
            "object_id": obj.object_id,
            "layout": obj.layout.model_dump(mode="json"),
            "fit": obj.fit,
            "transform": obj.transform.model_dump(mode="json"),
            "opacity": obj.opacity,
            "gain_db": obj.gain_db,
            "muted": obj.muted,
        }
    if isinstance(obj, GeneratorObject):
        common = {
            "object_id": obj.object_id,
            "layout": obj.layout.model_dump(mode="json"),
            "fit": obj.fit,
            "transform": obj.transform.model_dump(mode="json"),
            "opacity": obj.opacity,
        }
        if obj.runtime == "image-v1":
            return {"kind": "image", **common}
        return {
            "kind": "video",
            **common,
            "gain_db": -60.0,
            "muted": True,
        }
    if isinstance(obj, AudioObject):
        return {"kind": "audio", "object_id": obj.object_id, "gain_db": obj.gain_db}
    raise CompileError(f"unsupported object kind {obj.kind!r}")


def _prepared_speech(clip: Clip, speech_media: dict[str, dict]) -> dict:
    speech = clip.object
    assert isinstance(speech, SpeechObject)
    prepared = speech_media.get(speech.object_id)
    if prepared is None:
        raise CompileError(f"clip {clip.clip_id}: speech audio is not prepared")
    request = prepared.get("request") or {}
    expected = {
        "speech_object_id": speech.object_id,
        "text_digest": speech_text_digest(speech.text),
        "provider": speech.provider,
        "model": speech.model,
        "voice_id": speech.voice_id,
        "language": speech.language,
        "gain_db": speech.gain_db,
        "window_ticks": clip.range.duration,
    }
    if any(request.get(key) != value for key, value in expected.items()):
        raise CompileError(f"clip {clip.clip_id}: prepared speech does not match the saved version")
    media = prepared.get("media") or {}
    if not media.get("storage_key") or len(str(media.get("digest") or "")) != 64:
        raise CompileError(f"clip {clip.clip_id}: prepared speech lacks immutable bytes")
    if float(prepared.get("duration_s") or 0) <= 0:
        raise CompileError(f"clip {clip.clip_id}: prepared speech has no decoded duration")
    return prepared


def _compile_speech_clip(
    clip: Clip, content: CompositionContent, speech_media: dict[str, dict]
) -> dict[str, Any]:
    speech = clip.object
    assert isinstance(speech, SpeechObject)
    prepared = _prepared_speech(clip, speech_media)
    settings = content.settings
    start = _quantize_frames(clip.range.start, content)
    reviewed_end = _quantize_frames(clip.range.end, content)
    audio_frames = max(
        1,
        math.ceil(
            float(prepared["duration_s"]) * settings.fps.num / settings.fps.den - 1e-9
        ),
    )
    if start + audio_frames > reviewed_end:
        raise CompileError(f"clip {clip.clip_id}: prepared audio exceeds its reviewed fixed window")
    return {
        "clip_id": clip.clip_id,
        "start_frame": start,
        "end_frame": start + audio_frames,
        "scene_id": clip.scene_id,
        "source": {
            "url": prepared["media"]["storage_key"],
            "digest": prepared["media"]["digest"],
            "start_frame": 0,
            "end_frame": audio_frames,
        },
        "object": {
            "kind": "audio",
            "object_id": speech.object_id,
            "gain_db": speech.gain_db,
        },
        "animations": _compile_animations(clip, content),
    }


def _reviewed_cues(normalized_text: str, cues: list[dict], reviewed_text: str) -> list[dict]:
    if normalized_text == reviewed_text:
        return [dict(cue) for cue in cues]
    positions: list[int] = []
    for match in re.finditer(r"\S+", reviewed_text):
        if positions:
            positions.append(match.start() - 1)
        positions.extend(range(match.start(), match.end()))
    if " ".join(reviewed_text.split()) != normalized_text or len(positions) != len(normalized_text):
        raise CompileError("speech whitespace mapping does not match its synthesis identity")
    mapped = []
    for cue in cues:
        begin, end = cue["text_begin"], cue["text_end"]
        original_begin = positions[begin]
        original_end = positions[end - 1] + 1
        text = reviewed_text[original_begin:original_end]
        if " ".join(text.split()) != " ".join(cue["text"].split()):
            raise CompileError("speech cue differs from the reviewed narration")
        mapped.append({**cue, "text": text, "text_begin": original_begin, "text_end": original_end})
    return mapped


def _compile_derived_caption(
    clip: Clip, content: CompositionContent, speech_media: dict[str, dict]
) -> list[dict[str, Any]]:
    obj = clip.object
    assert isinstance(obj, TextObject) and obj.caption is not None
    if clip.animations:
        raise CompileError(f"clip {clip.clip_id}: derived cue timing cannot carry old text animations")
    prepared = speech_media.get(obj.caption.speech_object_id)
    if prepared is None:
        raise CompileError(f"clip {clip.clip_id}: linked speech is not prepared")
    request = prepared.get("request") or {}
    if request.get("speech_object_id") != obj.caption.speech_object_id or request.get(
        "text_digest"
    ) != obj.caption.source_text_digest:
        raise CompileError(f"clip {clip.clip_id}: caption and prepared speech versions differ")
    cues = _reviewed_cues(prepared["normalized_text"], prepared["cues"], obj.text)
    settings = content.settings
    clip_start = _quantize_frames(clip.range.start, content)
    clip_end = _quantize_frames(clip.range.end, content)
    compiled = []
    previous_end = clip_start
    for index, cue in enumerate(cues):
        start_time = Fraction(str(cue["time_begin"])) * settings.fps.num / (1000 * settings.fps.den)
        end_time = Fraction(str(cue["time_end"])) * settings.fps.num / (1000 * settings.fps.den)
        start = clip_start + math.floor(start_time)
        end = clip_start + math.ceil(end_time)
        start = max(start, previous_end)
        if end <= start:
            end = start + 1
        if start < clip_start or end > clip_end:
            raise CompileError(f"clip {clip.clip_id}: a derived caption escapes its fixed window")
        cue_object = obj.model_copy(
            update={
                "object_id": f"{obj.object_id}:cue:{index}",
                "text": cue["text"],
                "caption": None,
            }
        )
        compiled.append({
            "clip_id": f"{clip.clip_id}:cue:{index}",
            "start_frame": start,
            "end_frame": end,
            "scene_id": clip.scene_id,
            "source": None,
            "object": _compile_object(clip.model_copy(update={"object": cue_object})),
            "animations": [],
        })
        previous_end = end
    if not compiled:
        raise CompileError(f"clip {clip.clip_id}: prepared speech has no caption cues")
    return compiled


def _compile_clip(
    clip: Clip,
    content: CompositionContent,
    snapshots: dict[UUID, dict],
    generator_media: dict[str, dict],
    speech_media: dict[str, dict],
) -> dict[str, Any]:
    if isinstance(clip.object, SpeechObject):
        return _compile_speech_clip(clip, content, speech_media)
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
    if isinstance(clip.object, GeneratorObject):
        prepared = generator_media.get(clip.object.object_id)
        if prepared is None or prepared.get("program_digest") != clip.object.program_digest():
            raise CompileError(
                f"clip {clip.clip_id}: generator media is not prepared for this exact program"
            )
        media = prepared.get("media") or {}
        if not media.get("storage_key") or len(str(media.get("digest") or "")) != 64:
            raise CompileError(f"clip {clip.clip_id}: generator media lacks immutable bytes")
        out["source"] = {
            "url": media["storage_key"],
            "digest": media["digest"],
        }
        if clip.object.runtime == "drawing-v1":
            out["source"].update({
                "start_frame": 0,
                "end_frame": out["end_frame"] - out["start_frame"],
            })
    elif clip.source is not None:
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
            source_start = ticks_to_frames(
                clip.source.source_range.start,
                SOURCE_TIMEBASE,
                settings.fps.num,
                settings.fps.den,
            )
            source["start_frame"] = source_start
            if isinstance(clip.object, VideoObject):
                # Quantize once, then preserve the exact 1× output duration.
                # Independently rounding source start/end can otherwise add or
                # drop a frame and desynchronize the coupled original audio.
                source["end_frame"] = source_start + out["end_frame"] - out["start_frame"]
            else:
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
    generator_media: dict[str, dict] | None = None,
    speech_media: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Compile validated content into the renderer-neutral spec dict."""
    settings = content.settings
    generator_media = generator_media or {}
    speech_media = speech_media or {}
    total_ticks = max(
        (clip.range.end for track in content.timeline.tracks for clip in track.clips),
        default=0,
    )
    if total_ticks <= 0:
        raise CompileError("nothing to render: the timeline has no clips")
    tracks = []
    for track in content.timeline.tracks:
        clips = []
        for clip in sorted(track.clips, key=lambda item: item.range.start):
            if (
                isinstance(clip.object, TextObject)
                and clip.object.caption is not None
                and clip.object.caption.state == "derived"
            ):
                clips.extend(_compile_derived_caption(clip, content, speech_media))
            else:
                clips.append(_compile_clip(clip, content, snapshots, generator_media, speech_media))
        tracks.append(
            {
                "track_id": track.track_id,
                "kind": track.kind,
                "role": track.role,
                "order": track.order,
                "clips": clips,
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
