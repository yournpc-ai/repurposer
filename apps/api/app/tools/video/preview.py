"""Read-only, bounded CompositionVersion Scrub previews.

The browser and the editor receive an explicit time window or one isolated
object. Compilation resolves fixed sources and requested local Generator media.
"""
from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from fractions import Fraction
from typing import Any
from uuid import UUID

import av
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.schemas import (
    CaptionDerivation,
    CompositionContent,
    GeneratorObject,
    SpeechObject,
    TextObject,
    TimeRange,
    Timeline,
)
from app.editing.store import content_of, get_video_version, snapshot_facts
from app.editing.temporal import slice_clip, ticks_to_frames
from app.editing.video_spec import CompileError, compile_video_spec
from app.models.schemas import (
    MediaInput,
    MediaInputType,
    VideoObjectScrubTarget,
    VideoScrubTarget,
    VideoRangeScrubTarget,
    VideoSegmentScrubTarget,
)


class ScrubTargetError(ValueError):
    """A model/client target that is not a bounded part of this version."""


def project_video_scrub(
    content: CompositionContent,
    target: VideoScrubTarget | VideoRangeScrubTarget,
    *,
    allow_outside_target: bool = False,
    allow_complete: bool = False,
) -> tuple[CompositionContent, dict[str, Any]]:
    """Project a saved content value into a normalized local preview timeline.

    ``slice_clip`` owns source windows and frame-accurate animation sampling;
    this function only chooses the bounded target and rebases output time to 0.
    The saved CompositionContent is never mutated.
    """
    owners = [
        (track, clip)
        for track in content.timeline.tracks
        for clip in track.clips
    ]
    isolated = isinstance(target, VideoObjectScrubTarget)
    if isinstance(target, VideoObjectScrubTarget):
        matches = [(track, clip) for track, clip in owners if clip.object.object_id == target.object_id]
        if len(matches) != 1:
            raise ScrubTargetError("the scrub object_id must name exactly one Object in this version")
        clip = matches[0][1]
        window = deepcopy(clip.range)
        selected = {clip.clip_id}
    elif isinstance(target, (VideoSegmentScrubTarget, VideoRangeScrubTarget)):
        if isinstance(target, VideoRangeScrubTarget):
            bounds = TimeRange(start=0, end=max((c.range.end for _, c in owners), default=0))
        elif target.scene_id is not None:
            scene = next((row for row in content.scenes if row.scene_id == target.scene_id), None)
            if scene is None:
                raise ScrubTargetError("the scrub scene_id does not exist in this version")
            bounds = scene.range
        else:
            clip = next((row for _, row in owners if row.clip_id == target.clip_id), None)
            if clip is None:
                raise ScrubTargetError("the scrub clip_id does not exist in this version")
            bounds = clip.range
        timebase = content.settings.timebase
        window = TimeRange(
            start=round(target.start_seconds * timebase),
            end=round(target.end_seconds * timebase),
        )
        if not allow_outside_target and (window.start < bounds.start or window.end > bounds.end):
            if isinstance(target, VideoRangeScrubTarget):
                raise ScrubTargetError(f"Preview must stay within composition seconds 0–{bounds.end / timebase:g}.")
            raise ScrubTargetError("the scrub window must stay inside its named Scene or Clip")
        timeline_start = min((clip.range.start for _, clip in owners), default=0)
        timeline_end = max((clip.range.end for _, clip in owners), default=0)
        if not (allow_complete or isinstance(target, VideoRangeScrubTarget)) and window.start <= timeline_start and window.end >= timeline_end:
            raise ScrubTargetError("a pre-production Scrub cannot contain the complete video")
        selected = {
            clip.clip_id
            for _, clip in owners
            if clip.range.start < window.end and window.start < clip.range.end
        }
    else:
        raise ScrubTargetError("unknown Scrub target")
    if not selected and not isinstance(target, VideoRangeScrubTarget):
        raise ScrubTargetError("the scrub window contains no clips")

    tracks = []
    settings = content.settings
    for track in content.timeline.tracks:
        if selected and not any(clip.clip_id in selected for clip in track.clips):
            continue
        clips = []
        for clip in track.clips:
            if clip.clip_id not in selected:
                continue
            kept = TimeRange(
                start=max(window.start, clip.range.start),
                end=min(window.end, clip.range.end),
            )
            # Sub-frame boundary grazes contribute zero rendered frames to this
            # preview window; skip instead of failing slice_clip.
            if (
                isinstance(target, VideoRangeScrubTarget)
                and kept != clip.range
                and ticks_to_frames(kept.end, settings.timebase, settings.fps.num, settings.fps.den)
                <= ticks_to_frames(kept.start, settings.timebase, settings.fps.num, settings.fps.den)
            ):
                continue
            try:
                projected = deepcopy(clip) if kept == clip.range else slice_clip(content, clip, kept)
            except ValueError as exc:
                raise ScrubTargetError(
                    f"clip {clip.clip_id} cannot be cut at this window; choose its complete Clip or isolated Object"
                ) from exc
            projected.range = TimeRange(start=kept.start - window.start, end=kept.end - window.start)
            clips.append(projected)
        tracks.append(track.model_copy(update={"clips": clips}, deep=True))

    transitions = []
    if not isolated:
        by_id = {clip.clip_id: clip for _, clip in owners}
        for transition in content.timeline.transitions:
            cut = by_id[transition.from_clip_id].range.end
            before, after = transition.duration // 2, transition.duration - transition.duration // 2
            if window.start <= cut - before and cut + after <= window.end:
                if {transition.from_clip_id, transition.to_clip_id} <= selected:
                    transitions.append(deepcopy(transition))
            elif isinstance(target, VideoRangeScrubTarget) and window.start < cut + after and window.end > cut - before:
                rate = content.settings.timebase
                raise ScrubTargetError(
                    f"Include the complete transition at {(cut - before) / rate:g}–{(cut + after) / rate:g} seconds."
                )

    scenes = []
    for scene in content.scenes:
        start, end = max(window.start, scene.range.start), min(window.end, scene.range.end)
        if start >= end:
            continue
        scenes.append(scene.model_copy(update={
            "range": TimeRange(start=start - window.start, end=end - window.start),
            "speech_clip_ids": [clip_id for clip_id in scene.speech_clip_ids if clip_id in selected],
        }, deep=True))
    projected = content.model_copy(update={
        "scenes": scenes,
        "timeline": Timeline(tracks=tracks, transitions=transitions),
    }, deep=True)
    facts = {
        "target": target.model_dump(mode="json"),
        "source_range_seconds": {
            "start": window.start / content.settings.timebase,
            "end": window.end / content.settings.timebase,
        },
        "isolated_object": isolated,
        "clip_ids": sorted(selected),
    }
    return projected, facts


