"""Project router."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DBDep
from app.models.schemas import (
    ProjectCreate,
    ProjectResponse,
    ProjectStatus,
    ProjectUpdate,
)
from app.models.tables import Asset, Project
from app.services.storage import delete_file, delete_project_files

router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, db: DBDep) -> Project:
    """Create a new project."""
    project = Project(**data.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: DBDep,
    speaker_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Project]:
    """List projects."""
    query = select(Project)
    if speaker_id:
        query = query.where(Project.speaker_id == speaker_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, db: DBDep) -> Project:
    """Get project by ID."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: UUID, data: ProjectUpdate, db: DBDep) -> Project:
    """Update project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, db: DBDep) -> None:
    """Delete project and all associated assets."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Delete associated assets (files + DB rows)
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    assets = list(result.scalars().all())
    for asset in assets:
        delete_file(asset.file_url)
        await db.delete(asset)

    await db.delete(project)
    await db.commit()

    # Remove project upload directory after DB commit
    delete_project_files(project_id)


@router.post("/{project_id}/generate", response_model=dict)
async def generate_content(project_id: UUID, db: DBDep) -> dict:
    """Start content generation for a project.

    TODO: Implement actual generation workflow.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    project.status = ProjectStatus.PROCESSING
    await db.commit()

    return {
        "run_id": "placeholder-run-id",
        "status": "running",
        "message": "Generation started (placeholder)",
    }
