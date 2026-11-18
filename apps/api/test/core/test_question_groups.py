from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.chat.context import conversation_messages
from app.chat.service import _ask_content, _validate_group_answers, answer_question
from app.models.schemas import (
    AnswerPayload,
    BrandProfile,
    BrandSourceRef,
    Brief,
    BriefAnswerItem,
    BriefQuestionItem,
    BriefSlot,
    BriefSlotSource,
    CreativeState,
    GroupAnswerRequest,
    Option,
    PendingPlan,
    QuestionPayload,
    question_group_digest,
    seal_creative_state,
)
from app.models.tables import Conversation, Message, Project, SourceSnapshot, User, WorkflowRun

SLOTS = (
    ("purpose", "website"),
    ("target_seconds", "60"),
    ("narrative_mode", "mission_tech"),
    ("narration_language", "en"),
    ("subtitle_languages", "en"),
    ("aspect", "16:9"),
)


def group_payload(*, allow_freeform=True, numeric_ids=False):
    items = [
        BriefQuestionItem(
            slot=slot,
            question=f"Choose {slot}",
            options=[Option(
                id=str(index) if numeric_ids else option_id,
                label=option_id,
            )],
            allow_freeform=allow_freeform,
            required=True,
            default_path=f"Use a safe {slot} default",
        )
        for index, (slot, option_id) in enumerate(SLOTS, start=1)
    ]
    return QuestionPayload(
        kind="question",
        question="Confirm the production setup",
        items=items,
        group_digest=question_group_digest(items, Brief()),
        default_path="Use the stated safe defaults",
    )


