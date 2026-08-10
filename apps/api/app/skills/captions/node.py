"""translate_clip node (ADR-039 P1: runner relocated from pipeline/node_runners).

Translate existing clips' caption tracks into the target language, then
re-render (modifier step — acts on existing clips, not a generation).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minimax import MiniMaxError
from app.models.schemas import RenderStatus
from app.models.tables import WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.errors import TransientNodeError
from app.pipeline.morph import (
    _fan_out_renders,
    _modifier_target_clips,
    _record_target_output_ids,
    _run_origin,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary
from app.skills.captions.procedure import translate_caption_track


async def run_translate_clip(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Translate existing clips' caption tracks into the target language, then
    re-render (modifier step — acts on existing clips, not a generation)."""
    lang = (node.spec or {}).get("target_language")
    if not lang:
        raise ValueError("target_language is required for translate_clip")
    await _set_stage(node.id, "translating_captions")
    clips = await _modifier_target_clips(db, node, project)
    if not clips:
        await _set_summary(node.id, "No clips to translate")
        return []

    origin = await _run_origin(db, run)
    touched: list[UUID] = []
    for output in clips:
        spec = output.render_spec
        track = (spec or {}).get("caption_track") or []
        if not track:
            continue
        try:
            new_track = await translate_caption_track(track, lang)
        except MiniMaxError as e:
            # Provider failure after the client's own retries — still
            # transient at step level (W3 retry budget applies).
            raise TransientNodeError(f"caption translate failed: {e}") from e
        await apply_precomputed(
            db,
            output,
            "translate_captions",
            {"target_language": lang},
            {**spec, "caption_track": new_track, "target_language": lang},
            source=origin,
            user_id=project.user_id,
        )
        output.render_status = RenderStatus.PENDING
        output.render_error = None
        await db.flush()
        touched.append(output.id)

    if not touched:
        await _set_summary(node.id, "No captions to translate")
        return []
    await _fan_out_renders(db, run, node, touched)
    await _record_target_output_ids(node.id, touched)
    await _fill_summary(node.id, "translate_clip", n=len(touched), lang=lang)
    return touched
