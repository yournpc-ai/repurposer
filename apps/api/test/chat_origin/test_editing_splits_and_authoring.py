"""Layer 1A Chat-Origin: clip split/trim/transition editing and high-level revision authoring."""

from __future__ import annotations
import pytest

import asyncio


from uuid import UUID, uuid4


import pytest


from sqlalchemy import func, select


from app.chat.editor import SplitClipArgs, edit_clip


from app.chat.service import TurnStopped, stop_turn_at_visible_frontier


from app.editing.store import PermissionDenied, RequestMismatch, StaleBase, get_video_version


from app.models.schemas import ChatTurnStopRequest


from app.models.tables import CompositionVersion, Conversation, Message, MessageSeqCounter, Project


from test.support.db_helpers import _create, _project, _snapshots, _user





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


# --- High-level authoring & revision contracts ---

from copy import deepcopy


from types import SimpleNamespace


from uuid import UUID, uuid4


import pytest


from pydantic import ValidationError


from sqlalchemy import func, select


from app.agents.candidate_correction import (
    CandidateCorrectionArgs,
    CandidateRecord,
    CandidateScope,
    apply_correction,
)


from app.editing.revisions import RevisionTargetAmbiguityError, expand_revision_op, fixed_visual_ops


from app.editing.schemas import CompositionContent


from app.editing.service import compute_change_set, revise_video, video_version_read


from app.editing.store import StaleBase, apply_composition_edits, content_of


from app.models.schemas import ReviseVideoOpsArgs


from app.models.tables import Composition, CompositionVersion, Project, SourceSnapshot, User


from app.skills.package_session import SkillPackageSession


from app.skills.resolution import get_builtin_skill_option


WEB_ID = UUID("11111111-1111-1111-1111-111111111111")


VIDEO_ID = UUID("33333333-3333-3333-3333-333333333333")


WEB_DIGEST = "a" * 64


VIDEO_DIGEST = "c" * 64


def snapshot_facts(owner_id):
    return {
        WEB_ID: {
            "digest": WEB_DIGEST,
            "kind": "web",
            "owner_id": owner_id,
            "storage_key": "sources/web.json",
            "duration_ticks": None,
            "meta": {
                "views": [
                    {
                        "view_id": "hero",
                        "storage_key": "sources/hero.png",
                        "digest": "b" * 64,
                        "width": 1440,
                        "height": 900,
                        "elements": [
                            {
                                "id": "title",
                                "kind": "heading",
                                "x": 0.5,
                                "y": 0.3,
                                "w": 0.6,
                                "h": 0.15,
                            }
                        ],
                    }
                ]
            },
        },
        VIDEO_ID: {
            "digest": VIDEO_DIGEST,
            "kind": "video",
            "owner_id": owner_id,
            "storage_key": "sources/person.mp4",
            "duration_ticks": 900000,
            "meta": {"media": {"width": 1080, "height": 1920}},
        },
    }


def revision_content():
    def text_clip(scene_id, start, end):
        return {
            "clip_id": f"clp_{scene_id}_name",
            "scene_id": scene_id,
            "range": {"start": start, "end": end},
            "source": None,
            "animations": [],
            "object": {
                "kind": "text",
                "object_id": f"obj_{scene_id}_name",
                "text": "Evidence-led value",
                "layout": {"x": 153.6, "y": 432.0, "width": 1612.8, "height": 166.4},
                "style": {
                    "font_size": 104,
                    "color": "#F8FAFC",
                    "weight": 700,
                    "align": "center",
                    "line_height": 1.2,
                },
            },
        }

    scenes = [
        ("open", 0, 360000),
        ("proof", 360000, 720000),
        ("close", 720000, 990000),
    ]
    return CompositionContent.model_validate({
        "settings": {"width": 1920, "height": 1080, "background": "#0B1020"},
        "sources": [],
        "scenes": [
            {
                "scene_id": scene_id,
                "range": {"start": start, "end": end},
                "intent": f"Scene {scene_id}",
                "speech_clip_ids": [],
            }
            for scene_id, start, end in scenes
        ],
        "timeline": {
            "tracks": [
                {
                    "track_id": "trk_main",
                    "kind": "visual",
                    "role": "main",
                    "order": 0,
                    "clips": [],
                },
                {
                    "track_id": "trk_title",
                    "kind": "visual",
                    "role": "title",
                    "order": 1,
                    "clips": [text_clip(scene_id, start, end) for scene_id, start, end in scenes],
                },
            ],
            "transitions": [],
        },
    })


