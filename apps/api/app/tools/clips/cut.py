"""cut_segments — the compiler-facing deterministic clip producer (ADR-089 §2,
Agent Working Loop iter-2 ①, N-56).

The Execution World's "known span → first clip" seat: a Content Plan's clip
output compiles here — the spans were found and verdict-ed in the
Exploration World (the door validated them verbatim against the asset's word
timeline), the compiler only dereferences pointers into numbers. This node
NEVER discovers: no focus, no count, no ranking, no LLM. Language versions /
caption forms / dubbing are transform semantics with their own capabilities
(translate_clip / dub_clip chained downstream by the compiler) — never birth
params.

Implementation template = materialize_source's zero-LLM configuration
(ADR-043) generalized from the full span to N named spans — the shared
machinery (resolve_render_source / locate_span inside build_clip_spec /
render fan-out) is the same one select_clips' deterministic half rides.
Divergences from select_clips, all deliberate:

- no clip_writer / beat planner / music picker agents (deterministic);
- no project-wide purge of prior clips — a project accumulates clips across
  confirmed plans (multi-journey world); one chain births once;
- no score / publishing copy on the outputs (execution never judges — the
  judgment lives on the exploration Select's verdict);
- titles off, captions on in the source language (no LLM copy exists);
- prelude-free (needs_plan_prelude=False): understanding/planning already
  happened in the exploration chat — the paid world gets no second
  discovery seat. The word timeline is guaranteed upstream (exploration
  door) and the run's claim gate holds until asset processing drains.
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
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.clip_spec import build_clip_spec
from app.pipeline.graph import MEDIA, TRANSCRIPT, NodeBase, estimate_free
from app.pipeline.morph import fan_out_renders
from app.pipeline.step_context import list_assets
from app.pipeline.step_display import fill_summary, ui_lang_of
from app.platform.project_context import resolve_run_persona
from app.tools.clips.node import resolve_render_source
from app.tools.clips.params import CutSegmentSpan

logger = structlog.get_logger()


class CutSegments(NodeBase):
    kind = "cut_segments"
    node_type = "video"  # 词表 v3 (ADR-076) — 装配站 (区间裁剪)
    prototype = "editor"  # 参数程序 (区间/画幅杠杆行; 程序区无散文)
    task_name = "Cut segments"
    task_name_zh = "裁出片段"
    output_type = "clips"
    slot_label = "Segments"
    slot_label_zh = "片段"
    requires = (MEDIA, TRANSCRIPT)
    produces_outputs = True
    retries = 1
    # No count_default / count_limits — the span list IS the count; its
    # 1..5 bound lives in CutSegmentsParams (validate_task_list's count
    # channel reads a ``count`` field this params model deliberately lacks).

    def estimate(self, ctx: dict) -> dict | None:
        """Mechanical spec assembly — free (no LLM, no priced units;
        materialize precedent). The per-clip render fan-out is born mid-run
        — unquoted (P4 NULL), even though the spans make durations knowable
        at compile time; monetizing render_seconds is the decision-package
        quote topic (iter-2 ③), not this batch."""
        return estimate_free()

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        ctx = run.context or {}
        spec_in = dict(node.spec or {})
        spans = [
            CutSegmentSpan.model_validate(s) for s in (spec_in.get("segments") or [])
        ]
        if not spans:
            raise ValueError("cut_segments: spec carries no segments")

        assets = await list_assets(db, project.id)
        # Source resolution = the shared decision (ADR-043): the spec's
        # asset_id is the compiler-resolved pin (the Select's unique source
        # made explicit); run.context pins stay honored for chain shapes
        # that carry them.
        source_pin = str(spec_in.get("asset_id") or "") or ctx.get("source_asset_id")
        exemplar_pin = ctx.get("exemplar_asset_id")
        render_source, render_kind, still_images = await resolve_render_source(
            db,
            node,
            assets,
            source_asset_id=source_pin,
            exclude_asset_id=(
                exemplar_pin if exemplar_pin != source_pin else None
            ),
        )
        if render_source is None:
            raise ValueError("cut_segments: no renderable source asset")

        persona = await resolve_run_persona(db, run, project)
        brand_cfg, _brand_music_id = await resolve_brand_block(db, persona)
        brand = brand_from_block(brand_cfg)
        brand_ref = persona.id if persona is not None else None

        # The clip's language IS the source's spoken language (no LLM copy
        # to translate at birth; language versions are downstream morphs the
        # compiler chains). Asset truth first, then the run's pin.
        target_language = str(
            (render_source.meta or {}).get("language")
            or ctx.get("target_language")
            or "en"
        )
        # Aspect: the compiled spec wins, then the run context carry-over,
        # then the skin default (select_clips' order minus the exemplar
        # skeleton — exploration chains pin no exemplar).
        cfg = brand_cfg
        aspect = str(
            spec_in.get("aspect") or ctx.get("aspect") or cfg.get("aspect", "9:16")
        )
        cap_pos = cfg.get("captionPosition")
        cap_style_raw = cfg.get("captionStylePreset")
        cap_style = cap_style_raw if isinstance(cap_style_raw, str) else "clean-bottom"
        ttl_pos = cfg.get("titlePosition")
        ttl_size_raw = cfg.get("titleSize")
        ttl_size = int(ttl_size_raw) if isinstance(ttl_size_raw, (int, float)) else None

        # No exemplar on exploration chains → music follows the skin default
        # (materialize's second half; music_from_exemplar's input is always
        # None here by construction).
        music = await music_from_block(db, brand_cfg)

        # Render ownership (2026-08-15 morph/render race) is the helper's
        # law, one seat: birth PENDING, fan out, and a later NON-FORK morph
        # in this run flips the rows back to NULL and owns their render
        # (select_clips / materialize_source spell the same dance inline).
        output_ids: list[UUID] = []
        for i, span in enumerate(spans, start=1):
            segment = Segment(
                id=f"seg-{i}",
                source_text="",
                start_marker="",
                end_marker="",
                start_seconds=span.start,
                end_seconds=span.end,
                duration_seconds=max(5, int(round(span.end - span.start))),
            )
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
                raise ValueError("cut_segments: source is not renderable")
            output = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="clip",
                language=target_language,
                # birth: no generated track rides yet (ADR-026)
                provenance="real",
                payload=ClipPayload(
                    hook="",
                    title_options=[],
                    duration=int(round(span.end - span.start)),
                ).model_dump(mode="json"),
                source_ref={
                    "segment": segment.model_dump(mode="json"),
                    "start_seconds": span.start,
                    "end_seconds": span.end,
                    "asset_id": str(render_source.id),
                },
                render_spec=spec.model_dump(mode="json"),
                render_status=RenderStatus.PENDING,
            )
            db.add(output)
            await db.flush()
            output_ids.append(output.id)

        await fan_out_renders(db, run, node, output_ids)

        await fill_summary(
            node.id,
            self.kind,
            ui_language=ui_lang_of(run, project),
            n=len(output_ids),
            total_seconds=sum(int(round(s.end - s.start)) for s in spans),
        )
        return output_ids
