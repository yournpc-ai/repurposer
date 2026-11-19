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
    BriefDecisionPage,
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
from test.core.test_website_promo_readiness import website_question_arguments

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


def website_items():
    return [BriefQuestionItem.model_validate(item) for item in website_question_arguments()["items"]]


def issued_four_page_payload():
    payload = group_payload()
    for item in payload.items:
        value = item.options[0].label
        if item.slot == "target_seconds":
            value = int(value)
        elif item.slot == "subtitle_languages":
            value = [value]
        item.options[0].id = "1"
        item.option_values = {"1": value}
    pages = [
        (["purpose", "target_seconds"], "宣传片主要用在哪里、希望多长？"),
        (["narrative_mode"], "希望采用哪种表达方式？"),
        (["narration_language", "subtitle_languages"], "语言和字幕怎么配置？"),
        (["aspect"], "画面比例需要哪一种？"),
    ]
    by_slot = {item.slot: item for item in payload.items}
    for slots, title in pages:
        by_slot[slots[0]].decision_page = BriefDecisionPage(
            slots=slots, title=title, choices=[{slot: "1" for slot in slots}],
        )
    # An issued question keeps its original token across changes to the Brief schema.
    payload.group_digest = "ab" * 32
    return payload


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
@pytest.mark.parametrize("four_pages", [False, True])
async def test_group_answer_settles_one_row_and_backfills_all_slots_atomically(
    database, monkeypatch, four_pages
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
        payload = issued_four_page_payload() if four_pages else group_payload(numeric_ids=True)
        request = group_request(payload, numeric_ids=True)
        if four_pages:
            for answer in request.answers:
                answer.option_id = "1"
            request.answers.append(BriefAnswerItem(slot="constraints", kind="freeform", text="两幕、24 fps、纯电子 BGM"))
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
        answered, follow_up = await answer_question(
            db, user_id, question_id, request
        )
        assert follow_up is None
        assert answered.answer["kind"] == "group"
        assert len(answered.answer["answers"]) == len(request.answers)
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
        if four_pages:
            from app.tools.video.design import explicit_design_constraints

            assert stored.brief.constraints[0].value == "两幕、24 fps、纯电子 BGM"
            constraints = explicit_design_constraints(brief=stored.brief)
            assert (constraints["scene_count"], constraints["fps"]) == (2, 24)
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
async def test_streamed_ask_only_announces_activity():
    import asyncio
    from app.chat.routes import _make_tool_call_hook

    queue = asyncio.Queue()
    await _make_tool_call_hook(queue)("ask_user")
    assert queue.qsize() == 1
    assert queue.get_nowait().startswith("event: assistant.thinking")


def test_website_promo_question_items_reject_more_than_three_options():
    from app.chat.readiness import website_promo_question_items

    items = website_items()
    items[0].options = [
        Option(id=str(index), label=f"Option {index}") for index in range(1, 5)
    ]
    with pytest.raises(ValueError, match="1-3"):
        website_promo_question_items(items, Brief())


@pytest.mark.parametrize("label", [
    "中文 + 英文双语",
    "英文配音 + 中文字幕",
    "English and Chinese",
    "English / Chinese",
])
def test_website_promo_rejects_packaged_narration_options(label):
    from app.chat.readiness import website_promo_question_items

    items = website_items()
    narration = next(item for item in items if item.slot == "narration_language")
    narration.options = [
        Option(id="1", label="中文"),
        Option(id="2", label=label),
        Option(id="3", label="English (US)"),
    ]
    narration.option_values = {"1": "zh", "2": "en", "3": "en-US"}
    with pytest.raises(ValueError, match="exactly one spoken language"):
        website_promo_question_items(items, Brief())


def test_website_promo_accepts_single_language_narration_options():
    from app.chat.readiness import website_promo_question_items

    items = website_items()
    narration = next(item for item in items if item.slot == "narration_language")
    narration.options = [
        Option(id="1", label="中文"),
        Option(id="2", label="英文"),
        Option(id="3", label="English (US)"),
    ]
    narration.option_values = {"1": "zh", "2": "en", "3": "en-US"}
    assert len(website_promo_question_items(items, Brief())) == 5


def test_website_promo_freezes_clean_choices_from_legacy_model_values():
    from app.chat.readiness import website_promo_question_items

    items = website_items()
    items[1].options = [Option(id="1", label="30 秒（网站首屏投放）")]
    items[1].option_values = {"1": "30"}
    items[4].options = [Option(id="1", label="16:9，官网横幅与展会大屏")]
    items[4].option_values = {"1": "16:9"}
    projected = website_promo_question_items(items, Brief())
    assert projected[1].option_values == {"1": 30}
    assert projected[1].options[0].label == "30 秒"
    assert projected[4].options[0].label == "16:9"
    for invalid in ("30–45", "30 秒", "0", "1.5"):
        items[1].option_values = {"1": invalid}
        with pytest.raises(ValueError, match="target_seconds"):
            website_promo_question_items(items, Brief())


def test_new_direction_cannot_offer_an_audience_only_option():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="release setting and a storytelling treatment"):
        BriefQuestionItem.model_validate({
            "slot": "production_direction", "question": "Who is it for?", "question_language": "en",
            "options": [{"label": "Researchers", "value": "Researchers"}],
        })


