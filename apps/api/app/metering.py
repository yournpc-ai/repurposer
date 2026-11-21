"""Accumulate provider usage in the context of the calling MediaJob or Chat turn.

Media usage includes priced units. Chat folds provider tokens into conversation_usage.
The caller owns persistence and settlement.
"""

import contextvars
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger()

_current_cost_ledger: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "metering_cost_ledger",
    default=None,
)


def _new_ledger() -> dict:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "fixed_cost": 0.0,
        "token_cost_usd": None,
        "provider": None,
        "model": None,
        "units": {},
    }


class collect_execution_cost:
    """Collect provider usage within a single async execution."""

    def __init__(self) -> None:
        self._token: contextvars.Token[dict | None] | None = None
        self.accrued: dict = _new_ledger()

    def __enter__(self) -> "collect_execution_cost":
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
        or accrued.get("token_cost_usd") is not None
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
    if accrued.get("token_cost_usd") is not None:
        cost["token_cost_usd"] = round(
            float(cost.get("token_cost_usd") or 0.0)
            + float(accrued["token_cost_usd"]),
            6,
        )
    if accrued.get("provider") is not None:
        cost["provider"] = accrued["provider"]
    if accrued.get("model") is not None:
        cost["model"] = accrued["model"]
    units = dict(cost.get("units") or {})
    for key, value in (accrued.get("units") or {}).items():
        units[key] = round(float(units.get(key) or 0.0) + float(value), 4)
    if units:
        cost["units"] = units
    return cost


async def record_usage(
    usage: dict | None,
    *,
    provider: str | None = None,
    model: str | None = None,
    cost_usd: float | None = None,
) -> None:
    """Accumulate one LLM call's token usage and optional actual token cost.

    Providers with cache- or time-dependent prices pass their per-call cost;
    legacy callers retain the aggregate MiniMax pricing path. Pure ledger
    mutation — metering must never break generation.
    """
    if not usage:
        return
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if not prompt and not completion:
        return
    accrued = _current_cost_ledger.get()
    if accrued is not None:
        accrued["prompt_tokens"] += prompt
        accrued["completion_tokens"] += completion
        if provider is not None:
            accrued["provider"] = provider
        if model is not None:
            accrued["model"] = model
        if cost_usd is not None:
            accrued["token_cost_usd"] = float(accrued["token_cost_usd"] or 0.0) + cost_usd
    conversation = _current_conversation_ledger.get()
    if conversation is not None:
        conversation["prompt_tokens"] += prompt
        conversation["completion_tokens"] += completion
        if provider is not None:
            conversation["provider"] = provider
        if model is not None:
            previous_model = conversation.get("model")
            if previous_model not in (None, model):
                logger.warning(
                    "conversation_usage_mixed_models",
                    previous_model=previous_model,
                    model=model,
                )
            conversation["model"] = model
        if cost_usd is not None:
            conversation["cost_usd"] = float(conversation["cost_usd"] or 0.0) + cost_usd
        cached = _cached_tokens_of(usage)
        if cached is not None:
            conversation["cached_tokens"] = (
                int(conversation["cached_tokens"] or 0) + cached
            )


# ---- conversation-turn ledger (ADR-117 D3 — metered, never billed) ---------

_current_conversation_ledger: contextvars.ContextVar[dict | None] = (
    contextvars.ContextVar("metering_conversation_ledger", default=None)
)
_current_conversation_trace: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("metering_conversation_trace", default=None)
)


_current_model_prompt: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "model_prompt_diagnostics", default=None,
)


def current_model_prompt() -> dict[str, Any] | None:
    return _current_model_prompt.get()


@contextmanager
def bind_model_prompt(assembly: dict[str, Any]):
    """Diagnostic sideband only; reset on success, failure and cancellation."""
    token = _current_model_prompt.set(assembly)
    try:
        yield
    finally:
        _current_model_prompt.reset(token)


def current_conversation_trace() -> dict[str, str] | None:
    """Optional local diagnostic correlation; never part of model input."""
    return _current_conversation_trace.get()


def _new_conversation_ledger() -> dict:
    # cached_tokens stays None until the provider actually reports cache
    # hits (conversation_usage.cached_tokens is nullable — 返回即记).
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": None,
        "provider": None,
        "model": None,
        "cost_usd": None,
    }


