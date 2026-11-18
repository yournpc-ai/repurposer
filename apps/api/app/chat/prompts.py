"""Render the four existing Chat routes and their shared video rounds."""

import json
import re
from copy import deepcopy
from dataclasses import replace
from typing import Literal

from pydantic import create_model, field_validator

from app.agents.base import jinja_env
from app.agents.tool_loop import RoundAssembly
from app.tools import tool_catalog_lines

ChatMode = Literal["plan", "conversation", "event", "delivery"]

_QUOTED_TITLE_EDIT = re.compile(
    r'把(?:刚才保存(?:的)?作品的)?(?:第(?P<zh_scene>[一二三四五六七八九1-9])幕的?)?标题'
    r'(?:改为|改成)[“"](?P<zh_text>[^”"]+)[”"][。.]?'
    r'(?:只改这个标题(?:[，,]不要重新审片)?(?:[，,]不要制作或渲染正式视频)?[。.]?)?'
    r'|(?:change|set|replace) the (?:(?P<en_scene>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth) scene(?:’s|\x27s)? )?'
    r'title (?:to|with) [“"](?P<en_text>[^”"]+)[”"][.!]?',
    re.IGNORECASE,
)


def _compact_title_round(facts: dict, resolution: dict, tools: list) -> RoundAssembly | None:
    """Project an explicit, standalone title replacement without the project catalog."""
    if (
        resolution["stage"] != "version_edit" or resolution.get("pending") is not None
        or facts.get("active_repair") is not None or facts.get("material_pending")
    ):
        return None
    user_text = (facts.get("user_text") or "").strip()
    match = _QUOTED_TITLE_EDIT.fullmatch(user_text)
    if not match:
        return None
    new_text = match["zh_text"] or match["en_text"]
    if not new_text.strip() or len(new_text) > 9000:
        return None
    target = resolution["target"]
    ordinal = match["zh_scene"] or match["en_scene"]
    scene_id = None
    if ordinal:
        if ordinal.isascii() and ordinal.isdigit():
            index = int(ordinal) - 1
        else:
            ordinals = (
                list("一二三四五六七八九") if match["zh_scene"]
                else "first second third fourth fifth sixth seventh eighth ninth".split()
            )
            index = ordinals.index(ordinal.lower())
        scenes = sorted(target.get("scenes") or [], key=lambda scene: (scene.get("range") or {}).get("start", 0))
        if index >= len(scenes):
            return None
        scene_id = scenes[index]["scene_id"]
    candidates = [
        {key: clip[key] for key in ("clip_id", "scene_id", "text") if key in clip}
        for clip in target.get("clip_targets") or []
        if clip.get("object_kind") == "text" and not clip.get("derived_caption")
        and (scene_id is None or clip.get("scene_id") == scene_id)
    ]
    if not candidates:
        return None
    saved = facts.get("version_saved", False)
    if saved:
        names = {"answer"}
    elif len(candidates) != 1:
        names = {"ask_user"}
    else:
        names = {"revise_video", "answer"}
    base_ref = target["base_ref"]
    compact_tools = [tool for tool in tools if tool.name in names]
    if "revise_video" in names:
        from app.models.schemas import ReviseVideoTextArgs

        def current_base(value):
            if value.model_dump(mode="json") != base_ref:
                raise ValueError("use the current base_ref for the selected work")
            return value

        scoped_args = create_model(
            "ScopedVideoTextRevision", __base__=ReviseVideoTextArgs,
            __validators__={"current_base": field_validator("base_ref")(current_base)},
            clip_id=(Literal[candidates[0]["clip_id"]], ...),
            text=(Literal[new_text], ...),
        )
        compact_tools = [
            replace(tool, params_model=scoped_args, wire_view=None, repairable=False,
                    description="Replace exactly one native Text Clip's text; preserve all other content.")
            if tool.name == "revise_video" else tool
            for tool in compact_tools
        ]
    if not compact_tools:
        return None

    if saved:
        rule = (
            "In your message text, confirm the actual saved title change in one short sentence. "
            "Then call answer. An answer call without message text does not finish the turn."
        )
    elif len(candidates) != 1:
        rule = "Call ask_user with the relevant title choices and wait for the user's answer."
    else:
        rule = (
            "Use the supplied current base_ref and exact title target to call revise_video directly. "
            "If the current text already equals the request, use answer to say so. "
            "After a rejected write, use the refreshed facts or report the actual blocker. "
            "Claim a save only after the tool confirms it."
        )
    dynamic = {
        "video_stage": "version_edit",
        "base_ref": base_ref, "title_targets": candidates,
    }
    return RoundAssembly(
        tools=compact_tools,
        system=f"You are the Rookie Cut video editor. Reply in the language the user speaks in this conversation. {rule}",
        context="CURRENT VIDEO ROUND (server-derived target and state; not model claims):\n"
        + json.dumps(dynamic, ensure_ascii=False),
        stage="version_edit", include_project_context=False, include_observation_media=False,
        allow_interim_prose=True, opening_text=user_text,
    )


