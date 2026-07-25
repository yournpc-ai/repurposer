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
from app.models.tables import Asset, Output, Project, Speaker

DEMO_PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")


def speaker_context_from_row(speaker: Speaker | None) -> SpeakerContext | None:
    """Build a SpeakerContext from a Speaker DB row."""
    if speaker is None:
        return None
    return SpeakerContext.model_validate(speaker)


async def get_project_for_user(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID | None,
    allow_demo: bool = True,
) -> Project:
    """Fetch a project and ensure it belongs to the given user.

    The seeded demo project is readable by every user (``allow_demo=True``);
    anonymous users can only access the demo project. Write operations should
    pass ``allow_demo=False`` so the demo stays intact.
    """
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if user_id is not None and project.user_id == user_id:
        return project
    if allow_demo and project.id == DEMO_PROJECT_ID:
        return project
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found",
    )


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
) -> tuple[Output, Segment]:
    """Load and validate a clip output for revision.

    Returns the output and its source segment. Raises ``ValueError`` if the
    output is missing, belongs to another project, is not a clip, or has no
    source segment.

    Callers in routers should convert the ``ValueError`` to an HTTPException.
    """
    output = await db.get(Output, clip_id)
    if output is None or output.project_id != project_id or output.type != "clip":
        raise ValueError("Clip not found")

    segment_data = (output.source_ref or {}).get("segment")
    if not segment_data:
        raise ValueError("Clip has no source segment to revise from")

    try:
        source_segment = Segment.model_validate(segment_data)
    except Exception as e:
        raise ValueError(f"Invalid clip data: {e}") from e

    return output, source_segment
