"""Project router."""

import io
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Integer, cast, delete, or_, select

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetResponse,
    ExportRequest,
    GenerateRequest,
    GenerateResponse,
    GraphEdgeResponse,
    GraphNodeResponse,
    GraphReviseRequest,
    GraphReviseResponse,
    OutputResponse,
    ProjectCreate,
    ProjectGraphResponse,
    ProjectResponse,
    ProjectResultsResponse,
    ProjectStatus,
    ProjectUpdate,
    RunResponse,
    WorkflowStatus,
)
from app.models.tables import (
    Asset,
    Conversation,
    GraphEdge,
    GraphNode,
    Message,
    Operation,
    Output,
    Publication,
    WorkflowStep,
    Persona,
    Project,
    User,
    WorkflowRun,
)
from app.chat.service import (
    discard_unanswered_task_book,
    get_project_prompt,
    seed_project_prompt,
)
from app.pipeline.orchestrator import TaskSpec, create_run, first_task_language
from app.pipeline.outputs import (
    aggregate_step_cost,
    compose_spec_prompt,
    list_visible_outputs,
    model_facts_for,
    workflow_step_to_response,
    run_to_response,
    visible_outputs_stmt,
)
from app.platform.billing import (
    CreditsInsufficientError,
    credits_at_ratio,
    estimate_usd_range,
    release_run,
)
from app.platform.configs import get_config
from app.platform.project_context import get_project_for_user
from app.providers.storage import delete_file, delete_project_files, resolve_stored_url

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
        select(Project, thumb.c.video_url, thumb.c.duration, thumb.c.render_spec)
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
        ratio = await get_config(db, "credits.per_cost_usd")
        latest_run_resp.steps = [workflow_step_to_response(n, ratio=ratio) for n in nodes]
        latest_run_resp.cost = aggregate_step_cost(nodes)

    # Per-product spec prompts (ADR-051 F — hover prompt 框): the producing
    # step's slot/params composed in the run's pinned ui_language, stamped
    # only for outputs whose step is in this payload (carried rows stay None
    # — the 框 falls back to its empty-revision form). Same stamp, the
    # per-product model/provider facts (ADR-051 H — 详情面模型事实): the
    # producing step's kind projected to its real model usage (a fact
    # registry, never a selector).
    if latest_run is not None:
        ui_language = str((latest_run.context or {}).get("ui_language") or "en")
        spec_by_step = {
            str(n.id): compose_spec_prompt(n, ui_language) for n in nodes
        }
        kind_by_step = {str(n.id): n.kind for n in nodes}
        for output in outputs:
            if output.workflow_step_id is None:
                continue
            step_id = str(output.workflow_step_id)
            prompt_text = spec_by_step.get(step_id)
            if prompt_text:
                output.spec_prompt = prompt_text
            if step_id in kind_by_step:
                output.model_facts = model_facts_for(kind_by_step[step_id], output)

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
        "pending_brief": project.pending_brief,
    }


