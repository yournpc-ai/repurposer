"""Editing splits and authoring — infra contracts."""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.chat.editor import SplitClipArgs, edit_clip
from app.chat.service import TurnStopped, stop_turn_at_visible_frontier
from app.editing.revisions import fixed_visual_ops
from app.editing.service import compute_change_set, revise_video, video_version_read
from app.editing.store import (
    PermissionDenied,
    RequestMismatch,
    StaleBase,
    apply_composition_edits,
    content_of,
    get_video_version,
)
from app.models.schemas import ChatTurnStopRequest, ReviseVideoOpsArgs
from app.models.tables import (
    Composition,
    CompositionVersion,
    Conversation,
    Message,
    MessageSeqCounter,
    Project,
    SourceSnapshot,
    User,
)
from app.skills.resolution import get_builtin_skill_option
from test.support.db_helpers import _create, _snapshots
from test.support.revision_fixtures import (
    VIDEO_ID,
    revision_args,
    revision_content,
    snapshot_facts,
)

pytestmark = pytest.mark.infra


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
    # Distinguish the identity of a user's request from the placement arguments.
    from app.models.schemas import AssetType
    from app.models.tables import Asset, SourceSnapshot
    from test.support.composition_fixtures import IMG_SNAPSHOT

    placement = dict(source_id=IMG_SNAPSHOT, start_seconds=1, end_seconds=3)
    with pytest.raises(ValueError, match="from this project"):
        await execute("insert_visual", "unbound", **placement)
    async with database() as db:
        source = await db.get(SourceSnapshot, IMG_SNAPSHOT)
        asset = Asset(user_id=owner, project_id=pid, type=AssetType.IMAGE, title="product.png")
        db.add(asset)
        await db.flush()
        source.asset_id = asset.id
        source.meta = {"width": 220, "height": 120}
        await db.commit()
    pictures = [await save("insert_visual", **placement) for _ in range(2)]
    targets = [picture["changed_clips"][0] for picture in pictures]
    assert targets[0]["clip_id"] != targets[1]["clip_id"]
    assert targets[0]["object_id"] != targets[1]["object_id"]
    assert targets[0]["source"] == targets[1]["source"]
    with pytest.raises(ValueError, match="window"):
        await execute("insert_visual", "outside-window", **{**placement, "end_seconds": 10})
    for name, native, args, saved in calls:
        replay = await execute(name, native, **args)
        assert replay["replayed"] and replay["version_id"] == saved
        changed = dict(args)
        field = next(k for k in ("time", "end", "x", "value", "start_seconds") if k in changed)
        changed[field] += 0.2
        with pytest.raises(RequestMismatch):
            await execute(name, native, **changed)

    async with database() as db:
        _, head = await get_video_version(db, owner_id=owner, composition_id=comp.id)
        assert head.version == initial.version + len(calls)
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


