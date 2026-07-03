"""Tests for new MVP router functions (called directly with a DB session)."""

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.models.schemas import (
    AssetStatus,
    AssetType,
    DerivativeType,
    MessageRole,
    ProjectStatus,
)
from app.models.tables import Asset, Clip, Derivative, Message, Project, User
from app.routers.clips import regenerate_clip
from app.routers.derivatives import regenerate_derivative
from app.routers.library import list_library
from app.routers.projects import get_project_results


@pytest.fixture
async def auth_user(db):
    """Create and return a test user."""
    user = User(
        id=uuid4(),
        email="test@repurposer.local",
        name="Test User",
    )
    db.add(user)
    await db.commit()
    return user


async def test_get_project_results(db, auth_user):
    project = Project(
        user_id=auth_user.id,
        title="Test Results",
        language="en",
        status=ProjectStatus.COMPLETED,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    user_message = Message(
        project_id=project.id,
        role=MessageRole.USER,
        content="Generate clips and LinkedIn posts",
    )
    db.add(user_message)

    clip = Clip(
        project_id=project.id,
        hook="Test hook",
        script={"hook": "Test hook", "duration_seconds": 30, "shots": []},
        title_options=["Title"],
        music_mood="calm",
        duration=30,
        language="en",
    )
    derivative = Derivative(
        project_id=project.id,
        type=DerivativeType.LINKEDIN_POST,
        content={"content": "Hello LinkedIn", "hashtags": []},
        language="en",
    )
    db.add_all([clip, derivative])
    await db.commit()

    result = await get_project_results(project.id, db, auth_user)
    assert result["project"].id == project.id
    assert result["prompt"] == "Generate clips and LinkedIn posts"
    assert len(result["clips"]) == 1
    assert len(result["derivatives"]) == 1
    assert result["latest_job"] is None


async def test_get_project_results_rejects_other_user(db, auth_user):
    other_user = User(email="other@example.com")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    project = Project(
        user_id=other_user.id,
        title="Other User Project",
        language="en",
    )
    db.add(project)
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_project_results(project.id, db, auth_user)
    assert exc_info.value.status_code == 404


async def test_list_library(db, auth_user):
    project = Project(
        user_id=auth_user.id,
        title="Library Test",
        language="en",
        status=ProjectStatus.COMPLETED,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    asset = Asset(
        user_id=auth_user.id,
        project_id=project.id,
        type=AssetType.VIDEO,
        file_url=f"{auth_user.id}/uploads/projects/{project.id}/talk.mp4",
        processing_status=AssetStatus.COMPLETED,
    )
    clip = Clip(
        project_id=project.id,
        hook="Library clip",
        script={"hook": "Library clip", "duration_seconds": 30, "shots": []},
        title_options=["Title"],
        music_mood="calm",
        duration=30,
        language="en",
    )
    derivative = Derivative(
        project_id=project.id,
        type=DerivativeType.SUMMARY,
        content={"tldr": "TL;DR", "key_points": []},
        language="en",
    )
    db.add_all([asset, clip, derivative])
    await db.commit()

    items = await list_library(None, db, auth_user)
    assert len(items) == 3

    clip_items = await list_library("clip", db, auth_user)  # type: ignore[arg-type]
    assert len(clip_items) == 1
    assert clip_items[0].type == "clip"


async def test_regenerate_clip(db, auth_user):
    project = Project(
        user_id=auth_user.id,
        title="Regenerate Test",
        language="en",
        status=ProjectStatus.COMPLETED,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    clip = Clip(
        project_id=project.id,
        hook="Hook",
        script={"hook": "Hook", "duration_seconds": 30, "shots": []},
        title_options=["Title"],
        music_mood="calm",
        duration=30,
        language="en",
    )
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    result = await regenerate_clip(
        clip.id,
        type("RegenerateRequest", (), {"instruction": "Make it shorter"})(),
        db,
        auth_user,
    )
    assert "job_id" in result
    assert "message_id" in result


async def test_regenerate_clip_rejects_other_user(db, auth_user):
    other_user = User(email="other@example.com")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    project = Project(
        user_id=other_user.id,
        title="Other Project",
        language="en",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    clip = Clip(
        project_id=project.id,
        hook="Hook",
        script={"hook": "Hook", "duration_seconds": 30, "shots": []},
        title_options=["Title"],
        music_mood="calm",
        duration=30,
        language="en",
    )
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    with pytest.raises(HTTPException) as exc_info:
        await regenerate_clip(
            clip.id,
            type("RegenerateRequest", (), {"instruction": ""})(),
            db,
            auth_user,
        )
    assert exc_info.value.status_code == 403


async def test_regenerate_derivative_rejects_other_user(db, auth_user):
    other_user = User(email="other@example.com")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    project = Project(
        user_id=other_user.id,
        title="Other Project",
        language="en",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    derivative = Derivative(
        project_id=project.id,
        type=DerivativeType.LINKEDIN_POST,
        content={"content": "Hello", "hashtags": []},
        language="en",
    )
    db.add(derivative)
    await db.commit()
    await db.refresh(derivative)

    with pytest.raises(HTTPException) as exc_info:
        await regenerate_derivative(
            derivative.id,
            type("DerivativeRegenerateRequest", (), {"instruction": ""})(),
            db,
            auth_user,
        )
    assert exc_info.value.status_code == 403
