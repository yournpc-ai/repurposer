import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.chat import editor_media, service
from app.models.schemas import OptionAnswerRequest, ChatTurnStopRequest
from app.models.tables import Conversation, CreditTransaction, Message, Project, User, WorkflowRun, WorkflowStep
from app.tools.music.score import GenerateMusicArgs
from test.core.test_compositions import _create, _project, _snapshots, _user


@pytest.mark.asyncio
async def test_native_music_request_replay_stop_and_permission(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "cached_music_preparation", AsyncMock(return_value=None))
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, version, _ = await _create(database, owner, pid)
    args = GenerateMusicArgs(style="ambient", duration_seconds=4)
    async with database() as db:
        project = await db.get(Project, pid)
        convo = Conversation(user_id=owner, project_id=pid)
        db.add(convo)
        await db.commit()
        async def opening():
            row = await service._create_message(db, convo.id, "user", "Make music")
            row.turn_state = "in_flight"
            await db.commit()
            return SimpleNamespace(project=project, user_id=owner, turn_id=row.id, conversation_id=convo.id,
                                   _video_base_ref={"content_digest": version.content_digest})
        turn = await opening()
        def submit(turn, args=args):
            return editor_media.submit_editor_media(turn, "generate_music", args, comp, version, "call-1")
        twin = await asyncio.gather(submit(turn), submit(turn))
        assert twin[0].workflow_run_id == twin[1].workflow_run_id and twin[0].id == twin[1].id
        with pytest.raises(ValueError, match="different parameters"):
            await submit(turn, args.model_copy(update={"bpm": 92}))
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
        assert await db.scalar(select(func.count()).select_from(WorkflowStep)) == 1
        assert await service.stop_turn_at_visible_frontier(db, turn.turn_id, ChatTurnStopRequest()) == "cancelled"
        assert (await db.get(WorkflowRun, twin[0].workflow_run_id)).status.value == "cancelled"
        assert await db.get(Message, twin[0].id)
        with pytest.raises(service.TurnStopped):
            await submit(turn)
        early = await opening()
        await service.stop_turn_at_visible_frontier(db, early.turn_id, ChatTurnStopRequest())
        with pytest.raises(service.TurnStopped):
            await submit(early)
        user = await db.get(User, owner)
        user.settings = {"confirm_execution": "ask"}
        await db.commit()
        ask = await opening()
        receipt = await submit(ask)
        assert receipt.question["kind"] == "question" and receipt.workflow_run_id is None
        decline, _ = await service.answer_question(db, owner, receipt.id, OptionAnswerRequest(kind="option", option_id="decline"))
        assert decline.intent["media_result"] == {"status": "declined"}
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
        permit = await submit(await opening())
        accepted = await editor_media.answer_media_permission(db, project, permit, True)
        await db.commit()
        assert accepted.workflow_run_id is not None
        assert all(v == 0 for v in await db.scalars(select(CreditTransaction.amount).where(
            CreditTransaction.kind.in_(["hold", "capture", "release"]))))


