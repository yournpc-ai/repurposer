"""Project router."""

import io
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Integer, cast, delete, select

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetType,
    ExportRequest,
    GenerateRequest,
    OutputResponse,
    PendingIntent,
    ProjectCreate,
    ProjectIntentRequest,
    ProjectIntentResponse,
    ProjectResponse,
    ProjectResultsResponse,
    ProjectStatus,
    ProjectUpdate,
    RunResponse,
)
from app.models.tables import (
    Asset,
    Output,
    WorkflowStep,
    Project,
    Speaker,
    User,
    WorkflowRun,
)
from app.chat.intent import composer_intent_agent
from app.chat.service import get_project_prompt, seed_project_prompt
from app.pipeline.orchestrator import TaskSpec, create_run
from app.pipeline.outputs import (
    aggregate_step_cost,
    list_visible_outputs,
    workflow_step_to_response,
    run_to_response,
    visible_outputs_stmt,
)
from app.platform.project_context import get_project_for_user
from app.tools.storage import delete_file, delete_project_files, resolve_stored_url

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
            Output.project_id.label("project_id"),
            Output.files["video"].as_string().label("video_url"),
            cast(Output.payload["duration"].as_string(), Integer).label("duration"),
            Output.render_spec.label("render_spec"),
        )
        .distinct(Output.project_id)
        .where(Output.type == "clip")
        .where(Output.files.has_key("video"))
        .order_by(Output.project_id, Output.created_at.asc())
        .subquery()
    )
    # Projects are private to their owner; anonymous users see nothing.
    if not current_user:
        return []
    query = (
        select(Project, thumb.c.video_url, thumb.c.duration, thumb.c.render_spec)
        .outerjoin(thumb, thumb.c.project_id == Project.id)
        .where(Project.user_id == current_user.id)
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

    responses = []
    for project, video_url, duration, render_spec in rows:
        resp = ProjectResponse.model_validate(project)
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
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}/results", response_model=ProjectResultsResponse)
async def get_project_results(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> dict:
    """Aggregate project results: metadata, prompt, outputs, latest run + steps."""
    project = await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )

    # The original prompt is the first user message in the project-scoped conversation.
    prompt = await get_project_prompt(db, project_id)

    latest_run_result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()

    # User-facing outputs only (internal node artifacts stay hidden). Outputs
    # are replaced per type on each run, so the list is already "latest".
    outputs = await list_visible_outputs(db, project_id)

    nodes: list[WorkflowStep] = []
    if latest_run is not None:
        nodes_result = await db.execute(
            select(WorkflowStep)
            .where(WorkflowStep.run_id == latest_run.id)
            .order_by(WorkflowStep.seq)
        )
        nodes = list(nodes_result.scalars().all())

    latest_run_resp = None
    if latest_run is not None:
        latest_run_resp = RunResponse.model_validate(latest_run)
        latest_run_resp.steps = [workflow_step_to_response(n) for n in nodes]
        latest_run_resp.cost = aggregate_step_cost(nodes)

    # Asset processing statuses power the overlay's pre-run placeholder (the
    # transcribing/parsing phase before the generation run's steps exist).
    assets_result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)
    )
    assets = list(assets_result.scalars().all())

    return {
        "project": project,
        "prompt": prompt,
        "outputs": outputs,
        "latest_run": latest_run_resp,
        "assets": assets,
        "pending_intent": project.pending_intent,
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
        db, project_id, current_user.id
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
        db, project_id, current_user.id
    )

    # Delete child rows in FK-safe order, then the project. Asset files are
    # unlinked individually since we need each file_url before deletion.
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    for asset in result.scalars().all():
        await delete_file(asset.file_url)

    await db.execute(delete(Output).where(Output.project_id == project_id))
    await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(delete(Asset).where(Asset.project_id == project_id))
    await db.delete(project)
    await db.commit()

    # Remove project upload directory after DB commit
    await delete_project_files(project_id, current_user.id)


