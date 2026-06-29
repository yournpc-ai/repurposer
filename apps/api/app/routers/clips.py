"""Clip router for feedback and revision."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.agents.reviser import reviser_agent
from app.clients.minimax import MiniMaxError
from app.config import settings
from app.dependencies import DBDep
from app.models.schemas import (
    AssetType,
    ClipResponse,
    ClipScript,
    ClipUpdate,
    DubRequest,
    FeedbackRequest,
    RenderStatus,
    Segment,
    SpeakerPersona,
    TranslateCaptionsRequest,
)
from app.models.tables import Asset, Clip, HumanFeedback, Project, Speaker
from app.services.caption_translate import translate_caption_track
from app.services.storage import get_output_path, output_url, resolve_file_path
from app.services.voice import clone_voice, extract_audio, synthesize

router = APIRouter()


@router.get("/{clip_id}", response_model=ClipResponse)
async def get_clip(clip_id: UUID, db: DBDep) -> Clip:
    """Get a single clip (editor load + render-status polling)."""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip not found",
        )
    return clip


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


@router.post("/{clip_id}/translate-captions", response_model=ClipResponse)
async def translate_captions(
    clip_id: UUID,
    data: TranslateCaptionsRequest,
    db: DBDep,
) -> Clip:
    """Re-translate the clip's caption track into ``target_language``.

    Operates on the persisted ``render_spec``, so the editor saves pending edits
    first. Stays word-level (see services.caption_translate) and updates the
    spec's ``target_language`` in place.
    """
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip not found",
        )

    spec = clip.render_spec
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
    clip.render_spec = {
        **spec,
        "caption_track": new_track,
        "target_language": data.target_language,
    }
    clip.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(clip)
    return clip


@router.post("/{clip_id}/dub", response_model=ClipResponse)
async def dub_clip(clip_id: UUID, data: DubRequest, db: DBDep) -> Clip:
    """Voice-clone dub the clip into ``target_language`` (speaker's own voice).

    Clones from the project's voice sample (VOICE_SAMPLE > AUDIO > VIDEO audio),
    translates the captions, synthesizes the dub via MiniMax T2A, and bakes a
    ``dub`` track into ``render_spec`` — the renderer then mutes the source audio
    and plays the dub (overlay; no lip-sync). GDPR set aside for MVP.
    """
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clip not found")

    spec = clip.render_spec
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
            await db.execute(select(Asset).where(Asset.project_id == clip.project_id))
        ).scalars()
    )
    sample = (
        next((a for a in assets if a.type == AssetType.VOICE_SAMPLE and a.file_url), None)
        or next((a for a in assets if a.type == AssetType.AUDIO and a.file_url), None)
        or next((a for a in assets if a.type == AssetType.VIDEO and a.file_url), None)
    )
    if sample is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No voice sample — upload audio/video (or a voice sample) to dub",
        )
    src_path = resolve_file_path(sample.file_url)
    if src_path is None or not src_path.is_file():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Voice sample file missing")

    try:
        # Reuse a cached cloned voice (MiniMax clones are ~168h temporary).
        voice_id = (sample.meta or {}).get("voice_id")
        if not voice_id:
            audio_path = src_path
            tmp = None
            if sample.type == AssetType.VIDEO:
                tmp = await run_in_threadpool(extract_audio, src_path)
                if tmp is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        "Could not extract audio from the video for voice cloning",
                    )
                audio_path = tmp
            voice_id = await run_in_threadpool(clone_voice, audio_path)
            if tmp is not None:
                tmp.unlink(missing_ok=True)
            if not voice_id:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Voice cloning unavailable")
            sample.meta = {**(sample.meta or {}), "voice_id": voice_id}

        new_track = await translate_caption_track(track, data.target_language)
        text = " ".join(str(c.get("text", "")).strip() for c in new_track).strip()
        audio_bytes = await run_in_threadpool(synthesize, text, voice_id, data.target_language)
    except MiniMaxError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    out_path = get_output_path(clip.project_id, f"{clip_id}_dub_{data.target_language}.mp3")
    out_path.write_bytes(audio_bytes)
    rel = str(out_path.relative_to(settings.output_dir))

    # Reassign a NEW dict so SQLAlchemy flushes the JSON column.
    clip.render_spec = {
        **spec,
        "caption_track": new_track,
        "target_language": data.target_language,
        "dub": {"url": output_url(rel), "enabled": True, "gain_db": 0.0},
    }
    clip.updated_at = datetime.now(UTC)
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
