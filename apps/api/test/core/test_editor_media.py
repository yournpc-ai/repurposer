import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.chat import editor_media, service
from app.models.schemas import OptionAnswerRequest, ChatTurnStopRequest
from app.models.tables import Conversation, CreditTransaction, Message, Project, User, WorkflowRun, WorkflowStep
from app.tools.music.score import GenerateMusicArgs
from test.core.test_compositions import _create, _project, _snapshots, _user


@pytest.mark.asyncio
async def test_native_music_request_replay_stop_and_permission(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "cached_music_preparation", AsyncMock(return_value=None))
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, version, _ = await _create(database, owner, pid)
    args = GenerateMusicArgs(style="ambient", duration_seconds=4)
    async with database() as db:
        project = await db.get(Project, pid)
        convo = Conversation(user_id=owner, project_id=pid)
        db.add(convo)
        await db.commit()
        async def opening():
            row = await service._create_message(db, convo.id, "user", "Make music")
            row.turn_state = "in_flight"
            await db.commit()
            return SimpleNamespace(project=project, user_id=owner, turn_id=row.id, conversation_id=convo.id,
                                   _video_base_ref={"content_digest": version.content_digest})
        turn = await opening()
        def submit(turn, args=args):
            return editor_media.submit_editor_media(turn, "generate_music", args, comp, version, "call-1")
        twin = await asyncio.gather(submit(turn), submit(turn))
        assert twin[0].workflow_run_id == twin[1].workflow_run_id and twin[0].id == twin[1].id
        with pytest.raises(ValueError, match="different parameters"):
            await submit(turn, args.model_copy(update={"bpm": 92}))
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
        assert await db.scalar(select(func.count()).select_from(WorkflowStep)) == 1
        assert await service.stop_turn_at_visible_frontier(db, turn.turn_id, ChatTurnStopRequest()) == "cancelled"
        assert (await db.get(WorkflowRun, twin[0].workflow_run_id)).status.value == "cancelled"
        assert await db.get(Message, twin[0].id)
        with pytest.raises(service.TurnStopped):
            await submit(turn)
        early = await opening()
        await service.stop_turn_at_visible_frontier(db, early.turn_id, ChatTurnStopRequest())
        with pytest.raises(service.TurnStopped):
            await submit(early)
        user = await db.get(User, owner)
        user.settings = {"confirm_execution": "ask"}
        await db.commit()
        ask = await opening()
        receipt = await submit(ask)
        assert receipt.question["kind"] == "question" and receipt.workflow_run_id is None
        decline, _ = await service.answer_question(db, owner, receipt.id, OptionAnswerRequest(kind="option", option_id="decline"))
        assert decline.intent["media_result"] == {"status": "declined"}
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
        permit = await submit(await opening())
        accepted, _ = await service.answer_question(db, owner, permit.id, OptionAnswerRequest(kind="option", option_id="approve"))
        assert accepted.workflow_run_id is not None
        assert all(v == 0 for v in await db.scalars(select(CreditTransaction.amount).where(
            CreditTransaction.kind.in_(["hold", "capture", "release"]))))
