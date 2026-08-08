"""Voice-clone dub pipeline — shared by the sync endpoint and the run runner.

Clones from the project's voice sample (VOICE_SAMPLE > AUDIO with words >
VIDEO audio), translates the captions (persona register injected,
2026-08-07), synthesizes via MiniMax T2A, and returns the new render_spec
dict (dub track baked in — the renderer mutes the source audio and plays the
dub; overlay, no lip-sync).

**Cue-aligned synthesis (dub 生产级, 2026-08-07)**: the free-running
whole-clip TTS (voice drifting away from the burned captions within seconds)
is retired. Each translation unit (~10 words) is synthesized separately and
fitted to its source-time window — pass 1 at speed 1.0, measured via decode,
and if it overruns its window (window = source span + a capped bite of the
following pause) it is re-synthesized at the provider's voice-level speed
(≤1.35×, natural range — no pitch shift). Units are then placed at their cue
start times on a silent timeline; later units overwrite rare overlaps.

Error contract (agent-loop-upgrade W3): missing/invalid inputs raise
HTTPException (deterministic, per-clip skippable); provider / storage hiccups
raise TransientNodeError — each shell translates (run runner: step-level
retry; editor endpoint: 502).
"""

import asyncio
import io
from typing import Any

import numpy as np
import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.clients.minimax import MiniMaxError
from app.models.schemas import AssetType
from app.models.tables import Asset, Output, Persona, Project
from app.pipeline.errors import TransientNodeError
from app.tools.caption_translate import translate_caption_track, translate_text
from app.tools.storage import download_to_temp, get_output_path, output_url, save
from app.tools.voice import clone_voice, extract_audio, synthesize

logger = structlog.get_logger()

_UNIT_WORDS = 10  # synthesis unit granularity (mirrors caption_translate)
_RATE = 32000  # MiniMax T2A output sample rate (audio_setting)
_GAP_ALLOW_S = 0.8  # a unit may eat this much of the following pause
_SPEED_MAX = 1.35  # fastest re-synthesis (beyond = unnatural speech)
_TAIL_PAD_S = 0.5  # silence appended after the last unit
_TTS_CONCURRENCY = 4  # bounded parallel unit synthesis


