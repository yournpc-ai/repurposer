"""Frame-evidenced content review of one exact delivered video Output.

The reviewer sees decoded pixels from the Output's own media, never a fresh
render or the Composition's current head. ``render_probe`` remains the media
file's hard-check seat; this module adds only the first subjective read. Its
report is advisory and lives on that Output's existing quality read face.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any, Literal
from uuid import UUID

import av
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.service import format_storyboard_text, video_version_read
from app.models.schemas import MediaInput, MediaInputType, ReviewVideoArgs
from app.models.tables import Output, Project
from app.providers import storage

_MAX_SCENE_FRAMES = 16
_FRAME_LONG_EDGE = 1280


class ReviewError(ValueError):
    """An honest review refusal (wrong identity, undelivered or undecodable)."""


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


def _scene_targets(spec: dict[str, Any]) -> list[tuple[Fraction, str]]:
    """One settled-in frame per executed scene, using the spec's frame windows."""
    windows: dict[str, tuple[int, int]] = {}
    for track in spec.get("tracks") or []:
        for clip in track.get("clips") or []:
            scene_id = clip.get("scene_id")
            start, end = clip.get("start_frame"), clip.get("end_frame")
            if not scene_id or not isinstance(start, int) or not isinstance(end, int) or end <= start:
                continue
            previous = windows.get(str(scene_id))
            windows[str(scene_id)] = (
                min(previous[0], start) if previous else start,
                max(previous[1], end) if previous else end,
            )
    ordered = sorted(windows.items(), key=lambda item: item[1][0])
    if len(ordered) > _MAX_SCENE_FRAMES:
        # Bounded whole-film coverage without privileging only the opening.
        indexes = {round(i * (len(ordered) - 1) / (_MAX_SCENE_FRAMES - 1)) for i in range(_MAX_SCENE_FRAMES)}
        ordered = [ordered[i] for i in sorted(indexes)]
    return [
        (Fraction(start * 2 + (end - start), 2), scene_id)
        for scene_id, (start, end) in ordered
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
        rows.append(
            json.dumps(
                {
                    "frame_id": frame.frame_id,
                    "actual_time_seconds": frame.time_seconds,
                    "actual_frame": frame.frame,
                    "scene_id": frame.scene_id,
                    "active_clips": _active_clip_facts(spec, frame.frame),
                },
                ensure_ascii=False,
            )
        )
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
) -> list[ReviewFrame]:
    fps = _fps(spec)
    duration_frames = int(spec.get("duration_frames") or 0)
    if duration_frames <= 0:
        raise ReviewError("the executed video spec has no duration")
    targets: list[tuple[Fraction, str | None]] = []
    if at_seconds:
        # A focused recheck is defined by its requested times; do not inflate it
        # with a second whole-film scene sample.
        for seconds in at_seconds:
            if seconds < 0 or seconds * float(fps) >= duration_frames:
                raise ReviewError(f"requested review time {seconds:g}s is outside this Output")
            targets.append((Fraction(str(seconds)) * fps, None))
    else:
        targets.extend(_scene_targets(spec))

    # Exact requested times take priority; duplicate targets decode only once.
    unique: dict[int, tuple[Fraction, str | None]] = {}
    for target, scene_id in targets:
        frame_number = max(0, min(duration_frames - 1, int(target)))
        unique.setdefault(frame_number, (target, scene_id))
    if len(unique) > _MAX_SCENE_FRAMES + 4:
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


def _reusable_report(
    quality: dict[str, Any] | None,
    output_id: UUID,
    args: ReviewVideoArgs,
) -> dict[str, Any] | None:
    saved = (quality or {}).get("content_review")
    if (
        not args.refresh
        and isinstance(saved, dict)
        and saved.get("output_id") == str(output_id)
        and saved.get("requirements") == args.requirements
        # Older reports have no sampling metadata: they cannot prove that
        # they cover this request, so they are never reused by implication.
        and "at_seconds" in saved
        and saved["at_seconds"] == args.at_seconds
    ):
        return saved
    return None


async def review_video(
    db: AsyncSession,
    *,
    owner_id: UUID,
    args: ReviewVideoArgs,
) -> dict[str, Any]:
    output = await db.scalar(
        select(Output)
        .join(Project, Output.project_id == Project.id)
        .where(Output.id == args.output_id, Project.user_id == owner_id)
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

    saved = _reusable_report(output.quality, output.id, args)
    if saved is not None:
        return saved

    # This read resolves the Output's exact version, including when it is old.
    read = await video_version_read(db, owner_id=owner_id, output_id=output.id)
    video = await storage.read(video_key)
    frames = await _extract_frames(video, spec, args.at_seconds)
    output_facts = {
        "output_id": str(output.id),
        **pinned,
        "execution_digest": (output.payload or {}).get("execution_digest"),
        "video_sha256": hashlib.sha256(video).hexdigest(),
        "duration_frames": spec.get("duration_frames"),
        "fps": str(_fps(spec)),
    }
    from app.tools.video.agents import video_reviewer  # deferred: declaration/import cycle

    answer = await video_reviewer.call(
        requirements=args.requirements,
        output_facts=json.dumps(output_facts, ensure_ascii=False),
        storyboard=format_storyboard_text(read),
        frame_facts=_frame_facts(frames, spec),
        frames=_media_inputs(frames),
    )
    report = {
        "schema_version": 1,
        "output_id": str(output.id),
        **pinned,
        "execution_digest": output_facts["execution_digest"],
        "video_sha256": output_facts["video_sha256"],
        "reviewed_at": datetime.now(UTC).isoformat(),
        "requirements": args.requirements,
        "at_seconds": args.at_seconds,
        "summary": answer.summary or "",
        "scope": {
            "actual_output_decoded": True,
            "static_frames_checked": True,
            "motion_and_transitions_checked": False,
            "audio_and_av_sync_checked": False,
        },
        "limitations": [
            "Findings are based on the listed decoded still frames, not continuous motion playback.",
            "Audio, music, transitions and audio-visual synchronization were not reviewed.",
        ],
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
        "findings": _report_findings(answer, frames, spec, args.requirements),
    }
    quality = dict(output.quality or {})
    quality["content_review"] = report
    output.quality = quality
    await db.commit()
    return report
