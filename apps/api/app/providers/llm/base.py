"""Vendor-neutral LLM seam vocabulary (Model 层, ADR-077 判词④ 配套结构收口).

The error types every client speaks — de-branded from their MiniMax birth
names so a second provider's client raises the SAME types and every upstream
catch (intent agents, chat loop, pipeline nodes, route boundaries) keeps
working unchanged. The ``user_key`` tax is unchanged: raise sites key the
failure mode, wrapper layers propagate the key.

The wire-format law (层只换线格式，永不动调用契约): the three tiers swap ONLY
the wire format — the validated call contract is identical across them, so
falling to a lower tier is always safe and repair/error-feedback semantics
are isomorphic. Each client declares its ``ProviderCapabilities`` once; the
harness picks the highest tier both sides speak (``pick_wire_tier``) and
degradation is automatic.

- Tier 0 ``ACTION_JSON`` (the floor): action-JSON in the prompt — the
  research node's bounded loop already carries every call semantic this
  way, so every provider can always be spoken to.
- Tier 1 ``NATIVE_TOOLS``: the provider's native tool_calls channel — prose
  rides the content channel, calls ride tool_call argument accumulation
  (M3's only schema-following channel, spike 2026-09-11/12).
- Tier 2 ``PROVIDER_NATIVE``: provider-specific extras (strict schema /
  parallel calls / reasoning control), declared per provider.
"""

from dataclasses import dataclass
from enum import IntEnum


class LLMError(Exception):
    """LLM provider API error.

    ``user_key`` names the localized user-facing line (pipeline/errors.py's
    USER_ERROR_LINES) for when this surfaces on a failed step row — set at the
    raise site by failure mode, propagated through wrapper layers via
    ``propagate_key``."""

    def __init__(self, message: str, *, user_key: str | None = None) -> None:
        super().__init__(message)
        self.user_key = user_key


class LLMSchemaError(LLMError):
    """Structured-output validation failed at the Model boundary (the raw
    completion did not parse into the caller's contract — a response_model,
    or a tool call's arguments; the truncation signature — finish_reason
    says tool_calls but the arguments hit EOF — is the same class).

    Distinct from transport/HTTP failures so the harness can answer with its
    one bounded repair round (structured echo, ADR-039 P3) — the only retry
    with feedback. Tenacity at the client layer must NOT retry it (a blind
    re-roll); the repair round replaces it. Transport failures stay
    tenacity-retried — a transport concern, never repaired by the harness.
    """

    def __init__(self, message: str, *, user_key: str = "ai_unreadable") -> None:
        super().__init__(message, user_key=user_key)


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a client's provider can speak, declared once on the client class
    (ADR-077 判词④). The harness reads these flags to pick a wire tier; it
    never probes or guesses capabilities itself.

    ``reasoning_dialect`` names the provider's reasoning-channel dialect the
    client normalizes INTERNALLY (ADR-066 位置律 — e.g. MiniMax's
    ``<think>…</think>`` preamble, stripped by its own client before any
    fragment reaches an upstream consumer). ``None`` = no reasoning channel.
    """

    supports_native_tools: bool = False
    supports_json_schema: bool = False
    reasoning_dialect: str | None = None


class WireTier(IntEnum):
    """The three wire-format layers (ADR-077 判词④), ordered — a higher tier
    is a richer channel for the SAME call contract, never a different
    call."""

    ACTION_JSON = 0  # the floor: action-JSON in the prompt
    NATIVE_TOOLS = 1  # native tool_calls channel
    PROVIDER_NATIVE = 2  # provider-specific extras, declared per provider


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation from the provider's tool_calls channel — the
    Tier-1 wire's call unit. ``arguments`` is the PARSED JSON object: a
    fragment stream that fails to parse never reaches here — it raises
    ``LLMSchemaError`` at the seam (truncation signature: finish_reason says
    tool_calls but the arguments hit EOF) so the harness answers it with the
    one feedback repair round, same class as any schema rejection."""

    id: str | None
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolGeneration:
    """Provider-neutral result of a tool-formatted generation: ``content`` is
    the prose channel (dialect-clean — the client's reasoning dialect is
    already stripped at the seam), ``tool_calls`` the accumulated calls.
    Empty ``tool_calls`` with prose is a LEGAL shape (tool_choice="auto",
    the model chose to speak) — what that means is the caller's contract,
    never the wire's."""

    content: str
    tool_calls: list[ToolCall]


def pick_wire_tier(harness_max: WireTier, capabilities: ProviderCapabilities) -> WireTier:
    """The highest tier BOTH sides speak (harness 选双方共持最高层).

    The floor is always speakable (Tier 0 is prompt-side, every provider
    answers it), so selection never fails: a client without native tools
    lands the harness on Tier 0 — 降级自动, no special case at the call
    site. Tier 2 has no auto-pick signal yet: provider-specific extras are
    opted into per provider by the harness, never inferred from flags.
    """
    client_max = (
        WireTier.NATIVE_TOOLS if capabilities.supports_native_tools else WireTier.ACTION_JSON
    )
    return min(harness_max, client_max)
