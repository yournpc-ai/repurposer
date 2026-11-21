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
    from app.models.schemas import CreativeState, ExternalSkillReference, PendingPlan
    from app.skills.external import SkillPolicy

    owner = await _user(database)
    state = CreativeState()
    pending = PendingPlan(creative_state=state, brief=state.brief)
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
async def test_working_draft_migration_saves_valid_content_and_rejects_without_data_loss(database):
    from app.chat.editor_create import migrate_working_drafts
    from app.editing.store import content_of
    from test.core.fixtures import valid_content

    owner = await _user(database)
    project_id = await _project(database, owner)
    await _snapshots(database, owner)
    async with database() as db:
        project = await db.get(Project, project_id)
        conversation = Conversation(user_id=owner, project_id=project_id)
        db.add(conversation)
        await db.commit()
        draft_id = "cnd_valid"
        conversation.context = {"schema_version": 1, "items": [{
            "id": "valid-item", "turn_id": str(uuid4()), "tool": "design_video", "target_tool": "design_video",
            "executed_arguments": {"content": valid_content().model_dump(mode="json"), "design": {"name": "Recovered work"}},
            "candidate": {"candidate_id": draft_id, "candidate_digest": "d" * 64, "active": True},
            "text": "{}", "ok": True,
        }]}
        migrations = await migrate_working_drafts(db, project, conversation)
        assert migrations[draft_id]["status"] == "saved"
        versions = list((await db.scalars(select(CompositionVersion))).all())
        assert len(versions) == 1
        assert content_of(versions[0]).settings.width == 1920
        assert conversation.context["items"][0]["candidate"]["active"] is False

        invalid_id = "cnd_invalid"
        conversation.context["items"].append({
            "id": "invalid-item", "turn_id": str(uuid4()), "tool": "design_video", "target_tool": "design_video",
            "executed_arguments": {"content": {"settings": {"width": 1920, "height": 1080}, "scenes": [], "timeline": {"tracks": []}}, "design": {}},
            "candidate": {"candidate_id": invalid_id, "candidate_digest": "e" * 64, "active": True},
            "text": "{}", "ok": False,
        })
        migrations = await migrate_working_drafts(db, project, conversation)
        assert migrations[invalid_id]["status"] == "rejected"
        assert len(list((await db.scalars(select(CompositionVersion))).all())) == 1
        assert conversation.context["items"][-1]["candidate"]["active"] is True
        assert project.pending_brief is None
        assert conversation.context["working_draft_migrations"][draft_id]["status"] == "saved"


@pytest.mark.asyncio
async def test_website_source_becomes_editable_version_with_user_constraints(database, monkeypatch):
    from app.chat.readiness import brief_with_user_constraints
    from app.models.schemas import PendingPlan
    from app.models.tables import Output, SourceSnapshot, WorkflowRun

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
        project.pending_brief = PendingPlan(prompt=text, brief=brief).model_dump(mode="json")
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
        assert await db.scalar(select(func.count()).select_from(WorkflowRun)) == 0
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
async def test_rejected_draft_stays_visible_without_reopening_creation(database, monkeypatch):
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.editor_create import migrate_working_drafts
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round
    from app.tools.project_context import load_project_context

    owner = await _user(database)
    project_id = await _project(database, owner)
    async with database() as db:
        project = await db.get(Project, project_id)
        conversation = Conversation(user_id=owner, project_id=project_id)
        db.add(conversation)
        await db.commit()
        conversation.context = {"schema_version": 1, "items": [{
            "id": "invalid-only", "turn_id": str(uuid4()), "tool": "design_video", "target_tool": "design_video",
            "executed_arguments": {"content": {"settings": {"width": 320, "height": 180}, "scenes": [], "timeline": {"tracks": []}}, "design": {}},
            "candidate": {"candidate_id": "cnd_only_invalid", "candidate_digest": "e" * 64, "active": True},
            "text": "{}", "ok": False,
        }]}
        await migrate_working_drafts(db, project, conversation)
        snapshot = await load_project_context(db, project_id=project_id, owner_id=owner)
        assert any(resource.get("kind") == "working_draft_recovery" for _, resource in snapshot.resources)
        assembly = assemble_video_round({
            "tools": intent_router.tools, "snapshot": snapshot,
            "user_text": "请继续这个草稿。", "mode": "plan",
        })
        assert assembly.stage == "working_draft_unavailable"
        assert {tool.name for tool in assembly.tools} == {"answer"}
        assert conversation.context["items"][0]["candidate"]["active"] is True
        from app.chat.service import prepare_chat_turn
        from app.models.schemas import ChatRequest

        turn = await prepare_chat_turn(db, owner, ChatRequest(project_id=project_id, message="请继续这个草稿。"))
        assert await db.get(Message, turn.user_message.id) is not None
        assert turn.user_message.turn_state == "in_flight"
        assert await db.scalar(select(func.count()).select_from(Composition)) == 0


@pytest.mark.asyncio
async def test_empty_project_does_not_open_migration_session(database, monkeypatch):
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
