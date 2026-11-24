"""Layer 1A Chat-Origin: creation via POST /api/v1/chat, native motion_blocks, style_preset, /text-animation, and brand seats."""

from __future__ import annotations
import pytest

from datetime import UTC, datetime


from types import SimpleNamespace


from uuid import UUID, uuid4


import httpx


import pytest


from pydantic import ValidationError


from sqlalchemy import func, select


from app.agents.tool_loop import BatchDeclared, BatchMember, ContextSnapshot, ReadExecuting


from app.agents.tool_progress import bind_progress


from app.chat.activity import (
    KIND_STEPS,
    ActivityProjector,
    finalize_steps,
    frame_persistence,
    sanitize_steps,
)


from app.chat.context import conversation_messages


from app.chat.editor import (
    GenerateSfxArgs,
    InsertMotionBlockArgs,
    _remember_labels,
    edit_clip,
    project_editor_reply,
)


from app.chat.editor_create import CreateVideoArgs, create_video


from app.chat.editor_media import execute_generate_sfx


from app.chat.intent import intent_router


from app.chat.plan_turn import run_plan_turn


from app.chat.prompts import assemble_video_round


from app.chat.service import _create_message, prepare_chat_turn


from app.config import settings


from app.dependencies import get_current_user_required, get_db


from app.editing.catalog import MOTION_BLOCK_CATALOG


from app.editing.store import content_of


from app.main import app


from app.models import database as database_module


from app.models.schemas import AssetStatus, AssetType, ChatMessageResponse, ChatRequest


from app.models.tables import (
    Asset,
    Composition,
    CompositionVersion,
    Conversation,
    ExportJob,
    MediaJob,
    Message,
    MessageFeedback,
    Output,
    Project,
    SourceSnapshot,
    User,
)


from app.platform.conversation_context import find_conversation


from app.providers import storage


from app.providers.llm.base import ToolCall, ToolGeneration


from test.support.db_helpers import _project, _user


class _ScriptedClient:
    model = "test-eval-model-v1"
    capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=False)

    def __init__(self, generations: list[ToolGeneration]):
        self._generations = list(generations)
        self.calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        assert self._generations, "Unexpected extra LLM iteration"
        return self._generations.pop(0)


def _api_client(database, user: User):
    async def _override_db():
        async with database() as session:
            yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_required] = _override_user
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_h1_create_video_native_motion_blocks_with_style_and_transitions(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)

    with pytest.raises(ValidationError):
        CreateVideoArgs(name="Empty work")

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner, project_id=project_id, title="Project chat")
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "做一个 3 幕 15 秒动效短片")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(
            project=project,
            conversation_id=conv.id,
            turn_id=opening.id,
            text=opening.content,
        )

    args = CreateVideoArgs(
        name="Rookie Cut Kinetic Promo",
        style_preset="vox_editorial",
        motion_blocks=[
            {
                "block_id": "statement_hook",
                "duration_seconds": 5.0,
                "props": {"headline": "Cut Videos by Chat", "subheadline": "Zero timeline friction"},
                "transition_after": "whip_pan",
                "transition_duration_seconds": 0.5,
            },
            {
                "block_id": "metric_grid",
                "duration_seconds": 5.0,
                "props": {
                    "title": "Real Speed",
                    "items": [
                        {"label": "Draft Time", "value": "3s"},
                        {"label": "Edit Time Saved", "value": "85%"},
                    ],
                },
                "transition_after": "crossfade",
                "transition_duration_seconds": 0.4,
            },
            {
                "block_id": "closing_cta",
                "duration_seconds": 5.0,
                "props": {"brand_name": "Rookie Cut", "tagline": "Ship faster today"},
            },
        ],
    )

    async with database() as db:
        with bind_progress("create-mg-1", None):
            result = await create_video(db, turn, args)

    assert result["saved"] is True
    assert result["version"] == 1
    assert result["duration_seconds"] == pytest.approx(15.0)
    assert len(result["motion_blocks"]) == 3
    assert [b["block_id"] for b in result["motion_blocks"]] == [
        "statement_hook",
        "metric_grid",
        "closing_cta",
    ]
    # H4 check: composition_id full + prefixes registered immediately after create_video
    cid = result["composition_id"]
    assert cid in turn._editor_labels
    assert cid[:8] in turn._editor_labels
    assert cid[:12] in turn._editor_labels

    async with database() as db:
        saved = await db.get(CompositionVersion, UUID(result["version_id"]))
        content = content_of(saved)
        assert content.settings.style is not None
        assert content.settings.style.preset_id == "vox_editorial"
        assert len(content.scenes) == 3
        assert len(content.timeline.transitions) == 2
        assert content.timeline.transitions[0].kind == "whip_pan"
        assert content.timeline.transitions[1].kind == "crossfade"


