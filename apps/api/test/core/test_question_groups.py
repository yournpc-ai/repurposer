from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select

from app.chat.context import conversation_messages
from app.chat.service import _ask_content, _validate_group_answers, answer_question
from app.models.schemas import (
    AnswerPayload,
    AnswerRequest,
    BrandProfile,
    BrandSourceRef,
    Brief,
    BriefAnswerItem,
    BriefQuestionItem,
    BriefSlot,
    BriefSlotSource,
    CreativeState,
    GroupAnswerRequest,
    ProjectBrief,
    QuestionPayload,
    question_group_digest,
    seal_creative_state,
)
from app.models.tables import Conversation, Message, Project, SourceSnapshot, User
from test.core.test_website_promo_readiness import website_question_arguments

def group_payload(*, allow_freeform=True):
    items = website_items()
    for item in items:
        item.allow_freeform = allow_freeform
    return QuestionPayload(
        kind="question",
        question="Confirm the production setup",
        items=items,
        group_digest=question_group_digest(items, Brief()),
        default_path="Use the stated safe defaults",
    )


def group_request(payload):
    return GroupAnswerRequest(
        kind="group",
        group_digest=payload.group_digest,
        answers=[
            BriefAnswerItem(slot=item.slot, kind="option", option_id=item.options[0].id)
            for item in payload.items
        ],
    )


def website_items():
    return [BriefQuestionItem.model_validate(item) for item in website_question_arguments()["items"]]


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


def test_group_validation_rejects_bad_membership_duplicates_required_and_freeform():
    payload = group_payload(allow_freeform=False)
    request = group_request(payload)
    with pytest.raises(HTTPException) as duplicate:
        _validate_group_answers(
            payload,
            request.model_copy(
                update={
                    "answers": [request.answers[0], request.answers[0], *request.answers[1:]],
                }
            ),
        )
    assert duplicate.value.status_code == 422

    with pytest.raises(HTTPException) as missing:
        _validate_group_answers(
            payload, request.model_copy(update={"answers": request.answers[:-1]})
        )
    assert missing.value.status_code == 422

    with pytest.raises(HTTPException) as wrong_option:
        _validate_group_answers(
            payload,
            request.model_copy(
                update={
                    "answers": [
                        BriefAnswerItem(slot="production_direction", kind="option", option_id="other"),
                        *request.answers[1:],
                    ],
                }
            ),
        )
    assert wrong_option.value.status_code == 422

    with pytest.raises(HTTPException) as freeform:
        _validate_group_answers(
            payload,
            request.model_copy(
                update={
                    "answers": [
                        BriefAnswerItem(slot="production_direction", kind="freeform", text="conference"),
                        *request.answers[1:],
                    ],
                }
            ),
        )
    assert freeform.value.status_code == 422

    with pytest.raises(HTTPException) as stale:
        _validate_group_answers(payload, request.model_copy(update={"group_digest": "0" * 64}))
    assert stale.value.status_code == 409


@pytest.mark.parametrize("kind", ["group", "bail"])
def test_questionnaire_rejects_removed_notes_on_submit_and_skip(kind):
    with pytest.raises(ValidationError) as error:
        TypeAdapter(AnswerRequest).validate_python({
            "kind": kind,
            "group_digest": "0" * 64,
            "answers": [{"slot": "constraints", "kind": "freeform", "text": "24 fps"}],
        })
    assert error.value.errors()[0]["loc"][-1] == "slot"


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
        payload = group_payload()
        request = group_request(payload)
        opening_id = uuid4()
        question = Message(
            turn_id=opening_id,
            id=uuid4(),
            conversation_id=conversation.id,
            role="assistant",
            content=payload.question,
            question=payload.model_dump(mode="json"),
            seq=1,
        )
        db.add(user)
        await db.flush()
        db.add(project)
        await db.flush()
        db.add(conversation)
        await db.flush()
        db.add(Message(id=opening_id, conversation_id=conversation.id, role="user", turn_state="settled",
                       content="给官网做一支宣传片", seq=0,
                       mentions=[{"type": "asset", "id": "source", "label": "logo.png"}]))
        db.add(question)
        await db.commit()
        user_id, project_id, conversation_id, question_id = (
            user.id,
            project.id,
            conversation.id,
            question.id,
        )

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
    async with database() as db:
        answered, follow_up = await answer_question(
            db, user_id, question_id, request
        )
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
        with pytest.raises(HTTPException) as replay:
            await answer_question(
                db, user_id, question_id, request
            )
        assert replay.value.status_code == 409


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
        payload = group_payload()
        question = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="assistant",
            content=payload.question,
            question=payload.model_dump(mode="json"),
            seq=1,
        )
        db.add(user)
        await db.flush()
        db.add(project)
        await db.flush()
        add_website_snapshot(db, user.id, project.id)
        db.add(conversation)
        await db.flush()
        db.add(question)
        await db.commit()
        question_id = question.id
        project_id = project.id
        user_id = user.id

    async def no_model_follow_up(*args, **kwargs):
        assert not kwargs.get("group_answer_submitted")
        return None, None

    monkeypatch.setattr("app.chat.service._plan_turn", no_model_follow_up)
    from app.models.schemas import BailAnswerRequest

    async with database() as db:
        answered, _ = await answer_question(
            db,
            user_id,
            question_id,
            BailAnswerRequest(
                kind="bail",
                group_digest=payload.group_digest,
                answers=answers,
            ),
        )
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


