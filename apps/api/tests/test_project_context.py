"""Tests for project_context helpers."""

import pytest
from fastapi import HTTPException

from app.models.schemas import Segment
from app.models.tables import Asset, AssetType, Clip, Project, Speaker, User
from app.services.project_context import (
    collect_materials,
    get_project_for_user,
    resolve_clip_for_revision,
    resolve_speaker,
)


async def _make_user(db, email="test@example.com"):
    user = User(email=email)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_project(db, user, title="Test Project", speaker_id=None):
    project = Project(user_id=user.id, title=title, speaker_id=speaker_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def _make_speaker(db, user, name="Test Speaker", core_values=None):
    speaker = Speaker(
        user_id=user.id,
        name=name,
        core_values=core_values or [],
    )
    db.add(speaker)
    await db.commit()
    await db.refresh(speaker)
    return speaker


async def test_get_project_for_user_returns_owned_project(db):
    user = await _make_user(db)
    project = await _make_project(db, user)

    result = await get_project_for_user(db, project.id, user.id)
    assert result.id == project.id


async def test_get_project_for_user_raises_404_for_other_user(db):
    user_a = await _make_user(db, email="a@example.com")
    user_b = await _make_user(db, email="b@example.com")
    project = await _make_project(db, user_a)

    with pytest.raises(HTTPException) as exc_info:
        await get_project_for_user(db, project.id, user_b.id)
    assert exc_info.value.status_code == 404


async def test_collect_materials_prefers_extracted_text(db):
    user = await _make_user(db)
    project = await _make_project(db, user)

    asset = Asset(
        user_id=user.id,
        project_id=project.id,
        type=AssetType.TRANSCRIPT,
        extracted_text="extracted",
        transcript="transcript",
    )
    db.add(asset)
    await db.commit()

    materials = await collect_materials(db, project.id)
    assert materials == ["extracted"]


async def test_collect_materials_falls_back_to_transcript(db):
    user = await _make_user(db)
    project = await _make_project(db, user)

    asset = Asset(
        user_id=user.id,
        project_id=project.id,
        type=AssetType.AUDIO,
        transcript="spoken words",
    )
    db.add(asset)
    await db.commit()

    materials = await collect_materials(db, project.id)
    assert materials == ["spoken words"]


async def test_collect_materials_skips_empty_assets(db):
    user = await _make_user(db)
    project = await _make_project(db, user)

    db.add_all(
        [
            Asset(user_id=user.id, project_id=project.id, type=AssetType.IMAGE),
            Asset(
                user_id=user.id,
                project_id=project.id,
                type=AssetType.TRANSCRIPT,
                transcript="keep me",
            ),
        ]
    )
    await db.commit()

    materials = await collect_materials(db, project.id)
    assert materials == ["keep me"]


async def test_resolve_speaker_without_speaker(db):
    user = await _make_user(db)
    project = await _make_project(db, user)

    speaker = await resolve_speaker(db, project)
    assert speaker is None


async def test_resolve_speaker_returns_speaker(db):
    user = await _make_user(db)
    speaker = await _make_speaker(db, user, core_values=["clarity"])
    project = await _make_project(db, user, speaker_id=speaker.id)

    resolved_speaker = await resolve_speaker(db, project)
    assert resolved_speaker is not None
    assert resolved_speaker.id == speaker.id
    assert resolved_speaker.core_values == ["clarity"]


async def test_resolve_speaker_filters_by_user_when_required(db):
    user_a = await _make_user(db, email="a@example.com")
    user_b = await _make_user(db, email="b@example.com")
    speaker = await _make_speaker(db, user_b)
    project = await _make_project(db, user_a, speaker_id=speaker.id)

    speaker_result = await resolve_speaker(db, project, require_user=True)
    assert speaker_result is None


async def test_resolve_clip_for_revision_returns_parsed_data(db):
    user = await _make_user(db)
    project = await _make_project(db, user)
    segment = Segment(
        id="seg-1",
        source_text="hello world",
        start_marker="0",
        end_marker="1",
    ).model_dump()
    clip = Clip(
        project_id=project.id,
        hook="hello",
        source_segment=segment,
    )
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    resolved_clip, source_segment = await resolve_clip_for_revision(
        db, clip.id, project.id
    )
    assert resolved_clip.id == clip.id
    assert source_segment.source_text == "hello world"


async def test_resolve_clip_for_revision_requires_source_segment(db):
    user = await _make_user(db)
    project = await _make_project(db, user)
    clip = Clip(
        project_id=project.id,
        hook="hello",
        source_segment=None,
    )
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    with pytest.raises(ValueError, match="no source segment"):
        await resolve_clip_for_revision(db, clip.id, project.id)


async def test_resolve_clip_for_revision_rejects_wrong_project(db):
    user = await _make_user(db)
    project_a = await _make_project(db, user, title="A")
    project_b = await _make_project(db, user, title="B")
    clip = Clip(
        project_id=project_a.id,
        hook="hello",
        source_segment=Segment(
            id="seg-1", source_text="x", start_marker="0", end_marker="1"
        ).model_dump(),
    )
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    with pytest.raises(ValueError, match="Clip not found"):
        await resolve_clip_for_revision(db, clip.id, project_b.id)
