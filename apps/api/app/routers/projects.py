"""Project router."""

import io
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetType,
    ClipResponse,
    DerivativeResponse,
    DerivativeType,
    ExportRequest,
    GenerateRequest,
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
    Project,
    Speaker,
    User,
    WorkflowRun,
)
from app.services.chat import get_project_prompt, seed_project_prompt
from app.services.demo_seed import DEMO_PROJECT_ID
from app.services.project_context import get_project_for_user
from app.services.storage import delete_file, delete_project_files, resolve_stored_url

router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
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
    current_user: User | None = Depends(get_current_user),
    speaker_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[ProjectResponse]:
    """List projects for the current user, with a representative clip thumbnail.

    Left-joins each project to its earliest rendered clip (by created_at) so
    the home page can show a real video thumbnail + duration/aspect badge
    without a second round trip per card.
    """
    thumb = (
        select(
            Clip.project_id.label("project_id"),
            Clip.video_url.label("video_url"),
            Clip.duration.label("duration"),
            Clip.render_spec.label("render_spec"),
        )
        .distinct(Clip.project_id)
        .where(Clip.video_url.isnot(None))
        .order_by(Clip.project_id, Clip.created_at.asc())
        .subquery()
    )
    # Anonymous users see only the demo project. Authenticated users see their
    # own projects plus the demo project (the demo is owned by the shared
    # default user; nothing else of the default user leaks into anyone's list).
    if current_user:
        ownership_filter = (Project.user_id == current_user.id) | (
            Project.id == DEMO_PROJECT_ID
        )
    else:
        ownership_filter = Project.id == DEMO_PROJECT_ID
    query = (
        select(Project, thumb.c.video_url, thumb.c.duration, thumb.c.render_spec)
        .outerjoin(thumb, thumb.c.project_id == Project.id)
        .where(ownership_filter)
    )
    if speaker_id:
        query = query.where(Project.speaker_id == speaker_id)
    query = (
        query.order_by(Project.updated_at.desc().nulls_last())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()

    # Demo project is an onboarding aid; hide it once the user has created real
    # projects so the home page only shows their own work.
    has_real_project = current_user is not None and any(
        project.id != DEMO_PROJECT_ID and project.user_id == current_user.id
        for project, *_ in rows
    )

    responses = []
    for project, video_url, duration, render_spec in rows:
        if has_real_project and project.id == DEMO_PROJECT_ID:
            continue
        resp = ProjectResponse.model_validate(project)
        resp.is_demo = project.id == DEMO_PROJECT_ID
        resp.thumbnail_url = resolve_stored_url(video_url)
        resp.thumbnail_duration = duration
        resp.thumbnail_aspect = (render_spec or {}).get("aspect")
        responses.append(resp)
    return responses


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> ProjectResponse:
    """Get project by ID."""
    project = await get_project_for_user(db, project_id, current_user.id if current_user else None)
    resp = ProjectResponse.model_validate(project)
    resp.is_demo = project.id == DEMO_PROJECT_ID
    return resp


# Stepper prefix phases (asset processing → planning) always exist; output
# phases are included only when the run requested them.
_UI_STEP_BASE = ["transcribing", "queued", "analyze", "plan", "prepare"]
_UI_STEP_TEXT_OUTPUTS = {"post", "quotes", "article", "carousel"}


def _ui_steps_for_outputs(outputs: list[str]) -> list[str]:
    steps = list(_UI_STEP_BASE)
    if "clips" in outputs:
        steps += ["selecting_segments", "building_specs"]
    if any(o in _UI_STEP_TEXT_OUTPUTS for o in outputs):
        steps.append("writing_copy")
    if "quotes" in outputs:
        steps.append("generating_image")
    if "clips" in outputs:
        steps.append("ready_to_render")
    return steps


def _compute_ui_step(
    assets: list[Asset],
    latest_job: WorkflowRun | None,
    clips: list[Clip],
) -> dict | None:
    """Stepper position for the results-page loading dialog.

    The stepper is a numbered list derived from the pipeline itself, so the
    frontend only renders {key, index, total} (percent = (index + 1) / total)
    — every step advances by the same increment, and the final step
    (ready_to_render) sits at 100% while clips wait for the render worker.
    None = hide the dialog (no run, run failed, or everything settled).
    """
    if latest_job is None or latest_job.status == "failed":
        return None

    ctx = latest_job.context or {}
    outputs = ctx.get("outputs") or ["clips"]
    steps = _ui_steps_for_outputs(outputs)

    def at(key: str) -> dict:
        return {"key": key, "index": steps.index(key), "total": len(steps)}

    # Assets still processing (ASR / extraction) — the run queues behind them.
    if any(a.processing_status in ("pending", "processing") for a in assets):
        return at("transcribing")

    if latest_job.status == "pending":
        return at("queued")

    step = latest_job.current_step
    if step in ("analyze", "plan", "prepare"):
        return at(step)

    if step == "clips":
        stage = (ctx.get("output_status") or {}).get("clips", {}).get("stage")
        return at(stage if stage in steps else "selecting_segments")

    # Text derivatives run concurrently, so they share one step; quotes' image
    # rendering is the last sub-stage.
    if step in _UI_STEP_TEXT_OUTPUTS:
        quotes_stage = (ctx.get("output_status") or {}).get("quotes", {}).get("stage")
        if quotes_stage == "generating_image" and "generating_image" in steps:
            return at("generating_image")
        return at("writing_copy")

    if step == "done" or latest_job.status == "completed":
        if "ready_to_render" in steps and any(
            c.render_status in ("pending", "rendering") for c in clips
        ):
            return at("ready_to_render")
        return None

    # Unknown step label: stay at the end of planning.
    return at("prepare")


@router.get("/{project_id}/results", response_model=ProjectResultsResponse)
async def get_project_results(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> dict:
    """Aggregate project results: metadata, prompt, clips, derivatives, latest job."""
    project = await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )

    # The original prompt is the first user message in the project-scoped chat session.
    prompt = await get_project_prompt(db, project_id)

    latest_job_result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(1)
    )
    latest_job = latest_job_result.scalar_one_or_none()

    # Filter clips/derivatives to the latest workflow run. Rows with a NULL
    # workflow_run_id are legacy data from before this column existed; include
    # them so existing projects don't appear empty immediately after the
    # migration.
    latest_job_id = latest_job.id if latest_job is not None else None
    clips_filter = Clip.project_id == project_id
    derivatives_filter = Derivative.project_id == project_id
    if latest_job_id is not None:
        clips_filter = clips_filter & (
            (Clip.workflow_run_id == latest_job_id) | Clip.workflow_run_id.is_(None)
        )
        derivatives_filter = derivatives_filter & (
            (Derivative.workflow_run_id == latest_job_id)
            | Derivative.workflow_run_id.is_(None)
        )

    clips_result = await db.execute(
        select(Clip).where(clips_filter).order_by(Clip.created_at.desc())
    )
    clips = list(clips_result.scalars().all())

    derivatives_result = await db.execute(
        select(Derivative)
        .where(derivatives_filter)
        .order_by(Derivative.created_at.desc())
    )
    derivatives = list(derivatives_result.scalars().all())

    # Asset processing statuses power the results-page loading state (the
    # transcribing/parsing phase before the generation run starts).
    assets_result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)
    )
    assets = list(assets_result.scalars().all())

    return {
        "project": project,
        "prompt": prompt,
        "clips": clips,
        "derivatives": derivatives,
        "latest_job": latest_job,
        "assets": assets,
        "ui_step": _compute_ui_step(assets, latest_job, clips),
    }


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Project:
    """Update project."""
    project = await get_project_for_user(
        db, project_id, current_user.id, allow_demo=False
    )

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
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete project and all associated assets."""
    project = await get_project_for_user(
        db, project_id, current_user.id, allow_demo=False
    )

    # Delete child rows in FK-safe order, then the project. Asset files are
    # unlinked individually since we need each file_url before deletion.
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    for asset in result.scalars().all():
        await delete_file(asset.file_url)

    await db.execute(delete(Clip).where(Clip.project_id == project_id))
    await db.execute(delete(Derivative).where(Derivative.project_id == project_id))
    await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(delete(Asset).where(Asset.project_id == project_id))
    await db.delete(project)
    await db.commit()

    # Remove project upload directory after DB commit
    await delete_project_files(project_id, current_user.id)


@router.post("/{project_id}/generate", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def generate_content(
    project_id: UUID,
    request: GenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Queue background generation for a project.

    Ensures the project-scoped chat session exists so the original prompt is
    persisted, then creates a PENDING WorkflowRun. The background worker claims
    and runs it (see app.worker).
    """
    project = await get_project_for_user(
        db, project_id, UUID(str(current_user.id)), allow_demo=False
    )

    # Clips need a renderable media source (video / audio / image / slides).
    # Reject early instead of letting the run produce unrenderable clips.
    if "clips" in request.outputs and request.scope == "full":
        media_result = await db.execute(
            select(Asset.id)
            .where(
                Asset.project_id == project_id,
                Asset.type.in_(
                    [
                        AssetType.VIDEO,
                        AssetType.AUDIO,
                        AssetType.IMAGE,
                        AssetType.SLIDES,
                    ]
                ),
                Asset.file_url.isnot(None),
            )
            .limit(1)
        )
        if media_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Clips need a video, audio, or image source. "
                    "Upload one or deselect clips."
                ),
            )

    # Persist the original prompt in the project-scoped chat session if it is
    # not already there. This is a no-op when the session already has messages.
    prompt_text = request.instruction or "Generate content from the uploaded assets."
    await seed_project_prompt(db, UUID(str(current_user.id)), project_id, prompt_text)

    run = WorkflowRun(
        project_id=project_id,
        status=WorkflowStatus.PENDING,
        current_step="analyze",
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
        },
    )
    db.add(run)
    project.status = ProjectStatus.PROCESSING
    await db.commit()
    await db.refresh(run)

    return {
        "job_id": str(run.id),
        "status": run.status.value,
    }


