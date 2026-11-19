"""Current video design agents and their bounded declarations."""

from __future__ import annotations

from app.agents.base import Agent, AssembleResult
from app.agents.tool_loop import ChatTool
import json

from app.editing.source_selection import SourceSelectionAnswer, SourceSentence
from app.editing.director import (
    AlignedNarrationDirection,
    ComponentVideoDirection,
    GeneratedImageDirection,
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
        description="列出绑定包的精简镜头索引、序列及模板标识。只读；大型索引可筛选或分页。",
        params_model=ListSkillShotsArgs,
        terminal=False,
    ),
    ChatTool(
        name="read_skill_reference",
        description="从绑定包中的 SKILL.md、镜头卡、序列或模板读取一个限定范围的片段。",
        params_model=ReadSkillReferenceArgs,
        terminal=False,
    ),
    ChatTool(
        name="read_skill_demo",
        description="从选定的演示源码或已声明的 demos/lib 依赖读取一个限定片段。源码只供参考，不执行。",
        params_model=ReadSkillDemoArgs,
        terminal=False,
    ),
    ChatTool(
        name="get_skill_preview",
        description="读取所选镜头的真实预览。默认优先使用声明的时间线图片，其次为 MP4。没有预览时如实返回 available=false。",
        params_model=GetSkillPreviewArgs,
        terminal=False,
    ),
]

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
        "你是动态图形设计师，负责有独立时序的文字块、视觉层级与原生图形。所有屏幕文案都逐字照录，不编造事实。只输出有效 JSON。"
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
        "你是动态图形导演，根据 READY 状态的旁白对齐结果创作。选择真实存在的句子和逐字原文片段。音频及各词的时间由系统负责。只输出有效 JSON。"
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
        "你是视频合成师，只使用已固定的真实录像。选取有依据的源片段，准确填写原生标题和字幕。结构、布局、渲染和音乐由系统负责。只输出有效 JSON。"
    ),
    temperature=0.4,
    assemble=_assemble_mixed,
    stream=True,
    timeout_s=300,
    read_tools=SKILL_READ_TOOLS,
)


def _assemble_source_selection(
    query: str, sentences: tuple[SourceSentence, ...]
) -> AssembleResult:
    payload = [sentence.model_dump(mode="json") for sentence in sentences]
    return {"query": query, "sentences_json": json.dumps(payload, ensure_ascii=False)}, []


source_selector: Agent[SourceSelectionAnswer] = Agent(
    name="source_selector",
    prompt="video/source_selection.j2",
    schema=SourceSelectionAnswer,
    system="只返回结构化的连续句子选段结果。",
    temperature=0.0,
    assemble=_assemble_source_selection,
    timeout_s=120,
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
        "你是动态图形程序员。按用户的动态画面要求编写原创、确定性的 draw-2d 程序，不用预设名或伪代码代替实现。只输出有效 JSON。"
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
        "你负责创作程序化画面。按用户要求编写原创、确定性的多文件 Remotion 场景，内容适合时用连贯镜头组织全片。不要用预设替代实现，不使用未声明的导入、任意依赖或伪代码。只输出有效 JSON。"
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
        "你是图像美术指导。撰写一条精确的文生图请求来生成没有文字的背景。原生文案保留为独立可编辑对象。只输出有效 JSON。"
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
        "你是视频内容审阅员。新的视觉发现只能依据本次所附的实际解码帧。音频事实使用确定性媒体检查，先前审阅的事实只说明历史检查范围。只输出有效 JSON。"
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
    "source_selector",
    "video_reviewer",
]
