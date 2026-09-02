"""select_clips node (ADR-039 P2 objectified: the P1 runner is now a NodeBase).

Select segments + write scripts + build render specs (composite node — Phase 1
keeps selection and script fused in one clip-writer call). Also fans out one
render node per produced clip (claimed via outputs.render_status, D2).
"""

from uuid import UUID

import structlog
from sqlalchemy import bindparam, delete, select, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.brand import (
    brand_from_block,
    music_from_plan,
    resolve_brand_block,
)
from app.models.schemas import (
    AssetType,
    ClipPayload,
    RenderStatus,
)
from app.models.tables import (
    Asset,
    Music,
    Output,
    WorkflowStep,
    Project,
    WorkflowRun,
)
from app.pipeline.clip_spec import build_clip_spec
from app.pipeline.edges import _load_plan_prelude_outputs
from app.pipeline.graph import MEDIA, TRANSCRIPT, NodeBase, estimate_agent, token_bounds
from app.pipeline.morph import _later_inplace_morph_exists, _render_step_label
from app.agents.base import MAX_CHARS_PER_TEXT
from app.agents.contexts import _generation_context
from app.pipeline.step_context import (
    _list_assets,
    collect_asset_media,
)
from app.pipeline.step_display import (
    _fill_summary,
    _node_slot,
    _pop_spec_field,
    _set_stage,
    slot_tag,
    ui_lang_of,
)
from app.platform.project_context import collect_asset_texts, resolve_run_persona
from app.tools.clips.agents import clip_writer
from app.tools.clips.transcript import build_anchored_transcript
from app.tools.stills.agents import stills_editor, stills_editor_outline
from app.tools.stills.beats import plan_still_beats
from app.providers.storage import stream_url

logger = structlog.get_logger()


async def resolve_render_source(
    db: AsyncSession, node: WorkflowStep, assets: list[Asset]
) -> tuple[Asset | None, str, list[str]]:
    """The render-source decision shared by select_clips and materialize_source
    (ADR-043 — one home, never a second copy): an upstream align_stills edge
    wins (its timeline-materialized transcript asset); else a video with
    words; else an audio with words; else a stills set. Returns
    ``(render_source, render_kind, still_images)``."""
    aligned_source: Asset | None = None
    for upstream_id in node.inputs or []:
        upstream = await db.get(WorkflowStep, UUID(str(upstream_id)))
        if upstream is None or upstream.kind != "align_stills":
            continue
        aligned_id = (upstream.spec or {}).get("aligned_asset_id")
        if aligned_id:
            candidate = await db.get(Asset, UUID(str(aligned_id)))
            if candidate is not None and (candidate.meta or {}).get("words"):
                aligned_source = candidate
        break

    def _has_words(a: Asset) -> bool:
        return bool(a.file_url and (a.meta or {}).get("words"))

    slide_page_urls = [
        u
        for a in assets
        if a.type == AssetType.SLIDES
        for p in (a.slide_pages or [])
        if (u := stream_url(p))
    ]
    image_urls = [
        u
        for a in assets
        if a.type == AssetType.IMAGE and (u := stream_url(a.file_url))
    ]
    still_images = slide_page_urls + image_urls
    source_video = next(
        (a for a in assets if a.type == AssetType.VIDEO and _has_words(a)),
        None,
    )
    source_audio = next(
        (a for a in assets if a.type == AssetType.AUDIO and _has_words(a)),
        None,
    )
    first_visual = next(
        (
            a
            for a in assets
            if a.type in (AssetType.SLIDES, AssetType.IMAGE) and a.file_url
        ),
        None,
    )
    if aligned_source is not None:
        return aligned_source, "stills", still_images
    if source_video is not None:
        return source_video, "video", still_images
    if source_audio is not None:
        return source_audio, "stills", still_images
    if first_visual is not None and still_images:
        return first_visual, "stills", still_images
    return None, "video", still_images


