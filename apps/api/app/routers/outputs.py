"""Outputs router: the unified product API (ADR-030).

Replaces the retired /clips and /derivatives routers. Clip-specific actions
(render / cover / translate-captions / dub / revise) live as sub-paths on the
output id; regeneration for any type goes through the chat layer.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.agents.reviser import reviser_agent
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    AssetType,
    ChatRequest,
    ClipSpec,
    DubRequest,
    FeedbackRequest,
    OutputResponse,
    RenderStatus,
    TranslateCaptionsRequest,
    validate_output_payload,
)
from app.models.tables import Asset, Output, Project, User
from app.services.caption_translate import translate_caption_track
from app.services.chat import chat
from app.services.node_runners import generate_clip_cover_image
from app.services.project_context import (
    DEMO_PROJECT_ID,
    resolve_clip_for_revision,
    resolve_speaker,
    speaker_context_from_row,
)
from app.services.storage import download_to_temp, get_output_path, output_url, save
from app.services.voice import clone_voice, extract_audio, synthesize

router = APIRouter()

CLIP_TYPES = {"clip"}
DERIVATIVE_TYPES = {"post", "quotes", "carousel", "article"}


async def _get_output_for_user(
    db: AsyncSession,
    output_id: UUID,
    user_id: UUID | None,
) -> Output:
    """Fetch an output and ensure it belongs to the given user or is the demo."""
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
    if project.id == DEMO_PROJECT_ID:
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
    """Partial update for an output (editor save / content edit)."""

    payload: dict | None = None
    status: str | None = None
    render_spec: ClipSpec | None = None
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
    """Update an output's editable fields (payload / render_spec / publishing)."""
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))

    if data.payload is not None:
        output.payload = validate_output_payload(output.type, data.payload)
    if data.status is not None:
        output.status = data.status
    if data.render_spec is not None:
        output.render_spec = data.render_spec.model_dump(mode="json")
    if data.publishing is not None:
        output.publishing = {**(output.publishing or {}), **data.publishing}
    output.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(output)
    return output


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

    speaker = await resolve_speaker(db, project)
    payload = output.payload or {}

    try:
        revised = await reviser_agent.revise(
            clip_hook=payload.get("hook", ""),
            clip_duration=payload.get("duration", 30),
            clip_title_options=payload.get("title_options") or [],
            clip_music_mood=payload.get("music_mood", "calm"),
            segment=source_segment,
            feedback=feedback,
            speaker=speaker_context_from_row(speaker),
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
    first. Stays word-level (see services.caption_translate) and updates the
    spec's ``target_language`` in place.
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

    # Reassign a NEW dict so SQLAlchemy flushes the JSON column (no in-place mutation).
    output.render_spec = {
        **spec,
        "caption_track": new_track,
        "target_language": data.target_language,
    }
    output.updated_at = datetime.now(UTC)
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
    """Voice-clone dub the clip into ``target_language`` (speaker's own voice).

    Clones from the project's voice sample (VOICE_SAMPLE > AUDIO > VIDEO audio),
    translates the captions, synthesizes the dub via MiniMax T2A, and bakes a
    ``dub`` track into ``render_spec`` — the renderer then mutes the source audio
    and plays the dub (overlay; no lip-sync). GDPR set aside for MVP.
    """
    output = _require_clip(
        await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    )

    project = await db.get(Project, output.project_id)
    if project is None or project.user_id != UUID(str(current_user.id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")

    spec = output.render_spec
    if not isinstance(spec, dict):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Clip has no render_spec (text-only project)"
        )
    track = spec.get("caption_track") or []
    if not track:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Clip has no captions to dub")

    # Voice sample priority: explicit voice sample > talk audio > talk video.
    assets = list(
        (
            await db.execute(select(Asset).where(Asset.project_id == output.project_id))
        ).scalars()
    )
    sample = (
        next((a for a in assets if a.type == AssetType.VOICE_SAMPLE and a.file_url), None)
        or next(
            (
                a
                for a in assets
                if a.type == AssetType.AUDIO and a.file_url and (a.meta or {}).get("words")
            ),
            None,
        )
        or next((a for a in assets if a.type == AssetType.VIDEO and a.file_url), None)
    )
    if sample is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No voice sample — upload audio/video (or a voice sample) to dub",
        )
    src_path = await download_to_temp(sample.file_url)
    if src_path is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Voice sample file missing")

    tmp_audio_path = None
    try:
        # Reuse a cached cloned voice (MiniMax clones are ~168h temporary).
        voice_id = (sample.meta or {}).get("voice_id")
        if not voice_id:
            audio_path = src_path
            if sample.type == AssetType.VIDEO:
                tmp_audio_path = await run_in_threadpool(extract_audio, src_path)
                if tmp_audio_path is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        "Could not extract audio from the video for voice cloning",
                    )
                audio_path = tmp_audio_path
            voice_id = await run_in_threadpool(clone_voice, audio_path)
            if not voice_id:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Voice cloning unavailable")
            sample.meta = {**(sample.meta or {}), "voice_id": voice_id}

        new_track = await translate_caption_track(track, data.target_language)
        text = " ".join(str(c.get("text", "")).strip() for c in new_track).strip()
        audio_bytes = await run_in_threadpool(synthesize, text, voice_id, data.target_language)
    except MiniMaxError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    finally:
        if tmp_audio_path is not None:
            tmp_audio_path.unlink(missing_ok=True)
        if src_path is not None:
            src_path.unlink(missing_ok=True)

    out_key = str(
        get_output_path(
            output.project_id,
            project.user_id,
            f"{output_id}_dub_{data.target_language}.mp3",
        )
    )
    out_key = await save(out_key, audio_bytes)

    # Reassign a NEW dict so SQLAlchemy flushes the JSON column.
    output.render_spec = {
        **spec,
        "caption_track": new_track,
        "target_language": data.target_language,
        "dub": {"url": output_url(out_key), "enabled": True, "gain_db": 0.0},
    }
    output.updated_at = datetime.now(UTC)
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
        "job_id": str(result.job_id) if result.job_id else None,
        "message_id": str(result.assistant_message.id),
        "session_id": str(result.session_id),
    }
