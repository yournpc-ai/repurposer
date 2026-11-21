"""Typed, user-safe evidence carried by settled Activity frames.

Full tool observations remain model-facing. This module selects only the
world facts Worked may display; source code, raw provider payloads, storage
internals and unverified judgments never enter the receipt sideband.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from pydantic import BaseModel, Field


VideoReviewIssueCode = Literal[
    "AUDIO_MISSING",
    "AUDIO_DECODE_FAILED",
    "AUDIO_SILENT",
    "AUDIO_QUIET",
    "AUDIO_CLIPPED",
]
_OUTPUT_ISSUE_CODES = frozenset({
    "AUDIO_MISSING",
    "AUDIO_DECODE_FAILED",
    "AUDIO_SILENT",
    "AUDIO_QUIET",
    "AUDIO_CLIPPED",
})


class SkillReadReceipt(BaseModel):
    """Successful package evidence reusable after a failed or settled turn."""

    kind: Literal["skill_read"] = "skill_read"
    package_identity: str = Field(min_length=1)
    skill_reference: dict[str, Any]
    owner_id: str | None = None
    reads: list[dict[str, Any]] = []
    preview_checks: list[dict[str, Any]] = []
    media_files: int = Field(ge=0)


class VideoReviewFrameReceipt(BaseModel):
    frame_id: str = Field(min_length=1)
    time_seconds: float = Field(ge=0, allow_inf_nan=False)


class VideoReviewFindingReceipt(BaseModel):
    kind: Literal["observed_issue", "aesthetic_suggestion"]
    frame_id: str = Field(min_length=1)
    observed: str = Field(min_length=1)


class VideoReviewScopeReceipt(BaseModel):
    actual_output_decoded: bool
    static_frames_checked: bool
    deterministic_output_checks: bool
    sampled_frame_signals_checked: bool
    audio_signal_checked: bool
    motion_and_transitions_checked: bool
    audio_and_av_sync_checked: bool


class VideoReviewReceipt(BaseModel):
    kind: Literal["video_review"] = "video_review"
    frames: list[VideoReviewFrameReceipt]
    findings: list[VideoReviewFindingReceipt]
    output_issue_codes: list[VideoReviewIssueCode]
    scope: VideoReviewScopeReceipt


class ComponentClipReceipt(BaseModel):
    clip_id: str = Field(min_length=1)
    program_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    poster_url: str = Field(min_length=1)
    preview_frame: int = Field(ge=0)
    dynamic_sample_frames: list[int] = Field(min_length=2)
    duration_frames: int = Field(gt=0)
    fps: int = Field(gt=0)


class ComponentReceipt(BaseModel):
    kind: Literal["component"] = "component"
    components: list[ComponentClipReceipt] = Field(min_length=1)


class VideoRevisionMovedSceneReceipt(BaseModel):
    scene_id: str = Field(min_length=1)
    from_seconds: float = Field(ge=0, allow_inf_nan=False)
    to_seconds: float = Field(ge=0, allow_inf_nan=False)


class VideoRevisionSceneReceipt(BaseModel):
    added: list[str] = []
    removed: list[str] = []
    moved: list[VideoRevisionMovedSceneReceipt] = []


class VideoRevisionAddedClipReceipt(BaseModel):
    clip_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)


class VideoRevisionUpdatedClipReceipt(BaseModel):
    clip_id: str = Field(min_length=1)
    changes: list[
        Literal["range", "object", "animations", "scene_id", "source", "linked_group_id"]
    ] = Field(min_length=1)


class VideoRevisionClipReceipt(BaseModel):
    added: list[VideoRevisionAddedClipReceipt] = []
    removed: list[str] = []
    updated: list[VideoRevisionUpdatedClipReceipt] = []


class VideoRevisionReceipt(BaseModel):
    kind: Literal["video_revision"] = "video_revision"
    version: int = Field(ge=1)
    settings: list[str] = []
    scenes: VideoRevisionSceneReceipt
    clips: VideoRevisionClipReceipt
    transitions_changed: bool
    components: list[ComponentClipReceipt] = []


class AudioCandidateReceipt(BaseModel):
    member_index: int = Field(ge=0)
    ordinal: int = Field(ge=1)
    title: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)


class SfxSearchReceipt(BaseModel):
    kind: Literal["sfx_search"] = "sfx_search"
    candidate_set_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    members: list[AudioCandidateReceipt] = Field(min_length=1)


class SfxImportReceipt(BaseModel):
    kind: Literal["sfx_import"] = "sfx_import"
    candidate_set_id: str = Field(min_length=1)
    member_index: int = Field(ge=0)
    asset_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)


class MusicSearchReceipt(BaseModel):
    kind: Literal["music_search"] = "music_search"
    candidate_set_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    members: list[AudioCandidateReceipt] = Field(min_length=1)


class MusicSelectionReceipt(BaseModel):
    kind: Literal["music_selection"] = "music_selection"
    candidate_set_id: str = Field(min_length=1)
    member_index: int = Field(ge=0)
    music_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)


ActivityReceipt = (
    VideoReviewReceipt
    | ComponentReceipt
    | VideoRevisionReceipt
    | SfxSearchReceipt
    | SfxImportReceipt
    | MusicSearchReceipt
    | MusicSelectionReceipt
    | SkillReadReceipt
)


def video_review_receipt(report: Mapping[str, Any]) -> VideoReviewReceipt | None:
    """Select the current report's displayable facts; never invent a category.

    Empty findings mean no content findings in the sampled frames, not a
    review pass. Unknown output issue codes are ignored while the original
    report remains untouched. A malformed report simply has no Activity
    receipt; it must not change tool or Activity lifecycle semantics.
    """
    if not isinstance(report, Mapping):
        return None
    try:
        frames = [VideoReviewFrameReceipt.model_validate(frame) for frame in report["frames"]]
        findings = [
            VideoReviewFindingReceipt.model_validate(finding)
            for finding in report["findings"]
        ]
        scope = VideoReviewScopeReceipt.model_validate(report["scope"])
    except (KeyError, TypeError, ValueError):
        return None

    inspection = report.get("media_inspection") or {}
    raw_issues = inspection.get("issues", []) if isinstance(inspection, Mapping) else []
    output_issue_codes: list[VideoReviewIssueCode] = []
    if isinstance(raw_issues, list):
        for issue in raw_issues:
            if not isinstance(issue, Mapping):
                continue
            code = issue.get("code")
            if isinstance(code, str) and code in _OUTPUT_ISSUE_CODES:
                output_issue_codes.append(cast(VideoReviewIssueCode, code))

    return VideoReviewReceipt(
        frames=frames,
        findings=findings,
        output_issue_codes=output_issue_codes,
        scope=scope,
    )


def _component_clip_evidence(
    read: Mapping[str, Any], *, clip_ids: set[str] | None = None
) -> list[ComponentClipReceipt]:
    """Join saved component clips to their exact enriched preview facts."""
    storyboard = read.get("storyboard")
    if not isinstance(storyboard, Mapping):
        return []
    clips = [
        clip
        for scene in storyboard.get("scenes", [])
        if isinstance(scene, Mapping)
        for clip in scene.get("clips", [])
        if isinstance(clip, Mapping)
    ] + [
        clip
        for clip in storyboard.get("unassigned_clips", [])
        if isinstance(clip, Mapping)
    ]
    by_id = {
        clip.get("clip_id"): clip
        for clip in clips
        if isinstance(clip.get("clip_id"), str)
        and clip.get("producer") == "remotion-project"
    }
    previews = read.get("generator_previews")
    if not isinstance(previews, list):
        return []

    evidence: list[ComponentClipReceipt] = []
    for preview in previews:
        if not isinstance(preview, Mapping):
            continue
        clip_id = preview.get("clip_id")
        clip = by_id.get(clip_id)
        if clip is None or (clip_ids is not None and clip_id not in clip_ids):
            continue
        if preview.get("program_digest") != clip.get("program_digest"):
            continue
        diagnostics = preview.get("diagnostics")
        output = preview.get("output")
        if not isinstance(diagnostics, Mapping) or not isinstance(output, Mapping):
            continue
        try:
            evidence.append(ComponentClipReceipt.model_validate({
                "clip_id": clip_id,
                "program_digest": preview["program_digest"],
                "media_digest": preview["media_digest"],
                "poster_url": preview["poster_url"],
                "preview_frame": diagnostics["preview_frame"],
                "dynamic_sample_frames": diagnostics["dynamic_sample_frames"],
                "duration_frames": output["duration_frames"],
                "fps": output["fps"],
            }))
        except (KeyError, TypeError, ValueError):
            continue
    return evidence


def component_receipt(read: Mapping[str, Any]) -> ComponentReceipt | None:
    components = _component_clip_evidence(read)
    return ComponentReceipt(components=components) if components else None


def video_revision_receipt(
    read: Mapping[str, Any], *, component_clip_ids: set[str] | None = None
) -> VideoRevisionReceipt | None:
    """Project the system delta, dropping raw before/after values and code."""
    change_set = read.get("change_set")
    if not isinstance(change_set, Mapping):
        return None
    try:
        return VideoRevisionReceipt(
            version=read["version"],
            settings=sorted((change_set.get("settings") or {}).keys()),
            scenes=VideoRevisionSceneReceipt.model_validate(change_set.get("scenes") or {}),
            clips=VideoRevisionClipReceipt.model_validate(change_set.get("clips") or {}),
            transitions_changed="transitions" in change_set,
            components=_component_clip_evidence(read, clip_ids=component_clip_ids),
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def sfx_search_receipt(facts: Mapping[str, Any]) -> SfxSearchReceipt | None:
    try:
        return SfxSearchReceipt.model_validate(facts)
    except (TypeError, ValueError):
        return None


def sfx_import_receipt(
    facts: Mapping[str, Any], *, candidate_set_id: Any, member_index: int
) -> SfxImportReceipt | None:
    try:
        return SfxImportReceipt.model_validate({
            **facts,
            "candidate_set_id": str(candidate_set_id),
            "member_index": member_index,
        })
    except (TypeError, ValueError):
        return None


def music_search_receipt(facts: Mapping[str, Any]) -> MusicSearchReceipt | None:
    try:
        return MusicSearchReceipt.model_validate(facts)
    except (TypeError, ValueError):
        return None


def music_selection_receipt(
    facts: Mapping[str, Any], *, candidate_set_id: Any, member_index: int
) -> MusicSelectionReceipt | None:
    try:
        return MusicSelectionReceipt.model_validate({
            **facts,
            "candidate_set_id": str(candidate_set_id),
            "member_index": member_index,
        })
    except (TypeError, ValueError):
        return None


__all__ = [
    "ActivityReceipt",
    "ComponentClipReceipt",
    "ComponentReceipt",
    "MusicSearchReceipt",
    "MusicSelectionReceipt",
    "SfxImportReceipt",
    "SfxSearchReceipt",
    "VideoReviewReceipt",
    "VideoRevisionReceipt",
    "component_receipt",
    "music_search_receipt",
    "music_selection_receipt",
    "sfx_import_receipt",
    "sfx_search_receipt",
    "video_review_receipt",
    "video_revision_receipt",
]
