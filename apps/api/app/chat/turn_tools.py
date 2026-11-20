"""The chat turn's tool set (ADR-077 判词② — action union 的机械翻译).

Declarations only: name + model-facing description + params model. The
executions live with the turn runners (``plan_turn.py`` / ``propose_turn.py``)
because they need the service layer's machinery (the ask_user machinery,
the run birthplace, the wiring door) — this module deliberately imports NOTHING from
the chat service so the import DAG stays one-directional:

    schemas ← turn_tools ← intent ← service ← plan_turn / propose_turn

    (turn_tools ← perception: the read registry's executes import the
    pipeline layer DEFERRED, so this module's own import stays light)

Tool names are model-facing only — they never surface in user copy (简报 §3
禁令). The PLAN_TOOLS / CHAT_TOOLS lists are the TERMINAL set (终态工具一调
即停); the NON-terminal read tools are the perception family's projections
below (T2b — ``app/chat/perception/`` is their registry home).

Description discipline (注册表条目扰动 = prompt 扰动): terse behavioral
contracts — WHEN to call, what the call does, what speech must precede it.
The parameter semantics live in the params models' Field descriptions; the
asking strategy / naming / disclosure rules stay in the system templates.
"""

import re
from copy import deepcopy
from dataclasses import replace

from app.agents.tool_loop import ChatTool, NATIVE_PRESENTATION, ToolPresentation, ToolPresentationVariant, ToolRejected, prune_wire_parameters
from app.chat.editor import EDITOR_NAMES, EDITOR_TOOLS
from app.chat.perception import perception_chat_tools
from app.models.schemas import (
    AnalyzeBrandArgs,
    AnnotateNarrationArgs,
    ChatAnswerArgs,
    ChatAskArgs,
    EditGraphArgs,
    GetNarrationAlignmentArgs,
    ImportSfxArgs,
    PlanAnswerArgs,
    PlanAskArgs,
    AlignRecordingArgs,
    PresentPlanArgs,
    ProposeTasksArgs,
    RetryUploadArgs,
    ReviewVideoArgs,
    SearchSfxArgs,
    SelectMusicArgs,
    SelectVideoPresetArgs,
    ShowMusicCandidatesArgs,
    ShowVideoPresetsArgs,
    StartRunArgs,
)

MAX_DESIGN_CORRECTIONS_PER_TURN = 2


def video_rejection_stop(
    current: ToolRejected, previous: tuple[ToolRejected, ...]
) -> bool:
    """Bound failed video design attempts without touching other tool loops.

    An exact repeated candidate signature stops on the second failure. When a
    rejected Composition carries a candidate digest, the same error text with
    a new digest is a materially changed attempt, not no-progress. Different
    validation/execution errors may still be genuine repairs, so they retain
    two more attempts; the third design rejection in one turn ends the loop
    regardless of signature. Accepted reads and successful designs do not
    erase the failure budget: this is a per-turn failed-design cap, not the
    deferred unified nested-LLM budget.
    """
    if current.tool_name != "design_video":
        return False
    history = (*previous, current)
    if previous:
        last = previous[-1]
        if (
            last.tool_name == current.tool_name
            and last.kind == current.kind
            and last.detail == current.detail
            and last.candidate_digest == current.candidate_digest
        ):
            return True
    return sum(event.tool_name == "design_video" for event in history) >= 3


_DESIGN_VIDEO_DESCRIPTION = (
    "通过向服务端工作草稿写入完整值构建视频。只写本次要处理的设置、来源、Scenes、Tracks、Clips 或 Transitions，未写入的范围保持原状。"
    "新轨道的首批 Clip 直接放入该 Track 的 clips。单独写 Clip 时，clips 项格式为 {track_id, clip}。save=false 将修改合入工作草稿。"
    "save=true 仅校验并保存已有 draft_ref，不附新的内容。保存不会启动制作。"
)


def _design_video_wire_view(description: str, parameters: dict) -> tuple[str, dict]:
    from app.config import settings

    pruned = deepcopy(parameters)
    if settings.component_bake_enabled:
        return description, pruned
    pruned = prune_wire_parameters(pruned, {"skill_resource"})
    producer = pruned.get("$defs", {}).get("GeneratorObject", {}).get("properties", {}).get("producer", {})
    if isinstance(producer.get("enum"), list):
        producer["enum"] = [item for item in producer["enum"] if item != "remotion-project"]
    return description + "当前部署不支持 remotion-project。", pruned


