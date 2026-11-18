import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.tool_loop import ChatTool, ToolObservation
from app.chat.media_journey import (
    allowed_media_tools,
    continue_media_journey,
    initial_media_journey,
    media_actions,
)
from app.chat.plan_turn import PlanTurn
from app.models.schemas import ChatRequest, WorkflowStatus
from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration
from app.tools.video.media_analysis import IMAGE_REVIEWER_VERSION
from app.tools.video.visual_assets import SceneAssetSpec


def draft_with_scene():
    spec = SceneAssetSpec(
        scene_id="intro",
        intent="Opening with source evidence",
        source={"kind": "minimax_image", "prompt": "A paper and symbol of verified evidence"},
    )
    return {
        "content": {"scenes": [{"scene_id": "intro"}]},
        "design": {"scene_assets": [spec.model_dump(mode="json")]},
    }, spec


def result_for(spec, status, **extra):
    return {
        "scene_id": spec.scene_id,
        "request_digest": spec.request_digest(),
        "content_review": {"status": status, "reviewer_version": IMAGE_REVIEWER_VERSION},
        **extra,
    }


def test_staged_media_preserves_original_intent_and_enforces_current_images():
    opening = SimpleNamespace(
        id=uuid4(), role="user", content="给 https://www.legitevi.com/en 做一只宣传片",
    )
    assert initial_media_journey(opening) == {"opening_id": str(opening.id)}
    opening.content = "分析 https://www.legitevi.com/en 的宣传片"
    assert initial_media_journey(opening) is None
    draft, spec = draft_with_scene()
    assert "prepare_narration" not in allowed_media_tools(media_actions(
        draft, []
    )["phase"])
    review = result_for(spec, "unavailable")
    assert media_actions(draft, [review])["review_retry_scene_ids"] == ["intro"]
    assert media_actions(
        draft, [review, {**review, "review_retry_of": {"digest": "r"}}]
    )["phase"] == "images_blocked"
    passed = result_for(spec, "pass")
    assert media_actions(draft, [passed])["phase"] == "audio"
    changed = spec.model_copy(update={"intent": "New scene intent"})
    draft["design"]["scene_assets"] = [changed.model_dump(mode="json")]
    assert media_actions(draft, [passed])["phase"] == "images"


@pytest.mark.asyncio
async def test_rejected_verified_plan_can_retry_without_searching_or_saving(monkeypatch):
    project = SimpleNamespace(id=uuid4(), language="zh")
    run = SimpleNamespace(context={})
    run_id = uuid4()
    calls = []
    db = SimpleNamespace()

    async def get(cls, key):
        assert key == run_id
        return run

    db.get = get
    turn = PlanTurn(
        db, uuid4(), SimpleNamespace(id=uuid4()), project,
        ChatRequest(project_id=project.id, message="English · 16:9"),
    )
    turn.media_state = {"phase": "images"}
    turn.media_journey = {"opening_id": str(uuid4())}
    exact_params = {
        "draft_ref": {"draft_id": "draft", "draft_digest": "a" * 64},
        "scene_ids": ["intro"],
        "review_existing": False,
    }

    async def dispatch(name, params, prose):
        assert name == "prepare_visual_assets"
        return ToolObservation(json.dumps({
            "cache": "miss",
            "plan_task": {"tool": name, "params": exact_params},
        }))

    async def present(params, prose):
        calls.append((params, prose))
        if len(calls) == 1:
            return "The saved draft changed before quotation."
        turn.outcome = (None, run_id, None, [])
        return None

    monkeypatch.setattr(turn, "_dispatch", dispatch)
    monkeypatch.setattr(turn, "_present_plan", present)
    first = await turn.execute("prepare_visual_assets", None, "")
    assert not first.ok and not first.stop_after_observation
    assert "changed before quotation" in first.text
    assert isinstance(await turn.execute("search_music", None, ""), str)
    assert isinstance(await turn.execute("design_video", SimpleNamespace(save=True), ""), str)
    accepted = await turn.execute("prepare_visual_assets", None, "")
    assert accepted.ok and accepted.stop_after_observation
    assert run.context["media_journey"] == turn.media_journey
    assert all(
        params.production_intent is True and params.tasks[0].params == exact_params and prose
        for params, prose in calls
    )