@pytest.mark.asyncio
async def test_generation_does_not_bind_an_older_version_and_insert_replays(database, monkeypatch):
    from app.chat.editor import InsertAudioArgs, SplitClipArgs, edit_clip
    from app.editing.store import RequestMismatch
    from app.models.tables import CompositionVersion, SourceSnapshot

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "cached_music_preparation", AsyncMock(return_value=None))
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, initial, _ = await _create(database, owner, pid)
    async with database() as db:
        project = await db.get(Project, pid)
        convo = Conversation(user_id=owner, project_id=pid)
        db.add(convo)
        await db.commit()
        opening = await service._create_message(db, convo.id, "user", "Score the opening")
        opening.turn_state = "in_flight"
        audio = SourceSnapshot(owner_id=owner, origin_project_id=pid, kind="audio", storage_key="tone.wav",
                               digest="3"*64, duration_ticks=90000, meta={"origin": {"kind": "programmatic_score"}})
        db.add(audio)
        await db.commit()
    def ref(v):
        return dict(composition_id=str(comp.id), composition_version_id=str(v.id), content_digest=v.content_digest)
    turn = SimpleNamespace(project=project, user_id=owner, turn_id=opening.id, conversation_id=convo.id,
                           _video_base_ref=ref(initial))
    args = GenerateMusicArgs(style="ambient", duration_seconds=1)
    request = await editor_media.submit_editor_media(turn, "generate_music", args, comp, initial, "score")
    async def edit(name, args, cid, base, seen=None):
        async with database() as db:
            return await edit_clip(db, project=project, opening_id=opening.id, conversation_id=convo.id,
                                   name=name, args=args, call_id=cid, base=base, inspected_version=seen)
    saved = await edit("split_clip", SplitClipArgs(clip_id="clp_bg", time=2), "split", ref(initial))
    from uuid import UUID
    async with database() as db:
        newer = await db.get(CompositionVersion, UUID(saved["version_id"]))
        assert audio.id not in [UUID(s["snapshot_id"]) for s in newer.sources]
        assert (await db.get(WorkflowRun, request.workflow_run_id)).status.value == "pending"
    insert = InsertAudioArgs(source_id=audio.id, start_seconds=1, gain_db=-10)
    with pytest.raises(ValueError, match="changed since inspection"):
        await edit("insert_audio", insert, "place", ref(newer), str(initial.id))
    with pytest.raises(RequestMismatch):
        await edit("insert_audio", insert, "score", ref(newer))
    placed = await edit("insert_audio", insert, "place", ref(newer), str(newer.id))
    again = await edit("insert_audio", insert, "place", ref(newer))
    assert again["replayed"] and again["version_id"] == placed["version_id"]
    with pytest.raises(RequestMismatch):
        await edit("insert_audio", insert.model_copy(update={"gain_db": -2}), "place", ref(newer))
    with pytest.raises(ValueError, match="different operation"):
        await editor_media.submit_editor_media(turn, "generate_music", args, comp, initial, "split")
    async with database() as db:
        final = await db.get(CompositionVersion, UUID(placed["version_id"]))
        assert final.base_version_id == newer.id and final.version == 3
        other_project_id = await _project(database, owner)
        # A different project's source remains forbidden to a newly issued insert.
        foreign = SourceSnapshot(owner_id=owner, origin_project_id=other_project_id, kind="audio",
                                 storage_key="foreign", digest="5"*64, duration_ticks=90000)
        db.add(foreign)
        await db.commit()
    with pytest.raises(ValueError, match="current project"):
        await edit("insert_audio", insert.model_copy(update={"source_id": foreign.id}), "foreign", ref(final))


@pytest.mark.asyncio
async def test_voice_credit_shortfall_and_unknown_original_do_not_resubmit(database, monkeypatch):
    from app.chat.editor import GenerateVoiceArgs
    from app.editing.schemas import SpeechObject
    from app.models.tables import VideoNarration, Wallet
    from app.platform.billing import CreditsInsufficientError, get_or_create_wallet
    from app.tools.video import narration_store

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    owner = await _user(database)
    pid = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, pid)
        user = await db.get(User, owner)
        user.settings = {"confirm_execution": "auto", "confirm_credits": "never"}
        await get_or_create_wallet(db, owner)
        wallet = await db.get(Wallet, owner)
        wallet.balance = 0
        convo = Conversation(user_id=owner, project_id=pid)
        db.add(convo)
        await db.commit()
        opening = await service._create_message(db, convo.id, "user", "Generate the English recording")
        opening.turn_state = "in_flight"
        await db.commit()
    turn = SimpleNamespace(turn_id=opening.id, user_id=owner, project=project, conversation_id=convo.id)
    voice = GenerateVoiceArgs(text="A fixed studio recording.", language="en")
    permission = None
    async with database() as db:
        try:
            permission = await editor_media.submit_editor_media(turn, "generate_voice", voice, None, None, "voice")
        except CreditsInsufficientError:
            pass
        else:
            assert permission.question
            with pytest.raises(CreditsInsufficientError):
                await editor_media.answer_media_permission(db, project, permission, True)
            await db.rollback()
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 0
        assert await db.scalar(select(func.count()).select_from(CreditTransaction).where(
            CreditTransaction.kind.in_(["hold", "capture"]))) == 0
    speech = SpeechObject(kind="speech", object_id="obj_voice", **voice.model_dump())
    await narration_store.resolve_original(owner, speech, execution_id="submitted-once")
    await narration_store.mark_outcome_unknown(owner, speech, execution_id="submitted-once", error="lost POST response")
    for identity in ("submitted-once", "second-worker"):
        with pytest.raises(narration_store.NarrationOutcomeUnknown):
            await narration_store.resolve_original(owner, speech, execution_id=identity)
    async with database() as db:
        rows = (await db.scalars(select(VideoNarration))).all()
        assert len(rows) == 1 and rows[0].owner_token == "submitted-once:original" and rows[0].status == "unknown"

    # An accepted paid step can report a provider overage. Replaying capture
    # must debit at most the actual authorized reservation, exactly once.
    async with database() as db:
        wallet = await db.get(Wallet, owner)
        if permission is not None:
            await service.answer_question(db, owner, permission.id, OptionAnswerRequest(kind="option", option_id="decline"))
        wallet.balance = 100
        await db.commit()
    second_voice = voice.model_copy(update={"text": "A separate recording."})
    accepted = await editor_media.submit_editor_media(turn, "generate_voice", second_voice, None, None, "paid")
    async with database() as db:
        if accepted.question:
            accepted = await editor_media.answer_media_permission(db, project, accepted, True)
        await db.commit()
        from app.platform.billing import capture_step

        hold = await db.scalar(select(CreditTransaction.amount).where(
            CreditTransaction.idempotency_key == f"run:{accepted.workflow_run_id}:hold"))
        step = await db.scalar(select(WorkflowStep).where(WorkflowStep.run_id == accepted.workflow_run_id))
        step.cost = {"fixed_cost": 500}
        assert hold < 0
        charged = await capture_step(db, user_id=owner, node=step)
        assert charged.amount == hold
        assert await capture_step(db, user_id=owner, node=step) is None


