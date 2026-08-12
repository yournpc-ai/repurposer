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
from app.pipeline.edges import _load_director_outputs
from app.pipeline.graph import MEDIA, TRANSCRIPT, NodeBase, estimate_agent, token_bounds
from app.agents.base import MAX_CHARS_PER_TEXT
from app.agents.contexts import _generation_context
from app.pipeline.step_context import (
    _list_assets,
    collect_asset_media,
)
from app.pipeline.step_display import (
    _fill_summary,
    _node_slot,
    _set_stage,
    slot_tag,
    ui_lang_of,
)
from app.platform.project_context import collect_asset_texts, resolve_run_persona
from app.skills.clips.agents import clip_writer
from app.tools.transcript import build_anchored_transcript
from app.tools.storage import stream_url

logger = structlog.get_logger()


class SelectClips(NodeBase):
    kind = "select_clips"
    output_type = "clips"
    slot_label = "Clips"
    slot_label_zh = "切片"
    slot_ordinal = 0
    needs_director = True
    requires = (MEDIA, TRANSCRIPT)
    produces_outputs = True
    count_default = 5
    count_limits = (1, 10)
    agents = (clip_writer,)

    def estimate(self, ctx: dict) -> dict | None:
        """One clip_writer call (multimodal): anchored transcript + asset
        texts + media snippets, completion scaling with the clip count. The
        per-clip render fan-out is born mid-run — unquoted (P4 NULL)."""
        chars = min(ctx["text_chars"], MAX_CHARS_PER_TEXT * ctx["text_count"])
        prompt = token_bounds(chars)
        prompt[0] += 800 * ctx["media_count"] + 500
        prompt[1] += 4000 * ctx["media_count"] + 2000
        slot = (ctx["spec"] or {}).get("slot") or {}
        count = slot.get("count") or self.count_default
        return estimate_agent(prompt, [80 * count, 200 * count])

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Select segments + write scripts + build render specs (composite node).

        Phase 1 keeps selection and script fused in one clip-agent call (Phase 2
        splits selection/script into separate nodes). Also fans out one render
        node per produced clip (claimed via outputs.render_status, D2).
        """
        ctx = run.context or {}
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
        understanding, storyboard = await _load_director_outputs(db, node)

        # Render source selection (docs/VIDEO_EDITOR.md §4). The DAG edge wins
        # first: an upstream align_stills node hands its timeline-materialized
        # transcript asset directly (spec.aligned_asset_id); only without that
        # edge do we scan the project's assets.
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
            render_source, render_kind = aligned_source, "stills"
        elif source_video is not None:
            render_source, render_kind = source_video, "video"
        elif source_audio is not None:
            render_source, render_kind = source_audio, "stills"
        elif first_visual is not None and still_images:
            render_source, render_kind = first_visual, "stills"
        else:
            render_source, render_kind = None, "video"

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
        aspect = str(cfg.get("aspect", "9:16"))
        cap_pos = cfg.get("captionPosition")
        cap_style_raw = cfg.get("captionStylePreset")
        cap_style = cap_style_raw if isinstance(cap_style_raw, str) else "clean-bottom"
        ttl_pos = cfg.get("titlePosition")
        ttl_size_raw = cfg.get("titleSize")
        ttl_size = int(ttl_size_raw) if isinstance(ttl_size_raw, (int, float)) else None
        ttl_enabled_raw = cfg.get("titleEnabled")
        ttl_enabled = True if ttl_enabled_raw is None else bool(ttl_enabled_raw)

        output_ids: list[UUID] = []
        for plan in plans.clips[:clip_count]:
            segment = plan.to_segment()
            music = await music_from_plan(db, plan, brand_cfg)
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
                    brand=brand,
                    music=music,
                    brand_ref=brand_ref,
                )
                if render_source is not None
                else None
            )
            output = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="clip",
                language=target_language,
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
                render_spec=spec.model_dump(mode="json") if spec else None,
                render_status=RenderStatus.PENDING if spec else None,
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
        max_seq = int(node.seq)
        for idx, output_id in enumerate(output_ids, start=1):
            db.add(
                WorkflowStep(
                    run_id=run.id,
                    kind="render",
                    status="pending",
                    seq=max_seq + idx,
                    inputs=[str(node.id)],
                    spec={"output_id": str(output_id)},
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
