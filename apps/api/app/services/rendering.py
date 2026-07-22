"""Drive the Remotion render service for a clip output.

The worker claims an output (``render_status=PENDING`` -> RENDERING) and calls
this. It absolutizes the clip-spec's source URL (the spec stores a relative
stream URL via the storage seam; the render service needs an absolute URL it
can fetch), POSTs the spec to the render service (black box: spec -> MP4+SRT),
and writes the resulting output keys back into ``output.files``.

Output keys carry a per-render timestamp suffix (``<output_id>-<ts>.mp4``) so a
re-render never overwrites the object a browser may have cached under the same
URL. The previous render's objects are deleted once the new one succeeds.

Render node mirror (RunPlan Phase 1, D2): if the output has a render plan node
(run-scoped renders), its status mirrors the render lifecycle — the node is
visibility + cost home, the claim stays on ``outputs.render_status`` so
run-less re-renders (manual render / dub / translate) keep working unchanged.
"""

import copy
import time
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select, text

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Output, Project
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

    Two kinds of relative values appear in persisted specs:
    - Bare object keys (``user/uploads/...``) — joined with the bucket's public
      URL base (the bucket is public-read).
    - Legacy API-relative paths (``/api/v1/...``, e.g. music stream URLs baked
      before music URLs became direct object URLs) — joined with the API's
      public base URL; those endpoints redirect to object storage.

    Any URL that is already absolute is left untouched.
    """

    def _resolve(value: str) -> str:
        if value.startswith(("http://", "https://")):
            return value
        if value.startswith("/api/"):
            return f"{settings.api_public_url.rstrip('/')}{value}"
        return public_url(value) or value

    src = spec.get("source", {})
    url = src.get("url", "")
    if url:
        src["url"] = _resolve(url)
    images = src.get("image_urls")
    if isinstance(images, list):
        src["image_urls"] = [_resolve(u) if isinstance(u, str) and u else u for u in images]
    brand = spec.get("brand")
    if isinstance(brand, dict):
        for card_key in ("intro", "outro"):
            card = brand.get(card_key)
            if isinstance(card, dict):
                media_url = card.get("media_url") or ""
                if media_url:
                    card["media_url"] = _resolve(media_url)
    music = spec.get("music")
    if isinstance(music, dict):
        track = music.get("url") or ""
        if track:
            music["url"] = _resolve(track)
    dub = spec.get("dub")
    if isinstance(dub, dict):
        dub_url = dub.get("url") or ""
        if dub_url:
            dub["url"] = _resolve(dub_url)
    return spec


async def _mirror_render_node(
    output_id: UUID,
    node_status: str,
    error: str | None = None,
) -> None:
    """Mirror render lifecycle onto the run's render node, if one exists."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "UPDATE plan_nodes SET status = :st, error = :err, "
                "finished_at = CASE WHEN :st IN ('done', 'failed') THEN now() "
                "ELSE finished_at END, updated_at = now() "
                "WHERE kind = 'render' AND status IN ('pending', 'running') "
                "AND spec->>'output_id' = :oid"
            ),
            {"st": node_status, "err": error, "oid": str(output_id)},
        )
        await db.commit()


async def render_output(output_id: UUID) -> None:
    """Render a claimed output via the render service; persist terminal state.

    Assumes the output is already claimed (RENDERING). On success writes
    files.video/files.srt + COMPLETED; on any error writes FAILED with the
    message. Terminal state is mirrored onto the render plan node when present.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Output, Project.user_id)
            .join(Project, Output.project_id == Project.id)
            .where(Output.id == output_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.warning("render_output_missing", output_id=str(output_id))
            return
        output, user_id = row
        if not output.render_spec:
            output.render_status = RenderStatus.FAILED
            output.render_error = "output has no render_spec"
            await db.commit()
            await _mirror_render_node(output_id, "failed", output.render_error)
            return

        try:
            spec = _absolutize(copy.deepcopy(output.render_spec))
            render_ts = int(time.time())
            video_key = await get_output_path(
                output.project_id, user_id, f"{output.id}-{render_ts}.mp4"
            )
            srt_key = await get_output_path(
                output.project_id, user_id, f"{output.id}-{render_ts}.srt"
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

            files = output.files or {}
            old_video_key = files.get("video")
            old_srt_key = files.get("srt")
            output.files = {**files, "video": data["video"], "srt": data["srt"]}
            output.render_status = RenderStatus.COMPLETED
            output.render_error = None
            await db.commit()
            await _mirror_render_node(output_id, "done")

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
                "output_rendered",
                output_id=str(output_id),
                video=output_url(output.files.get("video")),
            )
        except Exception as e:  # noqa: BLE001 — record any failure on the row
            logger.error("render_output_failed", output_id=str(output_id), error=str(e))
            output.render_status = RenderStatus.FAILED
            output.render_error = str(e)
            await db.commit()
            await _mirror_render_node(output_id, "failed", str(e)[:2000])
