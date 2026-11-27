"""Layer 0 pure contracts: Chat turn tool-surface gating, rejection loop bounds, speech language, and sanitized interim prose."""

from __future__ import annotations
import pytest

import json


from types import SimpleNamespace


from app.chat.editor import EDITOR_NAMES


import pytest


from app.providers.llm.base import LLMSchemaError, ToolCall


from app.providers.llm.minimax import (
    _MiniMaxToolMarkupStripper,
    _ToolCallAccumulator,
    _parse_tool_arguments,
    _strip_minimax_tool_markup,
    _tool_call_from_object,
)


def _fragment(idx: int, name: str | None = None, args: str | None = None,
              call_id: str | None = None) -> dict:
    """One ``delta.tool_calls[]`` entry as the provider streams it."""
    fn: dict = {}
    if name is not None:
        fn["name"] = name
    if args is not None:
        fn["arguments"] = args
    out: dict = {"index": idx, "function": fn}
    if call_id is not None:
        out["id"] = call_id
    return out


def _composition_resource(*, suffix="one", provenance=None):
    from uuid import NAMESPACE_URL, uuid5

    composition_id = str(uuid5(NAMESPACE_URL, f"test-composition-{suffix}"))
    version_id = str(uuid5(NAMESPACE_URL, f"test-version-{suffix}"))
    return {
        "kind": "composition",
        "composition_id": composition_id,
        "version_id": version_id,
        "content_digest": "d" * 64,
        "name": f"Work {suffix}",
        "base_ref": {
            "composition_id": composition_id,
            "composition_version_id": version_id,
            "content_digest": "d" * 64,
        },
        "skill_provenance": provenance or {},
        "scenes": [{"scene_id": "second"}],
        "clip_targets": [{"clip_id": "title-second", "text": "Old title"}],
    }


def _video_round(tools, *, drafts=(), snapshot, skill=None, material_pending=False,
                 package_sessions=None, user_text="review the draft", pending_question=None,
                 active_repair=None, mode="plan", iteration=None, interim_prose_count=0,
                 new_result=False, version_saved=False, new_result_tool=None, asset_mentions=None, attachments=()):
    from app.chat.prompts import assemble_video_round

    return assemble_video_round({
        "tools": tools,
        "drafts": drafts,
        "snapshot": snapshot,
        "skill": skill,
        "material_pending": material_pending,
        "package_sessions": package_sessions,
        "user_text": user_text,
        "version_saved": version_saved,
        "pending_question": pending_question,
        "active_repair": active_repair,
        "mode": mode,
        "iteration": iteration,
        "interim_prose_count": interim_prose_count,
        "new_result": new_result,
        "new_result_tool": new_result_tool,
        "asset_mentions": asset_mentions,
        "attachments": attachments,
    })


def test_bound_skill_tools_follow_material_and_saved_version_state():
    from types import SimpleNamespace
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.conversation_context import conversation_context_tool
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill

    skill = SimpleNamespace(skill_id="promo-video")
    declared = [*tools_for_bound_skill(intent_router.tools, skill), conversation_context_tool()]

    fresh = _video_round(
        declared, snapshot=ContextSnapshot("fresh", frozenset({"project:one"})),
        skill=skill, material_pending=True,
    ).tools
    fresh_names = {tool.name for tool in fresh}
    assert not {"get_graph", "get_node", "edit_graph"} & fresh_names
    assert "design_video" not in fresh_names
    assert "get_understanding" in fresh_names
    assert "prepare_video_materials" in fresh_names
    assert "read_conversation_context" in fresh_names
    assert {"ask_user", "answer"} <= fresh_names

    prepared = _video_round(
        declared,
        snapshot=ContextSnapshot(
            "prepared", frozenset({"project:one", "snapshot:source:digest"}),
            resources=(("snapshot:source:digest", {"kind": "image", "snapshot_id": "source", "digest": "d" * 64}),),
        ),
        skill=skill, material_pending=True,
    ).tools
    assert "create_video" in {tool.name for tool in prepared}
    assert "present_plan" not in {tool.name for tool in prepared}

    saved_resource = _composition_resource(provenance={"skill": "promo-video"})
    saved = _video_round(
        declared,
        snapshot=ContextSnapshot(
            "saved", frozenset({"project:one", "snapshot:source:digest", "composition:version:digest"}),
            resources=(("composition:version:digest", saved_resource),),
        ),
        skill=skill, material_pending=True, user_text="change the title",
    ).tools
    saved_names = {tool.name for tool in saved}
    assert {"split_clip", "inspect_timeline", "preview_range"} <= saved_names
    assert not {"revise_video", "present_plan", "start_run"} & saved_names
    assert "design_video" not in saved_names
    assert "create_video" not in saved_names


def test_scene_plan_and_explicit_count_have_no_six_scene_cap():
    from app.skills.external import SkillPolicy
    from app.chat.editor_create import CreateVideoArgs

    args = CreateVideoArgs.model_validate({
        "name": "Seven beats",
        "shots": [{"headline": f"Beat {index}", "duration_seconds": 1} for index in range(7)],
    })
    assert len(args.shots) == 7
    assert SkillPolicy(scene_count=7).scene_count == 7