def _design_video_tool() -> ChatTool:
    from app.tools.video.design import CompositionDesignVideoArgs

    return ChatTool(
        name="design_video",
        terminal=False,
        description=_DESIGN_VIDEO_DESCRIPTION,
        params_model=CompositionDesignVideoArgs,
        wire_view=_design_video_wire_view,
        draftable=True,
        presentation=ToolPresentation(
            kind="draft", active_key="chat.activity.videoDesign",
            done_key="chat.activity.videoDesignDone", defer_start=True,
            policy="design", receipt_kind="component",
        ),
    )


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


def _review_working_draft_tool() -> ChatTool:
    from app.tools.video.preview import ReviewWorkingDraftArgs

    return ChatTool(
        name="review_working_draft",
        terminal=False,
        draft_reader=True,
        description=(
            "只传 draft_ref 可检查服务端选择的下一个限定连续时间窗。查看所附 MP4 和代表帧，再针对其 evidence_id 记录观察与结论。"
            "窗口、证据标识和审阅状态由服务端管理。草稿发生变化后，保存前须取得新证据。"
        ),
        params_model=ReviewWorkingDraftArgs,
        presentation=ToolPresentation(
            kind="draft", active_key="chat.activity.videoReview",
            done_key="chat.activity.videoReviewDone", defer_start=True,
            policy="working_draft_review", receipt_kind="video_draft_review",
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
        "将该 ID 传给 prepare_video_materials 的 material_music_ids，启动草稿时把返回的快照用作 music_snapshot_id。修改已保存版本需使用支持的修订 Op。"
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


def _verbatim_copy_requested(user_text: str) -> bool:
    return bool(re.search(
        r"逐字|一字不差|原文不变|不得改写|exact(?:\s+\w+)*\s+copy|verbatim",
        user_text, re.IGNORECASE,
    ))


def _music_choice_requested(user_text: str) -> bool:
    has_music = bool(re.search(r"音乐|配乐|music", user_text, re.IGNORECASE))
    has_choice = bool(re.search(
        r"候选|试听|比较|选择|挑选|选一首|candidate|compare|listen|choose|pick",
        user_text, re.IGNORECASE,
    ))
    return has_music and has_choice


def _pending_facts(message) -> dict | None:
    if message is None:
        return None
    intent = getattr(message, "intent", None) or {}
    return {
        "message_id": str(getattr(message, "id", "")),
        "content": getattr(message, "content", None),
        "question": getattr(message, "question", None) or intent.get("question"),
    }


def _named_reference(value, key: str) -> str | None:
    if isinstance(value, dict):
        if isinstance(value.get(key), str):
            return value[key]
        for nested in value.values():
            found = _named_reference(nested, key)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _named_reference(nested, key)
            if found:
                return found
    return None


def resolve_video_stage(
    *, tools: list[ChatTool], drafts, snapshot, user_text: str = "",
    pending_question=None, target_hint=None, readiness=None,
) -> dict:
    """Resolve current evidence before projecting the target and tool stage."""
    from app.agents.working_drafts import working_draft_review_facts

    resources = [
        resource for _key, resource in (getattr(snapshot, "resources", ()) or ())
        if resource.get("kind") == "composition"
    ]
    pending = _pending_facts(pending_question)
    if readiness is not None and readiness.task_kind == "website_promo":
        gated = {"draft": None, "target": None, "pending": pending, "readiness": readiness}
        if readiness.capture_failed or not (readiness.text_ready and readiness.required_views_ready):
            return {"stage": "source_preparing", **gated}
        if not readiness.brand_profile_ready:
            return {"stage": "briefing", **gated}
        if readiness.required_next_action == "ask_user" or (
            pending and (pending.get("question") or {}).get("items")
        ):
            return {"stage": "briefing", **gated}
    hint = target_hint or {}
    if not isinstance(hint, dict):
        hint = {"base_ref": getattr(hint, "base_ref", None)}
    hinted_draft = _named_reference(pending, "draft_id") or _named_reference(hint, "draft_id")
    explicit_draft = hinted_draft or next(
        (draft.candidate_id for draft in drafts if draft.candidate_id in user_text), None
    )
    if explicit_draft is None and re.search(r"\b(?:working\s+)?draft\b|草稿", user_text, re.IGNORECASE):
        explicit_draft = drafts[0].candidate_id if len(drafts) == 1 else None
    selected_draft = next(
        (draft for draft in drafts if draft.candidate_id == explicit_draft), None
    )
    if selected_draft is None and len(drafts) == 1 and (not resources or explicit_draft):
        selected_draft = drafts[0]
    if selected_draft is not None:
        facts = working_draft_review_facts(selected_draft.arguments)
        has_content = bool((selected_draft.arguments.get("content") or {}).get("scenes"))
        sequential_requested = bool(re.search(
            r"(?:^|[。！？；，,\s])(?:请)?按(?:播放顺序|幕)(?:审查|审片|检查)|"
            r"(?:^|[.!?]\s+)(?:please\s+)?(?:review|check)\b[^.!?\n]*\b(?:in playback order|scene by scene)\b",
            user_text, re.IGNORECASE,
        ))
        review_requested = facts["review_started"] or sequential_requested
        complete_without_review = bool(facts["scenes"]) and all(
            scene["clip_ids"] for scene in facts["scenes"]
        )
        save_deferred = bool(re.search(
            r"(?:do\s+not|don't|never)\s+save\b|\bnot\s+save\b|"
            r"不(?:要|用)?保存|暂不保存|先不保存",
            user_text, re.IGNORECASE,
        ))
        website_draft = readiness is not None and readiness.task_kind == "website_promo"
        empty_timeline = not any(scene["clip_ids"] for scene in facts["scenes"])
        if empty_timeline and not facts["awaiting_judgment"] and not selected_draft.errors:
            stage = "draft_build"
        elif website_draft and not review_requested:
            stage = "draft_build"
        elif selected_draft.errors:
            stage = "draft_repair"
        elif complete_without_review and not review_requested:
            stage = "draft_hold" if save_deferred else "draft_finalize"
        elif not has_content or not review_requested:
            stage = "draft_build"
        elif facts["open_issues"] and not facts["unreviewed_ranges_seconds"] and not facts["awaiting_judgment"]:
            stage = "draft_repair"
        elif facts["save_ready"] and facts["review_started"]:
            stage = "draft_finalize"
        else:
            stage = "draft_review"
        return {"stage": stage, "draft": selected_draft, "target": None, "pending": pending, "empty_timeline": empty_timeline}
    if resources or drafts:
        return {"stage": "resolve_target", "draft": None, "target": None, "candidates": resources, "pending": pending}
    return {
        "stage": "draft_build" if any(tool.name == "design_video" for tool in tools) else "none",
        "draft": None,
        "target": None,
        "pending": pending,
    }


def _website_briefing_question_wire(
    description: str, parameters: dict, missing_slots: list[str], known_direction: dict[str, str]
) -> tuple[str, dict]:
    parameters = prune_wire_parameters(parameters, {
        "options", "slot", "recommended_id", "brief", "material_text",
        "material_urls", "allow_freeform", "pending_disposition",
    })
    properties = parameters["properties"]
    properties["question"]["description"] = "用对话语言为整份表单写简短的总标题，例如「宣传片制作偏好」。每一页的具体问题写在 items 中。"
    local_string = {"type": "string", "minLength": 1}
    language_code = {"type": "string", "description": "BCP 47 语言代码。"}

    def fields(**properties):
        return {
            "type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False,
        }

    option_values = {
        "production_direction": local_string,
        "target_seconds": {"type": "integer", "minimum": 1},
        "narration_language": language_code,
        "subtitle_languages": {"type": "array", "items": language_code, "minItems": 1},
        "aspect": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
    }
    direction_question = "这支片会在哪里播放？你希望我们怎样讲这个故事？"
    if "purpose" in known_direction:
        direction_question = "在你选定的播放场合，你希望我们怎样讲这个故事？"
    elif "narrative_mode" in known_direction:
        direction_question = "刚才讨论的这支片会在哪里播放？"
    questions = {
        "production_direction": (
            f"请用用户的语言询问：{direction_question} 每个选项的标签和值均写明播放场合及根据网站证据建议的叙事方式，保留用户已说明的条件。受众信息放在 Brief 中，来源 URL 用于指明调研素材。"
        ),
        "target_seconds": "询问期望片长，标签注明秒数，值为对应的整数秒。",
        "narration_language": "询问旁白要说哪种语言。每个选项标签只写一种语言。",
        "subtitle_languages": "询问字幕需要哪些语言。两种候选语言应分别提供单语选项，也可以另给双语选项。每个选项的 value 都是语言代码数组。",
        "aspect": "询问用户需要什么画幅，标签和值都用画面比例。",
    }
    properties["items"] = {
        "type": "array", "minItems": len(missing_slots), "maxItems": len(missing_slots),
        "description": (
            "按顺序在本组中各询问一次：" + ", ".join(missing_slots)
            + "。问题和用户可见的所有选项文字均使用对话语言。"
        ),
        "items": {"anyOf": [
            fields(
                slot={"type": "string", "enum": [slot]},
                question={**local_string, "description": questions[slot]},
                options={"type": "array", "minItems": 1, "maxItems": 3,
                         "items": fields(label=local_string, value=option_values[slot])},
            ) for slot in missing_slots
        ]},
    }
    parameters["required"] = ["question", "items", "default_path"]
    return (
        "用对话语言展示一份澄清表单。每个待决定的事项各有问题和选项，用户一次提交整份表单。",
        prune_wire_parameters(parameters, set()),
    )


def video_round_tools(
    tools: list[ChatTool], *, resolution: dict, snapshot, skill=None,
    material_pending: bool = False, package_sessions: dict | None = None,
    user_text: str = "",
) -> list[ChatTool]:
    """Project declarations from the same resolved target used by the prompt."""
    from app.tools.video.design import explicit_design_constraints

    stage = resolution["stage"]
    active_draft = resolution.get("draft") is not None
    draft_arguments = resolution["draft"].arguments if active_draft else None
    project_facts = next(
        (
            resource for _key, resource in (getattr(snapshot, "resources", ()) or ())
            if resource.get("kind") == "project"
        ),
        {},
    )
    user_constraints = resolution.get("user_constraints")
    if user_constraints is None:
        user_constraints = explicit_design_constraints(
            user_text,
            constraints=project_facts.get("user_stated_constraints") or (),
            draft=draft_arguments,
        )
        resolution["user_constraints"] = user_constraints
    target = resolution.get("target")
    has_saved_version = target is not None or bool(
        snapshot is not None and (
            any(key.startswith("composition:") for key in snapshot.keys)
            or any(resource.get("kind") == "composition" for _key, resource in snapshot.resources)
        )
    )
    has_prepared_sources = bool(
        snapshot is not None and any(key.startswith("snapshot:") for key in snapshot.keys)
    )
    package = (
        package_sessions.get(skill.model_dump_json())
        if package_sessions is not None and skill is not None else None
    )
    defer_design = (
        not active_draft and not has_saved_version
        and material_pending and not has_prepared_sources
    )
    readiness = resolution.get("readiness")
    stage_tools = {
        "source_preparing": (
            {"answer"} if readiness is not None and readiness.capture_failed
            else {"prepare_video_materials", "answer"}
        ),
        "briefing": {"analyze_brand", "answer"},
        "resolve_target": {"ask_user", "answer", "get_video_version", "read_conversation_context"},
        "draft_build": {
            "ask_user", "answer", "read_conversation_context",
            "get_understanding", "get_web_page", "get_asset", "list_project_media",
            "get_graph", "get_node", "edit_graph",
            "list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview",
            "prepare_video_materials", "capture_web", "design_video", "review_working_draft",
            "align_recording", "get_narration_alignment", "annotate_narration",
            "search_music", "show_music_candidates", "select_music",
            "show_video_presets", "select_video_preset", "search_sfx", "import_sfx",
        },
        "draft_review": {"review_working_draft", "ask_user", "answer", "read_conversation_context"},
        "draft_repair": {"design_video", "ask_user", "answer", "read_conversation_context"},
        "draft_finalize": {"design_video", "answer", "read_conversation_context"},
        "draft_hold": {"answer", "read_conversation_context"},
    }
    if resolution.get("empty_timeline"):
        stage_tools["draft_build"].discard("review_working_draft")
    if stage == "briefing" and readiness.brand_profile_ready:
        stage_tools["briefing"] = {"answer"} if resolution.get("pending") else {"ask_user"}
    if stage == "draft_build" and not active_draft and readiness and readiness.task_kind == "website_promo":
        stage_tools["draft_build"].discard("ask_user")
    review_facts = {}
    if stage == "draft_review" and active_draft:
        from app.agents.working_drafts import working_draft_review_facts

        review_facts = working_draft_review_facts(resolution["draft"].arguments)
        if review_facts["confirmation_blocked"]:
            stage_tools["draft_review"] = {"answer"}
    focus_clip_ids: list[str] = []
    focus_element_ids: list[str] = []
    complete_repair = False
    if stage == "draft_repair" and active_draft:
        from app.agents.working_drafts import working_draft_review_facts

        draft_facts = working_draft_review_facts(resolution["draft"].arguments)
        complete_repair = bool(draft_facts["scenes"]) and all(
            scene["clip_ids"] for scene in draft_facts["scenes"]
        ) and not draft_facts["open_issues"]
        editable = draft_facts["editable_targets"]
        issue_clip_ids = {
            clip_id for issue in draft_facts["open_issues"] for clip_id in issue.get("clip_ids") or []
        }
        targets = [clip for clip in editable if not issue_clip_ids or clip.get("clip_id") in issue_clip_ids]
        focus_clip_ids = [clip["clip_id"] for clip in targets if (clip.get("object") or {}).get("kind") == "web"]
        snapshots = {
            str(resource.get("snapshot_id")): resource
            for key, resource in (getattr(snapshot, "resources", ()) or ())
            if key.startswith("snapshot:")
        }
        for clip in targets:
            source = clip.get("source") or {}
            view_id = (clip.get("object") or {}).get("view_id")
            view = next(
                (
                    view for view in (snapshots.get(str(source.get("snapshot_id"))) or {}).get("views") or []
                    if view.get("view_id") == view_id
                ),
                None,
            )
            focus_element_ids.extend(
                str(element["id"]) for element in (view or {}).get("targets") or [] if element.get("id")
            )
        focus_element_ids = list(dict.fromkeys(focus_element_ids))
    projected = []
    for tool in tools:
        # Video rounds never need the manual Canvas read/write tools. Keep
        # their existing manual-surface executors, but do not spend model
        # context on unrelated graph operations.
        if tool.name in {"get_graph", "get_node", "edit_graph"}:
            continue
        if tool.name == "create_video":
            continue  # The native first-version seat is offered by the editor projection.
        if tool.name in EDITOR_NAMES:
            if has_saved_version or tool.name.startswith("generate_"):
                projected.append(tool)
            continue
        if stage in stage_tools and tool.name not in stage_tools[stage]:
            continue
        if (
            stage == "draft_build"
            and tool.name in {"show_music_candidates", "select_music"}
            and not _music_choice_requested(user_text)
        ):
            continue
        if skill is not None and tool.name == "start_run" and not has_saved_version:
            continue
        if defer_design and tool.name == "design_video":
            continue
        if tool.name in {"present_plan", "propose_tasks"} and (
            (active_draft and not (draft_arguments or {}).get("design", {}).get("scene_assets"))
            or (skill is not None and not has_saved_version)
        ):
            continue
        if tool.name in {"get_video_version"} and not has_saved_version:
            continue
        if (
            stage in {"briefing", "draft_build"}
            and tool.name == "ask_user"
            and readiness is not None
            and readiness.brand_profile_ready
            and readiness.brief_missing_slots
        ):
            from app.chat.readiness import stated_direction_inputs

            projected.append(replace(
                tool,
                wire_view=lambda description, parameters: (
                    _website_briefing_question_wire(
                        description, parameters, readiness.brief_missing_slots,
                        stated_direction_inputs(readiness.brief),
                    )
                ),
            ))
            continue
        if tool.name == "review_working_draft":
            draft = resolution.get("draft")
            if draft is None or not (draft.arguments.get("content") or {}).get("scenes"):
                continue
            awaiting = review_facts.get("awaiting_judgment", False)
            observed_required = any(
                item["representative_frame"] and item["evidence_id"] in review_facts["unjudged_evidence_ids"]
                for item in review_facts.get("evidence", [])
            )

            def review_wire(description: str, parameters: dict, *, needs_judgment=awaiting, needs_observation=observed_required, initial=stage == "draft_build"):
                if needs_judgment:
                    parameters = prune_wire_parameters(parameters, {"scene_id", "include_previous_scene"})
                    parameters["required"] = list(dict.fromkeys([
                        *parameters.get("required", []), "judgment",
                    ]))
                    if needs_observation:
                        parameters["$defs"]["WorkingDraftReviewJudgment"]["required"].append("observed")
                    return "为当前尚未判定的 evidence_id 记录结论，不要重复请求同一预览。", parameters
                if initial:
                    return (
                        "只有具体的动态疑问或用户要求时才启动局部预览。选择 scene_id，可附前一场衔接。只有用户要求开始顺序审阅时才省略 scene_id。",
                        prune_wire_parameters(parameters, {"judgment"}),
                    )
                return "获取服务端选定的下一段连续预览。", prune_wire_parameters(
                    parameters, {"judgment", "scene_id", "include_previous_scene"}
                )

            projected.append(replace(tool, wire_view=review_wire))
            continue
        if tool.name != "design_video":
            projected.append(tool)
            continue

        previous_wire = tool.wire_view
        allow_skill_resource = (
            stage == "draft_build" and getattr(package, "package_identity", None) is not None
        )
        if active_draft:
            def continuing_wire(description: str, parameters: dict, *, previous=previous_wire, current_stage=stage, skill_resources=allow_skill_resource, high_level=not allow_skill_resource, constraints=user_constraints, repair_complete=complete_repair):
                if previous is not None:
                    description, parameters = previous(description, parameters)
                parameters = _explicit_constraint_wire(parameters, constraints, include_fixed=False)
                hidden = {"composition_id"}
                if not skill_resources:
                    hidden.add("skill_resource")
                parameters = prune_wire_parameters(parameters, hidden)
                parameters["required"] = list(dict.fromkeys([
                    *parameters.get("required", []), "draft_ref",
                ]))
                if current_stage == "draft_finalize":
                    allowed = {"draft_ref", "save", "scrub", "pending_disposition"}
                    parameters = prune_wire_parameters(
                        parameters, set(parameters.get("properties") or {}) - allowed
                    )
                    return "用 save=true 仅保存已审阅的现有 draft_ref，不再写入内容。", parameters
                if current_stage == "draft_repair":
                    if focus_clip_ids and focus_element_ids:
                        allowed = {"draft_ref", "focus_clip_id", "focus_element_id", "pending_disposition"}
                        parameters = prune_wire_parameters(
                            parameters, set(parameters.get("properties") or {}) - allowed
                        )
                        parameters["properties"]["focus_clip_id"]["enum"] = focus_clip_ids
                        parameters["properties"]["focus_element_id"]["enum"] = focus_element_ids
                        parameters["required"] = ["draft_ref", "focus_clip_id", "focus_element_id"]
                        return "使用固定视图中的一个元素修复一个网页 Clip 的构图。", parameters
                    if repair_complete and high_level:
                        allowed = {"draft_ref", "save", "pending_disposition"}
                        parameters = prune_wire_parameters(
                            parameters, set(parameters.get("properties") or {}) - allowed
                        )
                        return (
                            "计划中的 Scene 均已在当前草稿内。不重开计划或新增字段。仅用 save=true 保存现有 draft_ref，不写内容。",
                            parameters,
                        )
                if high_level:
                    allowed = {
                        "draft_ref", "scene", "scene_assets", "narration_update",
                        "save", "scrub", "pending_disposition",
                    }
                    if (draft_arguments or {}).get("design", {}).get("scene_assets"):
                        allowed.difference_update({"save", "scrub"})
                    parameters = prune_wire_parameters(
                        parameters, set(parameters.get("properties") or {}) - allowed
                    )
                    return (
                        "编写一个当前 Scene、更新其 SceneAssetSpec，或在对齐达到 READY 后执行一次 narration_update。"
                        "场景素材准备阶段只保留未保存的工作草稿，不保存 CompositionVersion 或附加预览。服务端推导来源标识、真实提示点、Tracks、Clips、Objects 及整数时序。",
                        parameters,
                    )
                allowed = {
                    "draft_ref", "scene_id", "tracks", "save", "scrub", "pending_disposition",
                    "copy_references", "verbatim_copy",
                }
                if skill_resources:
                    allowed.add("skill_resource")
                parameters = prune_wire_parameters(
                    parameters, set(parameters.get("properties") or {}) - allowed
                )
                return (
                    "用最新 draft_ref 和 scene_id 续写工作草稿中一个已有场景。tracks[].clips 只放该场完整的 Clip，无顶层 clips 数组。"
                    "复用 draft_tracks 中已有 Track 的 ID、kind、role、order；服务端保留此次写入范围以外的所有 Clip。新 Track 一次声明完整的 kind、role、order。"
                    "动画和 object 同放在 Clip 上。最终调用只设 save=true 校验并保存现有 draft_ref，不传 scene_id 或写入内容。",
                    parameters,
                )

            projected.append(replace(
                tool,
                description="续写或保存当前视频工作草稿。",
                wire_view=continuing_wire,
            ))
        else:
            def initial_wire(description: str, parameters: dict, *, previous=previous_wire, skill_resources=allow_skill_resource, high_level=not allow_skill_resource, constraints=user_constraints):
                if previous is not None:
                    description, parameters = previous(description, parameters)
                parameters = _explicit_constraint_wire(parameters, constraints, include_fixed=True)
                hidden = {"draft_ref"} if has_saved_version else {"draft_ref", "composition_id"}
                if not skill_resources:
                    hidden.add("skill_resource")
                if high_level:
                    hidden.update({
                        "settings", "sources", "scenes", "tracks", "clips", "transitions", "scene_id",
                        "remove_scene_ids", "remove_track_ids", "remove_clip_ids", "remove_transition_ids",
                        "save", "scrub", "skill_resource", "scene", "focus_clip_id", "focus_element_id",
                        "copy_references",
                    })
                    if not _verbatim_copy_requested(user_text):
                        hidden.add("verbatim_copy")
                    description = (
                        "用 scene_plan、source_ids 和可选 scene_assets/music_snapshot_id 开始工作草稿。scene_plan 只决定叙事顺序，scene_assets 只为其中已有的场景 ID 附上当前画面要求。"
                        "服务端推导设置、来源绑定及初始时序。先准备所需画面，再在后续 Scene 写入中绑定固定快照。保存不会启动制作。"
                    )
                return description, prune_wire_parameters(parameters, hidden)

            projected.append(replace(tool, wire_view=initial_wire))
    return projected


def _video_project_tools() -> list[ChatTool]:
    return [
        *_skill_authoring_read_tools(),
        *_video_material_tools(),
        _design_video_tool(),
        *EDITOR_TOOLS,
        _REVIEW_VIDEO_TOOL,
        _review_working_draft_tool(),
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
        name="present_plan",
        description="展示需要用户确认的已注册后台任务及费用。",
        params_model=PresentPlanArgs,
        presentation=ToolPresentation(
            kind="draft", active_key="chat.activity.draft", done_key="chat.activity.draftDone",
        ),
    ),
    ChatTool(
        name="ask_user",
        presentation=NATIVE_PRESENTATION,
        description=(
            "集中澄清最影响结果的问题。问题及选项会展示给用户，回答或安全跳过后可继续。开放探索和浏览时，也可把值得比较的具体方向作为选项，标记倾向的一项，并允许跳过。"
        ),
        params_model=PlanAskArgs,
    ),
    ChatTool(
        name="edit_graph",
        description=(
            "仅在用户明确打开的手动 Canvas 中增删改查。所有相关操作必须在一次终结调用中提交：同次创建并连接节点（新节点用 add_node.after，或用 connect 操作）。按要求编辑、断连和删除。不会添加任务或成品投影、启动 Run 或打开 Canvas。"
        ),
        params_model=EditGraphArgs,
        presentation=ToolPresentation(
            kind="draft", active_key="chat.activity.edit", done_key="chat.activity.editDone",
        ),
    ),
    ChatTool(
        name="start_run",
        description=(
            "启动已确认方案的 Run。只有用户确认了已展示的方案才调用，例如在确认阶段表示“没问题，开始吧”。若是要求修改，调用 present_plan。"
        ),
        params_model=StartRunArgs,
        presentation=ToolPresentation(
            kind="run", active_key="chat.activity.run", done_key="chat.activity.runDone",
        ),
    ),
    ChatTool(
        name="answer",
        presentation=NATIVE_PRESENTATION,
        description=(
            "仅提供信息，如能力说明、项目解释或闲聊，不创建方案或 Run。先在消息正文中给出答复，同时调用本工具；没有正文的 answer 会被拒绝。"
            "用户已点名的工作在创意方向达成一致后应展示为方案。官网视频在商定方向阶段可用有依据的总结及下一步问题结束本轮。"
        ),
        params_model=PlanAnswerArgs,
    ),
]

# Chat terminal actions: production, manual Graph CRUD, recovery and answers.
CHAT_TOOLS = [
    ChatTool(
        name="propose_tasks",
        description="展示需要用户确认的已注册后台任务及费用。",
        params_model=ProposeTasksArgs,
        presentation=ToolPresentation(
            kind="draft", active_key="chat.activity.draft", done_key="chat.activity.draftDone",
        ),
    ),
    ChatTool(
        name="edit_graph",
        description=(
            "仅在用户明确打开的手动 Canvas 中增删改查。所有相关操作必须在一次终结调用中提交：同次创建并连接节点（新节点用 add_node.after，或用 connect 操作）。按要求编辑、断连和删除。不会添加任务或成品投影、启动 Run 或打开 Canvas。"
        ),
        params_model=EditGraphArgs,
        presentation=ToolPresentation(
            kind="draft", active_key="chat.activity.edit", done_key="chat.activity.editDone",
        ),
    ),
    # Production and recovery use the current Composition and Run contracts.
    ChatTool(
        name="retry_upload",
        terminal=False,
        description=(
            "仅重传已经渲染完成但上传失败的视频。复用成片缓存，不重新渲染。若无缓存，如实返回需要重新渲染的结果。"
        ),
        params_model=RetryUploadArgs,
        presentation=ToolPresentation(
            kind="read", active_key="chat.activity.upload", done_key="chat.activity.uploadDone",
        ),
    ),
    # Saved videos are revised only through the current Composition write door.
    ChatTool(
        name="ask_user",
        presentation=NATIVE_PRESENTATION,
        description=(
            "集中澄清最影响下一步的问题，并展示问题和选项。开放探索和浏览时可提供值得选择的具体方向，标记倾向的一项，并允许用户安全跳过。"
        ),
        params_model=ChatAskArgs,
    ),
    ChatTool(
        name="answer",
        presentation=NATIVE_PRESENTATION,
        description=(
            "仅提供信息，如能力说明、执行进度（先调用 get_run_status）、已有结果解释或闲聊。工作请求交给提案工具，有歧义时调用 ask_user，不要用 answer 回避。"
            "官网视频在尚无方案的创意方向阶段可在此结束；其他工作应展示提案或执行适当的修订。须在消息正文中给出答复并调用 answer，没有正文的调用会被拒绝。"
        ),
        params_model=ChatAnswerArgs,
    ),
]
PLAN_READ_TOOLS = [
    *perception_chat_tools(
        "get_understanding", "get_asset", "search_music", "search_transcript",
        "get_segment", "get_graph", "get_node", "get_web_page", "search_web", "list_project_media",
    ),
    *_video_project_tools(),
]
CHAT_READ_TOOLS = [
    *perception_chat_tools(
        "get_understanding", "get_run_status", "list_runs", "get_pending_plan",
        "get_asset", "search_music", "search_transcript", "get_segment", "get_graph",
        "get_web_page", "search_web", "list_project_media",
    ),
    *_video_project_tools(),
]


# ── 工具名回响 sanitizer (2026-09-30 用户拍板 — 彻底删掉) ──────────────────
# The model sometimes echoes the tool it is calling as a BARE bracketed line
# of prose ('[start_run]'): the name saturates its prompt (it must — it is
# the tool's name), and the bracket shape is the function-call markup of its
# pretraining. The real call rides the native tool channel; the echo is pure
# noise the spoken sentence already covers — and the user should never see
# machine vocabulary. Strip lines that are EXACTLY one registered tool's
# name in brackets; a name mentioned mid-sentence is prose and stays.
_TOOL_ECHO_NAMES = frozenset(
    tool.name for tool in [*PLAN_TOOLS, *CHAT_TOOLS, *CHAT_READ_TOOLS]
) | {"wrap_up"}  # the trigger turn's terminal (its module imports ours)
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
