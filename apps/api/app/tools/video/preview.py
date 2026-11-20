"""Read-only, bounded CompositionVersion Scrub previews.

The browser and the editor receive an explicit time window or one isolated
object. Compilation resolves fixed sources and requested local Generator media.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from copy import deepcopy
from fractions import Fraction
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import av
import httpx
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator
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
from app.editing.temporal import slice_clip
from app.editing.video_spec import CompileError, compile_video_spec
from app.models.schemas import (
    MediaInput,
    MediaInputType,
    VideoDraftRef,
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


class VideoDraftReviewTarget(BaseModel):
    """The current Scene, optionally joined to its immediately previous Scene."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    include_previous_scene: bool = False
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("include_previous_scene") is None:
            return {**data, "include_previous_scene": False}
        return data

    @model_validator(mode="after")
    def _bounded(self) -> "VideoDraftReviewTarget":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("review end_seconds must be after start_seconds")
        if self.end_seconds - self.start_seconds > 24:
            raise ValueError("one working-draft review is limited to 24 seconds")
        return self


class WorkingDraftReviewJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=24, max_length=24)
    observed: str | None = Field(default=None, min_length=1, max_length=1000,
                                 description="描述目标场景中实际可见的内容，再与要求比较。")
    verdict: Literal["pass", "issue", "uncertain"]
    summary: str = Field(min_length=1, max_length=1000)
    clip_ids: list[str] = Field(default_factory=list, max_length=16)
    resolves_issue_ids: list[str] = Field(default_factory=list, max_length=16)


class ReviewWorkingDraftArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_ref: VideoDraftRef
    scene_id: str | None = Field(default=None, min_length=1, max_length=64)
    include_previous_scene: bool = False
    judgment: WorkingDraftReviewJudgment | None = Field(
        default=None,
        description="针对当前 evidence_id 记录观察到的画面事实，填写 pass、issue 或 uncertain。",
    )
    _working_draft: dict[str, Any] | None = PrivateAttr(default=None)
    _review_target: VideoDraftReviewTarget | None = PrivateAttr(default=None)
    _confirmation_retry: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def _initial_target_only(self) -> "ReviewWorkingDraftArgs":
        if self.judgment is not None and self.scene_id is not None:
            raise ValueError("a judgment uses the current evidence_id only")
        if self.include_previous_scene and self.scene_id is None:
            raise ValueError("a preceding join requires a target Scene")
        return self

    def bind_working_draft(self, value: dict[str, Any]) -> None:
        self._working_draft = deepcopy(value)
        if self.judgment is None:
            from app.agents.working_drafts import working_draft_review_facts

            if self.scene_id is not None:
                from app.agents.candidate_correction import CorrectionError

                if (value.get("review") or {}).get("started"):
                    raise CorrectionError("invalid_review_target", "continue the current review using the server-selected window")
                content = CompositionContent.model_validate(value["content"])
                scenes = sorted(content.scenes, key=lambda scene: scene.range.start)
                index = next((i for i, scene in enumerate(scenes) if scene.scene_id == self.scene_id), None)
                if index is None or (index == 0 and self.include_previous_scene):
                    raise CorrectionError("invalid_review_target", "the requested Scene or preceding join does not exist in the draft")
                scene = scenes[index]
                timebase = content.settings.timebase
                start = scene.range.start / timebase
                end = scene.range.end / timebase
                if self.include_previous_scene:
                    start = max(scenes[index - 1].range.start / timebase, start - 1.5)
                self._review_target = VideoDraftReviewTarget(
                    scene_id=self.scene_id, include_previous_scene=self.include_previous_scene,
                    start_seconds=start, end_seconds=end,
                )
                self._working_draft["review"] = {
                    "started": True, "scope": {"start": start, "end": end}, "scene_id": self.scene_id,
                }
                return
            target = working_draft_review_facts(value)["next_review_target"]
            if target is not None:
                self._confirmation_retry = bool(target.get("confirmation_retry"))
                self._review_target = VideoDraftReviewTarget.model_validate({
                    key: target[key] for key in VideoDraftReviewTarget.model_fields
                })


