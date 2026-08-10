"""add_music node (ADR-039 P1: runner relocated from pipeline/node_runners).

Score existing clips with a music bed, then re-render. Resolution order (all
by code, never the LLM): music_id → mood → persona skin default → "calm".
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.brand import resolve_music_ref
from app.models.schemas import ClipMusic, ClipSpec, RenderStatus
from app.models.tables import WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.morph import (
    _fan_out_renders,
    _record_target_output_ids,
    _run_origin,
    _target_clips,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary
from app.platform.project_context import resolve_persona
from app.tools.storage import public_url


async def run_add_music(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Score existing clips with a music bed, then re-render.

    Resolution order (all by code, never the LLM): music_id → mood → brand
    default → "calm". A mood with no matching track fails the step with a
    clear error (CHAT_ARCH §10: the conversation offers alternatives).
    """
    await _set_stage(node.id, "adding_music")
    clips = await _target_clips(db, node, project)
    if not clips:
        await _set_summary(node.id, "No clips to score")
        return []

    mood = node.spec.get("mood")
    music_id = node.spec.get("music_id")
    gain_db = node.spec.get("gain_db")

    # Resolution order (all by code, never the LLM): music_id → mood →
    # persona skin default → "calm"; each unresolvable ref falls through to
    # the next. Only a fully unresolvable chain fails the step (CHAT_ARCH
    # §10: clear error).
    brand_default: Any = None
    if not music_id and not mood and project.persona_id is not None:
        persona = await resolve_persona(db, project)
        block = (persona.brand or {}) if persona is not None else {}
        brand_default = block.get("musicId") or block.get("musicMood")

    track = None
    for ref in (music_id, mood, brand_default, "calm"):
        if not ref:
            continue
        track = await resolve_music_ref(db, ref)
        if track is not None:
            break
    if track is None:
        raise ValueError(f"No music track found for mood '{mood}'")

    music = ClipMusic(
        music_id=str(track.id),
        url=public_url(track.file_path),
        enabled=True,
        gain_db=float(gain_db) if gain_db is not None else -18.0,
    )
    origin = await _run_origin(db, run)
    touched: list[UUID] = []
    for output in clips:
        spec = ClipSpec.model_validate(output.render_spec)
        await apply_precomputed(
            db,
            output,
            "set_music",
            {"music_id": music.music_id, "enabled": True, "gain_db": music.gain_db},
            spec.model_copy(update={"music": music}).model_dump(mode="json"),
            source=origin,
            user_id=project.user_id,
        )
        output.render_status = RenderStatus.PENDING
        output.render_error = None
        await db.flush()
        touched.append(output.id)

    await _fan_out_renders(db, run, node, touched)
    await _record_target_output_ids(node.id, touched)
    await _fill_summary(node.id, "add_music", mood=track.mood or mood or "calm")
    return touched
