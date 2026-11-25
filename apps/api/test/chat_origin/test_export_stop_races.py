"""Stop an export while the Chat SSE request is waiting for its durable job."""
import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import select

from app.chat import editor_media
from app.chat.intent import intent_router
from app.models.schemas import MediaInput
from app.models.tables import CreditTransaction, ExportJob, Message, Output, User, Wallet
from scripts.eval_chat_e2e import parse_sse_frames
from test.support.chat_http import tool
from test.support.db_helpers import (
    ScriptedToolClient, _create, _project, _snapshots, _user, bind_test_database, full_api_client,
)

pytestmark = [pytest.mark.chat_origin, pytest.mark.asyncio]


async def test_stop_queued_export_releases_hold_and_fences_delivery(database, monkeypatch):
    bind_test_database(monkeypatch, database)
    owner = await _user(database, settings={"confirm_execution": "auto", "confirm_credits": "auto"})
    project = await _project(database, owner)
    await _snapshots(database, owner)
    _, version, _ = await _create(database, owner, project)
    async with database() as db:
        user = await db.get(User, owner)
        db.add(Wallet(user_id=owner, balance=1000))
        await db.commit()

    # The renderer is the external boundary. The preview scope, export quote,
    # admission, hold and stop all go through the real application.
    media = MediaInput(type="video", mime="video/mp4", data_url="data:video/mp4;base64,AA==")
    monkeypatch.setattr("app.tools.video.preview.saved_preview_media", AsyncMock(return_value=(
        (media,), {"mp4_sha256": "a" * 64, "sample_seconds": [0], "audio_available_to_model": False},
    )))
    client = ScriptedToolClient([
        tool("preview_range", {"start_seconds": 0, "end_seconds": 1}),
        tool("export_video", {}),
        tool("answer", {}, "The export was stopped."),
    ], streaming=True)
    monkeypatch.setattr(intent_router, "client", client)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: client)
    admitted = asyncio.get_running_loop().create_future()
    release = asyncio.Event()
    original = editor_media.wait_for_media_result

    async def wait(receipt, **kwargs):
        admitted.set_result(receipt)
        await release.wait()
        return await original(receipt, **kwargs)

    monkeypatch.setattr(editor_media, "wait_for_media_result", wait)
    async with full_api_client(database, user) as http:
        async with asyncio.timeout(15):
            request = asyncio.create_task(http.post(
                "/api/v1/chat", json={"project_id": str(project), "message": "Preview and export this version as MP4."},
                headers={"Accept": "text/event-stream"},
            ))
            try:
                await asyncio.wait([request, admitted], return_when=asyncio.FIRST_COMPLETED)
                assert admitted.done(), (await request).text
                receipt = admitted.result()
                job_id = UUID(receipt.intent["export_job"])
                async with database() as db:
                    job = await db.get(ExportJob, job_id)
                    assert job.version_id == version.id and job.status == "queued"
                    hold = (await db.scalars(select(CreditTransaction.amount).where(
                        CreditTransaction.kind == "hold"))).one()
                    assert hold < 0
                for _ in range(2):
                    stopped = await http.post(f"/api/v1/chat/turns/{receipt.turn_id}/stop", json={})
                    assert stopped.status_code == 200 and stopped.json()["turn_state"] == "cancelled"
            finally:
                release.set()
                response = await request
    assert response.status_code == 200
    frames = parse_sse_frames(response.text)
    assert ("turn.started", {"turn_id": str(receipt.turn_id)}) in frames
    assert not any(event in {"turn.failed", "turn.completed"} for event, _ in frames)
    async with database() as db:
        assert (await db.get(ExportJob, job_id)).status == "cancelled"
        assert (await db.get(Message, receipt.turn_id)).turn_state == "cancelled"
        assert (await db.get(Message, receipt.id)).intent["media_result"]["charged_credits"] == 0
        assert await db.get(Output, job_id) is None
        assert (await db.get(Wallet, owner)).balance == 1000
        assert sorted(await db.execute(select(CreditTransaction.kind, CreditTransaction.amount))) == [
            ("hold", hold), ("release", -hold),
        ]
