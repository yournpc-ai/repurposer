"""Stills editor — the stills tool's private agent declarations (期 2 剪辑师).

``stills_editor`` plans one clip's beat plan (节拍方案) from the segment's
anchored narration slice + the backing visuals' anchors/labels; beyond the
单发可靠域 (≤15 拍 / ≤45s, 简报 §2.3) ``stills_editor_outline`` first lays
the global arc + resource assignment, then ``stills_editor`` runs per
section with explicit handoff state. The craft conventions ride the
``stills-editing-craft`` instruction pack (assembly-time injection only,
N-42 ⑦ 纪律).
"""

from typing import Any

from app.agents.base import Agent
from app.models.schemas import BeatOutline, BeatPlan


def _assemble_editor(
    span_transcript: str,
    images: list[dict[str, Any]],
    emphasis_hints: list[dict[str, Any]],
    span_seconds: float,
    target_beats: int,
    handoff: dict[str, Any] | None = None,
):
    """Editor inputs — request-scoped per clip, never persona (the skin owns
    caption style; the editor decides STRUCTURE only). ``handoff`` is the
    two-stage section call's explicit交接状态 (used visuals / last motion /
    emphasis history / span anchors); None = single pass over the clip."""
    return (
        {
            "span_transcript": span_transcript,
            "images": images,
            "emphasis_hints": emphasis_hints,
            "span_seconds": span_seconds,
            "target_beats": target_beats,
            "handoff": handoff,
        },
        [],
    )


stills_editor: Agent[BeatPlan] = Agent(
    name="stills_editor",
    prompt="stills_editor.j2",
    schema=BeatPlan,
    system=(
        "You are a senior short-form video editor cutting a photo-slideshow "
        "to a narration track. You output valid JSON only, with no extra "
        "commentary."
    ),
    temperature=0.3,
    assemble=_assemble_editor,
    packs=["stills-editing-craft"],
)


def _assemble_outline(
    span_transcript: str,
    images: list[dict[str, Any]],
    emphasis_hints: list[dict[str, Any]],
    span_seconds: float,
    target_beats: int,
):
    """大纲段 inputs — the same material view as the editor, minus handoff
    (the outline IS the first stage)."""
    return (
        {
            "span_transcript": span_transcript,
            "images": images,
            "emphasis_hints": emphasis_hints,
            "span_seconds": span_seconds,
            "target_beats": target_beats,
        },
        [],
    )


stills_editor_outline: Agent[BeatOutline] = Agent(
    name="stills_editor_outline",
    prompt="stills_editor_outline.j2",
    schema=BeatOutline,
    system=(
        "You are a senior short-form video editor outlining the narrative "
        "arc of a photo-slideshow before cutting it. You output valid JSON "
        "only, with no extra commentary."
    ),
    temperature=0.3,
    assemble=_assemble_outline,
    packs=["stills-editing-craft"],
)
