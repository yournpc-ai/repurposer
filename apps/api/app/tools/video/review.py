"""Frame-evidenced content review of one exact delivered video Output.

The reviewer sees decoded pixels from the Output's own media, never a fresh
render or the Composition's current head. ``render_probe`` remains the media
file's hard-check seat; this module adds advisory content review and separate
deterministic sampled-frame/audio-signal observations. Its report lives on
that Output's existing quality read face.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any, Literal
from uuid import UUID

import av
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.service import format_storyboard_text, video_version_read
from app.models.schemas import MediaInput, MediaInputType, ReviewVideoArgs
from app.models.tables import CompositionVersion, Conversation, Message, Output, Project
from app.providers import storage
from app.providers.llm.base import LLMError
from app.tools.video.output_checks import (
    OUTPUT_CHECKER_VERSION,
    FrameSample,
    OutputInspection,
    inspect_output_media,
)

_MAX_SCENE_FRAMES = 16
_MOTION_SAMPLES_PER_SECOND = 2
_FRAME_LONG_EDGE = 1280
_REVIEW_SCHEMA_VERSION = 4


class ReviewError(ValueError):
    """An honest review refusal (wrong identity, undelivered or undecodable)."""


class ReviewAttemptFailed(ReviewError):
    """The reviewer exhausted its bounded repair without a legal report."""

    def __init__(self, *, previous_report: dict[str, Any] | None) -> None:
        super().__init__("the reviewer did not produce a valid content report")
        self.previous_report = previous_report


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_observed_aliases(cls, data: Any) -> Any:
        """Accept only witnessed synonyms; server-owned facts stay server-owned."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for alias, canonical in (
            ("type", "kind"),
            ("observed_issue", "observed"),
            ("visual_evidence", "evidence"),
            ("smallest_useful_change", "suggestion"),
        ):
            if alias in data and data.get(canonical) is None:
                data[canonical] = data.pop(alias)
        # These frequently echoed values never override decoded/spec facts.
        data.pop("actual_time_seconds", None)
        data.pop("scene_id", None)
        return data

    kind: Literal["observed_issue", "aesthetic_suggestion"]
    frame_id: str = Field(min_length=2, max_length=8)
    observed: str = Field(min_length=1, max_length=600)
    requirement: str | None = Field(default=None, max_length=400)
    evidence: str | None = Field(default=None, max_length=600)
    suggestion: str = Field(min_length=1, max_length=400)
    clip_id: str | None = Field(default=None, max_length=100)
    object_id: str | None = Field(default=None, max_length=100)


class ContentReviewAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_identity_echoes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # The report's identity comes only from the fetched Output. These three
        # known prompt echoes are discarded, not trusted; every other extra
        # field remains a schema error and receives the normal repair feedback.
        for key in ("output_id", "composition_id", "composition_version_id"):
            data.pop(key, None)
        if data.get("findings") is None:
            data["findings"] = []
        return data

    summary: str | None = Field(default=None, max_length=1000)
    findings: list[ReviewFinding] = Field(default=[], max_length=8)


@dataclass
class ReviewFrame:
    frame_id: str
    frame: int
    time_seconds: float
    scene_id: str | None
    jpeg: bytes
    digest: str
    storage_key: str


def _fps(spec: dict[str, Any]) -> Fraction:
    raw = spec.get("fps") or {}
    fps = Fraction(int(raw.get("num") or 30), int(raw.get("den") or 1))
    if fps <= 0:
        raise ReviewError("the executed video spec has no usable frame rate")
    return fps


def _active_transitions(spec: dict[str, Any], frame: int) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for tr in spec.get("transitions") or []:
        t_start = int(tr.get("start_frame") or 0)
        t_end = int(tr.get("end_frame") or 0)
        if t_start <= frame < t_end:
            active.append({
                "kind": tr.get("kind"),
                "start_frame": t_start,
                "end_frame": t_end,
            })
    return active


