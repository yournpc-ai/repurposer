"""Chat delivery and media races — infra contracts."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.chat import editor_media, service
from app.models.schemas import ChatTurnStopRequest, OptionAnswerRequest
from app.models.tables import (
    Conversation,
    CreditTransaction,
    MediaJob,
    Message,
    Project,
    User,
)
from app.tools.music.score import GenerateMusicArgs
from test.support.db_helpers import _create, _project, _snapshots, _user

pytestmark = pytest.mark.infra


@pytest.mark.asyncio
async def test_native_music_request_replay_stop_and_permission(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
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
        assert twin[0].intent["media_job"] == twin[1].intent["media_job"] and twin[0].id == twin[1].id
        from app.models.schemas import ChatMessageResponse
        receipt_wire = ChatMessageResponse.model_validate(twin[0]).intent
        assert receipt_wire == {
            "operation": "generate_music", "media_status": "accepted",
            "native_call_id": "call-1", "media_job": twin[0].intent["media_job"],
        }
        with pytest.raises(ValueError, match="different parameters"):
            await submit(turn, args.model_copy(update={"bpm": 92}))
        assert await db.scalar(select(func.count()).select_from(MediaJob)) == 1
        assert await service.stop_turn_at_visible_frontier(db, turn.turn_id, ChatTurnStopRequest()) == "cancelled"
        assert (await db.get(MediaJob, twin[0].intent["media_job"])).status == "cancelled"
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
        ask.db = db
        ask.settled_pending = None
        monkeypatch.setattr(editor_media, "current_call_id", lambda: "call-1")
        observation = await editor_media.generate_media(ask, "generate_music", args, comp, version)
        receipt, settled = ask.outcome
        assert observation.awaiting_authorization and settled is None
        await db.commit()
        assert receipt.question["kind"] == "question"
        decline, _ = await service.answer_question(db, owner, receipt.id, OptionAnswerRequest(kind="option", option_id="decline"))
        assert decline.intent["media_result"] == {"status": "declined"}
        permit = await submit(await opening())
        accepted = await editor_media.answer_media_permission(db, project, permit, True)
        await db.commit()
        assert accepted.intent["media_job"]
        assert all(v == 0 for v in await db.scalars(select(CreditTransaction.amount).where(
            CreditTransaction.kind.in_(["hold", "capture", "release"]))))


@pytest.mark.asyncio
async def test_generation_does_not_bind_an_older_version_and_insert_replays(database, monkeypatch):
    from app.chat.editor import InsertAudioArgs, SplitClipArgs, edit_clip
    from app.editing.store import RequestMismatch
    from app.models.tables import CompositionVersion, SourceSnapshot

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
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
        assert (await db.get(MediaJob, request.intent["media_job"])).status == "queued"
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
async def test_native_remove_clip_preserves_original_and_other_tracks(database, monkeypatch):
    from uuid import UUID

    from app.chat.editor import ClipArgs, InsertAudioArgs, edit_clip
    from app.editing.store import StaleBase
    from app.models.tables import CompositionVersion, SourceSnapshot
    from test.support.composition_fixtures import AUDIO_SNAPSHOT

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, original, _ = await _create(database, owner, pid)
    async with database() as db:
        project = await db.get(Project, pid)
        source = await db.get(SourceSnapshot, AUDIO_SNAPSHOT)
        source.origin_project_id = pid
        conversation = Conversation(user_id=owner, project_id=pid)
        db.add(conversation)
        await db.commit()
        opening = await service._create_message(db, conversation.id, "user", "Add a second take")
        opening.turn_state = "in_flight"
        await db.commit()

    async def edit(name, args, version, call_id, preview=None):
        base = dict(composition_id=str(comp.id), composition_version_id=str(version.id),
                    content_digest=version.content_digest)
        async with database() as db:
            return await edit_clip(db, project=project, opening_id=opening.id, conversation_id=conversation.id,
                                   name=name, args=args, base=base, call_id=call_id, observed_preview=preview)

    duplicate = await edit("insert_audio", InsertAudioArgs(source_id=AUDIO_SNAPSHOT, start_seconds=0),
                           original, "double")
    async with database() as db:
        before = await db.get(CompositionVersion, UUID(duplicate["version_id"]))
        opening = await service._create_message(db, conversation.id, "user", "实际预览疑似叠音的片段，再按证据移除重复。")
        opening.turn_state = "in_flight"
        await db.commit()
    target = ClipArgs(clip_id=duplicate["added_clips"][0])
    with pytest.raises(ValueError, match="Preview the affected window"):
        await edit("remove_clip", target, before, "remove")
    preview = dict(version_id=str(before.id), content_digest=before.content_digest, mp4_sha256="7"*64,
                   windows=[{"start": 4, "end": 5}])
    with pytest.raises(ValueError, match="containing this clip"):
        await edit("remove_clip", target, before, "remove", preview)
    preview["windows"] = [{"start": 0, "end": 4}]
    with pytest.raises(ValueError, match="does not exist"):
        await edit("remove_clip", ClipArgs(clip_id="absent"), before, "missing", preview)
    result = await edit("remove_clip", target, before, "remove", preview)
    replay = await edit("remove_clip", target, before, "remove")
    assert replay["replayed"] and replay["version_id"] == result["version_id"]
    with pytest.raises(StaleBase):
        await edit("remove_clip", target, before, "stale", preview)
    async with database() as db:
        after = await db.get(CompositionVersion, UUID(result["version_id"]))
        def clips(version):
            return {clip["clip_id"]: (track["track_id"], clip)
                    for track in version.timeline["tracks"] for clip in track["clips"]}
        assert after.base_version_id == before.id
        assert clips(before)[target.clip_id][1]["source"] == clips(before)["clp_bed"][1]["source"]
        assert clips(after) == clips(original)


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
        from app.platform.billing import settle_media

        job = await db.get(MediaJob, accepted.intent["media_job"])
        hold = await db.scalar(select(CreditTransaction.amount).where(
            CreditTransaction.idempotency_key == f"media:{job.id}:hold"))
        assert hold == -job.authorized_credits < 0
        with pytest.raises(ValueError, match="exceeds"):
            await settle_media(db, user_id=owner, job_id=job.id, reserved=-hold, charged=1-hold)
        for _ in range(2):
            await settle_media(db, user_id=owner, job_id=job.id, reserved=-hold, charged=-hold)
        assert await db.scalar(select(func.count()).select_from(CreditTransaction).where(
            CreditTransaction.idempotency_key == f"media:{job.id}:capture")) == 1


@pytest.mark.asyncio
async def test_export_quote_replay_competing_openings_and_stop(database, monkeypatch):
    from app.chat.editor import ExportVideoArgs
    from app.editing.store import apply_composition_edits
    from app.models.tables import ExportJob
    from test.support.composition_fixtures import set_intent

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
        assert not await db.scalar(select(CreditTransaction.id).where(CreditTransaction.kind == "hold"))
        permission = await db.get(Message, first.id)
        permission.answer = {"kind": "option", "option_id": "approve"}
        execution = await editor_media.answer_media_permission(db, project, permission, True)
        await db.commit()
        replay = await submit(turn)
        assert replay.id == execution.id
        repeated = await editor_media.submit_editor_media(
            turn, "export_video", ExportVideoArgs(), comp, version, "repeated-same-version")
        assert repeated.id == execution.id
        with pytest.raises(ValueError, match="different parameters"):
            await editor_media.submit_editor_media(
                turn, "generate_music", GenerateMusicArgs(style="ambient", duration_seconds=1),
                comp, version, "repeated-same-version")
        user.settings = {"confirm_execution": "auto"}
        competing = await opening()
        with pytest.raises(ValueError):
            await submit(competing)
        assert await db.scalar(select(func.count()).select_from(ExportJob)) == 1
        assert await db.scalar(select(func.count()).select_from(CreditTransaction).where(CreditTransaction.kind == "hold")) == 1
        _, newer, _ = await apply_composition_edits(db, owner_id=owner, composition_id=comp.id,
            base_version_id=version.id, ops=[set_intent("Updated while exporting")])
        assert newer.id != version.id
        job = await db.get(ExportJob, execution.intent["export_job"])
        assert job.render_spec["provenance"] == ref
        replay_on_new_head = await editor_media.submit_editor_media(
            turn, "export_video", ExportVideoArgs(), comp, newer, "export1")
        assert replay_on_new_head.id == execution.id
        turn._video_base_ref = {**ref, "composition_version_id": str(newer.id), "content_digest": newer.content_digest}
        turn._editor_last_preview = {**turn._video_base_ref, "mp4_sha256": "b" * 64}
        second_version = await editor_media.submit_editor_media(
            turn, "export_video", ExportVideoArgs(), comp, newer, "distinct-export")
        assert second_version.question and "media_permission" in second_version.intent
        assert await db.scalar(select(func.count()).select_from(ExportJob)) == 1
        assert await service.stop_turn_at_visible_frontier(db, turn.turn_id, ChatTurnStopRequest()) == "cancelled"
        assert (await db.get(ExportJob, job.id, populate_existing=True)).status == "cancelled"


@pytest.mark.asyncio
async def test_auto_account_needs_permission_for_unrequested_export(database, monkeypatch):
    from app.chat.editor import ExportVideoArgs

    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)
    await _snapshots(database, owner)
    comp, version, _ = await _create(database, owner, project_id)
    ref = {"composition_id": str(comp.id), "composition_version_id": str(version.id),
           "content_digest": version.content_digest}
    async with database() as db:
        project = await db.get(Project, project_id)
        user = await db.get(User, owner)
        user.settings = {"confirm_execution": "auto", "confirm_credits": "auto"}
        conversation = Conversation(user_id=owner, project_id=project_id)
        db.add(conversation)
        await db.commit()
        opening = await service._create_message(db, conversation.id, "user", "How long is this MP4?")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(project=project, user_id=owner, turn_id=opening.id,
                               conversation_id=conversation.id, _video_base_ref=ref,
                               _editor_last_preview={**ref, "mp4_sha256": "a" * 64})
        receipt = await editor_media.submit_editor_media(
            turn, "export_video", ExportVideoArgs(), comp, version, "unrequested-export",
        )
        assert receipt.question
        assert not await db.scalar(select(CreditTransaction.id).where(CreditTransaction.kind == "hold"))


@pytest.mark.asyncio
async def test_expired_voice_occupancy_recovers_only_fixed_audio(database, monkeypatch):
    from datetime import timedelta

    from sqlalchemy import update

    from app.chat.editor import GenerateVoiceArgs
    from app.editing.schemas import SpeechObject
    from app.models.tables import VideoNarration
    from app.tools.video import narration_store as originals

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    args = GenerateVoiceArgs(text="Lease recovery.", language="en")
    speech = SpeechObject(kind="speech", object_id="obj_voice", **args.model_dump())
    first = await originals.resolve_original(owner, speech, execution_id="generator")
    assert first["state"] == "needs_audio"

    async with database() as db:
        row, now = (await db.execute(select(VideoNarration, func.now()))).one()
        assert timedelta(minutes=9) < row.lease_expires_at - now <= timedelta(minutes=10)
        await db.execute(update(VideoNarration).values(lease_expires_at=func.now()))
        await db.commit()

    with pytest.raises(originals.NarrationOutcomeUnknown):
        await originals.resolve_original(owner, speech, execution_id="recovery")

    async with database() as db:
        await db.execute(update(VideoNarration).values(
            status="aligning", audio_digest="a" * 64, storage_key="fixed.mp3",
            duration_s=1, usage_characters=15,
        ))
        await db.commit()

    recovery = await originals.resolve_original(owner, speech, execution_id="recovery")
    assert recovery["audio"]["synthesis_execution_id"] == "generator"
    assert recovery["state"] == "needs_alignment"
    assert recovery["audio"]["media"]["digest"] == "a" * 64
    with pytest.raises(originals.NarrationStoreError, match="lost its occupancy"):
        await originals.complete_alignment(owner, speech, execution_id="generator", cues=[])


@pytest.mark.asyncio
async def test_media_queue_limits_owner_fairness_and_fences_expired_workers(database, monkeypatch):
    from datetime import timedelta
    from uuid import uuid4

    from app.pipeline import media_jobs

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)

    async def seat():
        owner = await _user(database)
        pid = await _project(database, owner)
        async with database() as db:
            conversation = Conversation(project_id=pid, user_id=owner)
            db.add(conversation)
            await db.commit()
            return pid, conversation.id

    async def enqueue(seat, kind):
        pid, cid = seat
        async with database() as db:
            job_id = uuid4()
            receipt = await service._create_message(db, cid, "assistant", "", intent={
                "editor_media": str(job_id), "tool": kind,
            })
            await media_jobs.enqueue_media(db, await db.get(Project, pid), receipt, {}, 0)
            await db.commit()
            return job_id

    async def claim(kind):
        async with database() as db:
            return await media_jobs.claim_media(db, kind)

    seats = [await seat() for _ in range(9)]
    jobs = []
    for owner in seats[:8]:
        jobs.append([await enqueue(owner, "generate_image") for _ in range(4)])
        if len(jobs) == 1:
            with pytest.raises(ValueError, match="queue is full"):
                await enqueue(owner, "generate_image")
    with pytest.raises(ValueError, match="queue is full"):
        await enqueue(seats[-1], "generate_image")
    music = await enqueue(seats[0], "generate_music")
    workers = await asyncio.gather(claim("generate_image"), claim("generate_image"))
    claims = [claim for claim in workers if claim]
    if len(claims) == 1:
        claims.append(await claim("generate_image"))
    assert {claim[0] for claim in claims} == {jobs[0][0], jobs[1][0]}
    assert await claim("generate_image") is None
    assert (await claim("generate_music"))[0] == music
    oldest = next(item for item in claims if item[0] == jobs[0][0])
    for attempt in range(1, media_jobs.MAX_ATTEMPTS + 1):
        async with database() as db:
            row = await db.get(MediaJob, oldest[0], with_for_update=True)
            assert row.attempt == attempt
            row.lease_until = func.now() - timedelta(seconds=1)
            await db.commit()
            assert await db.scalar(select(MediaJob.id).where(*media_jobs._authority(*oldest))) is None
        reclaimed = await claim("generate_image")
        if attempt < media_jobs.MAX_ATTEMPTS:
            assert reclaimed[0] == oldest[0] and reclaimed[1] != oldest[1]
            oldest = reclaimed
        else:
            assert reclaimed is None
    async with database() as db:
        failed = await db.get(MediaJob, oldest[0])
        assert failed.status == "failed" and failed.attempt == 3
        assert (await db.get(MediaJob, jobs[1][0])).status == "running"


@pytest.mark.asyncio
async def test_recovered_paid_request_requires_bound_confirmation_with_auto_account(database, monkeypatch):
    from app.chat.editor import GenerateVoiceArgs
    from app.models.schemas import PlanEstimate

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    quote = AsyncMock(return_value=PlanEstimate(total=[2, 3], per_task=[[2, 3]]))
    monkeypatch.setattr(editor_media, "media_quote", quote)
    owner = await _user(database, settings={"confirm_execution": "auto", "confirm_credits": "auto"})
    pid = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, pid)
        conv = Conversation(project_id=pid, user_id=owner)
        db.add(conv)
        await db.commit()
        row = await service._create_message(db, conv.id, "user", "Generate narration.")
        row.turn_state = "in_flight"
        row.intent = {"resumed_media": "previously-delivered"}
        await db.commit()
        turn = SimpleNamespace(project=project, user_id=owner, turn_id=row.id, conversation_id=conv.id,
                               text=row.content)
        args = GenerateVoiceArgs(text="A new line.", language="en")
        async def submit(args):
            return await editor_media.submit_editor_media(turn, "generate_voice", args, None, None, "new-voice")
        question = await submit(args)
        assert question.intent["media_permission"]["params"]["text"] == args.text
        assert question.intent["media_permission"]["quote"]["total"][1] == 3
        assert (await submit(args)).id == question.id
        with pytest.raises(ValueError, match="different parameters"):
            await submit(args.model_copy(update={"text": "Different."}))
        assert await db.scalar(select(func.count()).select_from(MediaJob)) == 0
        question = await db.get(Message, question.id, with_for_update=True)
        execution = await editor_media.answer_media_permission(db, project, question, True)
        await db.commit()
        assert execution.intent["authorization_ref"] == str(question.id)
        assert (await submit(args)).id == execution.id
        assert await db.scalar(select(func.count()).select_from(MediaJob)) == 1
        assert list(await db.scalars(select(CreditTransaction.amount).where(
            CreditTransaction.ref["media_job_id"].astext == execution.intent["media_job"]))) == [-3]


async def test_existing_media_instruction_rejects_generation_before_any_receipt(database, monkeypatch):
    from app.chat.editor import GenerateImageArgs

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr(editor_media, "AsyncSessionLocal", database)
    owner = await _user(database)
    pid = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, pid)
        convo = Conversation(project_id=pid, user_id=owner)
        db.add(convo)
        await db.commit()
        opening = await service._create_message(db, convo.id, "user", "Edit the footage. No new media or export.")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(project=project, user_id=owner, turn_id=opening.id, conversation_id=convo.id)
        with pytest.raises(ValueError, match="excluded new media"):
            await editor_media.submit_editor_media(
                turn, "generate_image", GenerateImageArgs(prompt="Placeholder"), None, None, "call",
            )
        assert await db.scalar(select(func.count()).select_from(Message).where(
            Message.turn_id == opening.id, Message.id != opening.id,
        )) == 0
        assert await db.scalar(select(func.count()).select_from(MediaJob)) == 0
        assert await db.scalar(select(func.count()).select_from(CreditTransaction).where(
            CreditTransaction.kind.in_(("capture", "hold")),
        )) == 0