def chat_system(
    mode: ChatMode,
    *,
    available_tools: list | None = None,
    video_stage: str = "none",
    video_speech: str | None = None,
    scene_authoring: bool = False,
    staged_media: bool = False,
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


def _region_target_candidates(target: dict, region: dict) -> list[dict]:
    from app.tools.project_context import region_target_candidates

    return region_target_candidates(target, region)


def _target_resource_projection(target: dict, region: dict | None) -> dict:
    keys = (
        "kind", "composition_id", "name", "version_id", "version", "content_digest",
        "base_ref", "schema_version", "skill_provenance", "settings", "sources",
    )
    projected = {key: target[key] for key in keys if key in target}
    projected["scenes"] = [
        {key: scene[key] for key in ("scene_id", "range", "intent") if key in scene}
        for scene in target.get("scenes") or []
    ]
    projected["clip_targets"] = (
        _region_target_candidates(target, region)
        if region is not None else list(target.get("clip_targets") or [])
    )
    return projected


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
            "produce": "The user approved production of the presented version. Introduce the production plan briefly and call the production proposal tool. The server supplies the task and exact version.",
            "start": "The user confirmed the pending production quote. Call start_run with empty parameters.",
            "wait": "Tell the user the storyboard is still presenting and can be confirmed once it is visible.",
            "stale": "Tell the user the storyboard has changed and the current version needs to be presented before production.",
            "already_started": "Tell the user that production has already been requested for this storyboard, using the supplied run_status and delivery facts. If run_status is completed, tell them the existing result is ready and point to its video card; if it is pending or running, tell them it is underway. Otherwise state the exact status without guessing.",
        }
        available = [tool for tool in facts["tools"] if tool.name in {action_tool, "answer"}]
        if action == "produce":
            from app.agents.tool_loop import prune_wire_parameters

            def confirmation_wire(description, parameters):
                return (
                    "Dock the approved video's server-bound production task.",
                    prune_wire_parameters(parameters, set(parameters.get("properties", {})) - {"name"}),
                )

            available = [
                replace(tool, wire_view=confirmation_wire) if tool.name == action_tool else tool
                for tool in available
            ]
        return RoundAssembly(
            tools=available,
            system=f"Reply in the language the user speaks in this conversation. {rules[action]} For an informational reply, speak in message text then call answer.",
            context=json.dumps({"video_confirmation": confirmation}, ensure_ascii=False),
            stage="video_confirmation",
            include_project_context=False,
            include_observation_media=False,
            allow_interim_prose=True,
            opening_text=facts.get("user_text") or "",
        )

    if facts.get("draft_finalized"):

        presentation = jinja_env.get_template("chat/_video_presentation.j2").render()
        return RoundAssembly(
            tools=[tool for tool in facts["tools"] if tool.name == "answer"],
            system=(
                f"Reply in the language the user speaks in this conversation. The reviewed draft is already saved. "
                "Present that saved version from the design_video result, then call answer. "
                "Use message text for the presentation.\n" + presentation
            ),
            context='CURRENT VIDEO ROUND (server-derived target and state; not model claims):\n'
            '{"video_stage": "draft_present"}',
            stage="draft_present", include_project_context=False,
            include_observation_media=False, observation_tools=frozenset({"design_video"}),
            allow_interim_prose=True,
        )

    pending = facts.get("pending_question")
    if callable(pending):
        pending = pending()
    from app.chat.readiness import compute_source_readiness, render_readiness_context

    creative_state = facts.get("creative_state")
    if callable(creative_state):
        creative_state = creative_state()
    snapshot = facts.get("snapshot")
    resources = list(getattr(snapshot, "resources", ()) or ())
    readiness = compute_source_readiness(
        user_text=facts.get("user_text") or "",
        source_text=facts.get("source_text"),
        assets=[resource for _key, resource in resources if resource.get("kind") == "asset"],
        snapshots=[resource for _key, resource in resources if resource.get("kind") == "web"],
        creative_state=creative_state,
        draft_present=bool(facts.get("drafts")),
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
    tools = video_round_tools(
        facts["tools"],
        resolution=resolution,
        snapshot=facts.get("snapshot"),
        skill=facts.get("skill"),
        material_pending=facts.get("material_pending", False),
        package_sessions=facts.get("package_sessions"),
        user_text=facts.get("user_text") or "",
    )
    media_state = None
    if facts.get("media_journey") and resolution["stage"] in {
        "draft_build", "draft_review", "draft_repair", "draft_finalize", "draft_hold",
    }:
        from app.chat.media_journey import allowed_media_tools, audio_timing_ready, media_actions

        resolution["stage"] = "draft_build"
        current = resolution.get("draft")
        media_state = media_actions(
            current.arguments if current is not None else None,
            facts.get("media_visual_results") or [],
        )
        permitted = allowed_media_tools(media_state["phase"])
        if media_state["phase"] == "audio":
            media_state["audio_timing_ready"] = audio_timing_ready(current.arguments)
            if not media_state["audio_timing_ready"]:
                permitted = permitted - {"prepare_music"}
        tools = [tool for tool in tools if tool.name in permitted]
    compact = _compact_title_round(facts, resolution, tools)
    if compact is not None:
        return compact
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
        if resolution.get("target") is not None:
            target = resolution["target"]
            region = (facts.get("target_hint") or {}).get("selected_region")
            resources = [(
                f"composition:{target['version_id']}:{target['content_digest']}",
                _target_resource_projection(target, region),
            )]
        elif draft is not None:
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
                            "Source text was available during scene planning. For exact wording or new target facts, "
                            "read this snapshot with prepare_video_materials material_targets."
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
    elif resolution.get("target") is not None:
        target = resolution["target"]
        dynamic["base_ref"] = target["base_ref"]
        dynamic["target_composition_id"] = target["composition_id"]
        selected_region = (facts.get("target_hint") or {}).get("selected_region")
        if selected_region is not None:
            dynamic["selected_region"] = selected_region
            dynamic["region_target_candidates"] = [
                {
                    key: candidate[key]
                    for key in (
                        "clip_id", "object_id", "scene_id", "object_kind",
                        "range", "motion_at_selection",
                    )
                    if key in candidate
                }
                for candidate in _region_target_candidates(target, selected_region)
            ]
    elif resolution.get("candidates") is not None:
        dynamic["target_candidates"] = [
            {
                "composition_id": resource["composition_id"],
                "name": resource.get("name"),
                "base_ref": resource["base_ref"],
            }
            for resource in resolution["candidates"]
        ]
    if facts.get("active_repair") is not None:
        dynamic = {
            "video_stage": "candidate_repair",
            "instruction": "Correct only the retained candidate with the sole available correction tool.",
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
                "rule": "Copy one exact id from each list; aliases are rejected.",
            }
    draft_facts = dynamic.get("draft") or {}
    if media_state is not None:
        dynamic["media_preparation"] = media_state
        dynamic["media_instruction"] = (
            "The initial make request authorizes continuation subject to ordinary execution and "
            "credit policy. Preparation tools hand a verified task to the server automatically. "
            "During images, write only scene_plan and scene_assets, then prepare current pictures. "
            "Use review_existing for the listed retry scenes. Repair failed content locally. "
            "Use scene_failures to correct invalid SVG sources, and choose a local source when "
            "the provider outcome is unknown. Keep approved scenes unchanged. "
            "If the server lists blocked scenes, report them and stop. "
            "During audio, author draft scenes, prepare and align narration, retime from actual "
            "durations, then prepare electronic music. Do not request another user decision, "
            "search the music library, save the Composition or render."
        )
    if readiness.task_kind == "website_promo":
        dynamic["required_next_action"] = readiness.required_next_action
        context_parts.append(render_readiness_context(readiness))
    context_parts.append(
        "CURRENT VIDEO ROUND (server-derived target and state; not model claims):\n"
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
            scene_authoring=scene_authoring,
            staged_media=media_state is not None,
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
        allow_interim_prose=True,
        missing_tool_feedback=(
            "Continue the current media preparation using an available tool, or answer with the exact blocker."
            if media_state is not None and media_state["phase"] in {"images", "audio"} else
            "This requested video is still an unsaved draft. If you can proceed, call design_video "
            "for the next write or save. If a user decision is required, call ask_user. "
            "If a verified blocker prevents completion, state it and call answer."
            if media_state is None and stage == "draft_build" and draft is not None and not facts.get("version_saved")
            and facts.get("production_requested")
            else None
        ),
        include_observation_media=(
            stage in {"none", "briefing", "draft_build"}
            or (stage == "draft_review" and bool(draft_facts.get("awaiting_judgment")))
        ),
        caller_state={"video_target": resolution.get("target"), "media_state": media_state},
    )


def intent_router_system() -> str:
    return chat_system("plan")


def chat_intent_system() -> str:
    return chat_system("conversation")


def trigger_system() -> str:
    return chat_system("event")


def delivery_system() -> str:
    return chat_system("delivery")