def _settled_subinterval(
    start: int, stop: int, transitions: list[tuple[int, int]]
) -> tuple[int, int] | None:
    """Return the widest sub-interval of [start, stop) outside transition windows, or None."""
    segments = [(start, stop)]
    for t_start, t_end in transitions:
        next_segments: list[tuple[int, int]] = []
        for s_start, s_stop in segments:
            if t_end <= s_start or t_start >= s_stop:
                next_segments.append((s_start, s_stop))
            else:
                if s_start < t_start:
                    next_segments.append((s_start, t_start))
                if t_end < s_stop:
                    next_segments.append((t_end, s_stop))
        segments = next_segments
        if not segments:
            return None
    return max(segments, key=lambda seg: seg[1] - seg[0])


def _visual_targets(spec: dict[str, Any]) -> list[tuple[Fraction, str | None]]:
    """Sample each distinct visual interval, preferring settled frames outside transitions."""
    end = int(spec["duration_frames"])
    clips = [clip for track in spec.get("tracks", []) if track.get("kind") == "visual"
             for clip in track.get("clips", [])]
    cuts = sorted({0, end, *(clip[key] for clip in clips for key in ("start_frame", "end_frame")
                             if 0 < clip[key] < end)})
    transitions = [
        (int(tr.get("start_frame") or 0), int(tr.get("end_frame") or 0))
        for tr in (spec.get("transitions") or [])
        if int(tr.get("end_frame") or 0) > int(tr.get("start_frame") or 0)
    ]
    raw_intervals = list(zip(cuts, cuts[1:]))
    settled_intervals = [
        settled
        for start, stop in raw_intervals
        if (settled := _settled_subinterval(start, stop, transitions)) is not None
    ]
    intervals = settled_intervals or raw_intervals
    if len(intervals) > _MAX_SCENE_FRAMES:
        intervals = [intervals[round(i * (len(intervals) - 1) / (_MAX_SCENE_FRAMES - 1))]
                     for i in range(_MAX_SCENE_FRAMES)]
    targets = []
    for start, stop in intervals:
        frame = Fraction(start + stop, 2)
        scenes = {c.get("scene_id") for c in clips if c["start_frame"] <= frame < c["end_frame"]}
        targets.append((frame, scenes.pop() if len(scenes) == 1 else None))
    return targets


def _scene_window(spec: dict[str, Any], scene_id: str) -> tuple[int, int]:
    """Resolve one exact executed Scene's union of clip windows."""
    duration_frames = int(spec.get("duration_frames") or 0)
    if duration_frames <= 0:
        raise ReviewError("the executed video spec has no duration")
    windows: list[tuple[int, int]] = []
    for track in spec.get("tracks") or []:
        for clip in track.get("clips") or []:
            if clip.get("scene_id") != scene_id:
                continue
            start, end = clip.get("start_frame"), clip.get("end_frame")
            if type(start) is not int or type(end) is not int:
                raise ReviewError(f"Scene {scene_id!r} has a non-integer clip window")
            if end == start:
                raise ReviewError(f"Scene {scene_id!r} has an empty clip window")
            if end < start:
                raise ReviewError(f"Scene {scene_id!r} has an inverted clip window")
            if start < 0 or end > duration_frames:
                raise ReviewError(f"Scene {scene_id!r} has a clip window outside this Output")
            windows.append((start, end))
    if not windows:
        raise ReviewError(f"Scene {scene_id!r} does not exist in this Output's executed spec")
    return min(start for start, _ in windows), max(end for _, end in windows)


