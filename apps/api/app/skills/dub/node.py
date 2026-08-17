"""dub_clip node (ADR-039 P2 objectified: the P1 runner is now a NodeBase).

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

from app.agents.roster import translator
from app.models.schemas import RenderStatus
from app.models.tables import Output, WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.errors import TransientNodeError
from app.pipeline.graph import MEDIA, NodeBase, estimate_mechanical
from app.pipeline.morph import (
    _fan_out_renders,
    _guard_target_differs_from_source,
    _modifier_target_clips,
    _pend_suppressed_base_renders,
    _record_target_output_ids,
    _run_origin,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary, ui_lang_of
from app.pipeline.tracks import spec_provenance
from app.skills.dub.procedure import synthesize_dub

logger = structlog.get_logger()


class DubClip(NodeBase):
    kind = "dub_clip"
    task_name = "Dub voice"
    task_name_zh = "声音配音"
    # Acts on clips: this run's select_clips / materialize_source when one
    # exists (ADR-043), else the project's existing clips (empty inputs).
    after = ("select_clips", "materialize_source")
    requires = (MEDIA,)
    retries = 2
    agents = (translator,)

    def canvas_group(self, node):
        # One dub card per language — multi-language runs stack them in
        # parallel, each its own mention target.
        lang = (node.spec or {}).get("target_language") or ""
        return f"dub:{lang}"

    def estimate(self, ctx: dict) -> dict | None:
        """TTS 按字符 / 克隆按次 + translator token range, driven by the
        target clips' caption text — knowable only when the clips EXIST at
        compile time. A dub fan-out chained on this run's own clips node
        (select_clips or materialize_source — initial generation) is
        unquotable here: NULL (未估价)."""
        if {"select_clips", "materialize_source"} & set(ctx.get("input_kinds", ())):
            return None
        clips = ctx["clips"]
        if not clips:
            return None
        n = len(clips)
        caption_chars = sum(c["caption_chars"] for c in clips)
        # translator: one caption-track call per clip (+ up to one title
        # call); TTS: one synthesis per ~10-word unit, charged per char of
        # translated caption text — the source caption chars are the exact
        # unit driver (translation-length variance and fit re-takes, bounded
        # at 2×, ride the calibration loop).
        units: dict[str, float] = {"tts_chars": float(caption_chars)}
        if ctx["voice_clone_needed"]:
            units["voice_clones"] = 1.0
        return estimate_mechanical(
            units,
            prompt=[100 * n, 1400 * n],
            completion=[100 * n, 1600 * n],
        )

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Dub existing clips with the persona's cloned voice, then re-render
        (modifier step — morph in place, or fork into derived rows)."""
        lang = (node.spec or {}).get("target_language") or "en"
        fork = bool((node.spec or {}).get("fork"))
        await _set_stage(node.id, "dubbing")
        clips = await _modifier_target_clips(db, node, project)
        if not clips:
            await _set_summary(
                node.id,
                "没有可配音的片段" if ui_lang_of(run, project).startswith("zh") else "No clips to dub",
            )
            return []

        origin = await _run_origin(db, run)
        # Same-language guard (2026-08-17, translate 同款): dubbing zh into
        # zh clones the voice over the same words — pointless spend, fail
        # loud with the fix named.
        await _guard_target_differs_from_source(
            db, clips, lang, zh=ui_lang_of(run, project).startswith("zh")
        )
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
                # Derived row: language + provenance via the track-declaration
                # fold (ADR-044; the fork's spec carries the generated dub
                # track → "generated", cloned-voice synthetic audio — honest
                # disclosure metadata); source_ref
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
                    provenance=spec_provenance(new_spec),
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
            # Whole batch unresolvable — rescue the suppressed base renders
            # first so the clips still come out (pre-suppression behavior),
            # then fail the step.
            await _pend_suppressed_base_renders(db, run, node, clips)
            raise ValueError("No clips could be dubbed (missing captions or voice sample)")
        # Skip-rescue: per-clip skips keep their base spec — they still owe
        # a render when the producer's fan-out was suppressed for this chain.
        await _pend_suppressed_base_renders(db, run, node, clips, exclude=set(touched))
        await _fan_out_renders(db, run, node, touched, defer_to_later_morph=not fork)
        await _record_target_output_ids(node.id, touched)
        await _fill_summary(
            node.id, self.kind, ui_language=ui_lang_of(run, project), n=len(touched), lang=lang.upper()
        )
        return touched
