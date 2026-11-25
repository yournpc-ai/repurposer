"""Chat activity and questions — chat origin contracts."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.chat.context import conversation_messages
from app.models.schemas import (
    BrandProfile,
    BrandSourceRef,
    BriefAnswerItem,
    BriefSlotSource,
    CreativeState,
    ProjectBrief,
    QuestionPayload,
    seal_creative_state,
)
from app.models.tables import Conversation, Message, Project, SourceSnapshot, User
from test.support.chat_http import scripted_chat, tool
from test.support.db_helpers import full_api_client
from test.support.media_helpers import (
    group_payload,
    group_request,
)

pytestmark = pytest.mark.chat_origin


URL = "https://www.legitevi.com/en"


SNAPSHOT_ID = uuid4()


def website_pending():
    ref = BrandSourceRef(snapshot_id=str(SNAPSHOT_ID), digest="a" * 64)
    state = seal_creative_state(CreativeState(
        brand_profile=BrandProfile(
            extractor_version="website-brand-v1",
            source_refs=[ref],
            content_digest="c" * 64,
        ),
        source_refs=[ref],
    ))
    return ProjectBrief(
        prompt=f"给 {URL} 做一只宣传片",
        creative_state=state,
    )


def add_website_snapshot(db, owner_id, project_id):
    db.add(SourceSnapshot(
        id=SNAPSHOT_ID,
        owner_id=owner_id,
        origin_project_id=project_id,
        kind="web",
        storage_key="sources/legitevi.json",
        digest="a" * 64,
        meta={
            "canonical_url": URL,
            "lines": [{"line_id": "line_0000", "text": "Citations should be universal."}],
            "views": [{
                "view_id": "hero",
                "storage_key": "sources/hero.png",
                "digest": "b" * 64,
                "width": 1440,
                "height": 900,
            }],
        },
    ))


async def ask_group(database, monkeypatch, user, project, conversation, mentions=None):
    payload = group_payload()
    _, frames = await scripted_chat(
        database, monkeypatch, user.id, project.id, "给官网做一支宣传片",
        [tool("ask_user", {"question": payload.question,
                           "items": [item.model_dump(mode="json") for item in payload.items],
                           "default_path": payload.default_path}, "请确认制作设置。")],
        conversation_id=str(conversation.id), mentions=mentions or [],
    )
    response = frames[-1][1]
    question = response["assistant_message"]
    return UUID(response["user_message"]["id"]), UUID(question["id"]), QuestionPayload.model_validate(question["question"])


@pytest.mark.asyncio
async def test_group_answer_settles_one_row_and_backfills_all_slots_atomically(
    database, monkeypatch
):
    async with database() as db:
        user = User(id=uuid4(), email=f"{uuid4().hex}@example.com")
        project = Project(
            id=uuid4(),
            user_id=user.id,
            title="Website promo",
            pending_brief=ProjectBrief().model_dump(mode="json"),
        )
        conversation = Conversation(id=uuid4(), user_id=user.id, project_id=project.id)
        db.add(user)
        await db.flush()
        db.add(project)
        await db.flush()
        db.add(conversation)
        await db.flush()
        await db.commit()
        user_id, project_id, conversation_id = user.id, project.id, conversation.id
    opening_id, question_id, payload = await ask_group(database, monkeypatch, user, project, conversation,
        [{"type": "asset", "id": "source", "label": "logo.png"}])
    request = group_request(payload)

    continuations = []

    async def no_model_follow_up(*args, **kwargs):
        assert kwargs["group_answer_submitted"]
        continued_request = args[4]
        assert continued_request.message.startswith("给官网做一支宣传片")
        assert payload.question in continued_request.message
        assert [m.label for m in continued_request.mentions] == ["logo.png"]
        from app.chat.service import _interim_prose_callback, _lock_turn_for_final_commit
        assert kwargs["turn_id"] == opening_id
        await _interim_prose_callback(args[0], conversation_id, turn_id=opening_id)("检查来源")
        async with database() as writer:
            assert (await _lock_turn_for_final_commit(writer, opening_id)).turn_state == "in_flight"
        continuations.append(conversation_messages(kwargs["recent"]))
        return None, None

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.service._plan_turn", no_model_follow_up)
    async with full_api_client(database, user) as client, database() as db:
        url = f"/api/v1/chat/messages/{question_id}/answer"
        response = await client.post(url, json=request.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        answered = await db.get(Message, question_id)
        follow_up = response.json()["follow_up"]
        assert follow_up is None
        assert answered.answer["kind"] == "group"
        assert len(answered.answer["answers"]) == len(request.answers)
        assert [m["role"] for m in continuations[0]] == ["user", "assistant", "user"]
        assert continuations[0][0]["content"] == "给官网做一支宣传片"
        for item in payload.items:
            assert f"{item.question} {item.options[0].label}" in continuations[0][-1]["content"]
        stored = ProjectBrief.model_validate((await db.get(Project, project_id)).pending_brief)
        assert stored.brief.production_direction.value == "官网推广 · 用真实案例演示产品"
        assert stored.brief.target_seconds.value == 30
        assert stored.brief.narration_language.value == "en"
        assert stored.brief.subtitle_languages.value == ["en"]
        assert stored.brief.aspect.value == "16:9"
        assert stored.brief.constraints == []
        assert stored.creative_state is not None
        assert stored.creative_state.brief.target_seconds.value == 30
        assert stored.creative_state.content_digest
        assert (
            await db.scalar(
                select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
            )
        ) == 3
        assert (await db.get(Message, opening_id)).turn_state == "settled"
        replay = await client.post(url, json=request.model_dump(mode="json"))
        assert replay.status_code == 409


async def _answer_group_bail(database, monkeypatch, answers):
    async with database() as db:
        user = User(id=uuid4(), email=f"{uuid4().hex}@example.com")
        project = Project(
            id=uuid4(),
            user_id=user.id,
            title="Website promo",
            pending_brief=website_pending().model_dump(mode="json"),
        )
        conversation = Conversation(id=uuid4(), user_id=user.id, project_id=project.id)
        db.add(user)
        await db.flush()
        db.add(project)
        await db.flush()
        add_website_snapshot(db, user.id, project.id)
        db.add(conversation)
        await db.flush()
        await db.commit()
        project_id = project.id
    _, question_id, payload = await ask_group(database, monkeypatch, user, project, conversation)

    async def no_model_follow_up(*args, **kwargs):
        assert not kwargs.get("group_answer_submitted")
        return None, None

    monkeypatch.setattr("app.chat.service._plan_turn", no_model_follow_up)
    from app.models.schemas import BailAnswerRequest

    async with full_api_client(database, user) as client, database() as db:
        response = await client.post(f"/api/v1/chat/messages/{question_id}/answer", json=BailAnswerRequest(
            kind="bail", group_digest=payload.group_digest, answers=answers).model_dump(mode="json"))
        assert response.status_code == 200, response.text
        answered = await db.get(Message, question_id)
        stored = ProjectBrief.model_validate((await db.get(Project, project_id)).pending_brief)
    return answered, stored


@pytest.mark.asyncio
async def test_group_bail_leaves_unanswered_fields_empty(database, monkeypatch):
    answered, stored = await _answer_group_bail(database, monkeypatch, [])
    assert answered.answer["kind"] == "bail"
    assert answered.answer["answers"] == []
    for slot in ("production_direction", "target_seconds", "narration_language", "subtitle_languages", "aspect", "tone"):
        assert getattr(stored.brief, slot).value is None
    assert stored.creative_state.brief.target_seconds.value is None


@pytest.mark.asyncio
async def test_group_bail_preserves_only_submitted_answers(database, monkeypatch):
    answered, stored = await _answer_group_bail(
        database,
        monkeypatch,
        [BriefAnswerItem(slot="target_seconds", kind="option", option_id="2")],
    )
    assert answered.answer["kind"] == "bail"
    assert len(answered.answer["answers"]) == 1
    assert stored.brief.target_seconds.value == 60
    assert stored.brief.target_seconds.source == BriefSlotSource.USER_STATED
    assert stored.brief.production_direction.value is None
    assert stored.brief.aspect.value is None