def compile_video_scrub(
    content: CompositionContent,
    snapshots: dict[UUID, dict[str, Any]],
    *,
    composition_id: UUID,
    version_id: UUID,
    content_digest: str,
    target: VideoScrubTarget | VideoRangeScrubTarget,
    generator_media: dict[str, dict[str, Any]],
    allow_outside_target: bool = False,
    allow_complete: bool = False,
) -> dict[str, Any]:
    """Build one scoped preview DTO without performing media production."""
    projected, scope = project_video_scrub(
        content, target,
        allow_outside_target=allow_outside_target,
        allow_complete=allow_complete,
    )
    clips = [clip for track in projected.timeline.tracks for clip in track.clips]
    missing_fixed = [
        clip.clip_id
        for clip in clips
        if isinstance(clip.object, GeneratorObject)
        and clip.object.producer in {"draw-2d", "remotion-project"}
        and (
            generator_media.get(clip.object.object_id) or {}
        ).get("program_digest") != clip.object.program_digest()
    ]
    if missing_fixed:
        return {
            "status": "unavailable",
            "reason": "fixed_generator_media_unavailable",
            "clip_ids": missing_fixed,
            "scope": scope,
        }

    pending: list[dict[str, str]] = []
    for clip in clips:
        obj = clip.object
        if isinstance(obj, GeneratorObject) and obj.producer == "image-generation":
            pending.append({"clip_id": clip.clip_id, "object_id": obj.object_id, "kind": "image-generation"})
        elif isinstance(obj, SpeechObject) and obj.alignment is None:
            pending.append({"clip_id": clip.clip_id, "object_id": obj.object_id, "kind": "speech"})
        elif (
            isinstance(obj, TextObject)
            and obj.caption is not None
            and isinstance(obj.caption, CaptionDerivation)
            and obj.caption.state == "derived"
            and obj.caption.alignment != "faster-whisper-script-v1"
        ):
            pending.append({"clip_id": clip.clip_id, "object_id": obj.object_id, "kind": "derived-caption"})
    if pending:
        return {"status": "pending_media", "pending": pending, "scope": scope}

    try:
        spec = compile_video_spec(
            projected,
            snapshots,
            composition_id=composition_id,
            version_id=version_id,
            content_digest=content_digest,
            generator_media=generator_media,
            playback_ticks=(
                round(target.end_seconds * content.settings.timebase)
                - round(target.start_seconds * content.settings.timebase)
                if isinstance(target, VideoRangeScrubTarget) else None
            ),
        )
    except (CompileError, ValueError):
        return {"status": "unavailable", "reason": "preview_compile_failed", "scope": scope}
    return {"status": "ready", "video_spec": spec, "scope": scope}