# --- Native create_video concurrency, external skill & forbidden speech ---

import asyncio


import uuid


from types import SimpleNamespace


from uuid import uuid4


import pytest


from sqlalchemy import func, select


from app.agents.tool_progress import bind_progress


from app.chat.editor_create import CreateVideoArgs, create_video


from app.chat.service import _create_message


from app.editing.store import RequestMismatch


from app.models.tables import Composition, CompositionVersion, Conversation, Message, MessageSeqCounter, Project


from test.support.db_helpers import _project, _snapshots, _user


@pytest.mark.asyncio
async def test_concurrent_first_versions_and_native_call_replay(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, project_id)
        turns = []
        for _ in range(2):
            conversation = Conversation(user_id=owner, project_id=project_id)
            db.add(conversation)
            await db.commit()
            opening = await _create_message(db, conversation.id, "user", "Make a three-second title.")
            opening.turn_state = "in_flight"
            turns.append(SimpleNamespace(project=project, conversation_id=conversation.id, turn_id=opening.id))
        await db.commit()

    args = CreateVideoArgs(name="Title", shots=[{"headline": "Goodbye", "duration_seconds": 3}])

    async def submit(turn, params=args):
        async with database() as session:
            with bind_progress("first-card", None):
                return await create_video(session, turn, params)

    results = await asyncio.gather(*(submit(turn) for turn in turns), return_exceptions=True)
    saved = [index for index, result in enumerate(results) if isinstance(result, dict)]
    assert len(saved) == 1
    winner = saved[0]
    assert isinstance(results[1 - winner], ValueError)
    assert (await submit(turns[winner]))["version_id"] == results[winner]["version_id"]
    with pytest.raises(RequestMismatch):
        await submit(turns[winner], args.model_copy(update={"name": "Different work"}))
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 1
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 1


@pytest.mark.asyncio
async def test_create_video_preserves_creative_state_and_external_skill(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    from types import SimpleNamespace
    from app.chat.editor_create import create_video
    from app.models.schemas import CreativeState, ExternalSkillReference, ProjectBrief
    from app.skills.external import SkillPolicy

    owner = await _user(database)
    state = CreativeState()
    pending = ProjectBrief(creative_state=state, brief=state.brief)
    project_id = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, project_id)
        project.pending_brief = pending.model_dump(mode="json")
        conversation = Conversation(user_id=owner, project_id=project_id)
        db.add(conversation)
        await db.commit()
        opening = await _create_message(db, conversation.id, "user", "Use the external skill")
        opening.turn_state = "in_flight"
        await db.commit()
        skill_id = uuid4()
        skill = SimpleNamespace(
            package=SimpleNamespace(),
            provenance={"source_hash": "abc", "policy": SkillPolicy(mode="adaptive").model_dump(mode="json")},
            version=SimpleNamespace(id=skill_id),
        )
        turn = SimpleNamespace(
            project=project, conversation_id=conversation.id, turn_id=opening.id,
            skill=ExternalSkillReference(kind="external", skill_version_id=skill_id),
        )

    async def load_context(_db, **_kwargs):
        return skill

    placements = []

    async def place(_db, **kwargs):
        placements.append(kwargs)
        return kwargs["content"], "declaration-digest"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.skills.loading.load_skill_creative_context", load_context)
    monkeypatch.setattr("app.chat.editor_create._place_skill_generator", place)
    args = CreateVideoArgs(
        name="Skill first draft",
        shots=[{
            "headline": "Fresh package evidence", "duration_seconds": 4,
            "skill_resource": {"resource_id": "fixed-image"},
        }],
    )
    with bind_progress("skill-create", None):
        result = await create_video(db, turn, args)
    monkeypatch.undo()
    assert len(placements) == 1
    async with database() as db:
        saved = await db.get(CompositionVersion, uuid.UUID(result["version_id"]))
        assert saved.creative_state is not None
        assert saved.skill_provenance["external_skill"] == skill.provenance
        assert saved.skill_provenance["skill_reference"] == {"kind": "external", "skill_version_id": str(skill_id)}
        assert saved.skill_provenance["skill_generator_resources"]["clp_scene_1_skill"]["declaration_digest"] == "declaration-digest"