@router.post("/{project_id}/intent", response_model=ProjectIntentResponse)
async def infer_project_intent(
    project_id: UUID,
    data: ProjectIntentRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> ProjectIntentResponse:
    """Infer the generation task book for a project.

    Reads the project's assets so we can detect material/output conflicts
    (e.g. clips requested without renderable media). When the intent is
    ambiguous, ``needs_clarification`` is true and the frontend should show
    the inferred task book for confirmation before calling ``/generate``.
    """
    project = await get_project_for_user(
        db, project_id, UUID(str(current_user.id))
    )

    assets = list(
        (
            await db.execute(
                select(Asset).where(
                    Asset.project_id == project_id,
                    Asset.file_url.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    first_file = next((a for a in assets if a.file_url), None)
    filename = first_file.file_url.rsplit("/", 1)[-1] if first_file else None

    intent = await composer_intent_agent.infer(
        prompt=data.prompt or "",
        filename=filename,
    )

    has_renderable_media = any(
        a.type
        in (
            AssetType.VIDEO,
            AssetType.AUDIO,
            AssetType.IMAGE,
            AssetType.SLIDES,
        )
        for a in assets
    )

    reasons: list[str] = []
    if not intent.language_explicit:
        reasons.append("language_default")
    if not intent.outputs_explicit:
        reasons.append("outputs_default")
    if "clips" in intent.outputs and not intent.clip_count_explicit:
        reasons.append("clip_count_default")
    if "clips" in intent.outputs and not has_renderable_media:
        reasons.append("clips_without_media")

    needs_clarification = bool(reasons)

    # A call that omits brand_template_id (chat refinements, the overlay's
    # fallback fetch) must not clobber the brand choice the composer made.
    brand_template_id = data.brand_template_id
    if brand_template_id is None and isinstance(project.pending_intent, dict):
        brand_template_id = project.pending_intent.get("brand_template_id")

    # Persist the unconfirmed task book on the project: leaving the plan-
    # confirmation chat and coming back (any device) restores this exact
    # plan. Cleared by /generate once the run starts.
    project.pending_intent = PendingIntent(
        prompt=data.prompt or "",
        intent=intent,
        needs_clarification=needs_clarification,
        reasons=reasons,
        brand_template_id=brand_template_id,
    ).model_dump(mode="json")
    await db.commit()

    return ProjectIntentResponse(
        intent=intent,
        needs_clarification=needs_clarification,
        reasons=reasons,
    )


@router.post("/{project_id}/generate", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def generate_content(
    project_id: UUID,
    request: GenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Queue background generation for a project.

    Ensures the project-scoped conversation exists so the original prompt is
    persisted, then creates a PENDING WorkflowRun. The background worker claims
    and runs it (see app.worker).
    """
    project = await get_project_for_user(
        db, project_id, UUID(str(current_user.id))
    )

    # Full-scope runs from the composer must now provide an explicit task book
    # resolved by POST /projects/{id}/intent. Retries, targeted runs and API
    # callers continue to pass explicit outputs.
    outputs = request.outputs
    target_language = request.target_language
    clip_count = request.clip_count
    instruction = request.instruction
    if outputs is None and request.scope == "full":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task book must be confirmed via /projects/{id}/intent first.",
        )
    if outputs is None:
        # Non-full scopes without explicit outputs keep the pre-intent default.
        outputs = ["clips", "post", "quotes", "article"]
    target_language = target_language or "en"
    instruction = instruction or "Generate content from the uploaded assets."

    # Clips need a renderable media source (video / audio / image / slides).
    # Reject early instead of letting the run produce unrenderable clips.
    if "clips" in outputs and request.scope == "full":
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

    # Persist the original prompt in the project-scoped conversation if it is
    # not already there. This is a no-op when the conversation already has messages.
    prompt_text = request.instruction or "Generate content from the uploaded assets."
    await seed_project_prompt(db, UUID(str(current_user.id)), project_id, prompt_text)

    run = await create_run(
        db,
        project,
        TaskSpec(
            outputs=outputs,
            clip_count=clip_count,
            quotes_count=request.quotes_count,
            carousel_count=request.carousel_count,
            target_language=target_language,
            instruction=instruction,
            tone_settings=(
                request.tone_settings.model_dump() if request.tone_settings else None
            ),
            brand_template_id=(
                str(request.brand_template_id) if request.brand_template_id else None
            ),
            scope=request.scope,
            operation=request.operation,
            target_id=request.target_id,
        ),
    )
    project.status = ProjectStatus.PROCESSING
    # The task book is confirmed now — drop the unconfirmed copy.
    project.pending_intent = None
    await db.commit()
    await db.refresh(run)

    return {
        "run_id": str(run.id),
        "status": run.status.value,
    }


@router.get("/{project_id}/runs", response_model=list[RunResponse])
async def list_project_runs(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[WorkflowRun]:
    """List generation runs for a project, newest first."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/runs/{run_id}", response_model=RunResponse)
async def get_project_run(
    project_id: UUID,
    run_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> RunResponse:
    """Get a single generation run's status (with workflow steps + aggregated cost)."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
    run = await db.get(WorkflowRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    return await run_to_response(db, run)


@router.get("/{project_id}/clips", response_model=list[OutputResponse])
async def list_project_clips(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[Output]:
    """List generated clip outputs for a project."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
    return await list_visible_outputs(db, project_id, output_type="clip")


@router.get("/{project_id}/derivatives", response_model=list[OutputResponse])
async def list_project_derivatives(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[Output]:
    """List generated derivative outputs (posts, quote cards, …) for a project."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
    result = await db.execute(
        visible_outputs_stmt()
        .where(Output.project_id == project_id, Output.type != "clip")
        .order_by(Output.created_at.desc())
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
        db, project_id, current_user.id
    )

    outputs = await list_visible_outputs(db, project_id)
    clips = [o for o in outputs if o.type == "clip"]
    derivatives = [o for o in outputs if o.type != "clip"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Clips
        if clips:
            lines: list[str] = [f"# Clips for {project.title}\n"]
            for idx, clip in enumerate(clips, start=1):
                payload = clip.payload or {}
                lines.append(f"\n## Clip {idx}: {payload.get('hook', '')}\n")
                lines.append(f"- Duration: {payload.get('duration', 30)}s\n")
                lines.append(f"- Mood: {payload.get('music_mood', 'calm')}\n")
                lines.append(
                    f"- Title options: {', '.join(payload.get('title_options') or [])}\n"
                )
            zf.writestr("clips.md", "".join(lines))

        # Derivatives grouped by type
        posts = [d for d in derivatives if d.type == "post"]
        if posts:
            lines = [f"# Social Posts for {project.title}\n"]
            for d in posts:
                content = d.payload or {}
                lines.append(f"\n---\n\n{content.get('content', '')}\n")
                hashtags = content.get("hashtags", [])
                if hashtags:
                    lines.append("\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags) + "\n")
            zf.writestr("post.md", "".join(lines))

        quotes = [d for d in derivatives if d.type == "quotes"]
        if quotes:
            lines = [f"# Quotes for {project.title}\n"]
            for d in quotes:
                for q in (d.payload or {}).get("quotes", []):
                    lines.append(f"\n> \"{q.get('quote', '')}\"\n")
                    lines.append(f"> — {q.get('attribution', '')}\n")
            zf.writestr("quotes.md", "".join(lines))

        articles = [d for d in derivatives if d.type == "article"]
        if articles:
            lines = [f"# Articles for {project.title}\n"]
            for d in articles:
                content = d.payload or {}
                if content.get("title"):
                    lines.append(f"\n## {content['title']}\n")
                lines.append(f"\n{content.get('content', '')}\n")
            zf.writestr("article.md", "".join(lines))

        carousels = [d for d in derivatives if d.type == "carousel"]
        if carousels:
            lines = [f"# Carousels for {project.title}\n"]
            for d in carousels:
                for slide in (d.payload or {}).get("slides", []):
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
