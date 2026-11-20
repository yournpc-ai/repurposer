"""Render the four existing Chat routes and their shared video rounds."""

import json
from copy import deepcopy
from dataclasses import replace
from typing import Literal

from app.chat.editor import EDITOR_NAMES

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
    staged_media: bool = False,
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
        staged_media=staged_media,
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
    if confirmation is not None:

        action = confirmation["action"]
        action_tool = {
            "produce": "present_plan" if facts["mode"] == "plan" else "propose_tasks",
            "start": "start_run",
        }.get(action)
        rules = {
            "produce": "用户已批准制作所展示的版本。简要介绍制作方案，调用制作提案工具。服务端负责提供任务并绑定确切版本。",
            "start": "用户已确认待执行的制作报价。用空参数调用 start_run。",
            "wait": "告知用户分镜仍在展示，待完整可见后即可确认。",
            "stale": "告知用户分镜已有修改，需先展示当前版本再制作。",
            "already_started": "根据给定的 run_status 和交付事实，告知用户该分镜已请求制作。若为 completed，说明已有结果可在视频卡片查看；若为 pending 或 running，说明正在安排或制作。其他情况按实际状态说明，不猜测。",
        }
        available = [tool for tool in facts["tools"] if tool.name in {action_tool, "answer"}]
        if action == "produce":

            def confirmation_wire(description, parameters):
                return (
                    "展示服务端为已批准视频绑定的制作任务，供执行。",
                    prune_wire_parameters(parameters, set(parameters.get("properties", {})) - {"name"}),
                )

            available = [
                replace(tool, wire_view=confirmation_wire) if tool.name == action_tool else tool
                for tool in available
            ]
        return RoundAssembly(
            tools=available,
            system=f"用用户在本次对话中使用的语言作答。{rules[action]} 若只需告知情况，先在消息正文中说明，再调用 answer。",
            context=json.dumps({"video_confirmation": confirmation}, ensure_ascii=False),
            stage="video_confirmation",
            include_project_context=False,
            include_observation_media=False,
            opening_text=facts.get("user_text") or "",
        )

    if facts.get("draft_finalized"):

        presentation = jinja_env.get_template("chat/_video_presentation.j2").render()
        return RoundAssembly(
            tools=[tool for tool in facts["tools"] if tool.name == "answer"],
            system=(
                "用用户在本次对话中使用的语言作答。已审阅的草稿已经保存。根据 design_video 的结果在正文中展示该保存版本，然后调用 answer。\n" + presentation
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
    snapshot = facts.get("snapshot")
    resources = list(getattr(snapshot, "resources", ()) or ())
    works = [r for _, r in resources if r.get("kind") == "composition"]
    hint = facts.get("target_hint") or {}
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
            "selected": selected["base_ref"] if selected else None,
            "project": next(({k: r.get(k) for k in ("title", "project_id", "user_stated_constraints")}
                             for _, r in resources if r.get("kind") == "project"), None),
            "assets": [{k: r.get(k) for k in ("asset_id", "type", "name")} for _, r in resources if r.get("kind") == "asset"][:24],
        }
        if selected:
            context.update(clip_count=selected.get("clip_count"), scene_count=selected.get("scene_count"),
                           timebase=selected.get("timebase"), duration_ticks=selected.get("duration_ticks"),
                           selected_region=hint.get("selected_region"))
        names = EDITOR_NAMES | {"read_conversation_context", "answer", "ask_user", "list_project_media", "review_video"}

        def dialogue_wire(description, parameters):
            return description, prune_wire_parameters(parameters, {
                "brief", "material_text", "material_urls", "items", "slot",
            })

        tools = [t for t in facts["tools"] if t.name in names]
        tools = [replace(t, wire_view=dialogue_wire, description=(
            "用自然语言报告实际结果，同时调用 answer 结束本轮。" if t.name == "answer" else
            "询问一个确定目标所需的问题。"
        )) if t.name in {"answer", "ask_user"} else t for t in tools]
        if pending:
            context["pending_question"] = getattr(pending, "question", None)
        return RoundAssembly(
            tools=tools,
            system="你是视频剪辑师。先读取当前时间线定位用户描述的片段。目标不明确时询问。"
                   "依据工具返回的实际结果用用户的语言答复。预览只说明实际观察到的内容。"
                   "对用户用片段顺序和时间称呼目标，技术标识仅用于工具参数。完成后在正文中回答并调用 answer。",
            context=json.dumps(context, ensure_ascii=False), include_project_context=False,
            opening_text=facts.get("user_text") or "", enforce_offered_tools=True,
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
        and facts.get("new_result_tool") in {"design_video", "prepare_visual_assets"}
        and resolution.get("draft") is not None
        and resolution.get("stage") != "draft_build"
    ):
        resolution["stage"] = "draft_build"
    resolution.setdefault("readiness", readiness)
    resolution["selected_region"] = (facts.get("target_hint") or {}).get("selected_region")
    media_state = None
    if facts.get("media_journey") and resolution["stage"] in {
        "draft_build", "draft_review", "draft_repair", "draft_finalize", "draft_hold",
    }:
        from app.chat.media_journey import allowed_media_tools, audio_timing_issue, media_actions

        resolution["stage"] = "draft_build"
        current = resolution.get("draft")
        media_state = media_actions(
            current.arguments if current is not None else None,
            facts.get("media_visual_results") or [],
        )
        resolution["media_phase"] = media_state["phase"]
        permitted = allowed_media_tools(media_state["phase"])
        if media_state["phase"] == "audio":
            from app.agents.working_drafts import working_draft_review_facts

            scenes = working_draft_review_facts(current.arguments)["scenes"]
            resolution["scenes_filled"] = bool(scenes) and all(scene["clip_ids"] for scene in scenes)
            timing_issue = audio_timing_issue(current.arguments)
            media_state["audio_timing_ready"] = timing_issue is None
            media_state["timing_issue"] = timing_issue
            settled = facts.get("settled_narration")
            if settled is not None:
                from app.chat.media_journey import narration_resume_state

                resume = narration_resume_state(current.arguments, settled)
                media_state["narration_resume"] = resume
                if any(not scene.get("timing_confirmed") for scene in resume["scenes"]):
                    media_state["audio_timing_ready"] = False
            if not media_state["audio_timing_ready"]:
                permitted = permitted - {"prepare_music"}
    tools = video_round_tools(
        facts["tools"],
        resolution=resolution,
        snapshot=facts.get("snapshot"),
        skill=facts.get("skill"),
        material_pending=facts.get("material_pending", False),
        package_sessions=facts.get("package_sessions"),
        user_text=facts.get("user_text") or "",
    )
    if media_state is not None:
        tools = [tool for tool in tools if tool.name in permitted or tool.name in EDITOR_NAMES]
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
            if media_state is not None and "narration_resume" in media_state:
                bound = {
                    (row["scene_id"], row["alignment_id"]) for row in media_state["narration_resume"]["scenes"]
                    if row.get("timing_confirmed")
                }
                dynamic["narrations"] = [
                    fact for fact in dynamic["narrations"]
                    if (fact["scene_id"], (fact.get("alignment") or {}).get("alignment_id")) in bound
                ]
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
        and media_state is not None and media_state["phase"] == "images"
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
    if media_state is not None:
        dynamic["media_preparation"] = media_state
        if media_state["phase"] == "audio":
            dynamic["media_instruction"] = (
                "approved_images 中的每项对应相应场景已准备好的图片。在 design_video.scene 中直接使用它的 snapshot_id，传入相符的 scene_id 和确切的口播原文。"
                "先写完所有需要旁白的场景，再把同一最新 draft_ref 的各场 prepare_narration 调用组成一个 tool_calls 数组。录制完成后逐场读取实际对齐结果，标注至 READY，按实测时长和提示点确认时序，再准备配乐。"
            )
            required_next = "prepare_music" if media_state["audio_timing_ready"] else None
            resume = media_state.get("narration_resume")
            if resume is None and resolution["scenes_filled"] and not media_state["audio_timing_ready"]:
                dynamic["media_instruction"] = "各幕已填入画面和旁白。以当前 draft_ref 将待录场景一并提交 prepare_narration。"
                required_next = "prepare_narration"
            if resume is not None:
                dynamic["media_instruction"] = (
                    "旁白已录制。以本轮 draft_ref 和 narration_resume 为准。scenes 只列与当前原文、声音和语言一致的录音引用。"
                    "matched_audio_seconds 是已匹配的实测总长，remaining_seconds 是目标总长扣除这些录音后留给其余旁白和停顿的时间。"
                    "若剩余时间为负，或不足以容纳待录旁白，请先逐幕精简文案，给所有待录幕留足空间，由你决定各幕取舍和时长。"
                    "用 design_video.narration_update 改稿时传 scene_id、text，可带 target_duration_seconds，省略 alignment_id。"
                    "改完后用最新 draft_ref，将 pending_scene_ids 的 prepare_narration 一次并行提交。"
                    "保留录音时读取它的对齐，按需标注至 READY。确认时仅传 scene_id、alignment_id 和可选的 target_duration_seconds。"
                    "每次写入后用下一轮的新 draft_ref。所有幕的原音、提示点和目标总长核实后准备配乐。"
                )
                if not media_state["audio_timing_ready"]:
                    remaining = resume["remaining_seconds"]
                    if remaining is not None and (remaining < 0 or remaining == 0 and resume["pending_scene_ids"]):
                        required_next = "design_video"
                        if not facts.get("interim_prose_count"):
                            dynamic["media_instruction"] += (
                                "这次实测牵涉剪辑取舍。改稿时在同一响应的正文中，用对话语言告诉用户"
                                "录音和目标时长差多少、你会精简哪部分来保住哪句重点，然后动手。"
                            )
                    elif not resume["pending_scene_ids"]:
                        if all(s["timing_confirmed"] for s in resume["scenes"]):
                            required_next = "design_video"
                        elif facts.get("iteration") == 0:
                            required_next = "get_narration_alignment"
        elif media_state["phase"] == "images_blocked":
            dynamic["media_instruction"] = "说明哪些场景遇到阻碍，然后停止。"
            required_next = "answer"
        else:
            dynamic["media_instruction"] = (
                "只写入 scene_plan 和 scene_assets，再准备当前图片。使用现有图片时，对照页面、视图标题和像素，确认与目标场景相符。"
                "将源图必须显示的证据放在 source.visible_evidence，剪辑时叠加的内容放在 on_screen_copy。来源不对时，改选正确的固定图片或换用其他来源方式。"
                "对列入重试的场景使用 review_existing。局部修复失败内容，按 scene_failures 修正无效 SVG。如果供应商执行结果未知，选择本地来源。保留已批准场景。"
            )
            if media_state["missing_scene_ids"] or media_state["review_retry_scene_ids"]:
                required_next = "prepare_visual_assets"
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
            staged_media=media_state is not None,
            website_promo=readiness.task_kind == "website_promo",
        ),
        context="\n\n".join(context_parts),
        stage=stage,
        include_project_context=include_project_context,
        observation_tools=(
            frozenset({
                "design_video", "prepare_visual_assets", "prepare_video_materials", "capture_web",
                "prepare_narration", "get_narration_alignment", "annotate_narration", "prepare_music",
            })
            if draft is not None and stage in {"draft_build", "draft_finalize", "draft_hold"}
            else None
        ),
        stream_prose=not awaiting_brief,
        acknowledgment=acknowledgment,
        enforce_offered_tools=readiness.task_kind == "website_promo" and (
            stage in {"source_preparing", "briefing"} or (stage == "draft_build" and draft is None)
        ),
        invitation_tool=(
            "ask_user" if any(tool.name == "ask_user" for tool in tools) else None
        ),
        missing_tool_feedback=(
            "请通过原生 tool_calls 调用 ask_user，把全部缺失选项放进同一份问卷。正文只写给用户的邀请。"
            if awaiting_brief and pending is None else
            "使用可用工具继续准备当前媒体，或调用 answer 说明确切阻碍。"
            if media_state is not None and media_state["phase"] in {"images", "audio"} else
            "用户请求的视频仍是未保存的草稿。可以继续时，调用 design_video 完成下一步写入或保存。需要用户决定时调用 ask_user。"
            "确有已核实的阻碍而无法完成时，说明情况并调用 answer。"
            if media_state is None and stage == "draft_build" and draft is not None and not facts.get("version_saved")
            and facts.get("production_requested")
            else None
        ),
        include_observation_media=(
            stage in {"none", "briefing", "draft_build"}
            or (stage == "draft_review" and bool(draft_facts.get("awaiting_judgment")))
        ),
        caller_state={"media_state": media_state},
    )


def intent_router_system() -> str:
    return chat_system("plan")


def chat_intent_system() -> str:
    return chat_system("conversation")


def trigger_system() -> str:
    return chat_system("event")


def delivery_system() -> str:
    return chat_system("delivery")
