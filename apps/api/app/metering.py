"""Per-node LLM usage metering (ADR-025, RunPlan Phase 1).

The single LLM choke point (``providers/llm/minimax.py``) reports API ``usage`` here;
``record_usage`` accumulates it onto the workflow step currently bound via
``bind_workflow_step``. Binding is a contextvar, so concurrent node executions
(asyncio tasks) each meter their own node, and retries/fallbacks inside one
node accumulate naturally — every attempt is billed.

Media calls (TTS / clone / image / music) report through ``record_media_usage``:
actual units merge into ``cost.units`` and their priced money (the client's
``price_units`` — quantities from nodes, prices from the Model layer, N-34)
accumulates into ``cost.fixed_cost``.

Usage lands directly on ``workflow_steps.cost`` as
``{prompt_tokens, completion_tokens, fixed_cost, units?}`` — no step-name
intermediate. Run-level cost is an aggregate view (sum over the run's nodes).
"""

import contextvars
import json
from uuid import UUID

import structlog
from sqlalchemy import select, text

from app.models.database import AsyncSessionLocal
from app.models.tables import WorkflowStep

logger = structlog.get_logger()

_current_workflow_step_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "metering_workflow_step_id",
    default=None,
)


class bind_workflow_step:
    """Bind LLM usage to a workflow step for the current async context."""

    def __init__(self, node_id: UUID) -> None:
        self._node_id = node_id
        self._token: contextvars.Token[UUID | None] | None = None

    def __enter__(self) -> "bind_workflow_step":
        self._token = _current_workflow_step_id.set(self._node_id)
        return self

    def __exit__(self, *exc: object) -> bool:
        if self._token is not None:
            _current_workflow_step_id.reset(self._token)
        return False


async def record_usage(usage: dict | None) -> None:
    """Accumulate one LLM call's token usage onto the bound workflow step.

    Silently no-ops when no node is bound (e.g. request-path calls such as
    infer-intent) or when the provider omitted usage. Metering must never
    break generation, so failures are logged and swallowed.
    """
    if not usage:
        return
    node_id = _current_workflow_step_id.get()
    if node_id is None:
        return
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if not prompt and not completion:
        return
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    """
                    UPDATE workflow_steps
                    SET cost = jsonb_build_object(
                            'prompt_tokens',
                            COALESCE((cost->>'prompt_tokens')::int, 0) + :pt,
                            'completion_tokens',
                            COALESCE((cost->>'completion_tokens')::int, 0) + :ct,
                            'fixed_cost',
                            COALESCE((cost->>'fixed_cost')::float, 0.0)
                        ),
                        updated_at = now()
                    WHERE id = :nid
                    """
                ),
                {"pt": prompt, "ct": completion, "nid": node_id},
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — metering must never break generation
        logger.warning("metering_record_failed", error=str(e), node_id=str(node_id))


async def record_media_usage(units: dict[str, float]) -> None:
    """Accumulate one media call's actual units + priced money onto the bound
    workflow step (TTS chars / voice clones / images / music pieces).

    Units merge into ``cost.units`` (the actuals the estimate's mechanical
    units calibrate against); the money side (``price_units`` — the client's
    price list, imported deferred to keep client→metering the only import
    direction) adds into ``cost.fixed_cost``. Same no-op and never-break
    disciplines as ``record_usage``.
    """
    if not units:
        return
    node_id = _current_workflow_step_id.get()
    if node_id is None:
        return
    from app.providers.llm.minimax import price_units  # deferred: import cycle

    money = price_units(units)
    try:
        async with AsyncSessionLocal() as db:
            row = await db.scalar(
                select(WorkflowStep.cost).where(WorkflowStep.id == node_id)
            )
            cost = dict(row or {})
            cost["fixed_cost"] = round(
                float(cost.get("fixed_cost") or 0.0) + money, 6
            )
            merged = dict(cost.get("units") or {})
            for key, value in units.items():
                merged[key] = round(float(merged.get(key) or 0.0) + float(value), 4)
            cost["units"] = merged
            await db.execute(
                text(
                    "UPDATE workflow_steps SET cost = CAST(:cost AS jsonb), "
                    "updated_at = now() WHERE id = :nid"
                ),
                {"cost": json.dumps(cost), "nid": node_id},
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — metering must never break generation
        logger.warning("metering_record_failed", error=str(e), node_id=str(node_id))
