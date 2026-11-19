"""MiniMax M3 client."""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import MINIMAX_FLASH_MODEL, settings
from app.providers.llm.base import (
    LLMError,
    LLMSchemaError,
    ProviderCapabilities,
    ToolGeneration,
)
from app.providers.llm.openai_chat import (
    _parse_tool_arguments as _parse_tool_arguments,
    _ToolCallAccumulator,
    _payload_chars,
    _pooled_client,
    _raise_for_status,
    _retryable_provider_error,
    _tool_call_from_object,
)
from app.providers.llm.trace import trace_finish, trace_start

logger = structlog.get_logger()


def _log_usage(usage: dict | None) -> None:
    """Prefix-cache observability (MiniMax prompt-caching doc: verify hits in
    ``usage``) — one line per call, ledger-independent (``metering`` no-ops
    on request-path calls, exactly the chat-path majority)."""
    if not usage:
        return
    logger.info(
        "minimax_usage",
        **{k: v for k, v in usage.items() if "token" in k or "cache" in k},
    )


T = TypeVar("T", bound=BaseModel)

# ---- vendor price list (N-34 对称面) -----------------------------------------
#
# Nodes declare QUANTITIES (estimate.units / metered actuals); the Model layer
# declares PRICES — this table is the only place MiniMax pricing knowledge
# lives, and both sides of the calibration loop read it: the quotation fold
# (estimate units × price) and the metering ledger's fixed_cost (actual units
# × price). ADR-077 判词④: the table is keyed BY MODEL/SKU (provider 分家 =
# 模块本身——一厂一文件、价目表随 client；model 分家 = 表键), so another
# provider's or SKU's lines never collide in one flat dict. List prices in
# USD, snapshot 2026-08 (platform.minimax.io pay-go): adjust to contract
# pricing when it differs.
PRICING = {
    MINIMAX_FLASH_MODEL: {"prompt_per_mtoken": 0.15, "completion_per_mtoken": 0.60},
    # minimax-m3 standard tier (≤512K input): $0.30 / $1.20 per 1M tokens.
    "minimax-m3": {
        "prompt_per_mtoken": 0.30,
        "completion_per_mtoken": 1.20,
    },
    # speech-2.6-hd (providers/voice._TTS_MODEL): $100 per 1M characters.
    "speech-2.6-hd": {
        "tts_per_mchar": 100.0,
    },
    # Rapid voice clone: $1.50 per voice, billed on its first T2A use.
    "voice-clone": {
        "voice_clone_per_use": 1.50,
    },
    # image-01: $0.0035 per image.
    "image-01": {
        "image_per_piece": 0.0035,
    },
    # music-2.6-free SKU in use: $0 (music-2.6 list price is $0.15/track).
    "music-2.6-free": {
        "music_per_piece": 0.0,
    },
    # render_seconds carries no vendor price (own infrastructure) — the unit
    # is metered for quota/calibration, priced at zero here.
}


def price_units(units: dict[str, float]) -> float:
    """Money value (USD) of a mechanical-units record against ``PRICING``.
    Each unit kind prices against the SKU line that meters it — unit 种类 →
    model 价目行是该 SKU 的固定归属（TTS chars 永远按 speech 行计价）.

    ``video_seconds`` is the own-infra video-spec SKU with a menu price. The
    estimate fold and metering ledger read the same ``video.usd_per_second``
    operating parameter through the warmed config cache."""
    from app.platform.configs import peek_config  # deferred: provider layer stays a leaf

    return (
        units.get("tts_chars", 0.0) / 1_000_000 * PRICING["speech-2.6-hd"]["tts_per_mchar"]
        + units.get("voice_clones", 0.0) * PRICING["voice-clone"]["voice_clone_per_use"]
        + units.get("images", 0.0) * PRICING["image-01"]["image_per_piece"]
        + units.get("music_pieces", 0.0) * PRICING["music-2.6-free"]["music_per_piece"]
        + units.get("video_seconds", 0.0) * peek_config("video.usd_per_second")
    )