@pytest.mark.asyncio
async def test_website_source_becomes_editable_version_with_user_constraints(database, monkeypatch):
    from app.chat.readiness import brief_with_user_constraints
    from app.models.schemas import ProjectBrief
    from app.models.tables import Output, SourceSnapshot

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)
    source = SourceSnapshot(
        id=uuid4(), owner_id=owner, origin_project_id=project_id, kind="web",
        digest="a" * 64, storage_key="website/page.json",
        meta={
            "canonical_url": "https://example.org/en",
            "lines": [{"line_id": "line_1", "text": "Evidence for everyone"}],
            "views": [{"view_id": "paper", "heading": "Read the paper",
                       "digest": "b" * 64, "storage_key": "website/paper.png",
                       "width": 1280, "height": 720, "elements": []}],
        },
    )
    image = SourceSnapshot(
        id=uuid4(), owner_id=owner, origin_project_id=project_id, kind="image",
        digest="b" * 64, storage_key="website/paper.png",
        meta={"origin": "web_view", "web_snapshot_id": str(source.id), "view_id": "paper"},
    )
    text = "用 https://example.org/en 制作一条 3 秒、16:9、背景 #010203 的网页宣传片初稿，不要导出。"
    async with database() as db:
        db.add_all([source, image])
        project = await db.get(Project, project_id)
        brief = brief_with_user_constraints(text)
        project.pending_brief = ProjectBrief(prompt=text, brief=brief).model_dump(mode="json")
        conversation = Conversation(user_id=owner, project_id=project_id)
        db.add(conversation)
        await db.commit()
        opening = await _create_message(db, conversation.id, "user", text)
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(
            project=project, conversation_id=conversation.id, turn_id=opening.id,
            text=text, skill=None,
        )
        wrong = CreateVideoArgs(
            name="Wrong duration", aspect="16:9", background="#010203",
            shots=[{"snapshot_id": str(source.id), "view_id": "paper", "duration_seconds": 2}],
        )
        with bind_progress("wrong-duration", None), pytest.raises(ValueError, match="duration"):
            await create_video(db, turn, wrong)
        assert await db.scalar(select(func.count()).select_from(Composition)) == 0
        turn.project = await db.get(Project, project_id)
        args = CreateVideoArgs(
            name="Website evidence", aspect="16:9", background="#010203",
            shots=[{"snapshot_id": str(image.id), "text_color": "#FAFAFA",
                    "headline": "Evidence for everyone", "supporting_text": "Read the paper", "duration_seconds": 3}],
        )
        with bind_progress("website-first", None):
            result = await create_video(db, turn, args)
        saved = await db.get(CompositionVersion, uuid.UUID(result["version_id"]))
        assert saved.settings["background"] == "#010203"
        assert saved.creative_state["brief"]["target_seconds"]["value"] == 3
        clips = [clip for track in saved.timeline["tracks"] for clip in track["clips"]]
        web = next(clip for clip in clips if clip["object"]["kind"] == "web")
        assert all(clip["object"]["style"]["color"] == "#FAFAFA" for clip in clips if clip["object"]["kind"] == "text")
        assert web["object"]["view_id"] == "paper"
        assert web["source"] == {"snapshot_id": str(source.id), "snapshot_digest": source.digest, "source_range": None}
        assert sum((clip["range"]["end"] - clip["range"]["start"]) / saved.settings["timebase"] for clip in clips if clip["object"]["kind"] == "web") == 3
        assert await db.scalar(select(func.count()).select_from(Output)) == 0


