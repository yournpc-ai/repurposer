"""Tests for the three-tier wire-format law (providers/llm/base) — client
capability flags + ``pick_wire_tier`` (ADR-077 判词④).

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP). The
law: tiers swap ONLY the wire format, never the verdict contract — the
harness picks the highest tier both sides speak and degradation is
automatic (the Tier-0 floor is always speakable).
"""

from app.providers.llm.base import (
    ProviderCapabilities,
    WireTier,
    pick_wire_tier,
)
from app.providers.llm.minimax import MiniMaxClient

BARE = ProviderCapabilities()
TOOLS = ProviderCapabilities(supports_native_tools=True, reasoning_dialect="think_block")


def test_floor_is_always_speakable() -> None:
    """A capability-bare client still answers Tier 0 (action-JSON in prompt —
    the research-node precedent carries every verdict semantic there)."""
    assert pick_wire_tier(WireTier.ACTION_JSON, BARE) == WireTier.ACTION_JSON
    assert pick_wire_tier(WireTier.NATIVE_TOOLS, BARE) == WireTier.ACTION_JSON


def test_highest_mutual_tier_wins() -> None:
    """Both sides speak native tools → Tier 1."""
    assert pick_wire_tier(WireTier.NATIVE_TOOLS, TOOLS) == WireTier.NATIVE_TOOLS


def test_harness_ceiling_is_respected() -> None:
    """A capable client never lifts the harness past its declared ceiling."""
    assert pick_wire_tier(WireTier.ACTION_JSON, TOOLS) == WireTier.ACTION_JSON


def test_provider_native_is_never_inferred() -> None:
    """Tier 2 has no auto-pick signal: extras are opted into per provider by
    the harness, so flags alone never select PROVIDER_NATIVE."""
    assert pick_wire_tier(WireTier.PROVIDER_NATIVE, TOOLS) == WireTier.NATIVE_TOOLS
    assert pick_wire_tier(WireTier.PROVIDER_NATIVE, BARE) == WireTier.ACTION_JSON


def test_tier_ordering() -> None:
    """The rungs are ordered: floor < native tools < provider-native."""
    assert WireTier.ACTION_JSON < WireTier.NATIVE_TOOLS < WireTier.PROVIDER_NATIVE


def test_capability_defaults_are_the_floor() -> None:
    """An undeclared client is floor-only: no native tools, no json_schema,
    no reasoning dialect."""
    caps = ProviderCapabilities()
    assert not caps.supports_native_tools
    assert not caps.supports_json_schema
    assert caps.reasoning_dialect is None


def test_minimax_capability_declaration() -> None:
    """M3's declaration matches the spike findings (2026-09-11/12): native
    tool_calls is its only schema-following channel — json_schema is ignored
    outright — and the think-block dialect is normalized inside the client."""
    caps = MiniMaxClient.capabilities
    assert caps.supports_native_tools
    assert not caps.supports_json_schema
    assert caps.reasoning_dialect == "think_block"
