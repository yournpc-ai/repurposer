"""Layer 1A Chat-Origin: turn stop-fence, settlement, retraction, and SFX deterministic import races."""

from __future__ import annotations
import pytest

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
    exported = _design_no_progress_text("导出", version_saved=False, exported=True)
    assert "MP4 已导出" in exported and "未完成交付" in exported


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
    from test.support.composition_fixtures import valid_content

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


# --- SFX import concurrency & candidate context ---

import asyncio


import hashlib


import json


from datetime import UTC, datetime


from uuid import UUID, uuid4


import pytest


import pytest_asyncio


from sqlalchemy import func, select, text


from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


from app.config import settings


from app.editing.sources import register_snapshot


from app.editing.timing import SOURCE_TIMEBASE


from app.models.database import Base


from app.models.schemas import ImportSfxArgs


from app.models.tables import Asset, Conversation, Message, Project, SourceSnapshot, User


from app.providers.freesound import FreesoundSound


from app.tools.video import preparation, sfx





CANDIDATE_SET_ID = UUID("11111111-1111-1111-1111-111111111111")


MP3 = b"deterministic-test-mp3-bytes"


DIGEST = hashlib.sha256(MP3).hexdigest()


SOUND = FreesoundSound(
    provider_id="12345",
    title="Door click",
    author="field-recordist",
    duration_seconds=3.2,
    source_url="https://freesound.org/people/field-recordist/sounds/12345/",
    preview_url="https://cdn.freesound.org/previews/123/12345-hq.mp3",
    license="CC0",
    attribution='"Door click" by field-recordist on Freesound (CC0 1.0)',
)


async def test_concurrent_import_returns_one_verified_asset_and_snapshot(database, monkeypatch):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="SFX race")
        db.add(project)
        await db.commit()
        user_id, project_id = user.id, project.id

    args = ImportSfxArgs(candidate_set_id=CANDIDATE_SET_ID, member_index=0)
    envelope = {
        "kind": "set",
        "candidate_set_id": str(CANDIDATE_SET_ID),
        "topic": "door click",
        "asset_id": None,
        "members": [{
            "start": 0,
            "end": SOUND.duration_seconds,
            "excerpt": SOUND.title,
            "speaker": None,
            "provider": "freesound",
            "provider_id": SOUND.provider_id,
            "title": SOUND.title,
            "author": SOUND.author,
            "duration_seconds": SOUND.duration_seconds,
            "source_url": SOUND.source_url,
            "preview_url": SOUND.preview_url,
            "license": SOUND.license,
            "attribution": SOUND.attribution,
            "query": "door click",
        }],
    }

    async def persisted_events(*args, **kwargs):
        return [envelope]

    async def current_sound(provider_id):
        assert provider_id == SOUND.provider_id
        return SOUND

    both_downloading = asyncio.Event()
    download_count = 0
    download_lock = asyncio.Lock()

    async def download(sound):
        nonlocal download_count
        async with download_lock:
            download_count += 1
            if download_count == 2:
                both_downloading.set()
        await both_downloading.wait()
        return MP3

    objects: dict[str, bytes] = {}

    async def save(key, data, content_type=None):
        objects[key] = data

    async def read(key):
        return objects[key]

    async def fake_snapshot(db, asset, *, owner_id):
        return await register_snapshot(
            db,
            owner_id=owner_id,
            asset=asset,
            kind="audio",
            storage_key=f"source-snapshots/{DIGEST}.mp3",
            digest=DIGEST,
            duration_ticks=round(SOUND.duration_seconds * SOURCE_TIMEBASE),
            meta={"media": {"sample_rate": 48000, "channels": 2}, "origin": asset.meta["origin"]},
            captured_at=datetime.now(UTC),
        )

    monkeypatch.setattr(sfx, "persisted_candidate_events", persisted_events)
    monkeypatch.setattr(sfx, "get_cc0_mp3", current_sound)
    monkeypatch.setattr(sfx, "download_mp3_preview", download)
    monkeypatch.setattr(sfx, "_validate_mp3_bytes", lambda data: None)
    monkeypatch.setattr(sfx.storage, "save", save)
    monkeypatch.setattr(sfx.storage, "read", read)
    monkeypatch.setattr(preparation, "snapshot_audio_asset", fake_snapshot)

    async def import_in_own_transaction():
        async with database() as db:
            project = await db.get(Project, project_id)
            return await sfx.import_sfx_candidate(db, project=project, args=args)

    first, second = await asyncio.gather(
        import_in_own_transaction(), import_in_own_transaction()
    )
    assert download_count == 2
    assert first == second
    assert first["snapshot_digest"] == DIGEST

    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Asset)) == 1
        assert await db.scalar(select(func.count()).select_from(SourceSnapshot)) == 1
        asset = await db.get(Asset, UUID(first["asset_id"]))
        snapshot = await db.get(SourceSnapshot, UUID(first["snapshot_id"]))
        assert asset.user_id == user_id and asset.project_id == project_id
        assert asset.meta["content_sha256"] == DIGEST
        assert snapshot.asset_id == asset.id and snapshot.digest == DIGEST
        assert snapshot.meta["origin"]["candidate_set_id"] == str(CANDIDATE_SET_ID)


