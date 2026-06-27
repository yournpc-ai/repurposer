"""Drive the Remotion render service for a clip.

The worker claims a clip (``render_status=PENDING`` -> RENDERING) and calls this.
It absolutizes the clip-spec's source URL (the spec stores a relative stream URL
via the storage seam; the render service needs an absolute URL it can fetch),
POSTs the spec to the render service (black box: spec -> MP4+SRT), and writes the
resulting output URLs back onto the clip.
"""

import copy
from typing import Any
from uuid import UUID

import httpx
import structlog

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Clip
from app.services.storage import output_url

logger = structlog.get_logger()


def _absolutize(spec: dict[str, Any]) -> dict[str, Any]:
    """Make storage-relative URLs absolute so the render service can fetch them."""
    base = settings.api_public_url.rstrip("/")
    url = spec.get("source", {}).get("url", "")
    if url.startswith("/"):
        spec["source"]["url"] = base + url
    # Brand logo may be a relative storage URL too (usually an external absolute
    # URL, in which case this is a no-op).
    brand = spec.get("brand")
    if isinstance(brand, dict):
        logo = brand.get("logo_url") or ""
        if logo.startswith("/"):
            brand["logo_url"] = base + logo
    return spec


async def render_clip(clip_id: UUID) -> None:
    """Render a claimed clip via the render service; persist terminal state.

    Assumes the clip is already claimed (RENDERING). On success writes
    video_url/srt_url + COMPLETED; on any error writes FAILED with the message.
    """
    async with AsyncSessionLocal() as db:
        clip = await db.get(Clip, clip_id)
        if clip is None:
            logger.warning("render_clip_missing", clip_id=str(clip_id))
            return
        if not clip.render_spec:
            clip.render_status = RenderStatus.FAILED
            clip.render_error = "clip has no render_spec"
            await db.commit()
            return

        try:
            spec = _absolutize(copy.deepcopy(clip.render_spec))
            payload = {
                "spec": spec,
                "out_subdir": str(clip.project_id),
                "basename": str(clip.id),
            }
            async with httpx.AsyncClient(timeout=900) as client:
                resp = await client.post(settings.render_url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            clip.video_url = output_url(data["video"])
            clip.srt_url = output_url(data["srt"])
            clip.render_status = RenderStatus.COMPLETED
            clip.render_error = None
            await db.commit()
            logger.info("clip_rendered", clip_id=str(clip_id), video=clip.video_url)
        except Exception as e:  # noqa: BLE001 — record any failure on the row
            logger.error("clip_render_failed", clip_id=str(clip_id), error=str(e))
            clip.render_status = RenderStatus.FAILED
            clip.render_error = str(e)
            await db.commit()