@pytest.mark.asyncio
async def test_first_draft_rejects_explicitly_forbidden_speech_before_saving(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)
    text = "做一个 3 秒、16:9 的官网宣传片，不要生成图片、配音、旁白或新增语音，保留原声和配乐，不要导出。"
    async with database() as db:
        project = await db.get(Project, project_id)
        conversation = Conversation(user_id=owner, project_id=project_id)
        db.add(conversation)
        await db.commit()
        opening = await _create_message(db, conversation.id, "user", text)
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(project=project, conversation_id=conversation.id, turn_id=opening.id,
                               text=text, skill=None)
        args = CreateVideoArgs(name="Unexpected speech", shots=[{
            "headline": "Evidence", "duration_seconds": 3,
            "narration": "Unrequested speech", "narration_language": "en",
        }])
        with bind_progress("forbidden-speech", None), pytest.raises(ValueError, match="disallowed narration"):
            await create_video(db, turn, args)
        assert await db.scalar(select(func.count()).select_from(Composition)) == 0
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 0


@pytest.mark.asyncio
async def test_new_project_persists_chat_opening(database, monkeypatch):
    from app.chat.service import prepare_chat_turn
    from app.models.schemas import ChatRequest

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)
    async with database() as db:
        turn = await prepare_chat_turn(
            db=db, user_id=owner,
            request=ChatRequest(project_id=project_id, message="Create a title"),
        )
    assert await db_scalar_count(database, Message) == 1
    assert turn.user_message.turn_state == "in_flight"


async def db_scalar_count(factory, entity):
    async with factory() as db:
        return await db.scalar(select(func.count()).select_from(entity))


# --- Website analyze_brand seat persistence ---

import json


from uuid import uuid4


import pytest


from app.chat.readiness import (
    brief_with_user_constraints,
    compute_source_readiness,
)


from app.models import tables as _tables  # noqa: F401 — register metadata for the disposable DB


from app.models.schemas import (
    BrandProfile,
    BrandSourceRef,
    Brief,
    BriefSlot,
    BriefSlotSource,
    CreativeState,
)


URL = "https://www.legitevi.com/en"


def website_question_arguments():
    return {
        "question": "宣传片制作偏好",
        "items": [
            {"slot": "production_direction", "question": "这支片子打算在哪里播、怎么讲？",
             "options": [{"label": "官网推广 · 用真实案例演示产品", "value": "官网推广 · 用真实案例演示产品"},
                         {"label": "发布会开场 · 用品牌使命串起故事", "value": "发布会开场 · 用品牌使命串起故事"}]},
            {"slot": "target_seconds", "question": "希望片长是多少秒？",
             "options": [{"label": "30 秒", "value": 30}, {"label": "60 秒", "value": 60}]},
            {"slot": "narration_language", "question": "旁白用哪种语言？",
             "options": [{"label": "英文", "value": "en"}, {"label": "中文", "value": "zh"}]},
            {"slot": "subtitle_languages", "question": "字幕需要哪些语言？",
             "options": [{"label": "英文", "value": ["en"]}, {"label": "中文", "value": ["zh"]}]},
            {"slot": "aspect", "question": "画面比例选哪种？", "options": [{"label": "16:9", "value": "16:9"}, {"label": "9:16", "value": "9:16"}]},
        ],
        "default_path": "按推荐设置制作",
    }


def asset(status="pending", *, shots=True):
    return {
        "kind": "asset",
        "type": "web_page",
        "asset_id": "asset-1",
        "status": status,
        "url": URL,
        "text_snapshot_id": "snapshot-1",
        "captured_view_count": 1 if shots else 0,
        "meta": {
            "capture_url": URL,
            "research": {"body": ["Citations should be as universal as hashtags."]}
            if status == "completed"
            else None,
            "shots": [{"key": "sources/hero.png"}] if shots else [],
        },
    }


def snapshot(*, views=True):
    return {
        "snapshot_id": "snapshot-1",
        "kind": "web",
        "digest": "a" * 64,
        "canonical_url": URL,
        "citable_lines": [
            {"line_id": "line_0000", "text": "Citations should be as universal as hashtags."}
        ],
        "views": [
            {
                "view_id": "hero",
                "storage_key": "sources/hero.png",
                "digest": "b" * 64,
                "width": 1440,
                "height": 900,
                "artifact_role": "view",
            }
        ]
        if views
        else [],
    }


