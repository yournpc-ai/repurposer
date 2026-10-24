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
    GetArtifactParams,
    GetAssetParams,
    GetCraftSkeletonParams,
    GetNodeParams,
    GetOutputSpecParams,
    GetSegmentParams,
    GetWebPageParams,
    ListProjectMediaParams,
    SearchMusicParams,
    SearchTranscriptParams,
    SearchWebParams,
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
    # consult-first 律 (world seats): a fetch-capable tool declares the
    # world seat it consults BEFORE any network fetch — the seat names a
    # function in app/tools/world.py (the pure suite gates the reference).
    # None = no stored world fact exists for this read (ephemeral by
    # nature, e.g. web search). A NEW fetch-capable tool without a seat
    # declaration is the repeat-fetch bug class reborn — declare one.
    seat: str | None = None
    # The deployment-gate hook (same law as ChatTool.wire_view): rewrites
    # the (description, parameters) pair at spec time so a gated capability
    # slice (e.g. the film read's images, keyed to film_edits_enabled)
    # never reaches the wire while the gate is off.
    wire_view: Any = None  # Callable[[str, dict], tuple[str, dict]] | None
    # ADR-109: checkpoint 资格已通用化——任何非终态调用前的散文都走
    # checkpoint 座位（app/agents/tool_loop.py），注册表不再携带资格字段。


def _output_spec_wire_view(description: str, parameters: dict) -> tuple[str, dict]:
    """The film read's image slice rides the edit capability gate
    (settings.film_edits_enabled): gate OFF = the base description and a
    schema without ``views`` — the model is never told about an image
    channel the observation would not attach. The read's execute side
    simply never attaches images while gated (declaration and observation
    gate together)."""
    from app.config import settings  # deferred: config leaf

    if settings.film_edits_enabled:
        return description, parameters
    from app.agents.tool_loop import prune_wire_parameters

    return _OUTPUT_SPEC_DESCRIPTION, prune_wire_parameters(parameters, {"views"})


_OUTPUT_SPEC_DESCRIPTION = (
    "Read one output's current state (caption style, music, "
    "aspect, the text body; a film output reads back its "
    "storyboard version and per-scene ids) — "
    "ALWAYS before a relative edit "
    "('smaller', 'quieter', 'like before'): compose the change "
    "from the current settings, never invent them. Omit the output "
    "id to read the film's CURRENT storyboard version (the live "
    "draft when one stands, else the latest delivered film) — the "
    "re-read seat before continuing a targeted edit in a later turn."
)
_OUTPUT_SPEC_IMAGES_SENTENCE = (
    " A film read also attaches the site's captured view screenshots "
    "(the MATERIAL's views, never frames of the rendered film) and lists "
    "the candidate views an update_scene edit may name — the response "
    "carries up to 12 thumbnails with their camera-target inventories "
    "(the element ids a focus may name), or name views (page/shot pairs) "
    "for a specific set; one named view reads back in high resolution."
)


