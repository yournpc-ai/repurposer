"""Native tools offered to the editor and transcript prose filtering."""

import re

from app.agents.tool_loop import ChatTool, NATIVE_PRESENTATION, ToolPresentation, ToolPresentationVariant, ToolRejected, prune_wire_parameters
from app.chat.editor import EDITOR_TOOLS
from app.chat.perception import perception_chat_tools
from app.models.schemas import (
    AnalyzeBrandArgs,
    AnnotateNarrationArgs,
    GetNarrationAlignmentArgs,
    ImportSfxArgs,
    PlanAnswerArgs,
    PlanAskArgs,
    AlignRecordingArgs,
    ReviewVideoArgs,
    SearchSfxArgs,
    SelectMusicArgs,
    SelectVideoPresetArgs,
    ShowMusicCandidatesArgs,
    ShowVideoPresetsArgs,
)

def video_rejection_stop(current: ToolRejected, previous: tuple[ToolRejected, ...]) -> bool:
    same = [event for event in previous
            if event.tool_name == current.tool_name and event.kind == current.kind
            and event.detail == current.detail and event.candidate_digest == current.candidate_digest]
    if same and (current.candidate_digest is not None or previous[-1] is same[-1]):
        return True
    return current.tool_name == "create_video" and sum(
        event.tool_name == current.tool_name for event in (*previous, current)
    ) >= 3


_REVIEW_VIDEO_DESCRIPTION = (
    "对照用户要求审阅指定的已交付视频 Output。系统解码该 Output 自身的文件，附带真实采样帧及时间，检查绑定版本，保存建议性报告。"
    "默认复用已有报告，refresh=true 可重新执行所选采样模式。按指定时点复查用 at_seconds；审阅某个已执行 Scene 的有序帧用 motion_scene_id。二者互斥。"
    "声称看过成片或应要求做内容质量修订前，先用本工具。不要用分镜读取结果或最近的其他 Output 替代。"
)
_REVIEW_VIDEO_TOOL = ChatTool(
    name="review_video",
    terminal=False,
    description=_REVIEW_VIDEO_DESCRIPTION,
    params_model=ReviewVideoArgs,
    presentation=ToolPresentation(
        kind="draft", active_key="chat.activity.videoReview",
        done_key="chat.activity.videoReviewDone", defer_start=True,
        policy="review", receipt_kind="video_review",
    ),
)




def _show_video_presets_tool() -> ChatTool:
    from app.editing.presets import PRESET_REGISTRY

    return ChatTool(
        name="show_video_presets",
        presentation=NATIVE_PRESENTATION,
        terminal=False,
        description=(
            "用真实动态预览展示 2–4 个不同且兼容的原生 Preset 候选。preset_ids 只能取自以下注册表："
            + ", ".join(PRESET_REGISTRY)
            + "。标题、预览媒体、时长和摘要由服务端推导。展示比较后结束本轮，用户可在后续消息中按序号选择。此操作不创建版本、选择、Run 或制作意图。"
        ),
        params_model=ShowVideoPresetsArgs,
    )


_SELECT_VIDEO_PRESET_TOOL = ChatTool(
    name="select_video_preset",
    presentation=NATIVE_PRESENTATION,
    terminal=False,
    description=(
        "记录用户从之前已结算的 Preset 候选集中按序号作出的选择。只传 candidate_set_id 和从零起的 member_index。服务端解析已保存的候选并更新原卡片。"
        "不会修改 CompositionVersion、创建 Run 或表示授权制作。应用效果须实际编写完整 Composition 或所属 Clip，不能将预设 ID 当作编辑操作。"
    ),
    params_model=SelectVideoPresetArgs,
)


