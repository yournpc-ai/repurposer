"""Shared-crew registry (N-30/N-41): the agents every tool may draw on.

``director_understand`` / ``director_plan`` (the director's two steps),
``persona`` (style extraction), ``translator`` (caption-line translation —
the dub tool reuses it). Tool-private declarations live in each tool
package's ``agents.py`` (clip writer, the four copy writers, reviser).
Every declaration self-registers into ``agents/base.py``'s ``AGENTS`` on
construction (ADR-039 P2 full collection); the registry door
(``app/tools/__init__.py``) imports every package, and the startup
self-check validates node→agent references against it.
"""

from typing import Any

import structlog

from app.providers.llm.minimax import MiniMaxError
from app.models.schemas import (
    CaptionTranslation,
    ExtractedPersonaMemory,
    GenerationContext,
    MaterialUnderstanding,
    MediaInput,
    Storyboard,
)

from app.agents.base import Agent, trim_texts

logger = structlog.get_logger()


def _assemble_understand(
    asset_texts: list[str],
    asset_media: list[MediaInput] | None = None,
):
    """Director step 1 inputs — deliberately NO persona/tone/instruction:
    the understanding is material-scoped and reused across runs (asset-hash
    invalidation), so per-request values would poison reuse (purity is
    signature-enforced: there is no persona parameter to pass)."""
    if not asset_texts and not asset_media:
        raise MiniMaxError("No source texts or media provided for understanding")
    media = asset_media or []
    trimmed = trim_texts(asset_texts)
    if not trimmed and not media:
        raise MiniMaxError("No usable text or media found")
    return {"asset_texts": trimmed, "asset_media": media}, media


director_understand: Agent[MaterialUnderstanding] = Agent(
    name="director_understand",
    prompt="director_understand.j2",
    schema=MaterialUnderstanding,
    system=(
        "You are a senior content strategist. You analyze source "
        "material and output a faithful, self-contained material "
        "understanding as valid JSON, with no extra commentary."
    ),
    temperature=0.3,
    assemble=_assemble_understand,
    media_text_fallback=True,
)


def _assemble_plan(
    understanding: MaterialUnderstanding,
    context: GenerationContext,
    task_book: dict[str, Any],
    count_defaults_text: str,
):
    """Director step 2 inputs — the self-sufficiency contract: only the
    understanding, the shared context, and the task book; never the raw
    sources. ``count_defaults_text`` is the registry-derived per-type count
    defaults line (N-32), supplied by the caller — the harness never imports
    the graph layer."""
    return (
        {
            "understanding": understanding.model_dump(),
            "context": context.model_dump(),
            "task_book": task_book,
            "count_defaults_text": count_defaults_text,
        },
        [],
    )


director_plan: Agent[Storyboard] = Agent(
    name="director_plan",
    prompt="director_plan.j2",
    schema=Storyboard,
    system=(
        "You are a senior content strategist. You assign content "
        "work from a material understanding and output a storyboard "
        "as valid JSON, with no extra commentary."
    ),
    temperature=0.4,
    assemble=_assemble_plan,
)


def _assemble_persona(
    persona_name: str,
    persona_title: str | None,
    language: str,
    asset_texts: list[str],
):
    if not asset_texts:
        raise MiniMaxError("No source texts provided for persona generation")
    return (
        {
            "persona_name": persona_name,
            "persona_title": persona_title,
            "language": language,
            "asset_texts": trim_texts(asset_texts),
        },
        [],
    )


persona: Agent[ExtractedPersonaMemory] = Agent(
    name="persona",
    prompt="persona.j2",
    schema=ExtractedPersonaMemory,
    system=(
        "You are a professional speaking-style analyst."
        "You only output valid JSON, with no additional commentary."
    ),
    temperature=0.3,
    assemble=_assemble_persona,
)


def _assemble_translator(
    lines: list[str],
    target_language: str,
    style_hint: str | None = None,
):
    return (
        {
            "lines": lines,
            "target_language": target_language,
            "style_hint": style_hint,
        },
        [],
    )


def _align_line_count(
    result: CaptionTranslation, ctx: dict[str, Any]
) -> CaptionTranslation:
    """Pad/truncate to the input's line count so the caller's 1:1 timing
    mapping stays valid (never raise on length drift); missing lines fall
    back to the source text."""
    lines = ctx["lines"]
    out = list(result.lines)
    if len(out) != len(lines):
        logger.warning(
            "caption_translation_count_mismatch",
            expected=len(lines),
            got=len(out),
        )
        if len(out) < len(lines):
            out += lines[len(out) :]
        else:
            out = out[: len(lines)]
    return result.model_copy(update={"lines": out})


translator: Agent[CaptionTranslation] = Agent(
    name="translator",
    prompt="caption_translate.j2",
    schema=CaptionTranslation,
    system=(
        "You are a professional subtitle translator. You only output "
        "valid JSON, with no additional explanation."
    ),
    temperature=0.3,
    assemble=_assemble_translator,
    postprocess=_align_line_count,
)