def revision_args(version, action):
    return ReviseVideoOpsArgs.model_validate(
        {
            "base_ref": {
                "composition_id": str(version.composition_id),
                "composition_version_id": str(version.id),
                "content_digest": version.content_digest,
            },
            "ops": [action],
        }
    )


def test_native_create_and_high_level_revision_wires_stay_closed():
    from app.chat.editor_create import CreateVideoArgs

    assert CreateVideoArgs.model_json_schema()["additionalProperties"] is False

    from app.chat.editor import InsertVisualArgs

    raw = {
        "source_id": str(VIDEO_ID), "start_seconds": 4, "end_seconds": 8,
        "position": "lower-right", "width_ratio": 0.28,
    }
    with pytest.raises(ValidationError) as raised:
        InsertVisualArgs.model_validate(raw)
    import json

    errors = json.loads(raised.value.json(include_input=False, include_url=False))
    record = CandidateRecord.create(
        tool_name="insert_visual",
        arguments=raw,
        errors=errors,
        schema=InsertVisualArgs.model_json_schema(),
        scope=CandidateScope(owner_id=str(uuid4()), conversation_id=str(uuid4())),
        base_keys=frozenset({f"snapshot:{VIDEO_ID}:{VIDEO_DIGEST}"}),
        call_id="call_overlay",
    )
    diagnostic = record.diagnostic()
    assert "candidate" not in diagnostic
    assert diagnostic["candidate_id"] == record.candidate_id
    assert diagnostic["candidate_digest"] == record.candidate_digest
    assert diagnostic["errors"][0]["original_value"] == "lower-right"
    assert record.arguments["position"] == "lower-right"
    request = CandidateCorrectionArgs.model_validate(
        {
            "candidate_id": record.candidate_id,
            "candidate_digest": record.candidate_digest,
            "mode": "patch",
            "corrections": [{"error_id": "error_1", "value": "bottom_right"}],
        }
    ).root
    merged = apply_correction(record, request)
    corrected = InsertVisualArgs.model_validate(merged.arguments)
    assert corrected.position == "bottom_right"
    assert corrected.source_id == VIDEO_ID
    assert record.base_keys == frozenset({f"snapshot:{VIDEO_ID}:{VIDEO_DIGEST}"})


def test_ambiguous_target_returns_candidates_without_ops():
    owner = uuid4()
    content = revision_content()
    track, clip = next(
        (track, clip)
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.clip_id == "clp_open_name"
    )
    duplicate_track = deepcopy(track)
    duplicate_track.track_id = "trk_duplicate"
    duplicate_track.order = 99
    content.timeline.tracks.append(duplicate_track)
    args = revision_args(
        SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64),
        {"op": "set_text", "clip_id": clip.clip_id, "text": "Changed"},
    )
    with pytest.raises(RevisionTargetAmbiguityError) as raised:
        expand_revision_op(args.ops[0], content, facts=snapshot_facts(owner))
    assert len(raised.value.candidates) == 2

    omitted = revision_args(
        SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64),
        {"op": "set_text", "text": "Changed"},
    )
    with pytest.raises(RevisionTargetAmbiguityError) as missing:
        expand_revision_op(omitted.ops[0], content, facts=snapshot_facts(owner))
    assert missing.value.candidates
    assert all("text" in candidate for candidate in missing.value.candidates)


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


