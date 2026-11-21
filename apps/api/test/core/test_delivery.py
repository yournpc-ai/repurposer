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


@pytest.mark.parametrize("next_run_started", [False, True])
async def test_stop_during_media_handoff_keeps_delivered_answer_and_fences_the_next_start(database, next_run_started):
    from app.chat.routes import stop_chat_turn
    from app.chat.service import TurnStopped, _lock_turn_for_transcript_write
    from app.models.schemas import ChatTurnStopRequest

    uid = await owner(database)
    conversation_id, turn_id, project_id = await _open_turn(database, uid)
    journey = {"opening_id": str(turn_id)}
    async with database() as db:
        opening = await db.get(Message, turn_id)
        opening.turn_state = "settled"
        delivered = Message(
            conversation_id=conversation_id, role="assistant", content="Images ready", seq=11,
            intent={"type": "trigger_review", "media_journey": {**journey, "state": "active"}},
        )
        db.add(delivered)
        if next_run_started:
            run = WorkflowRun(project_id=project_id, status=WorkflowStatus.RUNNING, context={"media_journey": journey})
            db.add(run)
            await db.flush()
            db.add(Message(conversation_id=conversation_id, role="assistant", content="Recording", seq=12,
                           workflow_run_id=run.id, intent={"media_journey": {**journey, "state": "active"}}))
        await db.commit()
        user = await db.get(User, uid)
        request = ChatTurnStopRequest(scope="media_preparation")
        result = await stop_chat_turn(turn_id, request, db, user)
        assert result["accepted"] and result["journey_message"]["intent"]["media_journey"]["state"] == "stopped"
        assert result["journey_message"]["seq"] == (12 if next_run_started else 11)
        assert await stop_chat_turn(turn_id, request, db, user) == result
        assert opening.turn_state == "settled" and delivered.content == "Images ready"
        if next_run_started:
            assert run.status == WorkflowStatus.CANCELLED
        with pytest.raises(TurnStopped):
            await _lock_turn_for_transcript_write(db, turn_id)