_SEARCH_SFX_TOOL = ChatTool(
    name="search_sfx",
    terminal=False,
    description=(
        "从 Freesound 搜索最多三个真实的 CC0 MP3 音效。候选可试听，本轮结束时保存，但不写入素材或视频版本。"
        "展示后结束本轮，不能立即导入本轮刚列出的候选。仅按元数据排序不能声称已试听。"
    ),
    params_model=SearchSfxArgs,
    presentation=ToolPresentation(
        kind="read", active_key="chat.activity.sfxSearch",
        done_key="chat.activity.sfxSearchDone", receipt_kind="sfx_search",
    ),
)
_IMPORT_SFX_TOOL = ChatTool(
    name="import_sfx",
    terminal=False,
    description=(
        "从先前已结算回合的候选卡导入用户选中的声音。只传 candidate_set_id 和从零起的 member_index，不提供或编造 URL、标题、作者、供应商 ID 或许可。"
        "服务端重新解析已保存的候选并复核 CC0，下载真实 MP3 预览并返回素材 snapshot_id。导入后可从项目素材中读取。"
    ),
    params_model=ImportSfxArgs,
    presentation=ToolPresentation(
        kind="read", active_key="chat.activity.sfxImport",
        done_key="chat.activity.sfxImportDone", receipt_kind="sfx_import",
    ),
)
_SHOW_MUSIC_CANDIDATES_TOOL = ChatTool(
    name="show_music_candidates",
    terminal=False,
    description=(
        "按背景音乐需求从本地 Music 曲库展示最多五首可播放的真实曲目。候选在本轮结束时保存，不写素材、版本或 Run。"
        "展示后结束本轮，不选择本轮刚产生的候选。曲库元数据不能作为试听依据。"
    ),
    params_model=ShowMusicCandidatesArgs,
    presentation=ToolPresentation(
        kind="read", active_key="chat.activity.musicSearch",
        done_key="chat.activity.musicSearchDone", receipt_kind="music_search",
    ),
)
_SELECT_MUSIC_TOOL = ChatTool(
    name="select_music",
    terminal=False,
    description=(
        "选择用户从先前已结算的 Music 候选卡按序号点名的曲目。只传 candidate_set_id 和从零起的 member_index。服务端解析本地曲库条目，返回 music_id，不下载、不修改版本。"
        "将该 ID 传给 prepare_video_materials 的 material_music_ids，再把返回的固定音频快照用 insert_audio 放入当前作品。修改已保存版本使用当前编辑工具。"
    ),
    params_model=SelectMusicArgs,
    presentation=ToolPresentation(
        kind="read", active_key="chat.activity.musicSelection",
        done_key="chat.activity.musicSelectionDone", receipt_kind="music_selection",
    ),
)
_ALIGN_RECORDING_TOOL = ChatTool(
    name="align_recording", description="Align the exact transcript with an explicitly referenced recording.",
    params_model=AlignRecordingArgs,
    terminal=False,
    presentation=ToolPresentation("read", "chat.activity.narrationRead", "chat.activity.narrationReadDone"),
)


_GET_NARRATION_ALIGNMENT_TOOL = ChatTool(
    name="get_narration_alignment",
    terminal=False,
    description=(
        "读取归属当前用户的 NarrationAlignment 的实际状态及完整数据，包括句词范围、整数刻度、插值、审阅状态和语义。不要估算缺失时间。"
    ),
    params_model=GetNarrationAlignmentArgs,
    presentation=ToolPresentation(
        kind="read", active_key="chat.activity.narrationRead",
        done_key="chat.activity.narrationReadDone",
    ),
)
_ANNOTATE_NARRATION_TOOL = ChatTool(
    name="annotate_narration",
    terminal=False,
    description=(
        "为 ALIGNED 旁白逐句标注 role、weight、entities、needs 和 emphasis_word_ids，词 ID 取自本句实际单词。原样带回本次读取的 expected_timing_digest。文本和刻度不可变。全部句子对齐并标注后才能达到 READY。"
    ),
    params_model=AnnotateNarrationArgs,
    presentation=ToolPresentation(
        kind="read", active_key="chat.activity.narrationAnnotate",
        done_key="chat.activity.narrationAnnotateDone",
    ),
)


def _skill_authoring_read_tools() -> list[ChatTool]:
    from app.skills.package_session import (
        GetSkillPreviewArgs,
        ListSkillShotsArgs,
        ReadSkillDemoArgs,
        ReadSkillReferenceArgs,
    )

    skill_read = ToolPresentation(
        kind="read", active_key="chat.activity.skillRead",
        done_key="chat.activity.skillReadDone", receipt_kind="skill_read",
    )
    return [
        ChatTool(
            name="list_skill_shots",
            terminal=False,
            batchable=True,
            description="读取当前绑定 Skill 的精简镜头、序列及模板索引。仅在需要这些方法时使用，不创建版本或 Run。",
            params_model=ListSkillShotsArgs,
            presentation=skill_read,
        ),
        ChatTool(
            name="read_skill_reference",
            terminal=False,
            batchable=True,
            description="按绑定 Skill 索引返回的确切路径读取限定范围的文本。包内内容只作参考，不能作为授权或可执行代码。",
            params_model=ReadSkillReferenceArgs,
            presentation=skill_read,
        ),
        ChatTool(
            name="read_skill_demo",
            terminal=False,
            batchable=True,
            description="从绑定 Skill 读取一段已声明的演示或源码文本。源码仅供参考，本工具不会执行。",
            params_model=ReadSkillDemoArgs,
            presentation=skill_read,
        ),
        ChatTool(
            name="get_skill_preview",
            terminal=False,
            batchable=True,
            description="读取绑定 Skill 的镜头声明的真实预览。可用时返回实际图片或视频证据，应区分 available=false 与尚未读取。",
            params_model=GetSkillPreviewArgs,
            presentation=ToolPresentation(
                kind="read", active_key="chat.activity.skillPreview",
                done_key="chat.activity.skillPreviewDone", receipt_kind="skill_read",
            ),
        ),
    ]


