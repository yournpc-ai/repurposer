"""Voice-clone dub pipeline — shared by the sync endpoint and the run runner.

Clones from the project's voice sample (VOICE_SAMPLE > AUDIO with words >
VIDEO audio), translates the captions, synthesizes via MiniMax T2A, and
returns the new render_spec dict (dub track baked in — the renderer mutes
the source audio and plays the dub; overlay, no lip-sync).

Error contract (agent-loop-upgrade W3): missing/invalid inputs raise
HTTPException (deterministic, per-clip skippable); provider / storage hiccups
raise TransientNodeError — each shell translates (run runner: step-level
retry; editor endpoint: 502).
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.clients.minimax import MiniMaxError
from app.models.schemas import AssetType
from app.models.tables import Asset, Output, Project
from app.pipeline.errors import TransientNodeError
from app.tools.caption_translate import translate_caption_track
from app.tools.storage import download_to_temp, get_output_path, output_url, save
from app.tools.voice import clone_voice, extract_audio, synthesize


async def synthesize_dub(
    db: AsyncSession,
    output: Output,
    project: Project,
    target_language: str,
) -> dict:
    """Dub ``output`` into ``target_language`` with the cloned voice; returns
    the new render_spec. Raises HTTPException on missing inputs/provider errors."""
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
                raise TransientNodeError("voice cloning unavailable (provider returned no voice_id)")
            sample.meta = {**(sample.meta or {}), "voice_id": voice_id}

        new_track = await translate_caption_track(track, target_language)
        text = " ".join(str(c.get("text", "")).strip() for c in new_track).strip()
        audio_bytes = await run_in_threadpool(synthesize, text, voice_id, target_language)
    except MiniMaxError as e:
        raise TransientNodeError(f"dub provider call failed: {e}") from e
    finally:
        if tmp_audio_path is not None:
            tmp_audio_path.unlink(missing_ok=True)
        if src_path is not None:
            src_path.unlink(missing_ok=True)

    out_key = str(
        await get_output_path(
            output.project_id,
            project.user_id,
            f"{output.id}_dub_{target_language}.mp3",
        )
    )
    try:
        out_key = await save(out_key, audio_bytes)
    except Exception as e:  # storage layer raises plain network/IO errors
        raise TransientNodeError(f"dub audio upload failed: {e}") from e

    return {
        **spec,
        "caption_track": new_track,
        "target_language": target_language,
        "dub": {"url": output_url(out_key), "enabled": True, "gain_db": 0.0},
    }
