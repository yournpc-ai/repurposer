"""User settings — the confirmation prefs' seat (ADR-117 §1).

``users.settings`` JSONB carries the user-level preferences (persona
brand/voice 的 user 级先例). This module is the key set's sole vocabulary:
read tolerance (a missing/unknown value reads as the default — legacy rows
and hand-edited JSON never 500) and the merge write (other keys survive a
one-key PUT). Pure — the routes stay mechanical.

授权前移 (ADR-117): confirmation comes in exactly two kinds — execution
(whether the agent waits for a confirm beat before starting paid work) and
credits (whether a priced plan gets one priced confirmation). Both default
to ``auto`` (standing authorization): the presented plan starts on arrival.
``ask`` restores the per-beat confirm (ADR-092 口头确认律是 ask 档法律).
"""

from typing import Any, Literal

CONFIRM_MODES = ("auto", "ask")
DEFAULT_CONFIRM_MODE = "auto"
ConfirmationKey = Literal["confirm_execution", "confirm_credits"]
CONFIRMATION_KEYS: tuple[ConfirmationKey, ...] = (
    "confirm_execution",
    "confirm_credits",
)


def _read_mode(settings: dict[str, Any] | None, key: ConfirmationKey) -> str:
    value = (settings or {}).get(key)
    return value if value in CONFIRM_MODES else DEFAULT_CONFIRM_MODE


def read_confirmation_prefs(settings: dict[str, Any] | None) -> tuple[str, str]:
    """Read-tolerant prefs: absent settings, a missing key, or an unknown
    stored value all read as ``auto`` (读容忍律 — the value is a preference,
    never a gate). Returns ``(execution, credits)``."""
    return (
        _read_mode(settings, "confirm_execution"),
        _read_mode(settings, "confirm_credits"),
    )


def merge_confirmation_pref(
    settings: dict[str, Any] | None, key: ConfirmationKey, value: str
) -> dict[str, Any]:
    """One-key merge write — the rest of the settings block survives.
    Callers validate ``value`` against CONFIRM_MODES before this (the
    route's 422); this function never refuses."""
    merged = dict(settings or {})
    merged[key] = value
    return merged
