"""Drive the Remotion render service for a renderable output (clip or film).

The worker claims an output (``render_status=PENDING`` -> RENDERING) and calls
this. It absolutizes the spec's storage-relative URLs (the spec stores relative
keys via the storage seam; the render service needs absolute URLs it can
fetch), POSTs the spec to the render service (black box: spec -> MP4[+SRT]),
and writes the resulting output keys back into ``output.files``.

Two spec families (dispatch reads only ``spec.family``, ADR-016/ADR-119):
- clip (absent family): source/track URLs resolve through the track registry;
  the render yields video + srt.
- film: ``ui.image`` / ``end.logo_url`` resolve here (the film-spec has no
  track registry); the render yields video alone.

Output keys carry a per-render timestamp suffix (``<output_id>-<ts>.mp4``) so a
re-render never overwrites the object a browser may have cached under the same
URL. The previous render's objects are deleted once the new one succeeds.

Render node mirror (RunPlan Phase 1, D2): if the output has a render workflow step
(run-scoped renders), its status mirrors the render lifecycle — the node is
visibility + cost home, the claim stays on ``outputs.render_status`` so
run-less re-renders (manual render / dub / translate) keep working unchanged.
"""

import asyncio
import copy
import json
import time
from pathlib import Path
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
from app.pipeline.render_probe import (
    PROBE_OUTPUT_MISSING,
    ProbeViolation,
    probe_expectation_for,
    probe_rendered_sidecar,
    probe_rendered_video,
)
from app.pipeline.tracks import resolve_spec_urls
from app.providers.storage import (
    delete,
    download_to_temp,
    get_output_path,
    output_url,
    presign_upload,
    public_url,
)
from app.ui_locale import display_language

logger = structlog.get_logger()


def _resolve_url(value: str) -> str:
    """One relative value → absolute (the storage seam's two relative forms)."""
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("/api/"):
        return f"{settings.api_public_url.rstrip('/')}{value}"
    return public_url(value) or value


def _absolutize_film(spec: dict[str, Any]) -> dict[str, Any]:
    """The film family's URL absolutization (no track registry — the
    film-spec's URL-bearing slots: ui.image / end.logo_url / per-scene
    narration ``audio`` / the ``music`` bed)."""
    for scene in spec.get("scenes") or []:
        if scene.get("type") == "ui" and isinstance(scene.get("image"), str):
            scene["image"] = _resolve_url(scene["image"])
        if scene.get("type") == "end" and isinstance(scene.get("logo_url"), str):
            scene["logo_url"] = _resolve_url(scene["logo_url"])
        if isinstance(scene.get("audio"), str):
            scene["audio"] = _resolve_url(scene["audio"])
    music = spec.get("music")
    if isinstance(music, dict) and isinstance(music.get("url"), str):
        music["url"] = _resolve_url(music["url"])
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
    ``spec.family`` (never node type/name): film → its own walk; everything
    else → the clip track registry.
    """
    if spec.get("family") == "film":
        return _absolutize_film(spec)
    # Registry fold (ADR-044): the slots to resolve are each track's declared
    # url_fields — a newly registered track's URLs absolutize with zero changes
    # here.
    return resolve_spec_urls(spec, _resolve_url)


async def _stamp_render_failure(output_id: UUID, failure: dict[str, Any]) -> None:
    """Stamp the structured failure onto the render mirror step's spec — the
    SAME shape as the storyboard stages (``{stage, codes, detail}``, MG D2) so
    the failure stage ledger reads ONE field across the whole film chain.
    Best-effort (the mirror is visibility, not the ledger of record); run-less
    renders have no mirror row and simply match 0."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE workflow_steps SET "
                    "spec = jsonb_set(spec, '{failure}', CAST(:failure AS jsonb), true), "
                    "updated_at = now() "
                    "WHERE kind = 'render' AND spec->>'output_id' = :oid"
                ),
                {"failure": json.dumps(failure), "oid": str(output_id)},
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "render_failure_stamp_failed", output_id=str(output_id), error=str(e)
        )


