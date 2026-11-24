"""Project router."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Float, Integer, String, cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetStatus,
    BulkDeleteRequest,
    CreateConversationRequest,
    PublicationState,
    ChatOutputEntry,
    ProjectConversationSummary,
    ProjectCreate,
    ProjectResponse,
    ProjectResultsResponse,
    ProjectUpdate,
)
from app.models.tables import (
    Asset,
    Composition,
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
from app.providers.storage import delete_file, delete_project_files, is_export_location, matches_export_location, resolve_stored_url
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
    include_thumbnail: bool = True,
) -> list[ProjectResponse]:
    """List projects for the current user, with a representative clip thumbnail.

    Left-joins each project to its earliest rendered clip (by created_at) so
    the home page can show a real video thumbnail + duration/aspect badge
    without a second round trip per card.
    """
    # Projects are private to their owner; anonymous users see nothing.
    if not current_user:
        return []
    has_messages = (
        select(Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.project_id == Project.id)
        .exists()
    )
    query = select(Project).where(Project.user_id == current_user.id, has_messages)
    if include_thumbnail:
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
        query = query.outerjoin(thumb, thumb.c.project_id == Project.id).add_columns(
            thumb.c.output_id, thumb.c.video_url, thumb.c.duration, thumb.c.render_spec
        )
    if persona_id:
        query = query.where(Project.persona_id == persona_id)
    query = (
        query.order_by(Project.updated_at.desc().nulls_last(), Project.id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    if not include_thumbnail:
        return [ProjectResponse.model_validate(project) for project in result.scalars()]

    responses = []
    for project, output_id, video_url, duration, render_spec in result:
        resp = ProjectResponse.model_validate(project)
        if is_export_location(video_url):
            if matches_export_location(video_url, current_user.id, project.id, output_id):
                resp.thumbnail_url = resolve_stored_url(video_url)
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


@router.get("/{project_id}/conversations", response_model=list[ProjectConversationSummary])
async def list_project_conversations(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> list[ProjectConversationSummary]:
    """List all project-scoped conversations ordered by most recently updated first."""
    await get_project_for_user(db, project_id, UUID(str(current_user.id)))
    conversations = list(
        await db.scalars(
            select(Conversation)
            .where(
                Conversation.project_id == project_id,
                Conversation.user_id == current_user.id,
                Conversation.asset_id.is_(None),
            )
            .order_by(
                Conversation.updated_at.desc().nullslast(),
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
        )
    )
    if not conversations:
        return []
    conv_ids = [c.id for c in conversations]
    count_rows = (
        await db.execute(
            select(Message.conversation_id, func.count(Message.id))
            .where(
                Message.conversation_id.in_(conv_ids),
                Message.role.in_(("user", "assistant")),
                or_(
                    Message.intent.is_(None),
                    ~Message.intent["type"].astext.in_(
                        ("activity", "activity_forensics", "candidates_log", "partial")
                    ),
                ),
            )
            .group_by(Message.conversation_id)
        )
    ).all()
    counts = {cid: int(cnt) for cid, cnt in count_rows}

    active_export_convs = set(
        await db.scalars(
            select(Message.conversation_id)
            .join(ExportJob, ExportJob.receipt_id == Message.id)
            .where(
                Message.conversation_id.in_(conv_ids),
                ExportJob.status.in_(("queued", "running")),
            )
        )
    )
    active_media_convs = set(
        await db.scalars(
            select(Message.conversation_id)
            .join(MediaJob, MediaJob.receipt_id == Message.id)
            .where(
                Message.conversation_id.in_(conv_ids),
                MediaJob.status.in_(("queued", "running")),
            )
        )
    )
    active_convs = active_export_convs | active_media_convs

    summaries: list[ProjectConversationSummary] = []
    for conv in conversations:
        compact = (conv.context or {}).get("compact_summary")
        summaries.append(
            ProjectConversationSummary(
                id=conv.id,
                project_id=project_id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=counts.get(conv.id, 0),
                has_active_job=conv.id in active_convs,
                compacted=bool(isinstance(compact, dict) and compact.get("summary")),
                compacted_at=compact.get("compacted_at") if isinstance(compact, dict) else None,
            )
        )
    return summaries


@router.post(
    "/{project_id}/conversations",
    response_model=ProjectConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_conversation(
    project_id: UUID,
    data: CreateConversationRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> ProjectConversationSummary:
    """Create a fresh conversation thread under an owned project (sharing all project assets & compositions)."""
    await get_project_for_user(db, project_id, UUID(str(current_user.id)))
    now = datetime.now(UTC)
    title = (data.title or "").strip() or "New chat"
    conv = Conversation(
        user_id=current_user.id,
        project_id=project_id,
        title=title,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ProjectConversationSummary(
        id=conv.id,
        project_id=project_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
        has_active_job=False,
        compacted=False,
        compacted_at=None,
    )


def _version_duration_seconds(version: CompositionVersion) -> float:
    settings_dict = version.settings or {}
    timebase = int(settings_dict.get("timebase") or 90000)
    timeline = version.timeline or {}
    max_ticks = 0
    for track in timeline.get("tracks") or []:
        for clip in track.get("clips") or []:
            end = (clip.get("range") or {}).get("end") or 0
            if end > max_ticks:
                max_ticks = int(end)
    for scene in version.scenes or []:
        end = (scene.get("range") or {}).get("end") or 0
        if end > max_ticks:
            max_ticks = int(end)
    return round(max_ticks / timebase, 3) if timebase > 0 else 0.0


@router.get("/{project_id}/workbench")
async def get_project_workbench(
    project_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Project workbench projection: compositions/versions, outputs, assets, active jobs, and reusable skills."""
    from app.pipeline.outputs import visible_outputs_stmt
    from app.skills.resolution import list_available_skills

    owner_id = UUID(str(current_user.id))
    project = await get_project_for_user(db, project_id, owner_id)

    comps = list(
        await db.scalars(
            select(Composition)
            .where(
                Composition.origin_project_id == project_id,
                Composition.owner_id == owner_id,
            )
            .order_by(Composition.created_at.desc())
        )
    )
    comp_ids = [c.id for c in comps]
    versions_by_comp: dict[UUID, list[CompositionVersion]] = {cid: [] for cid in comp_ids}
    if comp_ids:
        all_versions = list(
            await db.scalars(
                select(CompositionVersion)
                .where(CompositionVersion.composition_id.in_(comp_ids))
                .order_by(CompositionVersion.version.desc())
            )
        )
        for v in all_versions:
            versions_by_comp.setdefault(v.composition_id, []).append(v)

    compositions_payload = [
        {
            "composition_id": str(comp.id),
            "name": comp.name,
            "current_version_id": str(comp.current_version_id) if comp.current_version_id else None,
            "versions": [
                {
                    "version_id": str(v.id),
                    "version": v.version,
                    "duration_seconds": _version_duration_seconds(v),
                    "style_preset": ((v.settings or {}).get("style") or {}).get("preset_id"),
                    "is_head": v.id == comp.current_version_id,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in versions_by_comp.get(comp.id, [])
            ],
        }
        for comp in comps
    ]

    outputs_rows = list(
        await db.scalars(
            visible_outputs_stmt()
            .where(Output.project_id == project_id)
            .order_by(Output.created_at.desc())
        )
    )
    outputs_payload = []
    for out in outputs_rows:
        resolved_files: dict[str, str | None] = {}
        for k, val in (out.files or {}).items():
            if isinstance(val, str):
                if is_export_location(val):
                    resolved_files[k] = (
                        resolve_stored_url(val)
                        if matches_export_location(val, owner_id, project_id, out.id)
                        else None
                    )
                else:
                    resolved_files[k] = resolve_stored_url(val)
            else:
                resolved_files[k] = val
        provenance = (out.render_spec or {}).get("provenance") or {}
        outputs_payload.append(
            {
                "id": str(out.id),
                "type": out.type,
                "status": out.status.value if hasattr(out.status, "value") else str(out.status),
                "files": resolved_files,
                "composition_id": str(out.composition_id) if out.composition_id else provenance.get("composition_id"),
                "composition_version_id": (
                    str(out.composition_version_id)
                    if out.composition_version_id
                    else provenance.get("composition_version_id")
                ),
                "created_at": out.created_at.isoformat() if out.created_at else None,
            }
        )

    asset_rows = list(
        await db.scalars(
            select(Asset)
            .where(Asset.project_id == project_id)
            .order_by(Asset.created_at.desc())
        )
    )
    assets_payload = [
        {
            "id": str(a.id),
            "type": a.type.value if hasattr(a.type, "value") else str(a.type),
            "title": a.title or a.display_name,
            "file_url": resolve_stored_url(a.file_url) if a.file_url else None,
            "processing_status": (
                a.processing_status.value
                if hasattr(a.processing_status, "value")
                else str(a.processing_status)
            ),
            "meta": a.meta or {},
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in asset_rows
    ]

    active_jobs: list[dict] = []
    export_rows = (
        await db.execute(
            select(ExportJob, Message.conversation_id)
            .join(Message, ExportJob.receipt_id == Message.id)
            .where(
                ExportJob.project_id == project_id,
                ExportJob.status.in_(("queued", "running")),
            )
            .order_by(ExportJob.created_at.asc())
        )
    ).all()
    for job, conv_id in export_rows:
        active_jobs.append(
            {
                "job_id": str(job.id),
                "kind": "export",
                "status": job.status,
                "label_key": "workbench.job.export",
                "conversation_id": str(conv_id) if conv_id else None,
                "receipt_id": str(job.receipt_id),
                "target_version_id": str(job.version_id),
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
        )

    media_kind_map = {
        "generate_image": "image",
        "generate_voice": "voice",
        "generate_music": "music",
        "image": "image",
        "voice": "voice",
        "music": "music",
    }
    media_rows = (
        await db.execute(
            select(MediaJob, Message.conversation_id, Message.intent)
            .join(Message, MediaJob.receipt_id == Message.id)
            .where(
                MediaJob.project_id == project_id,
                MediaJob.status.in_(("queued", "running")),
            )
            .order_by(MediaJob.created_at.asc())
        )
    ).all()
    for job, conv_id, intent in media_rows:
        norm_kind = media_kind_map.get(job.kind, job.kind)
        active_jobs.append(
            {
                "job_id": str(job.id),
                "kind": norm_kind,
                "status": job.status,
                "label_key": f"workbench.job.{norm_kind}",
                "conversation_id": str(conv_id) if conv_id else None,
                "receipt_id": str(job.receipt_id),
                "target_version_id": (intent or {}).get("version_id"),
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
        )

    for a in asset_rows:
        if a.processing_status == AssetStatus.PROCESSING:
            active_jobs.append(
                {
                    "job_id": str(a.id),
                    "kind": "asset_processing",
                    "status": "running",
                    "label_key": "workbench.job.assetProcessing",
                    "conversation_id": None,
                    "receipt_id": None,
                    "target_version_id": None,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
            )

    available_skills = await list_available_skills(db, owner_id=owner_id)
    blueprint_skills = [
        opt.model_dump(mode="json")
        for opt in available_skills
        if getattr(opt, "blueprint_summary", None) is not None
    ]

    return {
        "project": {
            "id": str(project.id),
            "title": project.title,
            "language": project.language,
            "status": project.status.value if hasattr(project.status, "value") else str(project.status),
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        },
        "compositions": compositions_payload,
        "outputs": outputs_payload,
        "assets": assets_payload,
        "active_jobs": active_jobs,
        "skills": blueprint_skills,
    }
