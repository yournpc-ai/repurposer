"""Shared utilities and base class for MiniMax-based agents."""

from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.clients.minimax import MiniMaxClient
from app.models.schemas import ContentPlan, DerivativeType, MediaInput

logger = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

_MAX_CHARS_PER_TEXT = 150_000


def _find_derivative_plan(
    content_plan: ContentPlan,
    derivative_type: DerivativeType | str,
) -> dict:
    """Return the matching DerivativePlan as a dict, or an empty fallback."""
    target = (
        derivative_type.value
        if isinstance(derivative_type, DerivativeType)
        else derivative_type
    )
    for plan in content_plan.derivatives:
        if plan.derivative_type == target:
            return plan.model_dump()
    return {}


class MiniMaxAgentBase:
    """Base class for agents that call MiniMax M3 with Jinja prompts.

    Provides shared helpers for:
    - loading prompt templates
    - trimming long text inputs
    - building OpenAI-compatible multimodal user messages
    - falling back to text-only when multimodal input is rejected
    """

    jinja_env = _jinja_env

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    @staticmethod
    def _trim_texts(texts: list[str]) -> list[str]:
        """Return non-empty texts trimmed to a safe length."""
        return [
            t[:_MAX_CHARS_PER_TEXT]
            for t in texts
            if t and t.strip()
        ]

    @staticmethod
    def _build_user_message(
        user_prompt: str, media_inputs: list[MediaInput]
    ) -> dict[str, Any]:
        """Build a user message mixing text prompt and media content parts."""
        content: list[dict[str, Any]] = []
        for media in media_inputs:
            part_key = f"{media.type}_url"
            content.append({"type": part_key, part_key: {"url": media.data_url}})
            if media.caption:
                content.append({"type": "text", "text": media.caption})
        content.append({"type": "text", "text": user_prompt})
        return {"role": "user", "content": content}

    async def _generate_with_fallback(
        self,
        messages: list[dict[str, Any]],
        user_prompt: str,
        media_inputs: list[MediaInput],
        response_model: type,
        temperature: float,
    ) -> Any:
        """Call M3; if media input fails for any reason, retry with text only.

        Media inputs (video/image/slide data URLs) are brittle: providers may
        reject them due to size, format, or transient issues, and the resulting
        exceptions are not always easy to classify. When media inputs are
        present we always fall back to the text-only prompt so generation can
        still succeed from transcripts/extracted text. Failures without media
        inputs are re-raised immediately.
        """
        try:
            return await self.client.generate(
                messages=messages,
                response_model=response_model,
                temperature=temperature,
            )
        except Exception as first_error:  # noqa: BLE001
            if not media_inputs:
                raise
            logger.warning(
                "multimodal_failed_falling_back_to_text",
                error=str(first_error),
                error_type=type(first_error).__name__,
                media_count=len(media_inputs),
            )
            if not messages:
                raise
            text_only_messages: list[dict[str, Any]] = [
                messages[0],
                {"role": "user", "content": user_prompt},
            ]
            return await self.client.generate(
                messages=text_only_messages,
                response_model=response_model,
                temperature=temperature,
            )
