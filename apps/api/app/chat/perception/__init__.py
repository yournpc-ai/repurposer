"""The chat loop's perception family (ADR-077 判词②, T2b) — the read tools.

世界的读法 vs 世界的改法: this registry is the READ half of the chat edge
agent's tool set (``app/tools/``'s TOOL_REGISTRY owns the WRITES the run
birthplace compiles). A read tool is how the agent LOOKS at the world
before closing a turn — read-before-write is the relative-revision and
recommendation journeys' functional premise (JOURNEYS 旅程三), not
experience sugar.

Registry discipline (same law as TOOL_REGISTRY): a static dict deployed
with the code — never a plugin system. Each entry carries exactly:

- ``name`` — the model-facing call name (a ``get_*``/``list_*``/``search_*``
  verb phrase; the pure consistency suite gates the prefix law and every
  prompt mention against membership here);
- ``description`` — model-facing, terse (注册表条目扰动 = prompt 扰动):
  WHEN to call it, in one sentence;
- ``params_model`` — the call's JSON schema (package-local, ``executes.py``;
  None = a zero-arg read);
- ``execute`` — the read itself (``executes.py``; 只读纪律 — no write
  functions exist there);
- ``activity_key`` — the 碎碎念 copy key for the SSE ``inspecting`` phase
  frame (i18n key, resolved client-side; the tool NAME never reaches the
  user face — 简报 §3 禁令).

The loop-facing projection is ``perception_chat_tools`` (each entry becomes
a non-terminal ``ChatTool``); the turn runners dispatch reads through
``run_perception_tool`` (one branch in their execute seats).
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.agents.tool_loop import ChatTool, ToolObservation
from app.chat.perception import executes
from app.chat.perception.executes import (
    GetAssetParams,
    GetCraftSkeletonParams,
    GetOutputSpecParams,
    SearchMusicParams,
)


@dataclass(frozen=True)
class PerceptionTool:
    """One registered read tool (name + params schema + execute + 碎碎念
    文案键 — the registry discipline, nothing else)."""

    name: str
    description: str
    params_model: type[BaseModel] | None
    execute: Any  # (db, project, params) -> str — the observation text
    activity_key: str  # i18n key for the inspecting phase frame


PERCEPTION_TOOLS: dict[str, PerceptionTool] = {
    entry.name: entry
    for entry in [
        PerceptionTool(
            name="get_output_spec",
            description=(
                "Read one output's current state (caption style, music, "
                "aspect, the text body) — ALWAYS before a relative edit "
                "('smaller', 'quieter', 'like before'): compose the change "
                "from the current settings, never invent them."
            ),
            params_model=GetOutputSpecParams,
            execute=executes.get_output_spec,
            activity_key="chat.inspecting.outputSpec",
        ),
        PerceptionTool(
            name="get_understanding",
            description=(
                "Read the material understanding of the project's assets "
                "(summary, thesis, themes, audience, quotable lines) — before "
                "summarizing the material or matching a recommendation to it."
            ),
            params_model=None,
            execute=executes.get_understanding,
            activity_key="chat.inspecting.understanding",
        ),
        PerceptionTool(
            name="list_caption_styles",
            description=(
                "List the caption style presets with behavior notes — before "
                "offering subtitle style choices."
            ),
            params_model=None,
            execute=executes.list_caption_styles,
            activity_key="chat.inspecting.captionStyles",
        ),
        PerceptionTool(
            name="search_music",
            description=(
                "Search the music library by mood/keyword (empty = the full "
                "catalog) — before recommending or proposing a music bed."
            ),
            params_model=SearchMusicParams,
            execute=executes.search_music,
            activity_key="chat.inspecting.music",
        ),
        PerceptionTool(
            name="get_run_status",
            description=(
                "Read the latest run's live status and per-step progress — "
                "for 'how far along / 还要多久' questions; never guess."
            ),
            params_model=None,
            execute=executes.get_run_status,
            activity_key="chat.inspecting.runStatus",
        ),
        PerceptionTool(
            name="get_asset",
            description=(
                "Read one asset's detail (processing status, language, "
                "duration, opening text). Omit the id for the project's "
                "only file asset — with several, the call returns the "
                "roster with their ids."
            ),
            params_model=GetAssetParams,
            execute=executes.get_asset,
            activity_key="chat.inspecting.asset",
        ),
        PerceptionTool(
            name="get_craft_skeleton",
            description=(
                "Read the pinned reference video's craft skeleton (aspect, "
                "shot rhythm, caption style best-fit, music mood, and the "
                "honest list of what a remix cannot reproduce) — ALWAYS the "
                "first read when a reference case is pinned or its decompile "
                "just finished; never guess at the case's style."
            ),
            params_model=GetCraftSkeletonParams,
            execute=executes.get_craft_skeleton,
            activity_key="chat.inspecting.craftSkeleton",
        ),
    ]
}


def perception_chat_tools(*names: str) -> list[ChatTool]:
    """Project registry entries into the loop's tool form — non-terminal by
    construction (终态工具一调即停 covers the terminal tools; a read never
    ends a turn). Unknown names raise at declaration time (startup), never
    mid-turn."""
    tools: list[ChatTool] = []
    for name in names:
        entry = PERCEPTION_TOOLS[name]
        tools.append(
            ChatTool(
                name=entry.name,
                description=entry.description,
                params_model=entry.params_model,
                terminal=False,
            )
        )
    return tools


async def run_perception_tool(db, project, name: str, params) -> ToolObservation:
    """The turn runners' read dispatch seat: the project scopes the read
    (tenant law — a read never crosses the turn's project); a project-less
    turn (defensive shape) reads as an honest empty observation."""
    if project is None:
        return ToolObservation(
            "No project context is loaded — there is nothing to read."
        )
    entry = PERCEPTION_TOOLS[name]  # membership was gated by the caller
    return ToolObservation(text=await entry.execute(db, project, params))


__all__ = [
    "PERCEPTION_TOOLS",
    "PerceptionTool",
    "perception_chat_tools",
    "run_perception_tool",
]
