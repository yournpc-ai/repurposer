"""Project router."""

import io
import zipfile
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from sqlalchemy import select

from app.agents.blog import blog_agent
from app.agents.linkedin import linkedin_agent
from app.agents.quote_card import quote_card_agent
from app.agents.summary import summary_agent
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep
from app.models.schemas import (
    AssetType,
    BlogPost,
    ClipResponse,
    DerivativeResponse,
    DerivativeType,
    ExportRequest,
    GenerateRequest,
    LinkedInPost,
    ProjectCreate,
    ProjectResponse,
    ProjectStatus,
    ProjectUpdate,
    QuoteCardsResponse,
    SpeakerPersona,
    Summary,
    WorkflowRunResponse,
    WorkflowStatus,
)
from app.models.tables import (
    Asset,
    Clip,
    Derivative,
    Project,
    Speaker,
    WorkflowRun,
)
from app.services.extraction import extract_text
from app.services.generation import run_generation
from app.services.storage import delete_file, delete_project_files

router = APIRouter()


async def _extract_project_materials(project_id: UUID, db: DBDep) -> list[str]:
    """Extract text from all analyzable project assets.

    Returns a list of non-empty extracted texts. Raises HTTPException
    if no usable text is found.
    """
    result = await db.execute(
        select(Asset).where(
            Asset.project_id == project_id,
            Asset.type.in_(
                [
                    AssetType.TRANSCRIPT,
                    AssetType.VIDEO,
                    AssetType.AUDIO,
                    AssetType.SLIDES,
                ]
            ),
        )
    )
    assets = list(result.scalars().all())
    if not assets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No analyzable assets found for this project",
        )

    materials: list[str] = []
    for asset in assets:
        if not asset.extracted_text and asset.file_url:
            asset.extracted_text = extract_text(asset.file_url)
            asset.processed_at = datetime.now(UTC)
            db.add(asset)
        if asset.extracted_text:
            materials.append(asset.extracted_text)

    if not materials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract text from any project asset",
        )

    await db.commit()
    return materials


async def _load_project_and_speaker(
    project_id: UUID, db: DBDep
) -> tuple[Project, Speaker | None]:
    """Load a project with its associated speaker (optional)."""
    result = await db.execute(
        select(Project, Speaker)
        .outerjoin(Speaker, Project.speaker_id == Speaker.id)
        .where(Project.id == project_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return row._tuple()  # type: ignore[attr-defined]


def _parse_persona(speaker: Speaker) -> SpeakerPersona | None:
    """Parse speaker persona from JSON if present."""
    if speaker.persona:
        return SpeakerPersona.model_validate(speaker.persona)
    return None


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, db: DBDep) -> Project:
    """Create a new project."""
    if data.speaker_id:
        speaker_result = await db.execute(select(Speaker).where(Speaker.id == data.speaker_id))
        speaker = speaker_result.scalar_one_or_none()
        if not speaker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Speaker not found",
            )

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


