"""Typed, user-safe evidence carried by settled review Activity frames.

The full review report remains the model-facing observation and the Output's
quality record. This module selects only the evidence Worked may display.
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


__all__ = [
    "VideoReviewReceipt",
    "video_review_receipt",
]
