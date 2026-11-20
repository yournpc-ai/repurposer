"""Write-door and Output-lineage tests against disposable Postgres (ADR-145).

Covers the batch-1 mechanics that need a real transaction: same-chat
independence of two Compositions, cross-Chat concurrent edits (row lock +
base_ref CAS — never an overwrite), request_id idempotency (retry replays,
same key + different payload is refused), owner/permission law, version
monotonicity + atomicity, and the produce seam's Output lineage pins.

No paid IO: snapshots are local rows; nothing here renders.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import TypeAdapter
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.editing.edits import EditError, Op
from app.editing.store import (
    PermissionDenied,
    RequestMismatch,
    StaleBase,
    apply_composition_edits,
    get_video_version,
)
from app.editing.validators import ContentValidationError
from app.models.database import Base
from app.models.tables import (
    Composition,
    CompositionVersion,
    Output,
    Project,
    SourceSnapshot,
    User,
)
from app.tools.video.produce import queue_composition_render
from test.core.fixtures import (
    AUDIO_SNAPSHOT,
    AUDIO_DIGEST,
    IMG_SNAPSHOT,
    IMG_DIGEST,
    FOUR_S_TICKS,
    creation_ops,
)

pytestmark = pytest.mark.asyncio


async def test_video_production_pins_reviewed_version_and_uses_run_render_billing(database, monkeypatch):
    """One production seam: receipt, real Run/hold, render barrier and lineage."""
    from unittest.mock import AsyncMock
    from app.chat.video_turn_seats import short_video_confirmation, stamp_video_presentation
    from app.editing.service import video_version_read
    from app.models.schemas import TaskItem
    from app.models.tables import Conversation, CreditTransaction, Message, WorkflowRun, WorkflowStep
    from app.pipeline.orchestrator import TaskSpec, create_run, derive_task_estimates
    from app.tools.video.production import pin_video_production
    from app.tools.video.production.node import ProduceVideo
    from app.pipeline import step_display
    from app.tools.video import preparation

    monkeypatch.setattr(step_display, "AsyncSessionLocal", database)
    monkeypatch.setattr(preparation, "ensure_font_resources", AsyncMock())
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, version, _ = await _create(database, uid, pid)
    async with database() as db:
        project = await db.get(Project, pid)
        conversation = Conversation(user_id=uid, project_id=pid)
        db.add(conversation)
        await db.flush()
        shown = Message(conversation_id=conversation.id, role="assistant", content="Storyboard", seq=1)
        approved = Message(conversation_id=conversation.id, role="user", content="OK", seq=2)
        db.add_all([shown, approved])
        await db.flush()
        read = await video_version_read(db, owner_id=uid, version_id=version.id)
        stamp_video_presentation(project, shown, read)
        assert await short_video_confirmation(db, project, conversation.id, "OK", None) is None
        stamp_video_presentation(project, shown, read, production_requested=True)
        assert shown.content == "Storyboard"
        assert (await short_video_confirmation(db, project, conversation.id, "OK", None))["action"] == "wait"
        task = TaskItem(tool="produce_video", params={"version_ref": read["base_ref"]})
        with pytest.raises(ValueError, match="finished presenting"):
            await pin_video_production(db, project, [task], approved.id)
        project.pending_brief = {**project.pending_brief, "video_presentation": {
            **project.pending_brief["video_presentation"], "presentation_complete": True,
        }}
        with pytest.raises(ValueError, match="later user approval"):
            await pin_video_production(db, project, [task], shown.id)
        with pytest.raises(ValueError, match="production invitation"):
            await pin_video_production(db, project, [task], approved.id)
        confirmation = await short_video_confirmation(db, project, conversation.id, "OK", None)
        assert confirmation == {
            "action": "produce", "base_ref": read["base_ref"],
            "presented_message_id": str(shown.id),
        }
        approved.intent = {"video_confirmation": confirmation}
        quote = await derive_task_estimates(db, project, [task])
        assert quote is not None and quote.total[1] > 0
        run = await create_run(db, project, TaskSpec(tasks=[task], video_authorized_by=approved.id))
        assert run.context["version_ref"] == read["base_ref"]
        with pytest.raises(ValueError, match="already requested"):
            await pin_video_production(db, project, [task], approved.id)
        steps = list((await db.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run.id))).all())
        assert [s.kind for s in steps] == ["produce_video"]
        hold = await db.scalar(select(CreditTransaction).where(CreditTransaction.kind == "hold"))
        assert hold is not None and hold.amount == -quote.total[1]
        await db.commit()
        run_id, step_id = run.id, steps[0].id
    # Editing while production exists cannot change the worker's input.
    async with database() as db:
        await apply_composition_edits(db, owner_id=uid, composition_id=comp.id,
            base_version_id=version.id, ops=[set_intent("later draft")])
        project = await db.get(Project, pid)
        with pytest.raises(ValueError, match="current storyboard"):
            await pin_video_production(db, project, [task], approved.id)
    async with database() as db:
        run = await db.get(WorkflowRun, run_id)
        step = await db.get(WorkflowStep, step_id)
        project = await db.get(Project, pid)
        ids = await ProduceVideo().run(db, run, step, project)
        assert len(ids) == 1
        output = await db.get(Output, ids[0])
        assert output.composition_version_id == version.id
        assert output.render_barrier == [str(step.id)]
        assert output.render_spec["provenance"] == run.context["version_ref"]
        mirrors = list((await db.scalars(select(WorkflowStep).where(
            WorkflowStep.run_id == run.id, WorkflowStep.kind == "render"))).all())
        assert len(mirrors) == 1
        await db.commit()
    async with database() as db:
        read_output = await video_version_read(db, owner_id=uid, output_id=ids[0])
        assert read_output["composition_version_id"] == str(version.id)
        assert read_output["is_current"] is False
        assert await db.scalar(select(WorkflowRun.id).where(
            WorkflowRun.context["version_ref"]["composition_id"].as_string() == str(comp.id),
        )) == run_id
        from app.tools.video.production import capture_video_render
        from app.models.schemas import RenderStatus
        await capture_video_render(db, ids[0])
        assert await db.scalar(select(CreditTransaction.id).where(CreditTransaction.kind == "capture")) is None
        output = await db.get(Output, ids[0])
        output.render_status = RenderStatus.COMPLETED
        output.files = {"video": "acceptance.mp4"}
        step = await db.get(WorkflowStep, step_id)
        step.output_refs = [str(output.id)]
        await db.flush()
        from app.chat.trigger_turn import _run_review_snapshot

        review_lines, refs = await _run_review_snapshot(db, run)
        assert isinstance(review_lines, list) and refs == [str(output.id)]
        await capture_video_render(db, ids[0])
        await capture_video_render(db, ids[0])
        captures = list((await db.scalars(select(CreditTransaction).where(CreditTransaction.kind == "capture"))).all())
        assert len(captures) == 1 and captures[0].amount == -quote.total[1]
        from app.models.schemas import WorkflowStatus
        run = await db.get(WorkflowRun, run_id)
        run.status = WorkflowStatus.COMPLETED
        approved_row = await db.get(Message, approved.id)
        approved_row.turn_state = "settled"
        delivery = Message(
            conversation_id=approved_row.conversation_id, role="assistant", content="Completed", seq=3,
            intent={"trigger": "run_completed", "ref": str(run_id), "output_refs": [str(output.id)]},
        )
        db.add(delivery)
        await db.flush()
        project = await db.get(Project, pid)
        repeated = await short_video_confirmation(db, project, approved_row.conversation_id, "Yes", None)
        assert repeated["action"] == "already_started"
        assert repeated["run_id"] == str(run_id)
        assert repeated["run_status"] == "completed"
        assert repeated["output_refs"] == [str(output.id)]
        assert repeated["delivery_message_id"] == str(delivery.id)

OP = TypeAdapter(Op)


async def test_revision_uses_its_own_presentation_when_another_work_was_shown(database):
    """Two works in one Chat must not turn an approved revision into a read loop."""
    from app.chat.video_turn_seats import stamp_video_presentation, video_proposal_guard
    from app.editing.service import video_version_read
    from app.models.schemas import TaskItem
    from app.models.tables import Conversation, Message

    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    first, v1, _ = await _create(database, uid, pid, name="Morning")
    _, other, _ = await _create(database, uid, pid, name="Night")
    async with database() as db:
        project = await db.get(Project, pid)
        conversation = Conversation(user_id=uid, project_id=pid)
        db.add(conversation)
        await db.flush()
        for seq, version in enumerate((v1, other), 1):
            shown = Message(conversation_id=conversation.id, role="assistant", content="Storyboard", seq=seq)
            db.add(shown)
            await db.flush()
            read = await video_version_read(db, owner_id=uid, version_id=version.id)
            stamp_video_presentation(project, shown, read)
            shown.blocks = [{**block, "presentation_complete": True} for block in shown.blocks]
            project.pending_brief = {**project.pending_brief, "video_presentation": {
                **project.pending_brief["video_presentation"], "presentation_complete": True,
            }}
        approval = Message(conversation_id=conversation.id, role="user", content="Revise Morning and make it", seq=3)
        db.add(approval)
        await db.flush()
        base = await video_version_read(db, owner_id=uid, version_id=v1.id)
        revised = await apply_composition_edits(db, owner_id=uid, composition_id=first.id,
            base_version_id=v1.id, ops=[set_intent("A brighter morning")])
        pending = await video_version_read(db, owner_id=uid, version_id=revised[1].id)
        pending["previous_version_ref"] = base["base_ref"]
        task = TaskItem(tool="produce_video", params={"version_ref": pending["base_ref"]})
        assert "export_video" in video_proposal_guard([task])
        assert "authorized_revision_message_id" not in pending
        assert project.pending_brief["video_presentation"]["composition_id"] == str(other.composition_id)


def set_intent(intent: str) -> Op:
    return OP.validate_python(
        {"op": "update_scene", "scene_id": "scn_open", "intent": intent}
    )


@pytest_asyncio.fixture
async def database():
    name = f"rep_editing_test_{uuid4().hex[:12]}"
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


async def _user(factory, **kwargs):
    async with factory() as db:
        user = User(email=f"{uuid4()}@example.test", name="test", **kwargs)
        db.add(user)
        await db.commit()
        return user.id


async def _project(factory, user_id, title="chat"):
    async with factory() as db:
        project = Project(user_id=user_id, title=title)
        db.add(project)
        await db.commit()
        return project.id


async def _snapshots(factory, owner_id):
    async with factory() as db:
        db.add_all(
            [
                SourceSnapshot(
                    id=IMG_SNAPSHOT,
                    owner_id=owner_id,
                    kind="image",
                    storage_key="snapshots/img.png",
                    digest=IMG_DIGEST,
                    duration_ticks=None,
                ),
                SourceSnapshot(
                    id=AUDIO_SNAPSHOT,
                    owner_id=owner_id,
                    kind="audio",
                    storage_key="snapshots/bed.wav",
                    digest=AUDIO_DIGEST,
                    duration_ticks=FOUR_S_TICKS,
                ),
            ]
        )
        await db.commit()


async def _create(factory, owner_id, project_id, request_id=None, name="sample"):
    async with factory() as db:
        return await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=project_id,
            ops=creation_ops(),
            request_id=request_id,
            name=name,
        )


def test_design_save_requires_an_existing_draft_and_no_new_content_writes():
    from app.tools.video.design import CompositionDesignVideoArgs

    draft_ref = {"draft_id": "draft-1", "draft_digest": "d" * 64}
    with pytest.raises(ValueError, match="requires an existing draft_ref"):
        CompositionDesignVideoArgs.model_validate({"save": True})
    for writes in (
        {"settings": {"width": 1920, "height": 1080}},
        {"scenes": [{"scene_id": "scene-1", "range": {"start": 0, "end": 90000}, "intent": "opening"}]},
    ):
        with pytest.raises(ValueError, match="only commits the existing draft"):
            CompositionDesignVideoArgs.model_validate({"save": True, "draft_ref": draft_ref, **writes})
    final = CompositionDesignVideoArgs.model_validate({"save": True, "draft_ref": draft_ref})
    assert final.save and not final.entity_writes().has_changes()


async def test_skill_assembly_failure_saves_no_version_and_preserves_draft(database, monkeypatch):
    from types import SimpleNamespace

    from app.agents.working_drafts import WorkingDraftRejected
    from app.chat.video_turn_seats import design_video_seat
    from app.tools.video import design as design_module

    monkeypatch.setattr(design_module, "AsyncSessionLocal", database)
    uid = await _user(database)
    pid = await _project(database, uid)
    args = design_module.CompositionDesignVideoArgs.model_validate({
        "scene_plan": [{"scene_id": "lead", "intent": "Lead with the actual source"}],
        "skill_resource": {
            "resource_id": "missing-generator",
            "scene_id": "lead",
            "track_id": "trk_main",
            "clip_id": "clp_missing",
        },
    })

    async def fail_assembly(_db, **_kwargs):
        raise design_module.CandidateDesignError(
            "declared Generator resource is unavailable",
            errors=[{"loc": ["skill_resource"], "type": "resource_unavailable", "msg": "missing"}],
        )

    monkeypatch.setattr(design_module, "_place_skill_generator", fail_assembly)
    with pytest.raises(design_module.CandidateDesignError, match="unavailable"):
        await design_module.design_video(
            owner_id=uid, project_id=pid, args=args, request_id="assembly-failure",
        )
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 0

    read, outcome = await design_video_seat(
        project=SimpleNamespace(user_id=uid, id=pid),
        args=args,
        request_id="assembly-failure-chat",
    )
    assert read is None
    assert isinstance(outcome, WorkingDraftRejected)
    assert outcome.arguments["content"]["scenes"][0]["scene_id"] == "lead"
    assert outcome.arguments["design"]["authoring"] == "high_level_scene"


async def test_scene_plan_rejects_unknown_and_foreign_snapshots(database, monkeypatch):
    from app.tools.video import design as design_module

    monkeypatch.setattr(design_module, "AsyncSessionLocal", database)
    uid = await _user(database)
    pid = await _project(database, uid)
    stranger = await _user(database)
    foreign_id = uuid4()
    async with database() as db:
        db.add(SourceSnapshot(
            id=foreign_id,
            owner_id=stranger,
            kind="video",
            storage_key="sources/foreign.mp4",
            digest="f" * 64,
            duration_ticks=900000,
            meta={"media": {"width": 1280, "height": 720}},
        ))
        await db.commit()

    for snapshot_id in (uuid4(), foreign_id):
        args = design_module.CompositionDesignVideoArgs.model_validate({
            "scene_plan": [{"scene_id": "lead", "intent": "Use the supplied video"}],
            "source_ids": [str(snapshot_id)],
        })
        with pytest.raises(design_module.DesignError, match="not accessible"):
            await design_module.design_video(
                owner_id=uid, project_id=pid, args=args, request_id=None,
            )
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 0


async def test_high_level_constraints_survive_scene_continuation_and_save(database, monkeypatch):
    from app.agents.working_drafts import WorkingDraftUpdated
    from app.editing.service import format_storyboard_text
    from app.editing.store import content_of
    from app.tools.video import design as design_module

    monkeypatch.setattr(design_module, "AsyncSessionLocal", database)
    uid = await _user(database)
    cases = (
        ("Make a promo from this website", (1920, 1080), "#F8FAFC"),
        ("制作宣传片，画幅 9:16", (1080, 1920), "#F8FAFC"),
    )
    for index, (request, dimensions, background) in enumerate(cases):
        pid = await _project(database, uid, title=f"constraints-{index}")
        initial = design_module.CompositionDesignVideoArgs.model_validate({
            "name": f"Constraints {index}",
            "scene_plan": [{"scene_id": "lead", "intent": "Introduce the real product"}],
        })
        planned = await design_module.design_video(
            owner_id=uid, project_id=pid, args=initial, request_id=None,
            request_context={"user_text": request},
        )
        assert isinstance(planned, WorkingDraftUpdated)
        scene = design_module.CompositionDesignVideoArgs.model_validate({
            "draft_ref": {"draft_id": "direct-draft", "draft_digest": "d" * 64},
            "scene": {"scene_id": "lead", "headline": "A defensible valuation"},
        })
        scene.bind_working_draft(planned.arguments)
        written = await design_module.design_video(
            owner_id=uid, project_id=pid, args=scene, request_id=None,
            request_context={"user_text": "继续当前草稿"},
        )
        assert isinstance(written, WorkingDraftUpdated)
        assert written.arguments["design"]["user_constraints"] == (
            {"aspect": "9:16"} if index else {}
        )
        invalid_focus = design_module.CompositionDesignVideoArgs.model_validate({
            "draft_ref": {"draft_id": "direct-draft", "draft_digest": "d" * 64},
            "focus_clip_id": "clp_missing", "focus_element_id": "missing-element",
        })
        invalid_focus.bind_working_draft(written.arguments)
        with pytest.raises(design_module.DesignError, match="existing web Clip"):
            await design_module.design_video(
                owner_id=uid, project_id=pid, args=invalid_focus, request_id=None,
                request_context={"user_text": "修正当前取景"},
            )
        save = design_module.CompositionDesignVideoArgs.model_validate({
            "save": True,
            "draft_ref": {"draft_id": "direct-draft", "draft_digest": "d" * 64},
        })
        save.bind_working_draft(written.arguments)
        saved = await design_module.design_video(
            owner_id=uid, project_id=pid, args=save, request_id=f"constraint-save-{index}",
            request_context={"user_text": "保存当前草稿"},
        )
        assert saved["version"] == 1 and saved["composition_version_id"]
        assert "Music: none in this saved version." in format_storyboard_text(saved)
        async with database() as db:
            versions = list((await db.scalars(
                select(CompositionVersion).join(Composition, CompositionVersion.composition_id == Composition.id)
                .where(Composition.origin_project_id == pid)
            )).all())
            assert len(versions) == 1
            content = content_of(versions[0])
            assert (content.settings.width, content.settings.height) == dimensions
            assert content.settings.background == background


async def test_focus_repair_loads_music_facts_independently(database, monkeypatch):
    from app.agents.working_drafts import WorkingDraftUpdated
    from app.tools.video import design as design_module

    monkeypatch.setattr(design_module, "AsyncSessionLocal", database)
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    web_id = uuid4()
    web_digest = "w" * 64
    view_digest = "v" * 64
    async with database() as db:
        db.add(SourceSnapshot(
            id=web_id,
            owner_id=uid,
            kind="web",
            storage_key="sources/web.json",
            digest=web_digest,
            duration_ticks=None,
            meta={"views": [{
                "view_id": "view-0", "storage_key": "sources/view.png", "digest": view_digest,
                "width": 1440, "height": 900,
                "elements": [{"id": "hero", "kind": "heading", "x": 0.5, "y": 0.4, "w": 0.4, "h": 0.2}],
            }]},
        ))
        await db.commit()

    planned = await design_module.design_video(
        owner_id=uid,
        project_id=pid,
        args=design_module.CompositionDesignVideoArgs.model_validate({
            "scene_plan": [{"scene_id": "lead", "intent": "Show the product"}],
            "source_ids": [str(web_id), str(AUDIO_SNAPSHOT)],
            "music_snapshot_id": str(AUDIO_SNAPSHOT),
        }),
        request_id=None,
    )
    scene = design_module.CompositionDesignVideoArgs.model_validate({
        "draft_ref": {"draft_id": "direct-draft", "draft_digest": "d" * 64},
        "scene": {
            "scene_id": "lead", "snapshot_id": str(web_id), "view_id": "view-0",
            "source_motion": "hold", "headline": "Product",
        },
    })
    scene.bind_working_draft(planned.arguments)
    written = await design_module.design_video(
        owner_id=uid,
        project_id=pid,
        args=scene,
        request_id=None,
    )
    for args in (
        planned,
        written,
    ):
        assert isinstance(args, WorkingDraftUpdated)

    focus = design_module.CompositionDesignVideoArgs.model_validate({
        "draft_ref": {"draft_id": "direct-draft", "draft_digest": "d" * 64},
        "focus_clip_id": "clp_lead_source",
        "focus_element_id": "hero",
    })
    focus.bind_working_draft(written.arguments)
    repaired = await design_module.design_video(
        owner_id=uid, project_id=pid, args=focus, request_id=None,
        request_context={"user_text": "修正当前取景"},
    )
    assert isinstance(repaired, WorkingDraftUpdated)
    tracks = repaired.arguments["content"]["timeline"]["tracks"]
    assert sum(track["track_id"] == "trk_music" for track in tracks) == 1
    source = next(
        clip for track in tracks for clip in track["clips"] if clip["clip_id"] == "clp_lead_source"
    )
    assert source["animations"]


async def test_copy_reference_errors_identify_all_mismatches_and_native_candidates(database):
    from app.editing.store import content_of
    from app.tools.video.design import (
        CandidateDesignError,
        CompositionCopyReference,
        _direct_copy_evidence,
    )

    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    _comp, version, _ = await _create(database, uid, pid)
    async with database() as db:
        source = await db.get(SourceSnapshot, IMG_SNAPSHOT)
        source.meta = {"lines": [
            {"line_id": "line_frame", "text": "Frame"},
            {"line_id": "line_missing", "text": "Missing"},
        ]}
        await db.flush()
        candidate = content_of(version)
        text_object = next(
            clip.object
            for track in candidate.timeline.tracks
            for clip in track.clips
            if clip.object.kind == "text"
        )
        text_object.text = "01   Frame"
        inferred = CompositionCopyReference(snapshot_id=IMG_SNAPSHOT, line_id="line_frame")
        text_object.text = "Frame"
        assert await _direct_copy_evidence(
            db, owner_id=uid, references=[inferred], candidate=candidate,
        ) == [{
            "text": "Frame", "snapshot_id": str(IMG_SNAPSHOT), "line_id": "line_frame", "quote": "Frame",
        }]
        text_object.text = "01   Frame"
        references = [
            CompositionCopyReference(
                text=text, snapshot_id=IMG_SNAPSHOT, snapshot_digest=IMG_DIGEST, line_id=line_id,
            )
            for text, line_id in (("Frame", "line_frame"), ("Missing", "line_missing"))
        ]
        with pytest.raises(CandidateDesignError) as raised:
            await _direct_copy_evidence(
                db, owner_id=uid, references=references, candidate=candidate,
            )
    assert [error["loc"] for error in raised.value.issues] == [
        ["copy_references", 0, "text"], ["copy_references", 1, "text"],
    ]
    assert raised.value.issues[0]["candidate_text_objects"] == [
        {"object_id": "obj_title", "text": "01   Frame"},
    ]
    assert raised.value.issues[1]["reference_text"] == "Missing"
    assert raised.value.issues[1]["candidate_text_objects"] == []


async def test_generic_design_verbatim_copy_rejects_extra_or_repeated_text(database):
    from app.editing.store import content_of
    from app.tools.video.design import (
        CandidateDesignError,
        CompositionDesignVideoArgs,
        _validate_direct_design,
    )

    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    _, version, _ = await _create(database, uid, pid)
    content = content_of(version)
    title = next(
        clip.object.text
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.object.kind == "text"
    )
    payload = content.model_dump(mode="json")
    args = CompositionDesignVideoArgs(verbatim_copy=[title])
    assert _validate_direct_design(args=args, composition=payload) == content
    args = CompositionDesignVideoArgs(verbatim_copy=[title, title])
    with pytest.raises(CandidateDesignError) as rejected:
        _validate_direct_design(args=args, composition=payload)
    assert rejected.value.issues[0]["type"] == "verbatim_copy_mismatch"
    assert rejected.value.issues[0]["actual"] == [title]


async def test_two_compositions_in_one_chat_are_independent(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp_a, ver_a1, _ = await _create(database, uid, pid, name="film A")
    comp_b, ver_b1, _ = await _create(database, uid, pid, name="film B")
    assert comp_a.id != comp_b.id and ver_a1.id != ver_b1.id

    # Edit A; B's head and content must not move.
    async with database() as db:
        _, ver_a2, _ = await apply_composition_edits(
            db,
            owner_id=uid,
            composition_id=comp_a.id,
            base_version_id=ver_a1.id,
            ops=[set_intent("new hook")],
        )
    async with database() as db:
        a = await db.get(Composition, comp_a.id)
        b = await db.get(Composition, comp_b.id)
        assert a.current_version_id == ver_a2.id
        assert b.current_version_id == ver_b1.id
        b_head = await db.get(CompositionVersion, b.current_version_id)
        assert b_head.scenes[0]["intent"] == "opening"


async def test_cross_chat_concurrent_edit_never_overwrites(database):
    uid = await _user(database)
    pid_a = await _project(database, uid, title="chat A")
    await _project(database, uid, title="chat B")
    await _snapshots(database, uid)
    comp, ver1, _ = await _create(database, uid, pid_a)

    async def edit(intent: str):
        async with database() as db:
            return await apply_composition_edits(
                db,
                owner_id=uid,
                composition_id=comp.id,
                base_version_id=ver1.id,
                ops=[set_intent(intent)],
            )

    # Two Chats edit the same Composition off the same base — one lands,
    # the other MUST lose with StaleBase, never overwrite.
    results = await asyncio.gather(edit("from chat A"), edit("from chat B"), return_exceptions=True)
    wins = [r for r in results if not isinstance(r, Exception)]
    losses = [r for r in results if isinstance(r, StaleBase)]
    assert len(wins) == 1 and len(losses) == 1, results

    async with database() as db:
        head = await db.get(Composition, comp.id)
        assert head.current_version_id == wins[0][1].id
        n = await db.scalar(
            select(func.count()).select_from(CompositionVersion).where(
                CompositionVersion.composition_id == comp.id
            )
        )
        assert n == 2  # v1 + the one winner — the loser left no row


async def test_request_retry_replays_and_key_reuse_is_refused(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    request_id = uuid4().hex
    comp, ver, replayed = await _create(database, uid, pid, request_id=request_id)
    assert not replayed and ver.version == 1

    # Timeout retry: same key, same payload → the committed version, no write.
    comp2, ver2, replayed2 = await _create(database, uid, pid, request_id=request_id)
    assert replayed2 and ver2.id == ver.id and comp2.id == comp.id

    async with database() as db:
        n = await db.scalar(select(func.count()).select_from(CompositionVersion))
        assert n == 1

    # Same key, different payload → refused, never silently re-executed.
    async with database() as db:
        with pytest.raises(RequestMismatch):
            await apply_composition_edits(
                db,
                owner_id=uid,
                composition_id=comp.id,
                base_version_id=ver.id,
                request_id=request_id,
                ops=[set_intent("mutated")],
            )


async def test_temporal_edit_with_stale_base_ref_creates_no_version(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, base, _ = await _create(database, uid, pid)
    async with database() as db:
        await apply_composition_edits(
            db, owner_id=uid, composition_id=comp.id,
            base_version_id=base.id, base_digest=base.content_digest,
            ops=[set_intent("newer head")],
        )
    temporal = OP.validate_python({
        "op": "temporal_edit", "action": "time_map",
        "target": {"kind": "timeline"}, "scale": 0.5, "source_policy": "crop_1x",
    })
    async with database() as db:
        with pytest.raises(StaleBase):
            await apply_composition_edits(
                db, owner_id=uid, composition_id=comp.id,
                base_version_id=base.id, base_digest=base.content_digest, ops=[temporal],
            )
    async with database() as db:
        assert await db.scalar(
            select(func.count()).select_from(CompositionVersion)
        ) == 2


@pytest.mark.parametrize("changed_field", ["composition_id", "base_version_id", "base_digest"])
async def test_request_identity_covers_edit_target_and_base(database, changed_field):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, base, _ = await _create(database, uid, pid)
    other, other_base, _ = await _create(database, uid, pid)
    request_id = uuid4().hex
    request = dict(
        owner_id=uid, composition_id=comp.id, base_version_id=base.id,
        base_digest=base.content_digest, request_id=request_id,
        ops=[set_intent("revised hook")],
    )
    async with database() as db:
        _, result, _ = await apply_composition_edits(db, **request)
    changed = dict(request)
    if changed_field == "composition_id":
        changed.update(composition_id=other.id, base_version_id=other_base.id)
    elif changed_field == "base_version_id":
        changed[changed_field] = result.id
    else:
        changed[changed_field] = "f" * 64
    async with database() as db:
        with pytest.raises(RequestMismatch):
            await apply_composition_edits(db, **changed)
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 3


@pytest.mark.parametrize("changed_field", ["origin_project_id", "name"])
async def test_create_request_identity_covers_context(database, changed_field):
    uid = await _user(database)
    pid = await _project(database, uid)
    other_pid = await _project(database, uid)
    await _snapshots(database, uid)
    request = dict(
        owner_id=uid, origin_project_id=pid, name="original",
        request_id=uuid4().hex, ops=creation_ops(),
    )
    async with database() as db:
        await apply_composition_edits(db, **request)
    changed = dict(request)
    changed[changed_field] = other_pid if changed_field == "origin_project_id" else "different"
    async with database() as db:
        with pytest.raises(RequestMismatch):
            await apply_composition_edits(db, **changed)
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 1


@pytest.mark.parametrize("mode", ["create", "edit"])
async def test_concurrent_identical_request_replays(database, monkeypatch, mode):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    request = dict(owner_id=uid, request_id=uuid4().hex)
    if mode == "edit":
        comp, base, _ = await _create(database, uid, pid)
        request.update(
            composition_id=comp.id, base_version_id=base.id,
            base_digest=base.content_digest, ops=[set_intent("one edit")],
        )
    else:
        request.update(origin_project_id=pid, ops=creation_ops())

    # Both transactions must observe the initial idempotency miss BEFORE
    # either proceeds. This forces the lock/unique-index recovery path,
    # rather than allowing a sequential retry to pass by scheduler luck.
    barrier = asyncio.Barrier(2)

    async def submit():
        async with database() as db:
            execute = db.execute
            first = True

            async def synchronized_execute(statement, *args, **kwargs):
                nonlocal first
                result = await execute(statement, *args, **kwargs)
                if first:
                    first = False
                    await barrier.wait()
                return result

            monkeypatch.setattr(db, "execute", synchronized_execute)
            return await apply_composition_edits(db, **request)

    results = await asyncio.wait_for(asyncio.gather(submit(), submit()), timeout=10)
    assert results[0][0].id == results[1][0].id
    assert results[0][1].id == results[1][1].id
    assert sorted(result[2] for result in results) == [False, True]
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 1
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == (
            2 if mode == "edit" else 1
        )


@pytest.mark.parametrize("origin", ["foreign", "missing"])
async def test_create_requires_owned_origin_chat(database, origin):
    uid = await _user(database)
    await _snapshots(database, uid)
    pid = await _project(database, await _user(database)) if origin == "foreign" else uuid4()
    async with database() as db:
        with pytest.raises(PermissionDenied):
            await apply_composition_edits(
                db, owner_id=uid, origin_project_id=pid, ops=creation_ops(),
            )
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 0
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 0


async def test_permission_law(database):
    owner = await _user(database)
    stranger = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, ver, _ = await _create(database, owner, pid)

    async with database() as db:
        # A stranger cannot edit, read, or reference the owner's snapshots.
        with pytest.raises(PermissionDenied):
            await apply_composition_edits(
                db,
                owner_id=stranger,
                composition_id=comp.id,
                base_version_id=ver.id,
                ops=[set_intent("hijack")],
            )
        with pytest.raises(PermissionDenied):
            await get_video_version(db, owner_id=stranger, composition_id=comp.id)

    # A stranger's own create binding the OWNER's snapshots is refused.
    stranger_pid = await _project(database, stranger, title="stranger chat")
    async with database() as db:
        with pytest.raises(PermissionDenied):
            await apply_composition_edits(
                db,
                owner_id=stranger,
                origin_project_id=stranger_pid,
                ops=creation_ops(),  # binds the OWNER's snapshots
            )


async def test_failed_batch_lands_no_version(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, ver1, _ = await _create(database, uid, pid)

    async with database() as db:
        with pytest.raises(ContentValidationError):
            await apply_composition_edits(
                db,
                owner_id=uid,
                composition_id=comp.id,
                base_version_id=ver1.id,
                ops=[
                    # valid op …
                    set_intent("fine"),
                    # … followed by a batch-poisoning op: unbound source digest.
                    OP.validate_python(
                        {
                            "op": "add_clip",
                            "track_id": "trk_main",
                            "clip": {
                                "clip_id": "clp_rogue",
                                "range": {"start": 0, "end": 90000},
                                "source": {
                                    "snapshot_id": str(IMG_SNAPSHOT),
                                    "snapshot_digest": "f" * 64,
                                },
                                "object": {
                                    "kind": "image",
                                    "object_id": "obj_rogue",
                                    "layout": {"x": 0, "y": 0, "width": 100, "height": 100},
                                },
                            },
                        }
                    ),
                ],
            )
    async with database() as db:
        head = await db.get(Composition, comp.id)
        assert head.current_version_id == ver1.id  # the head never moved
        n = await db.scalar(
            select(func.count()).select_from(CompositionVersion).where(
                CompositionVersion.composition_id == comp.id
            )
        )
        assert n == 1


async def test_queue_render_pins_output_lineage(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, ver, _ = await _create(database, uid, pid)

    async with database() as db:
        project = await db.get(Project, pid)
        composition = await db.get(Composition, comp.id)
        version = await db.get(CompositionVersion, ver.id)
        output = await queue_composition_render(
            db, project=project, composition=composition, version=version
        )
        await db.commit()
        output_id = output.id

    async with database() as db:
        row = await db.get(Output, output_id)
        # §2.2 three-fact pin + the work anchor law (work_id = Composition.id).
        assert row.composition_id == comp.id
        assert row.composition_version_id == ver.id
        assert row.payload["composition_digest"] == ver.content_digest
        assert row.work_id == comp.id
        assert row.type == "video"
        assert row.render_status is not None and row.render_status.value == "pending"
        spec = row.render_spec
        assert spec["family"] == "video"
        assert spec["provenance"] == {
            "composition_id": str(comp.id),
            "composition_version_id": str(ver.id),
            "content_digest": ver.content_digest,
        }
        # 4s @ 30fps — the spec's quantized facts.
        assert spec["duration_frames"] == 120
        assert spec["fps"] == {"num": 30, "den": 1}

        # The Output DTO (§10.3 read face) carries the lineage and the
        # video spec survives serialization as its own envelope.
        from app.models.schemas import OutputResponse

        dto = OutputResponse.model_validate(row)
        assert dto.composition_id == comp.id
        assert dto.composition_version_id == ver.id
        assert dto.render_spec is not None and dto.render_spec.family == "video"
        assert dto.payload["composition_digest"] == ver.content_digest

        # Cross-owner produce is refused (below, with a foreign project).
    # A project owned by a different user must not produce the composition.
    stranger = await _user(database)
    async with database() as db:
        foreign_project = Project(user_id=stranger, title="foreign")
        db.add(foreign_project)
        await db.flush()
        composition = await db.get(Composition, comp.id)
        version = await db.get(CompositionVersion, ver.id)
        with pytest.raises(PermissionDenied):
            await queue_composition_render(
                db, project=foreign_project, composition=composition, version=version
            )


async def test_nonexistent_snapshot_bind_rejected(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    ghost = uuid4()
    async with database() as db:
        ops = creation_ops()
        bind = OP.validate_python({"op": "bind_source", "snapshot_id": str(ghost)})
        with pytest.raises(EditError, match="does not exist"):
            await apply_composition_edits(
                db,
                owner_id=uid,
                origin_project_id=pid,
                ops=[*ops, bind],
            )



async def test_creative_state_is_versioned_and_inherited_without_output_duplication(database):
    from app.editing.store import content_of
    from app.models.schemas import (
        BrandProfile,
        BrandSourceRef,
        Brief,
        BriefSlot,
        BriefSlotSource,
        CreativeState,
        seal_creative_state,
    )

    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, original, _ = await _create(database, uid, pid)
    state = seal_creative_state(CreativeState(
        brief=Brief(
            purpose=BriefSlot(value="website", source=BriefSlotSource.USER_STATED),
            target_seconds=BriefSlot(value=60, source=BriefSlotSource.USER_STATED),
        ),
        brand_profile=BrandProfile(
            extractor_version="brand-test-v1",
            source_refs=[BrandSourceRef(snapshot_id=str(IMG_SNAPSHOT), digest=IMG_DIGEST)],
            content_digest="d" * 64,
        ),
    ))
    async with database() as db:
        content = content_of(original).model_copy(update={"creative_state": state})
        _, versioned, _ = await apply_composition_edits(
            db,
            owner_id=uid,
            composition_id=comp.id,
            base_version_id=original.id,
            base_digest=original.content_digest,
            content=content,
        )
        assert versioned.creative_state["brief"]["purpose"]["value"] == "website"
        assert versioned.creative_state["brand_profile"]["extractor_version"] == "brand-test-v1"
        assert versioned.creative_state["content_digest"] == state.content_digest
        _, revised, _ = await apply_composition_edits(
            db,
            owner_id=uid,
            composition_id=comp.id,
            base_version_id=versioned.id,
            base_digest=versioned.content_digest,
            ops=[set_intent("only the scene changes")],
        )
        assert revised.creative_state == versioned.creative_state
        assert revised.content_digest != versioned.content_digest
        original_row = await db.get(CompositionVersion, original.id)
        assert original_row.creative_state is None
        read = content_of(revised)
        assert read.creative_state is not None
        assert read.creative_state.brief.target_seconds.value == 60
        assert read.creative_state.brand_profile.source_refs[0].digest == IMG_DIGEST


async def test_design_video_injects_pending_creative_state_into_first_saved_version(database, monkeypatch):
    from app.agents.working_drafts import WorkingDraftUpdated
    from app.editing.store import content_of
    from app.models.schemas import Brief, BriefSlot, BriefSlotSource, CreativeState, PendingPlan, seal_creative_state
    from app.tools.video import design as design_module

    monkeypatch.setattr(design_module, "AsyncSessionLocal", database)
    uid = await _user(database)
    pid = await _project(database, uid)
    brief = Brief(
        purpose=BriefSlot(value="website", source=BriefSlotSource.USER_STATED),
        target_seconds=BriefSlot(value=60, source=BriefSlotSource.USER_STATED),
        aspect=BriefSlot(value="16:9", source=BriefSlotSource.USER_STATED),
    )
    pending = PendingPlan(
        brief=brief,
        creative_state=seal_creative_state(CreativeState(brief=brief)),
    )
    context = {"brief": pending.model_dump(mode="json"), "user_text": "保存官网宣传片草稿"}
    planned = await design_module.design_video(
        owner_id=uid,
        project_id=pid,
        args=design_module.CompositionDesignVideoArgs.model_validate({
            "scene_plan": [{"scene_id": "lead", "intent": "Introduce the brand"}],
        }),
        request_id=None,
        request_context=context,
    )
    assert isinstance(planned, WorkingDraftUpdated)
    scene = design_module.CompositionDesignVideoArgs.model_validate({
        "draft_ref": {"draft_id": "direct-draft", "draft_digest": "d" * 64},
        "scene": {"scene_id": "lead", "headline": "Evidence for everyone"},
    })
    scene.bind_working_draft(planned.arguments)
    written = await design_module.design_video(
        owner_id=uid,
        project_id=pid,
        args=scene,
        request_id=None,
        request_context=context,
    )
    save = design_module.CompositionDesignVideoArgs.model_validate({
        "save": True,
        "draft_ref": {"draft_id": "direct-draft", "draft_digest": "d" * 64},
    })
    save.bind_working_draft(written.arguments)
    saved = await design_module.design_video(
        owner_id=uid,
        project_id=pid,
        args=save,
        request_id=f"creative-state-{uuid4()}",
        request_context=context,
    )
    assert saved["creative_state"]["brief"]["purpose"]["value"] == "website"
    assert saved["creative_state"]["brief"]["target_seconds"]["value"] == 60
    async with database() as db:
        versions = list((await db.scalars(
            select(CompositionVersion).join(Composition, CompositionVersion.composition_id == Composition.id)
            .where(Composition.origin_project_id == pid)
        )).all())
        assert len(versions) == 1
        content = content_of(versions[0])
        assert content.creative_state is not None
        assert content.creative_state.brief.aspect.value == "16:9"
        assert (content.settings.width, content.settings.height) == (1920, 1080)
