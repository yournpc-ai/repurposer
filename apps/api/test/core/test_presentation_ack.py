from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select

from app.chat.routes import chat_router
from app.chat.video_turn_seats import stamp_video_presentation
from app.dependencies import get_current_user_required, get_db
from app.editing.service import video_version_read
from app.models.tables import Conversation, CreditTransaction, ExportJob, MediaJob, Message, Project, WorkflowRun
from test.core.test_compositions import _create, _project, _snapshots, _user


@pytest.mark.asyncio
async def test_presentation_ack_pins_display_and_never_submits_production(database):
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    app = FastAPI()
    app.include_router(chat_router, prefix="/chat")
    async def session():
        async with database() as db:
            yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=owner)
    rows = []
    async with database() as db:
        conversation = Conversation(user_id=owner, project_id=pid)
        db.add(conversation)
        await db.flush()
        project = await db.get(Project, pid)
        for seq in (1, 2):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        url = f"/chat/messages/{current}/video-presentation"
        assert (await client.post(url, json=earlier)).status_code == 409
        assert (await client.post(url, json={**latest, "presentation_digest": "invalid"})).status_code == 409
        assert (await client.post(f"/chat/messages/{old}/video-presentation", json=earlier)).json() == {"accepted": False}
        for _ in range(2):
            response = await client.post(url, json=latest)
            assert response.status_code == 200 and response.json() == {"accepted": True}
    async with database() as db:
        for message_id, exact in rows:
            block, = (await db.get(Message, message_id)).blocks
            assert all(block[k] == value for k, value in exact.items())
            assert block["presentation_complete"] is True
        assert (await db.get(Project, pid)).pending_brief["video_presentation"]["presented_message_id"] == str(current)
        for table in (ExportJob, MediaJob, WorkflowRun, CreditTransaction):
            assert await db.scalar(select(func.count()).select_from(table)) == 0