@pytest.mark.asyncio
async def test_present_plan_requires_an_explicit_production_intent_judgment():
    from app.chat.plan_turn import PlanTurn
    from app.models.schemas import ChatRequest, PresentPlanArgs

    request = ChatRequest(project_id=uuid4(), message="制作产品宣传片")
    turn = PlanTurn(
        db=None,
        user_id=uuid4(),
        conversation=SimpleNamespace(id=uuid4()),
        project=SimpleNamespace(pending_brief=None),
        request=request,
    )
    result = await turn._present_plan(
        PresentPlanArgs(tasks=[], production_intent=None),
        "Prepare the scene images.",
    )
    assert "production_intent is required" in result
    assert "true or false" in result


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
async def test_nested_start_never_commits_before_stop_fence(database, monkeypatch):
    from app.chat.service import (
        TurnStopped,
        answer_question,
        append_activity_row,
        stop_turn_at_visible_frontier,
    )
    from app.models.schemas import (
        ChatTurnStopRequest,
        InferredIntent,
        PendingPlan,
        StartAnswerRequest,
        TaskItem,
        VisibleProseFrontier,
    )

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    uid = await owner(database)
    conversation_id, turn_id, project_id = await _open_turn(database, uid)
    intent = InferredIntent(
        action="start", tasks=[TaskItem(tool="prepare_narration", params={"text": "Start", "voice_id": "presenter_male", "language": "en"})], name="Start"
    )
    pending = PendingPlan(prompt="start", intent=intent)
    async with database() as db:
        project = await db.get(Project, project_id)
        project.pending_brief = pending.model_dump(mode="json")
        question = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="Plan",
            turn_id=turn_id,
            question={"kind": "task_book", "requires_confirmation": False},
            intent=intent.model_dump(mode="json"),
        )
        partial = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="visible",
            turn_id=turn_id,
            intent={"type": "partial"},
        )
        db.add_all([question, partial])
        await db.commit()
        question_id, partial_id = question.id, partial.id

    create_run_calls = 0

    async def fake_create_run(db, project, _spec, **_kwargs):
        nonlocal create_run_calls
        create_run_calls += 1
        run = WorkflowRun(project_id=project.id, status=WorkflowStatus.PENDING, context={})
        db.add(run)
        await db.flush()
        await billing.hold_run(db, user_id=uid, run_id=run.id, amount=50)
        return run

    async def allow_lifecycle(*_args, **_kwargs):
        return SimpleNamespace()

    async def no_video_approval(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.pipeline.orchestrator.create_run", fake_create_run)
    monkeypatch.setattr("app.pipeline.lifecycle.project_lifecycle", allow_lifecycle)
    monkeypatch.setattr("app.pipeline.lifecycle.evaluate_start_gate", lambda **_kwargs: None)
    monkeypatch.setattr("app.tools.video.production.latest_video_approval", no_video_approval)

    async with database() as main:
        # Preload the opening row so the later Stop also exercises the
        # identity-map refresh at the final fence.
        assert (await main.get(Message, turn_id)).turn_state == "in_flight"
        await answer_question(
            main,
            uid,
            question_id,
            StartAnswerRequest(kind="start"),
            turn_id=turn_id,
            defer_start_commit=True,
        )
        async with database() as observer:
            # answer_question flushed a real Run + hold through the nested Start
            # chain, but no other session may see them before the outer fence.
            assert list((await observer.scalars(select(WorkflowRun).where(
                WorkflowRun.project_id == project_id
            ))).all()) == []
            assert await billing.held(observer, uid) == 0
        async with database() as activity_db:
            # Terminal Activity persistence uses its own session inside the same
            # Chat Turn. It must share the outer Start's fence rather than wait
            # on the opening-row lock that its owner cannot release yet.
            await asyncio.wait_for(
                append_activity_row(
                    activity_db,
                    conversation_id,
                    {
                        "activity_id": "redirected",
                        "kind": "repair",
                        "status": "completed",
                        "key": "chat.activity.repairDone",
                    },
                    turn_id=turn_id,
                ),
                timeout=1,
            )
            await activity_db.commit()
        await main.rollback()

    async with database() as stop_db:
        assert await stop_turn_at_visible_frontier(
            stop_db,
            turn_id,
            ChatTurnStopRequest(
                prose=[VisibleProseFrontier(message_id=partial_id, visible_chars=7)]
            ),
        ) == "cancelled"

    async with database() as main:
        with pytest.raises(TurnStopped):
            await answer_question(
                main,
                uid,
                question_id,
                StartAnswerRequest(kind="start"),
                turn_id=turn_id,
                defer_start_commit=True,
            )
        await main.rollback()
    assert create_run_calls == 1
    async with database() as observer:
        assert list((await observer.scalars(select(WorkflowRun).where(
            WorkflowRun.project_id == project_id
        ))).all()) == []
        assert await billing.held(observer, uid) == 0


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


async def test_cancel_preserves_capture_and_completed_outputs(database, monkeypatch):
    from app.pipeline.orchestrator import cancel_run

    async def price(_db, cost):
        return round(cost * 1000)

    monkeypatch.setattr(billing, "credits_for_cost", price)
    uid = await owner(database)
    async with database() as db:
        project = Project(
            user_id=uid, title="cancel", language="en", status=ProjectStatus.PROCESSING
        )
        db.add(project)
        await db.flush()
        run = WorkflowRun(project_id=project.id, status=WorkflowStatus.RUNNING)
        db.add(run)
        await db.flush()
        conversation = Conversation(user_id=uid, project_id=project.id)
        db.add(conversation)
        await db.flush()
        pending_question = Message(
            conversation_id=conversation.id,
            workflow_run_id=run.id,
            role="assistant",
            content="Choose a direction",
            question={"kind": "question", "question": "Continue?", "options": []},
        )
        delivery = Message(
            conversation_id=conversation.id,
            workflow_run_id=run.id,
            role="assistant",
            content="Delivery prose",
            intent={"type": "trigger_review", "trigger": "run_completed"},
        )
        user = Message(
            conversation_id=conversation.id,
            workflow_run_id=run.id,
            role="user",
            content="User prose",
        )
        answered = Message(
            conversation_id=conversation.id,
            workflow_run_id=run.id,
            role="assistant",
            content="Already answered",
            question={"kind": "question", "question": "Earlier?", "options": []},
            answer={"kind": "bail", "text": "existing"},
        )
        db.add_all([pending_question, delivery, user, answered])
        composition, version, provenance = await pinned_video_version(db, project)
        completed = pin_video_output(Output(
            project_id=project.id,
            type="video",
            render_status=RenderStatus.COMPLETED,
            files={"video": "already-delivered.mp4"},
        ), composition, version, provenance)
        active = Output(
            project_id=project.id,
            type="video",
            render_status=RenderStatus.PENDING,
            render_claim_token=uuid4(),
        )
        db.add_all([completed, active])
        await db.flush()
        done = WorkflowStep(
            run_id=run.id,
            kind="produce_video",
            status="done",
            output_refs=[str(completed.id)],
            cost={"fixed_cost": 0.030},
        )
        running = WorkflowStep(
            run_id=run.id,
            kind="render",
            status="running",
            spec={"output_id": str(active.id)},
            claim_token=uuid4(),
        )
        pending = WorkflowStep(run_id=run.id, kind="produce_video", status="pending")
        db.add_all([done, running, pending])
        await billing.hold_run(db, user_id=uid, run_id=run.id, amount=100)
        await billing.capture_step(db, user_id=uid, node=done)
        await db.commit()
        run_id, project_id = run.id, project.id
        completed_id, active_id = completed.id, active.id
        done_id = done.id
        pending_question_id, delivery_id, user_id, answered_id = (
            pending_question.id, delivery.id, user.id, answered.id
        )
        await cancel_run(db, run, project)

    async with database() as db:
        run = await db.get(WorkflowRun, run_id)
        assert run.status == WorkflowStatus.CANCELLED
        steps = list((await db.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run_id))).all())
        assert sorted(step.status for step in steps) == ["cancelled", "cancelled", "done"]
        assert all(step.claim_token is None for step in steps if step.status == "cancelled")
        assert (await db.get(Output, completed_id)).render_status == RenderStatus.COMPLETED
        cancelled_output = await db.get(Output, active_id)
        assert cancelled_output.render_status == RenderStatus.CANCELLED
        assert cancelled_output.render_claim_token is None
        assert (await db.get(Project, project_id)).status == ProjectStatus.REVIEW
        assert await billing.held(db, uid) == 0
        assert (await db.get(Wallet, uid)).balance == 970
        captures = list((await db.scalars(select(CreditTransaction).where(CreditTransaction.kind == "capture"))).all())
        assert sum(tx.amount for tx in captures) == -30
        assert (await db.get(Message, pending_question_id)).answer["kind"] == "bail"
        assert (await db.get(Message, delivery_id)).answer is None
        assert (await db.get(Message, user_id)).answer is None
        assert (await db.get(Message, answered_id)).answer == {
            "kind": "bail", "text": "existing"
        }

        # Even if a stale executor re-pends the row after cancellation, the
        # cancelled-run ownership gate refuses a fresh render claim.
        from app.pipeline import jobs

        cancelled_output.render_status = RenderStatus.PENDING
        cancelled_output.render_barrier = [str(done_id)]
        await db.commit()
        assert await jobs.claim_pending_render(db) is None


