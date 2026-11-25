"""Editing splits and authoring — chat origin contracts."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.models.tables import MessageSeqCounter, Project, User
from app.skills.resolution import get_builtin_skill_option
from test.support.chat_http import scripted_chat, tool
from test.support.db_helpers import _create, _project, _snapshots, _user

pytestmark = pytest.mark.chat_origin


@pytest.mark.asyncio
async def test_new_opening_does_not_inherit_historical_skill(database, monkeypatch, installed_promo):
    from app.models.tables import Conversation, Message

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project = await _project(database, owner)
    skill = get_builtin_skill_option("promo-video").reference
    async with database() as db:
        conversation = Conversation(
            user_id=owner,
            project_id=project,
        )
        db.add(conversation)
        await db.flush()
        clarification = uuid4()
        db.add_all([
            Message(
                conversation_id=conversation.id,
                role="user",
                content="first",
                turn_state="settled",
                seq=1,
                intent={"skill": skill.model_dump(mode="json")},
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                id=clarification,
                content="clarify",
                turn_state="settled",
                seq=2,
                intent={
                    "skill": skill.model_dump(mode="json"),
                    "skill_binding": "inherited",
                },
            ),
            Message(conversation_id=conversation.id, role="assistant", content="Which title?",
                    turn_id=clarification, seq=3, question={"kind": "question", "question": "Which title?"}),
        ])
        db.add(MessageSeqCounter(conversation_id=conversation.id, last_seq=3))
        await db.commit()
        llm, frames = await scripted_chat(database, monkeypatch, owner, project, "save the draft",
                                          [tool("answer", {}, "Ready.")], conversation_id=str(conversation.id))
        opening = await db.get(Message, UUID(frames[-1][1]["user_message"]["id"]))
        assert not (opening.intent or {}).get("skill")
        assert "read_skill_reference" not in {t["function"]["name"] for t in llm.calls[0]["tools"]}


async def test_split_then_trim_the_saved_clip(database, monkeypatch):
    from app.models.tables import Composition, CompositionVersion
    from test.support.chat_http import tool_result

    owner = await _user(database)
    project = await _project(database, owner)
    await _snapshots(database, owner)
    work, base, _ = await _create(database, owner, project)
    split, frames = await tool_result(
        database, monkeypatch, owner, project, "Split the background at two seconds.",
        "split_clip", {"clip_id": "clp_bg", "time": 2}, operation="app.chat.editor.edit_clip",
    )
    right = split["right_clip_id"]
    trimmed, _ = await tool_result(
        database, monkeypatch, owner, project, "Trim the second half of the background.",
        "trim_clip", {"clip_id": right, "start": 0.4, "end": 1.4}, operation="app.chat.editor.edit_clip",
        conversation_id=frames[-1][1]["conversation_id"],
    )
    async with database() as db:
        head = await db.get(CompositionVersion, (await db.get(Composition, work.id)).current_version_id)
        assert str(head.id) == trimmed["version_id"]
        assert str(head.base_version_id) == split["version_id"]
        assert (await db.get(CompositionVersion, head.base_version_id)).base_version_id == base.id
        clip = next(c for track in head.timeline["tracks"] for c in track["clips"] if c["clip_id"] == right)
        assert clip["range"] == {"start": 216000, "end": 306000}