def revision_scrub_affected(read: dict[str, Any], target: VideoScrubTarget) -> bool:
    """A revision may preview only a target touched by its server-computed delta."""
    storyboard = read.get("storyboard") or {}
    scenes = storyboard.get("scenes") or []
    unassigned = storyboard.get("unassigned_clips") or []
    clips = [clip for scene in scenes for clip in scene.get("clips") or []] + unassigned
    changes = read.get("change_set") or {}
    clip_changes = changes.get("clips") or {}
    affected = {
        str(item.get("clip_id"))
        for group in ("added", "updated")
        for item in clip_changes.get(group) or []
    }
    scene_changes = changes.get("scenes") or {}
    affected_scenes = set(scene_changes.get("added") or []) | {
        str(item.get("scene_id")) for item in scene_changes.get("moved") or []
    }
    for scene in scenes:
        if scene.get("scene_id") in affected_scenes:
            affected.update(str(clip.get("clip_id")) for clip in scene.get("clips") or [])
    transition_changes = changes.get("transitions") or {}
    for group in ("before", "after"):
        for transition in transition_changes.get(group) or []:
            affected.update(str(transition.get(key)) for key in ("from_clip_id", "to_clip_id"))

    if isinstance(target, VideoObjectScrubTarget):
        scope = {str(clip.get("clip_id")) for clip in clips if clip.get("object_id") == target.object_id}
    elif target.clip_id is not None:
        scope = {target.clip_id}
    else:
        scope = {
            str(clip.get("clip_id"))
            for scene in scenes if scene.get("scene_id") == target.scene_id
            for clip in scene.get("clips") or []
        }
    return bool(scope & affected)


async def prepare_saved_video_scrub(
    db: AsyncSession,
    read: dict[str, Any],
    *,
    owner_id: UUID,
    target: VideoScrubTarget | VideoRangeScrubTarget,
) -> dict[str, Any]:
    """Prepare local Generator media only for an explicitly requested scope."""
    from app.tools.video.components import ComponentError
    from app.tools.video.programs import (
        ProgramError,
        enrich_generator_previews,
        prepare_generator_media,
    )

    _, version = await get_video_version(
        db, owner_id=owner_id, version_id=UUID(read["composition_version_id"])
    )
    content = content_of(version)
    projected, scope = project_video_scrub(content, target)
    facts = await snapshot_facts(db, {binding.snapshot_id for binding in projected.sources})
    try:
        await prepare_generator_media(projected, snapshots=facts)
    except (ProgramError, ComponentError) as exc:
        return {
            **read,
            "scrub": target.model_dump(mode="json"),
            "generator_previews": [],
            "video_preview": {
                "status": "unavailable",
                "reason": "generator_preview_failed",
                "detail": str(exc),
                "scope": scope,
            },
        }
    read = await enrich_generator_previews(read, clip_ids=set(scope["clip_ids"]))
    return await enrich_video_scrub(db, read, owner_id=owner_id, target=target)


