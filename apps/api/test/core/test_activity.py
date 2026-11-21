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
from app.pipeline.lifecycle import confirmation_need
from app.tools.video.design import _ready_web_pages


def test_read_activity_opens_at_execute_after_the_interim_prose_seat():
    projector = ActivityProjector(_video_material_tools())

    assert projector.name_known("analyze_brand") == []
    assert projector.open_activity() is None
    executing = projector.feed_event(ReadExecuting(tool_name="analyze_brand", params=object()))
    assert projector.open_activity() is not None
    frames = [
        *executing,
        *projector.feed_event(ReadAccepted(tool_name="analyze_brand", ok=True)),
    ]

    assert [(frame.status, frame.key) for frame in frames] == [
        ("active", "chat.activity.brandAnalyze"),
        ("completed", "chat.activity.brandAnalyzeDone"),
    ]


@pytest.mark.parametrize(("params", "key"), [
    ({"material_urls": ["https://www.legitevi.com/en"]}, "viewWebPage"),
    ({"material_music_ids": [uuid4()]}, "videoMaterials"),
    ({"material_urls": ["https://www.legitevi.com/en"], "material_music_ids": [uuid4()]}, "videoMaterials"),
])
def test_material_activity_matches_validated_inputs(params, key):
    projector = ActivityProjector(_video_material_tools())
    name = "prepare_video_materials"
    assert projector.name_known(name) == []
    active, = projector.feed_event(ReadExecuting(name, PrepareVideoMaterialsArgs(**params)))
    done, = projector.feed_event(ReadAccepted(tool_name=name, ok=True))
    assert active.key == f"chat.activity.{key}"
    assert done.key == f"chat.activity.{key}Done"
    assert active.activity_id == done.activity_id


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


def test_unquotable_confirmation_follows_auto_and_ask_preferences():
    automatic = confirmation_need(
        execution="auto", credits="auto", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    execution_ask = confirmation_need(
        execution="ask", credits="auto", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    credits_ask = confirmation_need(
        execution="auto", credits="ask", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    above_guardrail = confirmation_need(
        execution="auto", credits="auto", quote_high=5001,
        unquotable=False, always_confirm_above=5000,
    )

    assert automatic.requires_confirmation is False
    assert execution_ask.requires_confirmation is True
    assert execution_ask.reason == "unquotable"
    assert credits_ask.requires_confirmation is True
    assert credits_ask.reason == "unquotable"
    assert above_guardrail.requires_confirmation is True
    assert above_guardrail.reason == "above_guardrail"


@pytest.mark.parametrize("ok", [False, True])
def test_mixed_material_steps_update_one_row_and_ignore_stale_progress(ok):
    from app.agents.tool_loop import ToolProgress

    projector = ActivityProjector(_video_material_tools())
    name = "prepare_video_materials"
    projector.name_known(name)
    params = PrepareVideoMaterialsArgs(material_urls=["https://www.legitevi.com/en"], material_music_ids=[uuid4()])
    start, = projector.feed_event(ReadExecuting(name, params, "call-1"))
    web, = projector.feed_event(ToolProgress("call-1", "view_webpage"))
    assert not projector.feed_event(ToolProgress("call-1", "view_webpage"))
    assert not projector.feed_event(ToolProgress("other", "import_music"))
    music, = projector.feed_event(ToolProgress("call-1", "import_music"))
    end, = projector.feed_event(ReadAccepted(name, ok))
    assert {f.activity_id for f in (start, web, music, end)} == {start.activity_id}
    assert [f.key for f in (start, web, music)] == [
        "chat.activity.videoMaterials", "chat.activity.viewWebPage", "chat.activity.importMusic",
    ]
    assert end.key == ("chat.activity.videoMaterialsDone" if ok else music.key)
    assert end.status == ("completed" if ok else "failed")
    assert not projector.feed_event(ToolProgress("call-1", "view_webpage"))


def test_all_chat_tool_registries_declare_a_presentation():
    from app.agents.candidate_correction import correction_tool
    from app.chat.conversation_context import conversation_context_tool
    from app.chat.intent import intent_router
    from app.chat.trigger_turn import delivery_agent, trigger_agent

    tools = [t for agent in (intent_router, trigger_agent, delivery_agent) for t in agent.tools]
    for tool in [*tools, conversation_context_tool(), correction_tool()]:
        assert tool.presentation is not None, tool.name
        assert tool.presentation.kind == "native" or tool.presentation.active_key, tool.name


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