def _motion_frame_numbers(window: tuple[int, int], fps: Fraction) -> list[int]:
    """Plan unique ordered frames at about 2fps, including both scene edges."""
    start, end = window
    frame_count = end - start
    if frame_count <= 0:
        raise ReviewError("the requested motion Scene has no executable frames")
    if frame_count <= _MAX_SCENE_FRAMES:
        return list(range(start, end))
    duration = Fraction(frame_count, 1) / fps
    desired = max(2, math.ceil(duration * _MOTION_SAMPLES_PER_SECOND) + 1)
    count = min(frame_count, _MAX_SCENE_FRAMES, desired)
    if count == 1:
        return [start]
    if desired <= _MAX_SCENE_FRAMES:
        step = fps / _MOTION_SAMPLES_PER_SECOND
        return sorted({start + min(frame_count - 1, round(index * step))
                       for index in range(count - 1)} | {end - 1})
    # count <= frame_count keeps the rounded targets unique without decoding
    # the same frame repeatedly to fill a quota.
    return [
        start + round(index * (frame_count - 1) / (count - 1))
        for index in range(count)
    ]


def _active_clip_facts(spec: dict[str, Any], frame: int) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for track in spec.get("tracks") or []:
        for clip in track.get("clips") or []:
            if not (int(clip.get("start_frame") or 0) <= frame < int(clip.get("end_frame") or 0)):
                continue
            obj = clip.get("object") or {}
            fact = {
                "clip_id": clip.get("clip_id"),
                "object_id": obj.get("object_id"),
                "kind": obj.get("kind"),
            }
            if obj.get("text") is not None:
                fact["text"] = obj["text"]
            facts.append(fact)
    return facts


def _frame_facts(frames: list[ReviewFrame], spec: dict[str, Any]) -> str:
    rows: list[str] = []
    for frame in frames:
        active_transitions = _active_transitions(spec, frame.frame)
        row: dict[str, Any] = {
            "frame_id": frame.frame_id,
            "actual_time_seconds": frame.time_seconds,
            "actual_frame": frame.frame,
            "scene_id": frame.scene_id,
            "active_clips": _active_clip_facts(spec, frame.frame),
        }
        if active_transitions:
            row["in_transition"] = True
            row["active_transitions"] = active_transitions
        rows.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(rows)


