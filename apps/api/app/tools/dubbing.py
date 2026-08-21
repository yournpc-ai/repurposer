"""Cue-aligned dub synthesis mechanics — pure mechanical (N-29: zero LLM,
zero agents, zero clients).

**Cue-aligned synthesis (dub 生产级, 2026-08-07)**: the free-running
whole-clip TTS (voice drifting away from the burned captions within seconds)
is retired. Each translation unit (~10 words) is synthesized separately and
fitted to its source-time window — pass 1 at speed 1.0, measured via decode,
and if it overruns its window (window = source span + a capped bite of the
following pause) it is re-synthesized at the provider's voice-level speed
(≤1.35×, natural range — no pitch shift). Units are then placed at their cue
start times on a silent timeline; later units overwrite rare overlaps.

The orchestration around these mechanics (voice-sample resolution, caption
translation, spec assembly, error contract) is the dub tool's private
procedure (``app/tools/dub/procedure.py``).
"""

import asyncio
import io
from typing import Any

import numpy as np
import structlog
from starlette.concurrency import run_in_threadpool

from app.metering import record_media_usage
from app.tools.voice import synthesize

logger = structlog.get_logger()

_UNIT_WORDS = 10  # synthesis unit granularity (mirrors caption units)
_RATE = 32000  # MiniMax T2A output sample rate (audio_setting)
_GAP_ALLOW_S = 0.8  # a unit may eat this much of the following pause
_SPEED_MAX = 1.35  # fastest re-synthesis (beyond = unnatural speech)
_TAIL_PAD_S = 0.5  # silence appended after the last unit
_TTS_CONCURRENCY = 4  # bounded parallel unit synthesis


class DubAssemblyError(Exception):
    """Mechanical dub-track assembly failure (decode/encode) — the dub
    tool's procedure maps it onto its error contract."""

    # Assembly failures surface with the voice family line (pipeline/errors.py).
    user_key = "voice_unavailable"


def group_units(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def clip_time_mapper(segments: list[dict[str, Any]] | None) -> Any:
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
        raise DubAssemblyError("dub unit decoded to zero samples")
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
    raise DubAssemblyError("no usable audio encoder for dub assembly")


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
    # Every synthesis call bills its characters — pass 2 re-synthesizes are
    # metered as a second call below.
    await record_media_usage({"tts_chars": float(len(unit["text"]))})
    pcm = await run_in_threadpool(_decode_mp3, audio)
    duration = len(pcm) / _RATE
    if duration > window * 1.05:
        speed = min(duration / window, _SPEED_MAX)
        async with sem:
            audio = await run_in_threadpool(
                synthesize, unit["text"], voice_id, target_language, speed
            )
        await record_media_usage({"tts_chars": float(len(unit["text"]))})
        pcm = await run_in_threadpool(_decode_mp3, audio)
        return unit["start"], pcm, True
    return unit["start"], pcm, False


async def synthesize_aligned_track(
    units: list[dict[str, Any]],
    voice_id: str,
    target_language: str,
    segments: list[dict[str, Any]] | None,
) -> tuple[bytes, str, int, float]:
    """Synthesize the translated units and assemble the cue-aligned dub track.

    Pure mechanics: timed units + a cloned voice id in, audio bytes out.
    Returns (audio_bytes, ext, sped_up_count, total_seconds_clip_time).
    """
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
    map_t = clip_time_mapper(segments)
    total_end = max(map_t(s) + len(p) / _RATE for s, p, _ in fitted)
    buf = np.zeros(int((total_end + _TAIL_PAD_S) * _RATE) + 1, dtype=np.int16)
    for start, pcm, _ in sorted(fitted, key=lambda f: f[0]):
        off = int(map_t(start) * _RATE)
        end = min(off + len(pcm), len(buf))
        if end > off:
            buf[off:end] = pcm[: end - off]
    audio_bytes, ext = await run_in_threadpool(_encode_audio, buf)
    return audio_bytes, ext, sped_up, total_end