def project_working_draft_review(
    content: CompositionContent, target: VideoDraftReviewTarget
) -> tuple[CompositionContent, dict[str, Any]]:
    scenes = sorted(content.scenes, key=lambda scene: scene.range.start)
    index = next((i for i, scene in enumerate(scenes) if scene.scene_id == target.scene_id), None)
    if index is None:
        raise ScrubTargetError("the review scene_id does not exist in this working draft")
    current = scenes[index]
    previous = scenes[index - 1] if target.include_previous_scene and index > 0 else None
    if target.include_previous_scene and previous is None:
        raise ScrubTargetError("the first Scene has no previous Scene to join")
    lower = previous.range.start if previous is not None else current.range.start
    timebase = content.settings.timebase
    if (
        round(target.start_seconds * timebase) < lower
        or round(target.end_seconds * timebase) > current.range.end
        or round(target.end_seconds * timebase) <= current.range.start
    ):
        raise ScrubTargetError("the review window must cover the current Scene and only its immediate predecessor")
    segment = VideoSegmentScrubTarget(
        scene_id=target.scene_id,
        start_seconds=target.start_seconds,
        end_seconds=target.end_seconds,
    )
    projected, scope = project_video_scrub(
        content,
        segment,
        allow_outside_target=previous is not None,
        allow_complete=True,
    )
    scope["review_target"] = target.model_dump(mode="json")
    scope["scene_ids"] = [
        scene.scene_id for scene in scenes
        if scene.range.start < round(target.end_seconds * timebase)
        and round(target.start_seconds * timebase) < scene.range.end
    ]
    scope["current_scene_ordinal"] = index + 1
    return projected, scope


def _representative_preview_frame(
    video: bytes, *, window_start: float, scene_start: float, window_end: float, retry: bool,
) -> tuple[bytes, float]:
    from app.tools.video.review import ReviewError, _decode_frame, _jpeg

    if not video or len(video) > 32 * 1024 * 1024:
        raise ScrubTargetError("the continuous preview exceeded its 32 MiB evidence budget")
    target_duration = window_end - max(window_start, scene_start)
    offset = min(0.75, target_duration / 3) if retry else min(0.25, target_duration / 4)
    try:
        with av.open(io.BytesIO(video), mode="r") as container:
            stream = next((item for item in container.streams if item.type == "video"), None)
            if stream is None:
                raise ScrubTargetError("the preview has no decodable video stream")
            fps = Fraction(stream.average_rate or 30)
            target = Fraction(str(window_end - offset - window_start))
            frame, actual = _decode_frame(container, stream, target, fps)
            seconds = round(window_start + float(actual), 6)
            if seconds < max(window_start, scene_start) or seconds >= window_end:
                raise ScrubTargetError("the preview frame falls outside the target Scene")
            return _jpeg(frame), seconds
    except (av.FFmpegError, ReviewError) as exc:
        raise ScrubTargetError("the target Scene's representative frame could not be decoded") from exc