@pytest.mark.parametrize("exit_kind", ["no_progress", "exhausted", "refusal", "provider_failure", "history_first"])
async def test_partial_edit_final_message(database, monkeypatch, exit_kind):
    from app.agents.tool_loop import LoopResult
    from app.chat.editor import ExtendStillArgs
    from app.chat.editor_recovery import recover_interrupted_edits
    from app.chat.plan_turn import PlanTurn
    from app.chat.service import _create_message, settle_failed_chat_turn
    from app.editing.store import apply_composition_edits, content_of
    from app.models.schemas import ChatRequest

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    work, first, _ = await _create(database, owner, pid)
    draft = content_of(first)
    caption = draft.timeline.tracks[1]
    caption.role = "caption"
    caption.clips[0].animations.clear()
    async with database() as db:
        _, base, _ = await apply_composition_edits(
            db, owner_id=owner, composition_id=work.id, base_version_id=first.id,
            base_digest=first.content_digest, content=draft.model_dump(mode="json"),
        )
        conv = Conversation(user_id=owner, project_id=pid)
        db.add(conv)
        await db.flush()
        opening_id = uuid4()
        question = "结尾再留半秒，其他保持原样。"
        opening = Message(id=opening_id, conversation_id=conv.id, seq=1, role="user",
                          content=question, turn_state="in_flight")
        db.add_all([opening, MessageSeqCounter(conversation_id=conv.id, last_seq=1)])
        await db.commit()
        project = await db.get(Project, pid)
        # The long-lived Chat session already holds the old opening in its identity map.
        async with database() as writer:
            args = dict(name="extend_still", project=project, opening_id=opening_id,
                        conversation_id=conv.id, call_id="caption", args=ExtendStillArgs(clip_id="clp_title", seconds=.5),
                        base={"composition_id": str(work.id), "composition_version_id": str(base.id),
                              "content_digest": base.content_digest})
            saved = await edit_clip(writer, **args)
        assert not (opening.intent or {}).get("editor_commits")
        expected_head = saved["version_id"]
        if exit_kind == "exhausted":
            async with database() as other:
                # A later writer may move the head while the original opening is running.
                _, later, _ = await apply_composition_edits(
                    other, owner_id=owner, composition_id=work.id,
                    base_version_id=UUID(saved["version_id"]), base_digest=saved["content_digest"],
                    content=draft.model_dump(mode="json"),
                )
                expected_head = str(later.id)
                await _create_message(
                    other, conv.id, "assistant", "允许导出吗？", turn_id=opening_id,
                    intent={"media_permission": {"quote": {}}}, question={"kind": "question"},
                )
                await other.commit()
        if exit_kind in ("provider_failure", "history_first"):
            if exit_kind == "history_first":
                async with database() as reader:
                    assert await recover_interrupted_edits(reader, conv.id)
                    await reader.commit()
            state, row = await settle_failed_chat_turn(opening_id, conv.id, "服务暂不可用。")
            state_again, duplicate = await settle_failed_chat_turn(opening_id, conv.id, "服务暂不可用。")
            assert state == state_again == "failed"
            assert row.id == duplicate.id
        else:
            turn = PlanTurn(db, owner, conv, project, ChatRequest(project_id=pid, message=question),
                            turn_id=opening_id)
            result = LoopResult("", None, None, 11, exhausted=exit_kind == "exhausted",
                                no_progress_tool="trim_clip" if exit_kind == "no_progress" else None,
                                ended_by="review_video" if exit_kind == "refusal" else None,
                                refusal_facts={"kind": "video_review_failure"})
            row, _ = await turn.finish(result)
            opening.turn_state = "settled"
            await db.commit()
        assert row.turn_id == opening_id
        assert "字幕延长了 0.5 秒" in row.content and "没有延长主画面" in row.content
        assert "之前交付" not in row.content
        expected = {"no_progress": "重复尝试", "exhausted": "处理上限",
                    "refusal": "复查未完成", "provider_failure": "服务暂不可用", "history_first": "本轮已中断"}
        assert expected[exit_kind] in row.content
        assert ("此后作品还有其他已保存的修改" in row.content) == (exit_kind == "exhausted")
        assert ("费用等待确认" in row.content) == (exit_kind == "exhausted")
    async with database() as replay:
        assert (await edit_clip(replay, **args))["version_id"] == saved["version_id"]
        assert not await recover_interrupted_edits(replay, conv.id)
        messages = (await replay.scalars(select(Message).where(Message.turn_id == opening_id))).all()
        assert [(m.id, m.content) for m in messages if not m.question] == [(row.id, row.content)]
        _, head = await get_video_version(replay, owner_id=owner, composition_id=work.id)
        assert str(head.id) == expected_head


async def _user(factory):
    async with factory() as db:
        row = User(email=f"{uuid4()}@example.test", name="promo")
        db.add(row)
        await db.commit()
        return row.id


async def _project(factory, owner_id):
    async with factory() as db:
        row = Project(user_id=owner_id, title="promo")
        db.add(row)
        await db.commit()
        return row.id


async def _sources(factory, owner_id):
    facts = snapshot_facts(owner_id)
    async with factory() as db:
        for snapshot_id, fact in facts.items():
            db.add(
                SourceSnapshot(
                    id=snapshot_id,
                    owner_id=owner_id,
                    kind=fact["kind"],
                    storage_key=fact["storage_key"],
                    digest=fact["digest"],
                    duration_ticks=fact["duration_ticks"],
                    meta=fact["meta"],
                )
            )
        await db.commit()