async def test_settled_candidate_log_feeds_next_turn_context_but_not_same_turn_import(
    database, monkeypatch,
):
    from app.chat.video_turn_seats import video_context_lines

    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="SFX context")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        user_id, project_id, conversation_id = user.id, project.id, conversation.id

    args = ImportSfxArgs(candidate_set_id=CANDIDATE_SET_ID, member_index=0)
    async with database() as db:
        project = await db.get(Project, project_id)
        with pytest.raises(sfx.SfxError, match="no persisted SFX candidate set"):
            await sfx.import_sfx_candidate(db, project=project, args=args)

    envelope = {
        "kind": "set",
        "candidate_set_id": str(CANDIDATE_SET_ID),
        "topic": "door click",
        "asset_id": None,
        "members": [{
            "provider": "freesound",
            "title": "Door click",
            "duration_seconds": 3.2,
        }],
    }
    async with database() as db:
        db.add(Message(
            conversation_id=conversation_id,
            role="assistant",
            content="",
            attachments=[],
            mentions=[],
            intent={"type": "candidates_log", "ref": "settled-search", "events": [envelope]},
            seq=1,
        ))
        await db.commit()

    async with database() as db:
        project = await db.get(Project, project_id)
        lines = await video_context_lines(db, project)
    assert lines[0].startswith("已保存的音频候选集")
    projected = json.loads(lines[1])
    assert projected["candidate_set_id"] == str(CANDIDATE_SET_ID)
    assert projected["members"] == [{
        "member_index": 0, "ordinal": 1,
        "title": "Door click", "duration_seconds": 3.2,
    }]


async def test_search_sfx_seat_uses_classified_user_intent(monkeypatch):
    from types import SimpleNamespace

    from app.chat.sfx_intent import SfxIntentDecision, sfx_intent_agent
    from app.chat.video_turn_seats import search_sfx_seat
    from app.models.schemas import SearchSfxArgs

    decision = SfxIntentDecision(action="add", evidence="使用真实 CC0 音效")

    async def classify(**kwargs):
        assert kwargs["user_text"] == "使用真实 CC0 音效"
        return decision

    calls = []

    async def provider(query):
        calls.append(query)
        return {"candidate_set_id": str(CANDIDATE_SET_ID), "topic": query, "members": []}

    emitted = []

    async def on_candidates(payload):
        emitted.append(payload)

    monkeypatch.setattr(sfx_intent_agent, "call", classify)
    monkeypatch.setattr("app.tools.video.sfx.search_sfx_candidates", provider)
    project = SimpleNamespace(user_id=uuid4())
    result = await search_sfx_seat(
        project=project,
        args=SearchSfxArgs(query="soft click"),
        user_text="使用真实 CC0 音效",
        on_candidates=on_candidates,
    )
    assert result.ok and calls == ["soft click"] and len(emitted) == 1
    assert '"action": "add"' in result.text
    assert "使用真实 CC0 音效" in result.text

    decision.action = "deny"
    rejected = await search_sfx_seat(
        project=project,
        args=SearchSfxArgs(query="another click"),
        user_text="使用真实 CC0 音效",
        on_candidates=on_candidates,
    )
    assert not rejected.ok and calls == ["soft click"] and len(emitted) == 1
    assert '"action": "deny"' in rejected.text


async def test_freesound_download_bypasses_ambient_proxy(monkeypatch):
    from app.providers import freesound

    captured = {}

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b"{}"

    class Stream:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *args):
            return None

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return Stream()

    monkeypatch.setattr(freesound.httpx, "AsyncClient", Client)
    data, content_type = await freesound._download(
        "https://freesound.org/apiv2/search/text/", max_bytes=16,
    )
    assert data == b"{}" and content_type == "application/json"
    assert captured["trust_env"] is False