def price_tokens(
    prompt_tokens: int, completion_tokens: int, *, model: str | None = None
) -> float:
    """Money value (USD) of a token-usage record against ``PRICING`` —
    defaults to the configured chat model (``settings.minimax_model``); a
    second provider's tokens price against ITS client's table, never this
    one (provider+model 分家). An unknown model is a deployment-config error
    — it raises, never silently prices at zero (fabricated pricing is worse
    than a loud failure)."""
    key = model or settings.minimax_model
    line = PRICING.get(key)
    if line is None:
        raise ValueError(f"no PRICING line for chat model {key!r}")
    return (
        prompt_tokens / 1_000_000 * line["prompt_per_mtoken"]
        + completion_tokens / 1_000_000 * line["completion_per_mtoken"]
    )


@dataclass(frozen=True)
class MusicGenerationResult:
    """Result of a MiniMax music_generation call.

    ``audio_url`` is set when ``output_format="url"`` (expires after ~24h, so the
    caller must download the bytes immediately); ``audio_hex`` is set when
    ``output_format="hex"``. ``duration_ms`` / ``size_bytes`` come from
    ``extra_info`` when the API populates them.
    """

    audio_url: str | None
    audio_hex: str | None
    duration_ms: int | None
    size_bytes: int | None
    sample_rate: int | None
    generation_id: str | None  # MiniMax trace_id
    status: int  # 1 = in progress, 2 = completed

# M3 may emit a <think>...</think> reasoning preamble before the JSON payload,
# even with thinking disabled. Strip it so JSON parsing doesn't choke on it.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class _ThinkStripper:
    """Stateful streaming filter swallowing ONE leading ``<think>…</think>``
    block from the delta channel (``_clean_json``'s regex is the same rule
    for assembled text).

    Provider dialects are normalized HERE at the Model seam (2026-09-11 用户
    拍板): upstream consumers (prose extractor / ask watcher / plan beat)
    only ever see clean payload text, so a second provider's reasoning
    dialect gets normalized in ITS client, never upstream. Tag-split safe: a
    tag may straddle chunk boundaries — while undecided we hold back a tail
    shorter than the tag. Once real payload starts, the filter is a pure
    pass-through (a mid-stream ``<think>`` is literal text — the same
    start-only rule as ``_clean_json``).
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._state = "prelude"  # prelude | in_think | payload

    def feed(self, fragment: str) -> str:
        """Consume a raw content fragment; return the clean portion (maybe '')."""
        if self._state == "payload":
            return fragment
        self._buf += fragment
        if self._state == "in_think":
            idx = self._buf.find(self._CLOSE)
            if idx == -1:
                # Keep only a tail that could be a split close tag; the rest
                # is swallowed reasoning (bounded memory on long thinks).
                self._buf = self._buf[-(len(self._CLOSE) - 1):]
                return ""
            self._state = "payload"
            out, self._buf = self._buf[idx + len(self._CLOSE):], ""
            return out
        # prelude: decide think vs payload (leading whitespace tolerated).
        stripped = self._buf.lstrip()
        if not stripped or self._OPEN.startswith(stripped):
            return ""  # undecided — keep buffering
        if stripped.startswith(self._OPEN):
            self._state = "in_think"
            self._buf = stripped[len(self._OPEN):]
            return self.feed("")  # the close tag may already be buffered
        self._state = "payload"
        out, self._buf = self._buf, ""
        return out


_MINIMAX_SENTINEL = "]<]minimax[>["
_MINIMAX_TOOL_MARKERS = ("<tool_call", "</tool_call", "<invoke", "</invoke")


def _minimax_tool_markup_start(text: str) -> int:
    """Locate only MiniMax's native-tool dialect, never arbitrary '<' text."""
    starts = [text.find(marker) for marker in _MINIMAX_TOOL_MARKERS]
    starts = [index for index in starts if index >= 0]
    sentinel = text.find(_MINIMAX_SENTINEL)
    if sentinel >= 0:
        starts.append(sentinel)
    return min(starts, default=-1)


def _strip_minimax_tool_markup(text: str) -> str:
    """Remove a malformed provider tool tail while preserving ordinary prose."""
    start = _minimax_tool_markup_start(text)
    return text if start < 0 else text[:start]


