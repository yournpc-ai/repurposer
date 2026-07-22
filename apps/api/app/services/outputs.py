"""Unified outputs read surface (ADR-030).

``visible_outputs_stmt`` is THE filter every user-facing read path must use —
results, library, export, and future MCP/gallery surfaces. Internal node
artifacts (``INTERNAL_OUTPUT_TYPES``, e.g. the director's content_plan) are
node bookkeeping, never user products, and must not leak into any listing.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.schemas import (
    INTERNAL_OUTPUT_TYPES,
    PlanNodeResponse,
    WorkflowRunResponse,
)
from app.models.tables import Output, PlanNode, WorkflowRun


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


def plan_node_to_response(node: PlanNode) -> PlanNodeResponse:
    """Serialize a node; ``stage`` is the display hint from spec (ui_step keys)."""
    return PlanNodeResponse(
        id=node.id,
        kind=node.kind,
        status=node.status,
        seq=node.seq,
        error=node.error,
        cost=node.cost,
        stage=(node.spec or {}).get("stage"),
        started_at=node.started_at,
        finished_at=node.finished_at,
    )


def aggregate_node_cost(nodes: list[PlanNode]) -> dict | None:
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


async def run_to_response(
    db: AsyncSession,
    run: WorkflowRun,
    *,
    with_nodes: bool = True,
) -> WorkflowRunResponse:
    """Serialize a run with its plan nodes and aggregated cost."""
    resp = WorkflowRunResponse.model_validate(run)
    if with_nodes:
        result = await db.execute(
            select(PlanNode).where(PlanNode.run_id == run.id).order_by(PlanNode.seq)
        )
        nodes = list(result.scalars().all())
        resp.nodes = [plan_node_to_response(n) for n in nodes]
        resp.cost = aggregate_node_cost(nodes)
    return resp
