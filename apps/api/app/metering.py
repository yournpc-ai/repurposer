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

Accumulation is IN MEMORY (D9, 2026-08-27): recording touches no SQL. The
bound step's ``execute_step`` folds the accrued ledger onto
``workflow_steps.cost`` in ONE write at the end of the execution — on the
success path and every terminal exception branch alike. The old per-call
UPDATEs opened a second session that locked the very row the runner's own
uncommitted session was holding — an application-level self-deadlock under
node concurrency.

Usage lands on ``workflow_steps.cost`` as
``{prompt_tokens, completion_tokens, fixed_cost, units?}`` — no step-name
intermediate. Run-level cost is an aggregate view (sum over the run's nodes).
"""

import contextvars
from uuid import UUID

import structlog

logger = structlog.get_logger()

_current_cost_ledger: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "metering_cost_ledger",
    default=None,
)


def _new_ledger() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "fixed_cost": 0.0, "units": {}}


class bind_workflow_step:
    """Bind an in-memory cost ledger to a workflow step for the current async
    context. ``accrued`` is the ledger itself — the caller (execute_step)
    keeps the reference and folds it onto the step row after the run, on
    success and failure paths alike."""

    def __init__(self, node_id: UUID) -> None:
        self._node_id = node_id
        self._token: contextvars.Token[dict | None] | None = None
        self.accrued: dict = _new_ledger()

    def __enter__(self) -> "bind_workflow_step":
        self._token = _current_cost_ledger.set(self.accrued)
        return self

    def __exit__(self, *exc: object) -> bool:
        if self._token is not None:
            _current_cost_ledger.reset(self._token)
        return False


def merge_accrued_cost(node_cost: dict | None, accrued: dict | None) -> dict | None:
    """Fold one execution's accrued ledger into the step's persisted cost.

    Additive over whatever the row already carries — a retried or bounced
    attempt bills on top of earlier attempts, same as the per-call UPDATE
    regime did. Returns the row's cost unchanged when nothing was metered
    this execution (a node with no LLM/media calls keeps ``cost`` NULL, so
    the estimate-vs-actual drift report keeps ignoring it).
    """
    if not accrued or not (
        accrued.get("prompt_tokens")
        or accrued.get("completion_tokens")
        or accrued.get("fixed_cost")
        or accrued.get("units")
    ):
        return node_cost
    cost = dict(node_cost or {})
    cost["prompt_tokens"] = int(cost.get("prompt_tokens") or 0) + int(
        accrued.get("prompt_tokens") or 0
    )
    cost["completion_tokens"] = int(cost.get("completion_tokens") or 0) + int(
        accrued.get("completion_tokens") or 0
    )
    cost["fixed_cost"] = round(
        float(cost.get("fixed_cost") or 0.0) + float(accrued.get("fixed_cost") or 0.0),
        6,
    )
    units = dict(cost.get("units") or {})
    for key, value in (accrued.get("units") or {}).items():
        units[key] = round(float(units.get(key) or 0.0) + float(value), 4)
    if units:
        cost["units"] = units
    return cost


async def record_usage(usage: dict | None) -> None:
    """Accumulate one LLM call's token usage onto the bound workflow step.

    Silently no-ops when no node is bound (e.g. request-path calls such as
    infer-intent) or when the provider omitted usage. Pure ledger mutation —
    metering must never break generation.
    """
    if not usage:
        return
    accrued = _current_cost_ledger.get()
    if accrued is None:
        return
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if not prompt and not completion:
        return
    accrued["prompt_tokens"] += prompt
    accrued["completion_tokens"] += completion


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
    accrued = _current_cost_ledger.get()
    if accrued is None:
        return
    try:
        from app.providers.llm.minimax import price_units  # deferred: import cycle

        money = price_units(units)
    except Exception as e:  # noqa: BLE001 — metering must never break generation
        logger.warning("metering_price_failed", error=str(e))
        money = 0.0
    accrued["fixed_cost"] = round(accrued["fixed_cost"] + money, 6)
    merged = accrued["units"]
    for key, value in units.items():
        merged[key] = round(float(merged.get(key) or 0.0) + float(value), 4)