@pytest.mark.asyncio
async def test_derived_web_view_infers_its_unique_view_id():
    from uuid import uuid4

    from app.editing.schemas import CompositionContent, VersionSettings
    from app.editing.validators import validate_content
    from app.tools.video.design import (
        CompositionSceneAuthoring,
        CompositionScenePlan,
        _expand_scene_authoring,
        _scene_plan_write,
    )

    parent_id, derived_id = uuid4(), uuid4()
    facts = {
        parent_id: {
            "kind": "web", "digest": "p" * 64, "storage_key": "web.json",
            "meta": {"views": [{
                "view_id": "view-3", "storage_key": "view.png", "digest": "v" * 64,
                "width": 1440, "height": 900, "elements": [],
            }]},
        },
        derived_id: {
            "kind": "image", "digest": "d" * 64, "storage_key": "derived.png",
            "meta": {
                "origin": "web_view", "web_snapshot_id": str(parent_id), "view_id": "view-3",
                "width": 1440, "height": 900,
            },
        },
    }
    content = _scene_plan_write({
        "schema_version": 1,
        "settings": VersionSettings(width=1920, height=1080).model_dump(mode="json"),
        "sources": [], "scenes": [], "timeline": {"tracks": [], "transitions": []},
    }, [CompositionScenePlan(scene_id="feature", intent="Show the actual feature")])
    expanded = await _expand_scene_authoring(content, CompositionSceneAuthoring(
        scene_id="feature", snapshot_id=derived_id, source_motion="hold", headline="Feature",
    ), facts)
    candidate = CompositionContent.model_validate(expanded)
    validate_content(candidate, facts)
    web = next(clip for track in candidate.timeline.tracks for clip in track.clips if clip.object.kind == "web")
    assert web.object.view_id == "view-3"
    assert web.source.snapshot_id == parent_id


def test_missing_package_session_uses_native_create_protocol(installed_promo):
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.skills.resolution import get_builtin_skill_option

    skill = get_builtin_skill_option("promo-video").reference
    declared = tools_for_bound_skill(intent_router.tools, skill)
    projected = _video_round(
        declared,
        snapshot=ContextSnapshot("fresh", frozenset({"project:one"})),
        skill=skill,
        package_sessions={},
    )
    create = next(tool for tool in projected.tools if tool.name == "create_video")
    properties = tool_spec(create)["function"]["parameters"]["properties"]
    assert "shots" in properties and "scene_plan" not in properties
    assert "create_video" in {tool.name for tool in projected.tools}


