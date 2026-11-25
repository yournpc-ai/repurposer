"""Chat turn settlement and imports — chat origin contracts."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import pytest

from app.chat.intent import intent_router
from app.models.schemas import ImportSfxArgs
from app.models.tables import (
    Conversation,
    Message,
    MessageSeqCounter,
    Project,
    User,
    Wallet,
)
from app.tools.video import sfx
from test.support.chat_http import post_chat, scripted_chat, tool
from test.support.db_helpers import ScriptedToolClient, bind_test_database, full_api_client

pytestmark = pytest.mark.chat_origin


async def owner(factory):
    async with factory() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        db.add(Wallet(user_id=user.id, balance=1000))
        await db.commit()
        return user.id


async def test_unbound_opening_has_native_creation_without_skill_context(database, monkeypatch, installed_promo):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    from app.chat.editor_create import CreateVideoArgs
    from app.chat.intent import intent_router
    from app.chat.service import (
        _create_message,
        _get_or_create_project_conversation,
    )
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
        llm, frames = await scripted_chat(database, monkeypatch, uid, project.id, "制作一个产品宣传片 promo-video",
                                          [tool("answer", {}, "Ready.")], conversation_id=str(conversation.id))
        opening = await db.get(Message, UUID(frames[-1][1]["user_message"]["id"]))
        assert not (opening.intent or {}).get("skill")
        declared = {t["function"]["name"] for t in llm.calls[0]["tools"]}
        assert next(t for t in intent_router.tools if t.name == "create_video").params_model is CreateVideoArgs
        assert "create_video" in declared
        assert not declared & {"list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview"}


CANDIDATE_SET_ID = UUID("11111111-1111-1111-1111-111111111111")


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
        db.add(MessageSeqCounter(conversation_id=conversation_id, last_seq=1))
        await db.commit()

    async with database() as db:
        project = await db.get(Project, project_id)
        lines = await video_context_lines(db, project)
    llm, _ = await scripted_chat(database, monkeypatch, user_id, project_id, "Which saved sound can I use?",
                                 [tool("answer", {}, "Door click.")], conversation_id=str(conversation_id))
    assert str(CANDIDATE_SET_ID) in json.dumps(llm.calls[0]["messages"])
    assert lines[0].startswith("已保存的音频候选集")
    projected = json.loads(lines[1])
    assert projected["candidate_set_id"] == str(CANDIDATE_SET_ID)
    assert projected["members"] == [{
        "member_index": 0, "ordinal": 1,
        "title": "Door click", "duration_seconds": 3.2,
    }]


async def test_concurrent_import_through_separate_conversations(database, monkeypatch, sfx_import_race):
    from test.support.sfx_import import assert_one_import

    race = sfx_import_race
    bind_test_database(monkeypatch, database)
    class ImportClient(ScriptedToolClient):
        async def generate_with_tools(self, **request):
            self.calls.append(request)
            if any(message.get("role") == "tool" for message in request["messages"]):
                return tool("answer", {}, "I checked the import result.")
            return tool("import_sfx", race.arguments.model_dump(mode="json"))

    llm = ImportClient([], streaming=True)
    monkeypatch.setattr(intent_router, "client", llm)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: llm)
    async with full_api_client(database, race.user) as http, asyncio.timeout(15):
        responses = await asyncio.gather(*(post_chat(http, race.project.id, "Import the door click sound effect.",
                                                    conversation_id=str(chat.id)) for chat in race.chats))
    offered = {spec["function"]["name"] for spec in llm.calls[0]["tools"]}
    assert "import_sfx" in offered, "The Chat route omitted import_sfx despite a settled SFX candidate set"
    for frames in responses:
        assert any(e == "assistant.candidates" and p.get("selected") == [0] for e, p in frames)
    observations = [m["content"] for call in llm.calls for m in call["messages"]
                    if m["role"] == "tool" and m.get("name") == "import_sfx"]
    first, second = [json.loads(text.splitlines()[-1]) for text in observations]
    await assert_one_import(database, race, first, second)
