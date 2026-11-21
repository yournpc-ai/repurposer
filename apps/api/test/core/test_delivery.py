"""Incident regressions against disposable Postgres; no user data or paid IO."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.database import Base
from app.models.tables import (
    Composition, CompositionVersion, CreditTransaction, Output, Project, User, Wallet,
    Conversation, Message,
)
from app.models.schemas import ProjectStatus, RenderStatus
from app.platform import billing

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def database():
    name = f"rep_settlement_test_{uuid4().hex[:12]}"
    server = settings.database_url.rsplit("/", 1)[0]
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(f"{server}/{name}")
    try:
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.connect() as c:
            await c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


async def owner(factory):
    async with factory() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        db.add(Wallet(user_id=user.id, balance=1000))
        await db.commit()
        return user.id


async def pinned_video_version(db, project):
    composition = Composition(
        owner_id=project.user_id, origin_project_id=project.id, name="delivery fixture",
    )
    db.add(composition)
    await db.flush()
    version = CompositionVersion(
        composition_id=composition.id,
        version=1,
        settings={},
        sources=[],
        scenes=[],
        timeline={"tracks": []},
        content_digest="c" * 64,
    )
    db.add(version)
    await db.flush()
    composition.current_version_id = version.id
    await db.flush()
    provenance = {
        "composition_id": str(composition.id),
        "composition_version_id": str(version.id),
        "content_digest": version.content_digest,
    }
    return composition, version, provenance


def pin_video_output(output, composition, version, provenance):
    output.composition_id = composition.id
    output.composition_version_id = version.id
    output.payload = {"composition_digest": version.content_digest}
    output.render_spec = {
        "family": "video", "tracks": [], "provenance": provenance,
    }
    return output


async def _open_turn(database, uid):
    async with database() as db:
        project = Project(user_id=uid, title="turns", language="en")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=uid, project_id=project.id)
        db.add(conversation)
        await db.flush()
        turn = Message(
            conversation_id=conversation.id,
            role="user",
            content="restore this draft",
            turn_state="in_flight",
        )
        db.add(turn)
        await db.flush()
        turn.turn_id = turn.id
        await db.commit()
        return conversation.id, turn.id, project.id


@pytest.mark.asyncio
async def test_no_progress_without_saved_version_does_not_claim_saved_history():
    from app.chat.service import _design_no_progress_text

    english = _design_no_progress_text("Make a promo", version_saved=False)
    chinese = _design_no_progress_text("制作宣传片", version_saved=False)
    assert "Previously saved" not in english
    assert "did not save a new storyboard" in english
    assert "此前保存" not in chinese
    assert "没有保存新的分镜" in chinese


@pytest.mark.asyncio
async def test_stop_without_visible_content_retracts_and_fences_late_writes(database, monkeypatch):
    from app.chat.service import (
        TurnStopped,
        append_activity_row,
        persist_interim_prose,
        persist_partial_prose,
        settle_interrupted_turn,
        stop_turn_at_visible_frontier,
    )
    from app.models.schemas import ChatTurnStopRequest

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    uid = await owner(database)
    conversation_id, turn_id, _ = await _open_turn(database, uid)
    async with database() as db:
        db.add_all([
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content="persisted but never displayed",
                turn_id=turn_id,
                intent={"type": "interim_prose"},
            ),
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content="buffered tail",
                turn_id=turn_id,
                intent={"type": "partial"},
            ),
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content="",
                turn_id=turn_id,
                intent={"type": "activity", "frame": {"status": "active"}},
            ),
        ])
        await db.commit()

    async with database() as db:
        assert await stop_turn_at_visible_frontier(
            db, turn_id, ChatTurnStopRequest()
        ) == "retracted"
        assert list((await db.scalars(select(Message).where(
            Message.conversation_id == conversation_id
        ))).all()) == []

    # Disconnect is only cleanup: it cannot resurrect or reverse the Stop.
    assert await settle_interrupted_turn(turn_id, conversation_id) is None
    async with database() as db:
        with pytest.raises(TurnStopped):
            await persist_partial_prose(db, conversation_id, turn_id, "late")
        with pytest.raises(TurnStopped):
            await persist_interim_prose(db, conversation_id, turn_id, "late")
        with pytest.raises(TurnStopped):
            await append_activity_row(db, conversation_id, {
                "activity_id": "late", "kind": "read", "status": "active", "key": "read",
            }, turn_id=turn_id)


@pytest.mark.asyncio
async def test_stop_keeps_visible_prefix_and_facts_only(database, monkeypatch):
    from app.chat.service import (
        TurnStopped,
        _lock_turn_for_final_commit,
        settle_activity_row,
        settle_interrupted_turn,
        stop_turn_at_visible_frontier,
    )
    from app.models.schemas import ChatTurnStopRequest, VisibleProseFrontier

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    uid = await owner(database)
    conversation_id, turn_id, _ = await _open_turn(database, uid)
    async with database() as db:
        partial = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="ab😀def",
            turn_id=turn_id,
            intent={"type": "partial"},
        )
        visible_activity = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="",
            turn_id=turn_id,
            intent={"type": "activity", "frame": {"status": "active"}},
        )
        db.add_all([
            partial,
            visible_activity,
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content="unseen interim",
                turn_id=turn_id,
                intent={"type": "interim_prose"},
            ),
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content="",
                turn_id=turn_id,
                intent={"type": "activity", "frame": {"status": "active"}},
            ),
        ])
        await db.commit()
        partial_id, activity_id = partial.id, visible_activity.id

    frontier = ChatTurnStopRequest(
        prose=[VisibleProseFrontier(message_id=partial_id, visible_chars=3)],
        activity_ids=[activity_id],
    )
    async with database() as db:
        assert await stop_turn_at_visible_frontier(db, turn_id, frontier) == "cancelled"

    async with database() as db:
        turn = await db.get(Message, turn_id)
        assert turn.turn_state == "cancelled"
        assert turn.intent["stop_visible"]["prose"][0]["visible_chars"] == 3
        rows = list((await db.scalars(select(Message).where(
            Message.conversation_id == conversation_id
        ))).all())
        assert {row.id for row in rows} == {turn_id, partial_id, activity_id}
        assert (await db.get(Message, partial_id)).content == "ab😀"
        activity = await db.get(Message, activity_id)
        assert activity.intent["frame"]["status"] == "cancelled"
        with pytest.raises(TurnStopped):
            await settle_activity_row(db, activity_id, {"status": "completed"})
        with pytest.raises(TurnStopped):
            await _lock_turn_for_final_commit(db, turn_id)
        await db.rollback()
    assert await settle_interrupted_turn(turn_id, conversation_id) == "cancelled"


@pytest.mark.asyncio
async def test_stop_clamps_prefix_and_keeps_only_visible_structure(database):
    from app.chat.service import stop_turn_at_visible_frontier
    from app.models.schemas import ChatTurnStopRequest, VisibleProseFrontier

    uid = await owner(database)
    conversation_id, turn_id, _ = await _open_turn(database, uid)
    async with database() as db:
        partial = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="server-owned",
            turn_id=turn_id,
            intent={"type": "partial"},
        )
        structure = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="",
            turn_id=turn_id,
            blocks=[{"type": "storyboard", "version": 3}],
        )
        outside = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="not part of this Turn",
            intent={"type": "partial"},
        )
        db.add_all([partial, structure, outside])
        await db.commit()
        partial_id, structure_id, outside_id = partial.id, structure.id, outside.id

    async with database() as db:
        assert await stop_turn_at_visible_frontier(db, turn_id, ChatTurnStopRequest(
            prose=[
                # Overlong values clamp to the server's own text; a foreign row
                # id cannot inject its content or make the Turn cancellable.
                VisibleProseFrontier(message_id=partial_id, visible_chars=999),
                VisibleProseFrontier(message_id=outside_id, visible_chars=5),
            ],
            structure_ids=[structure_id],
        )) == "cancelled"

    async with database() as db:
        assert (await db.get(Message, partial_id)).content == "server-owned"
        assert (await db.get(Message, structure_id)).blocks == [
            {"type": "storyboard", "version": 3}
        ]
        assert (await db.get(Message, outside_id)).content == "not part of this Turn"


@pytest.mark.asyncio
async def test_final_fence_rereads_preloaded_opening_row(database):
    from app.chat.service import (
        TurnStopped,
        _lock_turn_for_final_commit,
        stop_turn_at_visible_frontier,
    )
    from app.models.schemas import ChatTurnStopRequest, VisibleProseFrontier

    uid = await owner(database)
    conversation_id, turn_id, _ = await _open_turn(database, uid)
    async with database() as db:
        partial = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="visible",
            turn_id=turn_id,
            intent={"type": "partial"},
        )
        db.add(partial)
        await db.commit()
        partial_id = partial.id

    async with database() as main:
        opening = await main.get(Message, turn_id)
        assert opening.turn_state == "in_flight"
        async with database() as stop_db:
            assert await stop_turn_at_visible_frontier(
                stop_db,
                turn_id,
                ChatTurnStopRequest(
                    prose=[VisibleProseFrontier(message_id=partial_id, visible_chars=7)]
                ),
            ) == "cancelled"
        # The main session loaded in_flight before Stop committed. Its lock
        # must refresh that identity-map row instead of settling over cancelled.
        with pytest.raises(TurnStopped):
            await _lock_turn_for_final_commit(main, turn_id)
        await main.rollback()


@pytest.mark.asyncio
async def test_stop_rereads_preloaded_row_after_settlement(database):
    from app.chat.service import stop_turn_at_visible_frontier
    from app.models.schemas import ChatTurnStopRequest

    uid = await owner(database)
    conversation_id, turn_id, _ = await _open_turn(database, uid)
    async with database() as db:
        partial = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="settled reply",
            turn_id=turn_id,
            intent={"type": "partial"},
        )
        db.add(partial)
        await db.commit()
        partial_id = partial.id

    async with database() as main:
        opening = await main.get(Message, turn_id)
        assert opening.turn_state == "in_flight"
        async with database() as settled_db:
            settled = await settled_db.get(Message, turn_id, with_for_update=True)
            settled.turn_state = "settled"
            await settled_db.commit()
        assert await stop_turn_at_visible_frontier(
            main, turn_id, ChatTurnStopRequest()
        ) == "settled"
        await main.rollback()

    async with database() as db:
        assert (await db.get(Message, turn_id)).turn_state == "settled"
        assert (await db.get(Message, partial_id)).content == "settled reply"


@pytest.mark.asyncio
async def test_stop_winning_final_commit_rolls_back_the_reservation(database):
    from app.chat.service import (
        TurnStopped,
        _lock_turn_for_final_commit,
        stop_turn_at_visible_frontier,
    )
    from app.models.schemas import ChatTurnStopRequest, VisibleProseFrontier

    uid = await owner(database)
    conversation_id, turn_id, project_id = await _open_turn(database, uid)
    async with database() as db:
        partial = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="visible",
            turn_id=turn_id,
            intent={"type": "partial"},
        )
        db.add(partial)
        await db.commit()
        partial_id = partial.id
    async with database() as db:
        await stop_turn_at_visible_frontier(db, turn_id, ChatTurnStopRequest(
            prose=[VisibleProseFrontier(message_id=partial_id, visible_chars=7)]
        ))

    async with database() as db:
        await billing.hold_media(db, user_id=uid, job_id=uuid4(), credits=50)
        with pytest.raises(TurnStopped):
            await _lock_turn_for_final_commit(db, turn_id)
        await db.rollback()
    async with database() as db:
        assert await billing.held(db, uid) == 0


async def test_unbound_opening_has_native_creation_without_skill_context(database, monkeypatch, installed_promo):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.service import (
        _create_message,
        _get_or_create_project_conversation,
        prepare_chat_turn,
    )
    from app.chat.prompts import assemble_video_round
    from app.chat.turn_tools import tools_for_bound_skill
    from app.models.schemas import ChatRequest
    from app.chat.editor_create import CreateVideoArgs
    from app.skills.resolution import get_builtin_skill_option

    uid = await owner(database)
    skill = get_builtin_skill_option("promo-video").reference
    async with database() as db:
        project = Project(user_id=uid, title="skill continuation")
        db.add(project)
        await db.flush()
        conversation = await _get_or_create_project_conversation(db, uid, project.id)
        first = await _create_message(
            db, conversation.id, "user", "Use promo-video",
            intent={"skill": skill.model_dump(mode="json")},
        )
        first.turn_state = "settled"
        await db.commit()
        continued = await prepare_chat_turn(
            db, uid, ChatRequest(project_id=project.id, message="制作一个产品宣传片 promo-video")
        )
        assert continued.skill is None
        assert not (continued.user_message.intent or {}).get("skill")
        declared = tools_for_bound_skill(intent_router.tools, continued.skill)
        projected = assemble_video_round({
            "tools": declared,
            "drafts": (),
            "snapshot": ContextSnapshot("prepared", frozenset({"snapshot:source:digest"})),
            "skill": continued.skill,
            "material_pending": False,
            "mode": "plan",
            "user_text": continued.user_message.content,
        }).tools
        assert next(tool for tool in projected if tool.name == "create_video").params_model is CreateVideoArgs

        assert not {tool.name for tool in projected} & {"list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview"}


async def test_video_edit_read_returns_current_base_and_only_requested_clip(database):
    import json
    from app.chat.perception.executes import get_video_version
    from app.models.schemas import GetVideoVersionParams, canonical_json_hash
    from test.core.fixtures import valid_content

    uid = await owner(database)
    async with database() as db:
        project = Project(user_id=uid, title="narrow edit read")
        db.add(project)
        await db.flush()
        composition, version, _ = await pinned_video_version(db, project)
        content = valid_content()
        version.settings = content.settings.model_dump(mode="json")
        version.sources = [source.model_dump(mode="json") for source in content.sources]
        version.scenes = [scene.model_dump(mode="json") for scene in content.scenes]
        version.timeline = content.timeline.model_dump(mode="json")
        version.content_digest = canonical_json_hash(content.model_dump(mode="json"))
        await db.commit()
        result = await get_video_version(db, project, GetVideoVersionParams(
            composition_id=composition.id, purpose="edit", clip_id="clp_title",
        ))
        payload = json.loads(result.text)
        assert payload["base_ref"] == {
            "composition_id": str(composition.id),
            "composition_version_id": str(version.id),
            "content_digest": version.content_digest,
        }
        assert [clip["clip_id"] for clip in payload["clips"]] == ["clp_title"]
        assert "storyboard" not in payload




async def test_home_opening_is_admitted_once_even_after_retraction(database, monkeypatch):
    from fastapi import HTTPException
    from app.chat.service import prepare_chat_turn, stop_turn_at_visible_frontier
    from app.models.schemas import ChatRequest, ChatTurnStopRequest

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    uid = await owner(database)
    async with database() as db:
        project = Project(user_id=uid, title="Opening race")
        db.add(project)
        await db.commit()
        request = ChatRequest(project_id=project.id, message="Inspect my assets", first_message=True)

    async def admit():
        async with database() as db:
            try:
                return (await prepare_chat_turn(db, uid, request)).user_message.id
            except HTTPException as conflict:
                assert conflict.detail == {"code": "chat.already_opened"}
                return None

    winners = [opening for opening in await asyncio.gather(admit(), admit()) if opening]
    assert len(winners) == 1
    async with database() as db:
        assert await stop_turn_at_visible_frontier(db, winners[0], ChatTurnStopRequest()) == "retracted"
    assert await admit() is None


@pytest.mark.parametrize("save_version", [False, True])
async def test_native_create_stops_after_save_or_reports_failure(database, monkeypatch, save_version):
    import json
    from app.agents import tool_loop
    from app.chat.editor_create import CreateVideoArgs
    from app.chat.plan_turn import PlanTurn
    from app.models.schemas import ChatRequest
    from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        def __init__(self):
            self.rounds = 0

        async def generate_with_tools(self, **_kwargs):
            self.rounds += 1
            return ToolGeneration("", [ToolCall(
                id=f"call-{self.rounds}", name="create_video",
                arguments={"name": "Title", "shots": [{"headline": "Hello", "duration_seconds": 3}]},
            )])

    class Template:
        def render(self, **_kwargs):
            return "test"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name=f"test-native-save-{save_version}-{uuid4().hex}",
        prompt="unused.j2", system="test", assemble=lambda **_kwargs: ({}, []),
        tools=[tool_loop.ChatTool(
            name="create_video", description="Create the first version",
            params_model=CreateVideoArgs, terminal=False,
        )], client=Client(), max_iterations=2,
    )

    async def execute(_name, _params, _speech):
        if save_version:
            return tool_loop.ToolObservation(
                json.dumps({"ok": True, "saved": True}), ok=True,
                version_saved=True, stop_after_observation=True,
            )
        return "Composition validation failed"

    result = await agent.call_loop(execute)
    assert result.exhausted is not save_version
    assert result.version_saved is save_version

    uid = await owner(database)
    conversation_id, _, project_id = await _open_turn(database, uid)
    async with database() as db:
        project = await db.get(Project, project_id)
        request = ChatRequest(project_id=project_id, message="制作产品宣传片")
        turn = PlanTurn(db, uid, SimpleNamespace(id=conversation_id), project, request)
        turn.text = request.message
        message, _ = await turn.finish(result)
        message_id = message.id
        await db.commit()

    async with database() as db:
        content = (await db.get(Message, message_id)).content
        if save_version:
            assert "最近保存的分镜版本" in content
            assert "做不了" not in content
        else:
            assert "尚未保存本轮修改" in content
            assert "作品版本已保存" not in content
