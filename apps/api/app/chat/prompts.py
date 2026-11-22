"""Project the current Composition, its evidence and the available Chat tools."""

import json
import re
from dataclasses import replace

from app.agents.base import jinja_env
from app.agents.tool_loop import RoundAssembly, prune_wire_parameters
from app.chat.editor import EDITOR_NAMES, project_editor_reply

def chat_system() -> str:
    return jinja_env.get_template("chat/system.j2").render()


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


def _native_creation_tools(tools, *, facts):
    from app.config import settings
    from app.chat.turn_tools import _explicit_constraint_wire
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
    from app.chat.editor_create import voice_generation_forbidden

    voice_excluded = voice_generation_forbidden(facts.get("user_text") or "")
    fixed_voice = any(r.get("role") == "narration" and r.get("status") == "available"
                      for r in facts.get("media_receipts") or [])
    aligned_voice = any((r.get("alignment") or {}).get("status") == "READY" for _, r in resources)
    projected = []
    for tool in tools:
        if tool.name == "create_video":
            def creation_wire(description, parameters, *, constraints=constraints):
                parameters = _explicit_constraint_wire(parameters, constraints, include_fixed=True)
                hidden = set()
                if not external or not settings.component_bake_enabled:
                    hidden.add("skill_resource")
                if fixed_voice or voice_excluded:
                    hidden.update({"narration", "narration_voice_id", "narration_language"})
                if fixed_voice:
                    description += " 本轮旁白已固定，保存画面后可用 insert_audio 放入原音。"
                if fixed_voice and not aligned_voice:
                    hidden.update({"narration_snapshot_id", "narration_alignment_id"})
                shot = parameters["$defs"]["FirstShot"]
                for field in hidden:
                    shot["properties"].pop(field, None)
                parameters = prune_wire_parameters(parameters, set())
                if not external:
                    description += "未绑定外部 Skill，不使用 skill_resource。"
                elif not settings.component_bake_enabled:
                    description += "当前部署不支持受控 Generator；使用现有图片、视频和原生文字。"
                return description, parameters

            projected.append(replace(tool, wire_view=creation_wire))
        else:
            projected.append(tool)
    return projected


