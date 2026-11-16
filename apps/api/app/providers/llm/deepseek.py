"""DeepSeek text/code client using OpenAI-compatible Chat Completions."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time as datetime_time
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.llm.base import (
    LLMError,
    LLMSchemaError,
    ProviderCapabilities,
    ToolGeneration,
)
from app.providers.llm.openai_chat import (
    _ToolCallAccumulator,
    _pooled_client,
    _raise_for_status,
    _retryable_provider_error,
    _tool_call_from_object,
)
from app.providers.llm.trace import trace_finish, trace_start

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)
DeltaCallback = Callable[[str], Awaitable[None] | None]

# CNY per million tokens. Peak = 09:00-12:00 / 14:00-18:00 Asia/Shanghai
# on weekdays except configured public holidays. The accounting CNY/USD rate
# is deployment configuration rather than a fabricated market quote.
PRICING_CNY = {
    "deepseek-flash": {
        "peak": {"cache_hit": 0.04, "cache_miss": 2.0, "completion": 8.0},
        "offpeak": {"cache_hit": 0.02, "cache_miss": 1.0, "completion": 4.0},
    },
    "deepseek-v4-pro": {
        "peak": {"cache_hit": 0.30, "cache_miss": 9.0, "completion": 27.0},
        "offpeak": {"cache_hit": 0.15, "cache_miss": 4.5, "completion": 13.5},
    },
}
_MODEL_ALIASES = {"deepseek-v4-flash-vision-exp": "deepseek-flash"}
_VISION_MODELS = {"deepseek-flash", "deepseek-v4-flash-vision-exp"}


def _canonical_model(model: str) -> str:
    return _MODEL_ALIASES.get(model, model)


def _offpeak_dates() -> set[str]:
    return {
        value.strip()
        for value in settings.deepseek_offpeak_dates.split(",")
        if value.strip()
    }


def _is_peak(at: datetime) -> bool:
    local = at.astimezone(ZoneInfo("Asia/Shanghai"))
    if local.weekday() >= 5 or local.date().isoformat() in _offpeak_dates():
        return False
    current = local.time()
    return (
        datetime_time(9) <= current < datetime_time(12)
        or datetime_time(14) <= current < datetime_time(18)
    )


def _cny_to_usd(value: float) -> float:
    return value / settings.deepseek_cny_per_usd


def price_tokens(
    prompt_tokens: int, completion_tokens: int, *, model: str | None = None
) -> float:
    """Conservative estimate: peak, uncached input plus generated output."""
    key = _canonical_model(model or settings.deepseek_model)
    line = PRICING_CNY.get(key)
    if line is None:
        raise ValueError(f"no DeepSeek PRICING line for chat model {key!r}")
    rates = line["peak"]
    return _cny_to_usd(
        prompt_tokens / 1_000_000 * rates["cache_miss"]
        + completion_tokens / 1_000_000 * rates["completion"]
    )


def price_usage(usage: dict, *, model: str, at: datetime) -> float:
    """Price one actual response, retaining cache and peak/offpeak semantics."""
    key = _canonical_model(model)
    line = PRICING_CNY.get(key)
    if line is None:
        raise ValueError(f"no DeepSeek PRICING line for chat model {key!r}")
    rates = line["peak" if _is_peak(at) else "offpeak"]
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    hit_raw = usage.get("prompt_cache_hit_tokens")
    if hit_raw is None:
        hit_raw = usage.get("cached_tokens")
    if hit_raw is None:
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            hit_raw = details.get("cached_tokens")
    hit = int(hit_raw or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or max(prompt - hit, 0))
    return _cny_to_usd(
        hit / 1_000_000 * rates["cache_hit"]
        + miss / 1_000_000 * rates["cache_miss"]
        + completion / 1_000_000 * rates["completion"]
    )


def _log_usage(usage: dict | None) -> None:
    if usage:
        logger.info(
            "deepseek_usage",
            **{key: value for key, value in usage.items() if "token" in key or "cache" in key},
        )


async def _record_usage(usage: dict | None, *, model: str, started_at: datetime) -> None:
    if not usage:
        return
    from app.metering import record_usage

    _log_usage(usage)
    try:
        cost_usd = price_usage(usage, model=model, at=started_at)
    except Exception as exc:  # metering must never invalidate a completed generation
        logger.warning("deepseek_usage_price_failed", error=str(exc))
        cost_usd = None
    await record_usage(
        usage,
        provider="deepseek",
        model=model,
        cost_usd=cost_usd,
    )


def _clean_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _validated_json(response_model: type[T], raw: str, finish_reason: str | None) -> T:
    if finish_reason == "length":
        raise LLMSchemaError("DeepSeek JSON output was truncated (finish_reason=length)")
    content = _clean_json(raw)
    if not content:
        raise LLMSchemaError("DeepSeek returned empty JSON output")
    try:
        return response_model.model_validate_json(content)
    except ValidationError as exc:
        logger.error(
            "deepseek_json_validation_failed",
            error=str(exc),
            raw_content=content[:1000],
        )
        raise LLMSchemaError(
            f"Failed to validate response: {exc}\nRaw: {content[:500]}"
        ) from exc


def _project_messages(messages: list[dict]) -> list[dict]:
    """Project tool-result images into a following user evidence message.

    DeepSeek Chat Completions accepts images in user messages, not tool or
    assistant messages. A contiguous tool-result group stays contiguous; all
    of its images follow the complete group in one user message.
    """
    projected: list[dict] = []
    pending_evidence: list[dict] = []

    def flush_evidence() -> None:
        nonlocal pending_evidence
        if pending_evidence:
            projected.append({"role": "user", "content": pending_evidence})
            pending_evidence = []

    for message in messages:
        content = message.get("content")
        if message.get("role") != "tool" or not isinstance(content, list):
            flush_evidence()
            projected.append(message)
            continue
        has_images = any(isinstance(part, dict) and part.get("type") == "image_url" for part in content)
        if not has_images:
            projected.append(message)
            continue
        tool_text: list[str] = []
        evidence_started = False
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":
                evidence_started = True
                pending_evidence.append(part)
            elif part.get("type") == "text":
                if evidence_started:
                    pending_evidence.append(part)
                else:
                    tool_text.append(part.get("text") or "")
            else:
                # Non-image media remains in the tool text channel as an
                # explicit fact rather than being silently discarded.
                tool_text.append(f"Unsupported tool media part: {part.get('type')}")
        projected.append({**message, "content": "\n".join(tool_text)})
    flush_evidence()
    return projected


class DeepSeekClient:
    """DeepSeek Chat Completions client with the shared Agent call contract."""

    provider = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model
        self.capabilities = ProviderCapabilities(
            supports_native_tools=True,
            supports_json_schema=False,
            reasoning_dialect="reasoning_content",
            supports_constrained_decoding=False,
            prompt_cache="passive_prefix",
            supports_image_input=self.model in _VISION_MODELS,
            supports_video_input=False,
            supports_tool_result_images=False,
            understands_video_audio=False,
        )

    def _require_key(self) -> None:
        if not self.api_key:
            raise LLMError("DEEPSEEK_API_KEY not configured")

    def _payload(
        self,
        messages: list[dict],
        *,
        temperature: float,
        thinking: bool,
        stream: bool,
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        json_output: bool = False,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _project_messages(messages),
            "temperature": temperature,
            "max_tokens": settings.deepseek_max_output_tokens,
            "thinking": {"type": "enabled" if thinking else "disabled"},
            "stream": stream,
        }
        if thinking:
            payload["reasoning_effort"] = settings.deepseek_reasoning_effort
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        if tools is not None:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        return payload

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_retryable_provider_error),
        reraise=True,
    )
    async def generate(
        self,
        messages: list[dict],
        response_model: type[T],
        temperature: float = 0.3,
        thinking: bool = False,
        timeout_s: float | None = None,
    ) -> T:
        self._require_key()
        started_at = datetime.now(UTC)
        payload = self._payload(
            messages,
            temperature=temperature,
            thinking=thinking,
            stream=False,
            json_output=True,
        )
        call_id = trace_start(payload, "generate", provider="deepseek", model=self.model)
        t0 = time.monotonic()
        try:
            async with _pooled_client() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                    **({"timeout": timeout_s} if timeout_s is not None else {}),
                )
                _raise_for_status(response, provider="DeepSeek")
                data = response.json()
        except Exception as exc:
            trace_finish(call_id, provider="deepseek", model=self.model, error=exc)
            raise
        trace_finish(call_id, provider="deepseek", model=self.model, response=data)
        await _record_usage(data.get("usage"), model=self.model, started_at=started_at)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        logger.info(
            "llm_response",
            provider=self.provider,
            model=self.model,
            stream=False,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        return _validated_json(
            response_model, message.get("content") or "", choice.get("finish_reason")
        )

    async def generate_stream(
        self,
        messages: list[dict],
        response_model: type[T],
        temperature: float = 0.3,
        thinking: bool = False,
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
        timeout_s: float | None = None,
    ) -> T:
        self._require_key()
        started_at = datetime.now(UTC)
        payload = self._payload(
            messages,
            temperature=temperature,
            thinking=thinking,
            stream=True,
            json_output=True,
        )
        call_id = trace_start(payload, "generate_stream", provider="deepseek", model=self.model)
        t0 = time.monotonic()
        emitted = False
        last_exc: Exception | None = None
        accumulated = ""
        finish_reason: str | None = None
        usage: dict | None = None
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(min(2**attempt, 10))
            accumulated = ""
            finish_reason = None
            usage = None
            try:
                async with _pooled_client() as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                        **({"timeout": timeout_s} if timeout_s is not None else {}),
                    ) as response:
                        if response.status_code != 200:
                            await response.aread()
                            _raise_for_status(response, provider="DeepSeek")
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if raw == "[DONE]":
                                break
                            if not raw:
                                continue
                            chunk = json.loads(raw)
                            if chunk.get("usage"):
                                usage = chunk["usage"]
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            if choice.get("finish_reason"):
                                finish_reason = choice["finish_reason"]
                            delta = choice.get("delta") or {}
                            reasoning = delta.get("reasoning_content")
                            if reasoning and on_reasoning is not None:
                                result = on_reasoning(reasoning)
                                if result is not None:
                                    await result
                            fragment = delta.get("content")
                            if fragment:
                                accumulated += fragment
                                if on_delta is not None:
                                    emitted = True
                                    result = on_delta(fragment)
                                    if result is not None:
                                        await result
            except (httpx.TransportError, LLMError, json.JSONDecodeError) as exc:
                last_exc = exc
                if emitted or attempt == 2 or not _retryable_provider_error(exc):
                    trace_finish(call_id, provider="deepseek", model=self.model, error=exc)
                    if isinstance(exc, LLMError):
                        raise
                    raise LLMError(str(exc), user_key="provider_unreachable") from exc
                continue
            break
        else:
            if isinstance(last_exc, LLMError):
                raise last_exc
            raise LLMError(str(last_exc), user_key="provider_unreachable")
        trace_finish(
            call_id,
            provider="deepseek", model=self.model,
            response={"content": accumulated, "finish_reason": finish_reason, "usage": usage},
        )
        await _record_usage(usage, model=self.model, started_at=started_at)
        logger.info(
            "llm_response",
            provider=self.provider,
            model=self.model,
            stream=True,
            duration_ms=int((time.monotonic() - t0) * 1000),
            content_chars=len(accumulated),
        )
        return _validated_json(response_model, accumulated, finish_reason)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_retryable_provider_error),
        reraise=True,
    )
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.3,
        thinking: bool | None = None,
        tool_choice: str | dict = "auto",
    ) -> ToolGeneration:
        self._require_key()
        started_at = datetime.now(UTC)
        # DeepSeek requires complete historical reasoning_content on tool
        # continuations. The shared loop intentionally does not retain or
        # replay reasoning, so this wire is explicitly non-thinking.
        payload = self._payload(
            messages,
            temperature=temperature,
            thinking=False,
            stream=False,
            tools=tools,
            tool_choice=tool_choice,
        )
        call_id = trace_start(payload, "generate_with_tools", provider="deepseek", model=self.model)
        try:
            async with _pooled_client() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                _raise_for_status(response, provider="DeepSeek")
                data = response.json()
        except Exception as exc:
            trace_finish(call_id, provider="deepseek", model=self.model, error=exc)
            raise
        trace_finish(call_id, provider="deepseek", model=self.model, response=data)
        await _record_usage(data.get("usage"), model=self.model, started_at=started_at)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")
        content = (message.get("content") or "").strip()
        calls = [
            _tool_call_from_object(tool_call, finish_reason)
            for tool_call in message.get("tool_calls") or []
        ]
        if not content and not calls:
            logger.warning(
                "deepseek_empty_generation",
                finish_reason=finish_reason,
                usage=data.get("usage"),
            )
        return ToolGeneration(content=content, tool_calls=calls)

    async def generate_stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.3,
        thinking: bool | None = None,
        tool_choice: str | dict = "auto",
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
        on_tool_call: DeltaCallback | None = None,
    ) -> ToolGeneration:
        self._require_key()
        started_at = datetime.now(UTC)
        payload = self._payload(
            messages,
            temperature=temperature,
            thinking=False,
            stream=True,
            tools=tools,
            tool_choice=tool_choice,
        )
        call_id = trace_start(payload, "generate_stream_with_tools", provider="deepseek", model=self.model)
        t0 = time.monotonic()
        emitted = False
        last_exc: Exception | None = None
        accumulated = ""
        usage: dict | None = None
        finish_reason: str | None = None
        accumulator = _ToolCallAccumulator()
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(min(2**attempt, 10))
            accumulated = ""
            usage = None
            finish_reason = None
            accumulator = _ToolCallAccumulator()
            try:
                async with _pooled_client() as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            await response.aread()
                            _raise_for_status(response, provider="DeepSeek")
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            chunk = json.loads(raw)
                            if chunk.get("usage"):
                                usage = chunk["usage"]
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            if choice.get("finish_reason"):
                                finish_reason = choice["finish_reason"]
                            delta = choice.get("delta") or {}
                            reasoning = delta.get("reasoning_content")
                            if reasoning and on_reasoning is not None:
                                result = on_reasoning(reasoning)
                                if result is not None:
                                    await result
                            fragment = delta.get("content")
                            if fragment:
                                accumulated += fragment
                                if on_delta is not None:
                                    emitted = True
                                    result = on_delta(fragment)
                                    if result is not None:
                                        await result
                            tool_deltas = delta.get("tool_calls") or []
                            if tool_deltas:
                                names = accumulator.feed(tool_deltas)
                                if names and on_tool_call is not None:
                                    for name in names:
                                        emitted = True
                                        result = on_tool_call(name)
                                        if result is not None:
                                            await result
            except (httpx.TransportError, LLMError, json.JSONDecodeError) as exc:
                last_exc = exc
                if emitted or attempt == 2 or not _retryable_provider_error(exc):
                    trace_finish(call_id, provider="deepseek", model=self.model, error=exc)
                    if isinstance(exc, LLMError):
                        raise
                    raise LLMError(str(exc), user_key="provider_unreachable") from exc
                continue
            break
        else:
            if isinstance(last_exc, LLMError):
                raise last_exc
            raise LLMError(str(last_exc), user_key="provider_unreachable")
        trace_finish(
            call_id,
            provider="deepseek", model=self.model,
            response={
                "content": accumulated,
                "tool_calls": accumulator.raw_calls(),
                "finish_reason": finish_reason,
                "usage": usage,
            },
        )
        # Keep malformed raw arguments in the trace before parsing can fail.
        calls = accumulator.finish(finish_reason)
        await _record_usage(usage, model=self.model, started_at=started_at)
        logger.info(
            "llm_response",
            provider=self.provider,
            model=self.model,
            stream=True,
            tool_calls=True,
            duration_ms=int((time.monotonic() - t0) * 1000),
            content_chars=len(accumulated),
        )
        content = accumulated.strip()
        if not content and not calls:
            logger.warning(
                "deepseek_empty_generation",
                finish_reason=finish_reason,
                usage=usage,
            )
        return ToolGeneration(content=content, tool_calls=calls)


deepseek_client = DeepSeekClient()
