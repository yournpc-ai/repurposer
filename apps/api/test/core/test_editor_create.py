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
from test.core.test_compositions import _project, _snapshots, _user


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
    text = "用 https://example.org/en 做一个总时长 3 秒、16:9、背景 #010203 的网页宣传片初稿，不要导出。"
    async with database() as db:
        db.add(source)
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
            shots=[{"snapshot_id": str(source.id), "view_id": "paper",
                    "headline": "Evidence for everyone", "duration_seconds": 3}],
        )
        with bind_progress("website-first", None):
            result = await create_video(db, turn, args)
        saved = await db.get(CompositionVersion, uuid.UUID(result["version_id"]))
        assert saved.settings["background"] == "#010203"
        assert saved.creative_state["brief"]["target_seconds"]["value"] == 3
        clips = [clip for track in saved.timeline["tracks"] for clip in track["clips"]]
        web = next(clip for clip in clips if clip["object"]["kind"] == "web")
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
