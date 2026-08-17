"""Outputs router: the unified product API (ADR-030).

Replaces the retired /clips and /derivatives routers. Clip-specific actions
(render / cover / translate-captions / dub / revise) live as sub-paths on the
output id; regeneration for any type goes through the chat layer.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.revise.agents import reviser
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    ChatRequest,
    DubRequest,
    FeedbackRequest,
    OutputResponse,
    RenderStatus,
    TranslateCaptionsRequest,
    validate_output_payload,
)
from app.models.tables import Output, Project, User
from app.skills.captions.procedure import translate_caption_track
from app.chat.service import chat
from app.operations.service import apply_precomputed
from app.pipeline.images import generate_clip_cover_image
from app.platform.project_context import (
    resolve_clip_for_revision,
    persona_context_from_row,
    resolve_persona,
)
from app.skills.dub.procedure import synthesize_dub
from app.pipeline.errors import TransientNodeError, user_error_line
from app.tools.storage import delete_file
from app.ui_locale import current_ui_language

router = APIRouter()

CLIP_TYPES = {"clip"}
DERIVATIVE_TYPES = {"post", "quotes", "carousel", "article"}


async def _get_output_for_user(
    db: AsyncSession,
    output_id: UUID,
    user_id: UUID | None,
) -> Output:
    """Fetch an output and ensure it belongs to the given user."""
    output = await db.get(Output, output_id)
    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output not found",
        )
    project = await db.get(Project, output.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if user_id is not None and project.user_id == user_id:
        return output
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied",
    )


def _require_clip(output: Output) -> Output:
    if output.type != "clip":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This action is only valid for clip outputs",
        )
    return output


class OutputUpdate(BaseModel):
    """Partial update for an output (content edit).

    render_spec edits do NOT come through here — they go through the
    operations API (ADR-032: every render_spec write journals an operation).
    """

    model_config = ConfigDict(extra="forbid")

    payload: dict | None = None
    status: str | None = None
    publishing: dict | None = None


@router.get("/{output_id}", response_model=OutputResponse)
async def get_output(
    output_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> Output:
    """Get a single output (editor load + render-status polling)."""
    return await _get_output_for_user(
        db, output_id, UUID(str(current_user.id)) if current_user else None
    )


@router.put("/{output_id}", response_model=OutputResponse)
async def update_output(
    output_id: UUID,
    data: OutputUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Output:
    """Update an output's editable fields (payload / status / publishing)."""
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))

    if data.payload is not None:
        output.payload = validate_output_payload(output.type, data.payload)
    if data.status is not None:
        output.status = data.status
    if data.publishing is not None:
        output.publishing = {**(output.publishing or {}), **data.publishing}
    output.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(output)
    return output


