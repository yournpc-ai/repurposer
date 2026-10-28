"""The video design chain's LLM crew (ADR-145 phase B).

Declarations only — the Agent funnel (app/agents/base.py) owns the call.
Schemas and slot resolution live in app/editing/director.py (pure, gate
6a); the orchestration that calls these lives in tools/video/design.py.

- ``video_director``: the launch-film website promo — creative slots +
  citations over the captured pages' manifest; the launch-film SKILL.md
  craft pack is woven at assembly (``packs``), never loaded at runtime.
- ``mg_director``: the no-skill motion-graphics design over user copy.
"""

from __future__ import annotations

from app.agents.base import Agent, AssembleResult
from app.editing.director import (
    GeneratedImageDirection,
    LaunchFilmDirection,
    MgDirection,
    MixedDirection,
    ProgramDirection,
)


def _assemble_launch(
    *,
    lines_text: str,
    views_text: str,
    focus: str | None,
    instruction: str | None,
    language: str | None,
    current: str | None,
    page_images: list | None = None,
) -> AssembleResult:
    return (
        {
            "lines_text": lines_text,
            "views_text": views_text,
            "focus": focus,
            "instruction": instruction,
            "language": language,
            "current": current,
        },
        list(page_images or []),
    )


video_director: Agent[LaunchFilmDirection] = Agent(
    name="video_director",
    prompt="video_director.j2",
    schema=LaunchFilmDirection,
    system=(
        "You are a film director for evidence-led website launch films. You "
        "answer ONLY the creative slots — the structure, timing, layout and "
        "camera numbers are the system's. Output valid JSON, no commentary."
    ),
    temperature=0.5,
    assemble=_assemble_launch,
    packs=["launch-film"],
    media_text_fallback=True,
    stream=True,
    timeout_s=300,
)


def _assemble_mg(
    *,
    text: str,
    focus: str | None,
    instruction: str | None,
    language: str | None,
    current: str | None,
    scene_count: int | None = None,
    target_seconds: float | None = None,
    narration: str | None = None,
) -> AssembleResult:
    return (
        {
            "text": text,
            "focus": focus,
            "instruction": instruction,
            "language": language,
            "current": current,
            "scene_count": scene_count,
            "target_seconds": target_seconds,
            "narration": narration,
        },
        [],
    )


mg_director: Agent[MgDirection] = Agent(
    name="mg_director",
    prompt="mg_director.j2",
    schema=MgDirection,
    system=(
        "You are a motion-graphics designer. You pace short text scenes over "
        "a solid field — every line on screen is exact copy, never invented "
        "facts. Output valid JSON, no commentary."
    ),
    temperature=0.5,
    assemble=_assemble_mg,
    stream=True,
    timeout_s=300,
)


def _assemble_mixed(
    *,
    materials_text: str,
    focus: str | None,
    instruction: str | None,
    language: str | None,
    current: str | None,
    target_seconds: float | None,
    repair_feedback: str | None = None,
) -> AssembleResult:
    return (
        {
            "materials_text": materials_text,
            "focus": focus,
            "instruction": instruction,
            "language": language,
            "current": current,
            "target_seconds": target_seconds,
            "repair_feedback": repair_feedback,
        },
        [],
    )


mixed_director: Agent[MixedDirection] = Agent(
    name="mixed_director",
    prompt="mixed_director.j2",
    schema=MixedDirection,
    system=(
        "You are a video compositor working only from frozen real recordings. "
        "Select an honest source window and write exact native title/caption "
        "slots. Structure, layout, rendering and music are the system's. "
        "Output valid JSON, no commentary."
    ),
    temperature=0.4,
    assemble=_assemble_mixed,
    stream=True,
    timeout_s=300,
)


def _assemble_visual_request(
    *,
    text: str,
    focus: str | None,
    instruction: str,
    language: str | None,
    target_seconds: float | None,
) -> AssembleResult:
    return (
        {
            "text": text,
            "focus": focus,
            "instruction": instruction,
            "language": language,
            "target_seconds": target_seconds,
        },
        [],
    )


program_director: Agent[ProgramDirection] = Agent(
    name="program_director",
    prompt="program_director.j2",
    schema=ProgramDirection,
    system=(
        "You are a creative graphics programmer. Author an original deterministic "
        "drawing-v1 visual program for the user's requested moving picture; never "
        "substitute a preset name or pseudocode. Output valid JSON, no commentary."
    ),
    temperature=0.6,
    assemble=_assemble_visual_request,
    stream=True,
    timeout_s=300,
)


image_director: Agent[GeneratedImageDirection] = Agent(
    name="image_director",
    prompt="image_director.j2",
    schema=GeneratedImageDirection,
    system=(
        "You are an image art director. Author one precise text-to-image request "
        "for a background with no lettering; native copy stays a separate editable "
        "object. Output valid JSON, no commentary."
    ),
    temperature=0.5,
    assemble=_assemble_visual_request,
    stream=True,
    timeout_s=300,
)


__all__ = ["image_director", "mg_director", "mixed_director", "program_director", "video_director"]
