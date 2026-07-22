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
    ProjectCreate,
    ProjectResponse,
    ProjectResultsResponse,
    ProjectStatus,
    ProjectUpdate,
    WorkflowRunResponse,
)
from app.models.tables import (
    Asset,
    Output,
    PlanNode,
    Project,
    Speaker,
    User,
    WorkflowRun,
)
from app.services.chat import get_project_prompt, seed_project_prompt
from app.services.demo_seed import DEMO_PROJECT_ID
from app.services.orchestrator import TaskSpec, create_run
from app.services.outputs import (
    aggregate_node_cost,
    list_visible_outputs,
    plan_node_to_response,
    run_to_response,
    visible_outputs_stmt,
)
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
    nodes: list[PlanNode],
    outputs: list[Output],
) -> dict | None:
    """Stepper position for the results-page loading dialog.

    Derived from the run's plan_nodes (RunPlan Phase 1): the current step is
    the first non-settled node by seq; node kind/stage maps onto the existing
    i18n step keys, so the frontend contract ({key, index, total}) is
    unchanged. None = hide the dialog (no run, run failed, or everything
    settled).
    """
    if latest_job is None or latest_job.status == "failed":
        return None

    ctx = latest_job.context or {}
    outputs_requested = ctx.get("outputs") or ["clips"]
    steps = _ui_steps_for_outputs(outputs_requested)

    def at(key: str) -> dict:
        # Targeted runs (script/render) have no matching display step; park at
        # the end of planning rather than failing the index lookup.
        if key not in steps:
            key = "prepare"
        return {"key": key, "index": steps.index(key), "total": len(steps)}

    # Assets still processing (ASR / extraction) — the run queues behind them.
    if any(a.processing_status in ("pending", "processing") for a in assets):
        return at("transcribing")

    if latest_job.status == "pending":
        return at("queued")

    current = next(
        (n for n in nodes if n.status in ("pending", "running")), None
    )
    if current is not None:
        if current.kind in ("preprocess", "persona_bootstrap"):
            return at("analyze")
        if current.kind == "director_plan":
            return at("plan")
        if current.kind == "clips_pipeline":
            stage = (current.spec or {}).get("stage")
            return at(stage if stage in steps else "selecting_segments")
        if current.kind in ("post_gen", "quotes_gen", "carousel_gen", "article_gen"):
            stage = (current.spec or {}).get("stage")
            if stage == "generating_image":
                return at("generating_image")
            return at("writing_copy")
        if current.kind == "render":
            return at("ready_to_render")
        return at("prepare")

    if latest_job.status == "completed":
        if "ready_to_render" in steps and any(
            o.type == "clip" and o.render_status in ("pending", "rendering")
            for o in outputs
        ):
            return at("ready_to_render")
        return None

    return None


@router.get("/{project_id}/results", response_model=ProjectResultsResponse)
async def get_project_results(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> dict:
    """Aggregate project results: metadata, prompt, outputs, latest job + nodes."""
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

    # User-facing outputs only (internal node artifacts stay hidden). Outputs
    # are replaced per type on each run, so the list is already "latest".
    outputs = await list_visible_outputs(db, project_id)

    nodes: list[PlanNode] = []
    if latest_job is not None:
        nodes_result = await db.execute(
            select(PlanNode)
            .where(PlanNode.run_id == latest_job.id)
            .order_by(PlanNode.seq)
        )
        nodes = list(nodes_result.scalars().all())

    latest_job_resp = None
    if latest_job is not None:
        latest_job_resp = WorkflowRunResponse.model_validate(latest_job)
        latest_job_resp.nodes = [plan_node_to_response(n) for n in nodes]
        latest_job_resp.cost = aggregate_node_cost(nodes)

    # Asset processing statuses power the results-page loading state (the
    # transcribing/parsing phase before the generation run starts).
    assets_result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)
    )
    assets = list(assets_result.scalars().all())

    return {
        "project": project,
        "prompt": prompt,
        "outputs": outputs,
        "latest_job": latest_job_resp,
        "assets": assets,
        "ui_step": _compute_ui_step(assets, latest_job, nodes, outputs),
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

    await db.execute(delete(Output).where(Output.project_id == project_id))
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

    run = await create_run(
        db,
        project,
        TaskSpec(
            outputs=list(request.outputs),
            clip_count=request.clip_count,
            target_language=request.target_language,
            instruction=request.instruction,
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
) -> WorkflowRunResponse:
    """Get a single generation job's status (with plan nodes + aggregated cost)."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
    run = await db.get(WorkflowRun, job_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
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
        db, project_id, current_user.id, allow_demo=False
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
