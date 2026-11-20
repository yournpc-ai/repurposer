"""Render the four existing Chat routes and their shared video rounds."""

import json
import re
from copy import deepcopy
from dataclasses import replace
from typing import Literal

from app.chat.editor import EDITOR_NAMES, project_editor_reply

from app.agents.base import jinja_env
from app.agents.tool_loop import RoundAssembly, prune_wire_parameters
from app.tools import tool_catalog_lines

ChatMode = Literal["plan", "conversation", "event", "delivery"]

def chat_system(
    mode: ChatMode,
    *,
    available_tools: list | None = None,
    video_stage: str = "none",
    video_speech: str | None = None,
    scene_authoring: bool = False,
    website_promo: bool = False,
) -> str:
    from app.config import settings

    tool_names = {tool.name for tool in available_tools or []}
    return jinja_env.get_template("chat/system.j2").render(
        mode=mode,
        tool_names=tool_names,
        tool_lines=tool_catalog_lines(),
        menu_lines="",
        include_menu=False,
        wiring_lines="",
        chat_loop=mode == "conversation",
        component_bake_enabled=settings.component_bake_enabled,
        video_stage=video_stage,
        video_speech=video_speech,
        scene_authoring=scene_authoring,
        website_promo=website_promo,
    )


def _current_source_resources(snapshot, readiness, creative_state) -> list[tuple[str, dict]]:
    from app.chat.readiness import canonical_url

    urls = {canonical_url(url) for url in readiness.urls}
    source_ids = {
        str(ref.snapshot_id)
        for ref in [
            *(creative_state.source_refs if creative_state is not None else []),
            *(creative_state.brand_profile.source_refs
              if creative_state is not None and creative_state.brand_profile is not None else []),
        ]
    }
    selected = []
    for key, resource in getattr(snapshot, "resources", ()) or ():
        kind = resource.get("kind")
        if kind == "project":
            selected.append((key, resource))
            continue
        raw_url = resource.get("url") or resource.get("canonical_url")
        if raw_url and canonical_url(str(raw_url)) in urls:
            selected.append((key, resource))
            continue
        if str(resource.get("snapshot_id") or "") in source_ids:
            selected.append((key, resource))
    return selected


def _creative_state_projection(creative_state) -> dict:
    """Keep creative facts while source identities stay in the resource projection."""
    def compact(value):
        if isinstance(value, dict):
            return {
                key: compact(item)
                for key, item in value.items()
                if key not in {"source_refs", "content_digest"}
            }
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    return compact(creative_state.model_dump(mode="json"))


