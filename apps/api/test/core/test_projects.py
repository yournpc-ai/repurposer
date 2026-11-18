from uuid import uuid4

import pytest

from app.models.tables import Conversation, Message, Output, Project, User
from app.pipeline.routes.projects import list_projects

pytestmark = pytest.mark.asyncio


async def test_project_list_accepts_fractional_output_duration(database):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Fractional duration")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        db.add(Message(conversation_id=conversation.id, role="user", content="Make a video", seq=1))
        db.add(Output(
            project_id=project.id,
            type="video",
            files={"video": "clip.mp4"},
            payload={"duration": 23.433333333333334},
            render_spec={"aspect": "16:9"},
        ))
        await db.commit()

        rows = await list_projects(db=db, current_user=user)

    assert len(rows) == 1
    assert rows[0].id == project.id
    assert rows[0].thumbnail_duration == 23
    assert rows[0].thumbnail_aspect == "16:9"
