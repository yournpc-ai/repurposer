"""materialize_source — the whole-source materialization node (ADR-043).

An internal node (CHAT_ARCH §4.3: topology, never a registered skill — users
never say "materialize"; the whole source is the transform's implied object).
When a chain holds clip-spec consumers (translate / dub / music / filler) but
no select_clips, compile injects this node to materialize the project's
primary source as ONE full-span clip-spec — "给我的视频加字幕" never routes
through highlight extraction. Deterministic: no LLM, no selection, no angle.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.brand import (
    brand_from_block,
    music_from_block,
    resolve_brand_block,
)
from app.models.schemas import (
    ClipPayload,
    RenderStatus,
    Segment,
)
from app.models.tables import (
    Output,
    WorkflowStep,
    Project,
    WorkflowRun,
)
from app.pipeline.clip_spec import build_clip_spec
from app.pipeline.graph import NodeBase, estimate_free
from app.pipeline.morph import _later_inplace_morph_exists, _render_step_label
from app.pipeline.step_context import _list_assets
from app.pipeline.step_display import _set_summary, ui_lang_of
from app.platform.project_context import resolve_run_persona
from app.skills.clips.node import resolve_render_source

logger = structlog.get_logger()


class MaterializeSource(NodeBase):
    kind = "materialize_source"
    task_name = "Prepare full video"
    task_name_zh = "准备整条视频"
    # The derived type word "video" (整条视频) is display vocabulary only —
    # the node is compile-injected, never requested, so it declares no
    # output_type (the requestable-type registry stays untouched, N-32).
    internal = True
    produces_outputs = True
    retries = 1

    def estimate(self, ctx: dict) -> dict | None:
        """Mechanical spec assembly — free. The render fan-out is born
        mid-run (unquoted, same as select_clips' renders)."""
        return estimate_free()

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Materialize the primary source as one full-span clip output.

        The span is [0, source duration) — captions come from the full ASR
        word track (or the aligned/estimated timeline for stills), the skin
        follows the resolved persona, the title overlay stays off (no hook:
        nothing is excerpted). Fork semantics downstream (translate / dub)
        treat the row like any clip.
        """
        ctx = run.context or {}
        assets = await _list_assets(db, project.id)
        render_source, render_kind, still_images = await resolve_render_source(
            db, node, assets
        )
        if render_source is None:
            raise ValueError("materialize_source: no renderable source asset")

        persona = await resolve_run_persona(db, run, project)
        brand_cfg, _brand_music_id = await resolve_brand_block(db, persona)
        brand = brand_from_block(brand_cfg)
        brand_ref = persona.id if persona is not None else None
        # Whole-source aspect (2026-08-17 拍板: 链无 clip 技能 = 比例跟源):
        # explicit intent (spec / run.context) wins; otherwise "original" —
        # the renderer resolves the source's own dimensions at render time.
        # The persona skin's aspect is a SHORTS craft default and never
        # applies to a whole-video materialization (a landscape talk must
        # not come out cropped to 9:16).
        aspect = str(
            (node.spec or {}).get("aspect")
            or ctx.get("aspect")
            or "original"
        )
        cfg = brand_cfg
        cap_pos = cfg.get("captionPosition")
        cap_style_raw = cfg.get("captionStylePreset")
        cap_style = cap_style_raw if isinstance(cap_style_raw, str) else "clean-bottom"
        ttl_pos = cfg.get("titlePosition")
        ttl_size_raw = cfg.get("titleSize")
        ttl_size = int(ttl_size_raw) if isinstance(ttl_size_raw, (int, float)) else None

        words = (render_source.meta or {}).get("words") or []
        duration = render_source.duration_seconds or (
            float(words[-1]["end"]) if words else None
        )
        if duration is None:
            raise ValueError("materialize_source: source has no duration or words")

        target_language = str(ctx.get("target_language") or "en")
        segment = Segment(
            id="full",
            source_text="",
            start_marker="",
            end_marker="",
            start_seconds=0.0,
            end_seconds=float(duration),
            duration_seconds=max(5, int(duration)),
        )
        music = await music_from_block(db, brand_cfg)
        spec = build_clip_spec(
            render_source,
            segment,
            target_language,
            kind=render_kind,
            aspect=aspect,
            caption_position=cap_pos,
            caption_enabled=True,
            caption_style_preset=cap_style,
            title_size=ttl_size,
            title_position=ttl_pos,
            title_enabled=False,
            image_urls=still_images if render_kind == "stills" else None,
            brand=brand,
            music=music,
            brand_ref=brand_ref,
        )
        if spec is None:
            raise ValueError("materialize_source: source is not renderable")

        # Render ownership (2026-08-15 morph/render race): when a NON-FORK
        # morph sits later in this run, it rewrites this output's spec in
        # place and owns the render — the base render would be dead work and
        # a last-writer-wins race on the row. Leave render_status NULL
        # (render not requested); the morph pends + fans out (a morph that
        # skips the clip rescues it via _pend_suppressed_base_renders).
        suppressed = await _later_inplace_morph_exists(db, run, node)
        spec_dict = spec.model_dump(mode="json")
        output = Output(
            project_id=project.id,
            workflow_step_id=node.id,
            type="clip",
            language=target_language,
            # birth: no generated track rides yet (ADR-026)
            provenance="real",
            payload=ClipPayload(
                hook="",
                title_options=[project.title] if project.title else [],
                # No LLM mood pick here (no selection happened) — the schema
                # default ("calm") rides, same as every reader's fallback.
                duration=float(duration),
            ).model_dump(mode="json"),
            source_ref={
                "segment": segment.model_dump(mode="json"),
                "start_seconds": 0.0,
                "end_seconds": float(duration),
                "asset_id": str(render_source.id),
            },
            render_spec=spec_dict,
            render_status=None if suppressed else RenderStatus.PENDING,
        )
        db.add(output)
        await db.flush()

        if not suppressed:
            # Render fan-out (D2, select_clips 同款): the render worker claims
            # the output row (render_status=PENDING) and mirrors terminal
            # state back. The summary preset is the builder-written task name
            # (the task list's pending-row text).
            label = await _render_step_label(db, run)
            db.add(
                WorkflowStep(
                    run_id=run.id,
                    kind="render",
                    status="pending",
                    seq=int(node.seq) + 1,
                    inputs=[str(node.id)],
                    spec={
                        "output_id": str(output.id),
                        **({"summary": label} if label else {}),
                    },
                )
            )
            await db.flush()

        zh = ui_lang_of(run, project).startswith("zh")
        await _set_summary(
            node.id,
            f"整条视频就位 · {int(duration)} 秒" if zh else f"Full video ready · {int(duration)}s",
        )
        return [output.id]
