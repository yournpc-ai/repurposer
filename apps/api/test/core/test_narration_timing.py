from app.chat import service
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.editing.schemas import speech_text_digest
from app.editing.timing import SOURCE_TIMEBASE as TPS
from app.models.tables import Message
from app.tools.video.design import CompositionDesignVideoArgs, _design_composition_locked
from app.tools.video.narration_draft import NarrationDraftError, assert_narration_ready_for_score


def spoken_draft(ids):
    scenes, clips = [], []
    for index, scene_id in enumerate(ids):
        timing = {"start": index * 5 * TPS, "end": (index + 1) * 5 * TPS}
        scenes.append({"scene_id": scene_id, "range": timing, "speech_clip_ids": [f"speech_{scene_id}"]})
        clips.append({
            "clip_id": f"speech_{scene_id}", "scene_id": scene_id, "range": timing,
            "object": {"kind": "speech", "object_id": f"voice_{scene_id}", "text": scene_id,
                       "voice_id": "English", "language": "en"},
        })
    return {
        "content": {
            "settings": {"width": 1920, "height": 1080, "fps": {"num": 24, "den": 1}, "timebase": TPS},
            "scenes": scenes, "timeline": {"tracks": [
                {"track_id": "dialogue", "kind": "audio", "role": "dialogue", "order": 0, "clips": clips},
            ]},
        },
        "design": {"authoring": "high_level_scene"},
    }


@pytest.mark.asyncio
async def test_retiming_first_ready_scene_reprojects_all_following_cues_in_the_working_draft(monkeypatch):
    draft = spoken_draft(["a", "b", "c"])
    owner_id, project_id = uuid4(), uuid4()
    facts = []
    for scene in draft["content"]["scenes"]:
        start = scene["range"]["start"]
        facts.append({
            "scene_id": scene["scene_id"], "text_digest": speech_text_digest(scene["scene_id"]),
            "alignment": {"alignment_id": str(uuid4()), "status": "READY"},
            "snapshot": {"snapshot_id": str(uuid4()), "digest": "a" * 64},
            "source_duration_ticks": 2 * TPS, "source_timebase": TPS,
            "scene_range": dict(scene["range"]), "cues": [{
                "source_range": {"start": TPS, "end": 2 * TPS},
                "output_range": {"start": start + TPS, "end": start + 2 * TPS},
            }],
        })
    draft["design"]["narrations"] = facts
    alignment = SimpleNamespace(id=uuid4(), status="READY", content_digest="f" * 64,
                                text_digest=speech_text_digest("a"))
    audio = SimpleNamespace(id=uuid4(), origin_project_id=project_id, digest="a" * 64,
                            meta={"analysis_ref": {"digest": "f" * 64}})
    payload = SimpleNamespace(duration_ticks=2 * TPS, source_timebase=TPS, sentences=[
        SimpleNamespace(sentence_id="s1", text="a", text_start=0, text_end=1, start_tick=TPS, end_tick=2 * TPS),
    ])
    monkeypatch.setattr("app.tools.video.alignment_store.ready_alignment",
                        AsyncMock(return_value=(alignment, audio, payload)))
    monkeypatch.setattr("app.tools.video.media_analysis.read_report", AsyncMock(return_value={
        "media_kind": "audio", "analysis_scope": "full", "source_ref": {"digest": audio.digest},
        "media_facts": {"decode": {"fully_decoded": True}},
    }))
    args = CompositionDesignVideoArgs.model_validate({
        "narration_update": {"scene_id": "a", "target_duration_seconds": 7, "alignment_id": str(alignment.id)},
        "draft_ref": {"draft_id": "d", "draft_digest": "a" * 64},
    })
    args.bind_working_draft(draft)
    updated = await _design_composition_locked(
        None, owner_id=owner_id, project_id=project_id, args=args, request_id=None,
        skill=None, builtin_skill=None, skill_package=None,
    )
    output = updated.arguments
    projected = {f["scene_id"]: f for f in output["design"]["narrations"]}
    for index, source in enumerate(facts[1:], start=1):
        fact = projected[source["scene_id"]]
        assert fact["snapshot"] == source["snapshot"] and fact["alignment"] == source["alignment"]
        assert fact["cues"][0]["source_range"] == source["cues"][0]["source_range"]
        assert fact["cues"][0]["output_range"] == {
            "start": (5 * index + 3) * TPS, "end": (5 * index + 4) * TPS,
        }
        assert fact["scene_range"] == output["content"]["scenes"][index]["range"]
    assert_narration_ready_for_score(output)
    stale = deepcopy(output)
    stale["design"]["narrations"][0]["cues"][0]["output_range"] = {"start": 0, "end": TPS}
    with pytest.raises(NarrationDraftError, match="stale narration timing"):
        assert_narration_ready_for_score(stale)

