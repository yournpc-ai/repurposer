"""Executable tasks for the saved-Composition production RunPlan."""

from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel

import app.pipeline.node_runners  # noqa: F401
from app.tools.video.production.node import ProduceVideo  # noqa: F401
from app.tools.video.params import PrepareNarrationParams, ProduceVideoParams
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
            description="Render an existing, fully presented and approved video version. "
            "Use design_video first; never design or change content during production.",
            behavior="deterministic",
            params_model=ProduceVideoParams,
            summary_templates={"en": "Prepared video · {total_seconds:g}s",
                               "zh": "已准备短片 · {total_seconds:g} 秒"},
        ),
        ToolEntry(
            name="prepare_narration",
            description="Prepare one exact final script as a speed-1.0 narration original, "
            "freeze its real AUDIO snapshot and request NarrationAlignment. "
            "Runs as the only task in its Run; it creates no video or Composition.",
            behavior="deterministic",
            params_model=PrepareNarrationParams,
            summary_templates={"en": "Prepared narration · {duration_seconds:g}s",
                               "zh": "已准备旁白原音 · {duration_seconds:g} 秒"},
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
        raise ToolRejected("One saved Composition production takes exactly one task", suggestions=[])
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
