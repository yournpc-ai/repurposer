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
    WorkflowRun, WorkflowStep, Conversation, Message,
)
from app.models.schemas import ProjectStatus, RenderStatus, WorkflowStatus
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


@pytest.mark.parametrize("reservation,charges", [(191, [177]), (191, []), (191, [120, 130]), (0, [177])])
async def test_capture_consumes_reservation_once(database, monkeypatch, reservation, charges):
    async def price(_db, cost):
        return round(cost * 1000)
    monkeypatch.setattr(billing, "credits_for_cost", price)
    uid, rid = await owner(database), uuid4()
    async with database() as db:
        await billing.hold_run(db, user_id=uid, run_id=rid, amount=reservation)
        await db.commit()
    nodes = [SimpleNamespace(id=uuid4(), run_id=rid, kind="produce_video", attempt=0,
                             cost={"fixed_cost": amount / 1000}) for amount in charges]

    async def capture(node):
        async with database() as db:
            await billing.capture_step(db, user_id=uid, node=node)
            await db.commit()

    # Parallel steps and duplicate delivery of the same success callback.
    await asyncio.gather(*(capture(n) for n in nodes for _ in range(2)))
    async with database() as db:
        actual = sum(charges)
        wallet = await db.get(Wallet, uid)
        assert wallet.balance == 1000 - max(reservation, actual)
        assert await billing.held(db, uid) == max(0, reservation - actual)
        await billing.release_run(db, user_id=uid, run_id=rid)
        await billing.release_run(db, user_id=uid, run_id=rid)
        await db.commit()
        await db.refresh(wallet)
        assert wallet.balance == 1000 - actual
        assert await billing.held(db, uid) == 0
        delta = await db.scalar(select(func.coalesce(func.sum(CreditTransaction.amount), 0)))
        assert wallet.balance == 1000 + delta


async def test_legacy_repair_is_dry_by_default_and_idempotent(database, monkeypatch):
    from scripts import repair_credit_reservations as repair
    uid, rid = await owner(database), uuid4()
    monkeypatch.setattr(repair, "AsyncSessionLocal", database)
    async with database() as db:
        for kind, amount in [("hold", -191), ("capture", -177), ("release", 14)]:
            await billing._mutate(db, user_id=uid, kind=kind, amount=amount,
                                  ref={"run_id": str(rid)}, idem=f"legacy:{rid}:{kind}", note="test")
        await db.commit()
    await repair.main(str(rid), False)
    async with database() as db:
        assert (await db.get(Wallet, uid)).balance == 646
    await repair.main(str(rid), True)
    await repair.main(str(rid), True)
    async with database() as db:
        assert (await db.get(Wallet, uid)).balance == 823
        assert await billing.held(db, uid) == 0


async def test_capture_delta_and_rollback(database, monkeypatch):
    async def price(_db, cost):
        return round(cost * 1000)
    monkeypatch.setattr(billing, "credits_for_cost", price)
    uid, rid = await owner(database), uuid4()
    node = SimpleNamespace(id=uuid4(), run_id=rid, kind="produce_video", attempt=0,
                           cost={"fixed_cost": .100})
    async with database() as db:
        await billing.hold_run(db, user_id=uid, run_id=rid, amount=191)
        await db.commit()
        await billing.capture_step(db, user_id=uid, node=node)
        await db.rollback()  # no reservation refund can escape a failed transaction
        assert await billing.held(db, uid) == 191
        await billing.capture_step(db, user_id=uid, node=node)
        await db.commit()
        node.cost, node.attempt = {"fixed_cost": .230}, 1
        await billing.capture_step(db, user_id=uid, node=node)
        await billing.capture_step(db, user_id=uid, node=node)
        await billing.release_run(db, user_id=uid, run_id=rid)
        await db.commit()
        assert (await db.get(Wallet, uid)).balance == 770
        assert await billing.held(db, uid) == 0


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
async def test_stop_winning_final_commit_leaves_no_run_or_hold(database):
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
        run = WorkflowRun(project_id=project_id, status=WorkflowStatus.PENDING)
        db.add(run)
        await db.flush()
        await billing.hold_run(db, user_id=uid, run_id=run.id, amount=50)
        with pytest.raises(TurnStopped):
            await _lock_turn_for_final_commit(db, turn_id)
        await db.rollback()
    async with database() as db:
        assert list((await db.scalars(select(WorkflowRun).where(
            WorkflowRun.project_id == project_id
        ))).all()) == []
        assert await billing.held(db, uid) == 0


async def test_first_create_skill_inherits_until_a_saved_version(database, monkeypatch, installed_promo):
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
            db, uid, ChatRequest(project_id=project.id, message="Continue with one shot")
        )
        assert continued.skill == skill
        assert continued.user_message.intent["skill"] == skill.model_dump(mode="json")
        declared = tools_for_bound_skill(intent_router.tools, continued.skill)
        projected = assemble_video_round({
            "tools": declared,
            "drafts": (),
            "snapshot": ContextSnapshot("prepared", frozenset({"snapshot:source:digest"})),
            "skill": continued.skill,
            "material_pending": False,
            "mode": "plan",
            "user_text": "Continue with one shot",
        }).tools
        assert next(tool for tool in projected if tool.name == "create_video").params_model is CreateVideoArgs

        assert continued.user_message.intent["skill_binding"] == "inherited"
        continued.user_message.turn_state = "settled"
        await db.commit()
        ordinary = await prepare_chat_turn(
            db, uid, ChatRequest(project_id=project.id, message="What else can you do?")
        )
        assert ordinary.skill is None
        ordinary.user_message.turn_state = "settled"
        await db.commit()
        switched = await prepare_chat_turn(
            db, uid, ChatRequest(
                project_id=project.id, message="Use text animation instead",
                skill=get_builtin_skill_option("text-animation").reference,
            ),
        )
        assert switched.skill.skill_id == "text-animation"
        switched.user_message.turn_state = "settled"
        await db.commit()
        await pinned_video_version(db, project)
        await db.commit()
        saved = await prepare_chat_turn(
            db, uid, ChatRequest(project_id=project.id, message="What changed?")
        )
        assert saved.skill is None


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