def group_request(payload, *, numeric_ids=False):
    return GroupAnswerRequest(
        kind="group",
        group_digest=payload.group_digest,
        answers=[
            BriefAnswerItem(
                slot=slot,
                kind="option",
                option_id=str(index) if numeric_ids else option_id,
            )
            for index, (slot, option_id) in enumerate(SLOTS, start=1)
        ],
    )


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
    return PendingPlan(
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
                        BriefAnswerItem(slot="purpose", kind="option", option_id="other"),
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
                        BriefAnswerItem(slot="purpose", kind="freeform", text="conference"),
                        *request.answers[1:],
                    ],
                }
            ),
        )
    assert freeform.value.status_code == 422

    with pytest.raises(HTTPException) as stale:
        _validate_group_answers(payload, request.model_copy(update={"group_digest": "0" * 64}))
    assert stale.value.status_code == 409


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
            pending_brief=PendingPlan().model_dump(mode="json"),
        )
        conversation = Conversation(id=uuid4(), user_id=user.id, project_id=project.id)
        payload = group_payload(numeric_ids=True)
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
        db.add(conversation)
        await db.flush()
        db.add(Message(id=uuid4(), conversation_id=conversation.id, role="user",
                       content="给官网做一支宣传片", seq=0))
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
        continuations.append(conversation_messages(kwargs["recent"]))
        return None, None, None, []

    monkeypatch.setattr("app.chat.service._plan_turn", no_model_follow_up)
    async with database() as db:
        payload = group_payload(numeric_ids=True)
        answered, follow_up = await answer_question(
            db, user_id, question_id, group_request(payload, numeric_ids=True)
        )
        assert follow_up is None
        assert answered.answer["kind"] == "group"
        assert len(answered.answer["answers"]) == 6
        assert [m["role"] for m in continuations[0]] == ["user", "assistant", "user"]
        assert continuations[0][0]["content"] == "给官网做一支宣传片"
        for item, (_, value) in zip(payload.items, SLOTS, strict=True):
            assert f"{item.question} {value}" in continuations[0][-1]["content"]
        stored = PendingPlan.model_validate((await db.get(Project, project_id)).pending_brief)
        assert stored.brief.purpose.value == "website"
        assert stored.brief.target_seconds.value == 60
        assert stored.brief.narrative_mode.value == "mission_tech"
        assert stored.brief.narration_language.value == "en"
        assert stored.brief.subtitle_languages.value == ["en"]
        assert stored.brief.aspect.value == "16:9"
        assert stored.creative_state is not None
        assert stored.creative_state.brief.target_seconds.value == 60
        assert stored.creative_state.content_digest
        assert (
            await db.scalar(
                select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
            )
        ) == 2
        assert (await db.scalar(select(func.count(WorkflowRun.id)))) == 0
        with pytest.raises(HTTPException) as replay:
            await answer_question(
                db, user_id, question_id, group_request(payload, numeric_ids=True)
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
        return None, None, None, []

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
        stored = PendingPlan.model_validate((await db.get(Project, project_id)).pending_brief)
    return answered, stored


def _ready_after_bail(stored):
    from app.chat.readiness import compute_source_readiness
    from test.core.test_website_promo_readiness import snapshot

    evidence = snapshot()
    evidence["snapshot_id"] = str(SNAPSHOT_ID)
    return compute_source_readiness(
        user_text=f"给 {URL} 做一只宣传片",
        snapshots=[evidence],
        creative_state=stored.creative_state,
    )


@pytest.mark.asyncio
async def test_group_bail_uses_defaults_without_user_stated(database, monkeypatch):
    answered, stored = await _answer_group_bail(database, monkeypatch, [])
    assert answered.answer["kind"] == "bail"
    assert answered.answer["answers"] == []
    assert stored.brief.target_seconds.value == 30
    assert stored.brief.narrative_mode.value == "product_evidence"
    assert stored.brief.narration_language.value == "en"
    assert stored.brief.subtitle_languages.value == ["en"]
    assert stored.brief.aspect.value == "16:9"
    assert stored.brief.tone.value == "minimal_tech"
    for slot in (
        "purpose", "target_seconds", "narrative_mode", "narration_language",
        "subtitle_languages", "aspect", "tone",
    ):
        assert getattr(stored.brief, slot).source == BriefSlotSource.DEFAULT
    assert stored.creative_state.brief.target_seconds.value == 30
    assert _ready_after_bail(stored).required_next_action == "design_video"


@pytest.mark.asyncio
async def test_group_bail_preserves_answers_and_defaults_the_rest(database, monkeypatch):
    answered, stored = await _answer_group_bail(
        database,
        monkeypatch,
        [BriefAnswerItem(slot="target_seconds", kind="option", option_id="60")],
    )
    assert answered.answer["kind"] == "bail"
    assert len(answered.answer["answers"]) == 1
    assert stored.brief.target_seconds.value == 60
    assert stored.brief.target_seconds.source == BriefSlotSource.USER_STATED
    assert stored.brief.purpose.value == "website"
    assert stored.brief.purpose.source == BriefSlotSource.DEFAULT
    assert stored.brief.narration_language.value == "en"
    assert stored.brief.narrative_mode.value == "product_evidence"
    assert stored.brief.aspect.value == "16:9"
    assert _ready_after_bail(stored).required_next_action == "design_video"


def test_legacy_answer_and_question_shapes_remain_readable():
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
            "kind": "choice",
            "question": "Legacy",
            "options": [{"id": "1", "label": "One"}],
        }
    )
    assert question.kind == "question"
    assert question.items == []


def test_run_creative_state_is_copied_only_without_a_version_ref():
    from app.chat.service import _creative_run_context
    from app.models.schemas import CreativeState, seal_creative_state

    state = seal_creative_state(CreativeState(brief=Brief()))
    pending = PendingPlan(creative_state=state)
    assert (
        _creative_run_context(pending, {})["creative_state"]["content_digest"]
        == state.content_digest
    )
    assert _creative_run_context(pending, {"version_ref": {"composition_version_id": "v1"}}) == {}
    assert _creative_run_context(None, {}) == {}


def test_extended_single_slot_backfill_preserves_slot_types_and_creative_state():
    from app.chat.service import _backfill_brief_slot

    project = Project(id=uuid4(), user_id=uuid4(), title="Single slots")
    _backfill_brief_slot(project, "target_seconds", "60 seconds")
    _backfill_brief_slot(project, "subtitle_languages", "English")
    stored = PendingPlan.model_validate(project.pending_brief)
    assert stored.brief.target_seconds.value == 60
    assert stored.brief.subtitle_languages.value == ["en"]
    assert stored.creative_state is not None
    assert stored.creative_state.content_digest