@pytest.mark.parametrize("render_state,has_file,partial", [
    (RenderStatus.FAILED, False, False),
    (RenderStatus.FAILED, False, True),
    (RenderStatus.COMPLETED, False, False),
    (RenderStatus.COMPLETED, True, False),
])
async def test_finalization_uses_real_delivery(database, monkeypatch, render_state, has_file, partial):
    from app.pipeline import orchestrator
    uid = await owner(database)
    events = []
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", database)
    monkeypatch.setattr(orchestrator, "fire_trigger", lambda *args: events.append(args))
    async def resume(*args):
        pass
    monkeypatch.setattr(orchestrator, "_resume_parked_answered", resume)
    async with database() as db:
        project = Project(user_id=uid, title="incident", language="zh", status=ProjectStatus.PROCESSING)
        db.add(project)
        await db.flush()
        run = WorkflowRun(project_id=project.id, status=WorkflowStatus.RUNNING)
        db.add(run)
        await db.flush()
        composition, version, provenance = await pinned_video_version(db, project)
        output = pin_video_output(Output(
            project_id=project.id, type="video", render_status=render_state,
            files={"video": "video.mp4"} if has_file else {},
            render_error="视频已生成，但上传失败" if render_state == RenderStatus.FAILED else None,
        ), composition, version, provenance)
        db.add(output)
        await db.flush()
        refs = [str(output.id)]
        if partial:
            post = Output(project_id=project.id, type="post", payload={"text": "ready"})
            db.add(post)
            await db.flush()
            refs.append(str(post.id))
        db.add_all([
            WorkflowStep(run_id=run.id, kind="produce_video", status="done", output_refs=refs),
            WorkflowStep(run_id=run.id, kind="render", status="failed" if render_state == RenderStatus.FAILED else "done",
                         spec={"output_id": str(output.id)}, error=output.render_error),
        ])
        await db.commit()
        rid, pid = run.id, project.id
    await orchestrator.maybe_finalize_run(rid)
    await orchestrator.maybe_finalize_run(rid)  # idempotent terminal transition
    async with database() as db:
        run, project = await db.get(WorkflowRun, rid), await db.get(Project, pid)
        successful = render_state == RenderStatus.COMPLETED and has_file
        assert run.status == (WorkflowStatus.COMPLETED if successful else WorkflowStatus.FAILED)
        assert project.status == (ProjectStatus.REVIEW if successful or partial else ProjectStatus.DRAFT)
        assert len(events) == 1
        assert events[0][1] == ("run_completed" if successful or partial else "run_failed")


