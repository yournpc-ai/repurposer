"""Chat activity and questions — infra contracts."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agents.tool_loop import ReadAccepted, ReadExecuting
from app.chat.activity import ActivityProjector
from app.chat.service import append_activity_row, record_asset_activity
from app.chat.turn_tools import _video_material_tools
from app.models import database as database_module
from app.models.schemas import AssetStatus, AssetType, PrepareVideoMaterialsArgs
from app.models.tables import Asset, Conversation, Message, Project, User
from app.tools.video.design import _ready_web_pages

pytestmark = pytest.mark.infra


@pytest.mark.asyncio
async def test_late_asset_completion_reuses_the_originating_activity_row(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Late completion")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        await db.commit()
        turn_id = uuid4()
        db.add(Message(
            id=turn_id, conversation_id=conversation.id, role="user",
            content="make a promo", turn_id=turn_id, turn_state="settled", seq=1,
        ))
        row = await append_activity_row(db, conversation.id, {
            "activity_id": "prepare-materials-invocation",
            "kind": "read",
            "status": "completed",
            "key": "chat.activity.videoMaterialsDone",
        }, turn_id=turn_id)
        await db.commit()

        result = await record_asset_activity(
            db, user.id, project.id,
            status="completed", name="about-us", count=3, total=3,
            ref="child-page", duration_ms=53_000, asset_type="web_page",
            at=None, turn_id=str(turn_id),
        )
        await db.commit()

        assert result.id == row.id
        rows = list((await db.execute(
            select(Message).where(Message.intent["type"].astext == "activity")
        )).scalars().all())
        assert len(rows) == 1
        assert rows[0].intent["type"] == "activity"


@pytest.mark.asyncio
async def test_background_asset_completion_uses_the_same_activity_protocol(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Background completion")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        await db.commit()

        row = await record_asset_activity(
            db, user.id, project.id,
            status="completed", name="upload.mov", count=1, total=1,
            ref="asset-1", duration_ms=100, asset_type="video",
            at=None, turn_id=None,
        )
        await db.commit()

        assert row.intent["type"] == "activity"
        assert row.intent["frame"]["activity_id"] == "asset-reading:asset-1"
        assert row.intent["frame"]["kind"] == "read"


@pytest.mark.asyncio
async def test_chat_owned_asset_completion_without_a_row_adds_no_independent_activity(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Worker finishes first")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        await db.commit()

        result = await record_asset_activity(
            db, user.id, project.id,
            status="completed", name="early-page", count=1, total=1,
            ref="early-page", duration_ms=10, asset_type="web_page",
            at=None, turn_id=str(uuid4()),
        )

        assert result is None
        assert list((await db.execute(select(Message))).scalars().all()) == []


@pytest.mark.asyncio
async def test_ready_web_pages_waits_for_discovered_children(database):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Discovered children")
        db.add(project)
        await db.flush()
        parent = Asset(
            user_id=user.id, project_id=project.id, type=AssetType.WEB_PAGE,
            title="root", processing_status=AssetStatus.COMPLETED,
            meta={"capture_url": "https://example.com", "shots": [{"view_id": "v0"}]},
        )
        db.add(parent)
        await db.flush()
        child = Asset(
            user_id=user.id, project_id=project.id, type=AssetType.WEB_PAGE,
            title="child", processing_status=AssetStatus.PROCESSING,
            meta={"capture_url": "https://example.com/about", "discovered_from": str(parent.id)},
        )
        db.add(child)
        await db.commit()

        async def settle(_db, _project_id, *, asset_ids):
            current = await db.get(Asset, child.id)
            current.processing_status = AssetStatus.COMPLETED
            current.meta = {**current.meta, "shots": [{"view_id": "v1"}]}
            await db.commit()

        from app.tools.video import design as design_module
        original = design_module._await_captures_settled
        design_module._await_captures_settled = settle
        try:
            rows = await _ready_web_pages(
                db, project_id=project.id, owner_id=user.id, urls={"https://example.com"},
            )
        finally:
            design_module._await_captures_settled = original

        assert {asset.id for asset in rows} == {parent.id, child.id}


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_progress_survives_reload_and_settles_the_original_message(database, monkeypatch, cancel):
    import asyncio

    from app.agents.tool_loop import ToolProgress
    from app.chat.routes import _make_activity_persister, _make_loop_event_hook

    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Progress")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        conversation_id = conversation.id

    async def reload_frame():
        async with database() as db:
            row = (await db.scalars(select(Message).where(Message.conversation_id == conversation_id))).one()
            return row.id, row.intent["frame"]

    projector = ActivityProjector(_video_material_tools())
    queue = asyncio.Queue()
    append, mirror, cancel_open = _make_activity_persister(queue, projector, conversation_id)
    emit = _make_loop_event_hook(queue, projector, append, mirror)
    name = "prepare_video_materials"
    projector.name_known(name)
    params = PrepareVideoMaterialsArgs(material_urls=["https://www.legitevi.com/en"], material_music_ids=[uuid4()])
    await emit(ReadExecuting(name, params, "mixed"))
    row_id, first = await reload_frame()
    await emit(ToolProgress("mixed", "view_webpage"))
    await emit(ToolProgress("mixed", "import_music"))
    mid_id, mid = await reload_frame()
    assert (mid_id, mid["at"], mid["activity_id"]) == (row_id, first["at"], first["activity_id"])
    assert mid["key"] == "chat.activity.importMusic" and mid["status"] == "active"
    assert "settled_at" not in mid
    if cancel:
        await cancel_open()
    else:
        await emit(ReadAccepted(name))
    final_id, final = await reload_frame()
    assert final_id == row_id
    assert final["status"] == ("cancelled" if cancel else "completed")


@pytest.mark.asyncio
async def test_semantic_detail_persists_through_activity_row_lifecycle(database, monkeypatch):
    import asyncio

    from app.chat.editor import EDITOR_TOOLS, InsertMotionBlockArgs
    from app.chat.routes import _make_activity_persister, _make_loop_event_hook

    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Semantic Detail")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        conversation_id = conversation.id

    projector = ActivityProjector(EDITOR_TOOLS)
    queue = asyncio.Queue()
    append, mirror, _cancel = _make_activity_persister(queue, projector, conversation_id)
    emit = _make_loop_event_hook(queue, projector, append, mirror)

    projector.name_known("insert_motion_block")
    params = InsertMotionBlockArgs(
        block_id="data_chart", start_seconds=12.0, end_seconds=17.0, props={"title": "Revenue"}
    )
    await emit(ReadExecuting("insert_motion_block", params, "call-mb-1"))
    await emit(ReadAccepted("insert_motion_block", ok=True))

    async with database() as db:
        row = (await db.scalars(select(Message).where(Message.conversation_id == conversation_id))).one()
        frame = row.intent["frame"]
        assert frame["status"] == "completed"
        assert frame["detail"] == {"kind": "motion_block_insert", "block": "data_chart", "window": "12–17s"}