@pytest.mark.asyncio
async def test_export_quote_replay_competing_openings_and_stop(database, monkeypatch):
    from app.chat.editor import ExportVideoArgs
    from app.editing.store import apply_composition_edits
    from test.core.test_compositions import set_intent

    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, version, _ = await _create(database, owner, pid)
    ref = {"composition_id": str(comp.id), "composition_version_id": str(version.id),
           "content_digest": version.content_digest}
    async with database() as db:
        project = await db.get(Project, pid)
        user = await db.get(User, owner)
        user.settings = {"confirm_execution": "ask"}
        convo = Conversation(user_id=owner, project_id=pid)
        db.add(convo)
        await db.commit()

        async def opening():
            row = await service._create_message(db, convo.id, "user", "Export this version.")
            row.turn_state = "in_flight"
            await db.commit()
            return SimpleNamespace(project=project, user_id=owner, turn_id=row.id, conversation_id=convo.id,
                _video_base_ref=ref, _editor_last_preview={**ref, "model_media": ["video"], "mp4_sha256": "a"*64})

        def submit(turn):
            return editor_media.submit_editor_media(turn, "export_video", ExportVideoArgs(), comp, version, "export1")

        early = await opening()
        await service.stop_turn_at_visible_frontier(db, early.turn_id, ChatTurnStopRequest())
        with pytest.raises(service.TurnStopped):
            await submit(early)
        turn = await opening()
        first, duplicate = await asyncio.gather(submit(turn), submit(turn))
        assert first.id == duplicate.id and "MP4" in first.content
        assert not await db.scalar(select(WorkflowRun.id))
        assert not await db.scalar(select(CreditTransaction.id).where(CreditTransaction.kind == "hold"))
        execution = await editor_media.answer_media_permission(db, project, await db.get(Message, first.id), True)
        await db.commit()
        replay = await submit(turn)
        assert replay.workflow_run_id == execution.workflow_run_id
        user.settings = {"confirm_execution": "auto"}
        competing = await opening()
        with pytest.raises(ValueError):
            await submit(competing)
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
        assert await db.scalar(select(func.count()).select_from(CreditTransaction).where(CreditTransaction.kind == "hold")) == 1
        _, newer, _ = await apply_composition_edits(db, owner_id=owner, composition_id=comp.id,
            base_version_id=version.id, ops=[set_intent("Updated while exporting")])
        assert newer.id != version.id
        run = await db.get(WorkflowRun, execution.workflow_run_id)
        assert run.context["version_ref"] == ref
        replay_on_new_head = await editor_media.submit_editor_media(
            turn, "export_video", ExportVideoArgs(), comp, newer, "export1")
        assert replay_on_new_head.id == execution.id
        assert await service.stop_turn_at_visible_frontier(db, turn.turn_id, ChatTurnStopRequest()) == "cancelled"
        assert (await db.get(WorkflowRun, run.id, populate_existing=True)).status.value == "cancelled"
