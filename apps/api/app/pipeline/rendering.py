"""Resolve fixed video-spec sources and verify rendered bytes."""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import structlog

from app.config import settings
from app.pipeline.render_probe import (
    PROBE_OUTPUT_MISSING,
    ProbeViolation,
    probe_expectation_for,
    probe_rendered_video,
)
from app.providers.storage import (
    download_to_temp,
    public_url,
)

logger = structlog.get_logger()


def _resolve_url(value: str) -> str:
    """One relative value → absolute (the storage seam's two relative forms)."""
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("/api/"):
        return f"{settings.api_public_url.rstrip('/')}{value}"
    return public_url(value) or value


def absolutize_video(spec: dict[str, Any]) -> dict[str, Any]:
    """Absolutize every video source/font key; digests stay unchanged."""
    for font in spec.get("fonts") or []:
        if isinstance(font.get("url"), str):
            font["url"] = _resolve_url(font["url"])
    for track in spec.get("tracks") or []:
        for clip in track.get("clips") or []:
            source = clip.get("source")
            if isinstance(source, dict) and isinstance(source.get("url"), str):
                source["url"] = _resolve_url(source["url"])
            obj = clip.get("object")
            if isinstance(obj, dict) and obj.get("kind") == "motion_block":
                for resource in obj.get("resources") or []:
                    if isinstance(resource, dict) and isinstance(resource.get("url"), str):
                        resource["url"] = _resolve_url(resource["url"])
    return spec


def _absolutize(spec: dict[str, Any]) -> dict[str, Any]:
    """Make storage-relative URLs absolute so the render service can fetch them.

    Two kinds of relative values appear in persisted specs:
    - Bare object keys (``user/uploads/...``) — joined with the bucket's public
      URL base (the bucket is public-read).
    - Legacy API-relative paths (``/api/v1/...``, e.g. music stream URLs baked
      before music URLs became direct object URLs) — joined with the API's
      public base URL; those endpoints redirect to object storage.

    Any URL that is already absolute is left untouched. Dispatch reads only
    ``spec.family`` (never node type/name): video has its own walk;
    everything else uses the clip track registry.
    """
    if spec.get("family") == "video":
        return absolutize_video(spec)
    # Registry fold (ADR-044): the slots to resolve are each track's declared
    # url_fields — a newly registered track's URLs absolutize with zero changes
    # here.
    raise ValueError("Only a video-spec can be rendered")


async def _probe_artifacts(spec: dict[str, Any], video_key: str) -> tuple[list[ProbeViolation], str | None]:
    """放行闸③ (MG D4 / 禁止事项 10 — 禁无文件校验的成功态): download the fresh
    artifacts and probe them BEFORE the row may settle COMPLETED. ONE seat for
    both spec families; the check items dispatch on ``spec.family``
    (``probe_expectation_for``).

    Temp discipline (拍板): the downloaded copy is the probe's read-only
    working file and is deleted IMMEDIATELY on both outcomes — the artifact
    itself lives in object storage (a rejected object stays there as the
    forensic record, its key rides the failure detail), so the temp copy has
    no retention value.
    """
    expect = probe_expectation_for(spec)
    video_path: Path | None = None
    try:
        try:
            video_path = await download_to_temp(video_key)
        except Exception as e:  # noqa: BLE001 — an unreadable store read is
            # indistinguishable from a missing object at this seat; the render
            # fails either way and the attempt cap bounds the re-render.
            return [
                ProbeViolation(
                    PROBE_OUTPUT_MISSING,
                    f"video object unreadable from storage: {type(e).__name__}: {e}",
                )
            ], None
        def inspect():
            with video_path.open("rb") as media:
                digest = hashlib.file_digest(media, "sha256").hexdigest()
            return probe_rendered_video(video_path, expect), digest

        return await asyncio.to_thread(inspect)
    finally:
        for p in (video_path,):
            if p is not None:
                p.unlink(missing_ok=True)
