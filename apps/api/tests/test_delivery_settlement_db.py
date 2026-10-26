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
    from app.pipeline import jobs, orchestrator, rendering
    from app.pipeline.trigger_events import run_id_from_trigger_ref

    uid = await owner(database)
    monkeypatch.setattr(rendering, "AsyncSessionLocal", database)
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

        target = await rendering.resolve_upload_retry(db, project, run_id=rid)
        assert not isinstance(target, str)
        assert await rendering.queue_upload_retry(db, project, target) == rid
        await db.commit()
        assert output.render_status == RenderStatus.PENDING
        assert step.status == "pending" and step.spec["upload_only"] is True
        assert run.status == WorkflowStatus.RUNNING
        assert run.context["upload_retry_count"] == 1
        assert project.status == ProjectStatus.PROCESSING
        # A repeated request while recovery is queued cannot double-enqueue.
        assert isinstance(
            await rendering.resolve_upload_retry(db, project, run_id=rid), str
        )

    async with database() as db:
        assert await jobs.claim_pending_render(db) == oid
    await rendering.render_output(oid)
    async with database() as db:
        output, step = await db.get(Output, oid), await db.get(WorkflowStep, sid)
        run = await db.get(WorkflowRun, rid)
        assert requests[1]["upload_only"] is True
        assert "upload_only" not in step.spec
        assert len(events) == 2
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
