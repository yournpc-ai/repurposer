"""Layer 1A Chat-Origin: Project 1:N Conversation, shared assets, /compact pruning, message_feedback Eval snapshot, and /workbench."""

from __future__ import annotations
import pytest

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


from test.support.db_helpers import _project, _user


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



# --- Flagship Real HTTP Shared Project Assets Across Multiple Conversations ---


@pytest.mark.asyncio
async def test_shared_project_assets_visible_across_multiple_conversations_via_chat_api(
    database, monkeypatch
):
    """Project 1:N Conversation: two conversations on one Project share project assets,
    each runs real POST /api/v1/chat independently without MultipleResultsFound, and
    reports exact per-conversation message_count."""
    from test.support.db_helpers import ScriptedToolClient, bind_test_database, full_api_client

    bind_test_database(monkeypatch, database)

    owner_id = await _user(database)
    project_id = await _project(database, owner_id, title="Shared Asset Multi-Conv")
    async with database() as db:
        owner = await db.get(User, owner_id)
        shared_asset = Asset(
            user_id=owner_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            title="Shared Hero.png",
            file_url="uploads/shared-hero.png",
            processing_status=AssetStatus.COMPLETED,
        )
        db.add(shared_asset)
        await db.commit()
        shared_asset_id = str(shared_asset.id)

    try:
        async with full_api_client(database, owner) as client:
            c1 = (await client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Cut A"})).json()
            c2 = (await client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Cut B"})).json()

            for conv_id, reply_text in [(c1["id"], "Cut A 已看到共享素材。"), (c2["id"], "Cut B 也看到同一份共享素材。")]:
                scripted = ScriptedToolClient(
                    [
                        ToolGeneration(
                            content=reply_text,
                            tool_calls=[ToolCall(id=f"ans_{conv_id[:6]}", name="answer", arguments={"pending_disposition": "none"})],
                        )
                    ]
                )
                monkeypatch.setattr(intent_router, "client", scripted)
                monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: scripted)
                r = await client.post(
                    "/api/v1/chat",
                    json={"project_id": str(project_id), "conversation_id": conv_id, "message": "盘点项目共享素材"},
                )
                assert r.status_code == 201, r.text
                assert r.json()["conversation_id"] == conv_id

            listed = (await client.get(f"/api/v1/projects/{project_id}/conversations")).json()
            by_id = {row["id"]: row for row in listed}
            assert by_id[c1["id"]]["message_count"] == 2
            assert by_id[c2["id"]]["message_count"] == 2

            wb = (await client.get(f"/api/v1/projects/{project_id}/workbench")).json()
            assert any(a["id"] == shared_asset_id for a in wb["assets"])
    finally:
        app.dependency_overrides.clear()
