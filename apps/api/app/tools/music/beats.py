"""Beat-grid analysis for music library pieces (ADR-121 B3).

The film's cut snap reads ``music.meta.beats`` — computed HERE, once, at
birth (``create_music_from_generation``) or at seed/reconcile time
(``seed_default_music`` backfills the catalog); the runtime never analyzes
audio (no aubio/librosa in the deps — PyAV decodes, numpy does the math,
both already aboard).

Method (deliberately simple — the snap tolerance is ±0.2s, the bed is
background, not a dance track): energy-flux onset envelope → autocorrelation
tempo in 60–180 BPM → comb-filter phase alignment against the onsets.
Returns ``None`` when the track is too short or too flat to trust —
degrade-honest: no grid, no snap.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

_RATE = 22050  # decode rate — plenty for beat work, 4x cheaper than 44.1k
_HOP = 512
_BPM_RANGE = (60.0, 180.0)
_MIN_TRACK_S = 8.0  # shorter than this, a grid is meaningless for film cuts


def _decode_mono_pcm(data: bytes) -> np.ndarray:
    """Audio bytes → mono float32 PCM at _RATE (the narration module's
    decode idiom — s16 counts would quantize the flux math, so float)."""
    import av

    chunks: list[np.ndarray] = []
    with av.open(io.BytesIO(data)) as inp:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=_RATE)
        for frame in inp.decode(audio=0):
            for r in resampler.resample(frame):
                chunks.append(r.to_ndarray().reshape(-1))
        for r in resampler.resample(None):
            chunks.append(r.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError("music decoded to zero samples")
    return np.concatenate(chunks)


def analyze_beat_grid(data: bytes) -> dict[str, Any] | None:
    """Audio bytes → {"bpm": float, "beats": [seconds…]} or None (honest
    degrade: too short / no periodicity worth snapping to)."""
    pcm = _decode_mono_pcm(data)
    duration_s = len(pcm) / _RATE
    if duration_s < _MIN_TRACK_S:
        logger.info("beat_grid_skipped", reason="too_short", seconds=round(duration_s, 1))
        return None

    # Onset envelope: per-frame RMS energy, positive first difference.
    n_frames = len(pcm) // _HOP
    if n_frames < 32:
        return None
    framed = pcm[: n_frames * _HOP].reshape(n_frames, _HOP)
    energy = np.sqrt(np.mean(framed**2, axis=1))
    onset = np.maximum(0.0, np.diff(energy))
    if float(onset.std()) < 1e-6:
        logger.info("beat_grid_skipped", reason="flat")
        return None
    onset = onset - onset.mean()

    # Tempo: autocorrelation peak in the BPM window.
    fps = _RATE / _HOP  # envelope frames per second
    lo = int(fps * 60.0 / _BPM_RANGE[1])  # lag of the fastest tempo
    hi = int(fps * 60.0 / _BPM_RANGE[0])  # lag of the slowest
    corr = np.correlate(onset, onset, mode="full")[len(onset) - 1 :]
    if hi >= len(corr):
        logger.info("beat_grid_skipped", reason="window_wider_than_track")
        return None
    window = corr[lo:hi]
    if float(window.max()) <= 0:
        logger.info("beat_grid_skipped", reason="no_periodicity")
        return None
    lag = lo + int(np.argmax(window))
    # Sub-frame tempo: parabolic interpolation around the autocorrelation
    # peak — integer envelope-frame lags quantize the period (43 fps → 22
    # frames ≈ 117.5 BPM for a true 120), and the quantization DRIFTS the
    # grid off the audible beats over a minute-long bed.
    c = corr[lag]
    denom = corr[lag - 1] - 2 * c + corr[lag + 1]
    frac = 0.5 * (corr[lag - 1] - corr[lag + 1]) / denom if abs(denom) > 1e-12 else 0.0
    period = lag + float(frac)  # envelope frames per beat (fractional)
    bpm = 60.0 * fps / period

    # Phase: comb-filter the onsets at half-frame offset resolution, keeping
    # the offset whose grid carries the most onset energy.
    best_offset, best_energy = 0.0, -np.inf
    for off in np.arange(0.0, period, 0.5):
        idx = np.round(off + np.arange(len(onset)) * period).astype(int)
        idx = idx[idx < len(onset)]
        e = float(onset[idx].sum())
        if e > best_energy:
            best_energy, best_offset = e, float(off)

    beat_frames = best_offset + np.arange(n_frames) * period
    beat_frames = beat_frames[beat_frames < n_frames]
    beats = [round(float(f) * _HOP / _RATE, 3) for f in beat_frames]
    grid = {"bpm": round(bpm, 1), "beats": beats}
    logger.info(
        "beat_grid_analyzed",
        bpm=grid["bpm"],
        beats=len(beats),
        seconds=round(duration_s, 1),
    )
    return grid
