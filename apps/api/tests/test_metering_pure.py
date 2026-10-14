"""Tests for the conversation-turn usage ledger (ADR-117 D3 — B3).

Pure coverage only (suite discipline: no DB, no LLM, no HTTP — the db is an
in-memory add-capture stub; ``record_usage``/``fold_conversation_usage`` are
the units under test). The locked matrix:

- fold aggregation: a turn's tool-loop iterations aggregate into ONE
  conversation_usage row (summed tokens, cached folded, cost priced at
  write via price_tokens, model = the configured chat model).
- 空回合零行: a turn with no LLM call (typed answers, canned replies)
  writes NOTHING.
- never-break: a price-list failure degrades to cost_usd=0.0 + the row
  still lands (the token counts stay truthful); record_usage without a
  binding / without usage is a silent no-op.
- cached semantics: the provider's cache report rides when present
  (vendor key shapes tolerated), NULL when never reported.
"""

import uuid

import pytest

from app.config import settings
from app.metering import (
    bind_conversation_turn,
    bind_workflow_step,
    fold_conversation_usage,
    record_usage,
)
from app.providers.llm.minimax import price_tokens


class _DbStub:
    """The fold's only session surface is ``add`` — capture it."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, row) -> None:
        self.added.append(row)


def _usage(prompt: int, completion: int, **extra) -> dict:
    return {"prompt_tokens": prompt, "completion_tokens": completion, **extra}


@pytest.mark.asyncio
async def test_record_usage_accumulates_onto_the_bound_conversation_ledger() -> None:
    with bind_conversation_turn() as bound:
        await record_usage(_usage(100, 40))
        await record_usage(_usage(60, 10, prompt_cache_hit_tokens=80))
    assert bound.accrued == {
        "prompt_tokens": 160,
        "completion_tokens": 50,
        "cached_tokens": 80,
    }


@pytest.mark.asyncio
async def test_record_usage_without_binding_is_a_silent_noop() -> None:
    # No bind at all: nothing raised, nothing accumulated anywhere.
    await record_usage(_usage(100, 40))
    await record_usage(None)


@pytest.mark.asyncio
async def test_the_two_ledgers_are_independent() -> None:
    # The workflow ledger and the conversation ledger are independent
    # contextvars — each fold seat (execute_step vs the turn tail) reads
    # only its own, so a call lands on whichever ledgers happen to be bound
    # (structurally they never coexist: worker vs request path).
    with bind_workflow_step(uuid.uuid4()) as step:
        with bind_conversation_turn() as convo:
            await record_usage(_usage(10, 5))
    assert step.accrued["prompt_tokens"] == 10
    assert convo.accrued["prompt_tokens"] == 10


@pytest.mark.asyncio
async def test_fold_aggregates_the_turn_into_one_priced_row() -> None:
    db = _DbStub()
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
    with bind_conversation_turn() as bound:
        await record_usage(_usage(100, 40, prompt_cache_hit_tokens=70))
        await record_usage(_usage(60, 10))
        await fold_conversation_usage(
            db, user_id=user_id, project_id=project_id, accrued=bound.accrued
        )
    assert len(db.added) == 1
    row = db.added[0]
    assert row.user_id == user_id and row.project_id == project_id
    assert row.prompt_tokens == 160 and row.completion_tokens == 50
    assert row.cached_tokens == 70
    assert row.model == settings.minimax_model
    assert row.cost_usd == pytest.approx(price_tokens(160, 50), abs=1e-9)


@pytest.mark.asyncio
async def test_empty_turn_writes_no_row() -> None:
    db = _DbStub()
    await fold_conversation_usage(
        db, user_id=uuid.uuid4(), project_id=None, accrued=None
    )
    with bind_conversation_turn() as bound:  # bound but never metered
        pass
    await fold_conversation_usage(
        db, user_id=uuid.uuid4(), project_id=None, accrued=bound.accrued
    )
    assert db.added == []


@pytest.mark.asyncio
async def test_pricing_failure_never_breaks_the_fold() -> None:
    db = _DbStub()
    import app.providers.llm.minimax as minimax

    real = minimax.price_tokens
    minimax.price_tokens = None  # type: ignore[assignment]
    try:
        with bind_conversation_turn() as bound:
            await record_usage(_usage(100, 40))
            await fold_conversation_usage(
                db, user_id=uuid.uuid4(), project_id=None, accrued=bound.accrued
            )
    finally:
        minimax.price_tokens = real  # type: ignore[assignment]
    assert len(db.added) == 1
    row = db.added[0]
    assert row.prompt_tokens == 100 and row.completion_tokens == 40
    assert row.cost_usd == 0.0  # degraded, but the token counts stay truthful


@pytest.mark.asyncio
async def test_cached_tokens_null_when_the_provider_says_nothing() -> None:
    db = _DbStub()
    with bind_conversation_turn() as bound:
        await record_usage(_usage(10, 5))
        await fold_conversation_usage(
            db, user_id=uuid.uuid4(), project_id=None, accrued=bound.accrued
        )
    assert db.added[0].cached_tokens is None


@pytest.mark.asyncio
async def test_cached_tokens_tolerates_the_vendor_key_shapes() -> None:
    with bind_conversation_turn() as bound:
        await record_usage(_usage(10, 5, cached_tokens=3))
        await record_usage(
            _usage(10, 5, prompt_tokens_details={"cached_tokens": 7})
        )
    assert bound.accrued["cached_tokens"] == 10
