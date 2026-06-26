"""Clip router for feedback and revision."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.agents.reviser import reviser_agent
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep
from app.models.schemas import (
    ClipResponse,
    ClipScript,
    ClipUpdate,
    FeedbackRequest,
    RenderStatus,
    Segment,
    SpeakerPersona,
)
from app.models.tables import Clip, HumanFeedback, Project, Speaker

router = APIRouter()


@router.post(
    "/{clip_id}/feedback",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    clip_id: UUID,
    feedback: FeedbackRequest,
    db: DBDep,
) -> dict:
    """Submit human feedback for a clip."""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip not found",
        )

    record = HumanFeedback(
        clip_id=clip_id,
        scope=feedback.scope.value,
        reason=feedback.reason.value,
        detail=feedback.detail,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {
        "feedback_id": str(record.id),
        "clip_id": str(clip_id),
        "scope": feedback.scope.value,
        "reason": feedback.reason.value,
    }


@router.post("/{clip_id}/revise", response_model=ClipResponse)
async def revise_clip(
    clip_id: UUID,
    feedback: FeedbackRequest,
    db: DBDep,
) -> Clip:
    """Revise a clip based on feedback and return the updated clip."""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip not found",
        )

    result = await db.execute(select(Project).where(Project.id == clip.project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    result = await db.execute(select(Speaker).where(Speaker.id == project.speaker_id))
    speaker = result.scalar_one_or_none()

    # Parse existing script and source segment
    try:
        current_script = ClipScript.model_validate(clip.script)
        source_segment = (
            Segment.model_validate(clip.source_segment)
            if clip.source_segment
            else None
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid clip data: {e}",
        ) from e

    if not source_segment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip has no source segment to revise from",
        )

    persona = None
    if speaker is not None and speaker.persona:
        persona = SpeakerPersona.model_validate(speaker.persona)

    # Persist feedback first
    record = HumanFeedback(
        clip_id=clip_id,
        scope=feedback.scope.value,
        reason=feedback.reason.value,
        detail=feedback.detail,
    )
    db.add(record)

    try:
        revised_script = await reviser_agent.revise(
            script=current_script,
            segment=source_segment,
            feedback=feedback,
            persona=persona,
        )
    except MiniMaxError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    clip.script = revised_script.model_dump()
    clip.hook = revised_script.hook
    clip.title_options = revised_script.title_options
    clip.music_mood = revised_script.music_mood
    clip.duration = revised_script.duration_seconds
    clip.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(clip)
    return clip


@router.post(
    "/{clip_id}/render",
    response_model=ClipResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def render_clip(clip_id: UUID, db: DBDep) -> Clip:
    """Queue this clip for video rendering (worker claims render_status=PENDING)."""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip not found",
        )
    if not clip.render_spec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip has no render_spec (text-only project — no source video)",
        )
    clip.render_status = RenderStatus.PENDING
    clip.render_error = None
    await db.commit()
    await db.refresh(clip)
    return clip


@router.put("/{clip_id}", response_model=ClipResponse)
async def update_clip(
    clip_id: UUID,
    data: ClipUpdate,
    db: DBDep,
) -> Clip:
    """Directly edit a clip (hook, script, title options, music mood)."""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "script" and value is not None:
            setattr(clip, field, value.model_dump())
        elif value is not None:
            setattr(clip, field, value)

    # Keep the nested script object in sync with top-level fields.
    script_dict = dict(clip.script) if isinstance(clip.script, dict) else clip.script.model_dump()
    if data.hook is not None:
        script_dict["hook"] = data.hook
    if data.title_options is not None:
        script_dict["title_options"] = data.title_options
    if data.music_mood is not None:
        script_dict["music_mood"] = data.music_mood
    clip.script = script_dict

    # Sync top-level hook/duration/music_mood if script was updated
    if data.script is not None:
        clip.hook = data.script.hook
        clip.music_mood = data.script.music_mood
        clip.duration = data.script.duration_seconds

    clip.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(clip)
    return clip
