"""reframe_clip node (ADR-045 D6): speaker_map / face track → crop_track, re-render.

Deterministic (skills/reframe/procedure.py — YuNet anchors + the write-side
anti-dizzy constraints); never re-times the footage — only the crop fields
change (crop / crop_track), the segments stay put.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ClipSpec, CropKeyframe, RenderStatus
from app.models.tables import Asset, Project, WorkflowRun, WorkflowStep
from app.operations.service import apply_precomputed
from app.pipeline.graph import MEDIA, NodeBase, estimate_mechanical
from app.pipeline.morph import (
    _fan_out_renders,
    _pend_suppressed_base_renders,
    _record_target_output_ids,
    _run_origin,
    _target_clips,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary, ui_lang_of
from app.skills.reframe.procedure import compute_crop_track, resolve_mode
from app.tools.storage import download_to_temp


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
        clips = await _target_clips(db, node, project)
        if not clips:
            await _set_summary(
                node.id,
                "没有可分镜的片段" if ui_lang_of(run, project).startswith("zh") else "No clips to reframe",
            )
            return []

        mode_req = (node.spec or {}).get("mode") or "auto"
        origin = await _run_origin(db, run)
        touched: list[UUID] = []
        skipped = 0
        for output in clips:
            spec = ClipSpec.model_validate(output.render_spec)
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
            if mode == "interview_switch" and not (speaker_map or {}).get("turns"):
                # Nothing honest to switch on — skip the clip, don't touch it.
                skipped += 1
                continue

            if mode == "static_center":
                # Undo semantics only: clear the dynamic track and let the
                # clip's static crop speak again — never clobber a manual
                # set_crop (non-destructive doctrine).
                if spec.crop_track is None:
                    continue  # no reframe on this clip — nothing to undo
                new_spec = spec.model_copy(update={"crop_track": None})
            else:
                path = await download_to_temp(asset.file_url)
                if path is None:
                    skipped += 1
                    continue
                try:
                    keyframes, _resolved = compute_crop_track(
                        path, spec.model_dump(mode="json"), speaker_map, mode
                    )
                finally:
                    path.unlink(missing_ok=True)
                if not keyframes:
                    # No trackable face in the kept windows — skip honestly.
                    skipped += 1
                    continue
                new_spec = spec.model_copy(
                    update={"crop_track": [CropKeyframe(**kf) for kf in keyframes]}
                )

            # Journal the morph (agent-loop-upgrade W4): every render_spec write
            # goes through the operations service — undoable, hash chain intact.
            await apply_precomputed(
                db,
                output,
                "reframe_clip",
                {"mode": mode, "keyframe_count": len(new_spec.crop_track or [])},
                new_spec.model_dump(mode="json"),
                source=origin,
                user_id=project.user_id,
            )
            output.render_status = RenderStatus.PENDING
            output.render_error = None
            await db.flush()
            touched.append(output.id)

        if not touched:
            await _set_summary(
                node.id,
                "没有可分镜的片段" if ui_lang_of(run, project).startswith("zh") else "Nothing to reframe",
            )
        # Skip-rescue: clips left on their base spec (no faces / not an
        # interview) still owe a render when the producer's fan-out was
        # suppressed for this chain.
        await _pend_suppressed_base_renders(db, run, node, clips, exclude=set(touched))
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