def assemble_video_round(facts: dict) -> RoundAssembly:
    confirmation = facts.get("video_confirmation")
    if confirmation and confirmation["action"] in {"wait", "stale", "existing_export"}:
        action = confirmation["action"]
        rules = {
            "wait": "说明仍在展示该版本。",
            "stale": "说明引用的版本已过期，询问要使用哪一版。",
            "existing_export": "按导出任务的实际状态和回执作答。有交付消息时才能说已交付。",
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
    readiness = compute_source_readiness(
        user_text=user_text, source_text=facts.get("source_text"),
        assets=[r for _, r in resources if r.get("kind") == "asset"],
        snapshots=[r for _, r in resources if r.get("kind") == "web"],
        creative_state=creative_state,
    )
    native_creation = (
        not works and not hint and not facts.get("active_repair")
        and not facts.get("version_saved") and (not pending or facts.get("group_answer_submitted"))
        and any(tool.name == "create_video" for tool in facts["tools"])
    )
    if native_creation or works or hint.get("unavailable") or hint.get("composition_id"):
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
        from app.chat.editor_create import media_generation_forbidden, voice_generation_forbidden

        if media_generation_forbidden(user_text):
            names.difference_update({"generate_voice", "generate_music", "generate_image"})
        elif voice_generation_forbidden(user_text):
            names.discard("generate_voice")
        if not native_creation:
            names.discard("create_video")
        completed_delivery = facts.get("delivered") or {}
        if selected and (recent or facts.get("version_saved") or context.get("observed_preview")
                         or completed_delivery.get("composition_version_id") == selected["version_id"]):
            names.discard("ask_user")
        if native_creation:
            names.update({"prepare_video_materials", "get_asset", "get_understanding", "search_transcript"})
            # A project without a saved work can generate media, but has no timeline to inspect or edit.
            from app.chat.editor import WRITE_TOOLS
            names.difference_update({*WRITE_TOOLS, "inspect_timeline", "inspect_clip", "preview_range",
                                     "export_video", "deliver_video"})
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
                source_ids.update(
                    resource["text_snapshot_id"] for _, resource in resources
                    if resource.get("text_snapshot_id") and canonical_url(resource.get("url") or "") in urls
                )
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
                names.update({"analyze_brand", "capture_web"})
                context["source_readiness"] = readiness.model_dump()
                if not (readiness.text_ready and readiness.required_views_ready):
                    names.discard("create_video")
        from app.chat.video_turn_seats import asks_for_export, draft_only_request
        delivery = facts.get("preceding_delivery") or {}
        if selected and delivery.get("composition_id") == selected["composition_id"]:
            context["preceding_reviewed_delivery"] = delivery
            if recent.get("version_id") == selected["version_id"] and asks_for_export(user_text):
                delivered = facts.get("delivered") or {}
                exported = facts.get("exported") or {}
                context["revised_delivery"] = {
                    "requested_artifact": "Reviewed MP4 in this Chat, updated with the requested change",
                    "revised_version": selected["base_ref"],
                    "output": exported if exported.get("composition_version_id") == selected["version_id"] else None,
                    "chat_delivery": delivered if delivered.get("composition_version_id") == selected["version_id"] else None,
                }
        if not asks_for_export(user_text) and not hint.get("output_id") and not confirmation:
            context["delivery_scope"] = "The opening does not explicitly request formal export. Complete the requested editing or preview and report the saved result. A separate formal export would require confirmation."
        if draft_only_request(user_text):
            context["delivery_scope"] = "Save the requested work and report any requested preview. Formal export is outside this request."
            context.pop("revised_delivery", None)
            names.discard("export_video")
            names.discard("deliver_video")
        if hint.get("output_id") and selected is None:
            context["revision_target_status"] = "The referenced Output is historical. It can be reviewed and delivered as saved. Ask which baseline to use before editing."
            names = {"ask_user", "answer", "review_video"}
            if not draft_only_request(user_text) and facts.get("reviewed_output_id") == hint["output_id"]:
                names.add("deliver_video")

        exported = facts.get("exported") or {}
        if exported.get("status") == "available" and exported.get("output_id"):
            context["exported_this_opening"] = exported
            if (facts.get("authorized_media") or {}).get("role") == "export":
                # Continuation of the authorized job owns review and delivery of
                # this fixed file, including the decision after review.
                names.intersection_update({"review_video", "deliver_video", "answer", "ask_user"})
                if facts.get("reviewed_output_id") != exported["output_id"]:
                    names.discard("deliver_video")
                elif (facts.get("delivered") or {}).get("output_id") == exported["output_id"]:
                    names.intersection_update({"answer"})
            current = next((work for work in works if work["composition_id"] == exported["composition_id"]), None)
            if facts.get("review_pinned_export") or (
                current and current["version_id"] != exported["composition_version_id"]
                and recent.get("version_id") != current["version_id"]
            ):
                context["delivery_scope"] = (
                    "Another opening is working on this project. Review and deliver the exact MP4 in "
                    "exported_this_opening if it meets this opening's request. Identify the exported version."
                )
                names = {"answer", "review_video", "deliver_video"}

        def dialogue_wire(description, parameters):
            return description, prune_wire_parameters(parameters, {
                "brief", "material_text", "material_urls", "items", "slot",
            })

        tools = [t for t in facts["tools"] if t.name in names]
        if native_creation:
            tools = _native_creation_tools(tools, facts=facts)
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
        if facts.get("media_receipts"):
            context["original_user_request"] = user_text
            context["media_receipts_in_call_order"] = facts["media_receipts"]
        if (facts.get("authorized_media") or {}).get("status") == "declined":
            context["declined_operation"] = "The user declined this additional operation. Continue the original request using available media. Do not repropose the declined generation."
        if (facts.get("authorized_media") or {}).get("status") == "available":
            completed = facts["authorized_media"]
            delivered = facts.get("delivered") or {}
            delivered_output = delivered.get("output_id")
            attached = delivered_output is not None and delivered_output == completed.get("output_id")
            context["completed_media_this_turn"] = {
                **completed, "delivered_to_chat": completed.get("role") != "export" or attached,
            }
            if facts["authorized_media"].get("role") == "export":
                context["authorized_deliverable"] = "The user approved the exact Output above. Review it and deliver that version when it meets the request. Respect instructions to retain the edit. Report defects if it cannot be delivered."
        if pending:
            context["pending_question"] = getattr(pending, "question", None)
        website_evidence_rule = (
            "官网宣传片的产品主张和画面须来自这个网站的实际取证。采集失败时说明实际错误。"
            if readiness.task_kind == "website_promo" else ""
        )
        media_ready = bool(facts.get("media_receipts")) or facts.get("new_result_tool") in {"generate_voice", "generate_music", "generate_image"}
        return RoundAssembly(
            tools=tools,
            system="你是视频剪辑师。用本轮用户提问的语言回答。修改片段前，按需读取时间线定位目标。制作影片时，空项目按用户要求用 create_video 将镜头直接保存为可编辑作品。已有待配音片段时，核对原稿，对齐 READY 后用 bind_clip_source 绑定录音。独立新增的声音用 insert_audio。只有同时创建与旁白对齐的字幕时才填写镜头的两个 narration 引用，且对齐必须 READY。若用户只要求生成素材，已交付的素材回执即完成该项请求，直接说明可从对话中查看或播放。颜色、运动、时长、交付范围以用户原话为准。只要求调整和复看时，复看后答复；正式导出需要交付意图。目标不明确时询问。"
                   "可在同一响应提交独立的读取、素材生成或已知对象的修改。写入按声明次序保存。需要前项新标识时先看回执，再在下次决策引用。完成各项后再单独答复。根据已生成的素材、已保存动作和预览继续，已完成的要求只在观察到具体问题时再次修改。同窗对照按 earlier 与 current 的标记读图。构图以用户点名的主体与取景要求为准。局部取景修订也应保留原本完整可读的前景文字；新出现的露底和裁字要在同窗前后画面中核对。edges_matching_canvas_color_px 是采样图像与画布同色的边缘宽度，须结合画面确认是否露底。当前预览满足要求就结束，不追加未请求的构图、画幅或配音选择；素材取景限制改善时说明已看到的局限。采样范围限制用于如实陈述证据，不是继续寻找假设问题的理由；用户点名的内容已在当前版本得到观察且没有待修发现时，停止追加观察并完成用户要求的后续交付或答复。以当前版本已观察窗口和用户要求为依据，说明发现的问题及未检查范围。调整前后的几何与时间以版本数据为准。描述源取景时，source_clipped_px 是源画面被画布裁掉的像素，canvas_borders_px 是画布留边像素；source_clipped_px 大于 0 时不能声称完整源画面，canvas_borders_px 大于 0 时不能声称留边已消除，主体或文字是否被裁切仍以实际帧为准。face_evidence.face_fully_visible=false 时不能声称检测到的人脸完整或有安全边距；expanded_face_fully_visible=false 时不能声称头肩完整。人脸框和扩边区域不证明头发、肩膀完整或构图自然，未检测到时明确未知。几何坐标数组逐字段直接引用，不要重算成不同边界。静态图片来源不等于输出静止；sample_frames 中的像素差异只证明所列采样时点的变化，不证明未观察时段的运动，描述输出前先核对这些帧。只有实际收到可感知声音才能评价听感。播放范围取自 window_seconds；描述抽样帧时只引用 sample_seconds 中实际解码的时点。混合波形只说明整体电平，声部重叠时间以各轨片段为准。"
                   "如果用户只要初稿，draft_saved_this_turn 已满足保存要求，展示已保存作品。只在用户要求或已观察问题需要时生成额外素材。生成工具会按账户设置出具真实费用确认。用户要求生成时直接调用。preceding_reviewed_delivery 与 referenced_output 指认此前的成片。本轮要求播放修订片段时，交付该版本的局部预览。只有交付回执才表示正式成片已发到对话。费用按原 opening 归属：交付已有 MP4 时按回执中的本轮导出扣费答复。用户点名导出已预览的固定版本时，审阅并交付该版本，报告实际问题；另行修改素材或版本需用户提出。助手写的旁白、作品名称和分镜不能升级为用户硬要求。审阅发现问题时根据用户目标决定是否继续修改；涉及用户硬要求的发现若仍未解决，交付和最终回复必须明确报告该未满足项，不能把有 Output 或有交付卡等同于目标完成。delivered_to_chat 表示卡片已交付。completed_media_this_turn 中的素材已经完成，直接使用其固定引用，只补未完成的要求。按请求决定是否插入；单独试听无需预览影片。答复使用版本号、素材名称、位置和实测结果。技术标识仅用于工具参数。" + website_evidence_rule,
            context=json.dumps(context, ensure_ascii=False), include_project_context=False,
            opening_text=None if native_creation else user_text, enforce_offered_tools=True,
            stream_prose=native_creation and not media_ready,
            project_reply=(None if native_creation and not media_ready else
                           lambda text: project_editor_reply(text, facts.get("editor_labels", {}), user_text)),
            caller_state={"video_target": selected},
            invitation_tool="ask_user" if any(t.name == "ask_user" for t in tools) else None,
        )
    return RoundAssembly(
        tools=[tool for tool in facts["tools"] if tool.name == "answer"],
        system="保留现有成果。当前无法确定可编辑作品时，如实说明，不调用旧创作协议。",
        context=json.dumps({"video_target": "unresolved"}, ensure_ascii=False),
        include_project_context=False, opening_text=user_text, enforce_offered_tools=True,
    )