@pytest.mark.asyncio
async def test_batch_start_pins_every_scene_in_one_ordered_run_and_one_hold(database, monkeypatch):
    from sqlalchemy import select

    from app.models.schemas import InferredIntent, TaskItem
    from app.models.tables import Conversation, CreditTransaction, Project, User, WorkflowStep
    from app.pipeline import step_display
    from app.pipeline.orchestrator import TaskSpec, create_run, derive_task_estimates
    from app.pipeline.outputs import workflow_step_to_response
    from app.tools.video.production.node import PrepareNarration
    from app.tools import ToolRejected, validate_task_list
    from app.tools.video.narration_draft import scene_narration_request

    ids = ["intro", "proof", "close"]
    draft = spoken_draft(ids)
    ref = {"draft_id": "storyboard", "draft_digest": "c" * 64}
    tasks = [TaskItem(tool="prepare_narration", params={
        **scene_narration_request(draft, scene), "draft_ref": ref, "scene_id": scene,
    }) for scene in ids]
    with pytest.raises(ToolRejected):
        validate_task_list([tasks[0], tasks[0]])
    different = tasks[1].model_copy(update={"params": {**tasks[1].params, "draft_ref": {**ref, "draft_digest": "a" * 64}}})
    with pytest.raises(ToolRejected):
        validate_task_list([tasks[0], different])
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.video.narration_store.peek_original", AsyncMock(return_value=None))
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Storyboard")
        db.add(project)
        await db.flush()
        db.add(Conversation(project_id=project.id, user_id=user.id, context={"schema_version": 1, "items": [
            {"executed_arguments": draft, "candidate": {
                "active": True, "target_tool": "design_video", "candidate_id": ref["draft_id"],
                "candidate_digest": ref["draft_digest"],
            }},
        ]}))
        await db.commit()
        quote = await derive_task_estimates(db, project, tasks)
        assert quote.total[1] > 0
        await service.sync_plan_question(db, user.id, project, InferredIntent(action="draft", tasks=tasks),
                                         "准备旁白", estimate=quote)
        pending = await db.scalar(select(Message).where(Message.role == "assistant"))
        assert pending.question["estimate_credits"]["total"] == list(quote.total)
        assert not pending.blocks
        run = await create_run(db, project, TaskSpec(tasks=tasks))
        nodes = list(await db.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.seq)))
        assert [p["request"]["scene_id"] for p in run.context["narration_preparation"]["scenes"]] == ids
        assert [node.spec["scene_index"] for node in nodes] == [1, 2, 3]
        assert [node.inputs for node in nodes] == [[], [str(nodes[0].id)], [str(nodes[1].id)]]
        assert [node.spec["narration_policy"]["max_tts_characters"] for node in nodes] == [len(s) for s in ids]
        holds = list(await db.scalars(select(CreditTransaction).where(
            CreditTransaction.kind == "hold", CreditTransaction.idempotency_key == f"run:{run.id}:hold",
        )))
        assert len(holds) == 1 and holds[0].amount == -quote.total[1]
        await db.commit()

        # Run each real worker adapter against the persisted steps with local speech fixtures.
        async def synth(content, *, user_id, execution_id, policy, on_reuse):
            speech = content.timeline.tracks[0].clips[0].object
            assert execution_id == str(nodes[ids.index(speech.text)].id)
            on_reuse(False)
            return {speech.object_id: {"original": {"cache_hit": False}, "usage": {"tts_chars": len(speech.text)}}}

        async def freeze(db, project, *, text, original, scene_id):
            return SimpleNamespace(id=uuid4()), SimpleNamespace(
                id=uuid4(), digest="a" * 64, duration_ticks=TPS * (ids.index(scene_id) + 1),
                meta={"analysis_ref": {"digest": "b" * 64}},
            )

        monkeypatch.setattr(step_display, "AsyncSessionLocal", database)
        monkeypatch.setattr("app.tools.video.narration.prepare_speech_media", synth)
        monkeypatch.setattr("app.tools.video.preparation.snapshot_narration_original", freeze)
        monkeypatch.setattr("app.tools.video.alignment_store.request_alignment", AsyncMock(
            side_effect=[{"alignment_id": str(uuid4()), "status": "ALIGNED"} for _ in ids],
        ))
        for index, node in enumerate(nodes):
            await db.refresh(run)
            await PrepareNarration().run(db, run, node, project)
            await db.commit()
            await db.refresh(node)
            step = workflow_step_to_response(node, ratio=1)
            assert step.scene_index == index + 1
            assert any(stage.kind == "speech_media" and stage.status == "completed" for stage in step.production_stages)
        await db.refresh(run)
        results = [part["result"] for part in run.context["narration_preparation"]["scenes"]]
        assert [result["scene_id"] for result in results] == ids
        assert [result["duration_seconds"] for result in results] == [1, 2, 3]
