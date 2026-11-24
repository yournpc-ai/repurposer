"""Layer 1A Chat-Origin: activity row lifecycle, replay settlement, and questionnaire group backfill."""

from __future__ import annotations
import pytest

from uuid import uuid4


import pytest


from sqlalchemy import select


from app.agents.tool_loop import ReadAccepted, ReadExecuting


from app.chat.activity import ActivityProjector


from app.chat.service import append_activity_row, record_asset_activity


from app.chat.turn_tools import _video_material_tools


from app.models import database as database_module


from app.models.schemas import AssetStatus, AssetType, PrepareVideoMaterialsArgs


from app.models.tables import Asset, Conversation, Message, Project, User


from app.chat.service import confirmation_need


from app.tools.video.design import _ready_web_pages


def test_read_activity_opens_at_execute_after_the_interim_prose_seat():
    projector = ActivityProjector(_video_material_tools())

    assert projector.name_known("analyze_brand") == []
    assert projector.open_activity() is None
    executing = projector.feed_event(ReadExecuting(tool_name="analyze_brand", params=object()))
    assert projector.open_activity() is not None
    frames = [
        *executing,
        *projector.feed_event(ReadAccepted(tool_name="analyze_brand", ok=True)),
    ]

    assert [(frame.status, frame.key) for frame in frames] == [
        ("active", "chat.activity.brandAnalyze"),
        ("completed", "chat.activity.brandAnalyzeDone"),
    ]


@pytest.mark.parametrize(("params", "key"), [
    ({"material_urls": ["https://www.legitevi.com/en"]}, "viewWebPage"),
    ({"material_music_ids": [uuid4()]}, "videoMaterials"),
    ({"material_urls": ["https://www.legitevi.com/en"], "material_music_ids": [uuid4()]}, "videoMaterials"),
])
def test_material_activity_matches_validated_inputs(params, key):
    projector = ActivityProjector(_video_material_tools())
    name = "prepare_video_materials"
    assert projector.name_known(name) == []
    active, = projector.feed_event(ReadExecuting(name, PrepareVideoMaterialsArgs(**params)))
    done, = projector.feed_event(ReadAccepted(tool_name=name, ok=True))
    assert active.key == f"chat.activity.{key}"
    assert done.key == f"chat.activity.{key}Done"
    assert active.activity_id == done.activity_id


