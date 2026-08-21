"""revise_script node (ADR-039 P2 objectified: the P1 runner is now a NodeBase).

Targeted hook/clip revision via the reviser declaration (small topology).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ClipPayload, Segment
from app.models.tables import Output, WorkflowStep, Project, WorkflowRun
from app.pipeline.graph import NodeBase, estimate_agent
from app.pipeline.step_display import _fill_summary, ui_lang_of
from app.platform.project_context import persona_context_from_row, resolve_persona
from app.tools.revise.agents import reviser
from app.tools.revise.procedure import revise_by_instruction


class ReviseScript(NodeBase):
    kind = "revise_script"
    task_name = "Write script"
    task_name_zh = "撰写脚本"
    produces_outputs = True
    agents = (reviser,)

    def estimate(self, ctx: dict) -> dict | None:
        """One reviser call on one existing output (its source_text segment
        + the instruction); no mechanical ops, no re-render."""
        return estimate_agent([200, 4000], [200, 1200])

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Targeted hook/clip revision via the reviser agent (small topology)."""
        target_id = node.spec.get("target_id")
        if not target_id:
            raise ValueError("target_id is required for script revision")

        output = await db.get(Output, UUID(str(target_id)))
        if output is None or output.project_id != project.id or output.type != "clip":
            raise ValueError("Target clip not found")
        if not output.source_ref or not output.source_ref.get("segment"):
            raise ValueError("Clip has no source segment to revise from")

        segment = Segment.model_validate(output.source_ref["segment"])
        persona = await resolve_persona(db, project)
        payload = ClipPayload.model_validate(output.payload)

        revised = await revise_by_instruction(
            clip_hook=payload.hook,
            clip_duration=payload.duration,
            clip_title_options=payload.title_options or [],
            clip_music_mood=payload.music_mood,
            segment=segment,
            instruction=node.spec.get("instruction") or "Improve this clip",
            persona=persona_context_from_row(persona),
            scope=node.spec.get("scope", "clip"),
        )
        output.payload = ClipPayload(
            hook=revised.hook,
            title_options=revised.title_options,
            music_mood=revised.music_mood,
            duration=revised.duration_seconds,
        ).model_dump(mode="json")
        if revised.recommendation_score is not None:
            output.score = {
                "value": revised.recommendation_score,
                "reason": revised.score_reason or (output.score or {}).get("reason"),
            }
        output.updated_at = datetime.now(UTC)
        output.workflow_step_id = node.id
        await db.flush()
        await _fill_summary(
            node.id, self.kind,
            ui_language=ui_lang_of(run, project),
            # The recap names the human target (title option, hook fallback),
            # never the internal scope slug ("hook_and_title" is not copy).
            title=next((t for t in (payload.title_options or []) if t), None)
            or payload.hook[:40]
            or "clip",
        )
        return [output.id]