def test_saved_and_ambiguous_work_use_editor_without_legacy_draft_review():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    saved = _composition_resource()
    snapshot = ContextSnapshot(
        "complete project and an unrelated asset", frozenset({"composition:ver-one:digest"}),
        resources=(("composition:ver-one:digest", saved),
                   ("asset:first", {"kind": "asset", "asset_id": "first", "type": "image"}),
                   ("asset:second", {"kind": "asset", "asset_id": "second", "type": "image"})),
    )
    edited = _video_round(intent_router.tools, snapshot=snapshot, user_text="Change the second Scene title",
                          asset_mentions={"first": "product.png", "second": "product.png", "foreign": "other.png"})
    assert json.loads(edited.context)["mentioned_assets"] == [
        {"asset_id": asset_id, "type": "image", "label": "product.png"} for asset_id in ("first", "second")
    ]
    from app.models.schemas import ChatAttachment

    attachments = [ChatAttachment(id=id_, type="image", name="product.png")
                   for id_ in ("second", "foreign", "first")]
    attached = _video_round(intent_router.tools, snapshot=snapshot, attachments=attachments)
    assert json.loads(attached.context)["opening_attachments"] == [
        {"position": pos, "asset_id": id_, "type": "image", "name": "product.png"}
        for pos, id_ in [(1, "second"), (3, "first")]
    ]
    assert edited.caller_state["video_target"] == saved
    assert (EDITOR_NAMES - {"create_video", "instantiate_skill_blueprint"}) <= {tool.name for tool in edited.tools}
    assert not {"design_video", "review_working_draft"} & {tool.name for tool in edited.tools}
    assert "complete project and an unrelated asset" not in edited.context
    assert "title-second" not in edited.context
    assert edited.include_observation_media
    presenting = _video_round(intent_router.tools, snapshot=snapshot, version_saved=True,
                              user_text="Review the draft and deliver the MP4")
    assert presenting.caller_state["video_target"] == saved
    assert (EDITOR_NAMES - {"create_video", "instantiate_skill_blueprint"}) <= {tool.name for tool in presenting.tools}
    draft_only = _video_round(intent_router.tools, snapshot=snapshot, version_saved=True,
                             user_text="请保存初稿给我看。")
    assert {t.name for t in draft_only.tools} == {"answer"}

    other = _composition_resource(suffix="two")
    ambiguous = _video_round(
        intent_router.tools,
        snapshot=ContextSnapshot("two", resources=(("one", saved), ("two", other))),
    )
    assert ambiguous.caller_state["video_target"] is None
    assert (EDITOR_NAMES - {"create_video", "instantiate_skill_blueprint", "save_composition_as_skill"}) <= {tool.name for tool in ambiguous.tools}
    assert "ask_user" in {tool.name for tool in ambiguous.tools}


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_final_video_provider_request_clears_pending_and_historical_media(
    monkeypatch, streaming,
):
    from app.agents import tool_loop
    from app.chat.intent import intent_router
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration

    calls = []
    pending = SimpleNamespace(
        id="question-1", content="Which title?", question={"question": "Which title?"},
        intent={"question": {"question": "Which title?"}},
    )
    saved = _composition_resource()
    snapshot = tool_loop.ContextSnapshot(
        "full project", frozenset({"composition:ver-one:digest"}),
        resources=(("composition:ver-one:digest", saved),),
    )
    historical = {
        "role": "tool", "tool_call_id": "old", "content": [
            {"type": "text", "text": "old review"},
            {"type": "video", "caption": "Historical observation old", "data_url": "data:video/mp4;base64,AA=="},
        ],
    }

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            return await self.answer(**kwargs)

        async def generate_stream_with_tools(self, **kwargs):
            return await self.answer(**kwargs)

        async def answer(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ToolGeneration("", [ToolCall(
                    id="split-1", name="split_clip",
                    arguments={"clip_id": "title-second", "time": 1},
                )])
            return ToolGeneration("Saved", [ToolCall(id="answer-1", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "current user request"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name=f"video-round-{streaming}", prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None), tools=intent_router.tools, client=Client(),
    )

    async def restore(_snapshot, _messages):
        return tool_loop.ConversationHistory(messages=(historical,))

    async def execute(name, _params, _speech):
        nonlocal pending
        if name == "split_clip":
            pending = None
            return tool_loop.ToolObservation("saved")
        return None

    def assemble(**facts):
        from app.chat.prompts import assemble_video_round

        return assemble_video_round({
            **facts, "mode": "plan", "user_text": "Split the selected clip at one second.",
            "answered_this_opening": True,
            "pending_question": lambda: pending,
        })

    result = await agent.call_loop(
        execute, refresh_context=lambda: _immediate(snapshot), restore_context=restore,
        dialogue=[
            {"role": "user", "content": "old context" * 1000},
            {"role": "user", "content": "Keep the original audio."},
            {"role": "assistant", "content": "Which of the two titles should I split?"},
            {"role": "user", "content": "Second title"},
        ],
        round_assembler=assemble, on_delta=(lambda _text: _immediate(None)) if streaming else None,
    )
    assert result.tool_name == "answer"
    assert len(calls) == 2
    first, second = calls
    first_text = json.dumps(first["messages"], ensure_ascii=False)
    second_text = json.dumps(second["messages"], ensure_ascii=False)
    for wire in (first, second):
        speech = [m for m in wire["messages"] if m.get("content") in (
            "Keep the original audio.", "Which of the two titles should I split?", "Second title",
        )]
        assert [m["role"] for m in speech] == ["user", "assistant", "user"]
        assert "old context" not in str(wire["messages"])
        assert any("clarified_request" in str(m["content"]) and
                   "Split the selected clip at one second." in str(m["content"])
                   for m in wire["messages"])
    assert "Which title?" in first_text
    assert "Which title?" not in second_text
    assert "old review" not in second_text and "Historical observation old" not in second_text
    assert all(
        part.get("type") == "text"
        for message in second["messages"] if isinstance(message.get("content"), list)
        for part in message["content"] if isinstance(part, dict)
    )
    assert "review_working_draft" not in {
        item["function"]["name"] for item in second["tools"]
    }


async def _immediate(value):
    return value


def test_editor_tools_do_not_depend_on_requested_action():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    saved = _composition_resource()
    snapshot = ContextSnapshot("saved", resources=(("work", saved),))
    first = _video_round(intent_router.tools, snapshot=snapshot, user_text="Split the second clip")
    second = _video_round(intent_router.tools, snapshot=snapshot, user_text="Change the title")
    assert {t.name for t in first.tools} == {t.name for t in second.tools}
    assert (EDITOR_NAMES - {"create_video", "instantiate_skill_blueprint"}) <= {t.name for t in second.tools}
    assert not {"start_run", "revise_video", "design_video"} & {t.name for t in second.tools}
    assert "clip_targets" not in second.context and "title-second" not in second.context


def test_video_rounds_allow_service_text_for_reads_and_edits():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    for iteration in (0, 1, 6):
        projected = _video_round(intent_router.tools, snapshot=ContextSnapshot("empty"), iteration=iteration)
        assert projected.stream_prose
        assert "speech_rule" not in projected.context

    media = _video_round(
        intent_router.tools, snapshot=ContextSnapshot("empty"),
        user_text="Make a three-second ambient score only", new_result_tool="generate_music",
    )
    assert media.project_reply is not None and media.missing_tool_feedback is None

    saved = _composition_resource()
    edit = _video_round(
        intent_router.tools,
        snapshot=ContextSnapshot(
            "saved", resources=(("composition", saved),),
        ),
        user_text="Change the title", iteration=0, new_result=True,
    )
    assert edit.caller_state["video_target"] == saved
    assert edit.stream_prose and edit.project_reply is not None


def test_existing_media_only_offer_keeps_creation_and_excludes_generation():
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    turn = assemble_video_round({
        "tools": intent_router.tools, "snapshot": ContextSnapshot("empty"),
        "user_text": "Create a cut from the uploaded footage. No new media or export.",
    })
    tools = {tool.name: tool for tool in turn.tools}
    assert {"create_video", "prepare_video_materials"} <= tools.keys()
    assert not {"generate_voice", "generate_image", "generate_music", "export_video"} & tools.keys()
    shot = tool_spec(tools["create_video"])["function"]["parameters"]["$defs"]["FirstShot"]["properties"]
    assert "narration" not in shot and "snapshot_id" in shot


def test_fixed_recording_is_available_before_word_alignment():
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router

    audio = {"kind": "audio", "snapshot_id": "fixed", "alignment": {"status": "PROCESSING"}}
    snapshot = ContextSnapshot("fresh", resources=(("audio", audio),))
    from app.chat.prompts import assemble_video_round

    projected = assemble_video_round({
        "tools": intent_router.tools, "snapshot": snapshot, "user_text": "Create the video with this recording",
        "media_receipts": [{"role": "narration", "status": "available", "snapshot_id": "fixed"}],
    })
    tools = {tool.name: tool for tool in projected.tools}
    shot = tool_spec(tools["create_video"])["function"]["parameters"]["$defs"]["FirstShot"]["properties"]
    assert not {"narration", "narration_alignment_id", "narration_snapshot_id"} & shot.keys()
    assert "inspect_timeline" not in tools and "insert_audio" not in tools
    assert "fixed" in projected.context


def test_native_create_projection_keeps_skill_context(installed_promo):
    from types import SimpleNamespace
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill

    skill = SimpleNamespace(skill_id="promo-video")
    snapshot = ContextSnapshot("fresh", frozenset({"project:one"}), skill_method="COMPLETE SKILL METHOD FOR PLANNING")
    projected = _video_round(tools_for_bound_skill(intent_router.tools, skill), snapshot=snapshot, skill=skill)
    assert "create_video" in {tool.name for tool in projected.tools}
    assert "design_video" not in {tool.name for tool in projected.tools}
    assert "COMPLETE SKILL METHOD FOR PLANNING" in projected.context


def test_explicit_constraints_use_native_create_parameters(installed_promo):
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.editor_create import CreateVideoArgs
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.skills.resolution import get_builtin_skill_option

    skill = get_builtin_skill_option("promo-video").reference
    tools = tools_for_bound_skill(intent_router.tools, skill)
    snapshot = ContextSnapshot("prepared", frozenset({"snapshot:source:digest"}))
    projected = _video_round(tools, snapshot=snapshot, skill=skill, user_text="做 3 幕，总时长 24 秒，画幅 9:16，背景 #A1b2C3")
    create = next(tool for tool in projected.tools if tool.name == "create_video")
    properties = tool_spec(create)["function"]["parameters"]["properties"]
    assert {"shots", "aspect", "background"} <= set(properties)
    assert not {"scene_count", "target_seconds", "design_video"} & set(properties)
    args = CreateVideoArgs.model_validate({
        "name": "Constraint check", "aspect": "9:16", "background": "#A1B2C3",
        "shots": [{"headline": "One", "duration_seconds": 8}, {"headline": "Two", "duration_seconds": 8}, {"headline": "Three", "duration_seconds": 8}],
    })
    assert args.aspect == "9:16" and args.background == "#A1B2C3"
    assert sum(shot.duration_seconds for shot in args.shots) == 24


def test_concurrent_head_keeps_confirmed_actions_but_expires_old_targets_and_preview():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    saved = _composition_resource()
    receipt = {"tool": "move_clip", "version": 2, "arguments": {"clip_id": "moved", "time": 3}}
    round = assemble_video_round({
        "tools": intent_router.tools, "user_text": "Move the clip", "mode": "plan",
        "snapshot": ContextSnapshot("head", resources=(("work", saved),)),
        "recent_edit": {"composition_id": saved["composition_id"], "version_id": "old",
                        "clips": {"moved": {"start_seconds": 3}}, "applied": [receipt]},
        "last_preview": {"version_id": "old", "window_seconds": {"start": 3, "end": 4}},
    })
    facts = json.loads(round.context)
    assert facts["already_saved_this_turn"] == [receipt]
    assert facts["selected"] == saved["base_ref"]
    assert "recently_edited_clips" not in facts and "observed_preview" not in facts


def test_revised_playback_request_keeps_prior_export_as_history():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    work = _composition_resource()
    previous = {"composition_id": work["composition_id"], "output_id": "previous"}
    result = assemble_video_round({
        "tools": intent_router.tools, "user_text": "调整构图，然后播放这一段给我看。",
        "snapshot": ContextSnapshot("head", resources=(("work", work),)),
        "preceding_delivery": previous,
        "recent_edit": {"composition_id": work["composition_id"], "version_id": work["version_id"],
                        "clips": {"title": {"start_seconds": 2, "end_seconds": 4},
                                  "long": {"start_seconds": 0, "end_seconds": 20}}, "applied": [{"tool": "set_keyframe", "version": 2}]},
    })
    context = json.loads(result.context)
    short, long = context["recently_edited_clips"]
    assert short["preview_range"] == {"start_seconds": 2, "end_seconds": 4}
    assert "preview_range" not in long
    assert context["preceding_reviewed_delivery"] == previous
    assert "revised_delivery" not in context
    assert "does not explicitly request formal export" in context["delivery_scope"]


def test_export_opening_reviews_its_own_output_after_another_edit():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    work = _composition_resource()
    exported = {**work["base_ref"], "composition_version_id": "earlier-version", "status": "available",
                "output_id": "the-export", "content_digest": "e" * 64}
    result = assemble_video_round({
        "tools": intent_router.tools, "user_text": "Review and deliver the exported version",
        "snapshot": ContextSnapshot("head", resources=(("work", work),)), "exported": exported,
    })
    facts = json.loads(result.context)
    assert facts["selected"] == work["base_ref"]
    assert facts["exported_this_opening"] == exported
    assert {tool.name for tool in result.tools} == {"review_video", "deliver_video", "answer"}

    # A completed export can resume with the original edit request even when
    # no other opening advanced the head. The edit is already in the MP4.
    exported = {**work["base_ref"], "role": "export", "status": "available", "output_id": "the-export"}
    recovery_facts = {
        "tools": intent_router.tools, "user_text": "Extend the closing still by one second and export",
        "snapshot": ContextSnapshot("head", resources=(("work", work),)), "exported": exported,
        "authorized_media": exported,
        "recent_edit": {"composition_id": work["composition_id"], "version_id": work["version_id"],
                        "clips": {}, "applied": [{"tool": "extend_still", "version": 14}]},
    }
    resumed = assemble_video_round(recovery_facts)
    names = {tool.name for tool in resumed.tools}
    assert "review_video" in names and not {"extend_still", "export_video"} & names
    assert json.loads(resumed.context)["already_saved_this_turn"] == [{"tool": "extend_still", "version": 14}]
    reviewed = assemble_video_round({**recovery_facts, "reviewed_output_id": exported["output_id"]})
    assert {tool.name for tool in reviewed.tools} == {"answer", "deliver_video", "review_video"}


def test_create_rejection_stops_repeated_or_unproductive_attempts():
    from app.agents.tool_loop import ToolRejected
    from app.chat.turn_tools import video_rejection_stop

    first = ToolRejected(kind="params_validation", tool_name="create_video", iteration=0, detail="bad shot", duration_ms=0)
    same = ToolRejected(kind="params_validation", tool_name="create_video", iteration=1, detail="bad shot", duration_ms=0)
    assert video_rejection_stop(first, ()) is False
    assert video_rejection_stop(same, (first,)) is True
    other = ToolRejected(kind="execute_guardrail", tool_name="create_video", iteration=1, detail="other", duration_ms=0)
    third = ToolRejected(kind="execute_guardrail", tool_name="create_video", iteration=2, detail="third", duration_ms=0)
    assert video_rejection_stop(other, (first,)) is False
    assert video_rejection_stop(third, (first, other)) is True
    assert video_rejection_stop(ToolRejected(kind="execute_guardrail", tool_name="split_clip", iteration=0, detail="bad", duration_ms=0), (first, other)) is False
    preview = ToolRejected(kind="execute_guardrail", tool_name="preview_range", iteration=0, detail="generator_preview_failed: registerRoot missing", duration_ms=0)
    assert video_rejection_stop(preview, ()) is False
    assert video_rejection_stop(preview, (preview,)) is False
    assert video_rejection_stop(preview, (preview, preview)) is False
    assert video_rejection_stop(preview, (preview, preview, preview)) is True
    pending = ToolRejected(kind="execute_guardrail", tool_name="preview_range", iteration=0,
                           detail="pending_media", duration_ms=0, candidate_digest="same-window")
    animated = ToolRejected(kind="execute_guardrail", tool_name="translate", iteration=1,
                            detail="Keyframes control this property. Its static transform cannot make this edit.",
                            duration_ms=0, candidate_digest="same-transform")
    changed = ToolRejected(kind="execute_guardrail", tool_name="preview_range", iteration=2,
                           detail="pending_media", duration_ms=0, candidate_digest="another-window")
    # Write tools still stop on 2nd identical failure; read-only preview_range allows up to 3 identical retries (stops on 4th) or 6 total.
    assert video_rejection_stop(pending, (pending, animated)) is False
    assert video_rejection_stop(pending, (pending, pending, pending, animated)) is True
    assert video_rejection_stop(animated, (pending, animated, changed)) is True
    assert video_rejection_stop(changed, (pending, animated)) is False
    assert video_rejection_stop(changed, (pending, changed, changed, changed, pending)) is True


def test_saved_version_offers_materials_and_blocking_clarification():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    resource = _composition_resource()
    snapshot = ContextSnapshot("saved", resources=(("work", resource),))
    assembly = _video_round(intent_router.tools, snapshot=snapshot, version_saved=True)
    names = {tool.name for tool in assembly.tools}
    assert "create_video" not in names
    assert {"ask_user", "prepare_video_materials", "insert_visual"} <= names
    assert "translate" in names


def test_completed_delivery_does_not_reopen_optional_questionnaire():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    resource = _composition_resource()
    assembly = assemble_video_round({
        "tools": intent_router.tools,
        "snapshot": ContextSnapshot("saved", resources=(("work", resource),)),
        "user_text": "把刚才已审阅的 MP4 交付给我，不要再导出。",
        "delivered": {"composition_version_id": resource["version_id"], "delivered_to_chat": True},
    })
    assert "ask_user" not in {tool.name for tool in assembly.tools}


@pytest.mark.asyncio
async def test_observed_version_wire_allows_clarification_without_recreating_work():
    from copy import copy
    from types import SimpleNamespace
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round
    from app.providers.llm.base import ToolCall, ToolGeneration

    resource = _composition_resource()
    snapshot = ContextSnapshot("saved", resources=(("work", resource),))

    class Client:
        capabilities = SimpleNamespace(supports_native_tools=True)

        def __init__(self):
            self.wires = []

        async def generate_with_tools(self, **kwargs):
            self.wires.append(kwargs["tools"])
            return ToolGeneration(content="Done", tool_calls=[
                ToolCall(id="finish", name="answer", arguments={"pending_disposition": "none"}),
            ])

    client = Client()
    agent = copy(intent_router)
    agent.client = client

    def assemble(**facts):
        return assemble_video_round({**facts, "snapshot": snapshot, "user_text": "预览当前版本 0–3 秒，不要正式导出。",
                                    "last_preview": {"version_id": resource["version_id"]}})

    async def execute(_name, _params, _speech):
        return None

    result = await agent.call_loop(execute, round_assembler=assemble,
                                  message="预览当前版本 0–3 秒，不要正式导出。")
    assert result.calls == ["answer"]
    assert len(client.wires) == 1
    names = {tool["function"]["name"] for tool in client.wires[0]}
    assert "ask_user" in names and "create_video" not in names


@pytest.mark.asyncio
async def test_failed_observations_stop_across_equivalent_arguments_and_other_reads():
    from copy import copy
    from types import SimpleNamespace
    from app.agents.tool_loop import ChatTool
    from app.chat.intent import intent_router
    from app.chat.turn_tools import video_rejection_stop
    from app.models.schemas import VideoRangeScrubTarget
    from app.providers.llm.base import ToolCall, ToolGeneration

    calls = [
        ToolCall(id="first", name="preview_range", arguments={"start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="other", name="other_read", arguments={"start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="second", name="preview_range", arguments={"kind": "range", "start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="third", name="preview_range", arguments={"start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="fourth", name="preview_range", arguments={"kind": "range", "start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="unexpected", name="other_read", arguments={"start_seconds": 0, "end_seconds": 2}),
    ]

    class Client:
        capabilities = SimpleNamespace(supports_native_tools=True)

        def __init__(self):
            self.requests = 0

        async def generate_with_tools(self, **_kwargs):
            result = ToolGeneration(content="", tool_calls=[calls[self.requests]])
            self.requests += 1
            return result

    agent = copy(intent_router)
    agent.client = Client()
    agent.tools = [
        ChatTool(name="preview_range", description="Preview", params_model=VideoRangeScrubTarget, terminal=False),
        ChatTool(name="other_read", description="Read", params_model=VideoRangeScrubTarget, terminal=False),
    ]
    agent.max_iterations = 8

    async def execute(name, _params, _speech):
        from app.agents.tool_loop import ToolObservation

        return ToolObservation("pending_media" if name == "preview_range" else "{}", ok=name != "preview_range")

    result = await agent.call_loop(execute, should_stop_rejection=video_rejection_stop,
                                  message="Preview the saved work")
    assert result.no_progress_tool == "preview_range"
    assert result.iterations == 5
    assert agent.client.requests == 5
    assert [event.tool_name for event in result.rejections] == ["preview_range"] * 4


@pytest.mark.asyncio
async def test_multistep_video_edit_emits_sanitized_interim_prose_without_raw_clip_ids():
    from copy import copy
    from types import SimpleNamespace
    from app.agents.tool_loop import ContextSnapshot, ToolObservation
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round
    from app.providers.llm.base import ToolCall, ToolGeneration

    work = _composition_resource()
    snapshot = ContextSnapshot("saved", resources=(("work", work),))
    editor_labels = {"clp_intro_01": ("0–4 秒的片段", "the 0–4 s clip")}
    responses = [
        ToolGeneration(
            content="先检查 clp_intro_01 的参数，再同步调整动效和音效。",
            tool_calls=[ToolCall(id="c1", name="inspect_clip", arguments={"clip_id": "clp_intro_01"})],
        ),
        ToolGeneration(
            content="已完成 clp_intro_01 的检查并更新。",
            tool_calls=[ToolCall(id="c2", name="answer", arguments={"pending_disposition": "none"})],
        ),
    ]

    class StreamClient:
        capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=True)

        def __init__(self):
            self.index = 0
            self.on_delta_seen: list[bool] = []

        async def generate_stream_with_tools(self, **kwargs):
            gen = responses[self.index]
            self.index += 1
            self.on_delta_seen.append(kwargs.get("on_delta") is not None)
            if kwargs.get("on_delta") is not None and gen.content:
                kwargs["on_delta"](gen.content)
            return gen

        async def generate_with_tools(self, **kwargs):
            return await self.generate_stream_with_tools(**kwargs)

    agent = copy(intent_router)
    agent.client = StreamClient()
    deltas: list[str] = []
    interim: list[str] = []
    executed: list[str] = []

    def assemble(**facts):
        return assemble_video_round({
            **facts,
            "snapshot": snapshot,
            "user_text": "把开场片段的动效调流畅一点",
            "editor_labels": editor_labels,
        })

    async def execute(name, _params, _speech):
        executed.append(name)
        return ToolObservation('{"clip_id": "clp_intro_01"}') if name != "answer" else None

    result = await agent.call_loop(
        execute,
        round_assembler=assemble,
        message="把开场片段的动效调流畅一点",
        on_delta=deltas.append,
        on_interim_prose=interim.append,
    )
    # on_delta stays disabled while editor_labels is non-empty so raw clip_ids never leak mid-stream
    assert deltas == []
    # Sanitized interim prose emits before non-terminal tool execution with clip_id projected cleanly
    assert interim == ["先检查 0–4 秒的片段 的参数，再同步调整动效和音效。"]
    assert all("clp_intro_01" not in note for note in interim)
    assert executed == ["inspect_clip", "answer"]
    assert "0–4 秒的片段" in result.prose and "clp_intro_01" not in result.prose


# --- Speech language & mixed-batch ToolLoop contracts ---

from copy import deepcopy


from uuid import uuid4


import pytest


from app.agents.tool_loop import ContextSnapshot, ToolObservation


from app.chat.intent import intent_router


from app.chat.readiness import brief_with_user_constraints


from app.chat.speech_language import conversation_speech_language


from app.models.schemas import (
    BrandColor,
    BrandSourceRef,
    BrandTagline,
    BrandTypography,
    CreativeState,
    MediaInput,
    MediaInputType,
    seal_creative_state,
)


from app.models.tables import Message, SourceSnapshot


from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration


from app.tools.video.brand import build_brand_profile


from app.tools.video.brand_agent import BrandProfileExtraction, brand_profile_agent


from test.support.media_helpers import WEBSITE_URL as URL, website_asset as asset, website_snapshot as snapshot





def wire_copy(value):
    if isinstance(value, str):
        return str(value)
    if isinstance(value, list):
        return [wire_copy(item) for item in value]
    if isinstance(value, dict):
        return {key: wire_copy(item) for key, item in value.items()}
    return deepcopy(value)


class FakeToolProvider:
    capabilities = ProviderCapabilities(supports_native_tools=True)

    def __init__(self, calls, *, content="我来处理这一步。"):
        self.calls_to_make = list(calls)
        self.content = content
        self.wires = []

    async def generate_with_tools(self, *, messages, tools, **kwargs):
        self.wires.append({"messages": wire_copy(messages), "tools": wire_copy(tools)})
        batch = self.calls_to_make.pop(0)
        calls = batch if isinstance(batch, list) else [batch]
        return ToolGeneration(
            content=self.content,
            tool_calls=[ToolCall(id=f"call-{len(self.wires)}-{index}", name=name, arguments=arguments)
                        for index, (name, arguments) in enumerate(calls)],
        )

    async def generate_stream_with_tools(self, **kwargs):
        return await self.generate_with_tools(**kwargs)


def tool_names(wire):
    return {item["function"]["name"] for item in wire["tools"]}


def png():
    return MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/png",
        data_url="data:image/png;base64,iVBORw0KGgo=",
    )


def source_row(owner_id):
    return SourceSnapshot(
        id=uuid4(),
        owner_id=owner_id,
        kind="web",
        digest="a" * 64,
        storage_key="sources/page.json",
        meta={
            "canonical_url": URL,
            "lines": [
                {"line_id": "line_0000", "text": "Citations should be as universal as hashtags."}
            ],
            "views": snapshot()["views"],
        },
    )


class BrandFakeClient:
    def __init__(self):
        self.messages = None

    async def generate(self, *, messages, response_model, **kwargs):
        self.messages = wire_copy(messages)
        return BrandProfileExtraction(
            positioning="Universal citation infrastructure",
            taglines=[
                BrandTagline(
                    text="Citations should be as universal as hashtags.", line_ids=["line_0000"]
                )
            ],
            colors=[BrandColor(value="#DC0000", source="visual", confidence="inferred")],
            typography=[BrandTypography(candidate="Inter", source="visual", confidence="inferred")],
        )


async def test_url_and_suggestion_preserve_speech_language_until_user_writes_in_english():
    source_turn = uuid4()
    rows = [
        Message(role="user", content=f"给 {URL} 做一只宣传片"),
        Message(id=source_turn, role="assistant", content="Which voiceover would you like?"),
        Message(role="user", content="Use the English voiceover for this film.",
                suggestion_ref={"source_turn": str(source_turn), "suggestion_id": "en"}),
        Message(role="user", content=URL),
    ]
    chinese = conversation_speech_language(rows)
    assert chinese and chinese.split("-")[0] == "zh"
    rows.append(Message(role="user", content="Please walk me through your plan for the film."))
    english = conversation_speech_language(rows)
    assert english and english.split("-")[0] == "en"


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_stage_speech_precedes_activity_and_silent_calls_can_continue(monkeypatch, streaming):
    from app.agents.tool_loop import ChatTool, ToolObservation

    class Provider(FakeToolProvider):
        async def generate_with_tools(self, **kwargs):
            self.wires.append(wire_copy(kwargs["messages"]))
            return self.calls_to_make.pop(0)

    def call(n, name):
        return ToolCall(id=f"call-{n}", name=name, arguments={})

    original = {
        "role": "assistant", "reasoning_content": "test-only protocol marker",
        "tool_calls": [{"id": "call-c", "type": "function",
                        "function": {"name": "analyze_brand", "arguments": "{  }"}}],
    }
    requests = [
        ToolGeneration("同时检查两项。", [call("a", "read"), call("b", "read")]),
        ToolGeneration("", [call("c", "analyze_brand")], assistant_message=original),
        ToolGeneration("", [call("again", "analyze_brand")]),
        *(ToolGeneration(f"查看素材 {i}。", [call(i, "read")]) for i in range(6)),
        ToolGeneration("已完成。", [call("end", "answer")]),
    ]
    provider = Provider(requests)
    monkeypatch.setattr(intent_router, "client", provider)
    events = []

    async def execute(name, params, speech):
        events.append(name)
        return ToolObservation("observed") if name != "answer" else None

    result = await intent_router.call_loop(
        execute, tools=[
            ChatTool(name="analyze_brand", description="Read the brand", params_model=None, terminal=False),
            ChatTool(name="read", description="Read", params_model=None, terminal=False, batchable=True),
            ChatTool(name="answer", description="Reply", params_model=None),
        ],
        message="给 https://www.legitevi.com/en 做一只宣传片",
        speech_language_hint="zh",
        on_interim_prose=events.append,
        on_delta=(lambda _: None) if streaming else None,
    )
    assert original in provider.wires[2]
    assert events[:5] == ["同时检查两项。", "read", "read", "analyze_brand", "analyze_brand"]
    assert events[5:] == [entry for i in range(6) for entry in (f"查看素材 {i}。", "read")] + ["answer"]
    assert result.prose == "已完成。"


async def test_language_of_the_current_edit_overrides_an_older_english_turn():
    from types import SimpleNamespace

    rows = [SimpleNamespace(role="user", content=s) for s in (
        "Inspect the saved timeline and describe both clips.",
        "请裁剪已核对的第二段 elm_b，保留片段局部 0.3 到 7.6 秒，保存后告诉我新时长。",
    )]
    assert conversation_speech_language(rows) == "zh"
    rows[-1].content = "请查看项目素材列表，告诉我有几个素材。只读取，不需要生成。"
    assert conversation_speech_language(rows) == "zh"
    rows[-1].content = "Please inspect the clip named 开场采访 and tell me its duration."
    assert conversation_speech_language(rows) == "en"


async def test_mixed_terminal_and_invalid_member_keep_the_valid_sibling(monkeypatch):
    from app.agents.tool_loop import ChatTool
    from app.chat.editor import ClipArgs

    provider = FakeToolProvider([
        [("answer", {}), ("inspect_clip", {}), ("inspect_clip", {"clip_id": "known"})],
        ("answer", {}),
    ])
    monkeypatch.setattr(intent_router, "client", provider)
    accepted = []

    async def execute(name, params, speech):
        accepted.append(name)
        return ToolObservation("found known") if params is not None else None

    await intent_router.call_loop(
        execute,
        tools=[ChatTool("answer", "Reply", None),
               ChatTool("inspect_clip", "Read one clip", ClipArgs, terminal=False, batchable=True)],
        message="Inspect the clip",
    )
    assert accepted == ["inspect_clip", "answer"]
    replies = [m for m in provider.wires[1]["messages"] if m["role"] == "tool"]
    assert [r["tool_call_id"] for r in replies] == ["call-1-0", "call-1-1", "call-1-2"]
    assert "Not executed" in replies[0]["content"]
    assert "params_validation" in replies[1]["content"]
    assert replies[2]["content"] == "found known"