async def _probe_artifacts(
    spec: dict[str, Any], video_key: str, srt_key: str | None
) -> list[ProbeViolation]:
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
    srt_path: Path | None = None
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
            ]
        violations = await asyncio.to_thread(probe_rendered_video, video_path, expect)
        # Caption sidecar (clip family only — the film family renders video
        # alone): the non-empty bar mirrors the renderer, which writes the
        # srt from spec.caption_track alone (empty track → zero-byte VALID
        # srt); a non-empty track with a missing/empty sidecar is the broken
        # delivery this gate exists to catch.
        cues = bool(spec.get("caption_track"))
        if srt_key is None:
            if cues and not violations:
                violations.append(
                    ProbeViolation(
                        PROBE_OUTPUT_MISSING,
                        "caption track is non-empty but the render returned no srt",
                    )
                )
        elif not violations:
            try:
                srt_path = await download_to_temp(srt_key)
            except Exception as e:  # noqa: BLE001
                return [
                    ProbeViolation(
                        PROBE_OUTPUT_MISSING,
                        f"srt object unreadable from storage: {type(e).__name__}: {e}",
                    )
                ]
            violations.extend(
                await asyncio.to_thread(
                    probe_rendered_sidecar, srt_path, allow_empty=not cues
                )
            )
        return violations
    finally:
        for p in (video_path, srt_path):
            if p is not None:
                p.unlink(missing_ok=True)


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


async def _finalize_owning_run(output_id: UUID) -> None:
    """Render-terminal finalize hook (ADR-074② 翻案 2026-09-13): renders hold
    their run open now, and the mirror step settles HERE (the render chain),
    not in ``execute_step`` — so the render chain owes the run its last
    finalize check. No-op while any sibling step is still active. Only the
    done/failed paths call this: a superseded render's mirror just went done
    but the morph's fresh render step is pending, so the run is still held —
    and this path's own check would see that anyway."""
    from app.pipeline.orchestrator import (  # deferred: rendering stays a leaf
        maybe_finalize_run,
    )

    # One output can fan mirror rows across runs (an in-place morph re-render,
    # a later run's morph on the same clip) and a claim flips every pending
    # mirror — finalize EVERY owning run (terminal runs early-return inside).
    # A LIMIT-1 pick could land on a stale run's row and leave the live run
    # held open forever.
    async with AsyncSessionLocal() as db:
        run_ids = list(
            (
                await db.execute(
                    text(
                        "SELECT DISTINCT run_id FROM workflow_steps "
                        "WHERE kind = 'render' AND spec->>'output_id' = :oid"
                    ),
                    {"oid": str(output_id)},
                )
            )
            .scalars()
            .all()
        )
    for run_id in run_ids:
        await maybe_finalize_run(run_id)


