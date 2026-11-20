"""Saved-work editing through the real turn fence and Postgres version store."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.chat.editor import SplitClipArgs, split_clip
from app.chat.service import TurnStopped, stop_turn_at_visible_frontier
from app.editing.store import PermissionDenied, RequestMismatch, StaleBase, get_video_version
from app.models.schemas import ChatTurnStopRequest
from app.models.tables import CompositionVersion, Conversation, Message, Project
from test.core.test_compositions import _create, _project, _snapshots, _user

pytestmark = pytest.mark.asyncio


async def test_split_recovery_and_isolation(database):
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, initial, _ = await _create(database, owner, pid)
    base = dict(
        composition_id=str(comp.id),
        composition_version_id=str(initial.id),
        content_digest=initial.content_digest,
    )
    async with database() as db:
        project = await db.get(Project, pid)
        conversation = Conversation(user_id=owner, project_id=pid)
        db.add(conversation)
        await db.flush()
        turns = []
        for seq in [1, 2, 3]:
            uid = uuid4()
            turns.append(uid)
            db.add(
                Message(
                    id=uid,
                    turn_id=uid,
                    conversation_id=conversation.id,
                    seq=seq,
                    role="user",
                    content="Split the background",
                    turn_state="in_flight",
                )
            )
        await db.commit()

    async def edit(turn, identity, time=2, ref=base, current_project=project):
        async with database() as db:
            return await split_clip(
                db,
                project=current_project,
                opening_id=turn,
                conversation_id=conversation.id,
                call_id=identity,
                base=ref,
                args=SplitClipArgs(clip_id="clp_bg", time=time),
            )

    # Two requests against one inspected version cannot both land.
    results = await asyncio.gather(edit(turns[0], "a"), edit(turns[1], "b"), return_exceptions=True)
    assert sum(isinstance(x, StaleBase) for x in results) == 1
    winner = next(i for i, x in enumerate(results) if isinstance(x, dict))
    turn, identity = turns[winner], ["a", "b"][winner]
    saved = results[winner]
    current = {
        **base,
        "composition_version_id": saved["version_id"],
        "content_digest": saved["content_digest"],
    }
    twins = await asyncio.gather(edit(turn, identity), edit(turn, identity, ref=current))
    assert all(t["replayed"] and t["version_id"] == saved["version_id"] for t in twins)
    with pytest.raises(RequestMismatch):
        await edit(turn, identity, time=1, ref=current)
    with pytest.raises(ValueError, match="strictly inside"):
        await edit(turn, "edge", time=2, ref=current)

    async with database() as db:
        other_owner = await _user(database)
        foreign = await db.get(Project, await _project(database, other_owner))
    with pytest.raises(PermissionDenied):
        await edit(turns[2], "foreign", current_project=foreign)
    async with database() as db:
        await stop_turn_at_visible_frontier(db, turns[2], ChatTurnStopRequest())
    with pytest.raises(TurnStopped):
        await edit(turns[2], "stopped", ref=current)
    # Stop after commit cannot roll back the user's saved edit.
    async with database() as db:
        await stop_turn_at_visible_frontier(db, turn, ChatTurnStopRequest())
    async with database() as db:
        _, head = await get_video_version(db, owner_id=owner, composition_id=comp.id)
        assert str(head.id) == saved["version_id"] and head.base_version_id == initial.id
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 2
        assert head.timeline["tracks"][1:] == initial.timeline["tracks"][1:]
        assert head.settings == initial.settings and head.sources == initial.sources
        background = head.timeline["tracks"][0]["clips"]
        assert [(c["clip_id"], c["range"]) for c in background] == [
            ("clp_bg", {"start": 0, "end": 180000}),
            (saved["right_clip_id"], {"start": 180000, "end": 360000}),
        ]
