"""MiniMax M3 client."""

import re
from typing import TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

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

    def _clean_json(self, text: str) -> str:
        """Clean markdown code blocks and <think> preambles from a JSON response."""
        text = _THINK_BLOCK.sub("", text).strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        # If any prose still precedes the JSON (e.g. an unterminated think
        # block), fall back to the first balanced {...} / [...] span.
        if text and text[0] not in "{[":
            start = min(
                (i for i in (text.find("{"), text.find("[")) if i != -1),
                default=-1,
            )
            if start != -1:
                text = text[start:]
        return text.strip()


minimax_client = MiniMaxClient()