async def enrich_video_scrub(
    db: AsyncSession,
    read: dict[str, Any],
    *,
    owner_id: UUID,
    target: VideoScrubTarget | VideoRangeScrubTarget,
) -> dict[str, Any]:
    """Attach a scoped preview to an already owner-scoped exact-version read."""
    from app.pipeline.rendering import absolutize_video
    from app.tools.video.programs import _preview_manifests

    composition, version = await get_video_version(
        db, owner_id=owner_id, version_id=UUID(read["composition_version_id"])
    )
    content = content_of(version)
    _, scope = project_video_scrub(content, target)
    facts = await snapshot_facts(db, {binding.snapshot_id for binding in content.sources})
    manifests = await _preview_manifests(read, clip_ids=set(scope["clip_ids"]))
    generator_media = {clip["object_id"]: manifest for clip, manifest in manifests}
    preview = compile_video_scrub(
        content,
        facts,
        composition_id=composition.id,
        version_id=version.id,
        content_digest=version.content_digest,
        target=target,
        generator_media=generator_media,
    )
    if preview["status"] == "ready":
        preview["video_spec"] = absolutize_video(preview["video_spec"])
    return {**read, "scrub": target.model_dump(mode="json"), "video_preview": preview}












async def render_preview(spec: dict) -> bytes:
    from app.config import settings

    endpoint = settings.render_url.removesuffix("/render") + "/preview"
    try:
        async with httpx.AsyncClient(timeout=settings.render_timeout_seconds, trust_env=False) as client:
            response = await client.post(endpoint, json={"spec": spec})
    except httpx.HTTPError as exc:
        raise ScrubTargetError(f"continuous preview request failed: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise ScrubTargetError(f"continuous preview failed with renderer status {response.status_code}")
    return response.content


def source_geometry(content, clip, source_width, source_height):
    obj = clip.object
    if obj.fit != "contain" or obj.transform.rotation or clip.animations:
        return {}
    box, tr = obj.layout, obj.transform
    ratio = min(box.width / source_width, box.height / source_height)
    ox, oy = (box.width / 2, box.height / 2) if tr.origin == "center" else (0, 0)
    x = box.x + tr.x + ox + ((box.width - source_width * ratio) / 2 - ox) * tr.scale
    y = box.y + tr.y + oy + ((box.height - source_height * ratio) / 2 - oy) * tr.scale
    right = x + source_width * ratio * tr.scale
    bottom = y + source_height * ratio * tr.scale
    canvas_width, canvas_height = content.settings.width, content.settings.height
    clipped = {
        "left": round(max(0.0, -x), 2),
        "top": round(max(0.0, -y), 2),
        "right": round(max(0.0, right - canvas_width), 2),
        "bottom": round(max(0.0, bottom - canvas_height), 2),
    }
    borders = {
        "left": round(max(0.0, x), 2),
        "top": round(max(0.0, y), 2),
        "right": round(max(0.0, canvas_width - right), 2),
        "bottom": round(max(0.0, canvas_height - bottom), 2),
    }
    return {
        "source_bounds_canvas_px": [round(v, 2) for v in (x, y, right, bottom)],
        "source_visible_bounds_canvas_px": [
            round(max(0.0, x), 2), round(max(0.0, y), 2),
            round(min(float(canvas_width), right), 2), round(min(float(canvas_height), bottom), 2),
        ],
        "source_clipped_px": clipped,
        "canvas_borders_px": borders,
        "canvas_px": [canvas_width, canvas_height],
        "whole_source_inside_canvas": not any(clipped.values()),
    }


def face_geometry(bbox, score, geometry):
    source_width, source_height = geometry["source_pixels"]
    canvas_width, canvas_height = geometry["canvas_px"]
    left, top, right, bottom = geometry["source_bounds_canvas_px"]
    sx, sy = (right - left) / source_width, (bottom - top) / source_height
    x, y, width, height = bbox

    def project(box):
        px, py, pw, ph = box
        return [round(left + px * sx, 2), round(top + py * sy, 2),
                round(left + (px + pw) * sx, 2), round(top + (py + ph) * sy, 2)]

    def clipped(box):
        px, py, pw, ph = box
        x0, y0 = left + px * sx, top + py * sy
        x1, y1 = left + (px + pw) * sx, top + (py + ph) * sy
        return {
            "left": round(max(0.0, -x0), 2), "top": round(max(0.0, -y0), 2),
            "right": round(max(0.0, x1 - canvas_width), 2),
            "bottom": round(max(0.0, y1 - canvas_height), 2),
        }

    expanded = (
        max(0.0, x - width / 2), max(0.0, y - height / 2),
        min(float(source_width), x + width * 1.5) - max(0.0, x - width / 2),
        min(float(source_height), y + height * 1.5) - max(0.0, y - height / 2),
    )
    return {
        "source_bbox_px": [round(value, 2) for value in bbox],
        "canvas_bbox_px": project(bbox),
        "canvas_clipped_px": clipped(bbox),
        "face_fully_visible": not any(clipped(bbox).values()),
        "expanded_face_source_bbox_px": [round(value, 2) for value in expanded],
        "expanded_face_canvas_bbox_px": project(expanded),
        "expanded_face_canvas_clipped_px": clipped(expanded),
        "expanded_face_fully_visible": not any(clipped(expanded).values()),
        "confidence": round(score, 4),
    }


async def source_framing(db, owner_id, content, covered, sample_seconds):
    """Compare a single static video layout with its fixed, uncropped source."""
    import asyncio
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.tables import SourceSnapshot
    from app.providers import storage
    from app.tools.video.review import ReviewError, _decode_frame, _jpeg
    from botocore.exceptions import BotoCoreError, ClientError

    visible = [clip for track in content.timeline.tracks if track.kind == "visual"
               for clip in track.clips if clip.clip_id in covered]
    if not visible or any(clip.object.kind != "video" or not clip.source or not clip.source.source_range
                          for clip in visible):
        return None, None
    source_refs = {(clip.source.snapshot_id, clip.source.snapshot_digest) for clip in visible}
    if len(source_refs) != 1:
        return None, None
    clip = visible[0]
    obj = clip.object
    snapshot = await db.get(SourceSnapshot, clip.source.snapshot_id)
    if not snapshot or snapshot.owner_id != owner_id or snapshot.digest != clip.source.snapshot_digest:
        return None, None
    multiple = len(visible) > 1
    if not multiple:
        offset = Fraction(str(sample_seconds)) - Fraction(clip.range.start, content.settings.timebase)
        if not 0 <= offset < Fraction(clip.range.end - clip.range.start, content.settings.timebase):
            return None, None
        target = Fraction(clip.source.source_range.start, SOURCE_TIMEBASE) + offset
    try:
        length = await storage.size(snapshot.storage_key)
        if not length or length > 32 * 1024 * 1024:
            return None, None
        data = await storage.read(snapshot.storage_key)
        if hashlib.sha256(data).hexdigest() != snapshot.digest:
            return {"available": False, "reason": "Source digest mismatch."}, None
        with av.open(io.BytesIO(data)) as container:
            source_audio_present = bool(container.streams.audio)
            if not multiple:
                stream = container.streams.video[0]
                frame, actual = _decode_frame(container, stream, target, Fraction(stream.average_rate or 30))
                jpeg = _jpeg(frame)
                width, height = frame.width, frame.height
                square_upright = not frame.rotation and (stream.sample_aspect_ratio or 1) == 1
    except (OSError, IndexError, ReviewError, BotoCoreError, ClientError, av.FFmpegError):
        return {"available": False, "reason": "Could not decode fixed source reference."}, None

    source_audio = {"stream_present": source_audio_present}
    if source_audio_present:
        from app.tools.video.media_analysis import MediaAnalysisError, analyze_audio_bytes

        try:
            measured = await asyncio.to_thread(
                analyze_audio_bytes, data, snapshot_id=str(snapshot.id), source_digest=snapshot.digest,
                requested_probes=["decode", "pcm_stats"],
            )
            source_audio.update(
                fully_decoded=measured.media_facts["decode"]["fully_decoded"],
                is_silent=measured.media_facts["pcm_stats"]["is_silent"],
            )
        except MediaAnalysisError:
            source_audio["fully_decoded"] = False
    if multiple:
        return {"snapshot_id": str(snapshot.id), "source_audio": source_audio}, None
    facts = {"snapshot_id": str(snapshot.id), "source_seconds": float(actual),
             "source_pixels": [width, height], "fit": obj.fit, "transform": obj.transform.model_dump(),
             "source_audio": source_audio}
    if square_upright:
        geometry = {**source_geometry(content, clip, width, height), "source_pixels": [width, height]}
        facts.update(geometry)
        if geometry:
            from app.providers.vision import detect_faces

            scale = min(1.0, 640 / max(width, height))
            try:
                faces = await asyncio.to_thread(
                    detect_faces, frame.to_ndarray(format="bgr24"),
                    (max(32, int(width * scale)), max(32, int(height * scale))),
                )
                facts["face_evidence"] = {
                    "status": "detected" if faces else "no_face_detected",
                    "source_seconds": float(actual),
                    "faces": [face_geometry(face.bbox, face.score, geometry) for face in faces],
                    "scope": "YuNet face boxes only; expanded boxes are context, not proof of complete hair, shoulders or natural framing.",
                }
            except Exception as exc:
                import structlog

                structlog.get_logger().warning("preview_face_detection_unavailable", error_type=type(exc).__name__)
                facts["face_evidence"] = {"status": "unavailable", "reason": type(exc).__name__}
    return facts, MediaInput(type=MediaInputType.IMAGE, mime="image/jpeg",
                             caption=f"Uncropped SOURCE at {float(actual):g}s, before fit or transform. Compare with the rendered composition.",
                             data_url="data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"))


