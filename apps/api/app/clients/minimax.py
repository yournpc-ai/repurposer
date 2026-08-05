"""MiniMax M3 client."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


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


class MiniMaxError(Exception):
    """MiniMax API error."""

    pass


def _raise_for_status(response: httpx.Response) -> None:
    """``raise_for_status`` that speaks MiniMaxError.

    Callers up the stack (intent agents, chat loop) all catch MiniMaxError to
    degrade gracefully — a raw httpx.HTTPStatusError (402/429/5xx from the
    provider) would slip past every one of them and surface as a bare 500.
    """
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise MiniMaxError(
            f"MiniMax HTTP {exc.response.status_code}: "
            f"{exc.response.text[:300]}"
        ) from exc


class MiniMaxClient:
    """MiniMax M3 API client with structured output."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or settings.minimax_api_key
        self.base_url = base_url or settings.minimax_base_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
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
            raise MiniMaxError("MINIMAX_API_KEY not configured")

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
            raise MiniMaxError(f"Failed to validate response: {e}\nRaw: {content[:500]}")

    async def generate_stream(
        self,
        messages: list[dict],
        response_model: type[T],
        temperature: float = 0.3,
        thinking: bool = False,
        on_delta: Callable[[str], Awaitable[None] | None] | None = None,
        on_reasoning: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> T:
        """Streaming variant of ``generate`` — same single verdict call, but the
        raw response text is also forwarded chunk-by-chunk via ``on_delta`` as
        it arrives (chat SSE 流式: the service layer extracts prose previews
        from these fragments; the returned value is still the fully validated
        ``response_model``, parsed from the accumulated text exactly like
        ``generate``).

        Spike-verified (2026-08-04): MiniMax streams fine with
        ``response_format: json_object``; ``stream_options.include_usage``
        delivers usage in a final choice-less chunk so ADR-025 metering is
        preserved. A ``<think>`` preamble may precede the JSON — consumers of
        ``on_delta`` must tolerate it (the extractor keys off JSON depth).

        Retry policy differs from ``generate``: tenacity can't express "retry
        only until a side effect", so the loop is manual — retries happen
        only before the first ``on_delta`` call (a retry after emitted deltas
        would double-send preview text downstream); mid-stream failures raise
        MiniMaxError and callers take the same fallback paths as today.
        """
        if not self.api_key:
            raise MiniMaxError("MINIMAX_API_KEY not configured")

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
                                emitted = True
                                result = on_delta(fragment)
                                if result is not None:
                                    await result
            except (httpx.TransportError, MiniMaxError) as exc:
                last_exc = exc
                if emitted or attempt == 2:
                    raise MiniMaxError(str(exc)) from exc
                continue
            break
        else:
            raise MiniMaxError(str(last_exc))

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
            raise MiniMaxError(f"Failed to validate response: {e}\nRaw: {content[:500]}")

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
            raise MiniMaxError("MINIMAX_API_KEY not configured")

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
            raise MiniMaxError(
                f"MiniMax image generation failed: {base_resp.get('status_msg')}"
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
            raise MiniMaxError("MINIMAX_API_KEY not configured")

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
            raise MiniMaxError(
                f"MiniMax music generation failed: {base_resp.get('status_msg')}"
            )

        inner = data.get("data") or {}
        extra = data.get("extra_info") or {}
        status = int(inner.get("status", 0))
        if status != 2:
            raise MiniMaxError(
                f"MiniMax music generation did not complete (status={status})"
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
