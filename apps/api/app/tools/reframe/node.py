"""reframe_clip node (ADR-045 D6): speaker_map / face track → crop_track, re-render.

Deterministic (skills/reframe/procedure.py — YuNet anchors + the write-side
anti-dizzy constraints); never re-times the footage — only the crop track
changes, the segments stay put.
"""

from uuid import UUID

import asyncio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ClipSpec, CropKeyframe, RenderStatus
from app.models.tables import Asset, Output, Project, WorkflowRun, WorkflowStep
from app.operations.service import apply_precomputed
from app.pipeline.graph import MEDIA, NodeBase, estimate_mechanical
from app.pipeline.morph import (
    _fan_out_renders,
    _has_producer_upstream,
    _modifier_target_clips,
    _pend_suppressed_base_renders,
    _record_target_output_ids,
    _run_origin,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary, ui_lang_of
from app.skills.reframe.procedure import compute_crop_track, resolve_mode
from app.tools.storage import download_to_temp

logger = structlog.get_logger()


class ReframeClip(NodeBase):
    kind = "reframe_clip"
    task_name = "Reframe clips"
    task_name_zh = "智能分镜"
    # Acts on clips: this run's select_clips / materialize_source when one
    # exists (ADR-043), else the project's existing clips (empty inputs).
    after = ("select_clips", "materialize_source")
    requires = (MEDIA,)

    def estimate(self, ctx: dict) -> dict | None:
        """Detection cost scales with the kept seconds of the target clips —
        knowable only when the clips EXIST at compile time. A reframe chained
        on this run's own clips node (initial generation) is unquotable
        here: NULL (未估价). Own infrastructure: detect_seconds rides the
        quote as a metering unit, zero-priced like render_seconds."""
        if {"select_clips", "materialize_source"} & set(ctx.get("input_kinds", ())):
            return None
        clips = ctx["clips"]
        if not clips:
            return None
        return estimate_mechanical(
            {"detect_seconds": float(sum(c["seconds"] for c in clips))}
        )

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Write crop_track keyframes onto the target clips, then re-render."""
        await _set_stage(node.id, "reframing_clips")
        clips = await _modifier_target_clips(db, node, project)
        if not clips:
            await _set_summary(
                node.id,
                "没有可分镜的片段" if ui_lang_of(run, project).startswith("zh") else "No clips to reframe",
            )
            return []

        mode_req = (node.spec or {}).get("mode") or "auto"
        origin = await _run_origin(db, run)

        # Phase 1 — compute only, zero DB writes. Detection costs seconds-
        # to-minutes per clip and apply_precomputed locks the output row
        # (FOR UPDATE) until the step-boundary commit, so journaling must not
        # interleave with computing. Per-clip isolation matches the
        # speaker_map processor's posture: one corrupt/unreadable source
        # skips that clip, never fails the run.
        prepared: list[tuple[Output, str, list[CropKeyframe] | None]] = []
        skipped = 0
        for output in clips:
            try:
                spec = ClipSpec.model_validate(output.render_spec)
            except Exception:
                logger.warning(
                    "reframe_clip_spec_invalid", output_id=str(output.id), exc_info=True
                )
                skipped += 1
                continue
            if spec.source.kind != "video":
                # stills/audiogram sources have no video frames to reframe.
                skipped += 1
                continue
            asset_id = spec.source.asset_id or (output.source_ref or {}).get("asset_id")
            asset = await db.get(Asset, UUID(str(asset_id))) if asset_id else None
            if asset is None or not asset.file_url:
                skipped += 1
                continue
            speaker_map = (asset.meta or {}).get("speaker_map")
            mode = resolve_mode(speaker_map, mode_req)
            if mode == "interview_switch" and (
                (speaker_map or {}).get("form") != "interview"
                or not (speaker_map or {}).get("turns")
            ):
                # Nothing honest to switch on — skip the clip, don't touch it
                # (checked before the download: the map alone decides this).
                skipped += 1
                continue

            if mode == "static_center":
                # Undo semantics only: clear the dynamic track and let the
                # clip's static crop speak again — never clobber a manual
                # set_crop (non-destructive doctrine).
                if spec.crop_track is None:
                    skipped += 1  # no reframe on this clip — nothing to undo
                    continue
                prepared.append((output, mode, None))
                continue

            try:
                path = await download_to_temp(asset.file_url)
                if path is None:
                    skipped += 1
                    continue
                try:
                    # CPU-bound (decode + detection, minutes on long sources)
                    # — ride a thread like every other heavy call (ASR /
                    # speaker_map precedent); a bare call freezes the
                    # worker's single loop for the whole pass.
                    keyframes, _resolved = await asyncio.to_thread(
                        compute_crop_track,
                        path,
                        spec.model_dump(mode="json"),
                        speaker_map,
                        mode,
                    )
                finally:
                    path.unlink(missing_ok=True)
            except Exception:
                logger.warning(
                    "reframe_clip_compute_failed", output_id=str(output.id), exc_info=True
                )
                skipped += 1
                continue
            if keyframes is None:
                # No kept main-source windows — a static_center degrade:
                # clear a stale track when one exists, else nothing to undo.
                if spec.crop_track is not None:
                    prepared.append((output, "static_center", None))
                continue
            if not keyframes:
                # No trackable face in the kept windows — skip honestly.
                skipped += 1
                continue
            prepared.append((output, mode, [CropKeyframe(**kf) for kf in keyframes]))

        # Phase 2 — journal + re-pend in one short tail: the FOR UPDATE locks
        # are held for milliseconds, not for the detection pass. Per-clip
        # isolation here too: a clip deleted mid-detection (editor delete /
        # a concurrent select_clips re-run) skips — it must not abort the
        # tail and roll back the clips already journaled.
        touched: list[UUID] = []
        for output, mode, keyframes in prepared:
            try:
                # Re-read fresh and re-apply the delta onto it: the detection
                # pass took minutes, and a concurrent editor save on this clip
                # must survive the morph — only crop_track is this morph's to
                # write.
                await db.refresh(output)
                new_spec = ClipSpec.model_validate(output.render_spec).model_copy(
                    update={"crop_track": keyframes}
                )
                # Journal the morph (agent-loop-upgrade W4): every render_spec
                # write goes through the operations service — undoable, hash
                # chain intact.
                await apply_precomputed(
                    db,
                    output,
                    "reframe_clip",
                    {"mode": mode, "keyframe_count": len(new_spec.crop_track or [])},
                    new_spec.model_dump(mode="json"),
                    source=origin,
                    user_id=project.user_id,
                )
            except Exception:
                logger.warning(
                    "reframe_clip_journal_failed", output_id=str(output.id), exc_info=True
                )
                skipped += 1
                continue
            output.render_status = RenderStatus.PENDING
            output.render_error = None
            await db.flush()
            touched.append(output.id)

        logger.info("reframe_clip_done", touched=len(touched), skipped=skipped)
        if not touched:
            await _set_summary(
                node.id,
                "没有可分镜的片段" if ui_lang_of(run, project).startswith("zh") else "Nothing to reframe",
            )
        # Skip-rescue: clips left on their base spec (no faces / not an
        # interview) still owe a render when the producer's fan-out was
        # suppressed for this chain. Defer to a later morph only when it can
        # see them: a producer edge unions the full output_refs downstream;
        # an all-skip leaves empty refs so the later morph falls back to the
        # project-wide set. A partial touch without a producer edge renders
        # the skips now — the later morph would never see them.
        await _pend_suppressed_base_renders(
            db, run, node, clips, exclude=set(touched),
            defer_to_later_morph=not touched or await _has_producer_upstream(db, node),
        )
        if not touched:
            return []

        await _fan_out_renders(db, run, node, touched)
        await _record_target_output_ids(node.id, touched)
        await _fill_summary(
            node.id,
            self.kind,
            ui_language=ui_lang_of(run, project),
            n=len(touched),
        )
        return touched
