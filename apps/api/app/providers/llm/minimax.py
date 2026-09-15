"""MiniMax M3 client."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.providers.llm.base import (
    LLMError,
    LLMSchemaError,
    ProviderCapabilities,
    ToolCall,
    ToolGeneration,
)

logger = structlog.get_logger()

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
    model 价目行是该 SKU 的固定归属（TTS chars 永远按 speech 行计价）."""
    return (
        units.get("tts_chars", 0.0) / 1_000_000 * PRICING["speech-2.6-hd"]["tts_per_mchar"]
        + units.get("voice_clones", 0.0) * PRICING["voice-clone"]["voice_clone_per_use"]
        + units.get("images", 0.0) * PRICING["image-01"]["image_per_piece"]
        + units.get("music_pieces", 0.0) * PRICING["music-2.6-free"]["music_per_piece"]
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


def _parse_tool_arguments(name: str, raw: str, finish_reason: str | None) -> dict:
    """Parse one tool call's accumulated argument text (ONE parse law for the
    non-streaming object form and the streaming fragment form alike).

    Empty text is a legal zero-argument call (``{}``). Unparseable text is
    the TRUNCATION SIGNATURE (spike 2026-09-11/12: ~11% at the default token
    budget — finish_reason says tool_calls but the arguments hit EOF) or
    outright malformation; both are the schema class — ``LLMSchemaError`` so
    the harness's one feedback repair round carries the reason back to the
    model, never a blind re-roll, never a half-call.
    """
    if not raw:
        return {}
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMSchemaError(
            f"tool call {name!r} arguments did not parse "
            f"(finish_reason={finish_reason}; truncation or malformation): {e}\n"
            f"Raw: {raw[:500]}"
        ) from e
    if not isinstance(arguments, dict):
        raise LLMSchemaError(
            f"tool call {name!r} arguments are not a JSON object: {raw[:200]}"
        )
    return arguments


def _tool_call_from_object(tc: dict, finish_reason: str | None) -> ToolCall:
    """Parse one COMPLETE tool_calls[] object (the non-streaming form) —
    same law as ``_ToolCallAccumulator.finish``: a missing function name is
    wire-malformation (schema class), arguments go through the one parse law.
    """
    fn = tc.get("function") or {}
    name = fn.get("name") or ""
    if not name:
        raise LLMSchemaError(
            f"tool call {tc.get('id')!r} carried no function name "
            f"(finish_reason={finish_reason})"
        )
    return ToolCall(
        id=tc.get("id"),
        name=name,
        arguments=_parse_tool_arguments(name, fn.get("arguments") or "", finish_reason),
    )


@dataclass
class _AccCall:
    """One in-flight tool call inside ``_ToolCallAccumulator``."""

    id: str | None = None
    name: str | None = None
    arg_parts: list[str] = field(default_factory=list)


class _ToolCallAccumulator:
    """Pure assembler for the streaming tool_calls dialect (OpenAI-compatible):
    fragments arrive as ``delta.tool_calls[]`` entries keyed by ``index`` — a
    call's ``id`` / ``name`` arrive once (its first fragment), the arguments
    arrive as JSON text shards to concatenate. Pure state machine, no I/O:
    the parse law lives in ``_parse_tool_arguments`` and fires only at
    ``finish()``, so mid-stream fragments never raise.
    """

    def __init__(self) -> None:
        self._calls: dict[int, _AccCall] = {}

    def feed(self, deltas: list[dict]) -> list[str]:
        """Consume one chunk's ``delta.tool_calls``; return the names of calls
        whose name just became known — the ``on_tool_call`` hook's payload
        (the phase-frame seam: T2's 「正在查曲库…」inspecting frames ride it)."""
        named: list[str] = []
        for tc in deltas:
            idx = int(tc.get("index") or 0)
            call = self._calls.setdefault(idx, _AccCall())
            if tc.get("id"):
                call.id = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                if call.name is None:
                    named.append(fn["name"])
                call.name = fn["name"]
            fragment = fn.get("arguments")
            if fragment:
                call.arg_parts.append(fragment)
        return named

    def finish(self, finish_reason: str | None) -> list[ToolCall]:
        """Assemble the final calls in wire order (index ascending). A call
        whose name never arrived is wire-malformation — same schema class as
        an arguments parse failure."""
        calls: list[ToolCall] = []
        for idx in sorted(self._calls):
            call = self._calls[idx]
            if not call.name:
                raise LLMSchemaError(
                    f"tool call #{idx} never carried a function name "
                    f"(finish_reason={finish_reason})"
                )
            arguments = _parse_tool_arguments(
                call.name, "".join(call.arg_parts), finish_reason
            )
            calls.append(ToolCall(id=call.id, name=call.name, arguments=arguments))
        return calls


def _raise_for_status(
    response: httpx.Response, *, unavailable_key: str = "provider_unavailable"
) -> None:
    """``raise_for_status`` that speaks LLMError.

    Callers up the stack (intent agents, chat loop) all catch LLMError to
    degrade gracefully — a raw httpx.HTTPStatusError (402/429/5xx from the
    provider) would slip past every one of them and surface as a bare 500.
    Rate limiting gets its own user key (the honest "busy, try again" line);
    402 billing exhaustion gets its own ("out of quota" — the Claude-style
    exhausted line, 2026-08-14 裁定: a quota failure must SAY quota, never
    hide behind a generic unavailable line or a fabricated default answer);
    every other status reads as unavailable."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMError(
            f"MiniMax HTTP {exc.response.status_code}: "
            f"{exc.response.text[:300]}",
            user_key=(
                "provider_rate_limited"
                if exc.response.status_code == 429
                else "provider_quota_exhausted"
                if exc.response.status_code == 402
                else unavailable_key
            ),
        ) from exc


class MiniMaxClient:
    """MiniMax M3 API client with structured output."""

    # Capability declaration (ADR-077 判词④): M3's ONLY schema-following
    # channel is native tool_calls (spike 2026-09-11/12 — json_schema is
    # ignored outright); the reasoning dialect is the <think>…</think>
    # preamble plus reasoning_content deltas, normalized inside this client
    # (_ThinkStripper, ADR-066) — upstream layers never see it.
    capabilities = ProviderCapabilities(
        supports_native_tools=True,
        supports_json_schema=False,
        reasoning_dialect="think_block",
    )

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or settings.minimax_api_key
        self.base_url = base_url or settings.minimax_base_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Transport/HTTP hiccups only — a schema rejection is NEVER re-rolled
        # blind here; the harness answers it with one feedback repair round.
        retry=retry_if_not_exception_type(LLMSchemaError),
        reraise=True,
    )
    async def generate(
        self,
        messages: list[dict],
        response_model: type[T],
        temperature: float = 0.3,
        thinking: bool = False,
    ) -> T:
        """Generate structured output from MiniMax M3."""
        if not self.api_key:
            raise LLMError("MINIMAX_API_KEY not configured")

        payload: dict = {
            "model": settings.minimax_model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        if thinking:
            payload["thinking"] = True

        async with httpx.AsyncClient(timeout=120) as client:
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

        # ADR-025 metering: report usage to the bound workflow step (no-op when
        # unbound). Done before validation — tokens were consumed either way.
        from app.metering import record_usage

        await record_usage(data.get("usage"))

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
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if thinking:
            payload["thinking"] = True

        emitted = False
        last_exc: Exception | None = None
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(min(2**attempt, 10))
            accumulated = ""
            stripper = _ThinkStripper()
            usage: dict | None = None
            try:
                async with httpx.AsyncClient(timeout=120) as client:
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
                            if chunk.get("usage"):
                                usage = chunk["usage"]
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            reasoning = delta.get("reasoning_content")
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
                if emitted or attempt == 2:
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

        # ADR-025 metering (same contract as ``generate``: report before
        # validation — tokens were consumed either way).
        from app.metering import record_usage

        await record_usage(usage)

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
        retry=retry_if_not_exception_type(LLMSchemaError),
        reraise=True,
    )
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.3,
        thinking: bool = False,
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
            "temperature": temperature,
        }
        if thinking:
            payload["thinking"] = True

        async with httpx.AsyncClient(timeout=120) as client:
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

        # ADR-025 metering: report usage to the bound workflow step (no-op when
        # unbound). Done before validation — tokens were consumed either way.
        from app.metering import record_usage

        await record_usage(data.get("usage"))

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")
        # Prose is the content channel here — strip the reasoning dialect
        # (start-only rule, same as _clean_json) but never markdown fences.
        content = _THINK_BLOCK.sub("", message.get("content") or "").strip()
        calls = [
            _tool_call_from_object(tc, finish_reason)
            for tc in message.get("tool_calls") or []
        ]
        return ToolGeneration(content=content, tool_calls=calls)

    async def generate_stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.3,
        thinking: bool = False,
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
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if thinking:
            payload["thinking"] = True

        emitted = False
        last_exc: Exception | None = None
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(min(2**attempt, 10))
            accumulated = ""
            stripper = _ThinkStripper()
            accumulator = _ToolCallAccumulator()
            usage: dict | None = None
            finish_reason: str | None = None
            try:
                async with httpx.AsyncClient(timeout=120) as client:
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
                                # Reasoning fragments are a liveness signal
                                # only — never accumulated, never shown.
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
                                    clean = stripper.feed(fragment)
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
                if emitted or attempt == 2:
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

        # ADR-025 metering (same contract as ``generate``: report before
        # validation — tokens were consumed either way).
        from app.metering import record_usage

        await record_usage(usage)

        content = _THINK_BLOCK.sub("", accumulated).strip()
        # The truncation signature raises HERE (after the stream drained):
        # schema class, so the harness's repair round answers it with
        # feedback — never a blind client-side re-roll.
        calls = accumulator.finish(finish_reason)
        return ToolGeneration(content=content, tool_calls=calls)

    def _clean_json(self, raw: str) -> str:
        """Strip reasoning blocks and markdown fences from JSON payload."""
        cleaned = _THINK_BLOCK.sub("", raw).strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        return cleaned

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        response_format: str = "base64",
    ) -> list[str]:
        """Generate images with MiniMax image-01.

        Returns a list of base64 strings or URLs depending on ``response_format``.
        Defaults to ``base64`` so images can be persisted locally instead of
        relying on MiniMax's expiring URLs.
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

        async with httpx.AsyncClient(timeout=120) as client:
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

        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{self.base_url}/music_generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
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