def test_plain_option_answer_needs_no_group_or_workflow():
    answer = AnswerPayload.model_validate(
        {
            "kind": "option",
            "option_id": "1",
            "text": "One",
            "answered_at": "2026-01-01T00:00:00Z",
        }
    )
    assert answer.answers == []
    question = QuestionPayload.model_validate(
        {
            "kind": "question",
            "question": "Choose",
            "options": [{"id": "1", "label": "One"}],
        }
    )
    assert question.kind == "question"
    assert question.items == []
    from pydantic import TypeAdapter, ValidationError
    from app.models.schemas import AnswerRequest
    with pytest.raises(ValidationError):
        TypeAdapter(AnswerRequest).validate_python({"kind": "start"})


def test_extended_single_slot_backfill_preserves_slot_types_and_creative_state():
    from app.chat.service import _backfill_brief_slot

    project = Project(id=uuid4(), user_id=uuid4(), title="Single slots")
    _backfill_brief_slot(project, "target_seconds", "60 seconds")
    _backfill_brief_slot(project, "subtitle_languages", "English")
    stored = ProjectBrief.model_validate(project.pending_brief)
    assert stored.brief.target_seconds.value == 60
    assert stored.brief.subtitle_languages.value == ["en"]
    assert stored.creative_state is not None
    assert stored.creative_state.content_digest


@pytest.mark.asyncio
async def test_streamed_ask_only_announces_activity():
    import asyncio
    from app.chat.routes import _make_tool_call_hook

    queue = asyncio.Queue()
    await _make_tool_call_hook(queue)("ask_user")
    assert queue.qsize() == 1
    assert queue.get_nowait().startswith("event: assistant.thinking")


def test_group_digest_ignores_code_owned_material_bookkeeping():
    payload = group_payload()
    before = Brief()
    after = before.model_copy(update={
        "material_state": BriefSlot(
            value="attached", source=BriefSlotSource.DEFAULT,
        ),
    })
    assert question_group_digest(payload.items, before) == question_group_digest(
        payload.items, after
    )


def test_group_title_stays_out_of_the_message_prose():
    from app.models.schemas import QuestionProposal

    ask = QuestionProposal(prose="Brand evidence is ready.", question="Production setup")
    assert _ask_content(ask, has_dock_options=True) == "Brand evidence is ready."
    assert _ask_content(ask) == "Brand evidence is ready.\n\nProduction setup"


@pytest.mark.parametrize("values", [
    [["zh-CN", "en-US"]],
    [["zh-CN", "en-US"], "zh-CN"],
    ["zh-CN", "en-US"],
])
def test_subtitle_choices_preserve_authored_labels_order_and_language_sets(values):
    from app.models.schemas import missing_brief_question_items

    form = website_question_arguments()
    subtitles = next(item for item in form["items"] if item["slot"] == "subtitle_languages")
    options = [{"label": f"Choice {i}", "value": value} for i, value in enumerate(values)]
    subtitles["options"] = options
    items = [BriefQuestionItem.model_validate(item) for item in form["items"]]
    result = next(i for i in missing_brief_question_items(items, Brief()) if i.slot == "subtitle_languages")
    assert [(o.label, o.value) for o in result.options] == [
        (o["label"], [o["value"]] if isinstance(o["value"], str) else o["value"]) for o in options
    ]


def test_native_history_includes_intervening_dialogue_and_places_dock_pick_at_submission():
    from datetime import UTC, datetime, timedelta

    start = datetime.now(UTC)
    rows = [
        Message(id=uuid4(), role="user", content="给 https://www.legitevi.com/en 做一只宣传片"),
        Message(id=uuid4(), role="assistant", content="官网内容看过了。", question={
            "question": "旁白用哪种语言？", "options": [{"id": "en", "label": "英文"}],
        }, answer={"kind": "option", "text": "英文", "answered_at": (start + timedelta(seconds=4)).isoformat()}),
        Message(id=uuid4(), role="user", content="先说说你的想法"),
        Message(id=uuid4(), role="assistant", content="我想用官网画面做开头。"),
        Message(id=uuid4(), role="assistant", content="我来搭分镜。"),
    ]
    for row, seconds in zip(rows, [0, 1, 2, 3, 5], strict=True):
        row.created_at = start + timedelta(seconds=seconds)
    dialogue = conversation_messages(rows)
    assert [m["content"] for m in dialogue] == [
        rows[0].content, "官网内容看过了。\n旁白用哪种语言？\n英文", rows[2].content,
        rows[3].content, "英文", rows[4].content,
    ]
    assert dialogue[4]["role"] == "user"
    rows.insert(4, Message(id=uuid4(), role="user", content="英文",
                           intent={"answered_question_id": str(rows[1].id)},
                           created_at=start + timedelta(seconds=4)))
    assert conversation_messages(rows) == dialogue