async def test_typed_upload_retry_is_not_swallowed_by_trigger_run_anchor(database):
    """Typing the docked option verbatim must reach the chat tool loop. The
    trigger row's run id is a display anchor, not a parked-interrupt marker."""
    from app.chat.service import (
        _create_message,
        _get_or_create_project_conversation,
        prepare_chat_turn,
    )
    from app.chat.trigger_turn import _suggestions_payload
    from app.models.schemas import ChatRequest, SuggestionItem

    uid = await owner(database)
    async with database() as db:
        project = Project(user_id=uid, title="upload", language="zh")
        db.add(project)
        await db.flush()
        run = WorkflowRun(project_id=project.id, status=WorkflowStatus.FAILED)
        db.add(run)
        await db.flush()
        conversation = await _get_or_create_project_conversation(db, uid, project.id)
        question = await _create_message(
            db,
            conversation.id,
            "assistant",
            "视频已生成，但上传失败。",
            workflow_run_id=run.id,
            question=_suggestions_payload(
                [SuggestionItem(label="重新上传")], "zh"
            ).model_dump(mode="json"),
        )
        await db.commit()
        prepared = await prepare_chat_turn(
            db, uid, ChatRequest(project_id=project.id, message="重新上传")
        )
        assert prepared.interrupt_reply is None
        assert prepared.answered_question is not None
        assert prepared.answered_question.id == question.id
        assert prepared.user_message.intent["answered_question_id"] == str(question.id)
        assert prepared.plan_path is False


