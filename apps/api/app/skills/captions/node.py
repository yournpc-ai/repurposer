"""translate_clip node (ADR-039 P2 objectified: the P1 runner is now a NodeBase).

Translate existing clips' caption tracks into the target language, then
re-render (modifier step — acts on existing clips, not a generation).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.roster import translator
from app.clients.minimax import MiniMaxError
from app.models.schemas import RenderStatus
from app.models.tables import WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.errors import TransientNodeError
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

    def estimate(self, ctx: dict) -> dict | None:
        """One translator call per target clip, sized by the caption text —
        knowable only when clips exist at compile time (a modifier never
        fans out from an initial compile, so no upstream-kind check)."""
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
        """Translate existing clips' caption tracks into the target language, then
        re-render (modifier step — acts on existing clips, not a generation)."""
        lang = (node.spec or {}).get("target_language")
        if not lang:
            raise ValueError("target_language is required for translate_clip")
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
            await _set_summary(
                node.id,
                "没有可翻译的字幕" if ui_lang_of(run, project).startswith("zh") else "No captions to translate",
            )
            return []
        await _fan_out_renders(db, run, node, touched)
        await _record_target_output_ids(node.id, touched)
        await _fill_summary(
            node.id, self.kind, ui_language=ui_lang_of(run, project), n=len(touched), lang=lang
        )
        return touched