class _MiniMaxToolMarkupStripper:
    """Tag-split-safe streaming twin of ``_strip_minimax_tool_markup``.

    Once the provider's tool dialect starts, its payload is not assistant
    prose. Short suffixes that may become a marker stay buffered until the
    next fragment proves them literal text or provider markup.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._discarding = False

    def feed(self, fragment: str) -> str:
        if self._discarding:
            return ""
        self._buf += fragment
        start = _minimax_tool_markup_start(self._buf)
        if start >= 0:
            out = self._buf[:start]
            self._buf = ""
            self._discarding = True
            return out
        markers = (*_MINIMAX_TOOL_MARKERS, _MINIMAX_SENTINEL)
        held = 0
        for size in range(1, min(len(self._buf), max(map(len, markers))) + 1):
            suffix = self._buf[-size:]
            if any(marker.startswith(suffix) and len(suffix) < len(marker) for marker in markers):
                held = size
        if held:
            out, self._buf = self._buf[:-held], self._buf[-held:]
            return out
        out, self._buf = self._buf, ""
        return out

    def finish(self) -> str:
        if self._discarding:
            return ""
        tail, self._buf = self._buf, ""
        if len(tail) > 1 and any(
            marker.startswith(tail)
            for marker in (*_MINIMAX_TOOL_MARKERS, _MINIMAX_SENTINEL)
        ):
            return ""
        return tail


def _generation_options(temperature: float, thinking: bool | None) -> dict:
    if settings.minimax_model.casefold() == MINIMAX_FLASH_MODEL.casefold():
        # Flash always thinks. Fast routing requests use its lowest supported effort.
        options = {"thinking": {"type": "adaptive"}}
        if thinking is False:
            options["reasoning_effort"] = "low"
        return options
    options = {"temperature": temperature}
    if thinking is not None:
        options["thinking"] = {"type": "adaptive" if thinking else "disabled"}
    return options


class MiniMaxClient:
    """MiniMax M3 API client with structured output."""

    provider = "minimax"

    @property
    def model(self) -> str:
        return settings.minimax_model

    # Capability declaration (ADR-077 判词④): M3's ONLY schema-following
    # channel is native tool_calls (spike 2026-09-11/12 — json_schema is
    # ignored outright). Every chat call sends reasoning_split=True (官方强烈
    # 建议): thinking arrives as separate reasoning_content deltas /
    # reasoning_details blocks instead of a <think>…</think> preamble inside
    # content (wire-verified 2026-09-27: with the flag on, content arrives
    # clean and BOTH reasoning fields ride along — reasoning_content stays a
    # plain string fragment, so the liveness extraction is unchanged).
    # _ThinkStripper (ADR-066) stays as the fallback for any path where the
    # flag is not honored — upstream layers never see either dialect.
    capabilities = ProviderCapabilities(
        supports_native_tools=True,
        supports_json_schema=False,
        reasoning_dialect="reasoning_split",
        supports_constrained_decoding=False,
        # 被动前缀缓存（tools→system→history 顺序，≥512 token 起效，缓存价
        # ~2 折）——逐字节重放实测 17221/17222 命中（2026-09-27 取证）；
        # 逐 pod 独立 + 负载自适应 TTL，冷 pod 首调必 miss，故配启动预热。
        prompt_cache="passive_prefix",
        supports_image_input=True,
        supports_video_input=True,
        supports_tool_result_images=True,
        # 视频输入 = 抽帧看画面、音轨丢弃（spike 2026-10-05：原视频直发，
        # 模型自答「无法处理音频」）——语音主导素材走 ASR 文本进上下文。
        understands_video_audio=False,
    )

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or settings.minimax_api_key
        self.base_url = base_url or settings.minimax_base_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Transport/HTTP hiccups only — a schema rejection is NEVER re-rolled
        # blind here; the harness answers it with one feedback repair round.
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
        """Generate structured output from MiniMax M3.

        ``timeout_s`` overrides the pool's 300s read default for agents whose
        prompt/generation is known to run long (the film storyboarder's
        20k-token call — 2026-10-15 取证: 成功样本 142s, 已两次撞穿 120s);
        None inherits the pool timeout."""
        if not self.api_key:
            raise LLMError("MINIMAX_API_KEY not configured")

        payload: dict = {
            "model": settings.minimax_model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            **_generation_options(temperature, thinking),
            # Thinking out of the content channel (see capabilities note).
            "reasoning_split": True,
        }

        trace_id = trace_start(payload, "generate", provider="minimax", model=settings.minimax_model)
        t0 = time.monotonic()
        logger.info(
            "llm_request",
            model=settings.minimax_model,
            stream=False,
            payload_chars=_payload_chars(messages),
            timeout_s=timeout_s,
        )
        try:
            async with _pooled_client() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    **({"timeout": timeout_s} if timeout_s is not None else {}),
                )
                _raise_for_status(response)
                data = response.json()
                trace_finish(trace_id, provider="minimax", model=settings.minimax_model, response=data)
        except Exception as e:
            trace_finish(trace_id, provider="minimax", model=settings.minimax_model, error=e)
            logger.warning(
                "llm_request_failed",
                model=settings.minimax_model,
                stream=False,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )
            raise
        logger.info(
            "llm_response",
            model=settings.minimax_model,
            stream=False,
            duration_ms=int((time.monotonic() - t0) * 1000),
            content_chars=len(data["choices"][0]["message"].get("content") or ""),
        )

        # ADR-025 metering: report usage to the bound workflow step (no-op when
        # unbound). Done before validation — tokens were consumed either way.
        from app.metering import record_usage

        _log_usage(data.get("usage"))
        await record_usage(data.get("usage"), provider=self.provider, model=self.model)

        raw_content = data["choices"][0]["message"]["content"]
        content = self._clean_json(raw_content)

        try:
            return response_model.model_validate_json(content)
        except ValidationError as e:
            logger.error(
                "minimax_json_validation_failed",
                error=str(e),
                raw_content=content[:1000],
            )
            raise LLMSchemaError(f"Failed to validate response: {e}\nRaw: {content[:500]}")

    async def generate_stream(
        self,
        messages: list[dict],
        response_model: type[T],
        temperature: float = 0.3,
        thinking: bool = False,
        on_delta: Callable[[str], Awaitable[None] | None] | None = None,
        on_reasoning: Callable[[str], Awaitable[None] | None] | None = None,
        timeout_s: float | None = None,
    ) -> T:
        """Streaming variant of ``generate`` — same single call, but the
        raw response text is also forwarded chunk-by-chunk via ``on_delta`` as
        it arrives (chat SSE 流式: the service layer extracts prose previews
        from these fragments; the returned value is still the fully validated
        ``response_model``, parsed from the accumulated text exactly like
        ``generate``).

        The ``on_delta`` channel is dialect-clean: a leading ``<think>``
        preamble is stripped at this seam (``_ThinkStripper``) before any
        fragment reaches a consumer — upstream layers never learn the
        provider's reasoning dialect.

        Spike-verified (2026-08-04): MiniMax streams fine with
        ``response_format: json_object``; ``stream_options.include_usage``
        delivers usage in a final choice-less chunk so ADR-025 metering is
        preserved.

        Retry policy differs from ``generate``: tenacity can't express "retry
        only until a side effect", so the loop is manual — retries happen
        only before the first ``on_delta`` call (a retry after emitted deltas
        would double-send preview text downstream); mid-stream failures raise
        LLMError and callers take the same fallback paths as today.
        Because the stripper swallows the think preamble, ``emitted`` flips
        only when clean PAYLOAD text was actually delivered — a retry after a
        think-only prefix is safe and allowed.
        """
        if not self.api_key:
            raise LLMError("MINIMAX_API_KEY not configured")

        payload: dict = {
            "model": settings.minimax_model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            **_generation_options(temperature, thinking),
            "stream": True,
            "stream_options": {"include_usage": True},
            "reasoning_split": True,
        }

        trace_id = trace_start(payload, "generate_stream", provider="minimax", model=settings.minimax_model)
        t0 = time.monotonic()
        logger.info(
            "llm_request",
            model=settings.minimax_model,
            stream=True,
            payload_chars=_payload_chars(messages),
        )
        first_chunk_ms: int | None = None
        emitted = False
        last_exc: Exception | None = None
        for attempt in range(3):
            if attempt:
                logger.warning(
                    "llm_stream_retry",
                    model=settings.minimax_model,
                    attempt=attempt,
                    error=f"{type(last_exc).__name__}: {str(last_exc)[:200]}" if last_exc else None,
                )
                await asyncio.sleep(min(2**attempt, 10))
            accumulated = ""
            reasoning_chars = 0
            last_progress_at = time.monotonic()
            stripper = _ThinkStripper()
            usage: dict | None = None
            try:
                async with _pooled_client() as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        **({"timeout": timeout_s} if timeout_s is not None else {}),
                    ) as response:
                        if response.status_code != 200:
                            await response.aread()
                            _raise_for_status(response)
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            if not data:
                                continue
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                logger.warning("minimax_stream_bad_frame", frame=data[:200])
                                continue
                            if first_chunk_ms is None:
                                first_chunk_ms = int((time.monotonic() - t0) * 1000)
                                logger.info(
                                    "llm_first_chunk",
                                    model=settings.minimax_model,
                                    stream=True,
                                    first_chunk_ms=first_chunk_ms,
                                )
                            if chunk.get("usage"):
                                usage = chunk["usage"]
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            reasoning = delta.get("reasoning_content")
                            reasoning_chars += len(reasoning or "")
                            now = time.monotonic()
                            if now - last_progress_at >= 15:
                                logger.info(
                                    "llm_stream_progress", model=settings.minimax_model,
                                    attempt=attempt, duration_ms=int((now - t0) * 1000),
                                    content_chars=len(accumulated), reasoning_chars=reasoning_chars,
                                )
                                last_progress_at = now
                            if reasoning and on_reasoning is not None:
                                # Reasoning fragments are a liveness signal
                                # only — never accumulated into the JSON
                                # payload, never shown to the user.
                                result = on_reasoning(reasoning)
                                if result is not None:
                                    await result
                            fragment = delta.get("content")
                            if not fragment:
                                continue
                            accumulated += fragment
                            if on_delta is not None:
                                clean = stripper.feed(fragment)
                                if not clean:
                                    # Still inside (or undecided on) the think
                                    # preamble — nothing reaches consumers, so
                                    # the retry guard stays unburned.
                                    continue
                                emitted = True
                                result = on_delta(clean)
                                if result is not None:
                                    await result
            except (httpx.TransportError, LLMError) as exc:
                last_exc = exc
                if (
                    emitted
                    or attempt == 2
                    or not _retryable_provider_error(exc)
                ):
                    trace_finish(trace_id, provider="minimax", model=settings.minimax_model, error=exc)
                    logger.warning(
                        "llm_request_failed",
                        model=settings.minimax_model,
                        stream=True,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        first_chunk_ms=first_chunk_ms,
                        error=f"{type(exc).__name__}: {str(exc)[:200]}",
                    )
                    if isinstance(exc, LLMError):
                        # Already keyed — re-raise intact, never re-wrap.
                        raise
                    raise LLMError(
                        str(exc), user_key="provider_unreachable"
                    ) from exc
                continue
            break
        else:
            if isinstance(last_exc, LLMError):
                raise last_exc
            raise LLMError(str(last_exc), user_key="provider_unreachable")

        trace_finish(trace_id, provider="minimax", model=settings.minimax_model, response={"content": accumulated, "usage": usage})
        logger.info(
            "llm_response",
            model=settings.minimax_model,
            stream=True,
            duration_ms=int((time.monotonic() - t0) * 1000),
            first_chunk_ms=first_chunk_ms,
            content_chars=len(accumulated),
        )

        # ADR-025 metering (same contract as ``generate``: report before
        # validation — tokens were consumed either way).
        from app.metering import record_usage

        _log_usage(usage)
        await record_usage(usage, provider=self.provider, model=self.model)

        content = self._clean_json(accumulated)
        try:
            return response_model.model_validate_json(content)
        except ValidationError as e:
            logger.error(
                "minimax_json_validation_failed",
                error=str(e),
                raw_content=content[:1000],
            )
            raise LLMSchemaError(f"Failed to validate response: {e}\nRaw: {content[:500]}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Same discipline as ``generate``: transport/HTTP hiccups only — a
        # schema rejection (truncated/malformed tool arguments) is NEVER
        # re-rolled blind here; the harness answers it with one feedback
        # repair round.
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
        """Tier-1 wire format (ADR-077 判词④), non-streaming: the provider
        picks from the declared ``tools`` (OpenAI-compatible function specs);
        prose rides the content channel, calls ride tool_call arguments.

        No ``response_format``: with tools declared, content is free prose,
        not the JSON payload — the call contract moves to the arguments
        channel (层只换线格式，永不动调用契约: the caller validates the
        returned arguments against the same contract it holds today).
        """
        if not self.api_key:
            raise LLMError("MINIMAX_API_KEY not configured")

        payload: dict = {
            "model": settings.minimax_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            **_generation_options(temperature, thinking),
            "reasoning_split": True,
        }

        trace_id = trace_start(payload, "generate_with_tools", provider="minimax", model=settings.minimax_model)
        try:
            async with _pooled_client() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                _raise_for_status(response)
                data = response.json()
                trace_finish(trace_id, provider="minimax", model=settings.minimax_model, response=data)
        except (httpx.HTTPError, LLMError, json.JSONDecodeError) as exc:
            trace_finish(trace_id, provider="minimax", model=settings.minimax_model, error=exc)
            logger.warning(
                "llm_request_failed",
                model=settings.minimax_model,
                stream=False,
                tool_calls=True,
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )
            raise

        # ADR-025 metering: report usage to the bound workflow step (no-op when
        # unbound). Done before validation — tokens were consumed either way.
        from app.metering import record_usage

        _log_usage(data.get("usage"))
        await record_usage(data.get("usage"), provider=self.provider, model=self.model)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")
        # Prose is the content channel here — strip the reasoning dialect
        # (start-only rule, same as _clean_json) but never markdown fences.
        content = _strip_minimax_tool_markup(
            _THINK_BLOCK.sub("", message.get("content") or "").strip()
        )
        calls = [
            _tool_call_from_object(tc, finish_reason)
            for tc in message.get("tool_calls") or []
        ]
        if not content and not calls:
            # 空响应信标 (same law as the streaming twin): words and calls
            # BOTH empty — log finish_reason/usage so the next occurrence is
            # evidence, not speculation.
            logger.warning(
                "minimax_empty_generation",
                finish_reason=finish_reason,
                usage=data.get("usage"),
            )
        return ToolGeneration(content=content, tool_calls=calls, assistant_message=message)

    async def generate_stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.3,
        thinking: bool | None = None,
        tool_choice: str | dict = "auto",
        on_delta: Callable[[str], Awaitable[None] | None] | None = None,
        on_reasoning: Callable[[str], Awaitable[None] | None] | None = None,
        on_tool_call: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> ToolGeneration:
        """Streaming twin of ``generate_with_tools`` (Tier-1 流式, spike 已验
        形态 2026-09-11/12): prose fragments flow through ``on_delta``
        dialect-clean (the think preamble is stripped at this seam — same
        contract as ``generate_stream``); ``on_tool_call`` fires once per
        call when its name first arrives — the phase-frame seam (T2's
        「正在查曲库…」inspecting frames ride it); argument fragments
        accumulate silently and surface only in the returned
        ``ToolGeneration``.

        Retry law mirrors ``generate_stream``: manual, and only before the
        first downstream emission — ``emitted`` flips on the first delivered
        prose fragment OR the first delivered tool-call name (a shown phase
        frame is a side effect too). Truncation (finish_reason=tool_calls but
        arguments hit EOF) raises ``LLMSchemaError`` after the stream drains —
        prose already delivered stays delivered, and the harness's repair
        round answers the call channel, exactly like a schema rejection
        on the Tier-0 wire.
        """
        if not self.api_key:
            raise LLMError("MINIMAX_API_KEY not configured")

        payload: dict = {
            "model": settings.minimax_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            **_generation_options(temperature, thinking),
            "stream": True,
            "stream_options": {"include_usage": True},
            "reasoning_split": True,
        }

        trace_id = trace_start(payload, "generate_stream_with_tools", provider="minimax", model=settings.minimax_model)
        t0 = time.monotonic()
        logger.info(
            "llm_request",
            model=settings.minimax_model,
            stream=True,
            tool_calls=True,
            payload_chars=_payload_chars(messages),
        )
        first_chunk_ms: int | None = None
        emitted = False
        last_exc: Exception | None = None
        for attempt in range(3):
            if attempt:
                logger.warning(
                    "llm_stream_retry",
                    model=settings.minimax_model,
                    attempt=attempt,
                    error=f"{type(last_exc).__name__}: {str(last_exc)[:200]}" if last_exc else None,
                )
                await asyncio.sleep(min(2**attempt, 10))
            accumulated = ""
            reasoning_parts = []
            assistant_message = {"role": "assistant"}
            stripper = _ThinkStripper()
            tool_markup_stripper = _MiniMaxToolMarkupStripper()
            accumulator = _ToolCallAccumulator()
            usage: dict | None = None
            finish_reason: str | None = None
            try:
                async with _pooled_client() as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            await response.aread()
                            _raise_for_status(response)
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                logger.warning("minimax_stream_bad_frame", frame=data[:200])
                                continue
                            if first_chunk_ms is None:
                                first_chunk_ms = int((time.monotonic() - t0) * 1000)
                                logger.info(
                                    "llm_first_chunk",
                                    model=settings.minimax_model,
                                    stream=True,
                                    first_chunk_ms=first_chunk_ms,
                                )
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
                            if "reasoning_content" in delta and reasoning is not None:
                                reasoning_parts.append(reasoning)
                            if delta.get("name"):
                                assistant_message["name"] = delta["name"]
                            if "content" in delta:
                                assistant_message["content"] = delta["content"]
                            if reasoning and on_reasoning is not None:
                                # UI receives a liveness callback, not chat prose.
                                result = on_reasoning(reasoning)
                                if result is not None:
                                    await result
                            # Content and tool_calls are INDEPENDENT channels
                            # in one chunk — never an elif: a tool-calls chunk
                            # commonly carries no content at all.
                            fragment = delta.get("content")
                            if fragment:
                                accumulated += fragment
                                if on_delta is not None:
                                    clean = tool_markup_stripper.feed(stripper.feed(fragment))
                                    if clean:
                                        emitted = True
                                        result = on_delta(clean)
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
            except (httpx.TransportError, LLMError) as exc:
                last_exc = exc
                if (
                    emitted
                    or attempt == 2
                    or not _retryable_provider_error(exc)
                ):
                    trace_finish(trace_id, provider="minimax", model=settings.minimax_model, error=exc)
                    logger.warning(
                        "llm_request_failed",
                        model=settings.minimax_model,
                        stream=True,
                        tool_calls=True,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        first_chunk_ms=first_chunk_ms,
                        error=f"{type(exc).__name__}: {str(exc)[:200]}",
                    )
                    if isinstance(exc, LLMError):
                        # Already keyed — re-raise intact, never re-wrap.
                        raise
                    raise LLMError(
                        str(exc), user_key="provider_unreachable"
                    ) from exc
                continue
            break
        else:
            if isinstance(last_exc, LLMError):
                raise last_exc
            raise LLMError(str(last_exc), user_key="provider_unreachable")

        clean_tail = tool_markup_stripper.finish()
        if clean_tail and on_delta is not None:
            result = on_delta(clean_tail)
            if result is not None:
                await result

        trace_finish(trace_id, provider="minimax", model=settings.minimax_model, response={
            "content": accumulated,
            "tool_calls": accumulator.raw_calls(),
            "finish_reason": finish_reason,
            "usage": usage,
        })
        logger.info(
            "llm_response",
            model=settings.minimax_model,
            stream=True,
            tool_calls=True,
            duration_ms=int((time.monotonic() - t0) * 1000),
            first_chunk_ms=first_chunk_ms,
            content_chars=len(accumulated),
        )

        # ADR-025 metering (same contract as ``generate``: report before
        # validation — tokens were consumed either way).
        from app.metering import record_usage

        _log_usage(usage)
        await record_usage(usage, provider=self.provider, model=self.model)

        content = _strip_minimax_tool_markup(
            _THINK_BLOCK.sub("", accumulated).strip()
        )
        # The truncation signature raises HERE (after the stream drained):
        # schema class, so the harness's repair round answers it with
        # feedback — never a blind client-side re-roll. Raw arguments were
        # already persisted before this parse.
        calls = accumulator.finish(finish_reason)
        if not content and not calls:
            # 空响应信标: the turn's words and calls BOTH came back empty —
            # log the raw finish_reason/usage so the next occurrence is
            # evidence, not speculation (the harness retries this shape as
            # empty_bare_reply; this beacon tells provider flake apart from
            # a seam bug).
            logger.warning(
                "minimax_empty_generation",
                finish_reason=finish_reason,
                usage=usage,
            )
        if accumulated:
            assistant_message["content"] = accumulated
        if reasoning_parts:
            assistant_message["reasoning_content"] = "".join(reasoning_parts)
        if calls:
            assistant_message["tool_calls"] = [
                {"id": item["id"], "type": "function",
                 "function": {"name": item["name"], "arguments": item["arguments"]}}
                for item in accumulator.raw_calls()
            ]
        return ToolGeneration(content=content, tool_calls=calls, assistant_message=assistant_message)

    def _clean_json(self, raw: str) -> str:
        """Strip reasoning blocks and markdown fences from JSON payload."""
        cleaned = _THINK_BLOCK.sub("", raw).strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        return cleaned

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        response_format: str = "base64",
    ) -> list[str]:
        """Generate one image-01 request with a single non-idempotent POST.

        MiniMax documents no idempotency key or prior-result lookup. Transport
        or response-decoding failures therefore have an unconfirmed outcome:
        surface that fact instead of blindly submitting another paid request.
        Returns base64 strings or URLs depending on ``response_format``.
        """
        if not self.api_key:
            raise LLMError("MINIMAX_API_KEY not configured")

        payload = {
            "model": "image-01",
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": 1,
            "response_format": response_format,
        }

        try:
            async with _pooled_client() as client:
                response = await client.post(
                    f"{self.base_url}/image_generation",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                _raise_for_status(response)
                data = response.json()
        except (httpx.RequestError, json.JSONDecodeError) as exc:
            logger.warning(
                "minimax_image_outcome_unknown",
                error=f"{type(exc).__name__}: {str(exc)[:200]}",
            )
            raise LLMError(
                "MiniMax image generation outcome is unconfirmed; "
                "the request was not retried",
                user_key="provider_image_outcome_unknown",
            ) from exc

        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") != 0:
            raise LLMError(
                f"MiniMax image generation failed: {base_resp.get('status_msg')}",
                user_key="provider_unavailable",
            )

        if response_format == "base64":
            return data.get("data", {}).get("image_base64", []) or []
        return data.get("data", {}).get("image_urls", []) or []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def generate_music(
        self,
        prompt: str,
        *,
        model: str = "music-2.6-free",
        is_instrumental: bool = True,
        output_format: str = "url",
        audio_format: str = "mp3",
    ) -> MusicGenerationResult:
        """Generate a music piece with MiniMax (``/v1/music_generation``).

        The native API is synchronous: the request blocks until the audio is
        ready (``data.status == 2``). ``output_format="url"`` returns a
        short-lived (~24h) URL the caller must download immediately; ``"hex"``
        returns the audio bytes inline. Defaults to ``url`` so bytes stay out
        of the JSON response, then ``services/music_generation`` downloads and
        persists them under ``assets/music/``.
        """
        if not self.api_key:
            raise LLMError("MINIMAX_API_KEY not configured")

        payload: dict = {
            "model": model,
            "prompt": prompt,
            "is_instrumental": is_instrumental,
            "output_format": output_format,
            "audio_setting": {"format": audio_format},
        }

        async with _pooled_client() as client:
            response = await client.post(
                f"{self.base_url}/music_generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
            _raise_for_status(response)
            data = response.json()

        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") != 0:
            raise LLMError(
                f"MiniMax music generation failed: {base_resp.get('status_msg')}",
                user_key="provider_unavailable",
            )

        inner = data.get("data") or {}
        extra = data.get("extra_info") or {}
        status = int(inner.get("status", 0))
        if status != 2:
            raise LLMError(
                f"MiniMax music generation did not complete (status={status})",
                user_key="provider_unavailable",
            )

        audio = inner.get("audio")
        return MusicGenerationResult(
            audio_url=audio if output_format == "url" else None,
            audio_hex=audio if output_format == "hex" else None,
            duration_ms=extra.get("music_duration"),
            size_bytes=extra.get("music_size"),
            sample_rate=extra.get("music_sample_rate"),
            generation_id=data.get("trace_id"),
            status=status,
        )


# Module-level singleton for callers that don't need a custom client.
minimax_client = MiniMaxClient()