@pytest.mark.parametrize("succeeds", [True, False])
async def test_upload_tool_preserves_original_failed_run(database, monkeypatch, succeeds):
    """Re-upload is a foreground transfer; the failed production stays archived."""
    import httpx
    from app.pipeline import rendering, upload_recovery

    uid = await owner(database)
    monkeypatch.setattr(rendering, "AsyncSessionLocal", database)
    monkeypatch.setattr(upload_recovery, "AsyncSessionLocal", database)
    monkeypatch.setattr(rendering, "_absolutize", lambda spec: spec)
    async def path(*args):
        return "output/reuploaded.mp4"
    async def presign(*args, **kwargs):
        return "https://storage.test/put"
    async def probe(*args):
        return [], "verified"
    monkeypatch.setattr(rendering, "get_output_path", path)
    monkeypatch.setattr(rendering, "presign_upload", presign)
    monkeypatch.setattr(rendering, "_probe_artifacts", probe)
    requests = []
    def respond(request):
        import json
        requests.append(request)
        assert request.url.path == "/upload"
        assert json.loads(request.content)["upload_only"] is True
        return (httpx.Response(200, json={"video": "output/reuploaded.mp4"}) if succeeds
                else httpx.Response(409, json={"stage": "recovery", "code": "ARTIFACT_CACHE_MISS"}))
    client = httpx.AsyncClient
    monkeypatch.setattr(rendering.httpx, "AsyncClient",
                        lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    async with database() as db:
        project = Project(user_id=uid, title="upload", language="zh", status=ProjectStatus.DRAFT)
        db.add(project)
        await db.flush()
        run = WorkflowRun(project_id=project.id, status=WorkflowStatus.FAILED,
                          error="upload failed", context={})
        db.add(run)
        await db.flush()
        composition, version, provenance = await pinned_video_version(db, project)
        output = pin_video_output(Output(
            project_id=project.id, type="video", render_status=RenderStatus.FAILED, files={},
        ), composition, version, provenance)
        db.add(output)
        await db.flush()
        step = WorkflowStep(run_id=run.id, kind="render", seq=1, status="failed",
                            error="upload failed", spec={"output_id": str(output.id),
                            "failure": {"stage": "upload", "codes": ["EPIPE"]}})
        db.add(step)
        await db.commit()
        pid, rid, sid, oid = project.id, run.id, step.id, output.id
    uploaded_id, detail = await upload_recovery.upload_finished_output(pid, uid, oid)
    assert (uploaded_id == oid) is succeeds
    assert detail
    async with database() as db:
        run = await db.get(WorkflowRun, rid)
        step = await db.get(WorkflowStep, sid)
        assert run.status == WorkflowStatus.FAILED
        assert run.context == {}
        assert run.error == "upload failed"
        assert step.status == "failed" and step.error == "upload failed"
        assert (await db.get(Project, pid)).status == ProjectStatus.DRAFT
        assert len((await db.execute(select(WorkflowRun))).scalars().all()) == 1
        assert len((await db.execute(select(CreditTransaction))).scalars().all()) == 0
    if not succeeds:
        # A process crash during this foreground tool must not enqueue rendering.
        from app.pipeline.jobs import reap_stale
        async with database() as db:
            output = await db.get(Output, oid)
            output.render_status = RenderStatus.RENDERING
            await db.commit()
            await reap_stale(db)
            await db.refresh(output)
            assert output.render_status == RenderStatus.FAILED
            assert output.render_claim_token is None
            assert (await db.get(WorkflowStep, sid)).status == "failed"
    # The shared Chat reader includes foreground answers with no Run id.
    if succeeds:
        from app.pipeline.routes.projects import list_chat_delivered_outputs
        async with database() as db:
            conversation = Conversation(user_id=uid, project_id=pid)
            db.add(conversation)
            await db.flush()
            db.add(Message(conversation_id=conversation.id, role="assistant", content="Uploaded",
                           intent={"type": "answer", "output_refs": [str(oid)]}))
            await db.commit()
            entries = await list_chat_delivered_outputs(pid, db, SimpleNamespace(id=uid))
            assert [entry.output_id for entry in entries] == [oid]
            assert entries[0].output is not None
    # A delivered output cannot be uploaded a second time by the same request.
    if succeeds:
        again, _ = await upload_recovery.upload_finished_output(pid, uid, oid)
        assert again is None and len(requests) == 1


@pytest.mark.parametrize("successor", [False, True])
async def test_cancel_upload_cleans_only_its_own_claim(database, monkeypatch, successor):
    from app.pipeline import upload_recovery
    uid = await owner(database)
    monkeypatch.setattr(upload_recovery, "AsyncSessionLocal", database)
    async with database() as db:
        project = Project(user_id=uid, title="cancel upload")
        db.add(project)
        await db.flush()
        run = WorkflowRun(project_id=project.id, status=WorkflowStatus.FAILED)
        db.add(run)
        await db.flush()
        composition, version, provenance = await pinned_video_version(db, project)
        output = pin_video_output(Output(
            project_id=project.id, type="video", render_status=RenderStatus.FAILED, files={},
        ), composition, version, provenance)
        db.add(output)
        await db.flush()
        db.add(WorkflowStep(run_id=run.id, kind="render", seq=1, status="failed",
                           spec={"output_id": str(output.id), "failure": {"stage": "upload"}}))
        await db.commit()
        pid, oid, rid = project.id, output.id, run.id
    entered = asyncio.Event()
    release = asyncio.Event()
    async def transfer(*args, **kwargs):
        entered.set()
        await release.wait()
    monkeypatch.setattr(upload_recovery, "render_output", transfer)
    task = asyncio.create_task(upload_recovery.upload_finished_output(pid, uid, oid))
    await asyncio.wait_for(entered.wait(), 5)
    duplicate, _ = await upload_recovery.upload_finished_output(pid, uid, oid)
    assert duplicate is None
    successor_token = uuid4()
    if successor:
        async with database() as db:
            output = await db.get(Output, oid)
            output.render_claim_token = successor_token
            await db.commit()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with database() as db:
        output = await db.get(Output, oid)
        assert output.render_status == (RenderStatus.RENDERING if successor else RenderStatus.FAILED)
        if successor:
            assert output.render_claim_token == successor_token
        assert (await db.get(WorkflowRun, rid)).status == WorkflowStatus.FAILED
        assert await db.scalar(select(func.count()).select_from(CreditTransaction)) == 0


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




async def test_completed_video_delivery_survives_its_unanswered_dock(database, monkeypatch):
    from app.chat.trigger_turn import _run_review_snapshot, run_trigger_turn
    from app.chat.video_turn_seats import short_video_confirmation
    from app.models.schemas import InferredIntent, PendingPlan, WrapUpArgs
    from app.pipeline import trigger_events

    uid = await owner(database)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    events = []
    trigger_events.register_trigger_handler(lambda *args: events.append(args))

    class Reviewer:
        async def call_loop(self, execute, **_kwargs):
            await execute("wrap_up", WrapUpArgs(), "The saved video is ready.")
            return SimpleNamespace(exhausted=False, prose="The saved video is ready.", calls=[])

    monkeypatch.setattr("app.chat.trigger_turn.delivery_agent", Reviewer())
    async with database() as db:
        project = Project(user_id=uid, title="fixed video", language="en")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=uid, project_id=project.id)
        db.add(conversation)
        await db.flush()
        composition, version, ref = await pinned_video_version(db, project)
        run = WorkflowRun(
            project_id=project.id, status=WorkflowStatus.COMPLETED,
            context={
                "version_ref": ref,
                "confirmed_scope": {"compiled_scope": [{"tool": "produce_video"}]},
            },
        )
        db.add(run)
        await db.flush()
        output = pin_video_output(Output(
            project_id=project.id, type="video", render_status=RenderStatus.COMPLETED,
            files={"video": "fixed-video.mp4"},
        ), composition, version, ref)
        db.add(output)
        await db.flush()
        db.add(WorkflowStep(
            run_id=run.id, kind="produce_video", status="done", output_refs=[str(output.id)],
        ))
        pending = PendingPlan(
            prompt="OK",
            intent=InferredIntent(tasks=[{"tool": "produce_video", "params": {"version_ref": ref}}]),
            video_presentation={**ref, "presented_message_id": str(uuid4())},
        )
        project.pending_brief = pending.model_dump(mode="json")
        db.add(Message(
            conversation_id=conversation.id, role="assistant", content="Production plan",
            intent=pending.intent.model_dump(mode="json"),
            question={"kind": "task_book", "question": "", "options": []},
        ))
        await db.commit()
        pid, rid, oid, cid = project.id, run.id, output.id, conversation.id

    async with database() as db:
        project = await db.get(Project, pid)
        repeated = await short_video_confirmation(db, project, cid, "OK", None)
        assert repeated["action"] == "already_started"
        assert repeated["run_id"] == str(rid)
        assert repeated["delivery_message_id"] is None
    assert events == [(pid, "run_completed", str(rid))]

    async with database() as db:
        run = await db.get(WorkflowRun, rid)
        facts, refs = await _run_review_snapshot(db, run)
        assert facts[0] == "delivery=delivered"
        assert not any(line.startswith("GAP") for line in facts)
        assert refs == [str(oid)]

    delivered = await run_trigger_turn(pid, "run_completed", str(rid))
    assert delivered is not None
    assert delivered.intent["output_refs"] == [str(oid)]
    assert delivered.workflow_run_id == rid

    async with database() as db:
        project = await db.get(Project, pid)
        repeated = await short_video_confirmation(db, project, cid, "OK", None)
        assert repeated["delivery_message_id"] == str(delivered.id)
        assert repeated["output_refs"] == [str(oid)]
        assert len((await db.scalars(select(WorkflowRun).where(WorkflowRun.project_id == pid))).all()) == 1
    assert len(events) == 1

    from app.chat.prompts import assemble_video_round
    assembly = assemble_video_round({
        "mode": "conversation",
        "video_confirmation": {"action": "already_started"},
        "ui_language": "zh",
        "tools": [],
        "user_text": "OK",
    })
    assert "用户在本次对话中使用的语言" in assembly.system


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
        message, _, _, _ = await turn.finish(result)
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
