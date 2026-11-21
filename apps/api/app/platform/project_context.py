"""Shared helpers for loading project context used by routers and services.

This module centralizes small, repeated patterns that appear across generation,
derivative regeneration, and clip revision:

- fetch a project and verify ownership
- collect asset texts from a project's assets
- resolve a project's persona
- validate a clip for revision
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import PersonaContext
from app.models.tables import Asset, Output, Persona, Project


def persona_context_from_row(persona: Persona | None) -> PersonaContext | None:
    """Build a PersonaContext from a Persona DB row."""
    if persona is None:
        return None
    return PersonaContext.model_validate(persona)


async def lock_project_for_job(db: AsyncSession, project: Project) -> None:
    """Hold the project through admission. A concurrent delete owns the conflicting row lock."""
    project_id = await db.scalar(
        select(Project.id).where(Project.id == project.id, Project.user_id == project.user_id)
        .with_for_update(read=True, key_share=True, skip_locked=True)
    )
    if project_id is None:
        raise ValueError("The project is unavailable for new jobs.")


async def get_project_for_user(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID | None,
) -> Project:
    """Fetch a project and ensure it belongs to the given user.

    Projects are private to their owner — a 404 (not 403) is returned for
    other users' projects so existence doesn't leak.
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
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found",
    )


async def get_output_for_user(
    db: AsyncSession,
    output_id: UUID,
    user_id: UUID | None,
) -> Output:
    """Fetch an output and ensure it belongs to the given user."""
    output = await db.get(Output, output_id)
    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output not found",
        )
    project = await db.get(Project, output.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if user_id is not None and project.user_id == user_id:
        return output
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied",
    )


async def collect_asset_texts(
    db: AsyncSession,
    project_id: UUID,
) -> list[str]:
    """Collect all textual source material for a project.

    Reads the ONE text seat (``asset_text_content``, ADR-113 — transcript
    before extracted_text); empty assets are skipped. The import is deferred:
    pipeline already depends on this module (node_runners / verify), so the
    return edge stays lazy.
    """
    from app.pipeline.assets import asset_text_content

    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    assets = list(result.scalars().all())
    return [text for a in assets if (text := asset_text_content(a))]


async def resolve_persona(
    db: AsyncSession,
    project: Project,
    require_user: bool = False,
) -> Persona | None:
    """Resolve a project's persona.

    Returns ``None`` when the project has no persona. The optional
    ``require_user`` flag adds a ``Persona.user_id`` filter to match the
    stricter lookup used during auto-persona creation.
    """
    if not project.persona_id:
        return None

    query = select(Persona).where(Persona.id == project.persona_id)
    if require_user:
        query = query.where(Persona.user_id == project.user_id)

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def resolve_default_persona(
    db: AsyncSession,
    user_id: UUID,
) -> Persona | None:
    """The user's default persona (ADR-038 §6): a system-bootstrap persona
    (``auto_created_at`` set) outranks plain rows; ties break by earliest
    created."""
    result = await db.execute(
        select(Persona)
        .where(Persona.user_id == user_id)
        .order_by(Persona.auto_created_at.is_(None), Persona.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()