@pytest.mark.asyncio
async def test_group_preview_uses_execution_filtered_items_and_digest(database):
    import asyncio
    import json

    from app.chat.readiness import brief_with_user_constraints
    from app.chat.routes import _group_digest_resolver, _make_tool_hooks
    from app.models.schemas import PlanAskArgs, missing_brief_question_items

    text = (
        f"给 {URL} 做一只 60 秒、16:9、英文配音和英文字幕的品牌官网宣传片。"
    )
    async with database() as db:
        user = User(id=uuid4(), email=f"{uuid4().hex}@example.com")
        db.add(user)
        await db.flush()
        project = Project(
            id=uuid4(),
            user_id=user.id,
            title="Group preview",
            pending_brief=PendingPlan().model_dump(mode="json"),
        )
        db.add(project)
        await db.flush()
        conversation = Conversation(id=uuid4(), user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        conversation_id = conversation.id

    expected_brief = brief_with_user_constraints(text, Brief())
    expected_items = missing_brief_question_items(group_payload().items, expected_brief)
    expected_digest = question_group_digest(expected_items, expected_brief)
    resolver = _group_digest_resolver(conversation_id, text)
    queue = asyncio.Queue()
    _, on_tool_ready = _make_tool_hooks(queue, group_digest=resolver)
    await on_tool_ready(
        "ask_user",
        PlanAskArgs(
            question="Confirm the production setup",
            items=group_payload().items,
            default_path="Use safe defaults",
        ),
    )
    frame = queue.get_nowait()
    payload = json.loads(frame.split("data: ", 1)[1])
    assert [item["slot"] for item in payload["items"]] == [
        item.slot for item in expected_items
    ]
    assert payload["group_digest"] == expected_digest


def test_website_promo_question_items_reject_more_than_three_options():
    from app.chat.readiness import website_promo_question_items

    payload = group_payload()
    payload.items[0].options = [
        Option(id=str(index), label=f"Option {index}") for index in range(1, 5)
    ]
    with pytest.raises(ValueError, match="1-3"):
        website_promo_question_items(payload.items, Brief())


@pytest.mark.parametrize("label", [
    "中文 + 英文双语",
    "英文配音 + 中文字幕",
    "English and Chinese",
    "English / Chinese",
])
def test_website_promo_rejects_packaged_narration_options(label):
    from app.chat.readiness import website_promo_question_items

    payload = group_payload(numeric_ids=True)
    for item in payload.items:
        item.options = [Option(id="1", label=item.options[0].label)]
    payload.items[3].options = [
        Option(id="1", label="中文"),
        Option(id="2", label=label),
        Option(id="3", label="English (US)"),
    ]
    with pytest.raises(ValueError, match="exactly one spoken language"):
        website_promo_question_items(payload.items, Brief())


def test_website_promo_accepts_single_language_narration_options():
    from app.chat.readiness import website_promo_question_items

    payload = group_payload(numeric_ids=True)
    for item in payload.items:
        item.options = [Option(id="1", label=item.options[0].label)]
    payload.items[3].options = [
        Option(id="1", label="中文"),
        Option(id="2", label="英文"),
        Option(id="3", label="English (US)"),
    ]
    assert len(website_promo_question_items(payload.items, Brief())) == 6


def test_question_item_normalizes_option_labels_to_numeric_ids():
    item = BriefQuestionItem.model_validate({
        "slot": "purpose",
        "question": "Choose a purpose",
        "options": ["Website", "Brand"],
    })
    assert [(option.id, option.label) for option in item.options] == [
        ("1", "Website"), ("2", "Brand"),
    ]


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


def test_website_promo_group_requires_current_missing_fields_and_numeric_options():
    from app.chat.readiness import website_promo_question_items

    items = [
        item.model_copy(update={
            "options": [Option(id="1", label=item.options[0].label)],
        })
        for item in group_payload().items
    ]
    assert len(website_promo_question_items(items, Brief())) == 6

    with pytest.raises(ValueError, match="one items group"):
        website_promo_question_items([], Brief())
    with pytest.raises(ValueError, match="exactly the current missing fields"):
        website_promo_question_items(items[:1], Brief())

    invalid = [
        items[0].model_copy(update={
            "options": [Option(id="website", label="Website")],
        }),
        *items[1:],
    ]
    with pytest.raises(ValueError, match="numeric ids"):
        website_promo_question_items(invalid, Brief())


def test_group_title_stays_out_of_the_message_prose():
    from app.models.schemas import QuestionProposal

    ask = QuestionProposal(prose="Brand evidence is ready.", question="Production setup")
    assert _ask_content(ask, has_dock_options=True) == "Brand evidence is ready."
    assert _ask_content(ask) == "Brand evidence is ready.\n\nProduction setup"


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