@router.delete("/{output_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output(
    output_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete a product output — the row plus its produced storage objects
    (video/srt/image keys + the cover). Deleting is idempotent at the storage
    layer (S3 delete never 404s); derived fork rows are independent renders
    and survive their source's deletion."""
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    files = output.files or {}
    for key in (files.get("video"), files.get("srt"), files.get("image")):
        await delete_file(key)
    await delete_file((output.publishing or {}).get("cover_image_url"))
    await db.delete(output)
    await db.commit()


@router.post("/{output_id}/revise", response_model=OutputResponse)
async def revise_output(
    output_id: UUID,
    feedback: FeedbackRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Output:
    """Revise a clip output based on feedback and return the updated output."""
    output = _require_clip(
        await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    )

    project = await db.get(Project, output.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    try:
        output, source_segment = await resolve_clip_for_revision(
            db, output_id, UUID(str(project.id))
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    persona = await resolve_persona(db, project)
    payload = output.payload or {}

    try:
        revised = await reviser.call(
            clip_hook=payload.get("hook", ""),
            clip_duration=payload.get("duration", 30),
            clip_title_options=payload.get("title_options") or [],
            clip_music_mood=payload.get("music_mood", "calm"),
            segment=source_segment,
            feedback=feedback,
            persona=persona_context_from_row(persona),
        )
    except MiniMaxError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    output.payload = validate_output_payload(
        "clip",
        {
            "hook": revised.hook,
            "title_options": revised.title_options,
            "music_mood": revised.music_mood,
            "duration": revised.duration_seconds,
        },
    )
    output.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(output)
    return output


@router.post(
    "/{output_id}/render",
    response_model=OutputResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def render_output_endpoint(
    output_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Output:
    """Queue this clip for video rendering (worker claims render_status=PENDING)."""
    output = _require_clip(
        await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    )
    if not output.render_spec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip has no render_spec (text-only project — no source video)",
        )
    output.render_status = RenderStatus.PENDING
    output.render_error = None
    await db.commit()
    await db.refresh(output)
    return output


@router.post("/{output_id}/cover", response_model=OutputResponse)
async def generate_output_cover(
    output_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Output:
    """Generate a cover image for a clip on demand.

    The image is created only when requested by the UI to avoid paying
    image-generation costs for every clip.
    """
    output = _require_clip(
        await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    )

    project = await db.get(Project, output.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    publishing = output.publishing or {}
    image_url = await generate_clip_cover_image(
        output.id,
        project,
        topic=publishing.get("topic"),
        title=publishing.get("title"),
    )
    if image_url is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cover image generation failed",
        )

    output.publishing = {**publishing, "cover_image_url": image_url}
    output.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(output)
    return output


@router.post("/{output_id}/translate-captions", response_model=OutputResponse)
async def translate_captions(
    output_id: UUID,
    data: TranslateCaptionsRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Output:
    """Re-translate the clip's caption track into ``target_language``.

    Operates on the persisted ``render_spec``, so the editor saves pending edits
    first. Stays word-level (the captions skill's translation procedure) and
    updates the spec's ``target_language`` in place.
    """
    output = _require_clip(
        await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    )

    spec = output.render_spec
    if not isinstance(spec, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip has no render_spec (text-only project — no source video)",
        )
    track = spec.get("caption_track") or []
    if not track:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip has no captions to translate",
        )

    try:
        new_track = await translate_caption_track(track, data.target_language)
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    # Journal the operation (ADR-032): every render_spec write goes through
    # the operations service — this is what makes the edit undoable.
    new_spec = {
        **spec,
        "caption_track": new_track,
        "target_language": data.target_language,
    }
    await apply_precomputed(
        db,
        output,
        "translate_captions",
        {"target_language": data.target_language},
        new_spec,
        source="editor",
        user_id=UUID(str(current_user.id)),
    )
    await db.commit()
    await db.refresh(output)
    return output


@router.post("/{output_id}/dub", response_model=OutputResponse)
async def dub_output(
    output_id: UUID,
    data: DubRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Output:
    """Voice-clone dub the clip into ``target_language`` (the persona's own voice).

    Pipeline lives in ``skills/dub/procedure.py`` (shared with the dub_clip
    run runner); the endpoint additionally journals the operation (ADR-032).
    """
    output = _require_clip(
        await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    )
    project = await db.get(Project, output.project_id)
    if project is None or project.user_id != UUID(str(current_user.id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")

    # Shell translation (agent-loop-upgrade W3): the core speaks
    # TransientNodeError for provider/storage hiccups; the endpoint's contract
    # is HTTP — map to 502. The toast shows the detail, so it gets the
    # humanized line (request-scoped UI locale), never raw provider innards.
    # Deterministic input errors stay HTTPException.
    try:
        new_spec = await synthesize_dub(db, output, project, data.target_language)
    except TransientNodeError as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            user_error_line(e, current_ui_language() or "en"),
        ) from e
    await apply_precomputed(
        db,
        output,
        "set_dub",
        {"enabled": True, "gain_db": 0.0, "target_language": data.target_language},
        new_spec,
        source="editor",
        user_id=UUID(str(current_user.id)),
    )
    await db.commit()
    await db.refresh(output)
    return output


class OutputRegenerateRequest(BaseModel):
    """Request to regenerate an output with an optional instruction."""

    instruction: str | None = Field(
        default=None,
        description="Steering prompt for the regeneration.",
    )
    target_language: str = Field(
        default="en",
        description="Target language code, e.g. en/zh/fr/de/es/it",
    )


@router.post("/{output_id}/regenerate", response_model=dict)
async def regenerate_output(
    output_id: UUID,
    data: OutputRegenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Queue regeneration of a single output through the generic chat layer."""
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    if output.type not in CLIP_TYPES | DERIVATIVE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Output type {output.type} is not regenerable",
        )

    project = await db.get(Project, output.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    result = await chat(
        db,
        UUID(str(current_user.id)),
        ChatRequest(
            project_id=UUID(str(project.id)),
            asset_id=output_id,
            asset_type="clip" if output.type == "clip" else "derivative",
            message=data.instruction or f"Regenerate this {output.type}",
        ),
    )

    return {
        "run_id": str(result.run_id) if result.run_id else None,
        "message_id": str(result.assistant_message.id),
        "conversation_id": str(result.conversation_id),
    }
