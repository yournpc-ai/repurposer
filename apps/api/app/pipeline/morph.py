"""Modifier-step machinery (ADR-039 P1 split): the shared body of the morph
skills (remove_filler / add_music / translate_clip / dub_clip) — resolve the
clips a modifier acts on, journal the spec write, fan out one render step per
touched output.
"""

from uuid import UUID

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.tables import Message, Output, WorkflowStep
from app.models.tables import Project, WorkflowRun


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
        clips = list(
            (
                await db.execute(
                    select(Output).where(
                        Output.project_id == project.id,
                        Output.type == "clip",
                        Output.render_spec.isnot(None),
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


async def _fan_out_renders(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, output_ids: list[UUID]
) -> None:
    """One render step per touched output (same shape as the clips fan-out):
    claimed via outputs.render_status, terminal state mirrored back."""
    max_seq = int(
        (
            await db.execute(
                select(func.max(WorkflowStep.seq)).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        or node.seq
    )
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