PERCEPTION_TOOLS: dict[str, PerceptionTool] = {
    entry.name: entry
    for entry in [
        PerceptionTool(
            name="get_output_spec",
            description=_OUTPUT_SPEC_DESCRIPTION + _OUTPUT_SPEC_IMAGES_SENTENCE,
            params_model=GetOutputSpecParams,
            execute=executes.get_output_spec,
            activity_key="chat.inspecting.outputSpec",
            wire_view=_output_spec_wire_view,
        ),
        PerceptionTool(
            name="get_node",
            description=(
                "Read one graph node's FULL current program, state, "
                "products and downstream (the context's Graph section "
                "truncates long programs) — ALWAYS before an edit_graph "
                "revision of that node: compose the new program from the "
                "full current one, never from the truncated line."
            ),
            params_model=GetNodeParams,
            execute=executes.get_node,
            activity_key="chat.inspecting.node",
        ),
        PerceptionTool(
            name="get_understanding",
            description=(
                "Read the material understanding of the project's assets "
                "(summary, thesis, themes, audience, quotable lines) — before "
                "summarizing the material or matching a recommendation to it. "
                "While assets are still processing this read WAITS until the "
                "understanding lands (it never returns mid-processing), so a "
                "content-dependent answer can ground itself in the same turn."
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
            name="list_runs",
            description=(
                "List the project's recent run history (newest first) — "
                "for 'what did we already run / 之前跑过什么' questions; the "
                "latest run's live detail stays get_run_status's seat."
            ),
            params_model=None,
            execute=executes.list_runs,
            activity_key="chat.inspecting.runHistory",
        ),
        PerceptionTool(
            name="get_pending_plan",
            description=(
                "Read the plan currently docked for the user's confirmation "
                "(its task chain, name, extra instruction) — for 'what was "
                "the plan again / 计划是什么' questions on the chat path."
            ),
            params_model=None,
            execute=executes.get_pending_plan,
            activity_key="chat.inspecting.pendingPlan",
        ),
        PerceptionTool(
            name="get_graph",
            description=(
                "Read the canvas's current face — every node's state and "
                "label in visual order — when you need to speak about what "
                "the user is seeing (the workspace is visible to them once "
                "a plan is docked, before any run)."
            ),
            params_model=None,
            execute=executes.get_graph,
            activity_key="chat.inspecting.graph",
        ),
        PerceptionTool(
            name="search_transcript",
            description=(
                "Search the project's transcripts for a topic (deterministic "
                "keyword retrieval) — the discovery read: hits come back as "
                "[start–end] sections with their verbatim cue text, ready "
                "to evaluate as candidate members."
            ),
            params_model=SearchTranscriptParams,
            execute=executes.search_transcript,
            # 改籍 (iter-2 ⑥, N-57): the discovery read rides the work-session
            # family — the same read, the work-session vocabulary replaces
            # the generic inspecting word (done mirror = key + "Done").
            activity_key="chat.explore.searching",
        ),
        PerceptionTool(
            name="get_segment",
            description=(
                "Read one timeline range's verbatim speech ([start–end] in "
                "seconds) — read THIS before proposing a range as evidence: "
                "the excerpt must be what is actually said here."
            ),
            params_model=GetSegmentParams,
            execute=executes.get_segment,
            activity_key="chat.inspecting.segment",
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
            name="list_project_media",
            description=(
                "List the project's video/image assets a film may compose "
                "with — stable ids, kind, duration (known or unknown), "
                "dimensions, usability — BEFORE designing a film over "
                "uploaded footage or images: cite only ids from this "
                "project, never invent one. Pages newest-first (40 per "
                "page — the note names the offset for older rows); pass "
                "ids to read exact assets (the user's picks, past the "
                "page cap or not)."
            ),
            params_model=ListProjectMediaParams,
            execute=executes.list_project_media,
            activity_key="chat.inspecting.projectMedia",
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
        PerceptionTool(
            name="get_artifact",
            description=(
                "Read one exploration artifact's full fields (a candidate "
                "collection's sections, a pick's verdict + the section it "
                "points at, a plan card's deliverables) — before revising a "
                "pick (revise_selects) or answering what a landed pick/plan "
                "carries."
            ),
            params_model=GetArtifactParams,
            execute=executes.get_artifact,
            activity_key="chat.inspecting.artifact",
        ),
        PerceptionTool(
            name="get_web_page",
            description=(
                "Read one web page's readable text — when the user shares a "
                "link to discuss or evaluate, or an answer depends on a "
                "page's current content. A stored reading answers when one "
                "exists (the same page is never re-fetched unless the user "
                "says it changed). An empty read means the page could "
                "not be read — say so, never invent its content."
            ),
            params_model=GetWebPageParams,
            execute=executes.get_web_page,
            activity_key="chat.inspecting.webPage",
            seat="page_reading_for_url",
        ),
        PerceptionTool(
            name="search_web",
            description=(
                "Search the web for fresh facts on a topic — when the answer "
                "or the planned copy depends on current / time-sensitive "
                "information."
            ),
            params_model=SearchWebParams,
            execute=executes.search_web,
            activity_key="chat.inspecting.webSearch",
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
                wire_view=entry.wire_view,
            )
        )
    return tools


async def run_perception_tool(
    db,
    project,
    name: str,
    params,
) -> ToolObservation:
    """The turn runners' read dispatch seat: the project scopes the read
    (tenant law — a read never crosses the turn's project); a project-less
    turn (defensive shape) reads as an honest empty observation."""
    if project is None:
        return ToolObservation(
            "No project context is loaded — there is nothing to read."
        )
    entry = PERCEPTION_TOOLS[name]  # membership was gated by the caller
    if name == "get_understanding":
        # The read's landed flag rides the observation (ADR-102 §5) — the
        # loop mirrors it into ReadAccepted, and the read's frame settles
        # FAILED with the honest failed-form key instead of the done lie.
        text, ok = await executes.understanding_observation(db, project)
        return ToolObservation(text, ok=ok)
    if name == "get_output_spec":
        # The film read's attached view screenshots ride the observation
        # (R3 读取座) — the loop's wire seat projects them as content parts.
        text, images = await executes.output_spec_observation(db, project, params)
        return ToolObservation(text, images=tuple(images))
    return ToolObservation(text=await entry.execute(db, project, params))


__all__ = [
    "PERCEPTION_TOOLS",
    "PerceptionTool",
    "perception_chat_tools",
    "run_perception_tool",
]
