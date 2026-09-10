"""Repair-round visibility (2026-09-11 服务感).

Pure funnel coverage (suite discipline: no DB, no LLM, no HTTP — the client
is an in-memory stub): the schema-repair round fires the reserved
``on_repair`` kwarg exactly once, a clean first pass never fires it, a
second rejection still propagates after the signal, and the kwarg never
reaches ``assemble`` (the signature-purity discipline — a zero-arg assemble
would TypeError on the leak).
"""

import asyncio

import pytest
from pydantic import BaseModel

from app.agents.base import Agent
from app.providers.llm.minimax import MiniMaxSchemaError


class _Out(BaseModel):
    answer: str


def _assemble_no_args():
    """Zero-arg assemble: if the reserved kwarg leaked into the assemble
    inputs this would be a TypeError, so every call below doubles as the
    signature-purity assertion."""
    return ({}, [])


class _StubClient:
    """The first ``rejections`` generate calls raise MiniMaxSchemaError; the
    next one succeeds. Records call count for the once-only assertions."""

    def __init__(self, rejections: int):
        self.rejections = rejections
        self.calls = 0

    async def generate(self, *, messages, response_model, temperature):
        self.calls += 1
        if self.calls <= self.rejections:
            raise MiniMaxSchemaError("bad shape")
        return response_model(answer="ok")


def _agent(name: str, rejections: int) -> Agent[_Out]:
    return Agent(
        name=name,  # unique per test — AGENTS self-registration rejects duplicates
        prompt="chat_intent.j2",  # tiny template; the env renders any kwargs
        schema=_Out,
        system="test",
        assemble=_assemble_no_args,
        client=_StubClient(rejections),
    )


async def _run_clean_pass_never_fires_on_repair():
    fired = 0

    async def on_repair():
        nonlocal fired
        fired += 1

    result = await _agent("test_repair_clean", 0).call(on_repair=on_repair)
    assert result.answer == "ok"
    assert fired == 0


async def _run_repair_round_fires_on_repair_exactly_once():
    fired = 0

    async def on_repair():
        nonlocal fired
        fired += 1

    agent = _agent("test_repair_once", 1)
    result = await agent.call(on_repair=on_repair)
    assert result.answer == "ok"
    assert fired == 1
    assert agent.client.calls == 2  # first pass + the one bounded repair round


async def _run_second_rejection_propagates_after_the_signal():
    fired = 0

    async def on_repair():
        nonlocal fired
        fired += 1

    with pytest.raises(MiniMaxSchemaError):
        await _agent("test_repair_exhausted", 2).call(on_repair=on_repair)
    assert fired == 1  # signalled the round, then the round failed — honest


async def _run_sync_callback_is_accepted():
    """RepairCallback is sync-or-async, same discipline as DeltaCallback."""
    fired = 0

    def on_repair():
        nonlocal fired
        fired += 1

    result = await _agent("test_repair_sync_cb", 1).call(on_repair=on_repair)
    assert result.answer == "ok"
    assert fired == 1

def test_clean_pass_never_fires_on_repair():
    asyncio.run(_run_clean_pass_never_fires_on_repair())


def test_repair_round_fires_on_repair_exactly_once():
    asyncio.run(_run_repair_round_fires_on_repair_exactly_once())


def test_second_rejection_propagates_after_the_signal():
    asyncio.run(_run_second_rejection_propagates_after_the_signal())


def test_sync_callback_is_accepted():
    asyncio.run(_run_sync_callback_is_accepted())
