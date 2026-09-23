"""User settings — the confirm_strategy seat's pure law (ADR-092 §1, E5).

``users.settings`` JSONB carries the user-level preferences (persona
brand/voice 的 user 级先例). This module is the key set's sole vocabulary:
read tolerance (a missing/unknown value reads as the default — legacy rows
and hand-edited JSON never 500) and the merge write (other keys survive a
one-key PUT). Pure — the routes stay mechanical.
"""

from typing import Any

CONFIRM_STRATEGIES = ("always", "large", "never")
DEFAULT_CONFIRM_STRATEGY = "large"


def read_confirm_strategy(settings: dict[str, Any] | None) -> str:
    """Read-tolerant strategy: absent settings, a missing key, or an
    unknown stored value all read as the default (读容忍律 — the value is
    a preference, never a gate)."""
    value = (settings or {}).get("confirm_strategy")
    return value if value in CONFIRM_STRATEGIES else DEFAULT_CONFIRM_STRATEGY


def merge_confirm_strategy(settings: dict[str, Any] | None, value: str) -> dict[str, Any]:
    """One-key merge write — the rest of the settings block survives.
    Callers validate ``value`` against CONFIRM_STRATEGIES before this
    (the route's 422); this function never refuses."""
    merged = dict(settings or {})
    merged["confirm_strategy"] = value
    return merged