@pytest.mark.asyncio
async def test_settled_read_handoff_ends_the_loop_without_an_extra_model_call(monkeypatch):
    class Provider:
        capabilities = ProviderCapabilities(supports_native_tools=True)
        calls = 0

        async def generate_with_tools(self, **kwargs):
            self.calls += 1
            return ToolGeneration(
                content="I’ll prepare the image.",
                tool_calls=[ToolCall(id="read", name="prepare_image", arguments={})],
            )

    provider = Provider()
    from app.chat.intent import intent_router

    monkeypatch.setattr(intent_router, "client", provider)
    tools = [ChatTool(
        name="prepare_image", description="Prepare", params_model=None, terminal=False,
    )]

    async def dispatch(name, params, prose):
        return ToolObservation("authorized preparation docked", stop_after_observation=True)

    outcome = await intent_router.call_loop(dispatch, tools=tools, message="prepare")
    assert outcome.tool_name == "prepare_image"
    assert provider.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [True, False])
async def test_visual_settlement_continues_at_most_once_in_original_chat(monkeypatch, blocked):
    from app.chat import media_journey, plan_turn, service
    from app.models.schemas import PendingPlan
    from app.models.tables import Message, WorkflowRun

    draft, spec = draft_with_scene()
    conversation = SimpleNamespace(
        id=uuid4(), context={"schema_version": 1, "items": [{
            "candidate": {"target_tool": "design_video", "active": True, "candidate_id": "draft"},
            "executed_arguments": draft,
        }]},
    )
    opening = SimpleNamespace(
        id=uuid4(), conversation_id=conversation.id, turn_state="settled", intent={}, seq=1,
        content="给 https://www.legitevi.com/en 做一只宣传片",
    )
    run = SimpleNamespace(
        id=uuid4(), status=WorkflowStatus.COMPLETED,
        context={
            "media_journey": {"opening_id": str(opening.id)},
            "visual_asset_preparation": {"request": {"draft_ref": {"draft_id": "draft"}}},
            "creative_state": {},
        },
    )
    project = SimpleNamespace(id=uuid4(), user_id=uuid4())
    commits, resumed = [], []

    async def get(cls, key, **kwargs):
        assert key == (run.id if cls is WorkflowRun else opening.id)
        assert cls in {WorkflowRun, Message}
        return run if cls is WorkflowRun else opening

    async def absent(*args):
        return None

    async def results(*args):
        if blocked:
            return [result_for(spec, "unavailable", review_retry_of={"digest": "retry"})]
        return [{
            "scene_id": spec.scene_id, "request_digest": spec.request_digest(),
            "code": "execution_error", "detail": "Render interrupted",
        }]

    async def resume(db, user_id, conversation, project, request, **kwargs):
        assert kwargs["turn_id"] == opening.id
        assert isinstance(kwargs["media_resume_pending"], PendingPlan)
        assert kwargs["media_resume_pending"].prompt == opening.content
        resumed.append(True)
        return None, None, None, []

    async def commit():
        commits.append(True)

    monkeypatch.setattr(service, "latest_pending_question", absent)
    monkeypatch.setattr(service, "list_conversation_messages", absent)
    monkeypatch.setattr(service, "fold_conversation_usage", lambda *a, **k: absent())
    monkeypatch.setattr(plan_turn, "run_plan_turn", resume)
    monkeypatch.setattr(media_journey, "visual_results", results)
    db = SimpleNamespace(get=get, refresh=absent, scalar=absent, commit=commit)
    await continue_media_journey(db, project, conversation, run)
    await continue_media_journey(db, project, conversation, run)
    assert run.context["media_continuation_finished"] is True
    assert commits == [True]
    assert resumed == ([] if blocked else [True])


@pytest.mark.asyncio
async def test_audio_preparation_blocks_music_before_timing_and_blocks_formal_work(monkeypatch):
    from app.chat.media_journey import dock_media_observation, media_write_rejection

    turn = SimpleNamespace(media_state={"phase": "audio", "audio_timing_ready": False})
    candidate = ToolObservation(json.dumps({
        "cache": "miss",
        "plan_task": {"tool": "prepare_music", "params": {}},
    }))

    async def no_start(*args):
        pytest.fail("Music cannot start before actual narration timing is ready")

    monkeypatch.setattr(turn, "_present_plan", no_start, raising=False)
    held = await dock_media_observation(turn, "prepare_music", candidate)
    assert not held.ok and "READY" in held.text
    assert media_write_rejection("audio", "design_video", SimpleNamespace(save=True))
    assert media_write_rejection("audio", "review_working_draft", None)
    assert media_write_rejection("audio", "produce_video", None)
