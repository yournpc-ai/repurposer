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

from app.models.schemas import Segment, PersonaContext
from app.models.tables import Asset, Output, Persona, Project, WorkflowRun


def persona_context_from_row(persona: Persona | None) -> PersonaContext | None:
    """Build a PersonaContext from a Persona DB row."""
    if persona is None:
        return None
    return PersonaContext.model_validate(persona)


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


async def resolve_run_persona(
    db: AsyncSession,
    run: WorkflowRun,
    project: Project,
) -> Persona | None:
    """The persona a run generates with: the run-pinned choice
    (``run.context.persona_id``, written at task-book confirmation) → the
    project mount → the user's default persona. A historical run context's
    ``brand_template_id`` key is ignored on read — re-runs fall back to the
    persona skin.
    """
    pinned = (run.context or {}).get("persona_id")
    if pinned:
        try:
            result = await db.execute(
                select(Persona).where(
                    Persona.id == UUID(str(pinned)),
                    Persona.user_id == project.user_id,
                )
            )
            persona = result.scalar_one_or_none()
        except (ValueError, TypeError):
            persona = None
        if persona is not None:
            return persona
    if project.persona_id:
        persona = await resolve_persona(db, project)
        if persona is not None:
            return persona
    return await resolve_default_persona(db, UUID(str(project.user_id)))


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