@pytest.mark.asyncio
async def test_new_opening_does_not_inherit_historical_skill(database, monkeypatch, installed_promo):
    from app.chat.service import prepare_chat_turn
    from app.models.schemas import ChatRequest
    from app.models.tables import Conversation, Message

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project = await _project(database, owner)
    skill = get_builtin_skill_option("promo-video").reference
    async with database() as db:
        conversation = Conversation(
            user_id=owner,
            project_id=project,
        )
        db.add(conversation)
        await db.flush()
        clarification = uuid4()
        db.add_all([
            Message(
                conversation_id=conversation.id,
                role="user",
                content="first",
                turn_state="settled",
                seq=1,
                intent={"skill": skill.model_dump(mode="json")},
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                id=clarification,
                content="clarify",
                turn_state="settled",
                seq=2,
                intent={
                    "skill": skill.model_dump(mode="json"),
                    "skill_binding": "inherited",
                },
            ),
            Message(conversation_id=conversation.id, role="assistant", content="Which title?",
                    turn_id=clarification, seq=3, question={"kind": "question", "question": "Which title?"}),
        ])
        await db.commit()
        prepared = await prepare_chat_turn(
            db, owner, ChatRequest(project_id=project, message="save the draft"),
        )
        assert prepared.skill is None
        assert not (prepared.user_message.intent or {}).get("skill")


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
async def test_settled_skill_text_receipts_restore_only_same_owner_version_and_digest(tmp_path):
    from app.models.schemas import BuiltInSkillReference
    from app.skills.package_reader import SkillPackageReader

    skill = BuiltInSkillReference(kind="builtin", skill_id="promo-video", version="1.0.0")
    owner = uuid4()
    source_package = SkillPackageSession(SkillPackageReader(root=tmp_path))
    paths = [
        "references/sequences/product-evidence.md",
        "references/shots/opening/brand-emergence.md",
        "references/shots/camera/evidence-push.md",
        "references/shots/outro/next-step-lockup.md",
    ]
    for path in paths:
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"# {path}")
    reads = []
    for path in paths:
        source = await source_package.reader.read_text(path)
        reads.append({
            "path": path,
            "digest": source.digest,
            "kind": "reference",
            "offset": 0,
            "truncated": False,
        })
    package = SkillPackageSession(SkillPackageReader(root=tmp_path))
    receipt = {
        "package_identity": package.receipt_identity(skill),
        "skill_reference": skill.model_dump(mode="json"),
        "owner_id": str(owner),
        "reads": reads,
        "preview_checks": [{"shot_id": "evidence-push", "available": True}],
        "media_files": 1,
    }
    assert await package.restore_text_reads(receipt, skill=skill, owner_id=owner) == 4
    assert {(item["path"], item["digest"]) for item in package.reads} == {
        (item["path"], item["digest"]) for item in reads
    }
    assert package.provenance["preview_checks"] == []
    assert package.media_files == 0 and not package._media_cache

    changed_version = skill.model_copy(update={"version": "2.0.0"})
    other = SkillPackageSession(SkillPackageReader(root=tmp_path))
    assert await other.restore_text_reads(receipt, skill=changed_version, owner_id=owner) == 0
    foreign = SkillPackageSession(SkillPackageReader(root=tmp_path))
    assert await foreign.restore_text_reads(receipt, skill=skill, owner_id=uuid4()) == 0

    changed_reads = deepcopy(reads)
    changed_reads[2]["digest"] = "f" * 64
    stale = SkillPackageSession(SkillPackageReader(root=tmp_path))
    assert await stale.restore_text_reads(
        {**receipt, "reads": changed_reads}, skill=skill, owner_id=owner
    ) == 3
    assert changed_reads[2]["digest"] not in {item["digest"] for item in stale.reads}


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


def test_video_overlay_checks_the_source_window_and_aspect_before_adding_any_ops():
    content = revision_content()
    fact = snapshot_facts(uuid4())[VIDEO_ID]
    args = dict(source_id=VIDEO_ID, identity=uuid4().hex, scene_id="proof", start=360000,
                end=540000, position="bottom_right", width_ratio=0.28, margin_px=48)
    with pytest.raises(ValueError, match="real duration"):
        fixed_visual_ops(content, {**fact, "duration_ticks": 90000}, **args)
    with pytest.raises(ValueError, match="aspect"):
        fixed_visual_ops(content, fact, **{**args, "width_ratio": 0.95})
    assert content == revision_content()


@pytest.mark.asyncio
async def test_generic_scene_video_window_preserves_each_timebase_and_fails_closed():
    from app.tools.video.design import (
        CandidateDesignError,
        CompositionSceneAuthoring,
        _expand_scene_authoring,
    )

    owner = uuid4()
    facts = snapshot_facts(owner)
    content = CompositionContent(
        settings={"timebase": 45000, "width": 1920, "height": 1080},
        scenes=[{
            "scene_id": "proof",
            "range": {"start": 0, "end": 180000},
            "intent": "Show the source",
            "speech_clip_ids": [],
        }],
        timeline={"tracks": [{
            "track_id": "trk_main",
            "kind": "visual",
            "role": "main",
            "order": 0,
            "clips": [],
        }], "transitions": []},
    ).model_dump(mode="json")
    scene = CompositionSceneAuthoring.model_validate({
        "scene_id": "proof",
        "snapshot_id": str(VIDEO_ID),
        "source_start_seconds": 1,
        "source_end_seconds": 5,
    })
    expanded = await _expand_scene_authoring(deepcopy(content), scene, facts)
    clip = expanded["timeline"]["tracks"][0]["clips"][0]
    assert clip["range"] == {"start": 0, "end": 180000}
    assert clip["source"]["source_range"] == {"start": 90000, "end": 450000}
    assert clip["object"]["kind"] == "video"

    original = deepcopy(content)
    with pytest.raises(CandidateDesignError) as raised:
        await _expand_scene_authoring(
            deepcopy(content),
            CompositionSceneAuthoring.model_validate({
                "scene_id": "proof",
                "snapshot_id": str(VIDEO_ID),
                "source_start_seconds": 8,
                "source_end_seconds": 12,
            }),
            facts,
        )
    assert raised.value.issues[0]["type"] == "source_too_short"
    assert content == original
    with pytest.raises(ValidationError):
        CompositionSceneAuthoring.model_validate({
            "scene_id": "proof",
            "snapshot_id": str(VIDEO_ID),
            "source_start_seconds": 5,
            "source_end_seconds": 1,
        })


