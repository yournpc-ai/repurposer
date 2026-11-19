"""Shared, bounded Director repairs for authored visual sources.

This module never writes a CompositionVersion. Callers execute the returned
candidate through their existing design/revision preflight and write door.
"""
from __future__ import annotations

import json
from typing import Any

from app.editing.director import (
    ComponentDirection,
    ComponentProjectAnswer,
    ComponentSceneDirection,
    ComponentVideoDirection,
    ProgramDirection,
)
from app.editing.schemas import ProgramOutput, RemotionProjectSource
from app.tools.video.agents import component_director, program_director


class AuthoringRepairError(ValueError):
    """A repair could not preserve the candidate's identity or scene structure."""


def component_project_payload(direction: ComponentProjectAnswer) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "entry": direction.entry,
        "composition_id": direction.composition_id,
        "files": [item.model_dump(mode="json") for item in direction.files],
        "props": direction.props,
        "props_schema": direction.props_schema,
        "resources": [item.model_dump(mode="json") for item in direction.resources],
    }


def as_component_video(
    answer: ComponentVideoDirection | ComponentDirection,
) -> ComponentVideoDirection:
    """Read tolerance for historical single-scene Director fixtures/callers."""
    if isinstance(answer, ComponentVideoDirection):
        return answer
    return ComponentVideoDirection(
        name=answer.name,
        language=answer.language,
        scenes=[ComponentSceneDirection.model_validate(answer.model_dump(mode="json"))],
    )


async def repair_component_video(
    current: ComponentVideoDirection,
    *,
    failed_scene: int | None,
    diagnostic: str,
    text: str,
    focus: str | None,
    instruction: str,
    language: str | None,
    target_seconds: float | None,
    aspect: str,
    narration: str | None,
    current_summary: str | None,
    available_resources: list[dict[str, Any]] | None = None,
    read_executor: Any = None,
) -> ComponentVideoDirection:
    """Repair one failed scene, retaining successful scenes byte-for-byte."""
    scene_source = (
        current.scenes[failed_scene].model_dump(mode="json")
        if failed_scene is not None else None
    )
    feedback = json.dumps({
        "failed_scene": failed_scene + 1 if failed_scene is not None else None,
        "diagnostic": diagnostic,
        "current_scene": scene_source,
        "current_direction": None if scene_source is not None else current.model_dump(mode="json"),
    }, ensure_ascii=False)
    answer = await component_director.call(
        text=text,
        focus=focus,
        instruction=instruction,
        language=language,
        target_seconds=target_seconds,
        aspect=aspect,
        narration=narration,
        current=current_summary,
        available_resources=available_resources or [],
        read_executor=read_executor,
        repair_feedback=feedback,
    )
    repaired = as_component_video(answer)
    if failed_scene is None:
        return repaired
    if len(repaired.scenes) != len(current.scenes):
        raise AuthoringRepairError(
            "the repair changed the scene count while only one scene's source was being repaired"
        )
    scenes = list(current.scenes)
    scenes[failed_scene] = repaired.scenes[failed_scene]
    return ComponentVideoDirection(name=current.name, language=current.language, scenes=scenes)


async def repair_component_project(
    project: RemotionProjectSource,
    output: ProgramOutput,
    *,
    diagnostic: str,
    scene_summary: str,
) -> dict[str, Any]:
    """Repair a revision's one project without changing its output window."""
    project_answer = ComponentProjectAnswer.model_validate({
        "entry": project.entry,
        "composition_id": project.composition_id,
        "files": [{"path": item.path, "content": item.content} for item in project.files],
        "props": project.props,
        "props_schema": project.props_schema,
        "resources": [item.model_dump(mode="json") for item in project.resources],
    })
    duration = output.duration_frames / output.fps
    scene = ComponentSceneDirection(
        **project_answer.model_dump(mode="json"),
        name=None,
        language=None,
        title=None,
        intent="Preserve the current visual while repairing its execution",
        visual_description=scene_summary[:240],
        duration_seconds=duration,
        background=output.background,
        narration=None,
    )
    current = ComponentVideoDirection(name=None, language=None, scenes=[scene])
    repaired = await repair_component_video(
        current,
        failed_scene=0,
        diagnostic=diagnostic,
        text="",
        focus=None,
        instruction="仅修复已报告的源码或执行错误，保留请求中的视觉设计。",
        language=None,
        target_seconds=duration,
        aspect=_aspect_for_output(output),
        narration=None,
        current_summary=scene_summary,
    )
    repaired_scene = repaired.scenes[0]
    if abs(repaired_scene.duration_seconds - duration) > 1 / output.fps:
        raise AuthoringRepairError("the repair changed the revision's fixed Generator output window")
    payload = component_project_payload(repaired_scene)
    if payload["resources"] != [item.model_dump(mode="json") for item in project.resources]:
        raise AuthoringRepairError("the repair changed the revision's fixed resource identities")
    return payload


async def repair_program_direction(
    current: ProgramDirection,
    *,
    diagnostic: str,
    text: str,
    focus: str | None,
    instruction: str,
    language: str | None,
    target_seconds: float | None,
    current_summary: str | None,
    read_executor: Any = None,
) -> ProgramDirection:
    return await program_director.call(
        text=text,
        focus=focus,
        instruction=instruction,
        language=language,
        target_seconds=target_seconds,
        current=current_summary,
        read_executor=read_executor,
        repair_feedback=json.dumps({
            "diagnostic": diagnostic,
            "current_program": current.model_dump(mode="json"),
        }, ensure_ascii=False),
    )


async def repair_program_source(
    code: str,
    parameters: dict[str, str | float | bool],
    output: ProgramOutput,
    *,
    diagnostic: str,
    scene_summary: str,
) -> tuple[str, dict[str, str | float | bool]]:
    """Repair draw-2d source while preserving its native content and timing."""
    duration = output.duration_frames / output.fps
    current = ProgramDirection(
        name=None,
        language=None,
        title=None,
        intent="Preserve the current visual while repairing its execution",
        visual_description=scene_summary[:240],
        duration_seconds=duration,
        background=output.background,
        parameters=parameters,
        code=code,
    )
    answer = await repair_program_direction(
        current,
        diagnostic=diagnostic,
        text="",
        focus=None,
        instruction="仅修复已报告的源码或执行错误，保留请求中的视觉设计。",
        language=None,
        target_seconds=duration,
        current_summary=scene_summary,
    )
    if abs(answer.duration_seconds - duration) > 1 / output.fps:
        raise AuthoringRepairError("the repair changed the revision's fixed Generator output window")
    return answer.code, answer.parameters


def _aspect_for_output(output: ProgramOutput) -> str:
    if output.width == output.height:
        return "1:1"
    return "9:16" if output.height > output.width else "16:9"
