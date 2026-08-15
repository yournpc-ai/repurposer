"""Pipeline execution error taxonomy (agent-loop-upgrade W3).

Kept import-free so every layer (tools / node classes / orchestrator) can
share it without cycles.

**User-facing failure lines** (provider 错误人话化): exceptions carry a
``user_key`` — a machine key into ``USER_ERROR_LINES`` — and the orchestrator
bakes the localized line into ``node.error`` at fail time (the same
bake-at-write, UI-locale discipline as step summaries). Raw innards
(SQL/SQLAlchemy/httpx/pydantic dumps) stay in structlog only. Deterministic
input errors (plain ``ValueError`` sites, ``HTTPException.detail``) keep
their authored messages — a separate i18n debt, deliberately out of this
taxonomy.
"""

class TransientNodeError(Exception):
    """A retryable step failure: provider / network / storage hiccups.

    ``execute_step`` resets the node to ``pending`` (the worker's next tick is
    the backoff) when the kind carries retry budget (``NodeBase.retries``);
    anything else fails fast. Deterministic failures — missing inputs, empty
    batches, validation errors — must raise ordinary exceptions so they never
    burn retry budget.

    ``user_key`` names the user-facing line for the exhausted/terminal case.
    """

    def __init__(self, message: str, *, user_key: str | None = None) -> None:
        super().__init__(message)
        self.user_key = user_key


# Failure lines shown on the failed step row / clip card. Keys follow the
# UI locale (en/zh today); unknown locales fall back to English — the same
# fallback rule as summary_templates. Copy doctrine: plain and factual, an
# honest next step, no jargon ("provider" never appears).
USER_ERROR_LINES: dict[str, dict[str, str]] = {
    "provider_rate_limited": {
        "en": "The AI service is busy right now — please try again in a moment",
        "zh": "AI 服务正忙，请稍后重试",
    },
    "provider_quota_exhausted": {
        "en": "The AI service is out of quota — please try again later",
        "zh": "AI 服务额度已用完，请稍后再试",
    },
    "provider_unavailable": {
        "en": "The AI service is unavailable right now — please try again later",
        "zh": "AI 服务暂时不可用，请稍后重试",
    },
    "provider_unreachable": {
        "en": "Couldn't reach the AI service — please try again in a moment",
        "zh": "暂时连不上 AI 服务，请稍后重试",
    },
    "ai_unreadable": {
        "en": "The AI returned an unusable answer — please try again",
        "zh": "AI 返回了无法使用的回答，请重试",
    },
    "voice_unavailable": {
        "en": "The voice service is unavailable right now — please try again later",
        "zh": "配音服务暂时不可用，请稍后重试",
    },
    "storage_unavailable": {
        "en": "Saving the file failed — please try again",
        "zh": "文件保存失败，请重试",
    },
    "render_failed": {
        "en": "Video rendering failed — please try again",
        "zh": "视频渲染失败，请重试",
    },
    "step_failed": {
        "en": "This step hit an unexpected error",
        "zh": "这一步出了意外错误",
    },
}


def user_line(key: str, ui_language: str = "en") -> str:
    """The localized user-facing line for ``key``. Unknown keys/locales fall
    back to the generic line in English."""
    lines = USER_ERROR_LINES.get(key) or USER_ERROR_LINES["step_failed"]
    lang = (ui_language or "en").lower()
    return lines.get(lang) or lines["en"]


def user_error_line(exc: BaseException, ui_language: str = "en") -> str:
    """The localized user-facing line for ``exc``:

    1. ``user_key`` attr → the keyed localized line;
    2. **exact** ``ValueError`` → the authored message passes through (our
       deterministic raise sites speak human text — but pydantic's
       ``ValidationError`` IS a ValueError subclass whose str() is a
       technical dump, so the test is the exact type, never isinstance);
    3. a string ``detail`` attr (HTTPException — duck-typed to keep this
       module import-free) → the client-facing detail passes through;
    4. everything else (TypeError / SQLAlchemy / httpx innards) → the
       generic ``step_failed`` line.
    """
    key = getattr(exc, "user_key", None)
    if key:
        return user_line(key, ui_language)
    if type(exc) is ValueError:
        return str(exc)[:500]
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail[:500]
    return user_line("step_failed", ui_language)


def propagate_key(cause: BaseException, default: str) -> str:
    """The wrapper-site rule: a wrapped provider error keeps its own key;
    anything else gets the wrapper's family default."""
    return getattr(cause, "user_key", None) or default


__all__ = [
    "TransientNodeError",
    "USER_ERROR_LINES",
    "user_line",
    "user_error_line",
    "propagate_key",
]
