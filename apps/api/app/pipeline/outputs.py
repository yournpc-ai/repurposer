"""Owned video reads and shared delivery semantics.

Output rows remain internal media, execution and recovery facts. Chat delivery
messages own their exact video references; these helpers never create a gallery.
"""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.schemas import OutputResponse, ProductionStage, RunResponse, StepResponse
from app.models.tables import CompositionVersion, Output, Publication, WorkflowRun, WorkflowStep
from app.pipeline.graph import fold_estimates
from app.platform.billing import cost_usd, credits_at_ratio, estimate_usd_range
from app.platform.configs import get_config


def visible_outputs_stmt() -> Select:
    return select(Output).where(
        Output.type == "video",
        Output.archived_at.is_(None),
    )


def chat_delivery_output_ids(messages: list) -> list[UUID]:
    """Flatten only the exact refs persisted on each delivery message."""
    ordered: list[UUID] = []
    seen: set[UUID] = set()
    for message in messages:
        intent = message.intent or {}
        run_delivery = (
            message.workflow_run_id is not None
            and intent.get("type") == "trigger_review"
            and intent.get("trigger") in {"run_completed", "run_failed"}
        )
        upload_answer = intent.get("type") != "trigger_review"
        if (
            getattr(message, "role", "assistant") != "assistant"
            or not (run_delivery or upload_answer)
            or not isinstance(intent.get("output_refs"), list)
        ):
            continue
        for raw_ref in intent["output_refs"]:
            try:
                output_id = UUID(str(raw_ref))
            except (TypeError, ValueError):
                continue
            if output_id not in seen:
                seen.add(output_id)
                ordered.append(output_id)
    return ordered


def delivered_output_refs(steps: list, outputs: list) -> list[str]:
    """Snapshot actually deliverable refs in persisted step order."""
    by_id = {str(output.id): output for output in outputs}
    refs: list[str] = []
    seen: set[str] = set()
    for step in sorted(steps, key=lambda item: item.seq):
        for raw_ref in step.output_refs or []:
            ref = str(raw_ref)
            output = by_id.get(ref)
            if ref not in seen and output is not None and is_delivered_output(output):
                seen.add(ref)
                refs.append(ref)
    return refs


def is_delivered_output(output: Output) -> bool:
    render_status = getattr(output.render_status, "value", output.render_status)
    return (
        output.type == "video"
        and render_status == "completed"
        and bool((output.files or {}).get("video"))
    )


def is_chat_video_output(output: Output) -> bool:
    return is_delivered_output(output)


def output_to_response(
    output: Output,
    *,
    composition_version_number: int | None = None,
) -> OutputResponse:
    return OutputResponse.model_validate(output).model_copy(
        update={"composition_version_number": composition_version_number}
    )


async def composition_version_number(db: AsyncSession, output: Output) -> int | None:
    if output.composition_version_id is None:
        return None
    version = await db.get(CompositionVersion, output.composition_version_id)
    return version.version if version is not None else None


async def list_visible_outputs(db: AsyncSession, project_id: UUID) -> list[Output]:
    result = await db.execute(
        visible_outputs_stmt()
        .where(Output.project_id == project_id)
        .order_by(Output.created_at.desc())
    )
    return list(result.scalars().all())


def workflow_step_to_response(node: WorkflowStep, *, ratio: int) -> StepResponse:
    estimate_credits: list[int] | None = None
    if node.estimate:
        usd_low, usd_high = estimate_usd_range(node.estimate)
        estimate_credits = [
            credits_at_ratio(usd_low, ratio),
            credits_at_ratio(usd_high, ratio),
        ]
    production_stages = []
    raw_stages = (node.spec or {}).get("production_stages")
    if isinstance(raw_stages, list):
        for raw in raw_stages:
            try:
                production_stages.append(ProductionStage.model_validate(raw))
            except (ValidationError, TypeError):
                continue
    return StepResponse(
        id=node.id,
        kind=node.kind,
        status=node.status,
        seq=node.seq,
        attempt=node.attempt,
        error=node.error,
        cost=node.cost,
        stage=(node.spec or {}).get("stage"),
        summary=(node.spec or {}).get("summary"),
        noop=(node.spec or {}).get("noop") or None,
        output_refs=[UUID(str(ref)) for ref in (node.output_refs or [])],
        inputs=[UUID(str(upstream)) for upstream in (node.inputs or [])],
        estimate_credits=estimate_credits,
        cost_credits=credits_at_ratio(cost_usd(node.cost), ratio) if node.cost else None,
        started_at=node.started_at,
        finished_at=node.finished_at,
        scene_index=(node.spec or {}).get("scene_index"),
        production_stages=production_stages,
    )


def aggregate_step_cost(nodes: list[WorkflowStep]) -> dict | None:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "fixed_cost": 0.0}
    seen = False
    for node in nodes:
        if not node.cost:
            continue
        seen = True
        totals["prompt_tokens"] += int(node.cost.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(node.cost.get("completion_tokens") or 0)
        totals["fixed_cost"] += float(node.cost.get("fixed_cost") or 0.0)
    return totals if seen else None


def aggregate_step_estimate(nodes: list[WorkflowStep]) -> dict | None:
    quoted = [node.estimate for node in nodes if node.estimate]
    if not quoted:
        return None
    return fold_estimates(quoted)


def step_estimate_deviation(node: WorkflowStep) -> dict | None:
    if not node.estimate or not node.cost:
        return None

    def field(name: str) -> dict:
        low, high = (int(v) for v in node.estimate[name])
        actual = int(node.cost.get(name) or 0)
        return {
            "actual": actual,
            "low": low,
            "high": high,
            "delta": actual - min(max(actual, low), high),
        }

    out = {
        "prompt_tokens": field("prompt_tokens"),
        "completion_tokens": field("completion_tokens"),
    }
    est_units = node.estimate.get("units") or {}
    act_units = node.cost.get("units") or {}
    if est_units or act_units:
        out["units"] = {
            key: {
                "expected": float(est_units.get(key) or 0.0),
                "actual": float(act_units.get(key) or 0.0),
                "delta": float(act_units.get(key) or 0.0) - float(est_units.get(key) or 0.0),
            }
            for key in sorted(set(est_units) | set(act_units))
        }
    return out


async def delete_outputs_fk_safe(
    db: AsyncSession, doomed: list[UUID] | Select[tuple[UUID]]
) -> None:
    """Delete dependent Publication rows before their restricted Output rows."""
    if isinstance(doomed, list) and not doomed:
        return
    await db.execute(delete(Publication).where(Publication.output_id.in_(doomed)))
    await db.execute(delete(Output).where(Output.id.in_(doomed)))