@router.get("/{project_id}/jobs", response_model=list[WorkflowRunResponse])
async def list_project_jobs(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[WorkflowRun]:
    """List generation jobs for a project, newest first."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
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
    current_user: User | None = Depends(get_current_user),
) -> WorkflowRun:
    """Get a single generation job's status."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
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
    current_user: User | None = Depends(get_current_user),
) -> list[Clip]:
    """List generated clips for a project."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )

    result = await db.execute(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/derivatives", response_model=list[DerivativeResponse])
async def list_project_derivatives(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[Derivative]:
    """List generated derivatives (LinkedIn posts, quote cards) for a project."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
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
    current_user: User = Depends(get_current_user_required),
) -> Response:
    """Export all generated content for a project as a zip archive."""
    project = await get_project_for_user(
        db, project_id, current_user.id, allow_demo=False
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
                lines.append(f"\n## Clip {idx}: {clip.hook}\n")
                lines.append(f"- Duration: {clip.duration}s\n")
                lines.append(f"- Mood: {clip.music_mood}\n")
                lines.append(f"- Title options: {', '.join(clip.title_options or [])}\n")
            zf.writestr("clips.md", "".join(lines))

        # Derivatives grouped by type
        posts = [d for d in derivatives if d.type == DerivativeType.POST]
        if posts:
            lines = [f"# Social Posts for {project.title}\n"]
            for d in posts:
                content = d.content
                lines.append(f"\n---\n\n{content.get('content', '')}\n")
                hashtags = content.get("hashtags", [])
                if hashtags:
                    lines.append("\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags) + "\n")
            zf.writestr("post.md", "".join(lines))

        quotes = [d for d in derivatives if d.type == DerivativeType.QUOTES]
        if quotes:
            lines = [f"# Quotes for {project.title}\n"]
            for d in quotes:
                for q in d.content.get("quotes", []):
                    lines.append(f"\n> \"{q.get('quote', '')}\"\n")
                    lines.append(f"> — {q.get('attribution', '')}\n")
            zf.writestr("quotes.md", "".join(lines))

        articles = [d for d in derivatives if d.type == DerivativeType.ARTICLE]
        if articles:
            lines = [f"# Articles for {project.title}\n"]
            for d in articles:
                content = d.content
                if content.get("title"):
                    lines.append(f"\n## {content['title']}\n")
                lines.append(f"\n{content.get('content', '')}\n")
            zf.writestr("article.md", "".join(lines))

        carousels = [d for d in derivatives if d.type == DerivativeType.CAROUSEL]
        if carousels:
            lines = [f"# Carousels for {project.title}\n"]
            for d in carousels:
                for slide in d.content.get("slides", []):
                    if slide.get("title"):
                        lines.append(f"\n## {slide['title']}\n")
                    if slide.get("body"):
                        lines.append(f"\n{slide['body']}\n")
            zf.writestr("carousel.md", "".join(lines))

    buffer.seek(0)
    filename = f"{project.title.replace(' ', '_').lower() or 'export'}.zip"
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
