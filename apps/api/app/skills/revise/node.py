"""revise_script node (ADR-039 P1: runner relocated from pipeline/node_runners).

Targeted hook/clip revision via the reviser declaration (small topology).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ClipPayload, Segment
from app.models.tables import Output, WorkflowStep, Project, WorkflowRun
from app.pipeline.step_display import _fill_summary
from app.platform.project_context import persona_context_from_row, resolve_persona
from app.skills.revise.procedure import revise_by_instruction


async def run_script_revision(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
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
    await _fill_summary(node.id, "script", scope=node.spec.get("scope", "clip"))
    return [output.id]