@router.get("/{project_id}/graph", response_model=ProjectGraphResponse)
async def get_project_graph(
    project_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> dict:
    """The project graph's one read frame (ADR-057): nodes + edges + the
    joined display rows (asset rows / visible product rows / per-node credit
    estimates). The canvas renders this directly — zero projection, the
    display model IS the domain model."""
    await get_project_for_user(db, project_id, current_user.id if current_user else None)

    nodes = list(
        (
            await db.execute(
                select(GraphNode)
                .where(GraphNode.project_id == project_id)
                .order_by(GraphNode.created_at)
            )
        )
        .scalars()
        .all()
    )
    edges = list(
        (
            await db.execute(
                select(GraphEdge).where(GraphEdge.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    # B1-lite (2026-09-13 演示冻结期, ADR-072 批 B1 的读面先行): the task-book
    # document and every edge touching it are filtered at READ time only —
    # the canvas shows the pure material flow (源 → 文档 → 装配); the confirm
    # beat's seat is the dock pill (ADR-070), the card's own Start was the
    # redundant second seat. The stamp/runner/data are untouched — formal
    # retirement (de-stamp + history cleanup) is 批 B1 after the freeze lifts.
    hidden_book_ids = {
        str(n.id)
        for n in nodes
        if n.kind == "document" and (n.spec or {}).get("role") == "task_book"
    }
    if hidden_book_ids:
        nodes = [n for n in nodes if str(n.id) not in hidden_book_ids]
        edges = [
            e
            for e in edges
            if str(e.from_node) not in hidden_book_ids
            and str(e.to_node) not in hidden_book_ids
        ]
    if not nodes:
        return {"nodes": [], "edges": []}

    # ── Joined display rows ──────────────────────────────────────────────
    asset_ids = [
        UUID(str((n.spec or {}).get("asset_id")))
        for n in nodes
        if n.kind == "asset" and (n.spec or {}).get("asset_id")
    ]
    assets_by_id = {}
    if asset_ids:
        assets_by_id = {
            str(a.id): a
            for a in (
                await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))
            )
            .scalars()
            .all()
        }

    visible = await list_visible_outputs(db, project_id)
    outputs_by_id = {str(o.id): o for o in visible}

    # The outputs' dossier facts (spec_prompt / model_facts — OutputInspector
    # and the lightbox read them, same stamp as /results): the producing
    # step's slot/params composed in that step's run's pinned ui_language.
    step_ids = [o.workflow_step_id for o in visible if o.workflow_step_id is not None]
    if step_ids:
        steps = list(
            (
                await db.execute(select(WorkflowStep).where(WorkflowStep.id.in_(step_ids)))
            )
            .scalars()
            .all()
        )
        steps_by_id = {str(s.id): s for s in steps}
        run_ids = list({s.run_id for s in steps})
        runs = list(
            (
                await db.execute(select(WorkflowRun).where(WorkflowRun.id.in_(run_ids)))
            )
            .scalars()
            .all()
        )
        ui_lang_by_run = {
            str(r.id): str((r.context or {}).get("ui_language") or "en") for r in runs
        }
        for output in visible:
            step = steps_by_id.get(str(output.workflow_step_id))
            if step is None:
                continue
            prompt_text = compose_spec_prompt(
                step, ui_lang_by_run.get(str(step.run_id), "en")
            )
            if prompt_text:
                output.spec_prompt = prompt_text
            output.model_facts = model_facts_for(step.kind, output)

    ratio = await get_config(db, "credits.per_cost_usd")

    resp_nodes: list[GraphNodeResponse] = []
    for node in nodes:
        spec = dict(node.spec or {})
        estimate_credits: list[int] | None = None
        if spec.get("estimate"):
            usd_low, usd_high = estimate_usd_range(spec["estimate"])
            estimate_credits = [
                credits_at_ratio(usd_low, ratio),
                credits_at_ratio(usd_high, ratio),
            ]
        asset_resp = None
        if node.kind == "asset":
            asset = assets_by_id.get(str(spec.get("asset_id") or ""))
            if asset is not None:
                asset_resp = AssetResponse.model_validate(asset)
        node_outputs = sorted(
            (
                outputs_by_id[str(oid)]
                for oid in (spec.get("output_ids") or [])
                if str(oid) in outputs_by_id
            ),
            key=lambda o: o.created_at,
        )
        resp_nodes.append(
            GraphNodeResponse(
                id=node.id,
                kind=node.kind,
                state=node.state,
                spec=spec,
                layout=node.layout or {},
                estimate_credits=estimate_credits,
                asset=asset_resp,
                outputs=[OutputResponse.model_validate(o) for o in node_outputs],
                created_at=node.created_at,
                updated_at=node.updated_at,
            )
        )

    return {
        "nodes": resp_nodes,
        "edges": [GraphEdgeResponse.model_validate(e) for e in edges],
    }


@router.post(
    "/{project_id}/graph/revise",
    response_model=GraphReviseResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def revise_graph_node(
    project_id: UUID,
    request: GraphReviseRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> GraphReviseResponse:
    """The card-face prompt direct edit's deterministic dispatch (ADR-058):
    the revision IS a graph mutation, not a chat turn — ops are constructed
    by CODE (``edit_prompt`` the named node with the user's verbatim program
    + ``run`` the node and its downstream), land through the graph's ONLY
    write door, and the run births through the ONLY birthplace. Zero intent
    recognition (the node id is structurally exact), zero chat messages —
    the node's own state cycle (stale → queued → running → done, the graph
    frame's live read) is the whole feedback, so the run is stamped
    ``origin: node_revise`` for every display surface to stay silent about.
    """
    project = await get_project_for_user(db, project_id, UUID(str(current_user.id)))
    node = await db.get(GraphNode, request.node_id)
    if node is None or UUID(str(node.project_id)) != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Node not found")

    from app.pipeline.graph_revise import tasks_for_graph_nodes
    from app.pipeline.graph_store import WiringRejected, apply_wiring_ops

    try:
        delta = await apply_wiring_ops(
            db,
            project_id,
            [
                {"op": "edit_prompt", "node": str(request.node_id), "prompt": request.prompt},
                {"op": "run", "nodes": [str(request.node_id)]},
            ],
        )
        run_nodes = list(
            (
                await db.execute(
                    select(GraphNode).where(GraphNode.id.in_(delta.run_nodes))
                )
            )
            .scalars()
            .all()
        )
        by_id = {str(n.id): n for n in run_nodes}
        ordered = [by_id[str(nid)] for nid in delta.run_nodes if str(nid) in by_id]
        tasks = tasks_for_graph_nodes(ordered)
        if not tasks:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "The node's subgraph has nothing executable.",
            )
        run = await create_run(
            db,
            project,
            TaskSpec(
                tasks=tasks,
                target_language=first_task_language(tasks) or project.language or "en",
                # The edited program IS the instruction (the writers' steering
                # line) — the same pin as the chat wiring path's.
                instruction=request.prompt,
                scope="full",
            ),
        )
    except CreditsInsufficientError as exc:
        # Same structured shortfall payload as /generate and the chat
        # dispatch (BILLING §7) — the confirm card renders it in place.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "credits.insufficient",
                "balance": exc.balance,
                "required": exc.required,
            },
        ) from exc
    except WiringRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        # Birthplace rejects (active-run guard, requires gates) — 422 as-is.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    run.context = {**(run.context or {}), "origin": "node_revise"}
    project.status = ProjectStatus.PROCESSING
    await db.commit()
    await db.refresh(run)
    return GraphReviseResponse(run_id=run.id, status=run.status)


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
    # operations (journal, NO ACTION on both its FKs) and publications
    # (RESTRICT on output) must go BEFORE outputs; workflow_steps cascade
    # from runs, conversations/messages cascade from the project.
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    for asset in result.scalars().all():
        await delete_file(asset.file_url)

    await db.execute(delete(Operation).where(Operation.project_id == project_id))
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
        await release_run(db, user_id=current_user.id, run_id=rid)
    await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(delete(Asset).where(Asset.project_id == project_id))
    await db.delete(project)
    await db.commit()

    # Remove project upload directory after DB commit
    await delete_project_files(project_id, current_user.id)


@router.post(
    "/{project_id}/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_content(
    project_id: UUID,
    request: GenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> GenerateResponse:
    """Queue background generation for a project.

    Ensures the project-scoped conversation exists so the original prompt is
    persisted, then creates a PENDING WorkflowRun. The background worker claims
    and runs it (see app.worker).
    """
    project = await get_project_for_user(
        db, project_id, UUID(str(current_user.id))
    )

    # Full-scope runs from the composer must provide an explicit task book
    # resolved by POST /chat (ADR-043 — the chain is the only grammar).
    # Targeted scopes (hook/clip/derivative/render) carry no chain — they
    # re-run one node family off target_id.
    if request.tasks is None and request.scope == "full":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task book must be confirmed via the chat book path first.",
        )
    instruction = request.instruction or "Generate content from the uploaded assets."

    # Persist the original prompt in the project-scoped conversation if it is
    # not already there. This is a no-op when the conversation already has messages.
    await seed_project_prompt(db, UUID(str(current_user.id)), project_id, instruction)

    try:
        # Entry constraints (clips-media gate, targeted-scope validity) reject
        # at the birthplace — ValueError here is a client-facing 422.
        task_spec = TaskSpec(
            tasks=request.tasks,
            target_language=(
                request.target_language
                or first_task_language(request.tasks)
                or "en"
            ),
            instruction=instruction,
            tone_settings=(
                request.tone_settings.model_dump() if request.tone_settings else None
            ),
            autonomy=request.autonomy or "auto",
            scope=request.scope,
            operation=request.operation,
            target_id=request.target_id,
        )
        run = await create_run(db, project, task_spec)
    except CreditsInsufficientError as exc:
        # User-level shortfall (ADR-055): the structured 422 the dock's grey
        # row reads (BILLING §7) — strictly two vocabularies with provider
        # 402s. BEFORE the ValueError catch (it subclasses ValueError).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "credits.insufficient",
                "balance": exc.balance,
                "required": exc.required,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    project.status = ProjectStatus.PROCESSING
    # The task book is confirmed now — drop the unconfirmed copy.
    project.pending_brief = None
    # /generate starts the run without a human answer — discard the open
    # task_book question instead of archiving a fabricated answered question.
    await discard_unanswered_task_book(db, UUID(str(current_user.id)), project_id)
    await db.commit()
    await db.refresh(run)

    return GenerateResponse(run_id=run.id, status=run.status)


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