def complete_brief():
    values = {
        "purpose": "website",
        "target_seconds": 60,
        "narrative_mode": "mission_tech",
        "narration_language": "en",
        "subtitle_languages": ["en"],
        "aspect": "16:9",
    }
    return Brief(
        **{
            slot: BriefSlot(value=value, source=BriefSlotSource.USER_STATED)
            for slot, value in values.items()
        }
    )


def profile():
    from app.chat.readiness import WEBSITE_BRAND_EXTRACTOR_VERSION

    return BrandProfile(
        extractor_version=WEBSITE_BRAND_EXTRACTOR_VERSION,
        source_refs=[BrandSourceRef(snapshot_id="snapshot-1", digest="a" * 64)],
        content_digest="c" * 64,
    )


def round_assembly(text, *, assets, snapshots=(), state=None, pending=None, material_pending=False):
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.prompts import assemble_video_round
    from app.chat.editor import EDITOR_TOOLS
    from app.chat.turn_tools import PLAN_TOOLS, _video_material_tools

    resources = tuple(
        [("asset:1", item) for item in assets] + [("snapshot:1", item) for item in snapshots]
    )
    return assemble_video_round(
        {
            "tools": [*PLAN_TOOLS, *_video_material_tools(), *EDITOR_TOOLS],
            "drafts": (),
            "snapshot": ContextSnapshot(
                "evidence", frozenset(key for key, _ in resources), resources=resources
            ),
            "mode": "plan",
            "user_text": text,
            "creative_state": state,
            "pending_question": pending,
            "material_pending": material_pending,
        }
    )


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_analyze_brand_seat_commits_state_independently_without_mutating_snapshot(
    database, monkeypatch
):
    from copy import deepcopy
    from uuid import uuid4

    from app.chat.video_turn_seats import analyze_brand_seat
    from app.models.schemas import (
        AnalyzeBrandArgs,
        BrandColor,
        BrandTagline,
        BrandTypography,
        MediaInput,
        MediaInputType,
        ProjectBrief,
    )
    from app.models.tables import Project, SourceSnapshot, User
    from app.tools.video.brand_agent import BrandProfileExtraction, brand_profile_agent

    async with database() as db:
        user = User(id=uuid4(), email=f"{uuid4().hex}@example.com")
        db.add(user)
        await db.flush()
        project = Project(
            id=uuid4(),
            user_id=user.id,
            title="LegitEvi",
            pending_brief=ProjectBrief().model_dump(mode="json"),
        )
        db.add(project)
        await db.flush()
        source = SourceSnapshot(
            id=uuid4(),
            owner_id=user.id,
            origin_project_id=project.id,
            kind="web",
            digest="a" * 64,
            storage_key="sources/page.json",
            meta={
                "canonical_url": URL,
                "lines": [
                    {
                        "line_id": "line_0000",
                        "text": "Citations should be as universal as hashtags.",
                    }
                ],
                "views": snapshot()["views"],
            },
        )
        db.add(source)
        await db.commit()
        original_meta = deepcopy(source.meta)
        project_id, source_id, user_id = project.id, source.id, user.id

    extraction = BrandProfileExtraction(
        positioning="Universal citation infrastructure",
        taglines=[
            BrandTagline(
                text="Citations should be as universal as hashtags.", line_ids=["line_0000"]
            )
        ],
        colors=[BrandColor(value="#DC0000", source="visual", confidence="inferred")],
        typography=[BrandTypography(candidate="Inter", source="visual", confidence="inferred")],
    )

    class FakeClient:
        async def generate(self, *, messages, response_model, **kwargs):
            assert (
                sum(
                    part.get("type") == "image_url"
                    for message in messages
                    for part in (
                        message.get("content") if isinstance(message.get("content"), list) else []
                    )
                )
                == 1
            )
            return extraction

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.video.brand.AsyncSessionLocal", database)
    monkeypatch.setattr(brand_profile_agent, "client", FakeClient())
    monkeypatch.setattr(
        "app.tools.video.design._view_media_inputs",
        lambda *args, **kwargs: _async_value(
            [
                MediaInput(
                    type=MediaInputType.IMAGE,
                    mime="image/png",
                    data_url="data:image/png;base64,iVBORw0KGgo=",
                )
            ]
        ),
    )
    text = (
        f"给 {URL} 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    )
    async with database() as db:
        project = await db.get(Project, project_id)
        observation = await analyze_brand_seat(
            project=project, args=AnalyzeBrandArgs(), user_text=text
        )
        assert observation.ok
        assert observation.images == ()

    async with database() as db:
        stored = ProjectBrief.model_validate((await db.get(Project, project_id)).pending_brief)
        assert stored.creative_state is not None
        assert stored.creative_state.content_digest
        assert stored.creative_state.brief.target_seconds.value == 60
        assert stored.creative_state.brief.aspect.value == "16:9"
        assert stored.creative_state.brief.narrative_mode.value == "mission_tech"
        assert stored.creative_state.brief.narration_language.value == "en"
        assert stored.creative_state.brief.subtitle_languages.value == ["en"]
        assert stored.creative_state.brand_profile.source_refs[0].snapshot_id == str(source_id)
        assert (
            stored.creative_state.brand_profile.taglines[0].text
            == "Citations should be as universal as hashtags."
        )
        assert stored.creative_state.brand_profile.typography[0].candidate == "接近 Inter"
        unchanged = await db.get(SourceSnapshot, source_id)
        assert unchanged.meta == original_meta
        assert unchanged.digest == "a" * 64
        assert user_id == unchanged.owner_id


@pytest.mark.asyncio
async def test_analyze_brand_seat_recovers_source_and_brief_from_pending_prompt(
    database, monkeypatch
):
    from app.chat.video_turn_seats import analyze_brand_seat
    from app.models.schemas import AnalyzeBrandArgs, ProjectBrief
    from app.models.tables import Project, User

    prompt = (
        f"给 {URL} 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    )
    async with database() as db:
        user = User(id=uuid4(), email=f"{uuid4().hex}@example.com")
        db.add(user)
        await db.flush()
        project = Project(
            id=uuid4(),
            user_id=user.id,
            title="Resume brand analysis",
            pending_brief=ProjectBrief(prompt=prompt).model_dump(mode="json"),
        )
        db.add(project)
        await db.commit()
        project_id = project.id

    captured = {}
    result_profile = profile()

    async def fake_analyze_brand(**kwargs):
        captured.update(kwargs)
        return result_profile, {"brand_profile": result_profile.model_dump(mode="json")}

    monkeypatch.setattr("app.tools.video.brand.analyze_brand", fake_analyze_brand)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    async with database() as db:
        project = await db.get(Project, project_id)
        observation = await analyze_brand_seat(
            project=project,
            args=AnalyzeBrandArgs(),
            user_text="继续",
        )
        assert observation.ok

    assert captured["user_text"] == prompt
    assert captured["brief"].target_seconds.value == 60
    assert captured["brief"].aspect.value == "16:9"
    assert captured["brief"].narrative_mode.value == "mission_tech"
    assert captured["brief"].narration_language.value == "en"
    assert captured["brief"].subtitle_languages.value == ["en"]
    async with database() as db:
        stored = ProjectBrief.model_validate((await db.get(Project, project_id)).pending_brief)
        assert stored.creative_state is not None
        assert stored.creative_state.brief.target_seconds.value == 60
        assert stored.creative_state.brand_profile == result_profile



# --- Flagship Real HTTP POST /api/v1/chat (SSE) End-to-End Creation Journey ---


@pytest.mark.asyncio
async def test_chat_endpoint_sse_creates_motion_block_video_with_focus_steps_and_zero_id_leaks(
    database, monkeypatch
):
    """Real user door: POST /api/v1/chat (Accept: text/event-stream) -> update_focus +
    update_steps + create_video(motion_blocks, style_preset) -> SSE telemetry + DB + /workbench."""
    from scripts.eval_chat_e2e import collect_sse_telemetry, parse_sse_frames, score_chat_turn
    from test.support.db_helpers import ScriptedToolClient, bind_test_database, full_api_client

    bind_test_database(monkeypatch, database)

    owner_id = await _user(database)
    project_id = await _project(database, owner_id, title="Chat Origin Flagship")
    async with database() as db:
        owner = await db.get(User, owner_id)

    scripted = ScriptedToolClient(
        [
            ToolGeneration(
                content="",
                tool_calls=[
                    ToolCall(
                        id="c_focus_1",
                        name="update_focus",
                        arguments={"focus": "正在编排三幕深色发布动效短片"},
                    ),
                    ToolCall(
                        id="c_steps_1",
                        name="update_steps",
                        arguments={
                            "steps": [
                                {"title": "创建三幕动效初稿", "status": "in_progress"},
                                {"title": "检查节奏与风格", "status": "pending"},
                            ]
                        },
                    ),
                    ToolCall(
                        id="c_create_1",
                        name="create_video",
                        arguments={
                            "name": "Rookie Cut Launch",
                            "style_preset": "institutional_dark",
                            "motion_blocks": [
                                {
                                    "block_id": "statement_hook",
                                    "duration_seconds": 4.0,
                                    "props": {"headline": "写一句话，直接成片"},
                                },
                                {
                                    "block_id": "metric_grid",
                                    "duration_seconds": 5.0,
                                    "props": {
                                        "columns": 2,
                                        "items": [
                                            {"value": "10x", "label": "剪辑效率"},
                                            {"value": "1080p", "label": "成片直出"},
                                        ],
                                    },
                                },
                                {
                                    "block_id": "closing_cta",
                                    "duration_seconds": 4.0,
                                    "props": {
                                        "brand_name": "Rookie Cut",
                                        "tagline": "AI 视频工作台",
                                        "cta_label": "立即体验",
                                    },
                                },
                            ],
                        },
                    ),
                ],
            ),
            ToolGeneration(
                content="已为你生成 13 秒三幕深色发布动效初稿，你可以在右侧工作台预览或继续微调。",
                tool_calls=[ToolCall(id="c_ans_1", name="answer", arguments={"pending_disposition": "none"})],
            ),
        ],
        streaming=True,
    )
    monkeypatch.setattr(intent_router, "client", scripted)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: scripted)

    try:
        async with full_api_client(database, owner) as client:
            resp = await client.post(
                "/api/v1/chat",
                json={"project_id": str(project_id), "message": "做一个 13 秒三幕深色发布动效短片"},
                headers={"Accept": "text/event-stream"},
            )
            assert resp.status_code == 200, resp.text
            assert "text/event-stream" in resp.headers.get("content-type", "")

            frames = parse_sse_frames(resp.text)
            telemetry = collect_sse_telemetry(frames)
            score = score_chat_turn(
                turn_index=1,
                prompt="做一个 13 秒三幕深色发布动效短片",
                telemetry=telemetry,
                elapsed_seconds=0.5,
                require_steps_or_focus=True,
            )
            assert score.passed is True, score
            assert score.focus_count >= 1
            assert score.steps_count >= 1
            assert score.internal_id_leaks == []
            assert telemetry.done_payload is not None
            conv_id = telemetry.done_payload["conversation_id"]

            # Verify persisted workbench shows the newly created 3-act institutional_dark composition
            wb_resp = await client.get(f"/api/v1/projects/{project_id}/workbench")
            assert wb_resp.status_code == 200
            wb = wb_resp.json()
            assert len(wb["compositions"]) == 1
            assert wb["compositions"][0]["name"] == "Rookie Cut Launch"
            assert wb["compositions"][0]["versions"][0]["style_preset"] == "institutional_dark"
            assert wb["compositions"][0]["versions"][0]["is_head"] is True

            # Verify GET /messages replays persisted steps & clean assistant reply
            msgs_resp = await client.get(f"/api/v1/chat/conversations/{conv_id}/messages")
            assert msgs_resp.status_code == 200
            asst_items = [m for m in msgs_resp.json()["items"] if m["role"] == "assistant" and m.get("steps")]
            assert len(asst_items) >= 1
            assert asst_items[-1]["steps"][0]["status"] == "done"
    finally:
        app.dependency_overrides.clear()