def _cached_tokens_of(usage: dict) -> int | None:
    """The provider's prefix-cache hit count, tolerant over the vendor key
    shapes (MiniMax ``prompt_cache_hit_tokens`` / OpenAI
    ``prompt_tokens_details.cached_tokens`` / a bare ``cached_tokens``).
    None = the provider said nothing about caching on this call."""
    direct = usage.get("prompt_cache_hit_tokens")
    if direct is None:
        direct = usage.get("cached_tokens")
    if direct is not None:
        return int(direct)
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        return int(details["cached_tokens"])
    return None


class bind_conversation_turn:
    """Bind an in-memory usage ledger to a conversation turn for the current
    async context (``collect_execution_cost``'s mirror). ``accrued`` is the
    ledger itself — the turn-entry seam keeps the reference and folds it
    into ONE ``conversation_usage`` row with the turn's own commit.

    Fire-and-forget children spawned inside the turn inherit the binding
    (contextvars copy semantics — same stance as the workflow ledger): a
    warm call that outlives the turn writes into a ledger nobody folds,
    which is silently dropped — never miscounted onto another turn."""

    def __init__(
        self, *, conversation_id: UUID | None = None, turn_id: UUID | str | None = None,
        project_id: UUID | str | None = None
    ) -> None:
        self._token: contextvars.Token[dict | None] | None = None
        self._trace_token: contextvars.Token[dict[str, str] | None] | None = None
        self._trace = (
            {"conversation_id": str(conversation_id), "turn_id": str(turn_id)}
            if conversation_id is not None and turn_id is not None else None
        )
        if self._trace is not None and project_id is not None:
            self._trace["project_id"] = str(project_id)
        self.accrued: dict = _new_conversation_ledger()

    def __enter__(self) -> "bind_conversation_turn":
        self._token = _current_conversation_ledger.set(self.accrued)
        if self._trace is not None:
            self._trace_token = _current_conversation_trace.set(self._trace)
        return self

    def __exit__(self, *exc: object) -> bool:
        if self._trace_token is not None:
            _current_conversation_trace.reset(self._trace_token)
        if self._token is not None:
            _current_conversation_ledger.reset(self._token)
        return False


async def fold_conversation_usage(
    db: Any,
    *,
    user_id: UUID,
    project_id: UUID | None,
    accrued: dict | None,
) -> None:
    """Fold one conversation turn's accrued ledger into ONE
    ``conversation_usage`` row, added to the turn's own session so the row
    rides the SAME commit as the assistant message (billing write
    discipline). An empty turn (no LLM call — typed answers, canned
    replies) writes NO row. Pricing runs at write time and must never break
    the turn: a price-list failure degrades to ``cost_usd=0.0`` plus a
    warning (the token counts stay truthful).
    """
    if not accrued or not (
        accrued.get("prompt_tokens") or accrued.get("completion_tokens")
    ):
        return
    from app.config import settings
    from app.models.tables import ConversationUsage  # deferred: model edge
    from app.providers.llm import get_llm_client, price_text_tokens

    prompt = int(accrued.get("prompt_tokens") or 0)
    completion = int(accrued.get("completion_tokens") or 0)
    provider = accrued.get("provider")
    model = accrued.get("model")
    if provider is None and model is None:
        # Bare legacy records belong to MiniMax even after the deployment's
        # default text provider changes.
        provider = "minimax"
        model = settings.minimax_model
    model = model or get_llm_client().model
    if accrued.get("cost_usd") is not None:
        cost = float(accrued["cost_usd"])
    else:
        try:
            cost = price_text_tokens(
                prompt,
                completion,
                provider=provider,
                model=model,
            )
        except Exception as e:  # noqa: BLE001 — metering must never break the turn
            logger.warning("conversation_usage_price_failed", error=str(e))
            cost = 0.0
    db.add(
        ConversationUsage(
            user_id=user_id,
            project_id=project_id,
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=(
                int(accrued["cached_tokens"])
                if accrued.get("cached_tokens") is not None
                else None
            ),
            cost_usd=round(cost, 6),
            model=model,
        )
    )


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