async def _mirror_superseded_node(output_id: UUID, lang: str) -> None:
    """Terminal mirror for a render DISCARDED as superseded (a morph re-pended
    the row mid-render): only the RUNNING step — the morph's fresh render step
    stays pending for the next claim. Best-effort, same as _mirror_render_node."""
    try:
        summary = user_line("render_superseded", lang)
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

    Session discipline (D9, 2026-08-27): a SHORT session snapshots the row,
    NO session is held across the render-service POST (up to 900s — a session
    parked idle-in-transaction there invites lock pileups), and a fresh short
    session lands the guarded terminal write.
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
        mine = output.render_claim_token
        if mine is None:
            # Entry defense (ADR-079): an unclaimed/foreign row (pre-migration
            # in-flight, or a re-pend that already swallowed the claim) —
            # stand down BEFORE spending a render on it. A live claim
            # re-mints the token.
            logger.warning("render_foreign_row_refused", output_id=str(output_id))
            return
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
                    Output.render_claim_token == mine,
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
            else:
                logger.warning(
                    "render_fenced", output_id=str(output_id), tail="no_spec"
                )
            return
        # Snapshot everything the render + terminal write need as plain data —
        # the ORM objects die with this session.
        spec = _absolutize(copy.deepcopy(output.render_spec))
        is_film = spec.get("family") == "film"
        files = dict(output.files or {})
        project_id = output.project_id
        # 素材源缓存桥 (2026-10-07): the render service stages sources into the
        # SAME shared cache the api side reads (stage.ts ↔ storage
        # download_to_cache, one sha1 law) — carry the object key on the
        # ENVELOPE (api↔render, never clip-spec) so staging hits the bytes the
        # processing chain already downloaded instead of re-pulling the source.
        source_key: str | None = None
        source_asset_id = (spec.get("source") or {}).get("asset_id")
        if source_asset_id:
            from app.models.tables import Asset  # deferred: rendering stays a leaf

            source_asset = await db.get(Asset, UUID(str(source_asset_id)))
            if source_asset is not None and source_asset.file_url:
                source_key = str(source_asset.file_url)

    old_video_key = files.get("video")
    old_srt_key = files.get("srt")
    try:
        render_ts = int(time.time())
        video_key = await get_output_path(
            project_id, user_id, f"{output_id}-{render_ts}.mp4"
        )
        # A film renders to video alone (no caption track → no SRT artifact;
        # the render service's film branch likewise requires only video).
        srt_key = (
            None
            if is_film
            else await get_output_path(project_id, user_id, f"{output_id}-{render_ts}.srt")
        )
        video_put_url = await presign_upload(
            video_key, content_type="video/mp4", ttl=900
        )
        srt_put_url = (
            None
            if srt_key is None
            else await presign_upload(srt_key, content_type="text/srt", ttl=900)
        )
        payload = {
            "spec": spec,
            **({"source_key": source_key} if source_key else {}),
            "outputs": {
                "video": {
                    "key": video_key,
                    "put_url": video_put_url,
                    "content_type": "video/mp4",
                },
                **(
                    {
                        "srt": {
                            "key": srt_key,
                            "put_url": srt_put_url,
                            "content_type": "text/srt",
                        }
                    }
                    if srt_key is not None
                    else {}
                ),
            },
        }
        async with httpx.AsyncClient(timeout=settings.render_timeout_seconds) as client:
            resp = await client.post(settings.render_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # 放行闸③ (MG D4 / 禁止事项 10): the artifact must pass the probe gate
        # before the row may settle COMPLETED — a success without a file check
        # is forbidden. One seat, family-dispatched check items. A failed probe
        # settles FAILED (attempt-counted, cap-bounded — never a blind retry)
        # with the structured failure on the render mirror step; the rejected
        # object stays in storage as the forensic record (its key rides the
        # failure detail and the structlog event).
        violations = await _probe_artifacts(
            spec, data["video"], data.get("srt") if srt_key is not None else None
        )
        if violations:
            codes = sorted({v.code for v in violations})
            detail = "; ".join(v.detail for v in violations[:6])[:500]
            logger.warning(
                "render_probe_rejected",
                output_id=str(output_id),
                codes=codes,
                detail=detail,
                video_key=video_key,
            )
            async with AsyncSessionLocal() as db:
                failed = await db.execute(
                    update(Output)
                    .where(
                        Output.id == output_id,
                        Output.render_claim_token == mine,
                    )
                    .values(
                        render_status=RenderStatus.FAILED,
                        render_error=user_line("render_failed", lang),
                    )
                )
                await db.commit()
            if failed.rowcount:
                await _stamp_render_failure(
                    output_id, {"stage": "probe", "codes": codes, "detail": detail}
                )
                await _mirror_render_node(
                    output_id, "failed", user_line("render_failed", lang)
                )
                await _finalize_owning_run(output_id)
            else:
                # Fenced (a morph re-pended mid-render): this render's product
                # is stale regardless of probe outcome — discard the object
                # exactly like the superseded path.
                logger.warning(
                    "render_fenced", output_id=str(output_id), tail="probe"
                )
                for orphan_key in (k for k in (video_key, srt_key) if k):
                    try:
                        await delete(orphan_key)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "render_superseded_delete_failed",
                            key=orphan_key,
                            error=str(e),
                        )
            return

        # Guarded write (ADR-079): the predicate is the claim TOKEN, not the
        # render_status state — a state guard cannot tell executions apart
        # (a re-claim re-enters RENDERING: the morph-window race proof). A
        # morph landing mid-render re-pends the row (RENDERING -> PENDING and
        # the token NULLed) with a fresh spec; a reap + re-claim re-mints the
        # token. Either way this render's conditional UPDATE matches 0 rows —
        # its product is STALE and must be discarded, never clobber the row
        # (the re-pend renders the fresh spec on a later claim).
        async with AsyncSessionLocal() as db:
            claimed = await db.execute(
                update(Output)
                .where(
                    Output.id == output_id,
                    Output.render_claim_token == mine,
                )
                .values(
                    files={
                        **files,
                        "video": data["video"],
                        **({"srt": data["srt"]} if data.get("srt") else {}),
                    },
                    render_status=RenderStatus.COMPLETED,
                    render_error=None,
                )
            )
            await db.commit()
        if claimed.rowcount == 0:
            logger.info("render_superseded", output_id=str(output_id))
            for orphan_key in (k for k in (video_key, srt_key) if k):
                try:
                    await delete(orphan_key)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "render_superseded_delete_failed",
                        key=orphan_key,
                        error=str(e),
                    )
            await _mirror_superseded_node(output_id, lang)
            return
        await _mirror_render_node(output_id, "done")
        await _finalize_owning_run(output_id)

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
            video=output_url(data["video"]),
        )
    except Exception as e:  # noqa: BLE001 — record any failure on the row
        logger.error("render_output_failed", output_id=str(output_id), error=str(e))
        # Same token guard as the success path: a mid-render morph (or a
        # re-claim after reap) owns the row now — the stale failure must not
        # clobber its re-pend.
        async with AsyncSessionLocal() as db:
            failed = await db.execute(
                update(Output)
                .where(
                    Output.id == output_id,
                    Output.render_claim_token == mine,
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
            await _finalize_owning_run(output_id)