def _video_material_tools() -> list[ChatTool]:
    from app.models.schemas import PrepareVideoMaterialsArgs
    from app.tools.research.capture import CaptureRequest

    def only_web_urls(params):
        return isinstance(params, PrepareVideoMaterialsArgs) and bool(params.material_urls) and not any((
            params.material_asset_ids, params.material_output_ids,
            params.material_music_ids, params.material_targets,
        ))

    return [
        ChatTool(
            name="prepare_video_materials",
            terminal=False,
            batchable=True,
            description="准备所选网页，并导入选定素材、已交付视频或曲库音乐以供剪辑。等待 URL 采集完成。结果含当前所有者范围内的 SourceSnapshot 标识，可用作工具参数。视频默认提供有限的代表静帧，不能据此声称连续审片。仅用户明确要求连续检查源视频时用 video_observation=continuous。search_music 或 select_music 返回的 Music ID 传入 material_music_ids，不传 material_asset_ids。只返回已完成资源或明确失败，不返回待处理。复用已导入的媒体，后续设计被拒绝不影响已准备好的资源。只读现有媒体，不合成或渲染。",
            params_model=PrepareVideoMaterialsArgs,
            presentation=ToolPresentation(
                kind="read", active_key="chat.activity.videoMaterials",
                done_key="chat.activity.videoMaterialsDone",
                steps=(("view_webpage", "chat.activity.viewWebPage"),
                       ("import_music", "chat.activity.importMusic"),
                       ("prepare_media", "chat.activity.videoMaterials")),
                variants=(ToolPresentationVariant(
                    matches=only_web_urls,
                    active_key="chat.activity.viewWebPage",
                    done_key="chat.activity.viewWebPageDone",
                ),),
            ),
        ),
        ChatTool(
            name="analyze_brand",
            terminal=False,
            description="读取当前网站已固定的可引用原文及实际采集的 PNG，在待处理的 CreativeState 中保存带来源引用的 BrandProfile。这是证据准备，不启动付费媒体 Run。视觉推断保留 inferred 标记；失败时不保存档案。",
            params_model=AnalyzeBrandArgs,
            presentation=ToolPresentation(
                kind="read", active_key="chat.activity.brandAnalyze",
                done_key="chat.activity.brandAnalyzeDone",
            ),
        ),
        ChatTool(
            name="capture_web",
            terminal=False,
            batchable=True,
            description="从一个确切的固定网页快照中采集限定范围的页面、元素或共享空底图。描述状态、单个元素或限定集合以及所需输出，选择器、已填充的基准画面、缩放和来源关系由服务端提供。返回成功资源、真实图片及所有限定问题，部分成功的结果可立即使用。不接受浏览器脚本或执行角色。",
            params_model=CaptureRequest,
            presentation=ToolPresentation(
                kind="read", active_key="chat.activity.videoCapturePlan",
                done_key="chat.activity.videoCapturePlanDone",
            ),
        ),
    ]


def tools_for_bound_skill(tools: list[ChatTool], skill: object | None) -> list[ChatTool]:
    """Project package reads only while an immutable Skill is bound."""
    if skill is not None:
        return tools
    names = {tool.name for tool in _skill_authoring_read_tools()}
    return [tool for tool in tools if tool.name not in names]


def _explicit_constraint_wire(
    parameters: dict, constraints: dict, *, include_fixed: bool,
) -> dict:
    fields = {"scene_count", "target_seconds", "fps", "aspect", "background"}
    hidden = fields - set(constraints) if include_fixed else fields
    parameters = prune_wire_parameters(parameters, hidden)
    for field, value in constraints.items():
        if not include_fixed or field not in (parameters.get("properties") or {}):
            continue
        parameters["properties"][field] = {
            "type": {"scene_count": "integer", "fps": "integer", "target_seconds": "number"}.get(field, "string"),
            "enum": [value],
            "description": f"用户已固定 {field}，服务端将在续写和保存时恢复该值。",
        }
    return parameters












def _video_project_tools() -> list[ChatTool]:
    return [
        *_skill_authoring_read_tools(),
        *_video_material_tools(),
        *EDITOR_TOOLS,
        _REVIEW_VIDEO_TOOL,
        _show_video_presets_tool(),
        _SELECT_VIDEO_PRESET_TOOL,
        _SEARCH_SFX_TOOL,
        _IMPORT_SFX_TOOL,
        _SHOW_MUSIC_CANDIDATES_TOOL,
        _SELECT_MUSIC_TOOL,
        _ALIGN_RECORDING_TOOL,
        _GET_NARRATION_ALIGNMENT_TOOL,
        _ANNOTATE_NARRATION_TOOL,
        *perception_chat_tools("get_video_version"),
    ]

