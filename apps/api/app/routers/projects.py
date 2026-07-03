"""Project router."""

import io
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select

from app.dependencies import DBDep, get_current_user
from app.models.schemas import (
    ClipResponse,
    DerivativeResponse,
    DerivativeType,
    ExportRequest,
    GenerateRequest,
    MessageRole,
    ProjectCreate,
    ProjectResponse,
    ProjectResultsResponse,
    ProjectStatus,
    ProjectUpdate,
    WorkflowRunResponse,
    WorkflowStatus,
)
from app.models.tables import (
    Asset,
    Clip,
    Derivative,
    HumanFeedback,
    Message,
    Project,
    Speaker,
    User,
    WorkflowRun,
)
from app.services.messages import create_assistant_message
from app.services.project_context import get_project_for_user
from app.services.storage import delete_file, delete_project_files

router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Create a new project."""
    if data.speaker_id:
        speaker_result = await db.execute(
            select(Speaker).where(
                Speaker.id == data.speaker_id,
                Speaker.user_id == current_user.id,
            )
        )
        speaker = speaker_result.scalar_one_or_none()
        if not speaker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Speaker not found",
            )

    project = Project(**data.model_dump(), user_id=current_user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: DBDep,
    current_user: User = Depends(get_current_user),
    speaker_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Project]:
    """List projects for the current user."""
    query = select(Project).where(Project.user_id == current_user.id)
    if speaker_id:
        query = query.where(Project.speaker_id == speaker_id)
    query = (
        query.order_by(Project.updated_at.desc().nulls_last())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Get project by ID."""
    return await get_project_for_user(db, project_id, current_user.id)


