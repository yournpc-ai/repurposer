"""Project the current Composition, its evidence and the available Chat tools."""

import json
import re
from dataclasses import replace

from app.agents.base import jinja_env
from app.agents.tool_loop import RoundAssembly, prune_wire_parameters
from app.chat.editor import EDITOR_NAMES, project_editor_reply
from app.tools import tool_catalog_lines

ChatMode = str


def chat_system(mode: ChatMode, *, available_tools: list | None = None) -> str:
    from app.config import settings

    return jinja_env.get_template("chat/system.j2").render(
        mode=mode,
        tool_names={tool.name for tool in available_tools or []},
        tool_lines=tool_catalog_lines(),
        menu_lines="",
        include_menu=False,
        wiring_lines="",
        chat_loop=mode == "conversation",
        component_bake_enabled=settings.component_bake_enabled,
    )


def _creative_state_projection(creative_state) -> dict:
    def compact(value):
        if isinstance(value, dict):
            return {
                key: compact(item) for key, item in value.items()
                if key not in {"source_refs", "content_digest"}
            }
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    return compact(creative_state.model_dump(mode="json"))


def _source_creation_facts(resources) -> list[dict]:
    facts = []
    for _, resource in resources:
        if not resource.get("snapshot_id"):
            continue
        item = {
            key: value for key, value in resource.items()
            if key not in {"storage_key", "origin_project_id"}
        }
        if item.get("kind") == "web":
            item["citable_lines"] = (item.get("citable_lines") or [])[:120]
            item["views"] = [
                {**view, "targets": (view.get("targets") or [])[:80]}
                for view in item.get("views") or []
            ]
        facts.append(item)
    return facts[-24:]


def _native_creation_tools(tools, *, facts, readiness):
    from app.config import settings
    from app.chat.readiness import stated_direction_inputs
    from app.chat.turn_tools import _explicit_constraint_wire, _website_briefing_question_wire
    from app.models.schemas import ExternalSkillReference
    from app.tools.video.design import explicit_design_constraints

    resources = list(getattr(facts.get("snapshot"), "resources", ()) or ())
    project = next((resource for _, resource in resources if resource.get("kind") == "project"), {})
    state = facts.get("creative_state")
    pending = facts.get("pending_brief") or project.get("pending_brief") or getattr(state, "brief", None)
    constraints = explicit_design_constraints(
        facts.get("user_text") or "",
        constraints=project.get("user_stated_constraints") or (),
        brief=pending,
    )
    external = isinstance(facts.get("skill"), ExternalSkillReference)
    ask_website = (
        readiness.task_kind == "website_promo" and readiness.brand_profile_ready
        and readiness.brief_missing_slots
    )
    projected = []
    for tool in tools:
        if tool.name == "create_video":
            def creation_wire(description, parameters, *, constraints=constraints):
                parameters = _explicit_constraint_wire(parameters, constraints, include_fixed=True)
                if not external or not settings.component_bake_enabled:
                    parameters = prune_wire_parameters(parameters, {"skill_resource"})
                if not external:
                    description += "未绑定外部 Skill，不使用 skill_resource。"
                elif not settings.component_bake_enabled:
                    description += "当前部署不支持受控 Generator；使用现有图片、视频和原生文字。"
                return description, parameters

            projected.append(replace(tool, wire_view=creation_wire))
        elif tool.name == "ask_user" and ask_website:
            projected.append(replace(tool, wire_view=lambda description, parameters: (
                _website_briefing_question_wire(
                    description, parameters, readiness.brief_missing_slots,
                    stated_direction_inputs(readiness.brief),
                )
            )))
        else:
            projected.append(tool)
    return projected