@pytest.mark.asyncio
async def test_late_asset_completion_reuses_the_originating_activity_row(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Late completion")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        await db.commit()
        turn_id = uuid4()
        db.add(Message(
            id=turn_id, conversation_id=conversation.id, role="user",
            content="make a promo", turn_id=turn_id, turn_state="settled", seq=1,
        ))
        row = await append_activity_row(db, conversation.id, {
            "activity_id": "prepare-materials-invocation",
            "kind": "read",
            "status": "completed",
            "key": "chat.activity.videoMaterialsDone",
        }, turn_id=turn_id)
        await db.commit()

        result = await record_asset_activity(
            db, user.id, project.id,
            status="completed", name="about-us", count=3, total=3,
            ref="child-page", duration_ms=53_000, asset_type="web_page",
            at=None, turn_id=str(turn_id),
        )
        await db.commit()

        assert result.id == row.id
        rows = list((await db.execute(
            select(Message).where(Message.intent["type"].astext == "activity")
        )).scalars().all())
        assert len(rows) == 1
        assert rows[0].intent["type"] == "activity"


@pytest.mark.asyncio
async def test_background_asset_completion_uses_the_same_activity_protocol(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Background completion")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        await db.commit()

        row = await record_asset_activity(
            db, user.id, project.id,
            status="completed", name="upload.mov", count=1, total=1,
            ref="asset-1", duration_ms=100, asset_type="video",
            at=None, turn_id=None,
        )
        await db.commit()

        assert row.intent["type"] == "activity"
        assert row.intent["frame"]["activity_id"] == "asset-reading:asset-1"
        assert row.intent["frame"]["kind"] == "read"


@pytest.mark.asyncio
async def test_chat_owned_asset_completion_without_a_row_adds_no_independent_activity(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Worker finishes first")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        await db.commit()

        result = await record_asset_activity(
            db, user.id, project.id,
            status="completed", name="early-page", count=1, total=1,
            ref="early-page", duration_ms=10, asset_type="web_page",
            at=None, turn_id=str(uuid4()),
        )

        assert result is None
        assert list((await db.execute(select(Message))).scalars().all()) == []


@pytest.mark.asyncio
async def test_ready_web_pages_waits_for_discovered_children(database):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Discovered children")
        db.add(project)
        await db.flush()
        parent = Asset(
            user_id=user.id, project_id=project.id, type=AssetType.WEB_PAGE,
            title="root", processing_status=AssetStatus.COMPLETED,
            meta={"capture_url": "https://example.com", "shots": [{"view_id": "v0"}]},
        )
        db.add(parent)
        await db.flush()
        child = Asset(
            user_id=user.id, project_id=project.id, type=AssetType.WEB_PAGE,
            title="child", processing_status=AssetStatus.PROCESSING,
            meta={"capture_url": "https://example.com/about", "discovered_from": str(parent.id)},
        )
        db.add(child)
        await db.commit()

        async def settle(_db, _project_id, *, asset_ids):
            current = await db.get(Asset, child.id)
            current.processing_status = AssetStatus.COMPLETED
            current.meta = {**current.meta, "shots": [{"view_id": "v1"}]}
            await db.commit()

        from app.tools.video import design as design_module
        original = design_module._await_captures_settled
        design_module._await_captures_settled = settle
        try:
            rows = await _ready_web_pages(
                db, project_id=project.id, owner_id=user.id, urls={"https://example.com"},
            )
        finally:
            design_module._await_captures_settled = original

        assert {asset.id for asset in rows} == {parent.id, child.id}


def test_unbounded_native_quote_requires_confirmation_for_all_preferences():
    automatic = confirmation_need(
        execution="auto", credits="auto", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    execution_ask = confirmation_need(
        execution="ask", credits="auto", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    credits_ask = confirmation_need(
        execution="auto", credits="ask", quote_high=None,
        unquotable=True, always_confirm_above=5000,
    )
    above_guardrail = confirmation_need(
        execution="auto", credits="auto", quote_high=5001,
        unquotable=False, always_confirm_above=5000,
    )

    assert automatic.requires_confirmation and automatic.reason == "unquotable"
    assert execution_ask.requires_confirmation is True
    assert execution_ask.reason == "unquotable"
    assert credits_ask.requires_confirmation is True
    assert credits_ask.reason == "unquotable"
    assert above_guardrail.requires_confirmation is True
    assert above_guardrail.reason == "above_guardrail"


@pytest.mark.parametrize("ok", [False, True])
def test_mixed_material_steps_update_one_row_and_ignore_stale_progress(ok):
    from app.agents.tool_loop import ToolProgress

    projector = ActivityProjector(_video_material_tools())
    name = "prepare_video_materials"
    projector.name_known(name)
    params = PrepareVideoMaterialsArgs(material_urls=["https://www.legitevi.com/en"], material_music_ids=[uuid4()])
    start, = projector.feed_event(ReadExecuting(name, params, "call-1"))
    web, = projector.feed_event(ToolProgress("call-1", "view_webpage"))
    assert not projector.feed_event(ToolProgress("call-1", "view_webpage"))
    assert not projector.feed_event(ToolProgress("other", "import_music"))
    music, = projector.feed_event(ToolProgress("call-1", "import_music"))
    end, = projector.feed_event(ReadAccepted(name, ok))
    assert {f.activity_id for f in (start, web, music, end)} == {start.activity_id}
    assert [f.key for f in (start, web, music)] == [
        "chat.activity.videoMaterials", "chat.activity.viewWebPage", "chat.activity.importMusic",
    ]
    assert end.key == ("chat.activity.videoMaterialsDone" if ok else music.key)
    assert end.status == ("completed" if ok else "failed")
    assert not projector.feed_event(ToolProgress("call-1", "view_webpage"))


def test_all_chat_tool_registries_declare_a_presentation():
    from app.agents.candidate_correction import correction_tool
    from app.chat.conversation_context import conversation_context_tool
    from app.chat.intent import intent_router

    tools = intent_router.tools
    for tool in [*tools, conversation_context_tool(), correction_tool()]:
        assert tool.presentation is not None, tool.name
        assert tool.presentation.kind == "native" or tool.presentation.active_key, tool.name


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_progress_survives_reload_and_settles_the_original_message(database, monkeypatch, cancel):
    import asyncio
    from app.agents.tool_loop import ToolProgress
    from app.chat.routes import _make_activity_persister, _make_loop_event_hook

    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Progress")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        conversation_id = conversation.id

    async def reload_frame():
        async with database() as db:
            row = (await db.scalars(select(Message).where(Message.conversation_id == conversation_id))).one()
            return row.id, row.intent["frame"]

    projector = ActivityProjector(_video_material_tools())
    queue = asyncio.Queue()
    append, mirror, cancel_open = _make_activity_persister(queue, projector, conversation_id)
    emit = _make_loop_event_hook(queue, projector, append, mirror)
    name = "prepare_video_materials"
    projector.name_known(name)
    params = PrepareVideoMaterialsArgs(material_urls=["https://www.legitevi.com/en"], material_music_ids=[uuid4()])
    await emit(ReadExecuting(name, params, "mixed"))
    row_id, first = await reload_frame()
    await emit(ToolProgress("mixed", "view_webpage"))
    await emit(ToolProgress("mixed", "import_music"))
    mid_id, mid = await reload_frame()
    assert (mid_id, mid["at"], mid["activity_id"]) == (row_id, first["at"], first["activity_id"])
    assert mid["key"] == "chat.activity.importMusic" and mid["status"] == "active"
    assert "settled_at" not in mid
    if cancel:
        await cancel_open()
    else:
        await emit(ReadAccepted(name))
    final_id, final = await reload_frame()
    assert final_id == row_id
    assert final["status"] == ("cancelled" if cancel else "completed")


def test_update_focus_emits_lightweight_sanitized_frame_without_persisting():
    from app.chat.activity import KIND_FOCUS, frame_persistence, sanitize_focus_text
    from app.chat.turn_tools import UPDATE_FOCUS_TOOL, UpdateFocusArgs

    assert UPDATE_FOCUS_TOOL.batchable is True
    assert UPDATE_FOCUS_TOOL.terminal is False
    projector = ActivityProjector([UPDATE_FOCUS_TOOL])
    assert projector.name_known("update_focus") == []
    assert projector.open_activity() is None

    raw = f"正在将 6 幕脚本编排为 Vox 风格 clip_id=clp_01 {uuid4()} /Users/demo/a.mp4"
    frames = projector.feed_event(
        ReadExecuting(tool_name="update_focus", params=UpdateFocusArgs(focus=raw), call_id="f1")
    )
    assert len(frames) == 1
    frame = frames[0]
    assert frame.kind == KIND_FOCUS
    assert frame.status == "active"
    assert frame.focus == "正在将 6 幕脚本编排为 Vox 风格"
    assert frame_persistence(frame) is None
    assert projector.open_activity() is None
    assert not projector.has_active()
    assert projector.feed_event(ReadAccepted(tool_name="update_focus", ok=True)) == []
    assert projector.settled_frames() == []
    assert sanitize_focus_text("a" * 80, max_len=20).endswith("…")


def test_project_tool_detail_covers_all_high_frequency_editor_tools_without_internal_ids():
    from app.chat.activity import project_tool_detail
    from app.chat.editor import (
        AudioDuckWindowArgs,
        EditAudioClipArgs,
        EditTextArgs,
        GenerateSfxArgs,
        InsertMotionBlockArgs,
        InsertTextArgs,
        SetCompositionStyleArgs,
        SetTransitionArgs,
        UpdateMotionBlockArgs,
    )

    leaked_id = str(uuid4())
    cases = [
        (
            "set_composition_style",
            SetCompositionStyleArgs(preset_id="vox_editorial"),
            {"kind": "style", "preset": "vox_editorial"},
        ),
        (
            "insert_motion_block",
            InsertMotionBlockArgs(
                block_id="data_chart",
                start_seconds=12.0,
                end_seconds=17.0,
                props={"title": "Growth", "bars": [{"label": "Q1", "value": 10}]},
            ),
            {"kind": "motion_block_insert", "block": "data_chart", "window": "12–17s"},
        ),
        (
            "update_motion_block",
            UpdateMotionBlockArgs(
                clip_id="clp_motion_99",
                props_patch={"camera_preset": "dolly_zoom", "callout_steps": []},
            ),
            {"kind": "motion_block_update", "aspects": ["camera", "callout"]},
        ),
        (
            "insert_text",
            InsertTextArgs(
                text="SARAH LIN · HEAD OF DESIGN",
                start_seconds=0.5,
                end_seconds=4.0,
                preset_id="lower_third_tag",
                position="bottom_left",
            ),
            {
                "kind": "text_insert",
                "preset": "lower_third_tag",
                "position": "bottom_left",
                "role": "title",
                "window": "0.5–4s",
                "snippet": "SARAH LIN · HEAD…",
            },
        ),
        (
            "insert_text",
            InsertTextArgs(
                text="第一行中文\nSecond English line",
                start_seconds=0.5,
                end_seconds=4.0,
                preset_id="bilingual_cinema",
                role="caption",
            ),
            {
                "kind": "text_insert",
                "preset": "bilingual_cinema",
                "role": "caption",
                "bilingual": True,
                "window": "0.5–4s",
                "snippet": "第一行中文",
            },
        ),
        (
            "insert_text",
            InsertTextArgs(from_audio_clip_id="clp_voice_01", preset_id="karaoke_focus"),
            {"kind": "text_caption_from_audio", "preset": "karaoke_focus"},
        ),
        (
            "edit_text",
            EditTextArgs(scope="all_derived_captions", preset_id="karaoke_focus"),
            {"kind": "text_edit", "scope": "all_derived_captions", "preset": "karaoke_focus"},
        ),
        (
            "generate_sfx",
            GenerateSfxArgs(recipe_id="sub_swell", base_clip_id="clp_sfx_01"),
            {"kind": "sfx", "recipe": "sub_swell"},
        ),
        (
            "edit_audio_clip",
            EditAudioClipArgs(
                clip_id="clp_bgm_01",
                gain_db=-24.0,
                fade_in_seconds=0.5,
                duck_windows=[AudioDuckWindowArgs(start_seconds=1.0, end_seconds=4.0)],
            ),
            {"kind": "audio_edit", "aspects": ["gain", "fade"]},
        ),
        (
            "set_transition",
            SetTransitionArgs(from_clip_id="clp_1", to_clip_id="clp_2", kind="zoom_through"),
            {"kind": "transition", "preset": "zoom_through"},
        ),
    ]
    for tool_name, params, expected in cases:
        detail = project_tool_detail(tool_name, params)
        assert detail == expected, (tool_name, detail)
        serialized = str(detail)
        assert "clp_" not in serialized
        assert leaked_id not in serialized


@pytest.mark.asyncio
async def test_semantic_detail_persists_through_activity_row_lifecycle(database, monkeypatch):
    import asyncio
    from app.chat.editor import EDITOR_TOOLS, InsertMotionBlockArgs
    from app.chat.routes import _make_activity_persister, _make_loop_event_hook

    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Semantic Detail")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        conversation_id = conversation.id

    projector = ActivityProjector(EDITOR_TOOLS)
    queue = asyncio.Queue()
    append, mirror, _cancel = _make_activity_persister(queue, projector, conversation_id)
    emit = _make_loop_event_hook(queue, projector, append, mirror)

    projector.name_known("insert_motion_block")
    params = InsertMotionBlockArgs(
        block_id="data_chart", start_seconds=12.0, end_seconds=17.0, props={"title": "Revenue"}
    )
    await emit(ReadExecuting("insert_motion_block", params, "call-mb-1"))
    await emit(ReadAccepted("insert_motion_block", ok=True))

    async with database() as db:
        row = (await db.scalars(select(Message).where(Message.conversation_id == conversation_id))).one()
        frame = row.intent["frame"]
        assert frame["status"] == "completed"
        assert frame["detail"] == {"kind": "motion_block_insert", "block": "data_chart", "window": "12–17s"}


# --- Questionnaire groups & atomic backfill ---

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


from test.support.media_helpers import website_question_arguments


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