@router.post("/{project_id}/generate", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def generate_content(
    project_id: UUID,
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: DBDep,
) -> dict:
    """Queue background generation for a project.

    Creates a WorkflowRun, dispatches the orchestration to a background task,
    and returns immediately with a job id to poll.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
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
        },
    )
    db.add(run)
    project.status = ProjectStatus.PROCESSING
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(run_generation, run.id)

    return {"job_id": str(run.id), "status": run.status.value}


@router.get("/{project_id}/jobs", response_model=list[WorkflowRunResponse])
async def list_project_jobs(project_id: UUID, db: DBDep) -> list[WorkflowRun]:
    """List generation jobs for a project, newest first."""
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/jobs/{job_id}", response_model=WorkflowRunResponse)
async def get_project_job(project_id: UUID, job_id: UUID, db: DBDep) -> WorkflowRun:
    """Get a single generation job's status."""
    run = await db.get(WorkflowRun, job_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return run


@router.get("/{project_id}/clips", response_model=list[ClipResponse])
async def list_project_clips(project_id: UUID, db: DBDep) -> list[Clip]:
    """List generated clips for a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    result = await db.execute(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/derivatives", response_model=list[DerivativeResponse])
async def list_project_derivatives(project_id: UUID, db: DBDep) -> list[Derivative]:
    """List generated derivatives (LinkedIn posts, quote cards) for a project."""
    result = await db.execute(
        select(Derivative)
        .where(Derivative.project_id == project_id)
        .order_by(Derivative.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{project_id}/linkedin", response_model=LinkedInPost)
async def generate_linkedin_post(
    project_id: UUID, request: GenerateRequest, db: DBDep
) -> LinkedInPost:
    """Generate a LinkedIn post for a project."""
    project, speaker = await _load_project_and_speaker(project_id, db)
    materials = await _extract_project_materials(project_id, db)
    persona = _parse_persona(speaker) if speaker else None

    try:
        post = await linkedin_agent.generate(
            materials=materials,
            persona=persona,
            event_name=project.event_name,
            target_language=request.target_language,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    derivative = Derivative(
        project_id=project_id,
        type=DerivativeType.LINKEDIN_POST,
        content=post.model_dump(),
        language=project.language,
    )
    db.add(derivative)
    await db.commit()
    await db.refresh(derivative)

    return post


@router.post("/{project_id}/quote-cards", response_model=QuoteCardsResponse)
async def generate_quote_cards(
    project_id: UUID,
    request: GenerateRequest,
    count: int = 3,
    db: DBDep = None,  # type: ignore[assignment]
) -> QuoteCardsResponse:
    """Generate quote cards for a project."""
    project, speaker = await _load_project_and_speaker(project_id, db)
    materials = await _extract_project_materials(project_id, db)

    try:
        result = await quote_card_agent.generate(
            materials=materials,
            speaker_name=speaker.name,
            speaker_title=speaker.title,
            event_name=project.event_name,
            count=count,
            target_language=request.target_language,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    derivative = Derivative(
        project_id=project_id,
        type=DerivativeType.QUOTE_CARD,
        content=result.model_dump(),
        language=project.language,
    )
    db.add(derivative)
    await db.commit()
    await db.refresh(derivative)

    return result


@router.post("/{project_id}/summary", response_model=Summary)
async def generate_summary(
    project_id: UUID, request: GenerateRequest, db: DBDep
) -> Summary:
    """Generate a multi-language summary for a project."""
    project, speaker = await _load_project_and_speaker(project_id, db)
    materials = await _extract_project_materials(project_id, db)
    persona = _parse_persona(speaker) if speaker else None

    try:
        result = await summary_agent.generate(
            materials=materials,
            persona=persona,
            event_name=project.event_name,
            target_language=request.target_language,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    derivative = Derivative(
        project_id=project_id,
        type=DerivativeType.SUMMARY,
        content=result.model_dump(),
        language=request.target_language,
    )
    db.add(derivative)
    await db.commit()
    await db.refresh(derivative)

    return result


@router.post("/{project_id}/blog", response_model=BlogPost)
async def generate_blog(
    project_id: UUID, request: GenerateRequest, db: DBDep
) -> BlogPost:
    """Generate a blog post for a project."""
    project, speaker = await _load_project_and_speaker(project_id, db)
    materials = await _extract_project_materials(project_id, db)
    persona = _parse_persona(speaker) if speaker else None

    try:
        result = await blog_agent.generate(
            materials=materials,
            persona=persona,
            event_name=project.event_name,
            target_language=request.target_language,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    derivative = Derivative(
        project_id=project_id,
        type=DerivativeType.BLOG,
        content=result.model_dump(),
        language=request.target_language,
    )
    db.add(derivative)
    await db.commit()
    await db.refresh(derivative)

    return result


@router.post("/{project_id}/export")
async def export_project(
    project_id: UUID,
    request: ExportRequest,
    db: DBDep,
) -> Response:
    """Export all generated content for a project as a zip archive."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

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
