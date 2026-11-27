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

from app.agents.tool_loop import ChatTool, ToolObservation, ToolPresentation
from app.chat.perception import executes
from app.chat.perception.executes import (
    GetAssetParams,
    GetSegmentParams,
    GetWebPageParams,
    ListProjectMediaParams,
    SearchMusicParams,
    SearchTranscriptParams,
    SearchVoicesParams,
    SearchWebParams,
)
from app.models.schemas import GetVideoVersionParams


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
    wire_view: Any = None  # Callable[[str, dict], tuple[str, dict]] | None
    # ADR-109: interim_prose 资格已通用化——任何非终态调用前的散文都走
    # interim_prose 座位（app/agents/tool_loop.py），注册表不再携带资格字段。


_OUTPUT_SPEC_DESCRIPTION = (
    "读取一个输出当前的字幕样式、音乐、画幅或正文。相对修改（“缩小”“轻一点”“像之前一样”）前必须先读，再根据现值修改，不得猜测。"
)


PERCEPTION_TOOLS: dict[str, PerceptionTool] = {
    entry.name: entry
    for entry in [
        PerceptionTool(
            name="get_understanding",
            description=(
                "读取项目素材分析（概述、论旨、主题、受众、可引用原话），再总结素材或根据素材推荐。若素材仍在处理中，会等到分析就绪才返回，本轮即可据此作答。"
            ),
            params_model=None,
            execute=executes.get_understanding,
            activity_key="chat.inspecting.understanding",
        ),
        PerceptionTool(
            name="search_music",
            description=(
                "按风格、情绪、标签或关键词复用优先检索永久 Music 曲库（含平台与用户自有曲目），留空列出全库。返回可复用的 music_id（非 Asset ID），可直接传给 create_video 的 music_id 或 prepare_video_materials 的 material_music_ids。需要试听比较时用 show_music_candidates。"
            ),
            params_model=SearchMusicParams,
            execute=executes.search_music,
            activity_key="chat.inspecting.music",
        ),
        PerceptionTool(
            name="search_voices",
            description=(
                "按语言、风格预设、音色气质或关键词复用优先检索永久音色库（voices 表与已验证系统音色）。配音或设计新音色前先调用，优先复用已有 voice_id；需要用户试听比较时用 show_voice_candidates；无合适音色时再调用 design_voice。"
            ),
            params_model=SearchVoicesParams,
            execute=executes.search_voices,
            activity_key="chat.inspecting.voices",
        ),
        PerceptionTool(
            name="search_transcript",
            description=(
                "按主题检索项目转写文本（确定性关键词检索），返回带起止时间和逐字原文的候选段落，供判断选用。"
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
                "逐字读取指定时间线区段的口播（起止以秒计）。将某段作为证据提出前必须先读，引用这里实际说过的话。"
            ),
            params_model=GetSegmentParams,
            execute=executes.get_segment,
            activity_key="chat.inspecting.segment",
        ),
        PerceptionTool(
            name="get_asset",
            description=(
                "读取素材的处理状态、语言、时长和开头文本。项目只有一个文件素材时可省略 ID；有多个时返回带 ID 的清单。"
            ),
            params_model=GetAssetParams,
            execute=executes.get_asset,
            activity_key="chat.inspecting.asset",
        ),
        PerceptionTool(
            name="list_project_media",
            description=(
                "设计包含上传录像或图片的视频前，先列出项目中可用于合成的素材，含稳定 ID、类型、已知或未知的时长、尺寸及可用性。只引用本项目真实 ID。"
                "按最新在前分页，每页 40 条，提示中给出旧记录的偏移。可直接传入所选 ID 读取确切素材，不受页数限制。"
            ),
            params_model=ListProjectMediaParams,
            execute=executes.list_project_media,
            activity_key="chat.inspecting.projectMedia",
        ),
        PerceptionTool(
            name="get_web_page",
            description=(
                "读取网页正文。用户分享链接供讨论或评估，或答案依赖当前网页内容时使用。有已存记录则复用，除非用户说明网页有变化。读取为空时告知无法读取，不编造内容。"
            ),
            params_model=GetWebPageParams,
            execute=executes.get_web_page,
            activity_key="chat.inspecting.webPage",
            seat="page_reading_for_url",
        ),
        PerceptionTool(
            name="get_video_version",
            description=(
                "读取视频作品已保存的确切版本及标准分镜（逐场时间窗、准确屏幕文字和摄像机/动画 ID）。"
                "以 composition_id 指定当前版本，或用分镜卡或已有读取返回的确切 version_id，不能猜测。present=true 再次展示标准卡片；显式指定局部 scrub 时仅展示对应 Scene/Clip 时间窗或独立对象。"
            ),
            params_model=GetVideoVersionParams,
            execute=executes.get_video_version,
            activity_key="chat.inspecting.videoVersion",
        ),
        PerceptionTool(
            name="search_web",
            description=(
                "当答复或计划中的文案需要最新事实时，按主题搜索网页。"
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
                batchable=True,
                wire_view=entry.wire_view,
                presentation=ToolPresentation(kind="read", active_key=entry.activity_key),
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
        text, images = await executes.output_spec_observation(db, project, params)
        return ToolObservation(text, images=tuple(images))
    text = await entry.execute(db, project, params)
    if isinstance(text, ToolObservation):
        return text
    if name == "get_web_page" and isinstance(params, GetWebPageParams):
        from app.tools.project_context import page_context_key
        from app.tools.world import page_reading_for_url
        # A best-effort store write may have failed. In that case the result
        # remains turn-local and must not be folded into an absent resource.
        page = await page_reading_for_url(db, project.id, params.url)
        body = text.partition("\n\n")[2]
        if page is not None and page.text and page.text == body:
            return ToolObservation(text=text, context_lifetime="project", context_keys=(
                page_context_key(project.id, page.url, page.text),
            ))
    return ToolObservation(text=text)


__all__ = [
    "PERCEPTION_TOOLS",
    "PerceptionTool",
    "perception_chat_tools",
    "run_perception_tool",
]
