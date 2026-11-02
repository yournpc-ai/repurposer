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
    CreditTransaction, Output, Project, User, Wallet, WorkflowRun, WorkflowStep,
    Conversation, Message,
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


@pytest.mark.parametrize("reservation,charges", [(191, [177]), (191, []), (191, [120, 130]), (0, [177])])
async def test_capture_consumes_reservation_once(database, monkeypatch, reservation, charges):
    async def price(_db, cost):
        return round(cost * 1000)
    monkeypatch.setattr(billing, "credits_for_cost", price)
    uid, rid = await owner(database), uuid4()
    async with database() as db:
        await billing.hold_run(db, user_id=uid, run_id=rid, amount=reservation)
        await db.commit()
    nodes = [SimpleNamespace(id=uuid4(), run_id=rid, kind="launch_film", attempt=0,
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
    node = SimpleNamespace(id=uuid4(), run_id=rid, kind="launch_film", attempt=0,
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

    uid = await owner(database)
    conversation_id, turn_id, project_id = await _open_turn(database, uid)
    intent = InferredIntent(
        action="start", tasks=[TaskItem(tool="write_post")], name="Start"
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

    async def fake_create_run(db, project, _spec):
        nonlocal create_run_calls
        create_run_calls += 1
        run = WorkflowRun(project_id=project.id, status=WorkflowStatus.PENDING, context={})
        db.add(run)
        await db.flush()
        await billing.hold_run(db, user_id=uid, run_id=run.id, amount=50)
        return run

    async def allow_lifecycle(*_args, **_kwargs):
        return SimpleNamespace()

    async def no_draft_stamp(*_args, **_kwargs):
        return None

    async def no_video_approval(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.pipeline.orchestrator.create_run", fake_create_run)
    monkeypatch.setattr("app.pipeline.lifecycle.project_lifecycle", allow_lifecycle)
    monkeypatch.setattr("app.pipeline.lifecycle.evaluate_start_gate", lambda **_kwargs: None)
    monkeypatch.setattr("app.pipeline.graph_fill.stamp_draft_graph", no_draft_stamp)
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
        completed = Output(
            project_id=project.id,
            type="film",
            render_status=RenderStatus.COMPLETED,
            files={"video": "already-delivered.mp4"},
        )
        active = Output(
            project_id=project.id,
            type="film",
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
        output = Output(project_id=project.id, type="film", render_status=render_state,
                        files={"video": "video.mp4"} if has_file else {},
                        render_error="视频已生成，但上传失败" if render_state == RenderStatus.FAILED else None)
        db.add(output)
        await db.flush()
        refs = [str(output.id)]
        if partial:
            post = Output(project_id=project.id, type="post", payload={"text": "ready"})
            db.add(post)
            await db.flush()
            refs.append(str(post.id))
        db.add_all([
            WorkflowStep(run_id=run.id, kind="launch_film", status="done", output_refs=refs),
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


@pytest.mark.parametrize("recovery_succeeds", [True, False])
async def test_upload_failure_recovers_without_rerendering(
    database, monkeypatch, recovery_succeeds
):
    """The user's failed-delivery journey: the original run reopens, the
    existing worker sends upload_only, and either delivery settles or a cache
    miss honestly asks for a render. No paid regeneration step is created."""
    import httpx
    from app.pipeline import jobs, orchestrator, rendering, step_display
    from app.pipeline.trigger_events import run_id_from_trigger_ref

    uid = await owner(database)
    monkeypatch.setattr(rendering, "AsyncSessionLocal", database)
    monkeypatch.setattr(step_display, "AsyncSessionLocal", database)
    monkeypatch.setattr(rendering, "_absolutize", lambda spec: spec)
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", database)
    events = []
    monkeypatch.setattr(orchestrator, "fire_trigger", lambda *args: events.append(args))

    async def resume(*args):
        pass

    monkeypatch.setattr(orchestrator, "_resume_parked_answered", resume)

    async def path(*args):
        return "output/video.mp4"

    async def presign(*args, **kwargs):
        return "https://storage.test/video"

    probes = []

    async def probe(*args):
        probes.append(args)
        return []

    monkeypatch.setattr(rendering, "get_output_path", path)
    monkeypatch.setattr(rendering, "presign_upload", presign)
    monkeypatch.setattr(rendering, "_probe_artifacts", probe)
    responses = [
        httpx.Response(500, json={"stage": "upload", "code": "UND_ERR_HEADERS_TIMEOUT"}),
        (
            httpx.Response(200, json={"video": "output/video.mp4"})
            if recovery_succeeds
            else httpx.Response(
                409, json={"stage": "recovery", "code": "ARTIFACT_CACHE_MISS"}
            )
        ),
    ]
    requests = []

    def respond(request):
        import json

        requests.append(json.loads(request.content))
        return responses.pop(0)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        rendering.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    async with database() as db:
        project = Project(
            user_id=uid, title="upload", language="zh", status=ProjectStatus.PROCESSING
        )
        db.add(project)
        await db.flush()
        run = WorkflowRun(
            project_id=project.id,
            status=WorkflowStatus.RUNNING,
            context={"ui_language": "zh"},
        )
        db.add(run)
        await db.flush()
        output = Output(
            project_id=project.id,
            type="film",
            render_status=RenderStatus.PENDING,
            render_spec={"family": "film", "scenes": []},
        )
        db.add(output)
        await db.flush()
        producer = WorkflowStep(
            run_id=run.id,
            kind="launch_film",
            status="done",
            output_refs=[str(output.id)],
        )
        step = WorkflowStep(
            run_id=run.id,
            kind="render",
            status="pending",
            spec={"output_id": str(output.id)},
        )
        db.add_all([producer, step])
        await db.commit()
        oid, sid, rid, pid = output.id, step.id, run.id, project.id

    async with database() as db:
        assert await jobs.claim_pending_render(db) == oid
    async with database() as db:
        claimed_step = await db.get(WorkflowStep, sid)
        assert claimed_step.attempt == 1
        assert [
            (s["kind"], s["status"], s["attempt"])
            for s in claimed_step.spec["production_stages"]
        ] == [("render", "running", 1)]
    await rendering.render_output(oid)
    async with database() as db:
        output, step = await db.get(Output, oid), await db.get(WorkflowStep, sid)
        run, project = await db.get(WorkflowRun, rid), await db.get(Project, pid)
        assert output.render_status == RenderStatus.FAILED and not output.files
        assert "上传失败" in output.render_error
        assert step.spec["failure"] == {
            "stage": "upload",
            "codes": ["UND_ERR_HEADERS_TIMEOUT"],
        }
        assert run.status == WorkflowStatus.FAILED
        assert project.status == ProjectStatus.DRAFT
        assert "upload_only" not in requests[0]
        assert not probes
        assert [
            (s["kind"], s["status"], s["attempt"])
            for s in step.spec["production_stages"]
        ] == [("render", "completed", 1), ("upload", "failed", 1)]

        target = await rendering.resolve_upload_retry(db, project, run_id=rid)
        assert not isinstance(target, str)
        assert await rendering.queue_upload_retry(db, project, target) == rid
        await db.commit()
        assert output.render_status == RenderStatus.PENDING
        assert step.status == "pending" and step.spec["upload_only"] is True
        assert run.status == WorkflowStatus.RUNNING
        assert run.context["upload_retry_count"] == 1
        from app.pipeline.routes.runs import _run_frame
        assert _run_frame(run)["upload_retry_count"] == 1
        assert project.status == ProjectStatus.PROCESSING
        # A repeated request while recovery is queued cannot double-enqueue.
        assert isinstance(
            await rendering.resolve_upload_retry(db, project, run_id=rid), str
        )

    async with database() as db:
        assert await jobs.claim_pending_render(db) == oid
    async with database() as db:
        claimed_step = await db.get(WorkflowStep, sid)
        assert claimed_step.attempt == 2
        assert [
            (s["kind"], s["status"], s["attempt"])
            for s in claimed_step.spec["production_stages"]
        ] == [
            ("render", "completed", 1),
            ("upload", "failed", 1),
            ("upload", "running", 2),
        ]
    await rendering.render_output(oid)
    async with database() as db:
        output, step = await db.get(Output, oid), await db.get(WorkflowStep, sid)
        run = await db.get(WorkflowRun, rid)
        assert requests[1]["upload_only"] is True
        assert "upload_only" not in step.spec
        assert len(events) == 2
        expected_stages = [
            ("render", "completed", 1),
            ("upload", "failed", 1),
            ("upload", "completed" if recovery_succeeds else "failed", 2),
        ]
        if recovery_succeeds:
            expected_stages.append(("delivery", "completed", 2))
        assert [
            (s["kind"], s["status"], s["attempt"])
            for s in step.spec["production_stages"]
        ] == expected_stages
        if recovery_succeeds:
            assert output.render_status == RenderStatus.COMPLETED
            assert output.files["video"] and output.render_error is None
            assert step.status == "done" and step.spec["summary"] == "上传完成"
            assert "failure" not in step.spec
            assert run.status == WorkflowStatus.COMPLETED
            assert len(probes) == 1
            assert events[1][1] == "run_completed"
            assert events[1][2] != events[0][2]
            assert run_id_from_trigger_ref(events[1][2]) == rid
            project = await db.get(Project, pid)
            assert project.status == ProjectStatus.REVIEW
        else:
            assert output.render_status == RenderStatus.FAILED
            assert "缓存" in output.render_error
            assert step.status == "failed"
            assert step.spec["failure"]["stage"] == "recovery"
            assert run.status == WorkflowStatus.FAILED
            assert not probes
            assert events[1][1] == "run_failed"
            assert events[1][2] != events[0][2]
            assert run_id_from_trigger_ref(events[1][2]) == rid
            project = await db.get(Project, pid)
            assert isinstance(
                await rendering.resolve_upload_retry(db, project, run_id=rid), str
            )


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


async def test_film_retry_endpoint_preserves_inflight_claim(database):
    from fastapi import HTTPException
    from app.pipeline.routes.outputs import render_output_endpoint
    uid = await owner(database)
    async with database() as db:
        project = Project(user_id=uid, title="retry")
        db.add(project)
        await db.flush()
        output = Output(project_id=project.id, type="film", render_status=RenderStatus.FAILED,
                        render_spec={"family": "film", "scenes": []}, render_attempt=3,
                        render_error="upload failed", render_claim_token=uuid4())
        db.add(output)
        await db.commit()
        result = await render_output_endpoint(output.id, db, SimpleNamespace(id=uid))
        assert result.render_status == RenderStatus.PENDING
        assert result.render_attempt == 0 and result.render_error is None
        assert result.render_claim_token is None
        token = uuid4()
        output.render_status, output.render_claim_token = RenderStatus.RENDERING, token
        await db.commit()
        result = await render_output_endpoint(output.id, db, SimpleNamespace(id=uid))
        assert result.render_claim_token == token
        output.type = "post"
        await db.commit()
        with pytest.raises(HTTPException) as rejected:
            await render_output_endpoint(output.id, db, SimpleNamespace(id=uid))
        assert rejected.value.status_code == 400
