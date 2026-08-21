"""remove_filler node (ADR-039 P2 objectified: the P1 runner is now a NodeBase).

Remove filler words + repeated takes from existing clips, then re-render.
Deterministic (tools/filler.detect + clip_spec.remove_range); never touches
the source media — cuts land as hidden segments in the render_spec.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ClipSpec, RenderStatus
from app.models.tables import Asset, WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.clip_spec import remove_range
from app.pipeline.graph import TRANSCRIPT, NodeBase, estimate_free
from app.pipeline.morph import (
    _fan_out_renders,
    _has_producer_upstream,
    _pend_suppressed_base_renders,
    _record_target_output_ids,
    _run_origin,
    _target_clips,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary, ui_lang_of
from app.tools.filler.detect import detect


class RemoveFiller(NodeBase):
    kind = "remove_filler"
    task_name = "Remove filler words"
    task_name_zh = "去除口头禅"
    after = ("select_clips", "materialize_source")
    requires = (TRANSCRIPT,)

    def estimate(self, ctx: dict) -> dict | None:
        """Deterministic detect — no LLM, no priced units. The re-render
        consequence lives on the fan-out render nodes (born mid-run,
        unquoted this week)."""
        return estimate_free()

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Remove filler words + repeated takes from existing clips, then re-render.

        Deterministic (tools/filler.detect + clip_spec.remove_range); never touches
        the source media — cuts land as hidden segments in the render_spec.
        """
        await _set_stage(node.id, "removing_fillers")
        clips = await _target_clips(db, node, project)
        if not clips:
            await _set_summary(
                node.id,
                "没有可清理的片段" if ui_lang_of(run, project).startswith("zh") else "No clips to clean",
            )
            return []

        origin = await _run_origin(db, run)
        total_fillers = 0
        total_repeats = 0
        touched: list[UUID] = []
        for output in clips:
            spec = ClipSpec.model_validate(output.render_spec)
            asset_id = spec.source.asset_id or (output.source_ref or {}).get("asset_id")
            asset = await db.get(Asset, UUID(str(asset_id))) if asset_id else None
            words = (asset.meta or {}).get("words") if asset else None
            if not words:
                continue
            language = (asset.meta or {}).get("language") or output.language or "en"
            report = detect(words, language)

            new_spec = spec
            applied_fillers = 0
            applied_repeats = 0
            for start, end in report.ranges:
                if not any(
                    not s.hidden and s.start < end and start < s.end
                    for s in new_spec.segments
                ):
                    continue
                new_spec = remove_range(new_spec, start, end)
                if (start, end) in report.repeat_ranges:
                    applied_repeats += 1
                else:
                    applied_fillers += 1
            if new_spec is spec:
                continue

            # Journal the morph (agent-loop-upgrade W4): every render_spec write
            # goes through the operations service — undoable, hash chain intact.
            await apply_precomputed(
                db,
                output,
                "remove_filler",
                {"filler_count": applied_fillers, "repeat_count": applied_repeats},
                new_spec.model_dump(mode="json"),
                source=origin,
                user_id=project.user_id,
            )
            output.render_status = RenderStatus.PENDING
            output.render_error = None
            await db.flush()
            touched.append(output.id)
            total_fillers += applied_fillers
            total_repeats += applied_repeats

        if not touched:
            await _set_summary(
                node.id,
                "没有发现口水词" if ui_lang_of(run, project).startswith("zh") else "No fillers found",
            )
        # Skip-rescue: clips left on their base spec (no fillers found in
        # them) still owe a render when the producer's fan-out was suppressed
        # for this chain. Defer to a later morph only when it can see the
        # skips: a producer edge unions the full output_refs downstream; an
        # all-skip leaves empty refs so the later morph falls back to the
        # project-wide set; a partial touch without a producer edge renders
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
            filler_count=total_fillers,
            repeat_count=total_repeats,
        )
        return touched