@router.get("/{project_id}/results", response_model=ProjectResultsResponse)
async def get_project_results(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Aggregate project results: metadata, prompt, clips, derivatives, latest job."""
    project = await get_project_for_user(db, project_id, current_user.id)

    # Latest user message content as the original prompt.
    prompt_result = await db.execute(
        select(Message)
        .where(Message.project_id == project_id, Message.role == MessageRole.USER)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    latest_user_message = prompt_result.scalar_one_or_none()
    prompt = latest_user_message.content if latest_user_message else None

    clips_result = await db.execute(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.created_at.desc())
    )
    clips = list(clips_result.scalars().all())

    derivatives_result = await db.execute(
        select(Derivative)
        .where(Derivative.project_id == project_id)
        .order_by(Derivative.created_at.desc())
    )
    derivatives = list(derivatives_result.scalars().all())

    latest_job_result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(1)
    )
    latest_job = latest_job_result.scalar_one_or_none()

    return {
        "project": project,
        "prompt": prompt,
        "clips": clips,
        "derivatives": derivatives,
        "latest_job": latest_job,
    }


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Update project."""
    project = await get_project_for_user(db, project_id, current_user.id)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete project and all associated assets."""
    project = await get_project_for_user(db, project_id, current_user.id)

    # Delete child rows in FK-safe order, then the project. Asset files are
    # unlinked individually since we need each file_url before deletion.
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    for asset in result.scalars().all():
        delete_file(asset.file_url)

    clip_ids = select(Clip.id).where(Clip.project_id == project_id)
    await db.execute(delete(HumanFeedback).where(HumanFeedback.clip_id.in_(clip_ids)))
    await db.execute(delete(Clip).where(Clip.project_id == project_id))
    await db.execute(delete(Derivative).where(Derivative.project_id == project_id))
    await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(delete(Asset).where(Asset.project_id == project_id))
    await db.delete(project)
    await db.commit()

    # Remove project upload directory after DB commit
    delete_project_files(project_id, current_user.id)


@router.post("/{project_id}/generate", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def generate_content(
    project_id: UUID,
    request: GenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Queue background generation for a project.

    Creates a PENDING WorkflowRun and a matching assistant chat message, then
    returns immediately with a job id to poll; the background worker claims and
    runs it (see app.worker).
    """
    project = await get_project_for_user(db, project_id, current_user.id)

    assistant_message = await create_assistant_message(
        db,
        project_id,
        params={
            "outputs": request.outputs,
            "clip_count": request.clip_count,
            "target_language": request.target_language,
            "instruction": request.instruction,
            "scope": request.scope,
            "target_id": str(request.target_id) if request.target_id else None,
            "operation": request.operation,
        },
    )

    run = WorkflowRun(
        project_id=project_id,
        status=WorkflowStatus.PENDING,
        current_step="queued",
        progress=0,
        context={
            "outputs": request.outputs,
            "clip_count": request.clip_count,
            "tone_settings": (
                request.tone_settings.model_dump() if request.tone_settings else None
            ),
            "target_language": request.target_language,
            "brand_template_id": (
                str(request.brand_template_id) if request.brand_template_id else None
            ),
            "instruction": request.instruction,
            "scope": request.scope,
            "target_id": str(request.target_id) if request.target_id else None,
            "operation": request.operation,
            "assistant_message_id": str(assistant_message.id),
        },
    )
    db.add(run)
    project.status = ProjectStatus.PROCESSING
    await db.commit()
    await db.refresh(run)

    return {
        "job_id": str(run.id),
        "status": run.status.value,
        "message_id": str(assistant_message.id),
    }


@router.get("/{project_id}/jobs", response_model=list[WorkflowRunResponse])
async def list_project_jobs(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> list[WorkflowRun]:
    """List generation jobs for a project, newest first."""
    await get_project_for_user(db, project_id, current_user.id)
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/jobs/{job_id}", response_model=WorkflowRunResponse)
async def get_project_job(
    project_id: UUID,
    job_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> WorkflowRun:
    """Get a single generation job's status."""
    await get_project_for_user(db, project_id, current_user.id)
    run = await db.get(WorkflowRun, job_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return run


@router.get("/{project_id}/clips", response_model=list[ClipResponse])
async def list_project_clips(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> list[Clip]:
    """List generated clips for a project."""
    await get_project_for_user(db, project_id, current_user.id)

    result = await db.execute(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/derivatives", response_model=list[DerivativeResponse])
async def list_project_derivatives(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> list[Derivative]:
    """List generated derivatives (LinkedIn posts, quote cards) for a project."""
    await get_project_for_user(db, project_id, current_user.id)
    result = await db.execute(
        select(Derivative)
        .where(Derivative.project_id == project_id)
        .order_by(Derivative.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{project_id}/export")
async def export_project(
    project_id: UUID,
    request: ExportRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export all generated content for a project as a zip archive."""
    project = await get_project_for_user(db, project_id, current_user.id)

    clips_result = await db.execute(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.created_at.desc())
    )
    clips = list(clips_result.scalars().all())

    derivatives_result = await db.execute(
        select(Derivative)
        .where(Derivative.project_id == project_id)
        .order_by(Derivative.created_at.desc())
    )
    derivatives = list(derivatives_result.scalars().all())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Clips
        if clips:
            lines: list[str] = [f"# Clips for {project.title}\n"]
            for idx, clip in enumerate(clips, start=1):
                script = clip.script
                lines.append(f"\n## Clip {idx}: {clip.hook}\n")
                lines.append(f"- Duration: {clip.duration}s\n")
                lines.append(f"- Mood: {clip.music_mood}\n")
                lines.append(f"- Title options: {', '.join(clip.title_options or [])}\n")
                lines.append("\n### Script\n")
                for shot in script.get("shots", []):
                    lines.append(f"**{shot.get('time_range', '')}** — {shot.get('mood', '')}\n")
                    lines.append(f"> {shot.get('subtitle', '')}\n\n")
                    lines.append(f"Visual: {shot.get('visual', '')}\n\n")
            zf.writestr("clips.md", "".join(lines))

        # Derivatives grouped by type
        linkedin = [d for d in derivatives if d.type == DerivativeType.LINKEDIN_POST]
        if linkedin:
            lines = [f"# LinkedIn Posts for {project.title}\n"]
            for d in linkedin:
                content = d.content
                lines.append(f"\n---\n\n{content.get('content', '')}\n")
                hashtags = content.get("hashtags", [])
                if hashtags:
                    lines.append("\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags) + "\n")
            zf.writestr("linkedin.md", "".join(lines))

        quote_cards = [d for d in derivatives if d.type == DerivativeType.QUOTE_CARD]
        if quote_cards:
            lines = [f"# Quote Cards for {project.title}\n"]
            for d in quote_cards:
                for q in d.content.get("quotes", []):
                    lines.append(f"\n> \"{q.get('quote', '')}\"\n")
                    lines.append(f"> — {q.get('attribution', '')}\n")
            zf.writestr("quote-cards.md", "".join(lines))

        summaries = [d for d in derivatives if d.type == DerivativeType.SUMMARY]
        if summaries:
            lines = [f"# Summaries for {project.title}\n"]
            for d in summaries:
                content = d.content
                if content.get("tldr"):
                    lines.append(f"\n## TL;DR\n\n{content['tldr']}\n")
                if content.get("key_points"):
                    lines.append("\n### Key Points\n")
                    for p in content["key_points"]:
                        lines.append(f"- {p}\n")
                if content.get("full"):
                    lines.append(f"\n### Full Summary\n\n{content['full']}\n")
            zf.writestr("summary.md", "".join(lines))

        blogs = [d for d in derivatives if d.type == DerivativeType.BLOG]
        if blogs:
            lines = [f"# Blog Posts for {project.title}\n"]
            for d in blogs:
                content = d.content
                if content.get("title"):
                    lines.append(f"\n## {content['title']}\n")
                lines.append(f"\n{content.get('content', '')}\n")
            zf.writestr("blog.md", "".join(lines))

    buffer.seek(0)
    filename = f"{project.title.replace(' ', '_').lower() or 'export'}.zip"
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