@pytest.mark.parametrize(("known_slot", "expected"), [
    ("purpose", "How would you like us to tell the story?"),
    ("narrative_mode", "Where do you plan to show the film?"),
])
def test_website_direction_keeps_only_the_unsettled_part_in_its_question(known_slot, expected):
    from app.chat.readiness import website_promo_question_items

    items = website_items()
    items[0].question_language = "en-US"
    brief = Brief(**{known_slot: BriefSlot(value="previous choice", source=BriefSlotSource.USER_STATED)})
    result = website_promo_question_items(items, brief)[0]
    assert result.question == result.decision_page.title == expected
    assert "question_language" not in result.model_dump(mode="json")


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

    items = website_items()
    assert len(website_promo_question_items(items, Brief())) == 5

    with pytest.raises(ValueError, match="one items group"):
        website_promo_question_items([], Brief())
    assert [item.slot for item in website_promo_question_items(items[:1], Brief())] == [items[0].slot]

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


@pytest.mark.asyncio
async def test_website_question_repair_keeps_the_editors_invitation(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.chat import plan_turn
    from app.chat.intent import intent_router
    from app.models.schemas import ChatRequest
    from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration
    from test.core.test_website_promo_readiness import asset, profile, round_assembly, snapshot

    pending = website_pending()
    project = Project(id=uuid4(), pending_brief=pending.model_dump(mode="json"))
    turn = plan_turn.PlanTurn(
        None, uuid4(), Conversation(id=uuid4()), project,
        ChatRequest(project_id=project.id, message=pending.prompt),
    )
    turn.text = pending.prompt
    monkeypatch.setattr(turn, "_absorb", AsyncMock(return_value=Brief()))
    dock = AsyncMock(return_value=(Message(id=uuid4()), []))
    monkeypatch.setattr(plan_turn, "_dock_question", dock)

    form = website_question_arguments()
    invitation = "我看过官网了，想听听你打算怎么用这支片子。"
    attempts = [
        (invitation, {k: v for k, v in form.items() if k != "question"}),
        ("我修正了一下表单。", {**form, "items": form["items"][:-1]}),
        ("我补上了缺少的字段。", form),
    ]
    monkeypatch.setattr(intent_router, "client", SimpleNamespace(
        capabilities=ProviderCapabilities(supports_native_tools=True),
        generate_with_tools=AsyncMock(side_effect=[
            ToolGeneration(content=words, tool_calls=[ToolCall(id=str(i), name="ask_user", arguments=args)])
            for i, (words, args) in enumerate(attempts)
        ]),
    ))
    assembly = round_assembly(
        pending.prompt, assets=[asset("completed")], snapshots=[snapshot()],
        state=CreativeState(brand_profile=profile()),
    )
    result = await intent_router.call_loop(
        turn.execute, tools=assembly.tools, round_assembler=lambda **_: assembly, message=pending.prompt,
    )
    assert result.tool_name == "ask_user"
    dock.assert_awaited_once()
    assert dock.await_args.args[2] == invitation
    assert dock.await_args.kwargs["intent"]["ask"]["prose"] == invitation


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


def test_decision_page_freeform_preserves_one_sentence_and_validates_coverage():
    from app.chat.service import _backfill_brief_group

    payload = group_payload()
    slots = ['purpose', 'target_seconds']
    payload.items[0].decision_page = BriefDecisionPage(
        slots=slots, title='用途和时长', choices=[],
    )
    payload.group_digest = question_group_digest(payload.items, Brief())
    request = group_request(payload)
    request.group_digest = payload.group_digest
    sentence = '面向科研人员，45 秒'
    request.answers = [
        BriefAnswerItem(slot='purpose', kind='freeform', text=sentence, page_slots=slots),
        *[answer for answer in request.answers if answer.slot not in slots],
    ]
    normalized = _validate_group_answers(payload, request)
    assert normalized[0].text == sentence
    project = Project(pending_brief=PendingPlan(prompt='给官网做一支宣传片').model_dump(mode='json'))
    _backfill_brief_group(project, payload, normalized)
    brief = PendingPlan.model_validate(project.pending_brief).brief
    assert brief.target_seconds.value == 45
    assert any(sentence in constraint.value for constraint in brief.constraints)
    assert brief.target_seconds.value != sentence
    bad = request.model_copy(deep=True)
    bad.answers[0].page_slots = ['purpose', 'aspect']
    with pytest.raises(HTTPException):
        _validate_group_answers(payload, bad)
    duplicate = request.model_copy(deep=True)
    duplicate.answers.append(BriefAnswerItem(slot='target_seconds', kind='freeform', text='60'))
    with pytest.raises(HTTPException):
        _validate_group_answers(payload, duplicate)