def assemble_video_round(facts: dict) -> RoundAssembly:
    """Assemble prompt, facts, media retention and final tools from one target."""
    from app.chat.turn_tools import resolve_video_stage, video_round_tools
    from app.tools.project_context import render_resources

    confirmation = facts.get("video_confirmation")
    if confirmation and confirmation["action"] in {"wait", "stale", "already_started", "start"}:
        action = confirmation["action"]
        rules = {
            "wait": "说明仍在展示该版本。",
            "stale": "说明引用的版本已过期，询问要使用哪一版。",
            "already_started": "按已有执行回执陈述状态，交付以确切产物为准。",
            "start": "请用户在原有费用确认中核对并批准报价。",
        }
        available = [tool for tool in facts["tools"] if tool.name == "answer"]
        return RoundAssembly(
            tools=available,
            system=f"用用户在本次对话中使用的语言作答。{rules[action]} 若只需告知情况，先在消息正文中说明，再调用 answer。",
            context=json.dumps({"video_confirmation": confirmation}, ensure_ascii=False),
            stage="video_confirmation",
            include_project_context=False,
            include_observation_media=False,
            opening_text=facts.get("user_text") or "",
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
    if facts.get("draft_finalized") and (not works or (draft_requested and not additional_work
                                                       and not facts.get("production_requested"))):
        presentation = jinja_env.get_template("chat/_video_presentation.j2").render()
        return RoundAssembly(
            tools=[tool for tool in facts["tools"] if tool.name == "answer"],
            system=(
                "用用户在本次对话中使用的语言作答。草稿已经保存。根据 design_video 的结果在正文中展示该保存版本，然后调用 answer。\n" + presentation
            ),
            context="当前视频轮次（目标和状态由服务端提供）：\n{\"video_stage\": \"draft_present\"}",
            stage="draft_present", include_project_context=False,
            include_observation_media=False, observation_tools=frozenset({"design_video"}),
        )

    pending = facts.get("pending_question")
    if callable(pending):
        pending = pending()
    from app.chat.readiness import compute_source_readiness, render_readiness_context, website_promo_default_brief

    creative_state = facts.get("creative_state")
    if callable(creative_state):
        creative_state = creative_state()
    hint = facts.get("target_hint") or {}
    if confirmation and confirmation["action"] == "produce" and not hint:
        ref = confirmation["base_ref"]
        hint = {"composition_id": ref["composition_id"], "version_id": ref["composition_version_id"]}
    if (works or hint.get("unavailable") or hint.get("composition_id")) and not hint.get("draft_id"):
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
                user_text = facts.get("user_text") or ""
                named = [r for r in works if r["composition_id"] in user_text
                         or (r.get("name") and r["name"] in user_text)]
                selected = named[0] if len(named) == 1 else None
        context = {
            "works": [{k: r.get(k) for k in ("composition_id", "name", "version_id", "version")} for r in works],
            "referenced_output": hint if hint.get("output_id") else None,
            "selected": selected["base_ref"] if selected else None,
            "project": next(({k: r.get(k) for k in ("title", "project_id", "user_stated_constraints")}
                             for _, r in resources if r.get("kind") == "project"), None),
            "assets": [{k: r.get(k) for k in ("asset_id", "type", "name")} for _, r in resources if r.get("kind") == "asset"][:24],
        }
        context["fixed_media"] = [
            {k: r[k] for k in ("snapshot_id", "kind", "duration_ticks", "title", "alignment") if r.get(k) is not None}
            for _, r in resources if r.get("snapshot_id") and r.get("kind") in ("audio", "image")
        ][-24:]
        if selected and facts.get("draft_finalized"):
            context["draft_saved_this_turn"] = selected["base_ref"]
        if selected:
            context.update(clip_count=selected.get("clip_count"), scene_count=selected.get("scene_count"),
                           timebase=selected.get("timebase"), duration_ticks=selected.get("duration_ticks"),
                           selected_region=hint.get("selected_region"))
            if selected.get("timebase") and selected.get("duration_ticks") is not None:
                context["duration_seconds"] = selected["duration_ticks"] / selected["timebase"]
        recent = facts.get("recent_edit") or {}
        if selected and recent.get("composition_id") == selected["composition_id"]:
            context["already_saved_this_turn"] = recent["applied"]
            if recent["version_id"] == selected["version_id"]:
                context["recently_edited_clips"] = list(recent["clips"].values())
        last_preview = facts.get("last_preview") or {}
        if selected and last_preview.get("version_id") == selected["version_id"]:
            context["observed_preview"] = last_preview
        names = EDITOR_NAMES | {"read_conversation_context", "answer", "ask_user", "list_project_media", "review_video", "align_recording", "get_narration_alignment", "annotate_narration"}

        if hint.get("output_id") and selected is None:
            context["revision_target_status"] = "The referenced Output is historical. Ask which baseline to use before editing."
            names = {"ask_user", "answer", "review_video"}

        def dialogue_wire(description, parameters):
            return description, prune_wire_parameters(parameters, {
                "brief", "material_text", "material_urls", "items", "slot",
            })

        tools = [t for t in facts["tools"] if t.name in names]
        tools = [replace(t, wire_view=dialogue_wire, description=(
            "根据实际结果结束本轮；也可以直接在消息正文答复。" if t.name == "answer" else
            "询问一个确定目标所需的问题。"
        )) if t.name in {"answer", "ask_user"} else t for t in tools]
        if confirmation and confirmation["action"] == "produce":
            context["user_confirmed_export_of"] = confirmation["base_ref"]
        if facts.get("authorized_media"):
            context["completed_media_this_turn"] = {**facts["authorized_media"], "delivered_to_chat": facts["authorized_media"].get("role") != "export"}
        if pending:
            context["pending_question"] = getattr(pending, "question", None)
        return RoundAssembly(
            tools=tools,
            system="你是视频剪辑师。用本轮用户提问的语言回答。修改片段前，按需读取时间线定位目标。目标不明确时询问。"
                   "可在同一响应提交独立的读取、素材生成或已知对象的修改。写入按声明次序保存。需要前项新标识时先看回执，再在下次决策引用。完成各项后再单独答复。根据已生成的素材、已保存动作和预览继续，已完成的要求只在观察到具体问题时再次修改。同窗对照按 earlier 与 current 的标记读图。构图以用户点名的主体与取景要求为准，留边与是否填满画布是不同选择。当前预览满足要求就结束；素材取景限制改善时说明已看到的局限。以当前版本已观察窗口和用户要求为依据，说明发现的问题及未检查范围。调整前后的几何与时间以版本数据为准。只有实际收到可感知声音才能评价听感。按帧上的作品时间说明实际画面。混合波形只说明整体电平，声部重叠时间以各轨片段为准。"
                   "如果用户只要初稿，draft_saved_this_turn 已满足保存要求，展示已保存作品。只在用户要求或已观察问题需要时生成额外素材。生成工具会按账户设置出具真实费用确认。用户要求生成时直接调用。如果针对已交付的成片提出修改，仍需交付修订后的成片，除非用户只要预览。只有交付回执才表示正式成片已发到对话。审阅发现问题时根据用户目标决定是否继续修改。delivered_to_chat 表示卡片已交付。completed_media_this_turn 中的素材已经完成，直接使用其固定引用，只补未完成的要求。按请求决定是否插入；单独试听无需预览影片。答复使用版本号、素材名称、位置和实测结果。技术标识仅用于工具参数。",
            context=json.dumps(context, ensure_ascii=False), include_project_context=False,
            opening_text=facts.get("user_text") or "", enforce_offered_tools=True,
            stream_prose=False,
            project_reply=lambda text: project_editor_reply(text, facts.get("editor_labels", {}), facts.get("user_text") or ""),
            caller_state={"video_target": selected},
        )
    readiness = compute_source_readiness(
        user_text=facts.get("user_text") or "",
        source_text=facts.get("source_text"),
        assets=[resource for _key, resource in resources if resource.get("kind") == "asset"],
        snapshots=[resource for _key, resource in resources if resource.get("kind") == "web"],
        creative_state=creative_state,
        draft_present=bool(facts.get("drafts")),
        question_settled=facts.get("website_question_settled", False),
    )
    resolution = resolve_video_stage(
        tools=facts["tools"],
        drafts=facts.get("drafts") or (),
        snapshot=snapshot,
        user_text=facts.get("user_text") or "",
        pending_question=pending,
        target_hint=facts.get("target_hint"),
        readiness=readiness,
    )
    if (
        readiness.task_kind == "website_promo"
        and facts.get("new_result_tool") in {"design_video"}
        and resolution.get("draft") is not None
        and resolution.get("stage") != "draft_build"
    ):
        resolution["stage"] = "draft_build"
    resolution.setdefault("readiness", readiness)
    resolution["selected_region"] = (facts.get("target_hint") or {}).get("selected_region")
    tools = video_round_tools(
        facts["tools"],
        resolution=resolution,
        snapshot=facts.get("snapshot"),
        skill=facts.get("skill"),
        material_pending=facts.get("material_pending", False),
        package_sessions=facts.get("package_sessions"),
        user_text=facts.get("user_text") or "",
    )
    stage = resolution["stage"]
    draft = resolution.get("draft")
    draft_facts = {}
    if draft is not None:
        from app.agents.working_drafts import working_draft_review_facts

        draft_facts = working_draft_review_facts(draft.arguments)
    judging_preview = stage == "draft_review" and draft_facts.get("awaiting_judgment")
    snapshot = facts.get("snapshot")
    context_parts: list[str] = []
    if stage == "draft_build" and draft is None and snapshot is not None and snapshot.skill_method:
        context_parts.append(snapshot.skill_method)
    include_project_context = stage == "none"
    if not include_project_context and snapshot is not None and not judging_preview:
        resources = []
        if draft is not None:
            content = draft.arguments.get("content") or {}
            source_ids = {
                str(source.get("snapshot_id"))
                for source in content.get("sources") or []
                if source.get("snapshot_id")
            }
            for key, resource in snapshot.resources:
                if resource.get("kind") == "skill_read_receipt":
                    resources.append((key, resource))
                elif key.startswith("snapshot:") and str(resource.get("snapshot_id")) in source_ids:
                    compact = {
                        key: value for key, value in resource.items()
                        if key not in {"citable_lines", "capabilities"}
                    }
                    if resource.get("kind") == "web":
                        compact["text_projection"] = (
                            "场景规划时已有源文本。如需确切措辞或新的目标事实，通过 prepare_video_materials 的 material_targets 读取该快照。"
                        )
                    resources.append((key, compact))
        elif stage in {"source_preparing", "briefing", "draft_build"}:
            resources = (
                _current_source_resources(snapshot, readiness, creative_state)
                if readiness.task_kind == "website_promo"
                else list(snapshot.resources)
            )
        else:
            resources = [
                (key, {
                    key: value for key, value in resource.items()
                    if key in {"kind", "composition_id", "name", "base_ref", "skill_provenance"}
                })
                for key, resource in snapshot.resources
                if resource.get("kind") == "composition"
            ]
        if resources:
            context_parts.append(render_resources(resources).text)
    dynamic: dict = {"video_stage": stage}
    if readiness.task_kind == "website_promo":
        if creative_state is not None and stage in {"source_preparing", "briefing", "draft_build"}:
            dynamic["creative_state"] = _creative_state_projection(creative_state)
        if stage == "draft_build" and readiness.brief_missing_slots:
            sources = [res for _, res in _current_source_resources(snapshot, readiness, creative_state)
                       if res.get("kind") == "web"]
            working = website_promo_default_brief(readiness.brief, sources)
            dynamic["working_defaults"] = {
                slot: getattr(working, slot).value for slot in readiness.brief_missing_slots
            }
        if readiness.brand_profile_ready and "production_direction" in readiness.brief_missing_slots:
            from app.chat.readiness import stated_direction_inputs

            known_direction = stated_direction_inputs(readiness.brief)
            if known_direction:
                dynamic["known_direction_inputs"] = known_direction
    if resolution.get("user_constraints"):
        dynamic["user_constraints"] = resolution["user_constraints"]
    if resolution.get("pending") is not None:
        dynamic["pending_question"] = resolution["pending"]
    if draft is not None:
        dynamic["draft_ref"] = {
            "draft_id": draft.candidate_id,
            "draft_digest": draft.candidate_digest,
        }
        if stage in {"draft_build", "draft_finalize", "draft_hold"}:
            dynamic["draft"] = {
                key: draft_facts[key]
                for key in ("content_digest", "scenes", "review_started", "save_ready")
            }
        elif stage == "draft_review":
            dynamic["draft"] = {
                key: draft_facts[key]
                for key in (
                    "content_digest", "scenes", "review_started", "save_ready",
                    "current_scene_id", "current_scene_ordinal", "next_review_target",
                    "reviewed_ranges_seconds", "invalidated_ranges_seconds",
                    "unreviewed_ranges_seconds", "awaiting_judgment",
                    "unjudged_evidence_ids", "confirmation_blocked", "open_issues",
                )
            }
        elif stage == "draft_repair":
            issue_clip_ids = {
                clip_id
                for issue in draft_facts.get("open_issues") or []
                for clip_id in issue.get("clip_ids") or []
            }
            dynamic["draft"] = {
                key: draft_facts[key]
                for key in (
                    "content_digest", "scenes", "review_started", "save_ready",
                    "current_scene_id", "next_review_target", "open_issues",
                )
            }
            dynamic["draft"]["editable_targets"] = [
                target for target in draft_facts.get("editable_targets") or []
                if not issue_clip_ids or target.get("clip_id") in issue_clip_ids
            ]
        else:
            dynamic["draft"] = draft_facts
        if stage == "draft_build" and draft_facts["scenes"]:
            content = draft.arguments["content"]
            dynamic["scene_assets"] = deepcopy(
                (draft.arguments.get("design") or {}).get("scene_assets") or []
            )
            from app.tools.video.narration_draft import current_narration_facts

            dynamic["narrations"] = current_narration_facts(draft.arguments)
            dynamic["next_unfilled_scene"] = next(
                (scene for scene in draft_facts["scenes"] if not scene["clip_ids"]), None,
            )
            dynamic["draft_tracks"] = [
                {key: track[key] for key in ("track_id", "kind", "role", "order")}
                for track in (content.get("timeline") or {}).get("tracks") or []
            ]
        if draft.errors:
            dynamic["validation_errors"] = draft.errors
    if facts.get("active_repair") is not None:
        dynamic = {
            "video_stage": "candidate_repair",
            "instruction": "只用当前唯一可用的修正工具修改保留的候选内容。",
            "available_actions": [tool.name for tool in tools],
        }
        if resolution.get("user_constraints"):
            dynamic["user_constraints"] = resolution["user_constraints"]
        context_parts = []
        include_project_context = False
    else:
        dynamic["available_actions"] = [tool.name for tool in tools]
        if stage == "draft_repair":
            from app.agents.tool_loop import tool_spec

            design = next((tool for tool in tools if tool.name == "design_video"), None)
            properties = (
                tool_spec(design)["function"]["parameters"].get("properties") or {}
                if design is not None else {}
            )
            dynamic["focus_options"] = {
                "clip_ids": (properties.get("focus_clip_id") or {}).get("enum") or [],
                "element_ids": (properties.get("focus_element_id") or {}).get("enum") or [],
                "rule": "从每份列表中各复制一个确切 ID，不接受别名。",
            }
    draft_facts = dynamic.get("draft") or {}
    required_next = readiness.required_next_action
    awaiting_brief = stage == "briefing" and readiness.brand_profile_ready
    acknowledge_brief = (
        facts.get("group_answer_submitted", False)
        and readiness.task_kind == "website_promo"
        and stage == "draft_build"
        and not facts.get("interim_prose_count")
    )
    acknowledgment = None
    if acknowledge_brief:
        seconds = readiness.brief.target_seconds.value
        if (facts.get("speech_language") or "").startswith("zh"):
            film = f"这支 {seconds} 秒短片" if seconds else "这支短片"
            acknowledgment = f"收到，我会按你选的方向安排{film}的开场和镜头顺序。"
        else:
            length = f"{seconds}-second " if seconds else ""
            acknowledgment = f"Got it. I’ll shape the {length}storyboard around your choices, starting with the opening."
    if awaiting_brief and pending is not None:
        required_next = "answer"
    if readiness.task_kind == "website_promo":
        if required_next is not None:
            dynamic["required_next_action"] = required_next
        context_parts.append(render_readiness_context(readiness))
    context_parts.append(
        "当前视频轮次（目标和状态由服务端提供）：\n"
        + json.dumps(dynamic, ensure_ascii=False)
    )
    from app.agents.tool_loop import tool_spec

    design = next((tool for tool in tools if tool.name == "design_video"), None)
    design_properties = (
        tool_spec(design)["function"]["parameters"].get("properties") or {}
        if design is not None else {}
    )
    scene_authoring = bool(
        {"scene_plan", "scene"} & set(design_properties)
        and "tracks" not in design_properties
    )
    return RoundAssembly(
        tools=tools,
        system=chat_system(
            facts["mode"],
            available_tools=tools,
            video_stage=stage,
            video_speech="brief_answer" if acknowledge_brief else None,
            scene_authoring=scene_authoring,
            website_promo=readiness.task_kind == "website_promo",
        ),
        context="\n\n".join(context_parts),
        stage=stage,
        include_project_context=include_project_context,
        observation_tools=(
            frozenset({
                "design_video", "generate_image", "prepare_video_materials", "capture_web",
                "generate_voice", "get_narration_alignment", "annotate_narration",
            })
            if draft is not None and stage in {"draft_build", "draft_finalize", "draft_hold"}
            else None
        ),
        stream_prose=not awaiting_brief,
        acknowledgment=acknowledgment,
        enforce_offered_tools=True,
        invitation_tool=(
            "ask_user" if any(tool.name == "ask_user" for tool in tools) else None
        ),
        missing_tool_feedback=(
            "请通过原生 tool_calls 调用 ask_user，把全部缺失选项放进同一份问卷。正文只写给用户的邀请。"
            if awaiting_brief and pending is None else
            "用户请求的视频仍是未保存的草稿。可以继续时，调用 design_video 完成下一步写入或保存。需要用户决定时调用 ask_user。"
            "确有已核实的阻碍而无法完成时，说明情况并调用 answer。"
            if stage == "draft_build" and draft is not None and not facts.get("version_saved")
            and facts.get("production_requested")
            else None
        ),
        include_observation_media=(
            stage in {"none", "briefing", "draft_build"}
            or (stage == "draft_review" and bool(draft_facts.get("awaiting_judgment")))
        ),
    )


def intent_router_system() -> str:
    return chat_system("plan")


def chat_intent_system() -> str:
    return chat_system("conversation")


def trigger_system() -> str:
    return chat_system("event")


def delivery_system() -> str:
    return chat_system("delivery")