async def render_preview(spec: dict) -> bytes:
    from app.config import settings

    endpoint = settings.render_url.removesuffix("/render") + "/preview"
    try:
        async with httpx.AsyncClient(timeout=settings.render_timeout_seconds) as client:
            response = await client.post(endpoint, json={"spec": spec})
    except httpx.HTTPError as exc:
        raise ScrubTargetError(f"continuous preview request failed: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise ScrubTargetError(f"continuous preview failed with renderer status {response.status_code}")
    return response.content


async def source_framing(db, owner_id, content, covered, sample_seconds):
    """Compare a single static video layout with its fixed, uncropped source."""
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.tables import SourceSnapshot
    from app.providers import storage
    from app.tools.video.review import ReviewError, _decode_frame, _jpeg
    from botocore.exceptions import BotoCoreError, ClientError

    visible = [clip for track in content.timeline.tracks if track.kind == "visual"
               for clip in track.clips if clip.clip_id in covered]
    if len(visible) != 1:
        return None, None
    clip = visible[0]
    obj = clip.object
    if obj.kind != "video" or not clip.source or not clip.source.source_range:
        return None, None
    snapshot = await db.get(SourceSnapshot, clip.source.snapshot_id)
    if not snapshot or snapshot.owner_id != owner_id or snapshot.digest != clip.source.snapshot_digest:
        return None, None
    offset = Fraction(str(sample_seconds)) - Fraction(clip.range.start, content.settings.timebase)
    target = Fraction(clip.source.source_range.start, SOURCE_TIMEBASE) + offset
    try:
        length = await storage.size(snapshot.storage_key)
        if not length or length > 32 * 1024 * 1024:
            return None, None
        data = await storage.read(snapshot.storage_key)
        if hashlib.sha256(data).hexdigest() != snapshot.digest:
            return {"available": False, "reason": "Source digest mismatch."}, None
        with av.open(io.BytesIO(data)) as container:
            stream = container.streams.video[0]
            frame, actual = _decode_frame(container, stream, target, Fraction(stream.average_rate or 30))
            jpeg = _jpeg(frame)
            width, height = frame.width, frame.height
            square_upright = not frame.rotation and (stream.sample_aspect_ratio or 1) == 1
    except (OSError, IndexError, ReviewError, BotoCoreError, ClientError, av.FFmpegError):
        return {"available": False, "reason": "Could not decode fixed source reference."}, None

    facts = {"snapshot_id": str(snapshot.id), "source_seconds": float(actual),
             "source_pixels": [width, height], "fit": obj.fit, "transform": obj.transform.model_dump()}
    # For contain, the source is centered inside its layout box before the
    # renderer's origin-relative scale and canvas-space translation.
    if square_upright and obj.fit == "contain" and not obj.transform.rotation and not clip.animations:
        box, tr = obj.layout, obj.transform
        ratio = min(box.width / width, box.height / height)
        ox, oy = (box.width / 2, box.height / 2) if tr.origin == "center" else (0, 0)
        x = box.x + tr.x + ox + ((box.width - width * ratio) / 2 - ox) * tr.scale
        y = box.y + tr.y + oy + ((box.height - height * ratio) / 2 - oy) * tr.scale
        right, bottom = x + width * ratio * tr.scale, y + height * ratio * tr.scale
        facts["source_bounds_canvas_px"] = [round(v, 2) for v in (x, y, right, bottom)]
        facts["canvas_px"] = [content.settings.width, content.settings.height]
        facts["whole_source_inside_canvas"] = x >= 0 and y >= 0 and right <= content.settings.width and bottom <= content.settings.height
    return facts, MediaInput(type=MediaInputType.IMAGE, mime="image/jpeg",
                             caption=f"Uncropped SOURCE at {float(actual):g}s, before fit or transform. Compare with the rendered composition.",
                             data_url="data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"))


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
    samples = intervals if len(intervals) <= 6 else [intervals[i * (len(intervals) - 1) // 5] for i in range(6)]
    frames = []
    try:
        with av.open(io.BytesIO(video)) as container:
            stream = next(iter(container.streams.video), None)
            if stream is None:
                raise ScrubTargetError("The preview contains no video stream.")
            has_audio = bool(container.streams.audio)
            for start, end in samples:
                target = Fraction((start + end - 1) // 2, 1) / fps
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
        width, height = 320, 200
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
    return tuple(media), evidence


async def prepare_working_draft_review(
    db: AsyncSession,
    *,
    owner_id: UUID,
    args: ReviewWorkingDraftArgs,
) -> tuple[dict[str, Any], tuple[MediaInput, MediaInput]]:
    """Compile and render only an authenticated draft's bounded review window."""
    from app.editing.store import _raw_snapshot_ids
    from app.models.schemas import canonical_json_hash
    from app.pipeline.rendering import absolutize_video
    from app.tools.video.components import ComponentError
    from app.tools.video.programs import ProgramError, prepare_generator_media

    state = args._working_draft or {}
    target = args._review_target
    if target is None:
        raise ScrubTargetError("record the current evidence judgment before requesting another preview")
    content = CompositionContent.model_validate(state.get("content") or {})
    projected, scope = project_working_draft_review(content, target)
    snapshot_ids = _raw_snapshot_ids(content.model_dump(mode="json"))
    facts = await snapshot_facts(db, snapshot_ids)
    if any(facts.get(snapshot_id, {}).get("owner_id") != owner_id for snapshot_id in snapshot_ids):
        raise ScrubTargetError("a draft source is not accessible to this user")
    from app.editing.validators import validate_content

    validate_content(content, facts)
    try:
        generator_media = await prepare_generator_media(projected, snapshots=facts)
    except (ProgramError, ComponentError) as exc:
        raise ScrubTargetError(f"working-draft Generator preview is unavailable: {exc}") from exc
    content_digest = canonical_json_hash(content.model_dump(mode="json"))
    design = state.get("design") or {}
    composition_id = UUID(str(design["composition_id"])) if design.get("composition_id") else uuid5(
        NAMESPACE_URL, f"repurposer:draft-composition:{args.draft_ref.draft_id}"
    )
    preview_identity = uuid5(NAMESPACE_URL, f"repurposer:draft-preview:{args.draft_ref.draft_id}")
    preview = compile_video_scrub(
        content,
        facts,
        composition_id=composition_id,
        version_id=preview_identity,
        content_digest=content_digest,
        target=VideoSegmentScrubTarget(
            scene_id=target.scene_id,
            start_seconds=target.start_seconds,
            end_seconds=target.end_seconds,
        ),
        generator_media=generator_media,
        allow_outside_target=target.include_previous_scene,
        allow_complete=True,
    )
    if preview["status"] != "ready":
        raise ScrubTargetError(
            "working-draft preview is unavailable: "
            + json.dumps({key: value for key, value in preview.items() if key != "video_spec"}, ensure_ascii=False)
        )
    preview["video_spec"] = absolutize_video(preview["video_spec"])
    video = await render_preview(preview["video_spec"])
    scene = next(scene for scene in content.scenes if scene.scene_id == target.scene_id)
    jpeg, frame_seconds = _representative_preview_frame(
        video, window_start=target.start_seconds, scene_start=scene.range.start / content.settings.timebase,
        window_end=target.end_seconds, retry=args._confirmation_retry,
    )
    media_digest = hashlib.sha256(video).hexdigest()
    evidence = {
        "schema_version": 1,
        "draft_ref": args.draft_ref.model_dump(mode="json"),
        "content_digest": content_digest,
        "scope": scope,
        "requirements": design,
        "observation": {
            "mode": "continuous_mp4",
            "continuous": True,
            "media_digest": media_digest,
            "size_bytes": len(video),
            "duration_seconds": scope["source_range_seconds"]["end"] - scope["source_range_seconds"]["start"],
            "representative_frame": {
                "scene_id": target.scene_id, "output_seconds": frame_seconds,
                "digest": hashlib.sha256(jpeg).hexdigest(),
            },
            "confirmation_retry": args._confirmation_retry,
        },
        "limitations": [
            "Only the listed draft window was rendered and attached; no Run, Output or saved version was created.",
            "Visual continuous evidence does not by itself prove perceived audio quality or audio-visual synchronization.",
        ],
    }
    media = MediaInput(
        type=MediaInputType.VIDEO,
        mime="video/mp4",
        data_url="data:video/mp4;base64," + base64.b64encode(video).decode("ascii"),
        caption=(
            f"Working draft {args.draft_ref.draft_id} content {content_digest}; continuous MP4 "
            f"covering {json.dumps(scope['source_range_seconds'])} in Scenes {scope['scene_ids']}. "
            f"Media SHA-256 {media_digest}. This is not a saved-version Scrub or delivered Output."
        ),
    )
    still = MediaInput(
        type=MediaInputType.IMAGE, mime="image/jpeg",
        data_url="data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"),
        caption=f"Representative frame from this MP4 at output {frame_seconds:.3f}s in target Scene "
                f"{target.scene_id}. Use it for visible content, and the MP4 for motion or joins.",
    )
    return evidence, (media, still)
