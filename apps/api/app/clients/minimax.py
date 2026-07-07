"""MiniMax M3 client."""

import re
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
            response.raise_for_status()
            data = response.json()

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
            response.raise_for_status()
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
            response.raise_for_status()
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
