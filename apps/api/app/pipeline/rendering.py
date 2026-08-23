"""Drive the Remotion render service for a clip output.

The worker claims an output (``render_status=PENDING`` -> RENDERING) and calls
this. It absolutizes the clip-spec's source URL (the spec stores a relative
stream URL via the storage seam; the render service needs an absolute URL it
can fetch), POSTs the spec to the render service (black box: spec -> MP4+SRT),
and writes the resulting output keys back into ``output.files``.

Output keys carry a per-render timestamp suffix (``<output_id>-<ts>.mp4``) so a
re-render never overwrites the object a browser may have cached under the same
URL. The previous render's objects are deleted once the new one succeeds.

Render node mirror (RunPlan Phase 1, D2): if the output has a render workflow step
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
from sqlalchemy import select, text, update

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Output, Project, WorkflowRun
from app.pipeline.errors import user_line
from app.pipeline.tracks import resolve_spec_urls
from app.providers.storage import (
    delete,
    get_output_path,
    output_url,
    presign_upload,
    public_url,
)
from app.ui_locale import display_language

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

    # Registry fold (ADR-044): the slots to resolve are each track's declared
    # url_fields — a newly registered track's URLs absolutize with zero changes
    # here.
    return resolve_spec_urls(spec, _resolve)


async def _mirror_render_node(
    output_id: UUID,
    node_status: str,
    error: str | None = None,
) -> None:
    """Mirror render lifecycle onto the run's render node, if one exists.

    Best-effort: the mirror is visibility, not the ledger of record — a
    failure here must never flip the output's own terminal state, so errors
    are logged and swallowed.
    """
    try:
        async with AsyncSessionLocal() as db:
            # A done mirror also bakes the step's done summary — otherwise the
            # finished render row keeps the progressive stage copy ("正在渲染
            # 视频…" on a ✓ row, the same bug class as the kernel nodes). The
            # locale comes off the run's pinned UI language (display chain).
            summary: str | None = None
            if node_status == "done":
                run_id = (
                    await db.execute(
                        text(
                            "SELECT run_id FROM workflow_steps WHERE kind = 'render' "
                            "AND spec->>'output_id' = :oid LIMIT 1"
                        ),
                        {"oid": str(output_id)},
                    )
                ).scalar_one_or_none()
                run = await db.get(WorkflowRun, run_id) if run_id else None
                ctx = run.context if run is not None and isinstance(run.context, dict) else {}
                zh = str(ctx.get("ui_language") or "").startswith("zh")
                summary = "渲染完成" if zh else "Rendered"
            await db.execute(
                text(
                    "UPDATE workflow_steps SET status = CAST(:st AS varchar), error = :err, "
                    "finished_at = CASE WHEN CAST(:st AS varchar) IN ('done', 'failed') THEN now() "
                    "ELSE finished_at END, "
                    "spec = CASE WHEN CAST(:st AS varchar) = 'done' "
                    "  THEN jsonb_set(spec, '{summary}', to_jsonb(CAST(:summary AS varchar)), true) "
                    "  ELSE spec END, "
                    "updated_at = now() "
                    "WHERE kind = 'render' "
                    # pending/running take any mirror; a success mirror must
                    # also recover a node left 'failed' by an earlier attempt
                    # (re-render after failure would otherwise match 0 rows).
                    "AND (status IN ('pending', 'running') "
                    "     OR (CAST(:st AS varchar) = 'done' AND status = 'failed')) "
                    "AND spec->>'output_id' = :oid"
                ),
                {"st": node_status, "err": error, "oid": str(output_id), "summary": summary},
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "render_node_mirror_failed",
            output_id=str(output_id),
            status=node_status,
            error=str(e),
        )


async def _mirror_superseded_node(output_id: UUID, project: Project) -> None:
    """Terminal mirror for a render DISCARDED as superseded (a morph re-pended
    the row mid-render): only the RUNNING step — the morph's fresh render step
    stays pending for the next claim. Best-effort, same as _mirror_render_node."""
    try:
        lang = display_language(None, project.language)
        summary = "已被新的渲染取代" if lang.startswith("zh") else "Replaced by a newer render"
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE workflow_steps SET status = 'done', finished_at = now(), "
                    "spec = jsonb_set(spec, '{summary}', to_jsonb(CAST(:summary AS varchar)), true), "
                    "updated_at = now() "
                    "WHERE kind = 'render' AND status = 'running' "
                    "AND spec->>'output_id' = :oid"
                ),
                {"oid": str(output_id), "summary": summary},
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "render_node_superseded_mirror_failed",
            output_id=str(output_id),
            error=str(e),
        )


async def render_output(output_id: UUID) -> None:
    """Render a claimed output via the render service; persist terminal state.

    Assumes the output is already claimed (RENDERING). On success writes
    files.video/files.srt + COMPLETED; on any error writes FAILED with the
    message. Terminal state is mirrored onto the render workflow step when present.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Output, Project)
            .join(Project, Output.project_id == Project.id)
            .where(Output.id == output_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.warning("render_output_missing", output_id=str(output_id))
            return
        output, project = row
        user_id = project.user_id
        # render_error is USER copy (the clip card + the mirrored render node
        # row) — localized human lines only; raw httpx/storage innards stay in
        # the structlog event. Locale = the project's display chain (no run
        # context lives on this path).
        lang = display_language(None, project.language)
        if not output.render_spec:
            failed = await db.execute(
                update(Output)
                .where(
                    Output.id == output_id,
                    Output.render_status == RenderStatus.RENDERING,
                )
                .values(
                    render_status=RenderStatus.FAILED,
                    render_error=user_line("render_failed", lang),
                )
            )
            await db.commit()
            if failed.rowcount:
                await _mirror_render_node(
                    output_id, "failed", user_line("render_failed", lang)
                )
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
            # Guarded write (2026-08-15 morph/render race): a morph landing
            # mid-render re-pends the row (RENDERING -> PENDING) with a fresh
            # spec. The conditional UPDATE matches 0 rows then — this render's
            # product is STALE and must be discarded, never clobber the row
            # (the re-pend renders the fresh spec on a later claim).
            claimed = await db.execute(
                update(Output)
                .where(
                    Output.id == output_id,
                    Output.render_status == RenderStatus.RENDERING,
                )
                .values(
                    files={**files, "video": data["video"], "srt": data["srt"]},
                    render_status=RenderStatus.COMPLETED,
                    render_error=None,
                )
            )
            await db.commit()
            if claimed.rowcount == 0:
                logger.info("render_superseded", output_id=str(output_id))
                for orphan_key in (video_key, srt_key):
                    try:
                        await delete(orphan_key)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "render_superseded_delete_failed",
                            key=orphan_key,
                            error=str(e),
                        )
                await _mirror_superseded_node(output_id, project)
                return
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
            # Same guard as the success path: a mid-render morph owns the row
            # now — the stale failure must not clobber its re-pend.
            failed = await db.execute(
                update(Output)
                .where(
                    Output.id == output_id,
                    Output.render_status == RenderStatus.RENDERING,
                )
                .values(
                    render_status=RenderStatus.FAILED,
                    render_error=user_line("render_failed", lang),
                )
            )
            await db.commit()
            if failed.rowcount:
                await _mirror_render_node(
                    output_id, "failed", user_line("render_failed", lang)
                )
