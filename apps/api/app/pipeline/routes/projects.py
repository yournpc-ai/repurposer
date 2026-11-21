"""Project router."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Float, Integer, String, cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetStatus,
    BulkDeleteRequest,
    PublicationState,
    ChatOutputEntry,
    ProjectCreate,
    ProjectResponse,
    ProjectResultsResponse,
    ProjectUpdate,
)
from app.models.tables import (
    Asset,
    CompositionVersion,
    Conversation,
    ConversationUsage,
    CreditTransaction,
    ExportJob,
    MediaJob,
    NarrationAlignment,
    SourceSnapshot,
    Message,
    Output,
    Persona,
    Project,
    Publication,
    User,
)
from app.pipeline.outputs import (
    chat_delivery_output_ids,
    is_delivered_output,
    output_to_response,
)
from app.platform.billing import settled_job_amounts
from app.platform.conversation_context import get_project_prompt
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
    has_messages = (
        select(Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.project_id == Project.id)
        .exists()
    )
    query = (
        select(Project, thumb.c.output_id, thumb.c.video_url, thumb.c.duration, thumb.c.render_spec)
        .outerjoin(thumb, thumb.c.project_id == Project.id)
        .where(Project.user_id == current_user.id)
        .where(has_messages)
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
    """Read the owned project, original instruction, presentation and asset status."""
    project = await get_project_for_user(
        db, project_id, current_user.id if current_user else None
    )

    # The original prompt is the first user message in the project-scoped conversation.
    prompt = await get_project_prompt(db, project_id)

    assets_result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)
    )
    assets = list(assets_result.scalars().all())

    return {
        "project": project,
        "prompt": prompt,
        "assets": assets,
        "pending_brief": project.pending_brief,
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


async def _jobs_settled(db, project_ids, user_id):
    for model, ref_key in ((MediaJob, "media_job_id"), (ExportJob, "export_id")):
        jobs = (await db.execute(
            select(model, Message.intent).join(Message, Message.id == model.receipt_id)
            .where(model.project_id.in_(project_ids)).order_by(model.id)
        )).all()
        if not jobs:
            continue
        if any(job.status not in {"succeeded", "failed", "cancelled"} for job, _ in jobs):
            return False
        reference = CreditTransaction.ref[ref_key].astext
        totals = (await db.execute(
            select(reference, CreditTransaction.kind, func.sum(CreditTransaction.amount))
            .join(model, cast(model.id, String) == reference)
            .where(model.project_id.in_(project_ids), CreditTransaction.user_id == user_id,
                   CreditTransaction.kind.in_(("hold", "release", "capture")))
            .group_by(reference, CreditTransaction.kind)
        )).all()
        amounts = {(key, kind): amount for key, kind, amount in totals}
        for job, intent in jobs:
            result = (intent or {}).get("media_result") or {}
            expected = settled_job_amounts(job, result, export=model is ExportJob)
            if expected is None or any(
                amounts.get((str(job.id), kind), 0) != value for kind, value in expected.items()
            ):
                return False
    return True


async def _delete_projects(db: AsyncSession, ids: list[UUID], user_id: UUID) -> None:
    ids = sorted(set(ids))
    owned = (await db.scalars(
        select(Project.id).where(Project.id.in_(ids), Project.user_id == user_id)
        .order_by(Project.id).with_for_update()
    )).all()
    if len(owned) != len(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    busy = (
        select(Asset.id).where(Asset.project_id.in_(ids), or_(
            Asset.processing_status == AssetStatus.PROCESSING,
            (Asset.processing_status == AssetStatus.PENDING) & Asset.processing_requested_at.is_not(None),
        )),
        select(NarrationAlignment.id).join(SourceSnapshot, SourceSnapshot.id == NarrationAlignment.audio_snapshot_id)
        .where(SourceSnapshot.origin_project_id.in_(ids), NarrationAlignment.status.in_(("PENDING", "PROCESSING"))),
        select(Publication.id).where(Publication.project_id.in_(ids),
            Publication.state.in_((PublicationState.SCHEDULED, PublicationState.PUBLISHING, PublicationState.UNKNOWN))),
    )
    conflict = ("该项目仍有正在执行或待核对费用的任务，暂时无法删除。"
                if (current_ui_language() or "").startswith("zh")
                else "This project has active work or unsettled charges. Try again after settlement.")
    if not await _jobs_settled(db, ids, user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, conflict)
    for query in busy:
        if await db.scalar(query.limit(1)):
            raise HTTPException(status.HTTP_409_CONFLICT, conflict)

    files = (await db.scalars(select(Asset.file_url).where(Asset.project_id.in_(ids)))).all()
    await db.execute(delete(MediaJob).where(MediaJob.project_id.in_(ids)))
    await db.execute(delete(ExportJob).where(ExportJob.project_id.in_(ids)))
    await db.execute(delete(Publication).where(Publication.project_id.in_(ids)))
    await db.execute(delete(Output).where(Output.project_id.in_(ids)))
    await db.execute(delete(Asset).where(Asset.project_id.in_(ids)))
    await db.execute(update(ConversationUsage).where(ConversationUsage.project_id.in_(ids)).values(project_id=None))
    await db.execute(delete(Project).where(Project.id.in_(ids)))
    await db.commit()
    for key in files:
        await delete_file(key)
    for project_id in ids:
        await delete_project_files(project_id, user_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID, db: DBDep, current_user: User = Depends(get_current_user_required),
) -> None:
    await _delete_projects(db, [project_id], current_user.id)


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_projects(
    request: BulkDeleteRequest, db: DBDep, current_user: User = Depends(get_current_user_required),
) -> None:
    await _delete_projects(db, request.ids, current_user.id)


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
    by_id = {output.id: output for output in outputs if is_delivered_output(output)}
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
