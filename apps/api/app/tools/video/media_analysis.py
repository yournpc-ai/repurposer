"""Versioned image/audio analysis and pixel-grounded image ContentReview."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import subprocess
from typing import Any, Literal

import PIL
from PIL import Image, ImageStat
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.base import Agent, AssembleResult
from app.models.schemas import MediaInput, MediaInputType, canonical_json_hash
from app.providers import storage
from app.providers.llm.base import LLMError, LLMSchemaError

IMAGE_ANALYZER_SET_VERSION = "image-pillow-v1"
AUDIO_ANALYZER_SET_VERSION = "audio-pyav-numpy-ffmpeg-v2"
IMAGE_REVIEWER_VERSION = "scene-image-review-v6"
_ANALYSIS_PREFIX = "visual-media-analysis"
_AUDIO_ANALYSIS_PREFIX = "audio-media-analysis"
_REVIEW_PREFIX = "visual-content-reviews"
_MAX_IMAGE_BYTES = 16 * 1024 * 1024
_MAX_AUDIO_BYTES = 256 * 1024 * 1024


class MediaAnalysisError(ValueError):
    pass


def image_reviewer_version(source_kind: str) -> str:
    if source_kind == "existing_image":
        return f"{IMAGE_REVIEWER_VERSION}-source-evidence-v1"
    return IMAGE_REVIEWER_VERSION


class LoudnessAnalysisError(MediaAnalysisError):
    user_key = "audio_loudness_failed"


class MediaSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["snapshot"] = "snapshot"
    snapshot_id: str
    digest: str = Field(min_length=64, max_length=64)


class MediaAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    report_digest: str = Field(min_length=64, max_length=64)
    source_ref: MediaSourceRef
    media_kind: Literal["image", "audio"]
    requested_probes: list[str] = Field(min_length=1)
    parameters: dict[str, Any]
    analysis_scope: Literal["full", "bounded", "unavailable"]
    analyzer_set_version: str
    analyzer_facts: dict[str, Any]
    media_facts: dict[str, Any]
    issues: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ContentReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["observed_issue", "aesthetic_suggestion"]
    observed: str = Field(min_length=1, max_length=800)
    requirement: str | None = Field(default=None, max_length=500)
    evidence: str = Field(min_length=1, max_length=800)
    suggestion: str | None = Field(default=None, max_length=500)


class ContentReviewAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_provider_dialects(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "findings" in value:
            return value
        findings = []
        for keys, kind in (
            (("observed_issue", "observable_issues", "observed_issues"), "observed_issue"),
            (("aesthetic_suggestion", "aesthetic_suggestions"), "aesthetic_suggestion"),
        ):
            for key in keys:
                for item in value.get(key) or []:
                    if not isinstance(item, dict):
                        continue
                    evidence = (
                        item.get("evidence") or item.get("visible_evidence")
                        or item.get("visual_evidence")
                    )
                    observed = (
                        item.get("observed") or item.get("observation") or item.get("issue")
                        or evidence
                    )
                    if not observed or not evidence:
                        continue
                    findings.append({
                        "kind": kind,
                        "observed": observed,
                        "requirement": item.get("requirement"),
                        "evidence": evidence,
                        "suggestion": item.get("suggestion") or item.get("smallest_useful_change"),
                    })
        return {
            "status": value.get("status"),
            "summary": value.get("summary"),
            "findings": findings,
        }

    status: Literal["pass", "fail", "needs_human", "advisory"]
    summary: str = Field(min_length=1, max_length=1200)
    findings: list[ContentReviewFinding] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _status_matches_findings(self) -> ContentReviewAnswer:
        blocking = [item for item in self.findings if item.kind == "observed_issue"]
        if self.status == "fail" and not blocking:
            raise ValueError("fail needs at least one observed_issue with pixel evidence")
        for item in blocking:
            requirement = " ".join((item.requirement or "").casefold().split())
            evidence = " ".join(item.evidence.casefold().split())
            if not requirement or not evidence or requirement == evidence:
                raise ValueError(
                    "observed_issue requires a specific requirement and distinct pixel evidence"
                )
        if self.status == "pass" and self.findings:
            raise ValueError("pass cannot carry findings; use advisory or fail")
        if self.status == "advisory" and blocking:
            raise ValueError("observed delivery issues require fail or needs_human")
        return self


class ContentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    review_digest: str = Field(min_length=64, max_length=64)
    source_ref: MediaSourceRef
    scene_id: str
    request_digest: str = Field(min_length=64, max_length=64)
    analysis_report_ref: dict[str, str]
    reviewer_version: str
    status: Literal["pass", "fail", "needs_human", "advisory", "unavailable"]
    summary: str
    findings: list[ContentReviewFinding] = Field(default_factory=list)
    review_scope: Literal["full_static_image"] = "full_static_image"
    limitations: list[str] = Field(default_factory=list)


def analyze_image_bytes(
    data: bytes,
    *,
    snapshot_id: str,
    source_digest: str | None = None,
    requested_probes: list[Literal["decode", "dimensions", "pixel_stats"]] | None = None,
    parameters: dict[str, Any] | None = None,
    svg_text_bounds: list[dict[str, Any]] | None = None,
    caption_safe_area: dict[str, float] | None = None,
    analyzer_set_version: str = IMAGE_ANALYZER_SET_VERSION,
) -> MediaAnalysisReport:
    probes = requested_probes or ["decode", "dimensions", "pixel_stats"]
    params = {"max_bytes": _MAX_IMAGE_BYTES, **(parameters or {})}
    if not set(probes).issubset({"decode", "dimensions", "pixel_stats"}):
        raise MediaAnalysisError("unsupported image probe")
    if len(data) > int(params["max_bytes"]):
        raise MediaAnalysisError("image exceeds the analysis byte budget")
    digest = source_digest or hashlib.sha256(data).hexdigest()
    if hashlib.sha256(data).hexdigest() != digest:
        raise MediaAnalysisError("image bytes do not match their source digest")
    try:
        with Image.open(io.BytesIO(data)) as candidate:
            image_format = candidate.format
            candidate.verify()
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
            width, height = decoded.size
            mode = decoded.mode
            rgb = decoded.convert("RGB")
            statistics = ImageStat.Stat(rgb)
            alpha_extrema = (
                decoded.getchannel("A").getextrema() if "A" in decoded.getbands() else None
            )
    except (OSError, ValueError, SyntaxError) as exc:
        raise MediaAnalysisError(f"image is not fully decodable: {exc}") from exc
    if image_format != "PNG" or width <= 0 or height <= 0:
        raise MediaAnalysisError("visual assets must be non-empty PNG images")
    facts: dict[str, Any] = {}
    limitations: list[str] = []
    if "decode" in probes:
        facts["decode"] = {"fully_decoded": True, "format": "PNG", "frames": 1}
    if "dimensions" in probes:
        facts["dimensions"] = {"width": width, "height": height, "mode": mode}
    if "pixel_stats" in probes:
        facts["pixel_stats"] = {
            "rgb_mean": [round(value, 6) for value in statistics.mean],
            "rgb_stddev": [round(value, 6) for value in statistics.stddev],
            "alpha_extrema": alpha_extrema,
        }
    if "pixel_stats" not in probes:
        limitations.append("Pixel statistics were not requested")
    if svg_text_bounds is not None:
        canvas = {"left": 0.0, "top": 0.0, "right": float(width), "bottom": float(height)}
        safe = None
        if caption_safe_area is not None:
            area = caption_safe_area
            safe = {
                "left": area["x"] * width, "top": area["y"] * height,
                "right": (area["x"] + area["width"]) * width,
                "bottom": (area["y"] + area["height"]) * height,
            }

        def inside(box: dict, region: dict) -> bool:
            # Subpixel font metrics near an edge should not decide the verdict.
            return (
                box["left"] >= region["left"] - 0.5
                and box["top"] >= region["top"] - 0.5
                and box["right"] <= region["right"] + 0.5
                and box["bottom"] <= region["bottom"] + 0.5
            )

        facts["svg_text_geometry"] = {
            "source": "Chromium SVG layout boxes in output pixels",
            "caption_safe_area": safe,
            "text": [{
                **box, "inside_canvas": inside(box, canvas),
                "inside_caption_safe_area": inside(box, safe) if safe is not None else None,
            } for box in svg_text_bounds if box.get("text", "").strip()],
        }
        limitations.append("SVG layout boxes measure geometry, not which pixels are visible")
    payload = {
        "schema_version": 1,
        "source_ref": {
            "kind": "snapshot",
            "snapshot_id": str(snapshot_id),
            "digest": digest,
        },
        "media_kind": "image",
        "requested_probes": probes,
        "parameters": params,
        "analysis_scope": "full",
        "analyzer_set_version": analyzer_set_version,
        "analyzer_facts": {"library": "Pillow", "version": PIL.__version__},
        "media_facts": {
            "byte_count": len(data),
            "mime_type": "image/png",
            **facts,
        },
        "issues": [],
        "limitations": limitations,
    }
    return MediaAnalysisReport(report_digest=canonical_json_hash(payload), **payload)


def _ffmpeg_audio_facts(data: bytes, demuxer: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from imageio_ffmpeg import get_ffmpeg_exe

    try:
        executable = get_ffmpeg_exe()
        version = subprocess.run(
            [executable, "-version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.splitlines()[0].strip()
        command = [
            executable, "-hide_banner", "-nostdin", "-f", demuxer, "-i", "pipe:0",
            "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-",
        ]
        completed = subprocess.run(command, input=data, capture_output=True, timeout=120)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise LoudnessAnalysisError(f"FFmpeg loudness analysis failed: {exc}") from exc
    output = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise LoudnessAnalysisError("FFmpeg could not fully decode the audio for loudness analysis")

    def metric(pattern: str) -> float | None:
        matches = re.findall(pattern, output, flags=re.MULTILINE)
        if not matches:
            raise LoudnessAnalysisError("FFmpeg did not return the requested loudness metric")
        value = float(matches[-1])
        return value if math.isfinite(value) else None

    loudness = {
        "integrated_lufs": metric(r"^\s*I:\s*(-?\d+(?:\.\d+)?|-inf)\s+LUFS\s*$"),
        "true_peak_dbtp": metric(r"^\s*Peak:\s*(-?\d+(?:\.\d+)?|-inf)\s+dBFS\s*$"),
    }
    return {"version": version}, loudness


def analyze_audio_bytes(
    data: bytes,
    *,
    snapshot_id: str,
    source_digest: str | None = None,
    requested_probes: list[str] | None = None,
    parameters: dict[str, Any] | None = None,
    analyzer_set_version: str = AUDIO_ANALYZER_SET_VERSION,
) -> MediaAnalysisReport:
    """Fully decode one fixed audio source and retain only measured signal facts."""
    import av
    import numpy as np

    probes = requested_probes or ["decode", "pcm_stats", "waveform", "loudness"]
    supported = {"decode", "pcm_stats", "waveform", "loudness"}
    if not set(probes).issubset(supported):
        raise MediaAnalysisError("unsupported audio probe")
    params = {
        "max_bytes": _MAX_AUDIO_BYTES,
        "waveform_buckets": 48,
        "silence_threshold": 1e-5,
        "clipping_threshold": 0.999,
        **(parameters or {}),
    }
    if len(data) > int(params["max_bytes"]):
        raise MediaAnalysisError("audio exceeds the analysis byte budget")
    buckets = int(params["waveform_buckets"])
    if not 1 <= buckets <= 256:
        raise MediaAnalysisError("waveform bucket count is outside its resource bound")
    digest = source_digest or hashlib.sha256(data).hexdigest()
    if hashlib.sha256(data).hexdigest() != digest:
        raise MediaAnalysisError("audio bytes do not match their source digest")
    try:
        with av.open(io.BytesIO(data), mode="r") as container:
            stream = next((item for item in container.streams if item.type == "audio"), None)
            if stream is None:
                raise MediaAnalysisError("audio source has no audio stream")
            sample_rate = int(stream.codec_context.sample_rate or stream.rate or 0)
            channels = int(stream.channels)
            if sample_rate <= 0 or channels <= 0:
                raise MediaAnalysisError("audio stream has invalid sample rate or channels")
            container_fact = {
                "format": container.format.name,
                "duration_seconds": (
                    container.duration / av.time_base if container.duration is not None else None
                ),
            }
            resampler = av.AudioResampler(
                format="fltp", layout=stream.layout, rate=sample_rate
            )
            chunks = []
            for frame in container.decode(stream):
                for decoded in resampler.resample(frame):
                    chunks.append(decoded.to_ndarray().reshape(channels, -1))
            for decoded in resampler.resample(None):
                chunks.append(decoded.to_ndarray().reshape(channels, -1))
    except MediaAnalysisError:
        raise
    except Exception as exc:
        raise MediaAnalysisError(f"audio is not fully decodable: {exc}") from exc
    if not chunks:
        raise MediaAnalysisError("audio decoded to zero samples")
    pcm = np.concatenate(chunks, axis=1).astype(np.float64, copy=False)
    sample_count = int(pcm.shape[1])
    if sample_count <= 0:
        raise MediaAnalysisError("audio decoded to zero samples")
    actual_duration = sample_count / sample_rate
    analyzer_facts: dict[str, Any] = {
        "pyav": {"version": av.__version__},
        "numpy": {"version": np.__version__},
    }
    facts: dict[str, Any] = {
        "byte_count": len(data),
        "container": container_fact,
        "sample_rate": sample_rate,
        "channels": channels,
        "decode": {
            "fully_decoded": True,
            "sample_count": sample_count,
            "actual_range_samples": {"start": 0, "end": sample_count},
            "duration_seconds": actual_duration,
        },
    }
    issues: list[dict[str, Any]] = []
    if "pcm_stats" in probes or "waveform" in probes:
        rms = float(np.sqrt(np.mean(pcm**2)))
        peak = float(np.max(np.abs(pcm)))
        clipped = np.abs(pcm) >= float(params["clipping_threshold"])
        if "pcm_stats" in probes:
            facts["pcm_stats"] = {
                "rms": rms,
                "peak": peak,
                "clipped_sample_count": int(np.count_nonzero(clipped)),
                "clipped_sample_ratio": float(np.mean(clipped)),
                "is_silent": bool(
                    peak <= float(params["silence_threshold"])
                    or rms <= float(params["silence_threshold"])
                ),
            }
            if facts["pcm_stats"]["is_silent"]:
                issues.append({"code": "audio_silent", "scope": "full_decoded_audio"})
            if facts["pcm_stats"]["clipped_sample_count"]:
                issues.append({"code": "audio_clipping", "scope": "full_decoded_audio"})
        if "waveform" in probes:
            peaks = []
            energies = []
            for bucket in range(buckets):
                start = sample_count * bucket // buckets
                end = sample_count * (bucket + 1) // buckets
                segment = pcm[:, start:end]
                peaks.append(float(np.max(np.abs(segment))) if segment.size else 0.0)
                energies.append(float(np.sqrt(np.mean(segment**2))) if segment.size else 0.0)
            facts["waveform"] = {
                "bucket_count": buckets,
                "peak": peaks,
                "rms": energies,
                "source": "full_decoded_pcm",
            }
    if "loudness" in probes:
        # stdin has no filename and format probing can misidentify even a PCM WAV.
        # Use the demuxer that just decoded these exact bytes.
        ffmpeg, loudness = _ffmpeg_audio_facts(data, container_fact["format"].split(",")[0])
        analyzer_facts["ffmpeg"] = ffmpeg
        facts["loudness"] = loudness
    limitations = ["Signal analysis is not human listening or a subjective quality judgment"]
    if "loudness" not in probes:
        limitations.append("Integrated LUFS and True Peak were not measured")
    payload = {
        "schema_version": 1,
        "source_ref": {
            "kind": "snapshot", "snapshot_id": str(snapshot_id), "digest": digest,
        },
        "media_kind": "audio",
        "requested_probes": probes,
        "parameters": params,
        "analysis_scope": "full",
        "analyzer_set_version": analyzer_set_version,
        "analyzer_facts": analyzer_facts,
        "media_facts": facts,
        "issues": issues,
        "limitations": limitations,
    }
    return MediaAnalysisReport(report_digest=canonical_json_hash(payload), **payload)


def image_media_input(data: bytes, *, caption: str) -> MediaInput:
    return MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/png",
        data_url="data:image/png;base64," + base64.b64encode(data).decode("ascii"),
        caption=caption,
    )


def _assemble_image_review(
    *, scene_asset_json: str, analysis_json: str, image: MediaInput
) -> AssembleResult:
    return {
        "scene_asset_json": scene_asset_json,
        "analysis_json": analysis_json,
        "existing_image": json.loads(scene_asset_json)["source"]["kind"] == "existing_image",
    }, [image]


image_content_reviewer: Agent[ContentReviewAnswer] = Agent(
    name="scene_image_content_reviewer",
    prompt="video/visual_content_reviewer.j2",
    schema=ContentReviewAnswer,
    system=(
        "只对照 SceneAssetSpec 和确定性图像分析审阅所附 PNG。区分可观察的交付问题及审美建议。"
        "不要声称已审核运动、音频、可编辑性或未检查的维度。只输出有效 JSON。"
    ),
    temperature=0.2,
    assemble=_assemble_image_review,
    media_text_fallback=False,
    stream=False,
    timeout_s=180,
)


def _review_limitations() -> list[str]:
    return [
        "One static PNG was inspected; motion, audio and continuous playback were not reviewed",
        "SVG-internal elements are not native editable Composition objects",
    ]


async def review_image_content(
    data: bytes,
    *,
    scene_asset: Any,
    analysis: MediaAnalysisReport,
    analysis_ref: dict[str, str],
    reviewer: Any = None,
) -> ContentReview:
    source_ref = analysis.source_ref
    common = {
        "schema_version": 1,
        "source_ref": source_ref.model_dump(mode="json"),
        "scene_id": scene_asset.scene_id,
        "request_digest": scene_asset.request_digest(),
        "analysis_report_ref": analysis_ref,
        "reviewer_version": image_reviewer_version(scene_asset.source.kind),
        "review_scope": "full_static_image",
    }
    try:
        call = reviewer or image_content_reviewer.call
        answer = await call(
            scene_asset_json=json.dumps(scene_asset.model_dump(mode="json"), ensure_ascii=False),
            analysis_json=analysis.model_dump_json(),
            image=image_media_input(
                data,
                caption=(
                    f"Actual fixed PNG for scene {scene_asset.scene_id}; "
                    f"source digest {source_ref.digest}"
                ),
            ),
        )
        if isinstance(answer, dict):
            answer = ContentReviewAnswer.model_validate(answer)
        payload = {
            **common,
            "status": answer.status,
            "summary": answer.summary,
            "findings": [item.model_dump(mode="json") for item in answer.findings],
            "limitations": _review_limitations(),
        }
    except (LLMError, ValueError, TypeError) as exc:
        if isinstance(exc, LLMSchemaError) or not isinstance(exc, LLMError):
            reason = "review response did not match the expected schema"
        else:
            reason = "the review model could not complete the request"
        payload = {
            **common,
            "status": "unavailable",
            "summary": f"Content review unavailable: {reason}.",
            "findings": [],
            "limitations": [*_review_limitations(), "No content judgment was obtained"],
        }
    return ContentReview(review_digest=canonical_json_hash(payload), **payload)


async def _store_report(prefix: str, digest: str, report: BaseModel) -> dict[str, str]:
    key = f"{prefix}/{digest}.json"
    encoded = report.model_dump_json().encode("utf-8")
    if await storage.exists(key):
        existing = await storage.read(key)
        if hashlib.sha256(existing).hexdigest() != hashlib.sha256(encoded).hexdigest():
            raise MediaAnalysisError("content-addressed report identity collision")
    else:
        await storage.save(key, encoded, content_type="application/json")
    return {"storage_key": key, "digest": digest}


async def store_media_analysis(report: MediaAnalysisReport) -> dict[str, str]:
    prefix = _ANALYSIS_PREFIX if report.media_kind == "image" else _AUDIO_ANALYSIS_PREFIX
    return await _store_report(prefix, report.report_digest, report)


async def store_content_review(report: ContentReview) -> dict[str, str]:
    return await _store_report(_REVIEW_PREFIX, report.review_digest, report)


async def read_report(ref: dict[str, str]) -> dict[str, Any]:
    data = await storage.read(ref["storage_key"])
    value = json.loads(data)
    digest_key = "report_digest" if "report_digest" in value else "review_digest"
    if value.get(digest_key) != ref["digest"]:
        raise MediaAnalysisError("stored report identity does not match its reference")
    payload = {key: item for key, item in value.items() if key != digest_key}
    if canonical_json_hash(payload) != ref["digest"]:
        raise MediaAnalysisError("stored report content does not match its content digest")
    return value


__all__ = [
    "AUDIO_ANALYZER_SET_VERSION",
    "ContentReview",
    "ContentReviewAnswer",
    "IMAGE_ANALYZER_SET_VERSION",
    "IMAGE_REVIEWER_VERSION",
    "MediaAnalysisError",
    "MediaAnalysisReport",
    "analyze_audio_bytes",
    "analyze_image_bytes",
    "image_content_reviewer",
    "image_media_input",
    "image_reviewer_version",
    "read_report",
    "review_image_content",
    "store_content_review",
    "store_media_analysis",
]