def _group_units(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chunk word-level cues into timed synthesis units (~``_UNIT_WORDS`` each)."""
    units: list[dict[str, Any]] = []
    for i in range(0, len(cues), _UNIT_WORDS):
        chunk = cues[i : i + _UNIT_WORDS]
        text = " ".join(str(c.get("text", "")).strip() for c in chunk).strip()
        if not text:
            continue
        units.append(
            {
                "text": text,
                "start": float(chunk[0]["start"]),
                "end": float(chunk[-1]["end"]),
            }
        )
    return units


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


def _clip_time_mapper(segments: list[dict[str, Any]] | None) -> Any:
    """Map source-video time → clip time. The renderer cuts hidden segments and
    concatenates the kept ones, so the dub must be placed in CLIP time (a cue at
    source 37.7s with the clip starting at segment 37.74s sits at dub t≈0)."""
    spans: list[tuple[float, float, float]] = []  # (src_start, src_end, clip_offset)
    acc = 0.0
    for s in segments or []:
        if s.get("hidden"):
            continue
        a, b = float(s["start"]), float(s["end"])
        spans.append((a, b, acc))
        acc += max(0.0, b - a)

    def map_t(t: float) -> float:
        if not spans:
            return t
        for a, b, off in spans:
            if a <= t <= b:
                return off + (t - a)
        # Outside any kept span (rounding / cut edge): clamp to the nearest edge.
        if t < spans[0][0]:
            return spans[0][2]
        return spans[-1][2] + (spans[-1][1] - spans[-1][0])

    return map_t


def _decode_mp3(data: bytes) -> "np.ndarray":
    """Decode MP3 bytes to mono s16 PCM at ``_RATE`` (PyAV, no system ffmpeg)."""
    import av

    chunks: list[np.ndarray] = []
    with av.open(io.BytesIO(data)) as inp:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=_RATE)
        for frame in inp.decode(audio=0):
            for r in resampler.resample(frame):
                chunks.append(r.to_ndarray().reshape(-1))
        for r in resampler.resample(None):
            chunks.append(r.to_ndarray().reshape(-1))
    if not chunks:
        raise MiniMaxError("dub unit decoded to zero samples")
    return np.concatenate(chunks).astype(np.int16)


def _encode_audio(pcm: np.ndarray) -> tuple[bytes, str]:
    """Encode mono s16 PCM to (bytes, ext) — mp3 preferred, wav fallback."""
    import av

    for fmt, codec, ext in (("mp3", "libmp3lame", "mp3"), ("wav", "pcm_s16le", "wav")):
        buf = io.BytesIO()
        try:
            with av.open(buf, mode="w", format=fmt) as out:
                stream = out.add_stream(codec, rate=_RATE)
                for i in range(0, len(pcm), 4096):
                    frame = av.AudioFrame.from_ndarray(
                        pcm[i : i + 4096].reshape(1, -1), format="s16", layout="mono"
                    )
                    frame.sample_rate = _RATE
                    for packet in stream.encode(frame):
                        out.mux(packet)
                for packet in stream.encode(None):
                    out.mux(packet)
            return buf.getvalue(), ext
        except Exception as e:  # codec unavailable in this PyAV build
            logger.warning("dub_encode_fallback", format=fmt, error=str(e))
    raise MiniMaxError("no usable audio encoder for dub assembly")


async def _synthesize_fit_unit(
    unit: dict[str, Any],
    gap_s: float,
    voice_id: str,
    target_language: str,
    sem: asyncio.Semaphore,
) -> tuple[float, "np.ndarray", bool]:
    """Synthesize one unit and fit it to its source-time window.

    Returns (start_seconds, pcm, was_sped_up). Pass 1 at speed 1.0; when the
    measured duration overruns the window (span + capped pause bite), pass 2
    re-synthesizes at the provider speed that fits (≤``_SPEED_MAX``).
    """
    window = max(0.2, (unit["end"] - unit["start"]) + min(max(gap_s, 0.0), _GAP_ALLOW_S))
    async with sem:
        audio = await run_in_threadpool(synthesize, unit["text"], voice_id, target_language)
    pcm = await run_in_threadpool(_decode_mp3, audio)
    duration = len(pcm) / _RATE
    if duration > window * 1.05:
        speed = min(duration / window, _SPEED_MAX)
        async with sem:
            audio = await run_in_threadpool(
                synthesize, unit["text"], voice_id, target_language, speed
            )
        pcm = await run_in_threadpool(_decode_mp3, audio)
        return unit["start"], pcm, True
    return unit["start"], pcm, False


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
                raise TransientNodeError(
                    "voice cloning unavailable (provider returned no voice_id)"
                )
            sample.meta = {**(sample.meta or {}), "voice_id": voice_id}

        persona = (
            await db.get(Persona, project.persona_id) if project.persona_id else None
        )
        style_hint = _persona_style_hint(persona)
        new_track = await translate_caption_track(
            track, target_language, style_hint=style_hint
        )
        # The title card is part of the spec too — a dubbed clip with an
        # untranslated title reads broken (2026-08-09, dub contrast pack).
        title = spec.get("title") or {}
        title_text = str(title.get("text") or "").strip()
        new_title_text = (
            await translate_text(title_text, target_language, style_hint=style_hint)
            if title.get("enabled") and title_text
            else ""
        )

        units = _group_units(new_track)
        if not units:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Clip has no captions to dub")
        gaps = [
            max(0.0, units[i + 1]["start"] - u["end"]) if i + 1 < len(units) else _GAP_ALLOW_S
            for i, u in enumerate(units)
        ]
        sem = asyncio.Semaphore(_TTS_CONCURRENCY)
        fitted = await asyncio.gather(
            *[
                _synthesize_fit_unit(u, g, voice_id, target_language, sem)
                for u, g in zip(units, gaps, strict=True)
            ]
        )
        sped_up = sum(1 for _, _, s in fitted if s)

        # Placements are in CLIP time (hidden segments cut, kept ones
        # concatenated) — the dub plays from clip t=0, not source t=0.
        map_t = _clip_time_mapper(spec.get("segments"))
        total_end = max(map_t(s) + len(p) / _RATE for s, p, _ in fitted)
        buf = np.zeros(int((total_end + _TAIL_PAD_S) * _RATE) + 1, dtype=np.int16)
        for start, pcm, _ in sorted(fitted, key=lambda f: f[0]):
            off = int(map_t(start) * _RATE)
            end = min(off + len(pcm), len(buf))
            if end > off:
                buf[off:end] = pcm[: end - off]
        audio_bytes, ext = await run_in_threadpool(_encode_audio, buf)
        logger.info(
            "dub_aligned",
            output_id=str(output.id),
            target_language=target_language,
            units=len(units),
            sped_up=sped_up,
            duration_s=round(total_end, 2),
            encoder=ext,
        )
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
            f"{output.id}_dub_{target_language}.{ext}",
        )
    )
    try:
        out_key = await save(out_key, audio_bytes)
    except Exception as e:  # storage layer raises plain network/IO errors
        raise TransientNodeError(f"dub audio upload failed: {e}") from e

    return {
        **spec,
        "caption_track": new_track,
        "title": {**title, "text": new_title_text} if new_title_text else title,
        "target_language": target_language,
        "dub": {"url": output_url(out_key), "enabled": True, "gain_db": 0.0},
    }
