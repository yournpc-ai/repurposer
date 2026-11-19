"""Image generation mechanics (ADR-039 P1 split): MiniMax image-01 calls +
storage persistence for quote cards and clip covers.

Media generation rides the Model boundary's media method
(``minimax_client.generate_image``) — a mechanical provider call with no LLM
decision, same class as TTS. Failures degrade to None (a card without an
image), never raise.
"""

import base64
import time
from typing import Any
from uuid import UUID

import structlog

from app.providers.llm.base import LLMError
from app.providers.llm.minimax import minimax_client
from app.metering import record_media_usage
from app.models.tables import Project
from app.providers.storage import output_url, save_output

logger = structlog.get_logger()


def _quote_image_prompt(quote: str, attribution: str, event_name: str | None = None) -> str:
    """Build a visual prompt for MiniMax image-01 to illustrate a quote card."""
    base = (
        "为社交媒体设计一张简洁雅致的引言卡。使用柔和的渐变背景，将引语以清晰的字体居中突出展示。画面现代、专业、简洁，文字与背景对比鲜明。"
    )
    quote_ctx = f"引语：“{quote}”　署名：{attribution}"
    event_ctx = f" 活动背景：{event_name}。" if event_name else ""
    return base + quote_ctx + event_ctx


async def _save_minimax_image(
    project: Project,
    filename: str,
    prompt: str,
    aspect_ratio: str,
    *,
    log_context: dict[str, Any] | None = None,
) -> str | None:
    """Generate an image via MiniMax and save it to project storage.

    Returns the public URL or None on failure. Centralizes the repetitive
    generate_image / base64 decode / save_output / output_url flow so that
    quote cards, clip covers, and future image assets behave consistently.
    """
    log_ctx = log_context or {}
    try:
        images = await minimax_client.generate_image(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            response_format="base64",
        )
        if not images:
            return None
        await record_media_usage({"images": float(len(images))})
        image_bytes = base64.b64decode(images[0])
        relative_path = await save_output(
            project.id,
            project.user_id,
            filename,
            image_bytes,
        )
        return output_url(relative_path)
    except LLMError as e:
        logger.warning("minimax_image_failed", error=str(e), **log_ctx)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("minimax_image_unexpected_error", error=str(e), **log_ctx)
        return None


async def _save_quote_card_image(
    quote: str,
    attribution: str,
    output_id: UUID,
    project: Project,
) -> str | None:
    """Generate and save a quote-card PNG; return the public URL or None on failure.

    The filename carries a timestamp so a regeneration never overwrites the
    object a browser may have cached under the previous URL.
    """
    return await _save_minimax_image(
        project,
        f"quote_{output_id}-{int(time.time())}.png",
        _quote_image_prompt(quote, attribution, project.event_name),
        "1:1",
        log_context={"output_id": str(output_id), "kind": "quote_card"},
    )


async def generate_clip_cover_image(
    output_id: UUID,
    project: Project,
    *,
    topic: str | None = None,
    title: str | None = None,
) -> str | None:
    """Generate a vertical cover image for a clip output on demand.

    Returns the public URL or None on failure. The image is intentionally
    generated only when requested by the UI to avoid paying image-generation
    costs for every clip. (Public helper — the outputs router calls it.)
    """
    prompt = (
        "为知识短视频设计一张简洁雅致的竖版封面。构图干净，层次细腻，背景适合专业排版，不含文字、界面或多余元素。适合作为 9:16 视频缩略图。"
    )
    context_parts = []
    if topic:
        context_parts.append(f"主题：{topic}")
    if title:
        context_parts.append(f"标题：{title}")
    if context_parts:
        prompt += " ".join(context_parts)

    return await _save_minimax_image(
        project,
        f"cover_{output_id}-{int(time.time())}.png",
        prompt,
        "9:16",
        log_context={"output_id": str(output_id), "kind": "clip_cover"},
    )
