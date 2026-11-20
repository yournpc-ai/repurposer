"""Direct website score submission uses a durable turn identity across connections."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.agents.tool_loop import ToolObservation
from app.chat import media_journey, service
from app.editing.schemas import speech_text_digest
from app.editing.timing import SOURCE_TIMEBASE as ticks
from app.models.schemas import PendingPlan, TaskItem, WorkflowStatus
from app.models.tables import Conversation, CreditTransaction, Message, Project, User, WorkflowRun, WorkflowStep
from app.tools.video.narration_draft import reproject_narration_timing
from app.tools.video.music_preparation import PrepareMusicArgs
from app.chat.video_turn_seats import prepare_music_seat
from test.core.test_media_audio_continuation import spoken_draft


@pytest.mark.asyncio
async def test_direct_score_transactions(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    ids = ["intro", "end"]
    draft = spoken_draft(ids)
    draft["content"]["scenes"][-1]["range"]["end"] = 15 * ticks
    draft["design"].update(user_constraints={"target_seconds": 15}, narrations=[{
        "scene_id": sid, "text_digest": speech_text_digest(sid), "alignment": {"status": "READY"},
        "source_duration_ticks": ticks, "source_timebase": ticks,
        "cues": [{"source_range": {"start": 0, "end": ticks}}],
    } for sid in ids])
    reproject_narration_timing(draft)
    ref = {"draft_id": "score", "draft_digest": "a" * 64}
    task = TaskItem(tool="prepare_music", params={"name": "Study", "draft_ref": ref, "score": {
        "bpm": {"num": 96}, "sections": [{"scene_id": sid, "intent": "build"} for sid in ids],
        "instruments": [{"instrument_id": "lead", "kind": "pad"}], "seed": 42,
        "events": [{"scene_id": sid, "instrument_id": "lead", "start_beat": "0",
                    "duration_beats": "4", "midi": 60} for sid in ids],
    }})
    async with database() as db:
        owner = User(email=f"{uuid4()}@example.test")
        db.add(owner)
        await db.flush()
        project = Project(user_id=owner.id, title="Website")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=owner.id, project_id=project.id, context={
            "schema_version": 1, "items": [{"executed_arguments": draft, "candidate": {
                "candidate_id": "score", "candidate_digest": ref["draft_digest"], "target_tool": "design_video",
            }}]})
        db.add(conversation)
        await db.commit()
        opening = await service._create_message(db, conversation.id, "user", "Make a promo video for https://example.com")
        opening.turn_state = "settled"
        await db.commit()
    @service._scope_turn_row_lock_ownership
    async def submit(request, *, commit=True, origin=None, caller=None, hit=False):
        origin = origin or opening.id
        async with database() as db:
            turn = SimpleNamespace(db=db, project=await db.get(Project, project.id), user_id=caller or owner.id,
                                   turn_id=origin, conversation_id=conversation.id,
                                   media_journey={"opening_id": str(origin)}, settled_pending=None,
                                   media_state={"audio_timing_ready": True}, _current_pending=lambda: PendingPlan(),
                                   _present_plan=AsyncMock(side_effect=AssertionError("unexpected plan dock")))
            args = PrepareMusicArgs.model_validate(request.params)
            args.bind_working_draft(draft)
            with monkeypatch.context() as patch:
                patch.setattr("app.tools.video.music_preparation.cached_music_preparation",
                              AsyncMock(return_value={} if hit else None))
                obs = await prepare_music_seat(project=turn.project, args=args, managed=True)
            result = await media_journey.dock_media_observation(turn, "prepare_music", obs, music_args=args)
            if commit:
                await db.commit()
            return result, getattr(turn, "outcome", None)
    async with database() as db:
        other = await service._create_message(db, conversation.id, "user", opening.content)
        other.turn_state = "settled"
        discussion = await service._create_message(db, conversation.id, "user", "Discuss this image")
        discussion.turn_state = "settled"
        stopped = await service._create_message(db, conversation.id, "user", opening.content)
        stopped.turn_state = "settled"
        stopped.intent = {"stop_requested_at": "before submission"}
        await db.commit()
    with pytest.raises(service.TurnStopped):
        await submit(task, origin=stopped.id)
    for kwargs in ({"caller": uuid4()}, {"origin": discussion.id}):
        denied, outcome = await submit(task, **kwargs)
        assert not denied.ok and outcome is None

    # A real request needing approval must return to the existing plan door.
    with monkeypatch.context() as patch:
        dock = AsyncMock(return_value=ToolObservation("confirmation required"))
        patch.setattr(media_journey, "_dock_tasks", dock)
        patch.setattr(service, "_safe_task_estimate", AsyncMock(return_value=None))
        held, outcome = await submit(task)
        assert held.text == "confirmation required" and outcome is None
        dock.assert_awaited_once()
    with monkeypatch.context() as patch:
        from app.platform.billing import CreditsInsufficientError
        patch.setattr("app.pipeline.orchestrator.check_hold", AsyncMock(
            side_effect=CreditsInsufficientError(balance=0, required=1)))
        denied, outcome = await submit(task)
        assert "credits.insufficient" in denied.text and outcome is None
    first, _ = await submit(task, commit=False)
    assert first.ok and not first.persist, first.text
    async with database() as db:
        saved = (await db.get(Conversation, conversation.id)).context["music_requests"][str(opening.id)]
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 0
    twin = TaskItem.model_validate(saved["task"])
    pairs = await asyncio.gather(submit(twin), submit(task))
    assert all(obs.ok for obs, _ in pairs)
    assert pairs[0][1][1] == pairs[1][1][1]
    blocked, outcome = await submit(task, origin=other.id)
    assert not blocked.ok and outcome is None and "start.blocked" in blocked.text
    mismatch = task.model_copy(update={"params": {**task.params, "name": "Other"}})
    rejected, outcome = await submit(mismatch)
    assert not rejected.ok and outcome is None
    rejected, outcome = await submit(mismatch, hit=True)
    assert not rejected.ok and outcome is None
    async with database() as db:
        run = await db.get(WorkflowRun, pairs[0][1][1])
        run.status = WorkflowStatus.COMPLETED
        await db.commit()
    replayed, outcome = await submit(twin)
    assert replayed.ok and outcome[1] == pairs[0][1][1]
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
        assert await db.scalar(select(func.count()).select_from(WorkflowStep)) == 1
        assert not any(m.question or m.answer for m in (await db.scalars(select(Message))).all())
        charges = await db.scalars(select(CreditTransaction).where(
            CreditTransaction.kind.in_(["hold", "capture", "release"])))
        assert all(tx.amount == 0 for tx in charges)
        row = await db.get(Message, opening.id)
        row.intent = {"stop_requested_at": "now"}
        await db.commit()
    with pytest.raises(service.TurnStopped):
        await submit(task)
