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

Two caption modes ride both uses (``spec.bilingual``, 2026-08-14 双语字幕):
- single (default): the caption track is REPLACED by its translation.
- bilingual: the original word-level track stays; the translation lands
  on ``translation_track`` (unit-level cues) and the renderer shows the
  pair — translation as the primary line, original smaller beneath.

Either way the clip's title overlay is translated along (a subtitled clip
with an untranslated title card reads broken — dub 2026-08-09 同款).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import translator
from app.providers.llm.minimax import MiniMaxError
from app.models.schemas import RenderStatus
from app.models.tables import GraphNode, Output, WorkflowStep, Project, WorkflowRun
from app.operations.service import apply_precomputed
from app.pipeline.errors import TransientNodeError, propagate_key
from app.pipeline.graph import TRANSCRIPT, NodeBase, estimate_agent, token_bounds
from app.pipeline.morph import (
    _fan_out_renders,
    _guard_target_differs_from_source,
    _has_producer_upstream,
    _modifier_target_clips,
    _pend_suppressed_base_renders,
    _record_target_output_ids,
    _run_origin,
)
from app.pipeline.step_display import _fill_summary, _set_stage, _set_summary, ui_lang_of
from app.tools.captions.procedure import (
    TRANSLATION_ARTIFACT_KEY,
    build_translation_cues,
    find_reusable_translation,
    spread_translation_cues,
    translate_text,
    translation_source_hash,
    unit_translation_cues,
)


class TranslateClip(NodeBase):
    kind = "translate_clip"
    family = "assemble"  # 画布三族 (ADR-072 批 A3) — 装配站 (字幕成片)
    doc_station = "translation"  # 两站拆分: 文档站 = 译文稿 (ADR-072)
    task_name = "Translate captions"
    task_name_zh = "翻译字幕"
    # Acts on clips: this run's select_clips / materialize_source when one
    # exists (ADR-043), else the project's existing clips (empty inputs).
    after = ("select_clips", "materialize_source")
    requires = (TRANSCRIPT,)
    retries = 2
    agents = (translator,)

    # 图节点 (ADR-057): translate_clip is a GENERATOR node on the persistent
    # graph — its prompt is the parameterized intent (target language,
    # bilingual), editable on the card; each language's product lands in the
    # node's own product region.
    def estimate(self, ctx: dict) -> dict | None:
        """One translator call per target clip, sized by the caption text —
        knowable only when the clips EXIST at compile time. A translate
        fan-out chained on this run's own clips node (select_clips or
        materialize_source — initial generation, RECIPES §4.1 字幕卡) is
        unquotable here: NULL (未估价)."""
        if (
            {"select_clips", "materialize_source"} & set(ctx.get("input_kinds", ()))
            # The recipe card's sticker quotes the DECLARED typical source
            # (RECIPE_QUOTE_FACTS clips exist by declaration) — the guard is
            # for the live book, where the clips are unborn at compile time.
            and ctx.get("quote_scope") != "recipe"
        ):
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
        bilingual = bool((node.spec or {}).get("bilingual"))
        await _set_stage(node.id, "translating_captions")
        clips = await _modifier_target_clips(db, node, project)
        if not clips:
            await _set_summary(
                node.id,
                "没有可翻译的片段" if ui_lang_of(run, project).startswith("zh") else "No clips to translate",
            )
            return []

        origin = await _run_origin(db, run)
        # Same-language guard (2026-08-17 走查实修) — translating zh into zh
        # renders a 繁体+简体 "bilingual" pair with no English; fail loud with
        # the fix named, never a silent same-language rewrite.
        await _guard_target_differs_from_source(
            db, clips, lang, zh=ui_lang_of(run, project).startswith("zh")
        )
        # 译文 artifact 复用钩 (ADR-072 批 A2): the cue rows live on the graph
        # node's spec (persistent across runs — a re-render revision reads
        # them, translator capture 0). Hash = source cue times+words + title +
        # language; the TRANSLATED text is never hashed — the user's edit of
        # the 译文 IS the artifact's content (改字后重渲染不再买翻译).
        from app.pipeline.graph_fill import (  # deferred: import cycle
            merge_translation_artifact,
        )

        gnode_id = (node.spec or {}).get("graph_node_id")
        gnode = (
            await db.get(GraphNode, UUID(str(gnode_id))) if gnode_id else None
        )
        artifact = (
            (gnode.spec or {}).get(TRANSLATION_ARTIFACT_KEY) if gnode else None
        )
        touched: list[UUID] = []
        for output in clips:
            spec = output.render_spec
            track = (spec or {}).get("caption_track") or []
            if not track:
                continue
            title = dict(spec.get("title") or {})
            title_src = (
                str(title.get("text") or "")
                if title.get("enabled") and str(title.get("text") or "").strip()
                else ""
            )
            source_hash = translation_source_hash(track, title_src, lang, None)
            cached = find_reusable_translation(artifact, str(output.id), source_hash)
            try:
                if cached is not None:
                    rows = cached["rows"]
                    title_text = str((cached.get("title") or {}).get("text") or "")
                else:
                    rows = await build_translation_cues(track, lang)
                    # The title overlay translates along — a subtitled clip
                    # with an untranslated title card reads broken (dub
                    # 2026-08-09 同款).
                    title_text = (
                        await translate_text(
                            title_src, lang, style_hint="a short video title overlay"
                        )
                        if title_src
                        else ""
                    )
                    if gnode is not None:
                        # Persist per clip as it lands (own session): a retry
                        # mid-loop never re-buys the clips already translated.
                        await merge_translation_artifact(
                            UUID(str(gnode.id)),
                            {
                                str(output.id): {
                                    "source_hash": source_hash,
                                    "title": (
                                        {"source": title_src, "text": title_text}
                                        if title_src
                                        else None
                                    ),
                                    "rows": rows,
                                }
                            },
                        )
            except MiniMaxError as e:
                # Provider failure after the client's own retries — still
                # transient at step level (W3 retry budget applies).
                raise TransientNodeError(
                    f"caption translate failed: {e}",
                    user_key=propagate_key(e, "provider_unavailable"),
                ) from e
            if title_text:
                title["text"] = title_text
            if bilingual:
                # 双语对照轨: the original word-level track stays; the
                # translation lands as unit-level cues on
                # translation_track (renderer pairs them by time).
                new_spec = {
                    **spec,
                    "translation_track": unit_translation_cues(rows, lang),
                    "title": title,
                    "target_language": lang,
                }
            else:
                # A plain re-translate collapses a bilingual spec back to
                # single-language (the translation becomes THE track).
                new_spec = {
                    **spec,
                    "caption_track": spread_translation_cues(rows, lang),
                    "translation_track": [],
                    "title": title,
                    "target_language": lang,
                }
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
        # Skip-rescue: targets left on their base spec (no caption track)
        # still owe a render when the producer's fan-out was suppressed for
        # this chain. Defer to a later morph only when it can see the skips:
        # a producer edge unions the full output_refs downstream; an
        # all-skip leaves empty refs so the later morph falls back to the
        # project-wide set; a partial touch without a producer edge renders
        # the skips now — the later morph would never see them.
        await _pend_suppressed_base_renders(
            db, run, node, clips, exclude=set(touched),
            defer_to_later_morph=not touched or await _has_producer_upstream(db, node),
        )
        if not touched:
            return []
        await _fan_out_renders(db, run, node, touched, defer_to_later_morph=not fork)
        await _record_target_output_ids(node.id, touched)
        await _fill_summary(
            node.id, self.kind, ui_language=ui_lang_of(run, project), n=len(touched), lang=lang.upper()
        )
        return touched
