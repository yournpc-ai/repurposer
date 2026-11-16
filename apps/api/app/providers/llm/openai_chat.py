"""Shared OpenAI-compatible Chat Completions wire machinery.

Only provider-independent transport and tool-call framing live here. Model
selection, reasoning controls, content cleanup, media support and pricing stay
in each vendor's client.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx

from app.providers.llm.base import LLMError, LLMSchemaError, ToolCall


_client_pool: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None


def _shared_client() -> httpx.AsyncClient:
    """One connection pool per event loop, shared by compatible providers."""
    loop = asyncio.get_running_loop()
    global _client_pool
    if (
        _client_pool is None
        or _client_pool[0] is not loop
        or _client_pool[1].is_closed
    ):
        _client_pool = (
            loop,
            httpx.AsyncClient(
                timeout=httpx.Timeout(120, read=1800),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            ),
        )
    return _client_pool[1]


@asynccontextmanager
async def _pooled_client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield the shared pool without closing it after an individual call."""
    yield _shared_client()


def _payload_chars(messages: list[dict]) -> int:
    """Measure text and inline-media URL sizes without logging their content."""
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                total += len(part.get("text") or "")
                for key in ("image_url", "video_url", "audio_url"):
                    value = part.get(key)
                    if isinstance(value, dict) and value.get("url"):
                        total += len(value["url"])
    return total


def _raise_for_status(
    response: httpx.Response,
    *,
    provider: str = "MiniMax",
    unavailable_key: str = "provider_unavailable",
) -> None:
    """Translate HTTP failures into the provider-neutral error vocabulary."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMError(
            f"{provider} HTTP {exc.response.status_code}: {exc.response.text[:300]}",
            user_key=(
                "provider_rate_limited"
                if exc.response.status_code == 429
                else "provider_quota_exhausted"
                if exc.response.status_code == 402
                else unavailable_key
            ),
        ) from exc


def _retryable_provider_error(exc: BaseException) -> bool:
    """Retry transient transport failures, never schema or deterministic 4xx."""
    if isinstance(exc, LLMSchemaError):
        return False
    if isinstance(exc, (asyncio.TimeoutError, asyncio.CancelledError)):
        return False
    if not isinstance(exc, LLMError):
        return True
    cause = exc.__cause__
    if isinstance(cause, httpx.HTTPStatusError):
        status = cause.response.status_code
        if 400 <= status < 500 and status not in {408, 429}:
            return False
    return exc.user_key != "provider_quota_exhausted"


def _parse_tool_arguments(name: str, raw: str, finish_reason: str | None) -> dict:
    """Parse complete argument text; malformed/truncated calls are schema errors."""
    if not raw:
        return {}
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMSchemaError(
            f"tool call {name!r} arguments did not parse "
            f"(finish_reason={finish_reason}; truncation or malformation): {exc}\n"
            f"Raw: {raw[:500]}"
        ) from exc
    if not isinstance(arguments, dict):
        raise LLMSchemaError(
            f"tool call {name!r} arguments are not a JSON object: {raw[:200]}"
        )
    return arguments


def _tool_call_from_object(tc: dict, finish_reason: str | None) -> ToolCall:
    """Parse one complete non-streaming tool call."""
    function = tc.get("function") or {}
    name = function.get("name") or ""
    if not name:
        raise LLMSchemaError(
            f"tool call {tc.get('id')!r} carried no function name "
            f"(finish_reason={finish_reason})"
        )
    return ToolCall(
        id=tc.get("id"),
        name=name,
        arguments=_parse_tool_arguments(
            name, function.get("arguments") or "", finish_reason
        ),
    )


@dataclass
class _AccCall:
    """One in-flight tool call inside the streaming accumulator."""

    id: str | None = None
    name: str | None = None
    arg_parts: list[str] = field(default_factory=list)


class _ToolCallAccumulator:
    """Assemble OpenAI-compatible streaming tool-call argument fragments."""

    def __init__(self) -> None:
        self._calls: dict[int, _AccCall] = {}

    def feed(self, deltas: list[dict]) -> list[str]:
        """Consume deltas and return function names that became known."""
        named: list[str] = []
        for tool_call in deltas:
            index = int(tool_call.get("index") or 0)
            call = self._calls.setdefault(index, _AccCall())
            if tool_call.get("id"):
                call.id = tool_call["id"]
            function = tool_call.get("function") or {}
            if function.get("name"):
                if call.name is None:
                    named.append(function["name"])
                call.name = function["name"]
            fragment = function.get("arguments")
            if fragment:
                call.arg_parts.append(fragment)
        return named

    def raw_calls(self) -> list[dict]:
        """Return unparsed wire arguments in call order for full tracing."""
        return [
            {
                "id": call.id,
                "name": call.name,
                "arguments": "".join(call.arg_parts),
            }
            for _, call in sorted(self._calls.items())
        ]

    def finish(self, finish_reason: str | None) -> list[ToolCall]:
        """Return calls in wire order, validating every argument payload."""
        calls: list[ToolCall] = []
        for index in sorted(self._calls):
            call = self._calls[index]
            if not call.name:
                raise LLMSchemaError(
                    f"tool call #{index} never carried a function name "
                    f"(finish_reason={finish_reason})"
                )
            arguments = _parse_tool_arguments(
                call.name, "".join(call.arg_parts), finish_reason
            )
            calls.append(ToolCall(id=call.id, name=call.name, arguments=arguments))
        return calls
