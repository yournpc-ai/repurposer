"""translate_clip node (ADR-039 P2 objectified: the P1 runner is now a NodeBase).

Translate existing clips' caption tracks into the target language, then
re-render (modifier step — acts on existing clips, not a generation).

Two uses ride the same mechanism (N-19 — the use lives in the spec):
- morph (default, chat path): rewrite each target clip's render_spec in
  place and re-render it; sequential translations overwrite each other.
- fork (``spec.fork: true``, recipe path, RECIPES §4.1 多语言字幕卡):
  create one DERIVED Output row per translated clip — source rows
  untouched — so the original and N subtitled versions coexist in one
  run. Provenance is inherited (not hardcoded "generated"): the footage
  and the voice stay the original human ones — only the on-screen text
  is machine-translated.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.roster import translator
from app.clients.minimax import MiniMaxError
from app.models.schemas import RenderStatus
from app.models.tables import Output, WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.errors import TransientNodeError, propagate_key
from app.pipeline.graph import TRANSCRIPT, NodeBase, estimate_agent, token_bounds
from app.pipeline.morph import (
    _fan_out_renders,
    _modifier_target_clips,
    _record_target_output_ids,
    _run_origin,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary, ui_lang_of
from app.skills.captions.procedure import translate_caption_track


class TranslateClip(NodeBase):
    kind = "translate_clip"
    requires = (TRANSCRIPT,)
    retries = 2
    agents = (translator,)

    def canvas_group(self, node):
        # One subs card per language — multi-language runs stack them in
        # parallel, each its own mention target (dub_clip 同款).
        lang = (node.spec or {}).get("target_language") or ""
        return f"subs:{lang}"

    def estimate(self, ctx: dict) -> dict | None:
        """One translator call per target clip, sized by the caption text —
        knowable only when the clips EXIST at compile time. A translate
        fan-out chained on this run's own clips node (initial generation,
        RECIPES §4.1 字幕卡) is unquotable here: NULL (未估价)."""
        if "select_clips" in ctx.get("input_kinds", ()):
            return None
        clips = ctx["clips"]
        if not clips:
            return None
        n = len(clips)
        bounds = token_bounds(sum(c["caption_chars"] for c in clips))
        return estimate_agent(
            [bounds[0] + 100 * n, bounds[1] + 1000 * n],
            [bounds[0], bounds[1] + 500 * n],
        )

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Translate existing clips' caption tracks into the target language,
        then re-render (modifier step — morph in place, or fork into
        derived rows)."""
        lang = (node.spec or {}).get("target_language")
        if not lang:
            raise ValueError("target_language is required for translate_clip")
        fork = bool((node.spec or {}).get("fork"))
        await _set_stage(node.id, "translating_captions")
        clips = await _modifier_target_clips(db, node, project)
        if not clips:
            await _set_summary(
                node.id,
                "没有可翻译的片段" if ui_lang_of(run, project).startswith("zh") else "No clips to translate",
            )
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
                raise TransientNodeError(
                    f"caption translate failed: {e}",
                    user_key=propagate_key(e, "provider_unavailable"),
                ) from e
            new_spec = {**spec, "caption_track": new_track, "target_language": lang}
            if fork:
                # Derived row (dub_clip 同款, RECIPES §4.1): provenance
                # inherited — translated captions over the original voice
                # and footage are not synthetic media; source_ref carries
                # the lineage pointer; score/publishing/payload copied
                # (never shared — one dict, two rows, silent coupling);
                # the render worker fills `files` on render.
                derived = Output(
                    project_id=project.id,
                    workflow_step_id=node.id,
                    type="clip",
                    language=lang,
                    provenance=output.provenance,
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
                # Morph: rewrite in place — journaled so the overwrite is
                # undoable (the fork branch's new rows start their own
                # baseline instead).
                await apply_precomputed(
                    db,
                    output,
                    "translate_captions",
                    {"target_language": lang},
                    new_spec,
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
                "没有可翻译的字幕" if ui_lang_of(run, project).startswith("zh") else "No captions to translate",
            )
            return []
        await _fan_out_renders(db, run, node, touched)
        await _record_target_output_ids(node.id, touched)
        await _fill_summary(
            node.id, self.kind, ui_language=ui_lang_of(run, project), n=len(touched), lang=lang.upper()
        )
        return touched
