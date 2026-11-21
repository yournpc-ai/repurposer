"""Saved-work editing through the real turn fence and Postgres version store."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.chat.editor import SplitClipArgs, edit_clip
from app.chat.service import TurnStopped, stop_turn_at_visible_frontier
from app.editing.store import PermissionDenied, RequestMismatch, StaleBase, get_video_version
from app.models.schemas import ChatTurnStopRequest
from app.models.tables import CompositionVersion, Conversation, Message, MessageSeqCounter, Project
from test.core.test_compositions import _create, _project, _snapshots, _user

pytestmark = pytest.mark.asyncio


async def test_split_recovery_and_isolation(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
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
        db.add(MessageSeqCounter(conversation_id=conversation.id, last_seq=3))
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
            return await edit_clip(
                db,
                name="split_clip",
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


async def test_edit_sequence_replay_and_safe_boundaries(database, monkeypatch):
    from app.chat.editor import WRITE_TOOLS
    from app.chat.editor_recovery import editor_lock_key, recover_interrupted_edits
    from app.editing.store import apply_composition_edits, content_of

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, first, _ = await _create(database, owner, pid)
    # One fixed audio source is linked to the image. Title keyframes live on
    # a different track. All temporal operations must keep audio in sync.
    content = content_of(first)
    for i in [0, 2]:
        content.timeline.tracks[i].clips[0].linked_group_id = "sync"
    async with database() as db:
        _, initial, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            composition_id=comp.id,
            base_version_id=first.id,
            base_digest=first.content_digest,
            request_id=str(uuid4()),
            content=content.model_dump(mode="json"),
        )
        project = await db.get(Project, pid)
        convo = Conversation(user_id=owner, project_id=pid)
        db.add(convo)
        await db.flush()
        turn = uuid4()
        db.add(
            Message(
                id=turn,
                turn_id=turn,
                conversation_id=convo.id,
                seq=1,
                role="user",
                content="Edit these clips",
                turn_state="in_flight",
            )
        )
        db.add(MessageSeqCounter(conversation_id=convo.id, last_seq=1))
        await db.commit()

    ref = dict(
        composition_id=str(comp.id),
        composition_version_id=str(initial.id),
        content_digest=initial.content_digest,
    )

    async def execute(name, call, **arguments):
        async with database() as db:
            return await edit_clip(
                db,
                name=name,
                project=project,
                opening_id=turn,
                conversation_id=convo.id,
                call_id=call,
                base=ref,
                args=WRITE_TOOLS[name].params_model(**arguments),
            )

    calls = []

    async def save(name, **arguments):
        call = f"native-{len(calls)}"
        version = await execute(name, call, **arguments)
        assert version["base_version_id"] == ref["composition_version_id"]
        assert version["version"] == initial.version + len(calls) + 1
        calls.append((name, call, arguments, version["version_id"]))
        ref.update(
            composition_version_id=version["version_id"], content_digest=version["content_digest"]
        )
        return version

    split = await save("split_clip", clip_id="clp_bg", time=2)
    right = split["right_clip_id"]
    image = next(c for c in split["changed_clips"] if c["clip_id"] == right)
    trimmed = await save("trim_clip", clip_id=right, start=0.4, end=1.4)
    audio = next(c for c in trimmed["changed_clips"] if c["kind"] == "audio")
    assert audio["source"]["source_range"] == {"start": 216000, "end": 306000}
    assert (audio["start_seconds"], audio["end_seconds"]) == (2.4, 3.4)
    with pytest.raises(ValueError, match="overlap"):
        await execute("move_clip", "collision", clip_id=right, time=1)
    with pytest.raises(ValueError, match="escape Scene"):
        await execute("move_clip", "outside", clip_id=right, time=4)
    moved = await save("move_clip", clip_id=right, time=3)
    assert len(moved["changed_clips"]) == 2
    assert all((c["start_seconds"], c["end_seconds"]) == (3, 4) for c in moved["changed_clips"])
    assert (
        next(c for c in moved["changed_clips"] if c["kind"] == "audio")["source"] == audio["source"]
    )
    await save("scale", id=image["object_id"], value=0.7)
    await save("translate", id=image["object_id"], x=-18, y=0)
    with pytest.raises(ValueError, match="visual object"):
        await execute("scale", "not-visual", id=audio["object_id"], value=0.7)
    with pytest.raises(ValueError, match="already has"):
        await execute("translate", "no-change", id=image["object_id"], x=-18, y=0)
    for name, native, args, saved in calls:
        replay = await execute(name, native, **args)
        assert replay["replayed"] and replay["version_id"] == saved
        changed = dict(args)
        field = next(k for k in ("time", "end", "x", "value") if k in changed)
        changed[field] += 0.2
        with pytest.raises(RequestMismatch):
            await execute(name, native, **changed)

    async with database() as db:
        _, head = await get_video_version(db, owner_id=owner, composition_id=comp.id)
        assert head.version == initial.version + 5
        assert head.timeline["tracks"][1] == initial.timeline["tracks"][1]
        assert head.sources == initial.sources and head.settings == initial.settings
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == head.version
        # Simulate an ongoing SSE turn holding the transaction fence. History
        # must not reconcile it until that session exits.
        await db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn))))
        async with database() as reader:
            await recover_interrupted_edits(reader, convo.id)
            assert (await reader.get(Message, turn)).turn_state == "in_flight"
    async with database() as db:
        await recover_interrupted_edits(db, convo.id)
        await db.commit()
        assert (await db.get(Message, turn)).turn_state == "failed"
        summary = await db.scalar(
            select(Message.content).where(Message.intent["type"].astext == "editor_recovery")
        )
        assert "translation" in summary and "trim" in summary


async def test_transition_boundaries_and_targeted_keyframe_edit(database):
    from app.chat.editor import WRITE_TOOLS
    from app.editing.schemas import Animation, Transition
    from app.editing.store import apply_composition_edits, content_of

    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, first, _ = await _create(database, owner, pid)
    content = content_of(first)
    left = content.timeline.tracks[0].clips[0]
    left.object.fit = "cover"
    right = left.model_copy(deep=True)
    left.range.end = right.range.start = 180000
    right.clip_id, right.object.object_id = "right", "right_img"
    content.timeline.tracks[0].clips.append(right)
    content.timeline.transitions = [
        Transition(
            transition_id="fade",
            from_clip_id=left.clip_id,
            to_clip_id=right.clip_id,
            duration=36000,
        )
    ]
    title = content.timeline.tracks[1].clips[0]
    title.animations.append(
        Animation(
            animation_id="zoom",
            target_object_id=title.object.object_id,
            property="transform.scale",
            keyframes=[{"at": 0, "value": 1}, {"at": 90000, "value": 1.2}],
        )
    )
    async with database() as db:
        _, first, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            composition_id=comp.id,
            base_version_id=first.id,
            base_digest=first.content_digest,
            content=content,
        )
        project = await db.get(Project, pid)
        conversation = Conversation(user_id=owner, project_id=pid)
        db.add(conversation)
        await db.flush()
        turn = uuid4()
        db.add(
            Message(
                id=turn,
                turn_id=turn,
                conversation_id=conversation.id,
                seq=1,
                role="user",
                content="Edit",
                turn_state="in_flight",
            )
        )
        await db.commit()
    for name, args, error in [
        ("trim_clip", {"clip_id": left.clip_id, "end": 1}, "adjacent cut"),
        ("move_clip", {"clip_id": right.clip_id, "time": 1}, "adjacent cut"),
        ("scale", {"id": title.object.object_id, "value": 0.8}, "Keyframes"),
    ]:
        async with database() as db:
            with pytest.raises(ValueError, match=error):
                await edit_clip(
                    db,
                    name=name,
                    project=project,
                    opening_id=turn,
                    conversation_id=conversation.id,
                    call_id=name,
                    base=dict(
                        composition_id=str(comp.id),
                        composition_version_id=str(first.id),
                        content_digest=first.content_digest,
                    ),
                    args=WRITE_TOOLS[name].params_model(**args),
                )
    async with database() as db:
        _, head = await get_video_version(db, owner_id=owner, composition_id=comp.id)
        assert head.id == first.id and head.timeline == first.timeline

    # The same animated object accepts a value change at an existing tick.
    from app.chat.editor import SetKeyframeArgs

    ref = dict(composition_id=str(comp.id), composition_version_id=str(first.id),
               content_digest=first.content_digest)

    async def set_point(call_id, value):
        async with database() as db:
            return await edit_clip(
                db, name="set_keyframe", project=project, opening_id=turn,
                conversation_id=conversation.id, call_id=call_id, base=ref,
                args=SetKeyframeArgs(clip_id=title.clip_id, animation_id="zoom", at=90000, value=value),
            )

    with pytest.raises(ValueError, match="scalar"):
        await set_point("invalid", [2, 3])
    result = await set_point("update", 1.1)
    replay = await set_point("update", 1.1)
    assert replay["replayed"] and replay["version_id"] == result["version_id"]
    with pytest.raises(StaleBase):
        await set_point("stale", 1.15)
    async with database() as db:
        _, head = await get_video_version(db, owner_id=owner, composition_id=comp.id)
        expected = content_of(first)
        expected.timeline.tracks[1].clips[0].animations[-1].keyframes[1].value = 1.1
        assert head.timeline == expected.timeline.model_dump(mode="json")
        assert head.version == first.version + 1
