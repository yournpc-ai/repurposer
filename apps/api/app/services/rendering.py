"""Drive the Remotion render service for a clip.

The worker claims a clip (``render_status=PENDING`` -> RENDERING) and calls this.
It absolutizes the clip-spec's source URL (the spec stores a relative stream URL
via the storage seam; the render service needs an absolute URL it can fetch),
POSTs the spec to the render service (black box: spec -> MP4+SRT), and writes the
resulting output keys back onto the clip.

Output keys carry a per-render timestamp suffix (``<clip_id>-<ts>.mp4``) so a
re-render never overwrites the object a browser may have cached under the same
URL. The previous render's objects are deleted once the new one succeeds.
"""

import copy
import time
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Clip, Project
from app.services.storage import (
    delete,
    get_output_path,
    output_url,
    presign_upload,
    public_url,
)

logger = structlog.get_logger()


def _absolutize(spec: dict[str, Any]) -> dict[str, Any]:
    """Make storage-relative URLs absolute so the render service can fetch them.

    Source, brand media, music and dub URLs may be stored as object keys. Since
    the bucket is public-read, we join them with the public URL base. Any URL
    that is already absolute is left untouched.
    """
    src = spec.get("source", {})
    url = src.get("url", "")
    if url and not url.startswith(("http://", "https://")):
        src["url"] = public_url(url)
    images = src.get("image_urls")
    if isinstance(images, list):
        src["image_urls"] = [
            public_url(u)
            if isinstance(u, str) and u and not u.startswith(("http://", "https://"))
            else u
            for u in images
        ]
    brand = spec.get("brand")
    if isinstance(brand, dict):
        for card_key in ("intro", "outro"):
            card = brand.get(card_key)
            if isinstance(card, dict):
                media_url = card.get("media_url") or ""
                if media_url and not media_url.startswith(("http://", "https://")):
                    card["media_url"] = public_url(media_url)
    music = spec.get("music")
    if isinstance(music, dict):
        track = music.get("url") or ""
        if track and not track.startswith(("http://", "https://")):
            music["url"] = public_url(track)
    dub = spec.get("dub")
    if isinstance(dub, dict):
        dub_url = dub.get("url") or ""
        if dub_url and not dub_url.startswith(("http://", "https://")):
            dub["url"] = public_url(dub_url)
    return spec


async def render_clip(clip_id: UUID) -> None:
    """Render a claimed clip via the render service; persist terminal state.

    Assumes the clip is already claimed (RENDERING). On success writes
    video_url/srt_url + COMPLETED; on any error writes FAILED with the message.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Clip, Project.user_id)
            .join(Project, Clip.project_id == Project.id)
            .where(Clip.id == clip_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.warning("render_clip_missing", clip_id=str(clip_id))
            return
        clip, user_id = row
        if not clip.render_spec:
            clip.render_status = RenderStatus.FAILED
            clip.render_error = "clip has no render_spec"
            await db.commit()
            return

        try:
            spec = _absolutize(copy.deepcopy(clip.render_spec))
            render_ts = int(time.time())
            video_key = await get_output_path(
                clip.project_id, user_id, f"{clip.id}-{render_ts}.mp4"
            )
            srt_key = await get_output_path(
                clip.project_id, user_id, f"{clip.id}-{render_ts}.srt"
            )
            video_put_url = await presign_upload(
                video_key, content_type="video/mp4", ttl=900
            )
            srt_put_url = await presign_upload(
                srt_key, content_type="text/srt", ttl=900
            )
            payload = {
                "spec": spec,
                "outputs": {
                    "video": {
                        "key": video_key,
                        "put_url": video_put_url,
                        "content_type": "video/mp4",
                    },
                    "srt": {
                        "key": srt_key,
                        "put_url": srt_put_url,
                        "content_type": "text/srt",
                    },
                },
            }
            async with httpx.AsyncClient(timeout=900) as client:
                resp = await client.post(settings.render_url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            old_video_key = clip.video_url
            old_srt_key = clip.srt_url
            clip.video_url = data["video"]
            clip.srt_url = data["srt"]
            clip.render_status = RenderStatus.COMPLETED
            clip.render_error = None
            await db.commit()

            # Best-effort cleanup of the previous render's objects. Only bare
            # keys are deletable; legacy /api/v1 paths and absolute URLs are
            # skipped (deleting them would be a no-op anyway).
            for old_key in (old_video_key, old_srt_key):
                if old_key and not old_key.startswith(("http://", "https://", "/")):
                    try:
                        await delete(old_key)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "render_old_output_delete_failed",
                            key=old_key,
                            error=str(e),
                        )

            logger.info(
                "clip_rendered",
                clip_id=str(clip_id),
                video=output_url(clip.video_url),
            )
        except Exception as e:  # noqa: BLE001 — record any failure on the row
            logger.error("render_clip_failed", clip_id=str(clip_id), error=str(e))
            clip.render_status = RenderStatus.FAILED
            clip.render_error = str(e)
            await db.commit()
