"""Modifier-step machinery (ADR-039 P1 split): the shared body of the morph
tools (remove_filler / add_music / translate_clip / dub_clip) — resolve the
clips a modifier acts on, journal the spec write, fan out one render step per
touched output.
"""

from uuid import UUID

from sqlalchemy import cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Message, Output, WorkflowStep
from app.models.tables import Project, WorkflowRun

# Morph kinds that rewrite a clip's render_spec IN PLACE and re-render (the
# fork variants derive new rows and leave the base clip alone — they never
# suppress anything).
INPLACE_MORPH_KINDS = (
    "translate_clip",
    "dub_clip",
    "remove_filler",
    "add_music",
    "reframe_clip",
)

# Clip producers (their fan-out a later in-place morph suppresses).
_PRODUCER_KINDS = ("select_clips", "materialize_source")


async def _render_step_label(db: AsyncSession, run: WorkflowRun) -> str | None:
    """The runtime-born render step's builder-written task name (same label()
    source as compile-time nodes), localized to the run's pinned UI locale."""
    from app.pipeline.graph import NODE_KINDS  # deferred: import cycle
    from app.pipeline.step_display import ui_lang_of

    project = await db.get(Project, run.project_id)
    render_cls = NODE_KINDS.get("render")
    if project is None or render_cls is None:
        return None
    return render_cls.label(None, ui_lang_of(run, project))


async def _later_inplace_morph_exists(db: AsyncSession, run: WorkflowRun, node: WorkflowStep) -> bool:
    """True when a NON-FORK morph sibling sits LATER in this run's graph.

    That morph will rewrite the same outputs' render_spec in place and own
    their render — rendering now is dead work (a full render thrown away when
    the morph lands) AND a last-writer-wins race on the output row (the stale
    render's completion can clobber the morph's re-pend). Producers and
    earlier morphs use this to leave the render to the last morph in the
    chain; ``fork`` siblings don't count (they derive new rows and never
    touch the base clip). A ``target_output_id``-scoped morph doesn't count
    either: it rewrites one PRE-EXISTING output — its scope never covers
    this run's newborn clips, so it must not suppress their base renders.
    """
    count = await db.scalar(
        select(func.count())
        .select_from(WorkflowStep)
        .where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.kind.in_(INPLACE_MORPH_KINDS),
            WorkflowStep.seq > node.seq,
            func.coalesce(WorkflowStep.spec["fork"].astext, "false") != "true",
            func.coalesce(WorkflowStep.spec["target_output_id"].astext, "") == "",
        )
    )
    return bool(count)


async def _has_producer_upstream(db: AsyncSession, node: WorkflowStep) -> bool:
    """True when a clip producer feeds this modifier. The compiler wires the
    producer edge into EVERY modifier of the run, so a later morph's target
    set always unions the producer's full output_refs — this morph's skipped
    clips stay visible downstream (a rescue may safely defer to the later
    morph). Without a producer edge the later morph sees only this step's
    own output_refs (the touched set)."""
    if not node.inputs:
        return False
    count = await db.scalar(
        select(func.count())
        .select_from(WorkflowStep)
        .where(
            WorkflowStep.id.in_([UUID(str(i)) for i in node.inputs]),
            WorkflowStep.kind.in_(_PRODUCER_KINDS),
        )
    )
    return bool(count)


