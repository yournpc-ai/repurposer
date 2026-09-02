"""Shared-crew registry (N-30/N-41): the agents every tool may draw on.

``understand`` / ``plan`` (the plan prelude's two steps),
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

from app.agents.base import Agent, MAX_CHARS_PER_TEXT, trim_texts

logger = structlog.get_logger()


def _assemble_understand(
    source_blocks: list[dict[str, Any]],
    asset_media: list[MediaInput] | None = None,
    word_axis: list[dict[str, Any]] | None = None,
    image_refs: list[dict[str, str]] | None = None,
):
    """Understand node inputs — deliberately NO persona/tone/instruction:
    the understanding is material-scoped and reused across runs (asset-hash
    invalidation), so per-request values would poison reuse (purity is
    signature-enforced: there is no persona parameter to pass).

    ``source_blocks`` are the per-asset prompt texts (anchored cue lines when
    the asset carries an ASR word axis); ``word_axis``/``image_refs`` are the
    resolver's snapping inputs — they never render into the prompt itself
    beyond the ``has_time_axis`` / image-order facts.
    """
    if not source_blocks and not asset_media:
        raise MiniMaxError("No source texts or media provided for understanding")
    media = asset_media or []
    blocks = [
        {**b, "text": str(b.get("text") or "")[:MAX_CHARS_PER_TEXT]}
        for b in source_blocks
        if str(b.get("text") or "").strip()
    ]
    if not blocks and not media:
        raise MiniMaxError("No usable text or media found")
    return {
        "source_blocks": blocks,
        "asset_media": media,
        "has_time_axis": bool(word_axis),
        "image_refs": image_refs or [],
    }, media


def _resolve_understanding(
    result: MaterialUnderstanding, ctx: dict[str, Any]
) -> MaterialUnderstanding:
    """Snap the beat map's text anchors onto the ASR word axis (code half of
    理解层 v2 — the LLM never writes timestamps) and flag quotable-line
    self-containment."""
    from app.pipeline.beat_map import resolve_beat_map  # deferred: pipeline layer

    return resolve_beat_map(
        result, ctx.get("word_axis") or [], ctx.get("image_refs") or []
    )


understand: Agent[MaterialUnderstanding] = Agent(
    name="understand",
    prompt="understand.j2",
    schema=MaterialUnderstanding,
    system=(
        "You are a senior content strategist. You analyze source "
        "material and output a faithful, self-contained material "
        "understanding as valid JSON, with no extra commentary."
    ),
    temperature=0.3,
    assemble=_assemble_understand,
    postprocess=_resolve_understanding,
    media_text_fallback=True,
)


def _assemble_plan(
    understanding: MaterialUnderstanding,
    context: GenerationContext,
    task_book: dict[str, Any],
    count_defaults_text: str,
):
    """Plan node inputs — the self-sufficiency contract: only the
    understanding, the shared context, and the task book; never the raw
    sources. ``count_defaults_text`` is the registry-derived per-type count
    defaults line (N-32), supplied by the caller — the harness never imports
    the graph layer."""
    dump = understanding.model_dump()
    # The Quote Pool is the derived one-write view of quotable_lines (the
    # understanding stores the checked/anchored rows; planning reads texts).
    dump["quote_candidates"] = [q.text for q in understanding.quotable_lines]
    return (
        {
            "understanding": dump,
            "context": context.model_dump(),
            "task_book": task_book,
            "count_defaults_text": count_defaults_text,
        },
        [],
    )


plan: Agent[Storyboard] = Agent(
    name="plan",
    prompt="plan.j2",
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
