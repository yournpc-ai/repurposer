"""Per-node LLM usage metering (ADR-025, RunPlan Phase 1).

The single LLM choke point (``clients/minimax.py``) reports API ``usage`` here;
``record_usage`` accumulates it onto the plan node currently bound via
``bind_plan_node``. Binding is a contextvar, so concurrent node executions
(asyncio tasks) each meter their own node, and retries/fallbacks inside one
node accumulate naturally — every attempt is billed.

Usage lands directly on ``plan_nodes.cost`` as
``{prompt_tokens, completion_tokens, fixed_cost}`` — no step-name intermediate.
Run-level cost is an aggregate view (sum over the run's nodes).
"""

import contextvars
from uuid import UUID

import structlog
from sqlalchemy import text

from app.models.database import AsyncSessionLocal

logger = structlog.get_logger()

_current_plan_node_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "metering_plan_node_id",
    default=None,
)


class bind_plan_node:
    """Bind LLM usage to a plan node for the current async context."""

    def __init__(self, node_id: UUID) -> None:
        self._node_id = node_id
        self._token: contextvars.Token[UUID | None] | None = None

    def __enter__(self) -> "bind_plan_node":
        self._token = _current_plan_node_id.set(self._node_id)
        return self

    def __exit__(self, *exc: object) -> bool:
        if self._token is not None:
            _current_plan_node_id.reset(self._token)
        return False


async def record_usage(usage: dict | None) -> None:
    """Accumulate one LLM call's token usage onto the bound plan node.

    Silently no-ops when no node is bound (e.g. request-path calls such as
    infer-intent) or when the provider omitted usage. Metering must never
    break generation, so failures are logged and swallowed.
    """
    if not usage:
        return
    node_id = _current_plan_node_id.get()
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
                    UPDATE plan_nodes
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
