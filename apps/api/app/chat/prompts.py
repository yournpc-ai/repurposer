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
    fixed_voice = (
        any(r.get("role") == "narration" and r.get("status") == "available"
            for r in facts.get("media_receipts") or [])
        or any(
            r.get("kind") == "audio" and (r.get("alignment") or (r.get("origin") or {}).get("video_narration_hash"))
            for _, r in resources
        )
    )
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
                    description += " 旁白音频已固定，先保存画面版本，再用 insert_audio 放入原音。"
                if not aligned_voice:
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
            include_observation_media=False, observation_tools=frozenset({"create_video", "instantiate_skill_blueprint"}),
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
        if facts.get("answered_this_opening"):
            context["clarified_request"] = user_text
        if attachments := facts.get("attachments"):
            project_assets = {r["asset_id"]: r for _, r in resources if r.get("kind") == "asset"}
            context["opening_attachments"] = [
                {"position": index, "asset_id": item.id, "type": project_assets[item.id]["type"], "name": item.name}
                for index, item in enumerate(attachments, start=1)
                if item.status == "uploaded" and item.id in project_assets
            ]
        mentions = facts.get("asset_mentions") or {}
        if mentions:
            context["mentioned_assets"] = [
                {"asset_id": r["asset_id"], "type": r["type"], "label": mentions[r["asset_id"]]}
                for _, r in resources if r.get("kind") == "asset" and r["asset_id"] in mentions
            ]
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
                clips = []
                for clip in recent["clips"].values():
                    start, end = clip.get("start_seconds"), clip.get("end_seconds")
                    item = dict(clip)
                    if start is not None and end is not None and 0 < end - start <= 12:
                        item["preview_range"] = {"start_seconds": start, "end_seconds": end}
                    clips.append(item)
                context["recently_edited_clips"] = clips
        from app.chat.editor import requests_observation_first

        last_preview = facts.get("last_preview") or {}
        if selected and not recent and requests_observation_first(user_text):
            context["observation_requested_before_edit"] = "Inspect actual rendered footage before deciding whether anything needs changing."
        if selected and last_preview.get("version_id") == selected["version_id"]:
            context["observed_preview"] = last_preview
        names = set(EDITOR_NAMES) | {
            "read_conversation_context", "answer", "ask_user", "list_project_media",
            "review_video", "align_recording", "get_narration_alignment", "annotate_narration",
            "search_music", "show_music_candidates", "select_music",
        }
        from app.chat.editor_create import media_generation_forbidden, voice_generation_forbidden
        from app.editing.catalog import catalog_prompt_index

        context["creative_catalog"] = catalog_prompt_index()
        if media_generation_forbidden(user_text):
            names.difference_update({"generate_voice", "generate_music", "generate_image", "generate_sfx"})
        elif voice_generation_forbidden(user_text):
            names.discard("generate_voice")
        if not native_creation:
            names.discard("create_video")
            names.discard("instantiate_skill_blueprint")
        if not selected:
            names.discard("save_composition_as_skill")
        completed_delivery = facts.get("delivered") or {}
        if selected:
            names.update({"prepare_video_materials", "get_asset"})
            if completed_delivery.get("composition_version_id") == selected["version_id"]:
                names.discard("ask_user")
        website_evidence_rule = ""
        if native_creation:
            readiness = compute_source_readiness(
                user_text=user_text, source_text=facts.get("source_text"),
                assets=[r for _, r in resources if r.get("kind") == "asset"],
                snapshots=[r for _, r in resources if r.get("kind") == "web"],
                creative_state=creative_state,
            )
            names.update({"prepare_video_materials", "get_asset", "get_understanding", "search_transcript"})
            # A project without a saved work can generate media, but has no timeline to inspect or edit.
            from app.chat.editor import WRITE_TOOLS
            from app.models.schemas import ExternalSkillReference
            names.difference_update({*WRITE_TOOLS, "inspect_timeline", "inspect_clip", "preview_range",
                                     "export_video", "deliver_video", "save_composition_as_skill"})
            if not isinstance(facts.get("skill"), ExternalSkillReference):
                names.discard("instantiate_skill_blueprint")
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
                names.discard("instantiate_skill_blueprint")
            if facts.get("material_pending_line"):
                context["material_pending_line"] = facts["material_pending_line"]
            if readiness.task_kind == "website_promo":
                names.update({"analyze_brand", "capture_web"})
                context["source_readiness"] = readiness.model_dump()
                website_evidence_rule = "网站产品主张和画面取自当前来源。采集失败时说明实际错误。"
                if not (readiness.text_ready and readiness.required_views_ready):
                    names.discard("create_video")
                    names.discard("instantiate_skill_blueprint")
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
                names.intersection_update({"review_video", "deliver_video", "answer"})
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

        if (facts.get("authorized_media") or {}).get("status") == "available":
            names.discard("ask_user")

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
        media_ready = bool(facts.get("media_receipts")) or facts.get("new_result_tool") in {
            "generate_voice", "generate_music", "generate_image", "generate_sfx",
        }
        return RoundAssembly(
            tools=tools,
            system=("你是视频剪辑师，用用户的语言交流。检查本轮目标、所选作品、素材与已有回执。"
                    "目标明确就编辑。多个素材符合描述且用户未指定全用时，写入前用 ask_user 让用户选定，以可辨特征或附件序号列出选项。分镜按需表达。"
                    "保留未要求改变的画面、字幕、动画和声音。依赖新增对象或素材时先读取上一步返回的标识。"
                    "专业 MG 画面优先使用 insert_motion_block，单实例修订用 update_motion_block。"
                    "制作 25–45 秒多幕产品宣传片时，按专业工作室多幕节奏编排（通常 4–5 幕）：① 纯排版开场钩子 statement_hook（不压在网页截屏上，避免与首页 Hero 大标题复读）；② 2 幕不同真实网页视图的 product_showcase（配合 callout 局部聚焦框或轻量 kinetic_title(surface_style='pill_caption') 角标，不叠巨型复读标题卡）；③ 量化能力/指标卡 metric_grid；④ 品牌收尾卡 closing_cta（无 Logo 时用纯排版，有 Logo 时默认 logo_surface='light_pill'）。"
                    "相邻同轨全画幅不透明幕用 set_transition，按镜头选择 crossfade、whip_pan、wipe_reveal、zoom_through 或 iris_focus。"
                    "creative_catalog.shot_combinations 提供开箱即用的单镜方案；若用户未定风格或希望挑选方案，可在采集网页后用 ask_user 给出 2–3 个具名方案供点选。"
                    "配乐可用 search_music / show_music_candidates / select_music 选曲并经 prepare_video_materials(material_music_ids=…) 导入后 insert_audio（旁白下 BGM 压低至 −24 ~ −26 dB），并用 edit_audio_clip 设置平滑 fade_in_seconds / fade_out_seconds 与必要 duck_windows。"
                    "多幕旁白按幕留 0.4–0.6 秒自然呼吸气口，避免相邻旁白首尾撞车。"
                    "product_showcase 可用 camera_preset=flat/tilt_left/tilt_right/dolly_zoom/scroll_reveal；滚屏用 scroll_from_y/scroll_to_y (0..1)。用所选视图的真实 element_id 绑定 cursor(click_at_s) 和最多四个依次出现的 callout_steps(start_s,end_s,label)。用 backdrop_style=ambient_mesh/architectural_grid/editorial_paper/clean 设舞台，以幕内秒数安排 highlight_at_s 和 items[].reveal_at_s。音效用 generate_sfx，按视觉节拍从目录的 22 个配方中选择。开场用 title_bloom 或 sub_swell，框选聚焦用 callout_ping，数据卡用 metric_chime，"
                    "转场用 swoosh_cut、velvet_pass 或 page_turn，痛点转折用 sub_drop，收尾用 stinger。静态段落留白。音效峰值约 −2 dBFS，"
                    "旁白下常规点缀放 −14 至 −10 dB。单实例调电平、淡入淡出或换音源用 edit_audio_clip。"
                    "音效卡点结合 peak_offset_ms 与 sync_cue，对照 preview_range 的 audio_windows 与 masking_warnings 控电平；audio_available_to_model 为 false 时不声称主观听感。"
                    "当用户要求把已打磨的多幕作品固化为可复用 Skill / 模板时，调用 save_composition_as_skill 保存脱敏蓝图（SKILL.md + references/blueprint.json）；当本轮绑定了含 slot_blueprint_v1 的外部 Skill（见 bound_skill_method 与 skill_reference.skill_version_id）且尚无作品时，先按新需求采集目标网页/素材与新语言旁白（以及可选 BGM），再一次性调用 instantiate_skill_blueprint 填入全部可替换 Slot 展开成可编辑作品，之后按常规单实例工具预览或微调。"
                    "以本轮开始时的作品为基准，对照 already_saved_this_turn 的改动前后值（含 gain_delta_db 与 props_before/after）决定下一步；相对调整（如“减 3 dB”“慢一点”）每段只执行一次，禁止多轮重复叠加。按需选择是否预览和观看范围，用户点名的窗口要准确播放。"
                    "结束时说明实际改动和尚未达成的目标。画面和声音判断以实际收到的对应媒体及其覆盖范围为限。"
                    "不得擅改目标或追加未经许可的生成与导出。只预览的任务以播放为止。"
                    "正式交付须审阅固定 Output，按原 opening 的回执报告费用与尚未满足的要求。"
                    + website_evidence_rule),
            context=json.dumps(context, ensure_ascii=False), include_project_context=False,
            opening_text=None if native_creation else user_text, enforce_offered_tools=True,
            stream_prose=not media_ready and (
                native_creation or bool(selected and not facts.get("editor_labels") and not facts.get("authorized_media"))
            ),
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
