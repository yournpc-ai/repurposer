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
from app.agents.tool_loop import ChatTool
from app.editing.director import (
    AlignedNarrationDirection,
    ComponentVideoDirection,
    GeneratedImageDirection,
    LaunchFilmDirection,
    MgDirection,
    MixedDirection,
    ProgramDirection,
)
from app.skills.package_session import (
    GetSkillPreviewArgs,
    ListSkillShotsArgs,
    ReadSkillDemoArgs,
    ReadSkillReferenceArgs,
)
from app.tools.video.review import ContentReviewAnswer


SKILL_READ_TOOLS = [
    ChatTool(
        name="list_skill_shots",
        description="List the bound package's compact shot index, sequence and template identities. Read only; filter or page large indexes.",
        params_model=ListSkillShotsArgs,
        terminal=False,
    ),
    ChatTool(
        name="read_skill_reference",
        description="Read one bounded slice of SKILL.md, a shot card, sequence, or template inside the bound package.",
        params_model=ReadSkillReferenceArgs,
        terminal=False,
    ),
    ChatTool(
        name="read_skill_demo",
        description="Read one bounded slice of a selected demo source or declared demos/lib dependency. Source is reference only, never executable input.",
        params_model=ReadSkillDemoArgs,
        terminal=False,
    ),
    ChatTool(
        name="get_skill_preview",
        description="Read a selected shot's real preview, preferring its declared timeline image over MP4 by default; return an honest available=false when none exists.",
        params_model=GetSkillPreviewArgs,
        terminal=False,
    ),
]

def _assemble_launch(
    *,
    lines_text: str,
    capture_status_text: str,
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
            "capture_status_text": capture_status_text,
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
    prompt="video/website_director.j2",
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
    background: str | None = None,
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
            "background": background,
        },
        [],
    )


mg_director: Agent[MgDirection] = Agent(
    name="mg_director",
    prompt="video/mg_director.j2",
    schema=MgDirection,
    system=(
        "You are a motion-graphics designer. You choreograph independently timed text blocks, visual hierarchy and "
        "native graphics — every line on screen is exact copy, never invented "
        "facts. Output valid JSON, no commentary."
    ),
    temperature=0.5,
    assemble=_assemble_mg,
    stream=True,
    timeout_s=300,
    read_tools=SKILL_READ_TOOLS,
)
def _assemble_aligned_narration(
    *,
    alignment_json: str,
    focus: str | None,
    instruction: str | None,
    language: str | None,
    scene_count: int | None,
    background: str | None,
    component_bake_enabled: bool = False,
    repair_feedback: str | None = None,
) -> AssembleResult:
    return (
        {
            "alignment_json": alignment_json,
            "focus": focus,
            "instruction": instruction,
            "language": language,
            "scene_count": scene_count,
            "background": background,
            "component_bake_enabled": component_bake_enabled,
            "repair_feedback": repair_feedback,
        },
        [],
    )


aligned_narration_director: Agent[AlignedNarrationDirection] = Agent(
    name="aligned_narration_director",
    prompt="video/aligned_narration_director.j2",
    schema=AlignedNarrationDirection,
    system=(
        "You are a motion-graphics director working from a READY narration "
        "alignment. Select real sentences and exact source fragments; the "
        "system owns every audio and word time. Output valid JSON, no commentary."
    ),
    temperature=0.5,
    assemble=_assemble_aligned_narration,
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
    prompt="video/mixed_director.j2",
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
    read_tools=SKILL_READ_TOOLS,
)


def _assemble_visual_request(
    *,
    text: str,
    focus: str | None,
    instruction: str,
    language: str | None,
    target_seconds: float | None,
    narration: str | None = None,
    aspect: str | None = None,
    current: str | None = None,
    available_resources: list[dict] | None = None,
    repair_feedback: str | None = None,
) -> AssembleResult:
    return (
        {
            "text": text,
            "focus": focus,
            "instruction": instruction,
            "language": language,
            "target_seconds": target_seconds,
            "narration": narration,
            "aspect": aspect,
            "current": current,
            "available_resources": available_resources or [],
            "repair_feedback": repair_feedback,
        },
        [],
    )


program_director: Agent[ProgramDirection] = Agent(
    name="program_director",
    prompt="video/draw_2d_director.j2",
    schema=ProgramDirection,
    system=(
        "You are a creative graphics programmer. Author an original deterministic "
        "draw-2d visual program for the user's requested moving picture; never "
        "substitute a preset name or pseudocode. Output valid JSON, no commentary."
    ),
    temperature=0.6,
    assemble=_assemble_visual_request,
    stream=True,
    timeout_s=300,
    read_tools=SKILL_READ_TOOLS,
)


component_director: Agent[ComponentVideoDirection] = Agent(
    name="component_director",
    prompt="video/remotion_project_director.j2",
    schema=ComponentVideoDirection,
    system=(
        "You are a creative visual-program author. Write original deterministic "
        "multi-file Remotion scenes for the user's requested moving picture; organize "
        "a complete work into coherent shots when that fits the content. Never "
        "substitute a preset, undeclared imports, arbitrary dependencies or pseudocode. "
        "Output valid JSON, no commentary."
    ),
    temperature=0.6,
    assemble=_assemble_visual_request,
    stream=True,
    timeout_s=300,
    read_tools=SKILL_READ_TOOLS,
)


image_director: Agent[GeneratedImageDirection] = Agent(
    name="image_director",
    prompt="video/generated_image_director.j2",
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
    read_tools=SKILL_READ_TOOLS,
)


def _assemble_review(
    *,
    requirements: str,
    output_facts: str,
    storyboard: str,
    frame_facts: str,
    deterministic_checks: str,
    motion_review: str,
    previous_review_facts: str,
    frames: list | None = None,
) -> AssembleResult:
    return (
        {
            "requirements": requirements,
            "output_facts": output_facts,
            "storyboard": storyboard,
            "frame_facts": frame_facts,
            "deterministic_checks": deterministic_checks,
            "motion_review": motion_review,
            "previous_review_facts": previous_review_facts,
        },
        list(frames or []),
    )


video_reviewer: Agent[ContentReviewAnswer] = Agent(
    name="video_reviewer",
    prompt="video/reviewer.j2",
    schema=ContentReviewAnswer,
    system=(
        "You are a video content reviewer. Base new visual findings only on "
        "the actual decoded frames attached to the request; use the supplied "
        "deterministic media checks for audio facts, and treat earlier review "
        "facts as historical scope rather than new frames. Output valid JSON, "
        "no commentary."
    ),
    temperature=0.2,
    assemble=_assemble_review,
    # Never degrade to storyboard-only review and then claim pixels were seen.
    media_text_fallback=False,
    stream=True,
    timeout_s=300,
)


__all__ = [
    "aligned_narration_director",
    "component_director",
    "image_director",
    "mg_director",
    "mixed_director",
    "program_director",
    "video_director",
    "video_reviewer",
]
