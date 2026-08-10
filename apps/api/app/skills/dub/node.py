"""dub_clip node (ADR-039 P1: runner relocated from pipeline/node_runners).

Dub existing clips with the persona's cloned voice (the package's own
``procedure.synthesize_dub``), then re-render (modifier step).

Two uses ride the same mechanism (N-19 — the use lives in the spec):
- morph (default, chat path): rewrite each target clip's render_spec in
  place and re-render it; sequential dubs overwrite each other.
- fork (``spec.fork: true``, recipe path, RECIPES §4.1): create one
  DERIVED Output row per dubbed clip — source rows untouched — so the
  original and N language versions coexist in one run.
"""

from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import RenderStatus
from app.models.tables import Output, WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.errors import TransientNodeError
from app.pipeline.morph import (
    _fan_out_renders,
    _modifier_target_clips,
    _record_target_output_ids,
    _run_origin,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary
from app.skills.dub.procedure import synthesize_dub

logger = structlog.get_logger()


async def run_dub_clip(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Dub existing clips with the persona's cloned voice, then re-render
    (modifier step — morph in place, or fork into derived rows)."""
    lang = (node.spec or {}).get("target_language") or "en"
    fork = bool((node.spec or {}).get("fork"))
    await _set_stage(node.id, "dubbing")
    clips = await _modifier_target_clips(db, node, project)
    if not clips:
        await _set_summary(node.id, "No clips to dub")
        return []

    origin = await _run_origin(db, run)
    touched: list[UUID] = []
    for output in clips:
        try:
            new_spec = await synthesize_dub(db, output, project, lang)
        except TransientNodeError:
            # Transient failures are the step's, not the clip's — bubble up
            # for step-level retry instead of skipping the clip (W3).
            raise
        except HTTPException as e:
            # Per-clip skip (no captions / no sample usable for this one);
            # a fully unresolvable batch fails the step below.
            logger.info("dub_clip skip output %s: %s", output.id, e.detail)
            continue
        if fork:
            # Derived row: language + provenance="generated" (cloned-voice
            # synthetic audio — honest disclosure metadata); source_ref
            # carries the lineage pointer (derived_from_output_id, JSONB —
            # no column); score/publishing/payload inherit the source row's
            # content metadata (copied — sharing one dict object between two
            # rows would silently couple their later edits); the render
            # worker fills `files` on render.
            derived = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="clip",
                language=lang,
                provenance="generated",
                payload=dict(output.payload or {}),
                source_ref={
                    **(output.source_ref or {}),
                    "derived_from_output_id": str(output.id),
                },
                render_spec=new_spec,
                render_status=RenderStatus.PENDING,
                score=dict(output.score or {}) if output.score else None,
                publishing=dict(output.publishing or {}),
            )
            db.add(derived)
            await db.flush()
            touched.append(derived.id)
        else:
            # Morph: rewrite in place — journaled so the overwrite is undoable
            # (agent-loop-upgrade W4; the fork branch's new rows start their
            # own baseline instead).
            await apply_precomputed(
                db,
                output,
                "set_dub",
                {"enabled": True, "gain_db": 0.0, "target_language": lang},
                new_spec,
                source=origin,
                user_id=project.user_id,
            )
            output.render_status = RenderStatus.PENDING
            output.render_error = None
            await db.flush()
            touched.append(output.id)

    if not touched:
        raise ValueError("No clips could be dubbed (missing captions or voice sample)")
    await _fan_out_renders(db, run, node, touched)
    await _record_target_output_ids(node.id, touched)
    await _fill_summary(node.id, "dub", n=len(touched), lang=lang)
    return touched