def test_add_audio_effect_expands_to_a_trimmed_audio_clip():
    from app.editing.edits import apply_ops
    from app.editing.validators import validate_content

    audio_id = uuid4()
    content = revision_content()
    version = SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64)
    args = revision_args(version, {
        "op": "add_audio_effect",
        "source_id": str(audio_id),
        "scene_id": "proof",
        "start_seconds": 4.5,
        "duration_seconds": 0.2,
        "gain_db": -6,
    })
    facts = {
        **snapshot_facts(version.composition_id),
        audio_id: {
            "kind": "audio", "digest": "e" * 64, "storage_key": "sources/click.mp3",
            "duration_ticks": 90000, "meta": {},
        },
    }
    updated = apply_ops(
        content,
        expand_revision_op(args.ops[0], content, facts=facts),
        {audio_id: "e" * 64},
    )
    validate_content(updated, facts)
    track = next(track for track in updated.timeline.tracks if track.track_id == "trk_audio_effect")
    assert track.kind == "audio" and track.role == "effect"
    assert len(track.clips) == 1
    clip = track.clips[0]
    assert clip.object.kind == "audio" and clip.object.gain_db == -6
    assert clip.scene_id == "proof"
    assert clip.range.start == 405000 and clip.range.end == 423000
    assert clip.source.snapshot_id == audio_id
    assert clip.source.source_range.start == 0
    assert clip.source.source_range.end == 18000


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


def test_set_narration_changes_only_pending_speech_text():
    from app.editing.edits import apply_ops
    from app.editing.schemas import Clip, SpeechObject, Track
    from app.editing.validators import validate_content

    content = revision_content()
    scene = next(scene for scene in content.scenes if scene.scene_id == "proof")
    content.timeline.tracks.append(Track(
        track_id="trk_dialogue",
        kind="audio",
        role="dialogue",
        order=0,
        clips=[Clip(
            clip_id="clp_speech_proof",
            scene_id="proof",
            range=scene.range,
            source=None,
            object=SpeechObject(
                kind="speech",
                object_id="obj_speech_proof",
                text="A much longer narration that needs to be shortened",
                voice_id="presenter_male",
                language="en",
            ),
            animations=[],
        )],
    ))
    scene.speech_clip_ids.append("clp_speech_proof")
    args = revision_args(
        SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64),
        {"op": "set_narration", "clip_id": "clp_speech_proof", "text": "Shorter narration"},
    )
    updated = apply_ops(
        content,
        expand_revision_op(args.ops[0], content, facts=snapshot_facts(uuid4())),
        {},
    )
    validate_content(updated, snapshot_facts(uuid4()))
    speech = next(
        clip for track in updated.timeline.tracks for clip in track.clips if clip.clip_id == "clp_speech_proof"
    )
    assert speech.object.text == "Shorter narration"
    assert speech.object.voice_id == "presenter_male" and speech.object.language == "en"
    assert speech.range == scene.range and speech.scene_id == "proof"


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


def test_editor_does_not_silently_rebind_an_old_or_inaccessible_output():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.prompts import assemble_video_round
    from app.chat.intent import intent_router

    base = {"composition_id": str(uuid4()), "composition_version_id": str(uuid4()), "content_digest": "a"*64}
    work = {"kind": "composition", "base_ref": base, "composition_id": base["composition_id"],
            "version_id": base["composition_version_id"]}
    for hint in [{"unavailable": True}, {"composition_id": str(uuid4())},
                 {"composition_id": base["composition_id"], "version_id": str(uuid4())}]:
        assembly = assemble_video_round({"snapshot": ContextSnapshot("saved", resources=(("work", work),)),
                                         "tools": intent_router.tools, "mode": "plan", "target_hint": hint})
        assert assembly.caller_state["video_target"] is None

