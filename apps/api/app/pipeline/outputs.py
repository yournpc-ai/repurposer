"""Unified outputs read surface (ADR-030).

``visible_outputs_stmt`` is THE filter every user-facing read path must use —
results, library, export, and future MCP/gallery surfaces. Internal node
artifacts (``INTERNAL_OUTPUT_TYPES``, e.g. the director's material_understanding
/ storyboard) are node bookkeeping, never user products, and must not leak
into any listing.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.schemas import (
    INTERNAL_OUTPUT_TYPES,
    StepResponse,
    RunResponse,
)
from app.models.tables import Output, WorkflowStep, WorkflowRun
from app.pipeline.graph import fold_estimates, node_for


def visible_outputs_stmt() -> Select:
    """Base SELECT over user-facing outputs only (internal types excluded)."""
    return select(Output).where(Output.type.notin_(INTERNAL_OUTPUT_TYPES))


async def list_visible_outputs(
    db: AsyncSession,
    project_id: UUID,
    *,
    output_type: str | None = None,
) -> list[Output]:
    """List a project's user-facing outputs, newest first."""
    stmt = visible_outputs_stmt().where(Output.project_id == project_id)
    if output_type is not None:
        stmt = stmt.where(Output.type == output_type)
    result = await db.execute(stmt.order_by(Output.created_at.desc()))
    return list(result.scalars().all())


def workflow_step_to_response(node: WorkflowStep) -> StepResponse:
    """Serialize a node; ``stage`` is the display hint from spec (results.stepper.* keys)."""
    node_cls = node_for(node.kind)
    return StepResponse(
        id=node.id,
        kind=node.kind,
        status=node.status,
        seq=node.seq,
        error=node.error,
        cost=node.cost,
        stage=(node.spec or {}).get("stage"),
        summary=(node.spec or {}).get("summary"),
        # 渲染单元 (D6 修订) comes from the node CLASS (self-description,
        # like label()), never the row — legacy/unknown kinds fold into the
        # spine by default.
        canvas_key=node_cls.canvas_group(node) if node_cls else None,
        canvas_hidden=node_cls.canvas_hidden if node_cls else False,
        canvas_text=(node_cls.canvas_text(node) if node_cls else None),
        output_refs=[UUID(str(ref)) for ref in (node.output_refs or [])],
        inputs=[UUID(str(upstream)) for upstream in (node.inputs or [])],
        started_at=node.started_at,
        finished_at=node.finished_at,
    )


def aggregate_step_cost(nodes: list[WorkflowStep]) -> dict | None:
    """Run-level cost = sum over node cost ledgers (ADR-025)."""
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
    """Run-level quotation = fold over node estimates (P4, N-34 — the read
    side of 报价=图 fold; the write side is create_run's per-node estimate).
    None when every node is unquoted (NULL estimates)."""
    quoted = [node.estimate for node in nodes if node.estimate]
    if not quoted:
        return None
    return fold_estimates(quoted)


def step_estimate_deviation(node: WorkflowStep) -> dict | None:
    """actual (cost ledger) vs estimate (quotation), per token field — the
    calibration regression's read shape (AGENT_ARCH §8):

        {prompt_tokens:     {actual, low, high, delta},
         completion_tokens: {actual, low, high, delta},
         units?:            {<unit>: {expected, actual, delta}}}

    delta = actual − clamp(actual, low, high): 0 = in range, positive = the
    quote undershot, negative = it overshot. None when either side is
    missing (a node without an estimate or without metered usage yet). The
    SQL twin for the fleet-wide regression:

        SELECT kind,
               count(*) FILTER (WHERE (cost->>'prompt_tokens')::int
                  BETWEEN (estimate->'prompt_tokens'->>0)::int
                      AND (estimate->'prompt_tokens'->>1)::int) AS prompt_in_range,
               count(*) AS n
        FROM workflow_steps
        WHERE estimate IS NOT NULL AND cost IS NOT NULL
        GROUP BY kind;
    """
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
    # Mechanical units (media metering, record_media_usage): estimate carries
    # exact quantities, cost carries actuals — delta is signed drift.
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


def aggregate_run_summary(nodes: list[WorkflowStep]) -> str | None:
    """Run-level rollup of step summaries, derived at read time (no column).

    "Wrote a LinkedIn post · 739 words" — the recap tells what the user GOT,
    so only **tool** summaries join (registry members; internal-crew lines —
    understand / plan / render bookkeeping — stay on their own step rows),
    plus any bailed waiting-seat node's user-abort note (deliberate, see
    ``bail_waiting_interrupt`` — direction interrupt, 期 4 hook gate, …).
    Joined in seq order (CHAT_ARCH §8)."""
    from app.tools import TOOL_REGISTRY  # deferred: import cycle

    parts = [
        summary
        for node in sorted(nodes, key=lambda n: n.seq)
        if node.status == "done"
        and (summary := (node.spec or {}).get("summary"))
        and (
            node.kind in TOOL_REGISTRY
            or (node.spec or {}).get("bailed")
        )
    ]
    return " · ".join(parts) if parts else None


async def run_to_response(
    db: AsyncSession,
    run: WorkflowRun,
    *,
    with_steps: bool = True,
) -> RunResponse:
    """Serialize a run with its workflow steps and aggregated cost."""
    resp = RunResponse.model_validate(run)
    if with_steps:
        result = await db.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.seq)
        )
        nodes = list(result.scalars().all())
        resp.steps = [workflow_step_to_response(n) for n in nodes]
        resp.cost = aggregate_step_cost(nodes)
    return resp