def assemble_video_round(facts: dict) -> RoundAssembly:
    confirmation = facts.get("video_confirmation")
    if confirmation and confirmation["action"] in {"wait", "stale", "already_started", "start"}:
        action = confirmation["action"]
        rules = {
            "wait": "说明仍在展示该版本。",
            "stale": "说明引用的版本已过期，询问要使用哪一版。",
            "already_started": "按已有执行回执陈述状态，交付以确切产物为准。",
            "start": "请用户在原有费用确认中核对并批准报价。",
        }
        return RoundAssembly(
            tools=[tool for tool in facts["tools"] if tool.name == "answer"],
            system=f"用用户在本次对话中使用的语言作答。{rules[action]} 若只需告知情况，先在消息正文中说明，再调用 answer。",
            context=json.dumps({"video_confirmation": confirmation}, ensure_ascii=False),
            stage="video_confirmation", include_project_context=False,
            include_observation_media=False, opening_text=facts.get("user_text") or "",
        )

    snapshot = facts.get("snapshot")
    resources = list(getattr(snapshot, "resources", ()) or ())
    works = [r for _, r in resources if r.get("kind") == "composition"]
    user_text = facts.get("user_text") or ""
    draft_requested = re.search(r"初稿|草稿|分镜|\b(?:draft|storyboard)\b", user_text, re.I)
    additional_work = re.search(
        r"审片|检查|复看|修订|导出|交付|成片|\b(?:review|check|revise|render|export|deliver|mp4)\b",
        re.sub(r"不(?:要|用|需要)?(?:导出|交付|制作成片)|(?:do not|don't) (?:export|deliver|render)", "", user_text, flags=re.I),
        re.I,
    )
    if facts.get("version_saved") and (
        not works or (draft_requested and not additional_work and not facts.get("production_requested"))
    ):
        presentation = jinja_env.get_template("chat/_video_presentation.j2").render()
        return RoundAssembly(
            tools=[tool for tool in facts["tools"] if tool.name == "answer"],
            system="用用户在本次对话中使用的语言作答。作品已经保存。根据本次保存回执展示实际版本，然后调用 answer。\n" + presentation,
            context="当前视频轮次（目标和状态由服务端提供）：\n{\"video_stage\": \"version_present\"}",
            stage="version_present", include_project_context=False,
            include_observation_media=False, observation_tools=frozenset({"create_video"}),
        )

    pending = facts.get("pending_question")
    if callable(pending):
        pending = pending()
    from app.chat.readiness import compute_source_readiness

    creative_state = facts.get("creative_state")
    if callable(creative_state):
        creative_state = creative_state()
    hint = facts.get("target_hint") or {}
    if confirmation and confirmation["action"] == "produce" and not hint:
        ref = confirmation["base_ref"]
        hint = {"composition_id": ref["composition_id"], "version_id": ref["composition_version_id"]}
    rejected_recovery = next((resource for _, resource in resources if resource.get("kind") == "working_draft_recovery"), None)
    if rejected_recovery and not works:
        return RoundAssembly(
            tools=[tool for tool in facts["tools"] if tool.name == "answer"],
            system="已有工作草稿无法安全转换，原记录仍然保留。说明没有保存新版本，也没有继续旧创作协议；如需另建作品必须先让用户明确。不得把当前请求当成空项目创建。",
            context=json.dumps({"working_draft_recovery": rejected_recovery}, ensure_ascii=False),
            stage="working_draft_unavailable", include_project_context=False,
            opening_text=user_text, enforce_offered_tools=True,
        )
    readiness = compute_source_readiness(
        user_text=user_text, source_text=facts.get("source_text"),
        assets=[r for _, r in resources if r.get("kind") == "asset"],
        snapshots=[r for _, r in resources if r.get("kind") == "web"],
        creative_state=creative_state, draft_present=bool(facts.get("drafts")),
        question_settled=facts.get("website_question_settled", False),
    )
    native_creation = (
        not works and not hint and not facts.get("drafts") and not facts.get("active_repair")
        and not facts.get("version_saved") and (not pending or facts.get("group_answer_submitted"))
        and any(tool.name == "create_video" for tool in facts["tools"])
    )
    if (native_creation or works or hint.get("unavailable") or hint.get("composition_id")) and not hint.get("draft_id"):
        selected = None
        if hint.get("composition_id"):
            selected = next((r for r in works if r["composition_id"] == hint["composition_id"]
                             and (not hint.get("version_id") or r["version_id"] == hint["version_id"])), None)
        elif not hint.get("unavailable"):
            project = next((r for _, r in resources if r.get("kind") == "project"), {})
            work_count = (project.get("resource_counts") or {}).get("composition", len(works))
            if len(works) == work_count == 1:
                selected = works[0]
            else:
                named = [r for r in works if r["composition_id"] in user_text
                         or (r.get("name") and r["name"] in user_text)]
                selected = named[0] if len(named) == 1 else None
        project = next((r for _, r in resources if r.get("kind") == "project"), None)
        context = {
            "works": [{k: r.get(k) for k in ("composition_id", "name", "version_id", "version")} for r in works],
            "referenced_output": hint if hint.get("output_id") else None,
            "selected": selected["base_ref"] if selected else None,
            "project": ({k: project.get(k) for k in ("title", "project_id", "user_stated_constraints")}
                        if project else None),
            "assets": [{k: r.get(k) for k in ("asset_id", "type", "name")}
                       for _, r in resources if r.get("kind") == "asset"][:24],
        }
        context["fixed_media"] = [
            {k: r[k] for k in ("snapshot_id", "kind", "duration_ticks", "title", "alignment") if r.get(k) is not None}
            for _, r in resources if r.get("snapshot_id") and r.get("kind") in ("audio", "image")
        ][-24:]
        if selected:
            context.update(clip_count=selected.get("clip_count"), scene_count=selected.get("scene_count"),
                           timebase=selected.get("timebase"), duration_ticks=selected.get("duration_ticks"),
                           selected_region=hint.get("selected_region"))
            if selected.get("timebase") and selected.get("duration_ticks") is not None:
                context["duration_seconds"] = selected["duration_ticks"] / selected["timebase"]
            if facts.get("version_saved") and selected.get("version") == 1:
                context["draft_saved_this_turn"] = selected["base_ref"]
        recent = facts.get("recent_edit") or {}
        if selected and recent.get("composition_id") == selected["composition_id"]:
            context["already_saved_this_turn"] = recent["applied"]
            if recent["version_id"] == selected["version_id"]:
                context["recently_edited_clips"] = list(recent["clips"].values())
        from app.chat.editor import requests_observation_first

        last_preview = facts.get("last_preview") or {}
        if selected and not recent and requests_observation_first(user_text):
            context["observation_requested_before_edit"] = "Inspect actual rendered footage before deciding whether anything needs changing."
        if selected and last_preview.get("version_id") == selected["version_id"]:
            context["observed_preview"] = last_preview
        names = set(EDITOR_NAMES) | {"read_conversation_context", "answer", "ask_user", "list_project_media", "review_video", "align_recording", "get_narration_alignment", "annotate_narration"}
        if not native_creation:
            names.discard("create_video")
        completed_delivery = facts.get("delivered") or {}
        if selected and (recent or facts.get("version_saved") or context.get("observed_preview")
                         or completed_delivery.get("composition_version_id") == selected["version_id"]):
            names.discard("ask_user")
        if native_creation:
            names.update({"prepare_video_materials", "get_asset", "get_understanding", "search_transcript"})
            names.difference_update({"export_video", "deliver_video"})
            source_resources = resources
            if readiness.task_kind == "website_promo":
                from app.chat.readiness import canonical_url

                urls = {canonical_url(url) for url in readiness.urls}
                source_ids = {
                    str(ref.snapshot_id)
                    for ref in [*(creative_state.source_refs if creative_state else []),
                                *(creative_state.brand_profile.source_refs
                                  if creative_state and creative_state.brand_profile else [])]
                }
                source_resources = [
                    (key, resource) for key, resource in resources
                    if resource.get("kind") == "project"
                    or canonical_url(str(resource.get("url") or resource.get("canonical_url") or "")) in urls
                    or str(resource.get("snapshot_id") or "") in source_ids
                ]
            context["available_sources"] = _source_creation_facts(source_resources)
            if facts.get("skill") is not None:
                names.update({"list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview"})
                reference = facts["skill"]
                context["skill_reference"] = (
                    reference.model_dump(mode="json") if hasattr(reference, "model_dump")
                    else reference if isinstance(reference, dict)
                    else {key: value for key in ("kind", "skill_id", "version", "skill_version_id")
                          if (value := getattr(reference, key, None)) is not None}
                )
                if snapshot is not None and snapshot.skill_method:
                    context["bound_skill_method"] = snapshot.skill_method
            if creative_state is not None:
                context["creative_state"] = _creative_state_projection(creative_state)
            if facts.get("material_pending") and not context["available_sources"]:
                names.discard("create_video")
            if facts.get("material_pending_line"):
                context["material_pending_line"] = facts["material_pending_line"]
            if readiness.task_kind == "website_promo":
                from app.chat.readiness import render_readiness_context

                names.update({"analyze_brand", "capture_web"})
                context["source_readiness"] = readiness.model_dump()
                context["source_preparation"] = render_readiness_context(readiness)
                required = readiness.required_next_action
                if required in {"prepare_video_materials", "analyze_brand"}:
                    names = {required, "answer"}
                elif required in {"answer", "ask_user"}:
                    names = {required, "answer"}
                elif not pending:
                    names.discard("ask_user")
                if required == "ask_user":
                    from app.chat.readiness import stated_direction_inputs

                    context["known_direction_inputs"] = stated_direction_inputs(readiness.brief)
        from app.chat.video_turn_seats import asks_for_export, draft_only_request
        delivery = facts.get("preceding_delivery") or {}
        if selected and delivery.get("composition_id") == selected["composition_id"]:
            context["preceding_reviewed_delivery"] = delivery
            if recent.get("version_id") == selected["version_id"]:
                delivered = facts.get("delivered") or {}
                exported = facts.get("exported") or {}
                context["revised_delivery"] = {
                    "requested_artifact": "Reviewed MP4 in this Chat, updated with the requested change",
                    "revised_version": selected["base_ref"],
                    "output": exported if exported.get("composition_version_id") == selected["version_id"] else None,
                    "chat_delivery": delivered if delivered.get("composition_version_id") == selected["version_id"] else None,
                }
        elif not asks_for_export(user_text) and not hint.get("output_id") and not confirmation:
            context["delivery_scope"] = "The opening does not explicitly request formal export. Complete the requested editing or preview and report the saved result. A separate formal export would require confirmation."
        if draft_only_request(user_text):
            context["delivery_scope"] = "Save the requested work and report any requested preview. Formal export is outside this request."
            context.pop("revised_delivery", None)
            names.discard("export_video")
            names.discard("deliver_video")
        if hint.get("output_id") and selected is None:
            context["revision_target_status"] = "The referenced Output is historical. Ask which baseline to use before editing."
            names = {"ask_user", "answer", "review_video"}

        def dialogue_wire(description, parameters):
            return description, prune_wire_parameters(parameters, {
                "brief", "material_text", "material_urls", "items", "slot",
            })

        tools = [t for t in facts["tools"] if t.name in names]
        if native_creation:
            tools = _native_creation_tools(tools, facts=facts, readiness=readiness)
        def terminal_wire(tool):
            previous = tool.wire_view

            def view(description, parameters):
                description, parameters = dialogue_wire(description, parameters)
                return previous(description, parameters) if previous is not None else (description, parameters)

            return replace(tool, wire_view=view, description=(
                "根据实际结果结束本轮；也可以直接在消息正文答复。" if tool.name == "answer" else
                "询问一个确定目标所需的问题。"
            ))

        tools = [terminal_wire(t) if t.name in {"answer", "ask_user"} else t for t in tools]
        if confirmation and confirmation["action"] == "produce":
            context["user_confirmed_export_of"] = confirmation["base_ref"]
        if facts.get("authorized_media"):
            context["completed_media_this_turn"] = {**facts["authorized_media"], "delivered_to_chat": facts["authorized_media"].get("role") != "export"}
            if facts["authorized_media"].get("role") == "export":
                context["authorized_deliverable"] = "The user approved the exact Output above. Review it and deliver that version when it meets the request. Respect instructions to retain the edit. Report defects if it cannot be delivered."
        if pending:
            context["pending_question"] = getattr(pending, "question", None)
        acknowledgment = None
        if facts.get("group_answer_submitted") and readiness.task_kind == "website_promo":
            context["questionnaire_acknowledged"] = "用户刚提交制作偏好；按其已选项继续，不重复询问。"
            seconds = readiness.brief.target_seconds.value
            if not facts.get("interim_prose_count"):
                if (facts.get("speech_language") or "").startswith("zh"):
                    film = f"这支 {seconds} 秒短片" if seconds else "这支短片"
                    acknowledgment = f"收到，我会按你选的方向安排{film}的开场和镜头顺序。"
                else:
                    length = f"{seconds}-second " if seconds else ""
                    acknowledgment = f"Got it. I’ll shape the {length}storyboard around your choices, starting with the opening."
        website_evidence_rule = (
            "官网宣传片取证：讨论创意前，先读懂网站定位、视觉识别和核心主张。固定的正文和所需页面 PNG 均可读取后，才可询问制作或风格偏好、生成图片或旁白、设计分镜。遵循 required_next_action。采集失败时，说明实际错误和可行的恢复方式，不得编造 BrandProfile。原生 ask_user 用一份结构化问卷集中询问缺失偏好。"
            + (jinja_env.get_template("chat/_pending_question.j2").render()
               if any(t.name == "ask_user" for t in tools) else "")
            if readiness.task_kind == "website_promo" else ""
        )
        return RoundAssembly(
            tools=tools,
            system="你是视频剪辑师。用本轮用户提问的语言回答。修改片段前，按需读取时间线定位目标。空项目按用户要求用 create_video 将镜头直接保存为可编辑作品。颜色、运动、时长、交付范围以用户原话为准。只要求调整和复看时，复看后答复；正式导出需要交付意图。目标不明确时询问。"
                   "可在同一响应提交独立的读取、素材生成或已知对象的修改。写入按声明次序保存。需要前项新标识时先看回执，再在下次决策引用。完成各项后再单独答复。根据已生成的素材、已保存动作和预览继续，已完成的要求只在观察到具体问题时再次修改。同窗对照按 earlier 与 current 的标记读图。构图以用户点名的主体与取景要求为准，留边与是否填满画布是不同选择。当前预览满足要求就结束，不追加未请求的构图、画幅或配音选择；素材取景限制改善时说明已看到的局限。采样范围限制用于如实陈述证据，不是继续寻找假设问题的理由；用户点名的内容已在当前版本得到观察且没有待修发现时，停止追加观察并完成用户要求的后续交付或答复。以当前版本已观察窗口和用户要求为依据，说明发现的问题及未检查范围。调整前后的几何与时间以版本数据为准。描述源取景时，source_clipped_px 是源画面被画布裁掉的像素，canvas_borders_px 是画布留边像素；source_clipped_px 大于 0 时不能声称完整源画面，canvas_borders_px 大于 0 时不能声称留边已消除，主体或文字是否被裁切仍以实际帧为准。face_evidence.face_fully_visible=false 时不能声称检测到的人脸完整或有安全边距；expanded_face_fully_visible=false 时不能声称头肩完整。人脸框和扩边区域不证明头发、肩膀完整或构图自然，未检测到时明确未知。几何坐标数组逐字段直接引用，不要重算成不同边界。静态图片来源不等于输出静止；sample_frames 中的像素差异只证明所列采样时点的变化，不证明未观察时段的运动，描述输出前先核对这些帧。只有实际收到可感知声音才能评价听感。播放范围取自 window_seconds；描述抽样帧时只引用 sample_seconds 中实际解码的时点。混合波形只说明整体电平，声部重叠时间以各轨片段为准。"
                   "如果用户只要初稿，draft_saved_this_turn 已满足保存要求，展示已保存作品。只在用户要求或已观察问题需要时生成额外素材。生成工具会按账户设置出具真实费用确认。用户要求生成时直接调用。如果 preceding_reviewed_delivery 或 referenced_output 表明用户针对已交付的成片提出修改，仍需交付修订后的成片，除非用户只要预览。只有交付回执才表示正式成片已发到对话。审阅发现问题时根据用户目标决定是否继续修改；涉及用户硬要求的发现若仍未解决，交付和最终回复必须明确报告该未满足项，不能把有 Output 或有交付卡等同于目标完成。delivered_to_chat 表示卡片已交付。completed_media_this_turn 中的素材已经完成，直接使用其固定引用，只补未完成的要求。按请求决定是否插入；单独试听无需预览影片。答复使用版本号、素材名称、位置和实测结果。技术标识仅用于工具参数。" + website_evidence_rule,
            context=json.dumps(context, ensure_ascii=False), include_project_context=False,
            opening_text=None if native_creation else user_text, enforce_offered_tools=True,
            stream_prose=native_creation,
            project_reply=(None if native_creation else
                           lambda text: project_editor_reply(text, facts.get("editor_labels", {}), user_text)),
            caller_state={"video_target": selected}, acknowledgment=acknowledgment,
            invitation_tool="ask_user" if any(t.name == "ask_user" for t in tools) else None,
            missing_tool_feedback=(
                "请通过原生 tool_calls 调用 ask_user，把全部缺失选项放进同一份问卷。正文只写给用户的邀请。"
                if any(t.name == "ask_user" for t in tools) else None
            ),
        )
    if facts.get("drafts"):
        return RoundAssembly(
            tools=[tool for tool in facts["tools"] if tool.name == "answer"],
            system="现有工作草稿无法安全转换为完整作品。保留原草稿，不调用旧创作协议，不声称已保存新版本。说明只能读取已有成果或从当前素材重新创建，然后调用 answer。",
            context=json.dumps({"working_draft_recovery": "incomplete_or_invalid"}, ensure_ascii=False),
            stage="working_draft_unavailable", include_project_context=False,
            opening_text=user_text, enforce_offered_tools=True,
        )
    return RoundAssembly(
        tools=[tool for tool in facts["tools"] if tool.name == "answer"],
        system="保留现有成果。当前无法确定可编辑作品时，如实说明，不调用旧创作协议。",
        context=json.dumps({"video_target": "unresolved"}, ensure_ascii=False),
        include_project_context=False, opening_text=user_text, enforce_offered_tools=True,
    )


def intent_router_system() -> str:
    return chat_system("plan")


def chat_intent_system() -> str:
    return chat_system("conversation")


def trigger_system() -> str:
    return chat_system("event")


def delivery_system() -> str:
    return chat_system("delivery")