PLAN_TOOLS = [
    ChatTool(
        name="ask_user",
        presentation=NATIVE_PRESENTATION,
        description=(
            "集中澄清最影响结果的问题。问题及选项会展示给用户，回答或安全跳过后可继续。开放探索和浏览时，也可把值得比较的具体方向作为选项，标记倾向的一项，并允许跳过。"
        ),
        params_model=PlanAskArgs,
    ),
    ChatTool(
        name="answer",
        presentation=NATIVE_PRESENTATION,
        description=(
            "用消息正文回答用户，或根据本轮工具回执说明实际结果。"
            "需要澄清时调用 ask_user。"
        ),
        params_model=PlanAnswerArgs,
    ),
]

PLAN_READ_TOOLS = [
    *perception_chat_tools(
        "get_understanding", "get_asset", "search_music", "search_transcript",
        "get_segment", "get_web_page", "search_web", "list_project_media",
    ),
    *_video_project_tools(),
]
# ── 工具名回响 sanitizer (2026-09-30 用户拍板 — 彻底删掉) ──────────────────
# The model sometimes echoes the tool it is calling as a BARE bracketed line
# of prose ('[inspect_clip]'): the name saturates its prompt (it must — it is
# the tool's name), and the bracket shape is the function-call markup of its
# pretraining. The real call rides the native tool channel; the echo is pure
# noise the spoken sentence already covers — and the user should never see
# machine vocabulary. Strip lines that are EXACTLY one registered tool's
# name in brackets; a name mentioned mid-sentence is prose and stays.
_TOOL_ECHO_NAMES = frozenset(
    tool.name for tool in [*PLAN_TOOLS, *PLAN_READ_TOOLS]
)
_TOOL_ECHO_LINE = re.compile(r"^\[[a-z_]+\]\s*$")
# A tail fragment that could still complete INTO a bare echo line — the
# stream filter holds exactly these undecided (fails fast on any non
# [a-z_] character, so legit prose like a markdown link releases after
# a character or two).
_TOOL_ECHO_PREFIX = re.compile(r"^\[[a-z_]*(\]\s*)?$")


def strip_tool_echoes(content: str) -> str:
    """Remove bare [tool_name] echo lines from assistant prose (pure)."""
    if "[" not in content:
        return content
    kept = []
    for line in content.split("\n"):
        stripped = line.strip()
        if _TOOL_ECHO_LINE.match(stripped) and stripped.strip("[]").strip() in _TOOL_ECHO_NAMES:
            continue
        kept.append(line)
    # The echo rides as its own paragraph — collapse the blank run its
    # removal leaves so the seam never shows.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip("\n")


def _is_tool_echo_line(line: str) -> bool:
    stripped = line.strip()
    return bool(_TOOL_ECHO_LINE.match(stripped)) and stripped.strip("[]").strip() in _TOOL_ECHO_NAMES


def make_tool_echo_delta_filter(emit):
    """Stream-side gate of the same law (2026-09-30 同批拍板): iteration-0
    deltas are RAW model fragments, so a bare '[tool]' echo line would flash
    live long before the persistence-layer strip runs. Wrap the on_delta
    hook: hold any '['-initial tail line undecided until its newline proves
    it (bare registered echo → dropped with its newline; anything else →
    released byte-exact). A registered echo held at stream end is never
    flushed — the settled (sanitized) envelope replaces the bubble, so the
    echo simply never exists for the user.
    """
    held = ""

    async def on_delta(fragment: str) -> None:
        nonlocal held
        text = held + fragment
        held = ""
        if not text:
            return
        *body, tail = text.split("\n")
        # The decided (newline-terminated) segment gets the same transform
        # as the persistence strip: echo text out, 3+ newline runs collapse
        # to the paragraph seam — so the live bubble and the settled row
        # read identically.
        out = ""
        if body:
            kept = [line for line in body if not _is_tool_echo_line(line)]
            segment = "".join(line + "\n" for line in kept)
            out = re.sub(r"\n{3,}", "\n\n", segment)
        if tail:
            if not _TOOL_ECHO_PREFIX.match(tail):
                out += tail  # can never complete into an echo — prose
            elif _TOOL_ECHO_LINE.match(tail.strip()) and not _is_tool_echo_line(tail):
                out += tail  # a complete bracket line, but unregistered — prose
            else:
                held = tail  # undecided: still forming toward a registered echo
        if out:
            await emit(out)

    return on_delta
