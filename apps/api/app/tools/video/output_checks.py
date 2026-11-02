"""Deterministic signal checks for one exact Output's decoded media.

The render probe remains the delivery hard gate. These advisory observations
augment content review with facts an LLM cannot see reliably: sampled flat or
repeated pixels and full-stream audio levels. RMS/peak are not BS.1770 LUFS,
and neither sampled frames nor signal levels prove motion quality or AV sync.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any, Literal

import av
import numpy as np
from PIL import Image, ImageStat
from pydantic import BaseModel, ConfigDict

from app.pipeline.render_probe import probe_expectation_for

OUTPUT_CHECKER_VERSION = "output-checks-v1"
_AUDIO_RATE = 22050
_FLAT_STDDEV = 1.0
_SILENT_PEAK = 1e-5
_QUIET_RMS_DBFS = -45.0
_CLIPPED_THRESHOLD = 0.999
_CLIPPED_RATIO = 0.001


@dataclass(frozen=True)
class FrameSample:
    """One actual decoded Output frame, already JPEG-encoded by the reviewer."""

    frame: int
    time_seconds: float
    jpeg: bytes


class OutputCheckIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "AUDIO_MISSING",
        "AUDIO_DECODE_FAILED",
        "AUDIO_SILENT",
        "AUDIO_QUIET",
        "AUDIO_CLIPPED",
    ]
    observed: str


class FlatFrameCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame: int
    time_seconds: float
    mean_luma: float
    luma_stddev: float


class RepeatedFrameGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: list[int]
    times_seconds: list[float]


class VisualInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sampled_frames: int
    flat_frame_candidates: list[FlatFrameCandidate]
    repeated_frame_groups: list[RepeatedFrameGroup]


class AudioInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: bool
    present: bool | None
    decode_ok: bool
    scope: Literal["full_stream", "unavailable"]
    sample_rate: int | None = None
    samples: int = 0
    duration_seconds: float | None = None
    rms_dbfs: float | None = None
    peak_dbfs: float | None = None
    clipped_sample_ratio: float | None = None
    integrated_lufs: None = None


class OutputInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checker_version: str = OUTPUT_CHECKER_VERSION
    visual: VisualInspection
    audio: AudioInspection
    issues: list[OutputCheckIssue]


def _dbfs(level: float) -> float:
    return 20.0 * math.log10(max(level, 1e-12))


def inspect_frame_samples(samples: list[FrameSample]) -> VisualInspection:
    """Report candidates only: a static scene or solid MG field can be intentional."""
    flat: list[FlatFrameCandidate] = []
    repeated: dict[bytes, list[FrameSample]] = {}
    for sample in samples:
        with Image.open(io.BytesIO(sample.jpeg)) as image:
            stat = ImageStat.Stat(image.convert("L").resize((160, 90)))
        mean = float(stat.mean[0])
        stddev = float(stat.stddev[0])
        if stddev <= _FLAT_STDDEV:
            flat.append(FlatFrameCandidate(
                frame=sample.frame,
                time_seconds=sample.time_seconds,
                mean_luma=round(mean, 3),
                luma_stddev=round(stddev, 3),
            ))
        repeated.setdefault(sample.jpeg, []).append(sample)
    groups = [
        RepeatedFrameGroup(
            frames=[item.frame for item in rows],
            times_seconds=[item.time_seconds for item in rows],
        )
        for rows in repeated.values()
        if len(rows) > 1
    ]
    return VisualInspection(
        sampled_frames=len(samples),
        flat_frame_candidates=flat,
        repeated_frame_groups=groups,
    )


def _unavailable_audio(*, expected: bool, present: bool | None) -> AudioInspection:
    return AudioInspection(
        expected=expected,
        present=present,
        decode_ok=False,
        scope="unavailable",
    )


def inspect_output_audio(
    video: bytes, spec: dict[str, Any]
) -> tuple[AudioInspection, list[OutputCheckIssue]]:
    """Measure full-stream PCM without retaining the whole soundtrack in memory."""
    expected = probe_expectation_for(spec).audio is True
    issues: list[OutputCheckIssue] = []
    try:
        container = av.open(io.BytesIO(video), mode="r")
    except Exception as exc:  # noqa: BLE001 — decoder diagnostics stay bounded
        issues.append(OutputCheckIssue(
            code="AUDIO_DECODE_FAILED",
            observed=(
                "The media container could not be opened for audio inspection: "
                f"{type(exc).__name__}"
            ),
        ))
        return _unavailable_audio(expected=expected, present=None), issues
    with container:
        stream = next((item for item in container.streams if item.type == "audio"), None)
        if stream is None:
            audio = _unavailable_audio(expected=expected, present=False)
            if expected:
                issues.append(OutputCheckIssue(
                    code="AUDIO_MISSING",
                    observed="The executed spec expects sound, but the Output has no audio stream.",
                ))
            return audio, issues
        resampler = av.AudioResampler(format="flt", layout="mono", rate=_AUDIO_RATE)
        sample_count = 0
        square_sum = 0.0
        peak = 0.0
        clipped = 0
        try:
            def consume(frame: av.AudioFrame) -> None:
                nonlocal sample_count, square_sum, peak, clipped
                values = frame.to_ndarray().reshape(-1)
                if values.size == 0:
                    return
                sample_count += int(values.size)
                square_sum += float(np.dot(values, values))
                peak = max(peak, float(np.max(np.abs(values))))
                clipped += int(np.count_nonzero(np.abs(values) >= _CLIPPED_THRESHOLD))

            for decoded in container.decode(stream):
                for frame in resampler.resample(decoded):
                    consume(frame)
            for frame in resampler.resample(None):
                consume(frame)
        except Exception as exc:  # noqa: BLE001 — partial audio is not a pass
            issues.append(OutputCheckIssue(
                code="AUDIO_DECODE_FAILED",
                observed=f"The audio stream could not be fully decoded: {type(exc).__name__}",
            ))
            return _unavailable_audio(expected=expected, present=True), issues
    if sample_count == 0:
        issues.append(OutputCheckIssue(
            code="AUDIO_DECODE_FAILED",
            observed="The audio stream decoded to zero samples.",
        ))
        return _unavailable_audio(expected=expected, present=True), issues
    if not math.isfinite(square_sum) or not math.isfinite(peak):
        issues.append(OutputCheckIssue(
            code="AUDIO_DECODE_FAILED",
            observed="The audio stream produced non-finite signal measurements.",
        ))
        return _unavailable_audio(expected=expected, present=True), issues

    rms = math.sqrt(square_sum / sample_count)
    rms_dbfs = _dbfs(rms)
    peak_dbfs = _dbfs(peak)
    clipped_ratio = clipped / sample_count
    audio = AudioInspection(
        expected=expected,
        present=True,
        decode_ok=True,
        scope="full_stream",
        sample_rate=_AUDIO_RATE,
        samples=sample_count,
        duration_seconds=round(sample_count / _AUDIO_RATE, 6),
        rms_dbfs=round(rms_dbfs, 3),
        peak_dbfs=round(peak_dbfs, 3),
        clipped_sample_ratio=round(clipped_ratio, 8),
    )
    if peak <= _SILENT_PEAK:
        if expected:
            issues.append(OutputCheckIssue(
                code="AUDIO_SILENT",
                observed=(
                    "The executed spec expects sound, but the full decoded "
                    "audio stream is silent."
                ),
            ))
    elif expected and rms_dbfs < _QUIET_RMS_DBFS:
        issues.append(OutputCheckIssue(
            code="AUDIO_QUIET",
            observed=f"The full-stream RMS level is very low ({rms_dbfs:.1f} dBFS).",
        ))
    if clipped_ratio > _CLIPPED_RATIO:
        issues.append(OutputCheckIssue(
            code="AUDIO_CLIPPED",
            observed=(
                f"{clipped_ratio:.2%} of decoded samples are at or above "
                "the clipping threshold."
            ),
        ))
    return audio, issues


def inspect_output_media(
    video: bytes,
    spec: dict[str, Any],
    frames: list[FrameSample],
) -> OutputInspection:
    audio, issues = inspect_output_audio(video, spec)
    return OutputInspection(
        visual=inspect_frame_samples(frames),
        audio=audio,
        issues=issues,
    )
