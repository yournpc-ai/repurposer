"""Dub tool's private procedure — the voice-clone dub orchestration, shared
by the sync endpoint and the run runner (relocated from tools/dub/dubbing.py,
which now holds only the cue-aligned synthesis mechanics, N-29).

Clones from the project's voice sample (VOICE_SAMPLE > AUDIO with words >
VIDEO audio), translates the captions (persona register injected,
2026-08-07), synthesizes via the aligned-track mechanics, and returns the new
render_spec dict (dub track baked in — the renderer mutes the source audio
and plays the dub; overlay, no lip-sync).

Error contract (agent-loop-upgrade W3): missing/invalid inputs raise
HTTPException (deterministic, per-clip skippable); provider / storage hiccups
raise TransientNodeError — each shell translates (run runner: step-level
retry; editor endpoint: 502).
"""

from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.providers.llm.minimax import MiniMaxError
from app.models.schemas import AssetType
from app.models.tables import Asset, GraphNode, Output, Persona, Project
from app.metering import record_media_usage
from app.pipeline.errors import TransientNodeError, propagate_key
from app.tools.captions.procedure import (
    TRANSLATION_ARTIFACT_KEY,
    build_translation_cues,
    find_reusable_translation,
    spread_translation_cues,
    translate_text,
    translation_source_hash,
)
from app.tools.dub.dubbing import DubAssemblyError, synthesize_aligned_track
from app.providers.storage import download_to_temp, get_output_path, output_url, save
from app.providers.voice import VoiceError, clone_voice, extract_audio

logger = structlog.get_logger()


def _persona_style_hint(persona: Persona | None) -> str | None:
    """Compact persona register for the translation prompt (sentence style /
    tone / avoid-words — concision-friendly fields only)."""
    if persona is None:
        return None
    parts = [
        p
        for p in [
            f"sentence style: {persona.sentence_style}" if persona.sentence_style else None,
            f"emotional tone: {persona.emotional_tone}" if persona.emotional_tone else None,
            (
                f"avoid these words: {', '.join(persona.avoid_words)}"
                if persona.avoid_words
                else None
            ),
        ]
        if p
    ]
    return "; ".join(parts) or None


async def translate_dub_script(
    db: AsyncSession,
    output: Output,
    track: list[dict[str, Any]],
    title_text: str,
    target_language: str,
    style_hint: str | None,
    *,
    graph_node_id: Any = None,
) -> tuple[list[dict[str, Any]], str]:
    """The dub DOCUMENT station (ADR-072 批 A2 接缝): the translated script
    as unit cue rows + the translated title. The rows are the reusable
    artifact — cached on the graph node's ``spec.translation`` keyed by the
    source hash (source cue times+words + title + language + persona style
    hint); a hit (including USER-EDITED rows — the edit is the content)
    skips the translator entirely. ``graph_node_id=None`` (the editor sync
    endpoint) always translates fresh. Raises MiniMaxError on provider
    failure (the caller maps it onto the error contract)."""
    source_hash = translation_source_hash(track, title_text, target_language, style_hint)
    artifact = None
    if graph_node_id is not None:
        gnode = await db.get(GraphNode, graph_node_id)
        artifact = (gnode.spec or {}).get(TRANSLATION_ARTIFACT_KEY) if gnode else None
    cached = find_reusable_translation(artifact, str(output.id), source_hash)
    if cached is not None:
        return cached["rows"], str((cached.get("title") or {}).get("text") or "")

    rows = await build_translation_cues(track, target_language, style_hint=style_hint)
    # The title card is part of the spec too — a dubbed clip with an
    # untranslated title reads broken (2026-08-09, dub contrast pack).
    new_title_text = (
        await translate_text(title_text, target_language, style_hint=style_hint)
        if title_text
        else ""
    )
    if graph_node_id is not None:
        from app.pipeline.graph_fill import (  # deferred: import cycle
            merge_translation_artifact,
        )

        await merge_translation_artifact(
            graph_node_id,
            {
                str(output.id): {
                    "source_hash": source_hash,
                    "title": (
                        {"source": title_text, "text": new_title_text} if title_text else None
                    ),
                    "rows": rows,
                }
            },
        )
    return rows, new_title_text


async def synthesize_dub(
    db: AsyncSession,
    output: Output,
    project: Project,
    target_language: str,
    *,
    graph_node_id: Any = None,
) -> dict[str, Any]:
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
                raise TransientNodeError(
                    "voice cloning unavailable (provider returned no voice_id)",
                    user_key="voice_unavailable",
                )
            # Billed on first T2A use of the fresh voice (provider rule) — the
            # clone immediately synthesizes below, so the charge lands here.
            await record_media_usage({"voice_clones": 1.0})
            sample.meta = {**(sample.meta or {}), "voice_id": voice_id}

        persona = (
            await db.get(Persona, project.persona_id) if project.persona_id else None
        )
        style_hint = _persona_style_hint(persona)
        title = spec.get("title") or {}
        title_text = str(title.get("text") or "").strip()
        title_src = title_text if title.get("enabled") and title_text else ""
        rows, new_title_text = await translate_dub_script(
            db,
            output,
            track,
            title_src,
            target_language,
            style_hint,
            graph_node_id=graph_node_id,
        )
        new_track = spread_translation_cues(rows, target_language)

        # Synthesis units = the translation rows directly (the seam's unit
        # spans ARE the fit windows — the retired spread→re-chunk double
        # grouping derived the same union but with boundaries smeared across
        # row edges).
        units = [
            {"text": str(r["text"]), "start": float(r["start"]), "end": float(r["end"])}
            for r in rows
            if str(r["text"]).strip()
        ]
        if not units:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Clip has no captions to dub")
        audio_bytes, ext, sped_up, total_end = await synthesize_aligned_track(
            units, voice_id, target_language, spec.get("segments")
        )
        logger.info(
            "dub_aligned",
            output_id=str(output.id),
            target_language=target_language,
            units=len(units),
            sped_up=sped_up,
            duration_s=round(total_end, 2),
            encoder=ext,
        )
    except (MiniMaxError, VoiceError, DubAssemblyError) as e:
        raise TransientNodeError(
            f"dub provider call failed: {e}", user_key=propagate_key(e, "voice_unavailable")
        ) from e
    finally:
        if tmp_audio_path is not None:
            tmp_audio_path.unlink(missing_ok=True)
        if src_path is not None:
            src_path.unlink(missing_ok=True)

    out_key = str(
        await get_output_path(
            output.project_id,
            project.user_id,
            f"{output.id}_dub_{target_language}.{ext}",
        )
    )
    try:
        out_key = await save(out_key, audio_bytes)
    except Exception as e:  # storage layer raises plain network/IO errors
        raise TransientNodeError(
            f"dub audio upload failed: {e}", user_key="storage_unavailable"
        ) from e

    return {
        **spec,
        "caption_track": new_track,
        "title": {**title, "text": new_title_text} if new_title_text else title,
        "target_language": target_language,
        "dub": {"url": output_url(out_key), "enabled": True, "gain_db": 0.0},
    }
