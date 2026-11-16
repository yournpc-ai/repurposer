"""Read-only, bounded CompositionVersion Scrub previews.

A pre-production browser receives only one explicit Scene/Clip time window or
one isolated Object, never the complete video-spec. Compilation may resolve
already-fixed sources and explicitly requested local Generator media; it never
prepares Speech or model-generated media. Apply remains the separate write
through ``revise_video``.
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
    VideoSegmentScrubTarget,
)


class ScrubTargetError(ValueError):
    """A model/client target that is not a bounded part of this version."""


def project_video_scrub(
    content: CompositionContent,
    target: VideoScrubTarget,
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
    elif isinstance(target, VideoSegmentScrubTarget):
        if target.scene_id is not None:
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
            raise ScrubTargetError("the scrub window must stay inside its named Scene or Clip")
        timeline_start = min((clip.range.start for _, clip in owners), default=0)
        timeline_end = max((clip.range.end for _, clip in owners), default=0)
        if not allow_complete and window.start <= timeline_start and window.end >= timeline_end:
            raise ScrubTargetError("a pre-production Scrub cannot contain the complete video")
        selected = {
            clip.clip_id
            for _, clip in owners
            if clip.range.start < window.end and window.start < clip.range.end
        }
    else:
        raise ScrubTargetError("unknown Scrub target")
    if not selected:
        raise ScrubTargetError("the scrub window contains no clips")

    tracks = []
    for track in content.timeline.tracks:
        if any(clip.clip_id in selected for clip in track.clips) is False:
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
            if transition.from_clip_id not in selected or transition.to_clip_id not in selected:
                continue
            cut = by_id[transition.from_clip_id].range.end
            before, after = transition.duration // 2, transition.duration - transition.duration // 2
            if window.start <= cut - before and cut + after <= window.end:
                transitions.append(deepcopy(transition))

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
    target: VideoScrubTarget,
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
    target: VideoScrubTarget,
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
    target: VideoScrubTarget,
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
                                 description="What is actually visible in the target Scene, before comparing to the requirement.")
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
        description="Record observed visual facts and pass, issue or uncertain for the current evidence_id.",
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


async def prepare_working_draft_review(
    db: AsyncSession,
    *,
    owner_id: UUID,
    args: ReviewWorkingDraftArgs,
) -> tuple[dict[str, Any], tuple[MediaInput, MediaInput]]:
    """Compile and render only an authenticated draft's bounded review window."""
    from app.config import settings
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
    endpoint = settings.render_url.removesuffix("/render") + "/preview"
    try:
        async with httpx.AsyncClient(timeout=settings.render_timeout_seconds) as client:
            response = await client.post(endpoint, json={"spec": preview["video_spec"]})
    except httpx.HTTPError as exc:
        raise ScrubTargetError(f"continuous preview request failed: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise ScrubTargetError(f"continuous preview failed with renderer status {response.status_code}")
    video = response.content
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
