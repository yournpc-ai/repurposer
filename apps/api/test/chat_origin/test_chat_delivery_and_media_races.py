"""Chat delivery and media races — chat origin contracts."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.chat import editor_media
from app.chat.video_turn_seats import stamp_video_presentation
from app.editing.service import video_version_read
from app.models.tables import (
    Conversation,
    CreditTransaction,
    ExportJob,
    MediaJob,
    Message,
    Project,
    User,
)
from test.support.chat_http import scripted_chat, tool
from test.support.db_helpers import _create, _project, _snapshots, _user, full_api_client

pytestmark = pytest.mark.chat_origin


@pytest.mark.parametrize("words", [
    'Record a voiceover saying "generate an image".',
    "Generate an image prompt for an amber circle.",
    "请生成一张图片的提示词。",
])
@pytest.mark.asyncio
async def test_unrequested_paid_image_uses_exact_quote(database, monkeypatch, words):
    from app.chat.editor import GenerateImageArgs

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, project_id)
        user = await db.get(User, owner)
        user.settings = {"confirm_execution": "auto", "confirm_credits": "never"}
        convo = Conversation(project_id=project.id, user_id=owner)
        db.add(convo)
        await db.commit()
        args = GenerateImageArgs(prompt="A small amber circle")
        _, frames = await scripted_chat(database, monkeypatch, owner, project_id, words,
            [tool("generate_image", args.model_dump(mode="json"), call_id="unrequested-image")],
            conversation_id=str(convo.id))
        terminal = frames[-1][1]
        receipt = await db.get(Message, UUID(terminal["assistant_message"]["id"]))
        assert receipt.question["options"][0]["id"] == "approve"
        assert receipt.intent["media_permission"]["quote"]["total"][1] > 0
        # Duplicate submission of the exact native call reuses the durable quote.
        turn = SimpleNamespace(project=project, user_id=owner, turn_id=UUID(terminal["user_message"]["id"]),
                               conversation_id=convo.id)
        replay = await editor_media.submit_editor_media(turn, "generate_image", args, None, None, "unrequested-image")
        assert replay.id == receipt.id
        async with full_api_client(database, user) as client:
            declined = await client.post(f"/api/v1/chat/messages/{receipt.id}/answer",
                                         json={"kind": "option", "option_id": "decline"})
            assert declined.status_code == 200, declined.text
        assert await db.scalar(select(func.count()).select_from(MediaJob)) == 0
        assert await db.scalar(select(func.count()).select_from(CreditTransaction).where(
            CreditTransaction.kind.in_(("capture", "hold")))) == 0


@pytest.mark.asyncio
async def test_existing_media_instruction_rejects_generation_before_any_receipt(database, monkeypatch):

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    owner = await _user(database)
    pid = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, pid)
        convo = Conversation(project_id=pid, user_id=owner)
        db.add(convo)
        await db.commit()
        words = "Edit the footage. No new media or export."
        llm, frames = await scripted_chat(database, monkeypatch, owner, pid, words, [tool("answer", {}, "Understood.")],
                                          conversation_id=str(convo.id))
        assert "generate_image" not in {t["function"]["name"] for t in llm.calls[0]["tools"]}
        opening = await db.get(Message, UUID(frames[-1][1]["user_message"]["id"]))
        turn = SimpleNamespace(project=project, user_id=owner, turn_id=opening.id, conversation_id=convo.id)
        assert not await db.scalar(select(Message.id).where(
            Message.turn_id == opening.id, Message.intent.has_key("editor_media"),
        ))
        assert await db.scalar(select(func.count()).select_from(MediaJob)) == 0
        assert await db.scalar(select(func.count()).select_from(CreditTransaction).where(
            CreditTransaction.kind.in_(("capture", "hold")),
        )) == 0


@pytest.mark.asyncio
async def test_presentation_ack_pins_display_and_never_submits_production(database, monkeypatch):
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    _, frames = await scripted_chat(database, monkeypatch, owner, pid, "Show the reviewed storyboard.",
                                    [tool("answer", {}, "Here is the storyboard.")])
    rows = []
    async with database() as db:
        conversation = await db.get(Conversation, UUID(frames[-1][1]["conversation_id"]))
        user = await db.get(User, owner)
        project = await db.get(Project, pid)
        for seq in (3, 4):
            _, version, _ = await _create(database, owner, pid)
            read = await video_version_read(db, owner_id=owner, version_id=version.id)
            shown = Message(conversation_id=conversation.id, role="assistant", content="Storyboard", seq=seq)
            db.add(shown)
            await db.flush()
            read["authorized_revision_message_id"] = str(uuid4())
            stamp_video_presentation(project, shown, read, production_requested=True)
            rows.append((shown.id, {"composition_version_id": str(version.id),
                                    "presentation_digest": read["presentation_digest"]}))
        await db.commit()

    (old, earlier), (current, latest) = rows
    async with full_api_client(database, user) as client:
        url = f"/api/v1/chat/messages/{current}/video-presentation"
        assert (await client.post(url, json=earlier)).status_code == 409
        assert (await client.post(url, json={**latest, "presentation_digest": "invalid"})).status_code == 409
        assert (await client.post(f"/api/v1/chat/messages/{old}/video-presentation", json=earlier)).json() == {"accepted": False}
        for _ in range(2):
            response = await client.post(url, json=latest)
            assert response.status_code == 200 and response.json() == {"accepted": True}
    async with database() as db:
        for message_id, exact in rows:
            block, = (await db.get(Message, message_id)).blocks
            assert all(block[k] == value for k, value in exact.items())
            assert block["presentation_complete"] is True
        assert (await db.get(Project, pid)).pending_brief["video_presentation"]["presented_message_id"] == str(current)
        for table in (ExportJob, MediaJob, CreditTransaction):
            assert await db.scalar(select(func.count()).select_from(table)) == 0
