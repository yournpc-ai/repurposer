"""Executable tasks for authorized video production and preparation RunPlans."""

from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel

import app.pipeline.node_runners  # noqa: F401
from app.tools.video.production.node import ProduceVideo  # noqa: F401
from app.tools.video.params import (

    PrepareNarrationParams,
    PrepareVisualAssetsParams,
    ProduceVideoParams,
)
from app.tools.music.score import GenerateMusicArgs
from app.pipeline.graph import NODE_KINDS


class ToolRejected(ValueError):
    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.suggestions = suggestions or []


class ToolEntry(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    behavior: Literal["deterministic", "probabilistic"]
    params_model: type[BaseModel] | None = None
    summary_templates: dict[str, str] = {}
    seat: bool = False
    needs_media_file: bool = False
    llm_visible: bool = True


TOOL_REGISTRY: dict[str, ToolEntry] = {
    entry.name: entry
    for entry in [
        ToolEntry(
            name="produce_video",
            description="渲染已完整展示并获批准的现有视频版本。先用 design_video 完成设计，制作期间不得重新设计或修改内容。",
            behavior="deterministic",
            params_model=ProduceVideoParams,
            summary_templates={"en": "Prepared video · {total_seconds:g}s",
                               "zh": "已准备短片 · {total_seconds:g} 秒"},
        ),
        ToolEntry(
            name="prepare_narration",
            description="用确切的定稿文本准备一份 1.0 倍速的旁白原声，固定其真实 AUDIO 快照并请求 NarrationAlignment。该 Run 仅含此任务，不会创建视频或 Composition。",
            behavior="deterministic",
            llm_visible=False,
            params_model=PrepareNarrationParams,
            summary_templates={"en": "Prepared narration · {duration_seconds:g}s",
                               "zh": "已准备旁白原音 · {duration_seconds:g} 秒"},
        ),
        ToolEntry(
            name="prepare_visual_assets",
            description="根据 draft_ref 和 scene_ids 准备一批限定范围的图片，或用 review_existing 对审阅不可用的固定 PNG 重试审阅。该 Run 仅含此任务，不会创建 Composition 版本或 Output。",
            behavior="deterministic",
            llm_visible=False,
            params_model=PrepareVisualAssetsParams,
            summary_templates={"en": "Prepared scene images · {total_assets}",
                               "zh": "已准备分镜图片 · {total_assets} 张"},
        ),
        ToolEntry(
            name="prepare_music",
            description="为当前草稿合成已授权且确定性的电子配乐 ScoreSpec，固定私有 Music 及其音频 Snapshot，保留编排好的 BeatGrid 和音频分析。该 Run 仅含此任务，不会创建 Composition 版本或 Output。",
            behavior="deterministic",
            params_model=GenerateMusicArgs,
            llm_visible=False,
            summary_templates={"en": "Prepared electronic score · {duration_seconds:g}s",
                               "zh": "已准备电子配乐 · {duration_seconds:g} 秒"},
        ),
    ]
}


def dispatchable_tools() -> list[ToolEntry]:
    return [entry for entry in TOOL_REGISTRY.values() if not entry.seat and entry.name in NODE_KINDS]


def _params_doc(model: type[BaseModel]) -> str:
    return ", ".join(
        f"{name}: {field.description}" if field.description else name
        for name, field in model.model_fields.items()
    )


def tool_catalog_lines(*, exclude: frozenset[str] = frozenset()) -> str:
    return "\n".join(
        f"- {entry.name}: {entry.description}"
        + (f" (params: {_params_doc(entry.params_model)})" if entry.params_model else "")
        for entry in dispatchable_tools()
        if entry.llm_visible and entry.name not in exclude
    )


def capability_menu_lines() -> str:
    entry = TOOL_REGISTRY["produce_video"]
    return f"- {entry.description}" if entry in dispatchable_tools() else ""


def strip_null_params(params: dict | None) -> dict:
    return {
        key: value
        for key, value in (params or {}).items()
        if value is not None and not (isinstance(value, str) and value.strip().lower() == "null")
    }


def validate_task_list(tasks: list[Any]) -> list[ToolEntry]:
    if len(tasks) > 1:
        scenes = [(t.params or {}).get("scene_id") for t in tasks]
        ref = (tasks[0].params or {}).get("draft_ref")
        if (not ref or not all(isinstance(scene, str) and scene for scene in scenes)
                or len(set(scenes)) != len(scenes)
                or any(t.tool != "prepare_narration" or (t.params or {}).get("draft_ref") != ref for t in tasks)):
            raise ToolRejected("A batch must contain distinct scene narrations from the same draft", suggestions=[])
    dispatchable = {entry.name: entry for entry in dispatchable_tools()}
    entries: list[ToolEntry] = []
    for task in tasks:
        entry = dispatchable.get(task.tool)
        if entry is None:
            raise ToolRejected(
                f"'{task.tool}' is not a runnable plan task",
                suggestions=difflib.get_close_matches(task.tool, dispatchable.keys(), n=3, cutoff=0.4)
                or sorted(dispatchable.keys()),
            )
        if entry.params_model is not None:
            try:
                entry.params_model.model_validate(strip_null_params(task.params))
            except Exception as exc:
                raise ToolRejected(
                    f"Tool '{task.tool}' rejected its params: {exc}",
                    suggestions=[entry.name],
                ) from exc
        entries.append(entry)
    return entries
