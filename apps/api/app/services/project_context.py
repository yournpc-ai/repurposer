"""Shared helpers for loading project context used by routers and services.

This module centralizes small, repeated patterns that appear across generation,
derivative regeneration, and clip revision:

- fetch a project and verify ownership
- collect asset texts from a project's assets
- resolve a project's speaker
- validate a clip for revision
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import Segment, SpeakerContext
from app.models.tables import Asset, Clip, Project, Speaker


def speaker_context_from_row(speaker: Speaker | None) -> SpeakerContext | None:
    """Build a SpeakerContext from a Speaker DB row."""
    if speaker is None:
        return None
    return SpeakerContext.model_validate(speaker)


async def get_project_for_user(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
) -> Project:
    """Fetch a project and ensure it belongs to the given user."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


async def collect_asset_texts(
    db: AsyncSession,
    project_id: UUID,
) -> list[str]:
    """Collect all textual source material for a project.

    Prefers ``extracted_text`` (documents) and falls back to ``transcript``
    (audio/video ASR). Empty assets are skipped.
    """
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    assets = list(result.scalars().all())
    return [
        text
        for a in assets
        if (text := (a.extracted_text or a.transcript))
    ]


async def resolve_speaker(
    db: AsyncSession,
    project: Project,
    require_user: bool = False,
) -> Speaker | None:
    """Resolve a project's speaker.

    Returns ``None`` when the project has no speaker. The optional
    ``require_user`` flag adds a ``Speaker.user_id`` filter to match the
    stricter lookup used during auto-speaker creation.
    """
    if not project.speaker_id:
        return None

    query = select(Speaker).where(Speaker.id == project.speaker_id)
    if require_user:
        query = query.where(Speaker.user_id == project.user_id)

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def resolve_clip_for_revision(
    db: AsyncSession,
    clip_id: UUID,
    project_id: UUID,
) -> tuple[Clip, Segment]:
    """Load and validate a clip for revision.

    Returns the clip and its source segment. Raises ``ValueError`` if the clip
    is missing, belongs to another project, or has no source segment.

    Callers in routers should convert the ``ValueError`` to an HTTPException.
    """
    clip = await db.get(Clip, clip_id)
    if clip is None or clip.project_id != project_id:
        raise ValueError("Clip not found")

    if not clip.source_segment:
        raise ValueError("Clip has no source segment to revise from")

    try:
        source_segment = Segment.model_validate(clip.source_segment)
    except Exception as e:
        raise ValueError(f"Invalid clip data: {e}") from e

    return clip, source_segment
