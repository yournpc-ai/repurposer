"""Replay the Nov 20 music Start validation in a disposable Postgres database.

From apps/api:
PYTHONPATH=. .venv/bin/pytest -qs ../../artifacts/diagnostics/round2_music_start_probe.py
"""
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select, text

from app.models.database import AsyncSessionLocal
from app.models.tables import Conversation, Message, Project, User
from app.tools.video.narration_draft import NarrationDraftError
from app.tools.video.production import pin_music_preparation
from test.core.conftest import database  # noqa: F401 -- disposable database fixture

CONVERSATION = UUID("ac068938-93c6-48ee-b2e3-523f728e6404")
PLAN = UUID("769cab4f-79bc-407f-9ca2-1ad5555a85de")


def context(items):
    return {"schema_version": 1, "items": items}


def digest(item):
    return item["candidate"]["candidate_digest"]


@pytest.mark.asyncio
async def test_music_start_reader_visibility(database):
    async with AsyncSessionLocal() as source:
        await source.execute(text("SET TRANSACTION READ ONLY"))
        archive = await source.get(Conversation, CONVERSATION)
        plan = await source.get(Message, PLAN)
        task = SimpleNamespace(**plan.intent["tasks"][0])
        records = [
            item for item in archive.context["items"]
            if (item.get("candidate") or {}).get("candidate_id") == task.params["draft_ref"]["draft_id"]
            and item.get("ok") is not False
            and item.get("executed_arguments", {}).get("content")
        ]
        stages = [next(item for item in records if digest(item).startswith(prefix))
                  for prefix in ("3a0ef9de9bc8", "a9454bfb64f6", "ac1b07660b91")]

    async with database() as seed:
        owner = User(email="round2-probe@example.invalid")
        seed.add(owner)
        await seed.flush()
        project = Project(user_id=owner.id, title="Isolated music Start probe")
        seed.add(project)
        await seed.flush()
        seed.add(Conversation(id=CONVERSATION, project_id=project.id, user_id=owner.id,
                              context=context(stages[:1])))
        await seed.commit()

    async with database() as reader:
        held = await reader.get(Conversation, CONVERSATION)
        for count in (2, 3):
            async with database() as writer:
                row = await writer.get(Conversation, CONVERSATION)
                row.context = context(stages[:count])
                await writer.commit()
        # A column SELECT bypasses ORM entity hydration in the same transaction.
        persisted = await reader.scalar(select(Conversation.context).where(Conversation.id == CONVERSATION))
        print("isolation", await reader.scalar(text("SHOW transaction_isolation")))
        print("ORM", digest(held.context["items"][-1]), "SQL", digest(persisted["items"][-1]))
        assert digest(held.context["items"][-1]) == digest(stages[0])
        assert digest(persisted["items"][-1]) == task.params["draft_ref"]["draft_digest"]
        result = await pin_music_preparation(reader, project, [task])
        print("score", result["music_preparation"]["score_digest"])
        assert result["music_preparation"]["score_digest"].startswith("537e8abe775e")
        stale = deepcopy(task)
        stale.params["draft_ref"]["draft_digest"] = digest(stages[0])
        with pytest.raises(NarrationDraftError, match="draft_ref is stale or inactive"):
            await pin_music_preparation(reader, project, [stale])

        async with database() as writer:
            row = await writer.get(Conversation, CONVERSATION)
            inactive = deepcopy(stages[-1])
            inactive["candidate"]["active"] = False
            row.context = context([*stages, inactive])
            await writer.commit()
        with pytest.raises(NarrationDraftError, match="draft_ref is stale or inactive"):
            await pin_music_preparation(reader, project, [task])