def _jpeg(frame: av.VideoFrame) -> bytes:
    image = frame.to_image().convert("RGB")
    image.thumbnail((_FRAME_LONG_EDGE, _FRAME_LONG_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def _decode_frame(
    container: av.container.InputContainer,
    stream: av.VideoStream,
    target: Fraction,
    fps: Fraction,
) -> tuple[av.VideoFrame, Fraction]:
    timestamp = int(target / stream.time_base)
    container.seek(max(0, timestamp), stream=stream, backward=True, any_frame=False)
    tolerance = Fraction(1, 2) / fps
    for frame in container.decode(stream):
        if frame.time is None:
            continue
        actual = Fraction(frame.time).limit_denominator(1000000)
        if actual + tolerance >= target:
            return frame, actual
    raise ReviewError(f"no decodable frame at requested time {float(target):.3f}s")


def representative_source_frames(
    path: Any, *, duration_seconds: float, max_frames: int = 3
) -> list[ReviewFrame]:
    """Decode bounded source stills with the review path's real frame decoder."""
    if duration_seconds <= 0 or max_frames < 1:
        raise ReviewError("representative source frames need a real duration and frame budget")
    with av.open(str(path), mode="r") as container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            raise ReviewError("the source has no decodable video stream")
        fps = Fraction(stream.average_rate or 30)
        duration = Fraction(str(duration_seconds))
        targets = [Fraction(0)] if max_frames == 1 else [
            duration * index / (max_frames - 1) for index in range(max_frames)
        ]
        targets[-1] = max(Fraction(0), duration - 1 / fps)
        frames: list[ReviewFrame] = []
        for index, target in enumerate(targets, start=1):
            decoded, actual = _decode_frame(container, stream, target, fps)
            jpeg = _jpeg(decoded)
            frames.append(ReviewFrame(
                frame_id=f"F{index:02d}",
                frame=max(0, int(actual * fps)),
                time_seconds=float(actual),
                scene_id=None,
                jpeg=jpeg,
                digest=hashlib.sha256(jpeg).hexdigest(),
                storage_key="",
            ))
        return frames


async def _store_frame(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    key = f"video-review/{digest}.jpg"
    if await storage.exists(key):
        if hashlib.sha256(await storage.read(key)).hexdigest() != digest:
            raise ReviewError("an immutable review frame does not match its digest")
    else:
        await storage.save(key, data, content_type="image/jpeg")
    return key, digest


async def _extract_frames(
    video: bytes,
    spec: dict[str, Any],
    at_seconds: list[float] | None,
    motion_scene_id: str | None = None,
) -> list[ReviewFrame]:
    fps = _fps(spec)
    duration_frames = int(spec.get("duration_frames") or 0)
    if duration_frames <= 0:
        raise ReviewError("the executed video spec has no duration")
    if at_seconds is not None and motion_scene_id is not None:
        raise ReviewError("at_seconds and motion_scene_id are mutually exclusive")
    targets: list[tuple[Fraction, str | None]] = []
    motion_window: tuple[int, int] | None = None
    if motion_scene_id is not None:
        # A motion review consumes only its own Scene sequence. It is never
        # stacked with the default whole-film sample to evade either budget.
        motion_window = _scene_window(spec, motion_scene_id)
        targets.extend(
            (Fraction(frame_number), motion_scene_id)
            for frame_number in _motion_frame_numbers(motion_window, fps)
        )
    elif at_seconds:
        # A focused recheck is defined by its requested times; do not inflate it
        # with a second whole-film scene sample.
        for seconds in at_seconds:
            if seconds < 0 or seconds * float(fps) >= duration_frames:
                raise ReviewError(f"requested review time {seconds:g}s is outside this Output")
            targets.append((Fraction(str(seconds)) * fps, None))
    else:
        targets.extend(_visual_targets(spec))

    # Exact requested times take priority; duplicate targets decode only once.
    unique: dict[int, tuple[Fraction, str | None]] = {}
    for target, scene_id in targets:
        frame_number = max(0, min(duration_frames - 1, int(target)))
        unique.setdefault(frame_number, (target, scene_id))
    if len(unique) > _MAX_SCENE_FRAMES + 4 or (
        motion_scene_id is not None and len(unique) > _MAX_SCENE_FRAMES
    ):
        raise ReviewError("the review frame budget is exhausted")

    frames: list[ReviewFrame] = []
    with av.open(io.BytesIO(video), mode="r") as container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            raise ReviewError("the Output has no decodable video stream")
        for frame_number, (target, scene_id) in sorted(unique.items()):
            decoded, actual = _decode_frame(container, stream, Fraction(frame_number) / fps, fps)
            jpeg = _jpeg(decoded)
            key, digest = await _store_frame(jpeg)
            actual_frame = max(0, min(duration_frames - 1, int(actual * fps)))
            if motion_window is not None and not (
                motion_window[0] <= actual_frame < motion_window[1]
            ):
                raise ReviewError("a decoded motion sample fell outside the requested Scene")
            frames.append(
                ReviewFrame(
                    frame_id="",
                    frame=actual_frame,
                    time_seconds=float(actual),
                    scene_id=scene_id,
                    jpeg=jpeg,
                    digest=digest,
                    storage_key=key,
                )
            )
    frames.sort(key=lambda item: (item.time_seconds, item.digest))
    for index, frame in enumerate(frames, start=1):
        frame.frame_id = f"F{index:02d}"
    if not frames:
        raise ReviewError("no actual video frames could be decoded")
    return frames


def _motion_sampling_facts(
    frames: list[ReviewFrame], spec: dict[str, Any], scene_id: str
) -> dict[str, Any]:
    """Describe only the actual decoded sequence, never its requested plan."""
    if not frames or any(frame.scene_id != scene_id for frame in frames):
        raise ReviewError("the requested Scene produced no coherent motion sequence")
    start, end = _scene_window(spec, scene_id)
    fps = _fps(spec)
    ordered = sorted(frames, key=lambda frame: (frame.time_seconds, frame.frame))
    intervals = [
        later.time_seconds - earlier.time_seconds
        for earlier, later in zip(ordered, ordered[1:], strict=False)
    ]
    return {
        "scene_id": scene_id,
        "scene_start_frame": start,
        "scene_end_frame_exclusive": end,
        "last_executable_frame": end - 1,
        "scene_start_time_seconds": float(Fraction(start, 1) / fps),
        "scene_end_time_seconds_exclusive": float(Fraction(end, 1) / fps),
        "first_sample_frame": ordered[0].frame,
        "first_sample_time_seconds": ordered[0].time_seconds,
        "last_sample_frame": ordered[-1].frame,
        "last_sample_time_seconds": ordered[-1].time_seconds,
        "sampled_frame_count": len(ordered),
        "min_adjacent_sample_interval_seconds": (
            round(min(intervals), 6) if intervals else None
        ),
        "max_adjacent_sample_interval_seconds": (
            round(max(intervals), 6) if intervals else None
        ),
        "ordered_frame_ids": [frame.frame_id for frame in ordered],
    }


def _report_findings(
    answer: ContentReviewAnswer,
    frames: list[ReviewFrame],
    spec: dict[str, Any],
    requirements: str,
) -> list[dict[str, Any]]:
    by_id = {frame.frame_id: frame for frame in frames}
    findings: list[dict[str, Any]] = []
    for finding in answer.findings:
        frame = by_id.get(finding.frame_id)
        if frame is None:
            raise ReviewError(f"the reviewer cited unknown frame {finding.frame_id!r}")
        active = _active_clip_facts(spec, frame.frame)
        clip = next((item for item in active if item.get("clip_id") == finding.clip_id), None)
        object_id = finding.object_id if clip and clip.get("object_id") == finding.object_id else None
        findings.append(
            {
                "kind": finding.kind,
                "frame_id": frame.frame_id,
                "time_seconds": frame.time_seconds,
                "frame": frame.frame,
                "scene_id": frame.scene_id,
                "observed": finding.observed,
                # A missing prose slot must not erase an otherwise grounded
                # observation. Reuse the exact request / observed pixels rather
                # than inventing a more specific requirement or evidence claim.
                "requirement": finding.requirement or requirements,
                "evidence": finding.evidence or finding.observed,
                "suggestion": finding.suggestion,
                # Time evidence survives when identity cannot be proven.
                "clip_id": clip.get("clip_id") if clip else None,
                "object_id": object_id,
            }
        )
    return findings


def _media_inputs(frames: list[ReviewFrame]) -> list[MediaInput]:
    return [
        MediaInput(
            type=MediaInputType.IMAGE,
            mime="image/jpeg",
            data_url="data:image/jpeg;base64," + base64.b64encode(frame.jpeg).decode("ascii"),
            caption=(
                f"{frame.frame_id} — actual decoded Output frame {frame.frame}, "
                f"t={frame.time_seconds:.3f}s, scene={frame.scene_id or 'unspecified'}"
            ),
        )
        for frame in frames
    ]


def _build_review_report(
    *,
    output_facts: dict[str, Any],
    args: ReviewVideoArgs,
    requirements: str,
    answer: ContentReviewAnswer,
    frames: list[ReviewFrame],
    spec: dict[str, Any],
    inspection: OutputInspection,
    motion_sampling: dict[str, Any] | None,
) -> dict[str, Any]:
    motion_scene_id = motion_sampling.get("scene_id") if motion_sampling else None
    limitations = [
        "Findings are based on the listed decoded frames and their actual sampling "
        "coverage, not continuous motion playback.",
    ]
    if motion_scene_id is not None:
        limitations.append(
            f"Only Scene {motion_scene_id!r} has an ordered discrete-frame motion sequence; "
            "other Scenes and all inter-Scene transitions were not motion-reviewed. "
            "Adjacent samples do not prove the state of every intermediate frame."
        )
    else:
        limitations.append(
            "No ordered per-Scene motion sequence was decoded; motion between samples "
            "and inter-Scene transitions were not checked."
        )
    limitations.extend([
        "Flat or repeated sampled frames are candidates for inspection, not proof of a "
        "defect; an intentional final reading hold is not by itself a defect.",
        "Audio stream presence and PCM levels are measured; perceived mix quality and "
        "audio-visual synchronization are not reviewed.",
        "RMS and peak dBFS are not BS.1770 integrated LUFS.",
    ])
    return {
        "schema_version": _REVIEW_SCHEMA_VERSION,
        "output_id": output_facts["output_id"],
        "composition_id": output_facts["composition_id"],
        "composition_version_id": output_facts["composition_version_id"],
        "content_digest": output_facts["content_digest"],
        "execution_digest": output_facts["execution_digest"],
        "video_sha256": output_facts["video_sha256"],
        "reviewed_at": datetime.now(UTC).isoformat(),
        "requirements": requirements,
        "at_seconds": args.at_seconds,
        "motion_scene_id": motion_scene_id,
        "motion_sampling": motion_sampling,
        "summary": answer.summary or "",
        "scope": {
            "actual_output_decoded": True,
            "static_frames_checked": True,
            "deterministic_output_checks": True,
            "sampled_frame_signals_checked": True,
            "audio_signal_checked": inspection.audio.decode_ok,
            # Continuous playback and complete transition review remain unchecked;
            # the fine-grained list below is the actual discrete-motion scope.
            "motion_and_transitions_checked": False,
            "motion_reviewed_scene_ids": (
                [motion_scene_id] if motion_scene_id is not None else []
            ),
            "audio_and_av_sync_checked": False,
        },
        "limitations": limitations,
        "media_inspection": inspection.model_dump(mode="json"),
        "frames": [
            {
                "frame_id": frame.frame_id,
                "time_seconds": frame.time_seconds,
                "frame": frame.frame,
                "scene_id": frame.scene_id,
                "storage_key": frame.storage_key,
                "digest": frame.digest,
            }
            for frame in frames
        ],
        "findings": _report_findings(answer, frames, spec, requirements),
    }


def _reusable_report(
    quality: dict[str, Any] | None,
    output_id: UUID,
    video_sha256: str,
    args: ReviewVideoArgs,
    requirements: str,
) -> dict[str, Any] | None:
    saved = (quality or {}).get("content_review")
    if (
        args.refresh
        or not isinstance(saved, dict)
        or saved.get("output_id") != str(output_id)
        or saved.get("video_sha256") != video_sha256
        or saved.get("requirements") != requirements
        or saved.get("schema_version") != _REVIEW_SCHEMA_VERSION
        or (saved.get("media_inspection") or {}).get("checker_version")
        != OUTPUT_CHECKER_VERSION
        # Older reports have no sampling metadata: they cannot prove that
        # they cover this request, so they are never reused by implication.
        or "at_seconds" not in saved
        or saved["at_seconds"] != args.at_seconds
        or "motion_scene_id" not in saved
        or saved["motion_scene_id"] != args.motion_scene_id
    ):
        return None
    if args.motion_scene_id is None:
        return saved if saved.get("motion_sampling") is None else None
    sampling = saved.get("motion_sampling")
    scope = saved.get("scope")
    required_sampling_facts = {
        "scene_id",
        "scene_start_frame",
        "scene_end_frame_exclusive",
        "last_executable_frame",
        "scene_start_time_seconds",
        "scene_end_time_seconds_exclusive",
        "first_sample_frame",
        "first_sample_time_seconds",
        "last_sample_frame",
        "last_sample_time_seconds",
        "sampled_frame_count",
        "min_adjacent_sample_interval_seconds",
        "max_adjacent_sample_interval_seconds",
        "ordered_frame_ids",
    }
    if (
        not isinstance(sampling, dict)
        or not required_sampling_facts.issubset(sampling)
        or sampling.get("scene_id") != args.motion_scene_id
        or not isinstance(scope, dict)
        or scope.get("motion_reviewed_scene_ids") != [args.motion_scene_id]
    ):
        return None
    return saved


def _previous_review_facts(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """Carry earlier world facts forward without recycling prose as evidence."""
    if report is None:
        return None
    return {
        "requirements": report.get("requirements"),
        "at_seconds": report.get("at_seconds"),
        "motion_scene_id": report.get("motion_scene_id"),
        "motion_sampling": report.get("motion_sampling"),
        "reviewed_at": report.get("reviewed_at"),
        "scope": report.get("scope"),
        "media_inspection": report.get("media_inspection"),
    }


async def read_output_video(key: str) -> bytes:
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        return await storage.read(key)
    except (BotoCoreError, ClientError, OSError) as exc:
        raise ReviewError("The delivered MP4 cannot be read from storage.") from exc


async def _user_review_requirements(db, *, opening_id: UUID, output: Output, owner_id: UUID) -> str:
    opening = await db.scalar(select(Message).join(Conversation).where(
        Message.id == opening_id, Message.role == "user", Conversation.user_id == owner_id,
        Conversation.project_id == output.project_id,
    ))
    if opening is None:
        raise ReviewError("The review requires the user's opening in this project.")
    # The creation and edit requests refer to the exact exported lineage, including
    # when a later opening has already changed the composition's current version.
    pinned = await db.get(CompositionVersion, output.composition_version_id)
    if pinned is None or pinned.composition_id != output.composition_id:
        raise ReviewError("The exported version is unavailable.")
    edit_marker = func.jsonb_build_array(func.jsonb_build_object("request", CompositionVersion.request_id))
    made_version = select(CompositionVersion.id).where(
        CompositionVersion.composition_id == pinned.composition_id,
        CompositionVersion.version <= pinned.version,
        CompositionVersion.request_id.is_not(None),
        Message.intent["editor_commits"].contains(edit_marker),
    ).exists()
    prior = list(await db.scalars(select(Message.content).where(
        Message.conversation_id == opening.conversation_id, Message.role == "user",
        Message.seq < opening.seq, made_version,
    ).order_by(Message.seq.desc()).limit(4)))
    comparison = {}
    if pinned.base_version_id:
        from app.editing.store import content_of
        from app.editing.temporal import timeline_duration

        parent = await db.get(CompositionVersion, pinned.base_version_id)
        if parent and parent.composition_id == pinned.composition_id:
            durations = {}
            for label, version in (("parent", parent), ("exported", pinned)):
                content = content_of(version)
                durations[label] = {"version": version.version,
                                    "seconds": timeline_duration(content) / content.settings.timebase}
            comparison["immutable_version_durations"] = durations
    return json.dumps({
        **comparison,
        "current_user_request": opening.content,
        "prior_user_requests_for_this_work": list(reversed(prior)),
    }, ensure_ascii=False)


async def review_video(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    opening_id: UUID,
    args: ReviewVideoArgs,
) -> dict[str, Any]:
    output = await db.scalar(
        select(Output)
        .join(Project, Output.project_id == Project.id)
        .where(Output.id == args.output_id, Output.project_id == project_id, Project.user_id == owner_id)
    )
    if output is None or output.type != "video":
        raise ReviewError("no accessible delivered video Output at this exact id")
    video_key = (output.files or {}).get("video")
    render_status = getattr(output.render_status, "value", output.render_status)
    if render_status != "completed" or not isinstance(video_key, str) or not video_key:
        raise ReviewError("this Output has no completed delivered video file")
    spec = output.render_spec or {}
    pinned = {
        "composition_id": str(output.composition_id or ""),
        "composition_version_id": str(output.composition_version_id or ""),
        "content_digest": (output.payload or {}).get("composition_digest"),
    }
    if (
        spec.get("family") != "video"
        or not all(pinned.values())
        or spec.get("provenance") != pinned
    ):
        raise ReviewError("the Output's executed spec does not match its pinned content version")

    # Cache identity includes the actual delivered bytes, not just the Output id.
    video = await read_output_video(video_key)
    video_sha256 = hashlib.sha256(video).hexdigest()
    requirements = await _user_review_requirements(db, opening_id=opening_id, output=output, owner_id=owner_id)
    saved = _reusable_report(output.quality, output.id, video_sha256, args, requirements)
    if (saved is not None and saved.get("file") and
            all(saved.get(k) == v for k, v in pinned.items())):
        return saved
    try:
        with av.open(io.BytesIO(video)) as container:
            stream = container.streams.video[0]
            file_facts = {
                "bytes": len(video), "width": stream.width, "height": stream.height,
                "video_codec": stream.codec_context.name, "video_frames": stream.frames,
                "video_seconds": float(stream.duration * stream.time_base) if stream.duration else None,
                "audio_codecs": [s.codec_context.name for s in container.streams.audio],
            }
    except (av.FFmpegError, IndexError) as exc:
        raise ReviewError("The Output contains no readable video stream.") from exc
    if [file_facts["width"], file_facts["height"]] != [spec.get("width"), spec.get("height")]:
        raise ReviewError("The decoded Output size differs from its executed spec.")

    # This read resolves the Output's exact version, including when it is old.
    read = await video_version_read(db, owner_id=owner_id, output_id=output.id)
    frames = await _extract_frames(
        video, spec, args.at_seconds, motion_scene_id=args.motion_scene_id
    )
    motion_sampling = (
        _motion_sampling_facts(frames, spec, args.motion_scene_id)
        if args.motion_scene_id is not None
        else None
    )
    inspection = inspect_output_media(
        video,
        spec,
        [FrameSample(frame.frame, frame.time_seconds, frame.jpeg) for frame in frames],
    )
    output_facts = {
        "output_id": str(output.id),
        **pinned,
        "execution_digest": (output.payload or {}).get("execution_digest"),
        "video_sha256": video_sha256, "file": file_facts,
        "duration_frames": spec.get("duration_frames"),
        "fps": str(_fps(spec)),
    }
    from app.tools.video.agents import video_reviewer  # deferred: declaration/import cycle

    saved_report = (output.quality or {}).get("content_review")
    previous_report = (
        saved_report
        if isinstance(saved_report, dict)
        and saved_report.get("output_id") == str(output.id)
        and saved_report.get("requirements") == requirements
        and saved_report.get("video_sha256") == output_facts["video_sha256"]
        else None
    )
    try:
        answer = await video_reviewer.call(
            requirements=requirements,
            output_facts=json.dumps(output_facts, ensure_ascii=False),
            storyboard=format_storyboard_text(read),
            frame_facts=_frame_facts(frames, spec),
            deterministic_checks=json.dumps(inspection.model_dump(mode="json"), ensure_ascii=False),
            motion_review=json.dumps(motion_sampling, ensure_ascii=False),
            previous_review_facts=json.dumps(
                _previous_review_facts(previous_report), ensure_ascii=False
            ),
            frames=_media_inputs(frames),
        )
    except LLMError as exc:
        # A failed focused recheck must not erase or inherit the earlier report's
        # success. The shared seat closes from these real world facts instead.
        raise ReviewAttemptFailed(previous_report=previous_report) from exc
    report = _build_review_report(
        output_facts=output_facts,
        args=args,
        requirements=requirements,
        answer=answer,
        frames=frames,
        spec=spec,
        inspection=inspection,
        motion_sampling=motion_sampling,
    )
    report["file"] = file_facts
    quality = dict(output.quality or {})
    quality["content_review"] = report
    output.quality = quality
    await db.commit()
    return report
