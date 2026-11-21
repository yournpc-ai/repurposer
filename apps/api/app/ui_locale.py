"""Capture the browser language from Accept-Language for request-scoped display text."""

import contextvars

_request_ui_language: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ui_language",
    default=None,
)


def capture_ui_language(accept_language: str | None) -> None:
    """Middleware hook: keep the primary subtag ("zh-CN,zh;q=0.9" → "zh")."""
    primary = (accept_language or "").split(",")[0].split("-")[0].strip().lower()
    _request_ui_language.set(primary or None)


def current_ui_language() -> str | None:
    """The requesting browser's locale, None outside a request (worker)."""
    return _request_ui_language.get()
