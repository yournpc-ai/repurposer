"""Deterministic core tests for Wave 4B-3: H1-H5 harness fixes, update_steps,
Project 1:N Conversation, /compact, message_feedback Eval snapshots, and /workbench."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.agents.tool_loop import BatchDeclared, BatchMember, ContextSnapshot, ReadExecuting
from app.agents.tool_progress import bind_progress
from app.chat.activity import (
    KIND_STEPS,
    ActivityProjector,
    finalize_steps,
    frame_persistence,
    sanitize_steps,
)
from app.chat.context import conversation_messages
from app.chat.editor import (
    GenerateSfxArgs,
    InsertMotionBlockArgs,
    _remember_labels,
    edit_clip,
    project_editor_reply,
)
from app.chat.editor_create import CreateVideoArgs, create_video
from app.chat.editor_media import execute_generate_sfx
from app.chat.intent import intent_router
from app.chat.plan_turn import run_plan_turn
from app.chat.prompts import assemble_video_round
from app.chat.service import _create_message, prepare_chat_turn
from app.config import settings
from app.dependencies import get_current_user_required, get_db
from app.editing.catalog import MOTION_BLOCK_CATALOG
from app.editing.store import content_of
from app.main import app
from app.models import database as database_module
from app.models.schemas import AssetStatus, AssetType, ChatMessageResponse, ChatRequest
from app.models.tables import (
    Asset,
    Composition,
    CompositionVersion,
    Conversation,
    ExportJob,
    MediaJob,
    Message,
    MessageFeedback,
    Output,
    Project,
    SourceSnapshot,
    User,
)
from app.platform.conversation_context import find_conversation
from app.providers import storage
from app.providers.llm.base import ToolCall, ToolGeneration
from test.core.test_compositions import _project, _user


class _ScriptedClient:
    model = "test-eval-model-v1"
    capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=False)

    def __init__(self, generations: list[ToolGeneration]):
        self._generations = list(generations)
        self.calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        assert self._generations, "Unexpected extra LLM iteration"
        return self._generations.pop(0)


def _api_client(database, user: User):
    async def _override_db():
        async with database() as session:
            yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_required] = _override_user
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


# ---------------------------------------------------------------------------
# H1: create_video native motion_blocks + style_preset + transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_h1_create_video_native_motion_blocks_with_style_and_transitions(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)

    with pytest.raises(ValidationError):
        CreateVideoArgs(name="Empty work")

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner, project_id=project_id, title="Project chat")
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "做一个 3 幕 15 秒动效短片")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(
            project=project,
            conversation_id=conv.id,
            turn_id=opening.id,
            text=opening.content,
        )

    args = CreateVideoArgs(
        name="Rookie Cut Kinetic Promo",
        style_preset="vox_editorial",
        motion_blocks=[
            {
                "block_id": "statement_hook",
                "duration_seconds": 5.0,
                "props": {"headline": "Cut Videos by Chat", "subheadline": "Zero timeline friction"},
                "transition_after": "whip_pan",
                "transition_duration_seconds": 0.5,
            },
            {
                "block_id": "metric_grid",
                "duration_seconds": 5.0,
                "props": {
                    "title": "Real Speed",
                    "items": [
                        {"label": "Draft Time", "value": "3s"},
                        {"label": "Edit Time Saved", "value": "85%"},
                    ],
                },
                "transition_after": "crossfade",
                "transition_duration_seconds": 0.4,
            },
            {
                "block_id": "closing_cta",
                "duration_seconds": 5.0,
                "props": {"brand_name": "Rookie Cut", "tagline": "Ship faster today"},
            },
        ],
    )

    async with database() as db:
        with bind_progress("create-mg-1", None):
            result = await create_video(db, turn, args)

    assert result["saved"] is True
    assert result["version"] == 1
    assert result["duration_seconds"] == pytest.approx(15.0)
    assert len(result["motion_blocks"]) == 3
    assert [b["block_id"] for b in result["motion_blocks"]] == [
        "statement_hook",
        "metric_grid",
        "closing_cta",
    ]
    # H4 check: composition_id full + prefixes registered immediately after create_video
    cid = result["composition_id"]
    assert cid in turn._editor_labels
    assert cid[:8] in turn._editor_labels
    assert cid[:12] in turn._editor_labels

    async with database() as db:
        saved = await db.get(CompositionVersion, UUID(result["version_id"]))
        content = content_of(saved)
        assert content.settings.style is not None
        assert content.settings.style.preset_id == "vox_editorial"
        assert len(content.scenes) == 3
        assert len(content.timeline.transitions) == 2
        assert content.timeline.transitions[0].kind == "whip_pan"
        assert content.timeline.transitions[1].kind == "crossfade"


# ---------------------------------------------------------------------------
# H2: insert_motion_block seamless timeline extension
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_h2_insert_motion_block_auto_extends_timeline_and_rejects_large_gap(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner, project_id=project_id)
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "Create and extend")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(
            project=project,
            conversation_id=conv.id,
            turn_id=opening.id,
            text=opening.content,
        )
        with bind_progress("create-base", None):
            created = await create_video(
                db,
                turn,
                CreateVideoArgs(
                    name="Base 5s",
                    motion_blocks=[
                        {
                            "block_id": "statement_hook",
                            "duration_seconds": 5.0,
                            "props": {"headline": "Act 1"},
                        }
                    ],
                ),
            )
        base = {
            "composition_id": created["composition_id"],
            "composition_version_id": created["version_id"],
            "content_digest": created["content_digest"],
        }

        # Reject disconnected empty gap > 2s past end (5s + 2s = 7s; 10s fails)
        with pytest.raises(ValueError, match="2 seconds"):
            await edit_clip(
                db,
                name="insert_motion_block",
                project=project,
                opening_id=opening.id,
                conversation_id=conv.id,
                call_id="insert-gap-bad",
                base=base,
                args=InsertMotionBlockArgs(
                    block_id="closing_cta",
                    start_seconds=10.0,
                    end_seconds=15.0,
                    props={"brand_name": "Rookie Cut", "tagline": "Too far"},
                ),
                inspected_version=created["version_id"],
            )

        # Seamlessly append 5s..10s past original 5s duration
        extended = await edit_clip(
            db,
            name="insert_motion_block",
            project=project,
            opening_id=opening.id,
            conversation_id=conv.id,
            call_id="insert-extend-ok",
            base=base,
            args=InsertMotionBlockArgs(
                block_id="closing_cta",
                start_seconds=5.0,
                end_seconds=10.0,
                props={"brand_name": "Rookie Cut", "tagline": "Extended cleanly"},
            ),
            inspected_version=created["version_id"],
        )

    assert extended["version"] == 2
    assert extended["timeline_duration_seconds"] == pytest.approx(10.0)
    assert extended["extended_timeline"] is True
    async with database() as db:
        v2 = await db.get(CompositionVersion, UUID(extended["version_id"]))
        content = content_of(v2)
        assert len(content.scenes) == 2
        assert max(s.range.end for s in content.scenes) == 10 * content.settings.timebase


# ---------------------------------------------------------------------------
# H3: generate_sfx atomic place_at_seconds & non-placed next_step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_h3_generate_sfx_atomic_placement_and_unplaced_next_step(database, monkeypatch, tmp_path):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.editor_media.AsyncSessionLocal", database)
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    monkeypatch.setattr(settings, "s3_public_url", "http://127.0.0.1:8000/_local_storage")

    owner = await _user(database)
    project_id = await _project(database, owner)

    async def _fake_synthesize(*, owner_id, project_id, recipe_id, params, seed):
        import hashlib

        snap_id = uuid4()
        key = f"sfx/{snap_id}.wav"
        digest = hashlib.sha256(snap_id.bytes).hexdigest()
        await storage.save(key, b"RIFF0000WAVEfmt ", content_type="audio/wav")
        async with database() as sdb:
            snap = SourceSnapshot(
                id=snap_id,
                owner_id=owner_id,
                origin_project_id=project_id,
                kind="audio",
                digest=digest,
                storage_key=key,
                duration_ticks=90000,  # 1.0s at SOURCE_TIMEBASE (90000)
                meta={
                    "content_type": "audio/wav",
                    "origin": {
                        "kind": "sound_recipe",
                        "recipe_id": recipe_id,
                        "params": params,
                        "seed": seed,
                    },
                },
            )
            sdb.add(snap)
            await sdb.commit()
        return {
            "snapshot": {"snapshot_id": str(snap_id), "digest": digest},
            "media": {"storage_key": key, "digest": digest, "duration_seconds": 1.0},
            "analysis": {"analysis_digest": f"ana_{snap_id.hex[:8]}", "peaks": [0.7]},
            "cache_hit": False,
            "sound_recipe": {
                "recipe_id": recipe_id,
                "recipe_version": 2,
                "params": params,
                "seed": seed,
                "spec_sha256": f"spec_{snap_id.hex[:12]}",
            },
            "acoustics": {"duration_ms": 1000, "peak_offset_ms": 120, "peak_dbfs": -2.1},
        }

    async def _fake_playback_item(_db, _project, _role, result, _request):
        return {
            "snapshot_id": result["snapshot"]["snapshot_id"],
            "digest": result["snapshot"]["digest"],
            "duration_seconds": 1.0,
            "analysis_digest": result["analysis"]["analysis_digest"],
            "peaks": [0.7],
        }

    monkeypatch.setattr("app.tools.video.sfx_synthesis.synthesize_project_sfx", _fake_synthesize)
    monkeypatch.setattr("app.chat.editor_media.playback_item", _fake_playback_item)

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner, project_id=project_id)
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "加个转场音效")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(
            db=db,
            user_id=owner,
            project=project,
            conversation_id=conv.id,
            turn_id=opening.id,
            text=opening.content,
            on_row_append=None,
        )
        with bind_progress("create-for-sfx", None):
            created = await create_video(
                db,
                turn,
                CreateVideoArgs(
                    name="SFX Base",
                    motion_blocks=[
                        {
                            "block_id": "statement_hook",
                            "duration_seconds": 6.0,
                            "props": {"headline": "Hello"},
                        }
                    ],
                ),
            )
        comp = await db.get(Composition, UUID(created["composition_id"]))
        ver = await db.get(CompositionVersion, UUID(created["version_id"]))

        # 1) Without place_at_seconds -> placed=False + next_step
        with bind_progress("sfx-unplaced", None):
            obs_unplaced = await execute_generate_sfx(
                turn, GenerateSfxArgs(recipe_id="whoosh"), comp, ver
            )
        import json

        data_unplaced = json.loads(obs_unplaced.text)
        assert obs_unplaced.ok is True
        assert obs_unplaced.version_saved is False
        assert data_unplaced["placed"] is False
        assert "insert_audio" in data_unplaced["next_step"]

        # 2) With place_at_seconds -> atomic placement onto effect track!
        with bind_progress("sfx-placed", None):
            obs_placed = await execute_generate_sfx(
                turn,
                GenerateSfxArgs(recipe_id="impact", place_at_seconds=2.5, gain_db=-10.0),
                comp,
                ver,
            )
        data_placed = json.loads(obs_placed.text)
        assert obs_placed.ok is True
        assert obs_placed.version_saved is True
        assert data_placed["placed"] is True
        assert data_placed["version"] == 2
        assert data_placed["start_seconds"] == pytest.approx(2.5)
        assert data_placed["end_seconds"] == pytest.approx(3.5)
        assert turn._video_base_ref["composition_version_id"] == data_placed["version_id"]

        v2 = await db.get(CompositionVersion, UUID(data_placed["version_id"]))
        effect_clips = [
            c
            for t in content_of(v2).timeline.tracks
            if t.kind == "audio" and t.role == "effect"
            for c in t.clips
        ]
        assert len(effect_clips) == 1
        assert effect_clips[0].object.gain_db == pytest.approx(-10.0)


# ---------------------------------------------------------------------------
# H4 + H5: composition_id redaction, metric_grid guidance, local:// storage
# ---------------------------------------------------------------------------


def test_h4_h5_redaction_catalog_guidance_and_local_storage(tmp_path, monkeypatch):
    turn = SimpleNamespace()
    comp_id = UUID("27c839ec-1111-4222-8333-444455556666")
    ver_id = UUID("88aa99bb-1111-4222-8333-444455556666")
    _remember_labels(turn, [], ver_id, "abcdef1234567890", 1, composition_id=comp_id)

    leaked = f"已为你创建作品 `27c839ec`（完整 ID {comp_id}），当前版本 `88aa99bb`。"
    redacted = project_editor_reply(leaked, turn._editor_labels, "帮我做个视频")
    assert "27c839ec" not in redacted
    assert str(comp_id) not in redacted
    assert "88aa99bb" not in redacted
    assert "当前作品" in redacted
    assert "第 1 版" in redacted

    # version_present wires project_reply
    assembly = assemble_video_round({
        "tools": intent_router.tools,
        "snapshot": ContextSnapshot("empty"),
        "user_text": "帮我做个视频",
        "version_saved": True,
        "editor_labels": turn._editor_labels,
    })
    assert assembly.stage == "version_present"
    assert assembly.project_reply is not None
    assert "27c839ec" not in assembly.project_reply("组合 27c839ec 已保存")

    # H5: metric_grid unit guidance in catalog & schema
    assert "items[].value" in MOTION_BLOCK_CATALOG["metric_grid"]["desc"]
    assert "items[].value" in InsertMotionBlockArgs.model_fields["props"].description


@pytest.mark.asyncio
async def test_h5_local_storage_adapter_roundtrip_and_loopback_route(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    monkeypatch.setattr(settings, "s3_public_url", "http://testserver/_local_storage")

    key = "test-user/sfx/demo.wav"
    await storage.save(key, b"hello-local-audio", content_type="audio/wav")
    assert await storage.exists(key) is True
    assert await storage.size(key) == len(b"hello-local-audio")
    assert await storage.read(key) == b"hello-local-audio"
    assert key in await storage._list_keys("test-user/sfx/")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(f"/_local_storage/{key}")
        assert resp.status_code == 200
        assert resp.content == b"hello-local-audio"

        put_resp = await client.put("/_local_storage/test-user/put.txt", content=b"uploaded")
        assert put_resp.status_code == 200
        assert await storage.read("test-user/put.txt") == b"uploaded"

    await storage.delete(key)
    assert await storage.exists(key) is False

    # Disabled cleanly when s3_endpoint_url is https://
    monkeypatch.setattr(settings, "s3_endpoint_url", "https://tos-example.invalid")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/_local_storage/test-user/put.txt")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# update_steps: parallel batching, sanitization, live frames, and persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_steps_parallel_batch_sanitization_and_persistence(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.project_context.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.conversation_context.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)

    # Pure projector & sanitization test
    sanitized = sanitize_steps([
        {"title": "处理 clp_abc123 与 550e8400-e29b-41d4-a716-446655440000 画面", "status": "in_progress"},
        {"title": "调用 update_steps 更新进度", "status": "pending"},
    ])
    assert sanitized is not None
    assert "clp_abc123" not in sanitized[0]["title"]
    assert "550e8400" not in sanitized[0]["title"]
    assert "update_steps" not in sanitized[1]["title"]

    finalized = finalize_steps(sanitized, completed=True)
    assert finalized[0]["status"] == "done"
    assert finalized[1]["status"] == "pending"

    projector = ActivityProjector(intent_router.tools)
    assert projector.name_known("update_steps") == []
    emitted = projector.feed_event(
        ReadExecuting(
            tool_name="update_steps",
            call_id="c1",
            params=SimpleNamespace(steps=sanitized),
        )
    )
    assert len(emitted) == 1
    assert emitted[0].kind == KIND_STEPS
    assert emitted[0].activity_id == "__steps__"
    assert frame_persistence(emitted[0]) is None
    assert projector.latest_steps() == sanitized

    # Full run_plan_turn test: parallel update_steps + list_project_media -> persisted intent["steps"] & eval_meta
    client = _ScriptedClient([
        ToolGeneration(
            content="",
            tool_calls=[
                ToolCall(
                    id="call_steps_1",
                    name="update_steps",
                    arguments={
                        "steps": [
                            {"title": "盘点项目素材", "status": "in_progress"},
                            {"title": "编排三幕短片", "status": "pending"},
                            {"title": "配齐转场音效", "status": "pending"},
                        ]
                    },
                ),
                ToolCall(id="call_media_1", name="list_project_media", arguments={}),
            ],
        ),
        ToolGeneration(
            content="素材已盘点完毕，可以开始制作。",
            tool_calls=[],
        ),
    ])
    monkeypatch.setattr(intent_router, "client", client)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: client)

    events = []
    live_frames = []
    turn_projector = ActivityProjector(intent_router.tools)

    async def on_loop_event(ev):
        events.append(ev)
        if not isinstance(ev, (BatchDeclared, BatchMember)):
            live_frames.extend(turn_projector.feed_event(ev))

    async def on_tool_call(name):
        live_frames.extend(turn_projector.name_known(name))

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner, project_id=project_id, ui_language="zh")
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "先盘点素材再做三幕短片")
        opening.turn_state = "in_flight"
        await db.commit()

        assistant_msg, _ = await run_plan_turn(
            db,
            owner,
            conv,
            project,
            ChatRequest(project_id=project_id, message=opening.content),
            recent=[opening],
            turn_id=opening.id,
            on_tool_call=on_tool_call,
            on_loop_event=on_loop_event,
        )
        await db.commit()

    # update_steps excluded from BatchDeclared
    declared = [e for e in events if isinstance(e, BatchDeclared)]
    for d in declared:
        assert all(m.tool_name != "update_steps" for m in d.members)

    # Live SSE steps frame emitted
    step_frames = [f for f in live_frames if f.kind == KIND_STEPS]
    assert len(step_frames) == 1
    assert len(step_frames[0].steps) == 3

    # Persisted on assistant Message.intent["steps"] (in_progress promoted to done) and eval_meta stored
    assert assistant_msg is not None
    assert assistant_msg.intent["steps"][0]["status"] == "done"
    assert assistant_msg.intent["eval_meta"]["model_name"] == "test-eval-model-v1"
    assert len(assistant_msg.intent["eval_meta"]["system_prompt_sha256"]) == 64

    # Serialized ChatMessageResponse exposes steps and hides eval_meta
    serialized = ChatMessageResponse.model_validate(assistant_msg)
    assert serialized.steps is not None and len(serialized.steps) == 3
    assert "eval_meta" not in (serialized.intent or {})


# ---------------------------------------------------------------------------
# Project 1:N Conversation + /compact + message_feedback + /workbench
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_conversation_compact_feedback_and_workbench_api(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    owner_id = await _user(database)
    other_id = await _user(database)
    project_id = await _project(database, owner_id)

    async with database() as db:
        owner = await db.get(User, owner_id)
        other = await db.get(User, other_id)

    try:
        async with _api_client(database, owner) as client:
            # Create 2 conversations under the same project
            r1 = await client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Project chat"})
            assert r1.status_code == 201
            c1 = r1.json()
            c1_id = UUID(c1["id"])

            r2 = await client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Alt Cut Thread"})
            assert r2.status_code == 201
            c2 = r2.json()
            c2_id = UUID(c2["id"])

            # List conversations: returns both, ordered by updated_at DESC, never MultipleResultsFound
            rl = await client.get(f"/api/v1/projects/{project_id}/conversations")
            assert rl.status_code == 200
            listed = rl.json()
            assert len(listed) == 2
            assert {item["id"] for item in listed} == {str(c1_id), str(c2_id)}

            # GET /chat/conversation without conversation_id picks latest cleanly (no MultipleResultsFound)
            rc_default = await client.get(f"/api/v1/chat/conversation?project_id={project_id}")
            assert rc_default.status_code == 200
            assert rc_default.json()["id"] in {str(c1_id), str(c2_id)}

            # GET /chat/conversation with explicit conversation_id selects exact thread
            rc1 = await client.get(f"/api/v1/chat/conversation?project_id={project_id}&conversation_id={c1_id}")
            assert rc1.status_code == 200
            assert rc1.json()["id"] == str(c1_id)

            # Auto-title default "Project chat" on first user message via prepare_chat_turn
            async with database() as db:
                prep = await prepare_chat_turn(
                    db,
                    owner_id,
                    ChatRequest(
                        project_id=project_id,
                        conversation_id=c1_id,
                        message="帮我把首页产品亮点做成 15 秒宣传片",
                    ),
                )
                assert prep.conversation_id == c1_id
                assert prep.conversation.title.startswith("帮我把首页产品亮点")

                # Add assistant reply + activity row + forensics row on c1
                act_row = await _create_message(
                    db,
                    c1_id,
                    "assistant",
                    "",
                    turn_id=prep.user_message.id,
                    intent={
                        "type": "activity",
                        "frame": {
                            "activity_id": "act-1",
                            "kind": "read",
                            "status": "completed",
                            "key": "chat.activity.createVideoDone",
                            "duration_ms": 420,
                        },
                    },
                )
                assert act_row is not None
                # Also seed an activity_forensics row and a user intent lacking "type"
                # (regression guard for PostgreSQL three-valued NULL NOT IN logic).
                prep.user_message.intent = {
                    "editor_commits": [
                        {"request": "prior-req-id", "tool": "create_video", "fingerprint": "prior-fp"}
                    ]
                }
                await _create_message(
                    db,
                    c1_id,
                    "assistant",
                    "",
                    turn_id=prep.user_message.id,
                    intent={
                        "type": "activity_forensics",
                        "ref": str(prep.user_message.id),
                        "rejections": [],
                    },
                )
                asst_msg = await _create_message(
                    db,
                    c1_id,
                    "assistant",
                    "已为你生成 15 秒三幕宣传片初稿。",
                    turn_id=prep.user_message.id,
                    intent={
                        "steps": [{"title": "生成三幕初稿", "status": "done"}],
                        "eval_meta": {
                            "model_name": "test-model",
                            "system_prompt_sha256": "a" * 64,
                            "interaction_policy_version": "interaction_constitution.v2",
                            "assembled_context_excerpt": "{\"works\": []}",
                        },
                    },
                )
                prep.user_message.turn_state = "settled"
                await db.commit()
                asst_id = asst_msg.id
                user_msg_id = prep.user_message.id

            # Verify message_count on BOTH GET /projects/{id}/conversations AND PATCH /chat/conversations/{id}:
            # c1 has 2 visible messages (user w/ non-null intent lacking "type" + assistant w/ eval_meta/policy)
            # and 2 internal rows (activity + activity_forensics) that must be excluded -> exact count == 2.
            rl_after = await client.get(f"/api/v1/projects/{project_id}/conversations")
            assert rl_after.status_code == 200
            by_id_after = {item["id"]: item for item in rl_after.json()}
            assert by_id_after[str(c1_id)]["message_count"] == 2
            assert by_id_after[str(c2_id)]["message_count"] == 0

            r_patch_c1 = await client.patch(
                f"/api/v1/chat/conversations/{c1_id}",
                json={"title": "Renamed Primary Cut"},
            )
            assert r_patch_c1.status_code == 200
            assert r_patch_c1.json()["title"] == "Renamed Primary Cut"
            assert r_patch_c1.json()["message_count"] == 2

            # Rename conversation c2 via PATCH
            r_patch = await client.patch(
                f"/api/v1/chat/conversations/{c2_id}",
                json={"title": "Deep Dark Cut"},
            )
            assert r_patch.status_code == 200
            assert r_patch.json()["title"] == "Deep Dark Cut"
            assert r_patch.json()["message_count"] == 0

            # find_conversation with multiple rows never raises
            async with database() as db:
                found = await find_conversation(db, owner_id, project_id)
                assert found is not None

            # Compact conversation c1
            r_compact = await client.post(f"/api/v1/chat/conversations/{c1_id}/compact")
            assert r_compact.status_code == 200
            compact_body = r_compact.json()
            assert compact_body["conversation_id"] == str(c1_id)
            assert compact_body["compacted_through_seq"] >= 3
            assert compact_body["message_count"] >= 2
            assert compact_body["summary"]

            # Verify conversation_messages skips old messages while preserving newer ones
            async with database() as db:
                conv1_row = await db.get(Conversation, c1_id)
                compact_meta = conv1_row.context["compact_summary"]
                new_user = await _create_message(db, c1_id, "user", "第二轮微调：换成深色风格")
                await db.commit()
                all_msgs = list(
                    await db.scalars(
                        select(Message).where(Message.conversation_id == c1_id).order_by(Message.seq)
                    )
                )
                projected_dialogue = conversation_messages(all_msgs, compact_summary=compact_meta)
                assert len(projected_dialogue) == 1
                assert projected_dialogue[0]["content"] == "第二轮微调：换成深色风格"
                assert new_user is not None

            # Feedback: 400 on user message
            r_fb_user = await client.post(
                f"/api/v1/chat/messages/{user_msg_id}/feedback",
                json={"rating": "good"},
            )
            assert r_fb_user.status_code == 400

            # Feedback: good -> bad upsert with reason/tags and frozen context_snapshot
            r_fb_good = await client.post(
                f"/api/v1/chat/messages/{asst_id}/feedback",
                json={"rating": "good"},
            )
            assert r_fb_good.status_code == 200
            assert r_fb_good.json()["feedback"]["rating"] == "good"

            r_fb_bad = await client.post(
                f"/api/v1/chat/messages/{asst_id}/feedback",
                json={"rating": "bad", "reason": "节奏略快", "tags": ["pacing", "copy"]},
            )
            assert r_fb_bad.status_code == 200
            fb_payload = r_fb_bad.json()["feedback"]
            assert fb_payload["rating"] == "bad"
            assert fb_payload["reason"] == "节奏略快"
            assert fb_payload["tags"] == ["pacing", "copy"]

            async with database() as db:
                fb_rows = list(await db.scalars(select(MessageFeedback)))
                assert len(fb_rows) == 1
                snap = fb_rows[0].context_snapshot
                assert snap["user_prompt"]["content"] == "帮我把首页产品亮点做成 15 秒宣传片"
                assert snap["assistant_reply"]["content"] == "已为你生成 15 秒三幕宣传片初稿。"
                assert snap["prompt_meta"]["system_prompt_sha256"] == "a" * 64
                assert len(snap["tool_trace"]["activities"]) == 1
                assert snap["compact_summary"]["summary"] == compact_body["summary"]

            # GET messages returns full history + compact_summary + feedback + steps (no eval_meta)
            r_msgs = await client.get(f"/api/v1/chat/conversations/{c1_id}/messages")
            assert r_msgs.status_code == 200
            msgs_body = r_msgs.json()
            assert msgs_body["compact_summary"]["compacted_through_seq"] == compact_body["compacted_through_seq"]
            rated_item = next(m for m in msgs_body["items"] if m["id"] == str(asst_id))
            assert rated_item["feedback"]["rating"] == "bad"
            assert rated_item["steps"] == [{"title": "生成三幕初稿", "status": "done"}]
            assert "eval_meta" not in (rated_item.get("intent") or {})

            # Feedback delete when rating=None
            r_fb_clear = await client.post(
                f"/api/v1/chat/messages/{asst_id}/feedback",
                json={"rating": None},
            )
            assert r_fb_clear.status_code == 200
            assert r_fb_clear.json()["feedback"] is None
            async with database() as db:
                assert await db.scalar(select(func.count()).select_from(MessageFeedback)) == 0

            # Seed composition + asset + active export/media jobs for /workbench
            async with database() as db:
                project = await db.get(Project, project_id)
                turn_wb = SimpleNamespace(
                    project=project,
                    conversation_id=c1_id,
                    turn_id=user_msg_id,
                    text="Create workbench work",
                )
                # reopen turn briefly for create_video
                opening_row = await db.get(Message, user_msg_id)
                opening_row.turn_state = "in_flight"
                await db.commit()
                with bind_progress("wb-create", None):
                    created_wb = await create_video(
                        db,
                        turn_wb,
                        CreateVideoArgs(
                            name="Workbench Film",
                            style_preset="institutional_dark",
                            motion_blocks=[
                                {
                                    "block_id": "statement_hook",
                                    "duration_seconds": 4.0,
                                    "props": {"headline": "Workbench Ready"},
                                }
                            ],
                        ),
                    )
                opening_row.turn_state = "settled"

                asset_proc = Asset(
                    user_id=owner_id,
                    project_id=project_id,
                    type=AssetType.IMAGE,
                    title="Hero Shot",
                    processing_status=AssetStatus.PROCESSING,
                )
                db.add(asset_proc)
                receipt_exp = await _create_message(db, c2_id, "assistant", "", turn_id=user_msg_id)
                receipt_med = await _create_message(db, c1_id, "assistant", "", turn_id=user_msg_id)
                db.add(
                    ExportJob(
                        id=uuid4(),
                        receipt_id=receipt_exp.id,
                        project_id=project_id,
                        version_id=UUID(created_wb["version_id"]),
                        render_spec={"family": "video"},
                        authorized_credits=2,
                        status="running",
                        attempt=1,
                    )
                )
                db.add(
                    MediaJob(
                        id=uuid4(),
                        receipt_id=receipt_med.id,
                        project_id=project_id,
                        kind="generate_image",
                        request={"prompt": "studio"},
                        authorized_credits=1,
                        status="queued",
                        attempt=0,
                    )
                )
                db.add(
                    Output(
                        id=uuid4(),
                        project_id=project_id,
                        type="video",
                        files={"video": "test/out.mp4"},
                        composition_id=UUID(created_wb["composition_id"]),
                        composition_version_id=UUID(created_wb["version_id"]),
                    )
                )
                await db.commit()

            # Check /workbench payload
            r_wb = await client.get(f"/api/v1/projects/{project_id}/workbench")
            assert r_wb.status_code == 200
            wb = r_wb.json()
            assert wb["project"]["id"] == str(project_id)
            assert len(wb["compositions"]) == 1
            assert wb["compositions"][0]["versions"][0]["style_preset"] == "institutional_dark"
            assert wb["compositions"][0]["versions"][0]["is_head"] is True
            assert len(wb["assets"]) == 1
            kinds = {j["kind"] for j in wb["active_jobs"]}
            assert kinds == {"export", "image", "asset_processing"}

        # Owner isolation: foreign user gets 404 on workbench, conversations, compact, feedback
        async with _api_client(database, other) as foreign_client:
            assert (await foreign_client.get(f"/api/v1/projects/{project_id}/workbench")).status_code == 404
            assert (await foreign_client.get(f"/api/v1/projects/{project_id}/conversations")).status_code == 404
            assert (await foreign_client.post(f"/api/v1/projects/{project_id}/conversations", json={})).status_code == 404
            assert (await foreign_client.patch(f"/api/v1/chat/conversations/{c1_id}", json={"title": "Hack"})).status_code == 404
            assert (await foreign_client.post(f"/api/v1/chat/conversations/{c1_id}/compact")).status_code == 404
            assert (await foreign_client.post(f"/api/v1/chat/messages/{asst_id}/feedback", json={"rating": "bad"})).status_code == 404
    finally:
        app.dependency_overrides.clear()
