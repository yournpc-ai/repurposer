"""Vendor-neutral LLM seam vocabulary (Model 层, ADR-077 判词④ 配套结构收口).

The error types every client speaks — de-branded from their MiniMax birth
names so a second provider's client raises the SAME types and every upstream
catch (intent agents, chat loop, pipeline nodes, route boundaries) keeps
working unchanged. The ``user_key`` tax is unchanged: raise sites key the
failure mode, wrapper layers propagate the key.
"""


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
