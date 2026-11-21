"""Project router."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Float, Integer, cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetResponse,
    BulkDeleteRequest,
    ChatOutputEntry,
    GraphNodeResponse,
    ProjectCreate,
    ProjectGraphResponse,
    ProjectResponse,
    ProjectResultsResponse,
    ProjectUpdate,
    RunResponse,
    WorkflowStatus,
)
from app.models.tables import (
    Asset,
    CompositionVersion,
    Conversation,
    ConversationUsage,
    GraphEdge,
    GraphNode,
    Message,
    Output,
    Persona,
    Project,
    Publication,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.lifecycle import project_lifecycle
from app.pipeline.outputs import (
    aggregate_step_cost,
    chat_delivery_output_ids,
    is_chat_video_output,
    output_to_response,
    run_to_response,
    workflow_step_to_response,
)
from app.platform.billing import (
    release_run,
)
from app.platform.configs import get_config
from app.platform.conversation_context import (
    find_conversation,
    get_project_prompt,
    is_pending_plan,
    latest_pending_question,
)
from app.platform.project_context import get_project_for_user
from app.providers.storage import delete_file, delete_project_files, is_export_location, presign_download, matches_export_location, resolve_stored_url
from app.ui_locale import current_ui_language

router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Project:
    """Create a new project."""
    if data.persona_id:
        persona_result = await db.execute(
            select(Persona).where(
                Persona.id == data.persona_id,
                Persona.user_id == current_user.id,
            )
        )
        persona = persona_result.scalar_one_or_none()
        if not persona:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Persona not found",
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
    persona_id: UUID | None = None,
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
            Output.id.label("output_id"),
            Output.files["video"].as_string().label("video_url"),
            cast(
                func.floor(cast(Output.payload["duration"].as_string(), Float)), Integer
            ).label("duration"),
            Output.render_spec.label("render_spec"),
        )
        .distinct(Output.project_id)
        .where(Output.type == "video")
        .where(Output.files.has_key("video"))
        .order_by(Output.project_id, Output.created_at.asc())
        .subquery()
    )
    # Projects are private to their owner; anonymous users see nothing.
    if not current_user:
        return []
    # Empty-project filter (intent-surface-unification W4): the composer
    # creates the project BEFORE the first chat message lands — a project
    # with no conversation messages and no runs is an abandoned shell
    # (send → close), not a project. It reappears once the first message
    # or run exists, so the create→first-message window is invisible here.
    has_messages = (
        select(Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.project_id == Project.id)
        .exists()
    )
    has_runs = select(WorkflowRun.id).where(WorkflowRun.project_id == Project.id).exists()
    query = (
        select(Project, thumb.c.output_id, thumb.c.video_url, thumb.c.duration, thumb.c.render_spec)
        .outerjoin(thumb, thumb.c.project_id == Project.id)
        .where(Project.user_id == current_user.id)
        .where(or_(has_messages, has_runs))
    )
    if persona_id:
        query = query.where(Project.persona_id == persona_id)
    query = (
        query.order_by(Project.updated_at.desc().nulls_last())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()

    responses = []
    for project, output_id, video_url, duration, render_spec in rows:
        resp = ProjectResponse.model_validate(project)
        if is_export_location(video_url):
            if matches_export_location(video_url, current_user.id, project.id, output_id):
                resp.thumbnail_url = await presign_download(video_url)
        else:
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
    steps: list[WorkflowStep] = []
    if latest_run is not None:
        steps = list(
            (
                await db.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == latest_run.id)
                    .order_by(WorkflowStep.seq)
                )
            ).scalars().all()
        )
    latest_run_resp = None
    if latest_run is not None:
        latest_run_resp = RunResponse.model_validate(latest_run)
        ratio = await get_config(db, "credits.per_cost_usd")
        latest_run_resp.steps = [workflow_step_to_response(step, ratio=ratio) for step in steps]
        latest_run_resp.cost = aggregate_step_cost(steps)

    # Asset processing statuses power the overlay's pre-run placeholder (the
    # transcribing/parsing phase before the generation run's steps exist).
    assets_result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)
    )
    assets = list(assets_result.scalars().all())

    return {
        "project": project,
        "prompt": prompt,
        "latest_run": latest_run_resp,
        "assets": assets,
        "pending_brief": project.pending_brief,
        # Lifecycle Projection (ADR-087 §2, Phase 1): the server-named
        # stamp rides the same frame — additive; clients keep their old
        # derivations until the dual-read switch.
        "lifecycle": await _lifecycle_stamp(db, project),
    }


# asset_type → 媒介值 (上传素材 = 媒介×manual, ADR-076 映射律): a slides
# deck's consumption form is video (stills chain); a pasted transcript /
# past material reads as text.
_ASSET_MEDIUM = {
    "video": "video",
    "audio": "audio",
    "voice_sample": "audio",
    "image": "image",
    "slides": "video",
    "transcript": "text",
    "past_material": "text",
}


# ---- Lifecycle Projection stamp (ADR-087 §2, Phase 1) -----------------------

async def _lifecycle_stamp(db: AsyncSession, project: Project) -> dict:
    """Assemble the server-named lifecycle stamp for one read frame.

    The Agent Interface facts (the docked plan row) are fetched through the
    conversation store's shared read protocol (``app.platform.conversation_context``)
    and passed IN — the projection module itself never imports chat
    (dependency direction, ADR-087 §6)."""
    conversation = await find_conversation(db, project.user_id, project.id)
    pending = (
        await latest_pending_question(db, UUID(str(conversation.id)))
        if conversation is not None
        else None
    )
    stamp = await project_lifecycle(
        db,
        project,
        pending_question=pending,
        pending_plan=is_pending_plan(pending),
        ui_language=current_ui_language() or "en",
    )
    return stamp.to_payload()


@router.get("/{project_id}/graph", response_model=ProjectGraphResponse)
async def get_project_graph(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> dict:
    """Read only source assets and ordinary manual Graph nodes."""
    project = await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
    rows = list(
        (
            await db.execute(
                select(GraphNode)
                .where(GraphNode.project_id == project_id)
                .order_by(GraphNode.created_at.asc())
            )
        ).scalars().all()
    )
    nodes = [
        node for node in rows
        if node.type == "asset" or (node.spec or {}).get("prototype") == "manual"
    ]
    node_ids = {node.id for node in nodes}
    edges = list(
        (
            await db.execute(
                select(GraphEdge)
                .where(GraphEdge.project_id == project_id)
                .order_by(GraphEdge.created_at.asc())
            )
        ).scalars().all()
    )
    asset_ids = [node.spec.get("asset_id") for node in nodes if node.type == "asset"]
    assets = {
        str(asset.id): asset
        for asset in (
            await db.execute(select(Asset).where(Asset.id.in_([UUID(str(item)) for item in asset_ids])))
        ).scalars().all()
    } if asset_ids else {}
    response_nodes = []
    for node in nodes:
        spec = dict(node.spec or {})
        asset_response = None
        face_type = node.type
        if node.type == "asset":
            asset = assets.get(str(spec.get("asset_id")))
            if asset is None:
                continue
            asset_response = AssetResponse.model_validate(asset)
            meta = asset.meta or {}
            if isinstance(meta.get("width"), int) and isinstance(meta.get("height"), int):
                asset_response.width = meta["width"]
                asset_response.height = meta["height"]
            face_type = _ASSET_MEDIUM.get(str(asset.type), "text")
            spec["prototype"] = "manual"
        response_nodes.append(GraphNodeResponse(
            id=node.id,
            type=face_type,
            state=node.state,
            spec=spec,
            layout=node.layout or {},
            asset=asset_response,
            created_at=node.created_at,
            updated_at=node.updated_at,
        ))
    return {
        "nodes": response_nodes,
        "edges": [edge for edge in edges if edge.from_node in node_ids and edge.to_node in node_ids],
        "lifecycle": await _lifecycle_stamp(db, project),
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


async def _delete_project_rows(db: DBDep, project: Project, user_id: UUID) -> None:
    """The ONE deletion seat for a project (single + bulk doors share it).
    Child rows go in FK-safe order, then the project; asset files are
    unlinked individually since we need each file_url before deletion.
    operations (journal, NO ACTION on both its FKs) and publications
    (RESTRICT on output) must go BEFORE outputs; workflow_steps cascade
    from runs, conversations/messages cascade from the project. The caller
    owns the transaction boundary (no commit here)."""
    project_id = UUID(str(project.id))
    from app.models.tables import ExportJob
    from app.pipeline.export_jobs import cancel_export
    await db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    for job_id in await db.scalars(select(ExportJob.id).where(ExportJob.project_id == project_id)):
        await cancel_export(db, project, job_id)
    await db.execute(delete(ExportJob).where(ExportJob.project_id == project_id))
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    for asset in result.scalars().all():
        await delete_file(asset.file_url)

    await db.execute(delete(Publication).where(Publication.project_id == project_id))
    await db.execute(delete(Output).where(Output.project_id == project_id))
    # Credits (ADR-055): the ledger is append-only and outlives run rows, so
    # release every un-settled hold BEFORE the cascade deletes the runs — a
    # frozen hold would have no terminal left to settle at (orphan hold,
    # BILLING §8). RUNNING runs stay with their in-flight worker: its
    # finalize path settles from the ledger even after the row is gone.
    run_ids = (
        await db.execute(
            select(WorkflowRun.id).where(
                WorkflowRun.project_id == project_id,
                WorkflowRun.status != WorkflowStatus.RUNNING,
            )
        )
    ).scalars().all()
    for rid in run_ids:
        await release_run(db, user_id=user_id, run_id=rid)
    await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(delete(Asset).where(Asset.project_id == project_id))
    # conversation_usage is the conversation layer's COGS ledger (ADR-117
    # D3): append-only, outlives the project — the column is nullable by
    # design for project-less surfaces, so unhook, never delete.
    await db.execute(
        update(ConversationUsage)
        .where(ConversationUsage.project_id == project_id)
        .values(project_id=None)
    )
    await db.delete(project)


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
    await _delete_project_rows(db, project, current_user.id)
    await db.commit()

    # Remove project upload directory after DB commit
    await delete_project_files(project_id, current_user.id)


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_projects(
    request: BulkDeleteRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a batch of projects (the grid's multi-select bar). Ownership
    for every id is checked BEFORE a single row is touched — one unknown or
    foreign id 404s the whole request, then one transaction deletes the
    set (no silent partial passes)."""
    projects = [
        await get_project_for_user(db, pid, current_user.id) for pid in request.ids
    ]
    for project in projects:
        await _delete_project_rows(db, project, current_user.id)
    await db.commit()
    for pid in request.ids:
        await delete_project_files(pid, current_user.id)