@pytest.mark.asyncio
async def test_overlay_saves_change_set_and_stale_base_never_overwrites(database, installed_promo):
    owner = await _user(database)
    project = await _project(database, owner)
    await _sources(database, owner)
    provenance = {
        "skill": "promo-video",
        "skill_reference": get_builtin_skill_option("promo-video").reference.model_dump(
            mode="json"
        ),
        "skill_version": get_builtin_skill_option("promo-video").reference.version,
        "arc_id": "product-evidence",
        "language": "en",
        "copy_evidence": [],
        "builder_version": "promo-native-v1",
    }
    async with database() as db:
        composition, base, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            origin_project_id=project,
            content=revision_content(),
            skill_provenance=provenance,
            name="OxValue promo",
        )
    scene = next(scene for scene in base.scenes if scene["scene_id"] == "proof")
    start = scene["range"]["start"] + 45000
    async with database() as db:
        ops = fixed_visual_ops(content_of(base), snapshot_facts(owner)[VIDEO_ID], source_id=VIDEO_ID,
                               identity=uuid4().hex, scene_id="proof", start=start, end=start + 180000,
                               position="bottom_right", width_ratio=0.28, margin_px=48, fade_in=True)
        _, version, _ = await apply_composition_edits(
            db, owner_id=owner, composition_id=composition.id, base_version_id=base.id,
            base_digest=base.content_digest, ops=ops, request_id="promo-overlay-v2",
            skill_provenance=provenance,
        )
        read = await video_version_read(db, owner_id=owner, version_id=version.id)
        read["change_set"] = compute_change_set(content_of(base), content_of(version))
    added = read["change_set"]["clips"]["added"]
    assert len(added) == 1
    overlay_id = added[0]["clip_id"]
    assert not read["change_set"]["clips"]["updated"]
    assert not read["change_set"]["clips"]["removed"]
    storyboard_clip = next(
        clip
        for scene in read["storyboard"]["scenes"]
        for clip in scene["clips"]
        if clip["clip_id"] == overlay_id
    )
    assert storyboard_clip["object_kind"] == "video"
    async with database() as db:
        version = await db.get(CompositionVersion, read["composition_version_id"])
        assert version.skill_provenance["arc_id"] == "product-evidence"
        assert version.skill_provenance["builder_version"] == "promo-native-v1"
        assert "last_revision" not in version.skill_provenance
        content = content_of(version)
        track = next(
            track
            for track in content.timeline.tracks
            if any(clip.clip_id == overlay_id for clip in track.clips)
        )
        overlay = track.clips[0]
        assert track.kind == "visual" and track.role == "effect"
        assert round(overlay.object.layout.x + overlay.object.layout.width + 48) == 1920
        assert overlay.source.snapshot_id == VIDEO_ID
        assert overlay.source.source_range.duration == 180000
        assert len(overlay.animations) == 1
        with pytest.raises(StaleBase):
            await revise_video(
                db,
                owner_id=owner,
                args=revision_args(
                    base,
                    {
                        "op": "set_text",
                        "clip_id": "clp_open_name",
                        "text": "Must not overwrite",
                    },
                ),
                request_id="promo-stale-base",
            )
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 2
        current = await db.get(Composition, composition.id, populate_existing=True)
        assert current.current_version_id == UUID(read["composition_version_id"])


@pytest.mark.asyncio
async def test_add_audio_effect_loads_new_source_and_saves_version(database, installed_promo):
    owner = await _user(database)
    project = await _project(database, owner)
    await _sources(database, owner)
    audio_id = uuid4()
    async with database() as db:
        db.add(SourceSnapshot(
            id=audio_id,
            owner_id=owner,
            kind="audio",
            storage_key="sources/click.mp3",
            digest="e" * 64,
            duration_ticks=90000,
            meta={},
        ))
        composition, base, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            origin_project_id=project,
            content=revision_content(),
            name="Audio effect base",
        )
        await db.commit()
    async with database() as db:
        read = await revise_video(
            db,
            owner_id=owner,
            args=revision_args(base, {
                "op": "add_audio_effect",
                "source_id": str(audio_id),
                "scene_id": "proof",
                "start_seconds": 4.5,
                "duration_seconds": 0.2,
            }),
            request_id="audio-effect-v2",
        )
    assert read["version"] == 2
    async with database() as db:
        version = await db.get(CompositionVersion, read["composition_version_id"])
        updated = content_of(version)
    track = next(track for track in updated.timeline.tracks if track.track_id == "trk_audio_effect")
    assert track.kind == "audio" and track.role == "effect"
    assert len(track.clips) == 1
    assert track.clips[0].source.snapshot_id == audio_id


@pytest.mark.asyncio
async def test_direct_op_batch_saves_one_version_for_one_user_intent(database, installed_promo):
    owner = await _user(database)
    project = await _project(database, owner)
    async with database() as db:
        composition, base, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            origin_project_id=project,
            content=revision_content(),
            name="Direct Op batch",
        )
    args = ReviseVideoOpsArgs.model_validate({
        "base_ref": {
            "composition_id": str(composition.id),
            "composition_version_id": str(base.id),
            "content_digest": base.content_digest,
        },
        "ops": [
            {"op": "set_text", "clip_id": "clp_open_name", "text": "Direct opening"},
            {"op": "set_text", "clip_id": "clp_proof_name", "text": "Direct proof"},
        ],
    })
    async with database() as db:
        read = await revise_video(db, owner_id=owner, args=args, request_id="direct-op-batch")
        assert read["version"] == 2
        assert len(read["change_set"]["clips"]["updated"]) == 2
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 2
        current = await db.get(Composition, composition.id)
        assert current.current_version_id == UUID(read["composition_version_id"])
        content = content_of(await db.get(CompositionVersion, current.current_version_id))
        texts = {
            clip.object.text
            for track in content.timeline.tracks
            for clip in track.clips
            if clip.clip_id in {"clp_open_name", "clp_proof_name"}
        }
        assert texts == {"Direct opening", "Direct proof"}
