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

工作区布局 (ADR-123): ``workspace_layout`` = the canvas capability bit's
second judgment source — ``auto`` (default) follows the viewport; ``chat``
pins the chat-first workspace on every screen. The server only STORES it
(cross-device sync): the effective ``canvas_available`` is composed
client-side and rides every chat request (ADR-118 双键), so nothing
server-side consumes this key.
"""

from typing import Any, Literal

CONFIRM_MODES = ("auto", "ask")
DEFAULT_CONFIRM_MODE = "auto"
ConfirmationKey = Literal["confirm_execution", "confirm_credits"]
CONFIRMATION_KEYS: tuple[ConfirmationKey, ...] = (
    "confirm_execution",
    "confirm_credits",
)

WORKSPACE_LAYOUTS = ("auto", "chat")
DEFAULT_WORKSPACE_LAYOUT = "auto"


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


def read_workspace_layout(settings: dict[str, Any] | None) -> str:
    """Read-tolerant layout pref: absent/unknown reads as ``auto`` (读容忍
    — the value is a preference, never a gate)."""
    value = (settings or {}).get("workspace_layout")
    return value if value in WORKSPACE_LAYOUTS else DEFAULT_WORKSPACE_LAYOUT


def merge_workspace_layout(
    settings: dict[str, Any] | None, value: str
) -> dict[str, Any]:
    """One-key merge write — the rest of the settings block survives. The
    route validates ``value`` against WORKSPACE_LAYOUTS before this."""
    merged = dict(settings or {})
    merged["workspace_layout"] = value
    return merged