def preview_sample_frames(intervals):
    if len(intervals) <= 2:
        return sorted({index for start, end in intervals
                       for index in (start, (start + end - 1) // 2, end - 1)})
    if len(intervals) <= 6:
        return [(start + end - 1) // 2 for start, end in intervals]
    return [(intervals[i * (len(intervals) - 1) // 5][0]
             + intervals[i * (len(intervals) - 1) // 5][1] - 1) // 2 for i in range(6)]


def sampled_frame_facts(frames, *, background):
    from PIL import Image, ImageChops

    facts = []
    previous = None
    for jpeg, seconds in frames:
        with Image.open(io.BytesIO(jpeg)) as source:
            current = source.convert("RGB")
        # Measure only the decoded pixels. A matching strip can also be
        # intentional artwork; its width is evidence for visual comparison.
        delta = ImageChops.difference(current, Image.new("RGB", current.size, background))
        bounds = delta.point(lambda channel: 255 if channel > 8 else 0).getbbox()
        facts.append({
            "sample_size_px": list(current.size),
            "edges_matching_canvas_color_px": ({
                "left": bounds[0], "top": bounds[1],
                "right": current.width - bounds[2], "bottom": current.height - bounds[3],
            } if bounds else None),
            "seconds": seconds,
            "jpeg_sha256": hashlib.sha256(jpeg).hexdigest(),
            "pixel_difference_from_previous_bbox_px": (
                None if previous is None else list(ImageChops.difference(previous, current).getbbox() or ())
            ),
        })
        previous = current
    return facts


def _audio_window_facts(video: bytes, spec: dict, bounds_start: float, fps: Fraction) -> dict:
    """Deterministic time-window energy bins & dialogue/SFX/BGM overlap hints."""
    import math
    import numpy as np

    audio_clips = [
        {
            "clip_id": clip["clip_id"],
            "role": track["role"],
            "from": round(bounds_start + float(Fraction(clip["start_frame"], 1) / fps), 3),
            "to": round(bounds_start + float(Fraction(clip["end_frame"], 1) / fps), 3),
            "gain_db": float((clip.get("object") or {}).get("gain_db", 0.0)),
        }
        for track in spec.get("tracks", [])
        if track.get("kind") == "audio"
        for clip in track.get("clips", [])
    ]

    bins: list[dict] = []
    overall_peak_db = -96.0
    try:
        with av.open(io.BytesIO(video)) as container:
            astream = next(iter(container.streams.audio), None)
            if astream is not None:
                chunks = []
                sr = int(astream.rate or 48000)
                for frame in container.decode(astream):
                    arr = frame.to_ndarray()
                    if arr.ndim == 2:
                        # Handle planar (C, N) vs packed (1, N*C)
                        if arr.shape[0] <= 8 and arr.shape[1] > arr.shape[0]:
                            mono = arr.astype(np.float32).mean(axis=0)
                        else:
                            mono = arr.astype(np.float32).reshape(-1, max(1, len(astream.layout.channels))).mean(axis=1)
                    else:
                        mono = arr.astype(np.float32)
                    if np.issubdtype(arr.dtype, np.integer):
                        info = np.iinfo(arr.dtype)
                        mono = mono / float(max(abs(info.min), abs(info.max)))
                    chunks.append(mono)
                if chunks:
                    pcm = np.concatenate(chunks)
                    win = max(1, int(round(sr * 0.5)))
                    for i in range(0, len(pcm), win):
                        seg = pcm[i : i + win]
                        if len(seg) == 0:
                            continue
                        peak = float(np.max(np.abs(seg)))
                        rms = float(np.sqrt(np.mean(seg * seg)))
                        peak_db = round(20.0 * math.log10(peak), 2) if peak > 1e-6 else -96.0
                        rms_db = round(20.0 * math.log10(rms), 2) if rms > 1e-6 else -96.0
                        if peak_db > overall_peak_db:
                            overall_peak_db = peak_db
                        bins.append({
                            "from": round(bounds_start + i / sr, 3),
                            "to": round(bounds_start + (i + len(seg)) / sr, 3),
                            "rms_dbfs": rms_db,
                            "peak_dbfs": peak_db,
                        })
    except av.FFmpegError:
        pass

    warnings: list[str] = []
    if overall_peak_db > -1.0:
        warnings.append(f"Mixed audio peaks at {overall_peak_db} dBFS (close to 0 dBFS clipping); lower music or SFX gain_db.")
    dialogues = [c for c in audio_clips if c["role"] == "dialogue"]
    for d in dialogues:
        for other in audio_clips:
            if other["role"] == "dialogue":
                continue
            ov_start = max(d["from"], other["from"])
            ov_end = min(d["to"], other["to"])
            if ov_end <= ov_start:
                continue
            if other["role"] == "music" and other["gain_db"] > -12.0:
                warnings.append(
                    f"Music clip {other['clip_id']} ({other['gain_db']:+g} dB) overlaps dialogue {d['clip_id']} "
                    f"during {ov_start:g}-{ov_end:g}s; keep BGM around -16 to -20 dB under narration."
                )
            elif other["role"] == "effect" and other["gain_db"] > -6.0:
                warnings.append(
                    f"SFX clip {other['clip_id']} ({other['gain_db']:+g} dB) overlaps dialogue {d['clip_id']} "
                    f"during {ov_start:g}-{ov_end:g}s; lower SFX gain_db or soften tone if it masks speech."
                )

    return {
        "audio_clips_in_window": audio_clips,
        "audio_windows": bins,
        "masking_warnings": warnings,
    }


async def saved_preview_media(preview: dict, version_id: UUID):
    """Return the actual playback range and identify the media delivered to the model."""
    from app.providers.llm import get_llm_client

    bounds = preview["scope"]["source_range_seconds"]
    if preview["video_spec"].get("fonts"):
        from app.tools.video.preparation import ensure_font_resources

        await ensure_font_resources()
    video = await render_preview(preview["video_spec"])
    from app.tools.video.review import ReviewError, _decode_frame, _jpeg

    if not video or len(video) > 32 * 1024 * 1024:
        raise ScrubTargetError("The rendered preview is empty or exceeds its evidence budget.")
    spec = preview["video_spec"]
    fps = Fraction(spec["fps"]["num"], spec["fps"]["den"])
    clips = [clip for track in spec["tracks"] if track["kind"] == "visual" for clip in track["clips"]]
    cuts = sorted({0, spec["duration_frames"], *(c[k] for c in clips for k in ("start_frame", "end_frame"))})
    intervals = [(start, end) for start, end in zip(cuts, cuts[1:]) if start < end]
    frames = []
    try:
        with av.open(io.BytesIO(video)) as container:
            stream = next(iter(container.streams.video), None)
            if stream is None:
                raise ScrubTargetError("The preview contains no video stream.")
            has_audio = bool(container.streams.audio)
            for index in preview_sample_frames(intervals):
                target = Fraction(index, 1) / fps
                frame, actual = _decode_frame(container, stream, target, fps)
                frames.append((_jpeg(frame), round(bounds["start"] + float(actual), 6)))
    except (av.FFmpegError, ReviewError) as exc:
        raise ScrubTargetError("Could not decode evidence frames from the rendered window.") from exc
    capabilities = get_llm_client().capabilities
    caption = f"Saved version {version_id}, composition seconds {bounds}."
    media = []
    # MiniMax rejected a real half-second H.264/AAC clip (HTTP 400) even
    # as a standalone input. Keep the exact user window and label the still.
    if capabilities.supports_video_input and bounds["end"] - bounds["start"] >= 1:
        media.append(MediaInput(
            type=MediaInputType.VIDEO, mime="video/mp4", caption=caption,
            data_url="data:video/mp4;base64," + base64.b64encode(video).decode("ascii"),
        ))
    if capabilities.supports_tool_result_images:
        from PIL import Image, ImageDraw
        # The timestamps travel inside the pixels as well as in the wire.
        # A provider may sample the MP4 at a different cadence or resize it.
        width, height = (640, 382) if len(frames) <= 3 else (320, 200)
        columns = min(len(frames), 2)
        sheet = Image.new("RGB", (width * columns, height * ((len(frames) + 1) // 2)))
        draw = ImageDraw.Draw(sheet)
        for i, (jpeg, seconds) in enumerate(frames):
            with Image.open(io.BytesIO(jpeg)) as img:
                img.thumbnail((width, height - 22))
                x, y = (i % columns) * width, (i // columns) * height
                sheet.paste(img, (x + (width - img.width) // 2, y))
                draw.text((x + 4, y + height - 18), f"{seconds:g} s", fill="white")
        out = io.BytesIO()
        sheet.save(out, format="JPEG", quality=90)
        media.append(MediaInput(
            type=MediaInputType.IMAGE, mime="image/jpeg",
            caption=f"Current frames decoded from version {version_id}, labelled with absolute composition seconds.",
            data_url="data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii"),
        ))
    evidence = {
        "version_id": str(version_id), "scope": preview["scope"],
        "mp4_sha256": hashlib.sha256(video).hexdigest(),
        "sample_seconds": [time for _, time in frames],
        "sample_frames": sampled_frame_facts(frames, background=spec["background"]),
        "visual_windows": [
            {"from": round(bounds["start"] + float(start / fps), 6),
             "to": round(bounds["start"] + float(end / fps), 6),
             "active_clips": [c["clip_id"] for c in clips if c["start_frame"] <= start < c["end_frame"]]}
            for start, end in intervals
        ],
        "model_media": [item.type for item in media],
        "audio_available_to_model": capabilities.understands_video_audio and any(
            item.type == MediaInputType.VIDEO for item in media
        ),
    }
    evidence["audio_stream_present"] = has_audio
    if has_audio:
        import asyncio
        from app.tools.video.media_analysis import analyze_audio_bytes

        measured = await asyncio.to_thread(analyze_audio_bytes, video, snapshot_id=str(version_id),
                                           requested_probes=["decode", "pcm_stats", "loudness"])
        evidence["mixed_audio"] = {k: measured.media_facts[k] for k in ("decode", "pcm_stats", "loudness")}
        evidence.update(await asyncio.to_thread(_audio_window_facts, video, spec, bounds["start"], fps))
    return tuple(media), evidence