async def _target_clips(
    db: AsyncSession, node: WorkflowStep, project: Project
) -> list[Output]:
    """Clips a modifier step acts on: the upstream steps' output_refs (same
    run — e.g. a clips_pipeline or a previous modifier in the chain), else the
    project's existing renderable clips."""
    clip_ids: list[UUID] = []
    if node.inputs:
        upstream = list(
            (
                await db.execute(
                    select(WorkflowStep).where(
                        WorkflowStep.id.in_([UUID(str(i)) for i in node.inputs])
                    )
                )
            )
            .scalars()
            .all()
        )
        for step in upstream:
            # A FORK upstream's output_refs are NEW derived rows — its source
            # clips stay untouched and arrive via the chain's base edge
            # (select_clips / materialize_source, which is also in inputs).
            # The modifier→modifier edge exists for ORDERING only; collecting
            # the fork's rows would re-transform the derivative (an all-fork
            # translate→translate→dub chain would combinatorially fan out
            # instead of producing one version per named language).
            if (step.spec or {}).get("fork"):
                continue
            clip_ids.extend(UUID(str(ref)) for ref in (step.output_refs or []))
    if clip_ids:
        clips = list(
            (
                await db.execute(
                    select(Output).where(Output.id.in_(clip_ids), Output.type == "clip")
                )
            )
            .scalars()
            .all()
        )
    else:
        # "Existing" = PRE-RUN rows only: when every input edge is a skipped
        # fork (an all-fork chain on the existing profile, e.g. two subtitle
        # versions of clips from an earlier run), the first fork's derived
        # rows already sit in the project — an unfiltered project-wide
        # fallback would re-transform them and fan out combinatorially.
        this_run_steps = select(WorkflowStep.id).where(
            WorkflowStep.run_id == node.run_id
        )
        clips = list(
            (
                await db.execute(
                    select(Output).where(
                        Output.project_id == project.id,
                        Output.type == "clip",
                        Output.render_spec.isnot(None),
                        or_(
                            Output.workflow_step_id.is_(None),
                            Output.workflow_step_id.not_in(this_run_steps),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
    return [c for c in clips if c.render_spec]


async def _modifier_target_clips(
    db: AsyncSession, node: WorkflowStep, project: Project
) -> list[Output]:
    """Target resolution for modifier steps: an explicit
    ``spec.target_output_id`` (asset-scoped chat) wins; otherwise fall back to
    the upstream/project clips (``_target_clips``)."""
    target_id = (node.spec or {}).get("target_output_id")
    if target_id:
        clips = list(
            (
                await db.execute(
                    select(Output).where(
                        Output.id == UUID(str(target_id)),
                        Output.project_id == project.id,
                        Output.type == "clip",
                    )
                )
            )
            .scalars()
            .all()
        )
        return [c for c in clips if c.render_spec]
    return await _target_clips(db, node, project)


async def _run_origin(db: AsyncSession, run: WorkflowRun) -> str:
    """Operations-journal source for run-dispatched morphs (agent-loop-upgrade
    W4, ADR-033 shell parity): ``"chat"`` when the run was dispatched from a
    chat message (``messages.workflow_run_id`` backlink), else ``"system"``."""
    linked = await db.scalar(
        select(func.count()).select_from(Message).where(
            Message.workflow_run_id == run.id
        )
    )
    return "chat" if linked else "system"


async def _guard_target_differs_from_source(
    db: AsyncSession,
    clips: list[Output],
    lang: str,
    *,
    zh: bool,
) -> None:
    """Same-language guard (2026-08-17 走查实修): a translate/dub whose target
    IS the source's language produces a same-language "translation" — the
    中英双语 farce where the bilingual pair came out 繁体+简体 with no English
    anywhere (the PlanAgent had defaulted target_language to the prompt's own
    language). Fail loud and name the fix — a silent same-language rewrite is
    the banned posture. Source-language truth: the asset's ASR-detected
    ``meta.language``, then the caption cues' lang. Raises plain ``ValueError``
    — errors.py passes an exact ValueError's authored message through to the
    step's user-facing line.
    """
    from app.models.tables import Asset  # local: tables already imported piecemeal

    for output in clips:
        src_lang: str | None = None
        asset_id = (output.source_ref or {}).get("asset_id")
        if asset_id:
            asset = await db.get(Asset, UUID(str(asset_id)))
            if asset is not None:
                raw = (asset.meta or {}).get("language")
                src_lang = str(raw) if raw else None
        if not src_lang:
            track0 = (output.render_spec or {}).get("caption_track") or []
            if track0 and track0[0].get("lang"):
                src_lang = str(track0[0]["lang"])
        if src_lang and src_lang.lower() == str(lang).lower():
            raise ValueError(
                f"源素材已经是{src_lang}——目标语言必须换一种（中英双语的目标应为 en）。"
                if zh
                else f"The source is already {src_lang} — the target must be a different language (for Chinese-English bilingual, target en)."
            )


async def _fan_out_renders(
    db: AsyncSession,
    run: WorkflowRun,
    node: WorkflowStep,
    output_ids: list[UUID],
    *,
    defer_to_later_morph: bool = True,
) -> None:
    """One render step per touched output (same shape as the clips fan-out):
    claimed via outputs.render_status, terminal state mirrored back.

    Two orderings are enforced here (2026-08-15 morph/render race):
    - Supersede: still-pending sibling render steps for these outputs are
      deleted — this morph's spec rewrite obsoletes them. (A step already
      running can't be unclaimed; the render completion guard discards its
      stale product instead — see rendering.render_output.)
    - Defer (``defer_to_later_morph``): when a LATER non-fork morph exists in
      this run, it will rewrite the spec again and owns the render — the
      touched outputs go back to render_status NULL (render not requested)
      and no steps are added. Fork fan-outs pass False: a fork's derived
      rows are exclusively its own (later morphs act on the base clips,
      never on them)."""
    await db.execute(
        delete(WorkflowStep).where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.kind == "render",
            WorkflowStep.status == "pending",
            WorkflowStep.spec["output_id"].astext.in_([str(oid) for oid in output_ids]),
        )
    )
    if defer_to_later_morph and await _later_inplace_morph_exists(db, run, node):
        await db.execute(
            update(Output)
            .where(Output.id.in_(output_ids))
            .values(render_status=None)
        )
        await db.flush()
        return
    max_seq = int(
        (
            await db.execute(
                select(func.max(WorkflowStep.seq)).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        or node.seq
    )
    label = await _render_step_label(db, run)
    for idx, output_id in enumerate(output_ids, start=1):
        db.add(
            WorkflowStep(
                run_id=run.id,
                kind="render",
                status="pending",
                seq=max_seq + idx,
                inputs=[str(node.id)],
                spec={"output_id": str(output_id), **({"summary": label} if label else {})},
            )
        )
    await db.flush()


async def _pend_suppressed_base_renders(
    db: AsyncSession,
    run: WorkflowRun,
    node: WorkflowStep,
    outputs: list[Output],
    *,
    exclude: set[UUID] | None = None,
    defer_to_later_morph: bool = True,
) -> None:
    """Morph skip-rescue: targets the morph did NOT touch keep their base
    spec, so when the producer's render fan-out was suppressed for this run
    (render_status NULL = render not requested) the morph owes them the
    render they would otherwise never get. Goes through _fan_out_renders so
    a later in-place morph defers the same way — but only when that morph
    can actually SEE the rescued clips. Callers pass
    ``defer_to_later_morph = (not touched) or await _has_producer_upstream(...)``:
    a producer edge means every later morph unions the producer's full
    output_refs (skips stay visible); an all-skipped morph leaves empty
    output_refs, so the later morph's project-wide fallback sees them. A
    partial touch with no producer edge must NOT defer — the later morph's
    targets come from this step's output_refs (the touched set), so the
    skipped clips are invisible to it and would never render.
    """
    stale_ids = [
        o.id
        for o in outputs
        if o.render_spec
        and o.render_status is None
        and (exclude is None or o.id not in exclude)
    ]
    if not stale_ids:
        return
    await db.execute(
        update(Output)
        .where(Output.id.in_(stale_ids))
        .values(render_status=RenderStatus.PENDING)
    )
    await db.flush()
    await _fan_out_renders(
        db, run, node, stale_ids, defer_to_later_morph=defer_to_later_morph
    )


async def _record_target_output_ids(node_id: UUID, output_ids: list[UUID]) -> None:
    """Record the cross-run DAG edge (which outputs this step consumed) on the
    step's spec — jsonb_set in its own session, same discipline as _set_stage."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec,
                    pg_array(["target_output_ids"]),
                    cast([str(oid) for oid in output_ids], JSONB),
                    True,
                )
            )
        )
        await s.commit()
