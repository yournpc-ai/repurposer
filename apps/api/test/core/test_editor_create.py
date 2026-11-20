import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.agents.tool_progress import bind_progress
from app.chat.editor_create import CreateVideoArgs, create_video
from app.chat.service import _create_message
from app.editing.store import RequestMismatch
from app.models.tables import Composition, CompositionVersion, Conversation, Project
from test.core.test_compositions import _project, _user


@pytest.mark.asyncio
async def test_concurrent_first_versions_and_native_call_replay(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, project_id)
        turns = []
        for _ in range(2):
            conversation = Conversation(user_id=owner, project_id=project_id)
            db.add(conversation)
            await db.commit()
            opening = await _create_message(db, conversation.id, "user", "Make a three-second title.")
            opening.turn_state = "in_flight"
            turns.append(SimpleNamespace(project=project, conversation_id=conversation.id, turn_id=opening.id))
        await db.commit()

    args = CreateVideoArgs(name="Title", shots=[{"headline": "Goodbye", "duration_seconds": 3}])

    async def submit(turn, params=args):
        async with database() as session:
            with bind_progress("first-card", None):
                return await create_video(session, turn, params)

    results = await asyncio.gather(*(submit(turn) for turn in turns), return_exceptions=True)
    saved = [index for index, result in enumerate(results) if isinstance(result, dict)]
    assert len(saved) == 1
    winner = saved[0]
    assert isinstance(results[1 - winner], ValueError)
    assert (await submit(turns[winner]))["version_id"] == results[winner]["version_id"]
    with pytest.raises(RequestMismatch):
        await submit(turns[winner], args.model_copy(update={"name": "Different work"}))
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 1
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 1