class SelectClips(NodeBase):
    kind = "select_clips"
    task_name = "Generate clips"
    task_name_zh = "生成短片"
    output_type = "clips"
    slot_label = "Clips"
    slot_label_zh = "切片"
    needs_plan_prelude = True
    requires = (MEDIA, TRANSCRIPT)
    produces_outputs = True
    count_default = 3
    count_limits = (1, 10)
    agents = (clip_writer, stills_editor, stills_editor_outline)

    # No canvas_group (2026-08-19 名词节点收窄): the canvas renders nouns
    # only (素材 / 文本 / 产物) — the selection is a process VERB. Its two old
    # card roles demote cleanly: intervention ("swap segment 3") = chat on
    # the clip product / the expanded spine's step pill (@workflow_step);
    # the clip cards' fan-out lineage anchor = the 过程脊 (every keyless
    # step's edges resolve there). Same precedent as translate_clip
    # (2026-08-15).
    def estimate(self, ctx: dict) -> dict | None:
        """One clip_writer call (multimodal): anchored transcript + asset
        texts + media snippets, completion scaling with the clip count;
        stills chains (align_stills upstream) add one text-only editor call
        per clip (期 2 剪辑师 — two-stage overage is the ledger's calibration
        domain). The per-clip render fan-out is born mid-run — unquoted (P4 NULL)."""
        chars = min(ctx["text_chars"], MAX_CHARS_PER_TEXT * ctx["text_count"])
        prompt = token_bounds(chars)
        prompt[0] += 800 * ctx["media_count"] + 500
        prompt[1] += 4000 * ctx["media_count"] + 2000
        slot = (ctx["spec"] or {}).get("slot") or {}
        count = slot.get("count") or self.count_default
        completion = [80 * count, 200 * count]
        if "align_stills" in (ctx.get("input_kinds") or ()):
            prompt[0] += 600 * count
            prompt[1] += 1500 * count
            completion[0] += 80 * count
            completion[1] += 250 * count
        return estimate_agent(prompt, completion)

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Select segments + write scripts + build render specs (composite node).

        Phase 1 keeps selection and script fused in one clip-agent call (Phase 2
        splits selection/script into separate nodes). Also fans out one render
        node per produced clip (claimed via outputs.render_status, D2).
        """
        ctx = run.context or {}
        # 质检打回 (期 3): a bounced round's feedback rides the spec exactly
        # once — pop it so a later targeted regen never eats stale feedback.
        # The row write goes through _pop_spec_field's own session (D9,
        # 2026-08-28): an ORM assignment here would dirty the Session-2 node,
        # and the next autoflush would lock this row for the rest of the run
        # — deadlocking this runner's own display writers.
        spec = dict(node.spec or {})
        feedback = spec.pop("feedback", None)
        if feedback is not None:
            await _pop_spec_field(node.id, "feedback")
        slot = _node_slot(node, ctx, "clips")
        clip_count = (slot.count if slot else None) or self.count_default
        # Language resolves per slot first, then the task-book language.
        target_language = (
            (slot.language if slot else None) or ctx.get("target_language", "en")
        )

        await _set_stage(node.id, "selecting_segments")

        asset_texts = await collect_asset_texts(db, project.id)
        assets = await _list_assets(db, project.id)
        persona = await resolve_run_persona(db, run, project)
        brand_cfg, brand_music_id = await resolve_brand_block(db, persona)
        generation_context = _generation_context(
            run, project, persona, brand_music_id=brand_music_id
        )
        generation_context.target_language = target_language
        understanding, storyboard = await _load_plan_prelude_outputs(db, node)

        # Render source selection (docs/VIDEO_EDITOR.md §4) — the shared
        # decision (materialize_source resolves the same way).
        render_source, render_kind, still_images = await resolve_render_source(
            db, node, assets
        )

        async def _load_music_pieces() -> list[dict[str, str]]:
            music_rows = (
                await db.execute(
                    select(Music)
                    .where(Music.is_public.is_(True))
                    .order_by(Music.created_at.desc())
                )
            ).scalars().all()
            return [
                {"id": str(m.id), "mood": str(m.mood), "title": str(m.title)}
                for m in music_rows
            ]

        # Full-talk anchored transcript: the clip agent copies coarse timestamps
        # from line anchors; locate_span snaps them to word boundaries.
        anchored_transcript = (
            build_anchored_transcript((render_source.meta or {}).get("words") or [])
            if render_source is not None
            else None
        )

        # A schema rejection is answered by the harness's one bounded repair
        # round inside Agent.call (ADR-039 P3) — no blind retries here; a
        # second rejection is the node's failure (the graph's retry semantics).
        plans = await clip_writer.call(
            asset_texts=asset_texts,
            context=generation_context,
            understanding=understanding,
            storyboard=storyboard,
            asset_media=await collect_asset_media(assets),
            clip_count=clip_count,
            anchored_transcript=anchored_transcript,
            music_pieces=await _load_music_pieces(),
            repair_feedback=feedback,
        )

        await _set_stage(node.id, "building_specs")

        # Idempotency: clear this project's prior clip outputs before writing new
        # ones (same semantics as the retired _delete_prior_outputs). Pending
        # render nodes pointing at the deleted rows are cancelled (skipped).
        prior_clip_ids = (
            await db.execute(
                select(Output.id).where(
                    Output.project_id == project.id, Output.type == "clip"
                )
            )
        ).scalars().all()
        if prior_clip_ids:
            await db.execute(
                _text(
                    "UPDATE workflow_steps SET status = 'skipped', updated_at = now() "
                    "WHERE kind = 'render' AND status = 'pending' "
                    "AND spec->>'output_id' IN :oids"
                ).bindparams(bindparam("oids", expanding=True)),
                {"oids": [str(oid) for oid in prior_clip_ids]},
            )
            await db.execute(
                delete(Output).where(Output.id.in_(prior_clip_ids))
            )

        brand = brand_from_block(brand_cfg)
        brand_ref = persona.id if persona is not None else None
        cfg = brand_cfg
        # Frame format: the chain's aspect param (spec, user-named) wins,
        # then the run.context carry-over (legacy books), then the skin
        # default (2026-08-14 三档画幅; ADR-043 参数化).
        aspect = str(
            (node.spec or {}).get("aspect")
            or ctx.get("aspect")
            or cfg.get("aspect", "9:16")
        )
        cap_pos = cfg.get("captionPosition")
        cap_style_raw = cfg.get("captionStylePreset")
        cap_style = cap_style_raw if isinstance(cap_style_raw, str) else "clean-bottom"
        ttl_pos = cfg.get("titlePosition")
        ttl_size_raw = cfg.get("titleSize")
        ttl_size = int(ttl_size_raw) if isinstance(ttl_size_raw, (int, float)) else None
        ttl_enabled_raw = cfg.get("titleEnabled")
        ttl_enabled = True if ttl_enabled_raw is None else bool(ttl_enabled_raw)

        # Render ownership (2026-08-15 morph/render race): when a NON-FORK
        # morph sits later in this run, it rewrites these outputs' specs in
        # place and owns the render — the base fan-out would be dead work and
        # a last-writer-wins race on the rows. Leave render_status NULL; the
        # morph pends + fans out (skips are rescued by the morph).
        suppressed = await _later_inplace_morph_exists(db, run, node)
        output_ids: list[UUID] = []
        for plan in plans.clips[:clip_count]:
            segment = plan.to_segment()
            music = await music_from_plan(db, plan, brand_cfg)
            # 期 2 剪辑师 (stills 首接): the beat plan subdivides the clip's
            # narration span into planned shots. Editor failure degrades to
            # the legacy even split — never fails the clip.
            beat_plan = None
            if render_kind == "stills" and render_source is not None and still_images:
                try:
                    beat_plan = await plan_still_beats(
                        render_source, segment, understanding, assets
                    )
                except Exception as e:  # noqa: BLE001 — even-split fallback
                    logger.warning("beat_plan_failed", error=str(e))
            # Clip agent decides whether burned-in captions make sense for this segment;
            # the skin block only supplies the default.
            caption_enabled = (
                plan.caption_enabled
                if getattr(plan, "caption_enabled", None) is not None
                else brand.caption_enabled
            )
            spec = (
                build_clip_spec(
                    render_source,
                    segment,
                    generation_context.target_language,
                    kind=render_kind,
                    aspect=aspect,
                    caption_position=cap_pos,
                    caption_enabled=caption_enabled,
                    caption_style_preset=cap_style,
                    title_size=ttl_size,
                    title_position=ttl_pos,
                    title_enabled=ttl_enabled,
                    image_urls=still_images if render_kind == "stills" else None,
                    beat_plan=beat_plan,
                    brand=brand,
                    music=music,
                    brand_ref=brand_ref,
                )
                if render_source is not None
                else None
            )
            spec_dict = spec.model_dump(mode="json") if spec else None
            output = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="clip",
                language=target_language,
                # birth: no generated track rides yet (ADR-026)
                provenance="real",
                payload=ClipPayload(
                    hook=plan.hook,
                    title_options=plan.title_options or ([plan.title] if plan.title else []),
                    music_mood=plan.music_mood,
                    duration=plan.duration_seconds,
                ).model_dump(mode="json"),
                source_ref={
                    "segment": segment.model_dump(mode="json"),
                    "start_seconds": plan.start_seconds,
                    "end_seconds": plan.end_seconds,
                    "asset_id": str(render_source.id) if render_source is not None else None,
                },
                render_spec=spec_dict,
                render_status=(RenderStatus.PENDING if not suppressed else None) if spec_dict else None,
                score={
                    "value": plan.recommendation_score,
                    "reason": plan.score_reason or None,
                },
                publishing={
                    "title": plan.title or None,
                    "description": plan.description or None,
                    "hashtags": plan.hashtags or None,
                    "topic": plan.topic or None,
                },
            )
            db.add(output)
            await db.flush()
            output_ids.append(output.id)

        # Render fan-out (D2): one render node per clip with a render spec. These
        # nodes are NOT claimed via the node claim — the render worker claims the
        # output row (render_status=PENDING) and mirrors terminal state back here.
        # (Skipped when the render's owner sits downstream — a later non-fork
        # morph; see above.)
        if not suppressed:
            max_seq = int(node.seq)
            label = await _render_step_label(db, run)
            for idx, output_id in enumerate(output_ids, start=1):
                db.add(
                    WorkflowStep(
                        run_id=run.id,
                        kind="render",
                        status="pending",
                        seq=max_seq + idx,
                        inputs=[str(node.id)],
                        spec={
                            "output_id": str(output_id),
                            **({"summary": label} if label else {}),
                        },
                    )
                )
            await db.flush()

        await _fill_summary(
            node.id,
            self.kind,
            tag=slot_tag(slot),
            ui_language=ui_lang_of(run, project),
            n=len(output_ids),
            total_seconds=sum(
                int(plan.duration_seconds or 0) for plan in plans.clips[:clip_count]
            ),
        )

        return output_ids
