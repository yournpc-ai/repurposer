"""Thin opt-in Gemini 2.5 Pro client for controlled multimodal comparison.

Speaks the shared OpenAI-compatible Chat Completions endpoint with native
image + video + audio understanding (`understands_video_audio=True`). Inactive
unless explicitly selected via `LLM_PROVIDER=gemini` with `GEMINI_API_KEY`.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.providers.llm.base import (
    DeltaCallback,
    LLMError,
    LLMSchemaError,
    ProviderCapabilities,
    ToolCall,
    ToolGeneration,
)
from app.providers.llm.openai_chat import (
    _ToolCallAccumulator,
    _iter_sse_json,
    _pooled_client,
    _raise_for_status,
)
from app.providers.llm.trace import record_llm_exchange

T = TypeVar("T", bound=BaseModel)

# Public Gemini 2.5 Pro list rates (USD per 1M tokens, <= 200k prompt context).
_PRICING_USD_PER_M: dict[str, tuple[float, float]] = {
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50),
}


def price_tokens(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    model: str | None = None,
) -> float:
    in_rate, out_rate = _PRICING_USD_PER_M.get(
        model or settings.gemini_model,
        _PRICING_USD_PER_M["gemini-2.5-pro"],
    )
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000.0


def _project_messages(messages: list[dict]) -> list[dict]:
    """Keep text + image/video media parts; fold media in tool messages into follow-up user evidence."""
    projected: list[dict] = []
    evidence_parts: list[dict] = []

    def flush_evidence() -> None:
        if not evidence_parts:
            return
        projected.append({"role": "user", "content": list(evidence_parts)})
        evidence_parts.clear()

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role != "tool" or not isinstance(content, list):
            if role != "tool":
                flush_evidence()
            projected.append(message)
            continue
        tool_text: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                tool_text.append(str(part.get("text") or ""))
            elif ptype in {"image_url", "video_url", "input_audio"}:
                evidence_parts.append(part)
            else:
                tool_text.append(f"Unsupported tool media part: {ptype}")
        projected.append({**message, "content": "\n".join(tool_text)})
    flush_evidence()
    return projected


class GeminiClient:
    """Thin isolated Gemini OpenAI-compatible client implementing LLMClient."""

    provider = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self.capabilities = ProviderCapabilities(
            supports_native_tools=True,
            supports_json_schema=True,
            reasoning_dialect="none",
            supports_constrained_decoding=False,
            prompt_cache="none",
            supports_image_input=True,
            supports_video_input=True,
            supports_tool_result_images=False,
            understands_video_audio=True,
        )

    @property
    def api_key(self) -> str:
        return self._api_key if self._api_key is not None else settings.gemini_api_key

    @property
    def base_url(self) -> str:
        return (self._base_url or settings.gemini_base_url).rstrip("/")

    @property
    def model(self) -> str:
        return self._model or settings.gemini_model

    def _require_key(self) -> None:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY not configured")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[dict],
        *,
        temperature: float,
        stream: bool,
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        json_output: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _project_messages(messages),
            "temperature": temperature,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        return payload

    async def generate(
        self,
        messages: list[dict],
        response_model: type[T],
        temperature: float = 0.3,
        thinking: bool = False,
        timeout_s: float | None = None,
    ) -> T:
        self._require_key()
        payload = self._payload(messages, temperature=temperature, stream=False, json_output=True)
        async with _pooled_client() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=timeout_s or 180.0,
            )
            _raise_for_status(resp, provider="Gemini")
            data = resp.json()
        raw = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        try:
            return response_model.model_validate_json(raw)
        except ValidationError as exc:
            raise LLMSchemaError(f"Gemini schema validation failed: {exc}") from exc

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
        return await self.generate(
            messages, response_model, temperature=temperature, thinking=thinking, timeout_s=timeout_s
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
        payload = self._payload(
            messages, temperature=temperature, stream=False, tools=tools, tool_choice=tool_choice
        )
        async with _pooled_client() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=240.0,
            )
            _raise_for_status(resp, provider="Gemini")
            data = resp.json()
        record_llm_exchange(self.provider, self.model, payload, data)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls: list[ToolCall] = []
        for raw_call in msg.get("tool_calls") or []:
            fn = raw_call.get("function") or {}
            arg_str = fn.get("arguments") or "{}"
            try:
                parsed = json.loads(arg_str) if isinstance(arg_str, str) else arg_str
                if not isinstance(parsed, dict):
                    raise ValueError("arguments must be a JSON object")
                calls.append(ToolCall(id=raw_call.get("id") or "", name=fn.get("name") or "", arguments=parsed))
            except (json.JSONDecodeError, ValueError) as exc:
                calls.append(ToolCall(
                    id=raw_call.get("id") or "",
                    name=fn.get("name") or "",
                    arguments={},
                    argument_error=str(exc),
                ))
        return ToolGeneration(
            content=msg.get("content") or "",
            tool_calls=calls,
            finish_reason=choice.get("finish_reason") or "stop",
            usage=data.get("usage") or {},
        )

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
        payload = self._payload(
            messages, temperature=temperature, stream=True, tools=tools, tool_choice=tool_choice
        )
        acc = _ToolCallAccumulator()
        text_parts: list[str] = []
        finish_reason = "stop"
        usage: dict[str, Any] = {}
        async with _pooled_client() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=httpx.Timeout(120, read=600),
            ) as resp:
                _raise_for_status(resp, provider="Gemini")
                async for event in _iter_sse_json(resp):
                    if event.get("usage"):
                        usage = event["usage"]
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
                    delta = choice.get("delta") or {}
                    content_piece = delta.get("content")
                    if content_piece:
                        text_parts.append(content_piece)
                        if on_delta is not None:
                            maybe = on_delta(content_piece)
                            if maybe is not None:
                                await maybe
                    for tc in delta.get("tool_calls") or []:
                        acc.feed(tc)
                        if on_tool_call is not None and (tc.get("function") or {}).get("name"):
                            maybe = on_tool_call(tc["function"]["name"])
                            if maybe is not None:
                                await maybe
        return ToolGeneration(
            content="".join(text_parts),
            tool_calls=acc.finish(),
            finish_reason=finish_reason,
            usage=usage,
        )


gemini_client = GeminiClient()