@router.get("/{project_id}/chat/outputs", response_model=list[ChatOutputEntry])
async def list_chat_delivered_outputs(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> list[ChatOutputEntry]:
    """The Chat's exact delivered Outputs, including archived history."""
    await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )
    messages = list((
        await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.project_id == project_id, Message.role == "assistant")
            .order_by(Message.seq, Message.created_at)
        )
    ).scalars().all())
    refs = chat_delivery_output_ids(messages)
    if not refs:
        return []

    outputs = list((
        await db.execute(select(Output).where(
            Output.project_id == project_id,
            Output.id.in_(refs),
        ).order_by(Output.created_at, Output.id))
    ).scalars().all())
    by_id = {output.id: output for output in outputs if is_chat_video_output(output)}
    extant_ids = {output.id for output in outputs}
    version_ids = list(dict.fromkeys(
        output.composition_version_id for output in by_id.values()
        if output.composition_version_id is not None
    ))
    versions = list((
        await db.execute(select(CompositionVersion).where(CompositionVersion.id.in_(version_ids)))
    ).scalars().all()) if version_ids else []
    version_numbers = {version.id: version.version for version in versions}
    return [
        ChatOutputEntry(
            output_id=output_id,
            output=(
                output_to_response(
                    output,
                    composition_version_number=version_numbers.get(output.composition_version_id),
                )
                if (output := by_id.get(output_id)) is not None
                else None
            ),
        )
        for output_id in refs
        if output_id in by_id or output_id not in extant_ids
    ]


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
