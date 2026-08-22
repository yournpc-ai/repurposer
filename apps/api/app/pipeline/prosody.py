"""Prosody — deterministic pitch/energy feature extraction (产物质量线 期 1).

The acoustic half of the beat map's emphasis channel (简报 §2.2): per-word
F0 (YIN) and RMS energy with z-scores, emphasis peaks, and filler regions.
The SEMANTIC half lives on the understanding (LLM) — the two channels are
stored in separate fields by design (预合并 = 自信地错且不可溯源; their
disagreement is the editor's arbitration signal).

Family shape = ASR / speaker_map (asset_processing PROCESSORS chain): reads
the prior result's words, downloads the media to a temp file, CPU-bound work
in a thread, degrade-on-error — a prosody failure must never fail the asset
(ASR's outputs are already in hand). Word-level timestamps are the
deterministic foundation: this processor ONLY READS them, never writes.

Dependency-free (numpy YIN — no librosa/parselmouth). Validated by
``--selftest``: synthesized 120 Hz harmonic stack must read ≈120 Hz.
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

PROSODY_VERSION = 1

_RATE = 16000  # speech band; plenty for F0 50–600 Hz
_FRAME = 1024  # 64 ms window (≥3 periods of 50 Hz)
_HOP = 160  # 10 ms hop
_F0_MIN_HZ = 50.0
_F0_MAX_HZ = 600.0
_YIN_THRESHOLD = 0.10

# Emphasis / filler thresholds (先验 — anatomy-calibrated, never gates).
_EMPHASIS_Z = 1.5
_DEAD_AIR_S = 0.6
_FILLER_TOKENS = {
    "um", "uh", "er", "ah", "eh", "mm", "hmm",
    "呃", "嗯", "啊", "那个", "就是", "然后",
}


def _load_mono_16k(path: Path) -> np.ndarray:
    """Decode the first audio stream to mono float32 @16 kHz (PyAV)."""
    import av  # lazy: heavy

    container = av.open(str(path))
    try:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.zeros(0, dtype=np.float32)
        resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=_RATE)
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    finally:
        container.close()


def _yin_f0(pcm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """YIN (de Cheveigné & Kawahara 2002), numpy-only core.

    Returns (times, f0_hz): per-frame times (window centers, seconds) and F0
    in Hz (0.0 = unvoiced). Steps: difference function via FFT autocorrelation
    (d(τ) = r(0)+r₀(τ)−2r(τ)), cumulative mean normalized difference, absolute
    threshold τ pick within the 50–600 Hz lag range, parabolic interpolation.
    """
    n_frames = max(0, 1 + (len(pcm) - _FRAME) // _HOP)
    if n_frames == 0:
        return np.zeros(0), np.zeros(0)
    # Strided frame matrix (n_frames × _FRAME), mean-centered per frame.
    idx = np.arange(_FRAME)[None, :] + _HOP * np.arange(n_frames)[:, None]
    frames = pcm[idx].astype(np.float64)
    frames -= frames.mean(axis=1, keepdims=True)

    n_fft = 1 << (2 * _FRAME - 1).bit_length()
    spec = np.fft.rfft(frames, n=n_fft, axis=1)
    acf = np.fft.irfft(spec * np.conj(spec), n=n_fft, axis=1)[:, : _FRAME]
    # d(τ) = r(0) + r₀(τ) − 2r(τ): energy = full-frame r(0) (standard YIN
    # approximation, librosa's same form); r₀(τ) = energy of the shifted
    # window x[τ:] via reversed cumulative sums; r(τ) = the FFT autocorr.
    energy = np.sum(frames**2, axis=1)
    sq = frames**2
    rev_cumsum = np.cumsum(sq[:, ::-1], axis=1)[:, ::-1]  # rev_cumsum[:, t] = Σ_{j≥t} x[j]²
    d = energy[:, None] + rev_cumsum - 2.0 * acf
    d[:, 0] = 0.0
    # CMND: d'(τ) = d(τ) / ((1/τ) Σ_{j=1..τ} d(j)); d'(0) = 1.
    csum = np.cumsum(d, axis=1)
    taus = np.arange(_FRAME)
    with np.errstate(divide="ignore", invalid="ignore"):
        cmnd = d[:, 1:] / (csum[:, 1:] / taus[1:])
    cmnd = np.concatenate([np.ones((n_frames, 1)), cmnd], axis=1)

    tau_min = int(_RATE / _F0_MAX_HZ)
    tau_max = min(int(_RATE / _F0_MIN_HZ), _FRAME - 2)
    f0 = np.zeros(n_frames)
    times = (np.arange(n_frames) * _HOP + _FRAME / 2) / _RATE
    for i in range(n_frames):
        row = cmnd[i, tau_min : tau_max + 1]
        below = np.nonzero(row < _YIN_THRESHOLD)[0]
        if len(below) == 0:
            continue
        # First dip below threshold → its local minimum (not just the crossing).
        t = below[0]
        while t + 1 < len(row) and row[t + 1] < row[t]:
            t += 1
        tau = t + tau_min
        # Parabolic interpolation around the CMND minimum.
        if 1 <= tau < _FRAME - 1:
            y0, y1, y2 = cmnd[i, tau - 1], cmnd[i, tau], cmnd[i, tau + 1]
            denom = y0 - 2 * y1 + y2
            if abs(denom) > 1e-12:
                tau = tau + 0.5 * (y0 - y2) / denom
        if tau > 0:
            f0[i] = _RATE / tau
    return times, f0


def _frame_rms_db(pcm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """RMS dB per frame on the same grid as _yin_f0."""
    n_frames = max(0, 1 + (len(pcm) - _FRAME) // _HOP)
    if n_frames == 0:
        return np.zeros(0), np.zeros(0)
    idx = np.arange(_FRAME)[None, :] + _HOP * np.arange(n_frames)[:, None]
    frames = pcm[idx].astype(np.float64)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-20)
    times = (np.arange(n_frames) * _HOP + _FRAME / 2) / _RATE
    return times, 20.0 * np.log10(np.maximum(rms, 1e-10))


def build_prosody(path: Path, words: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Local media file + ASR words → the prosody block (CPU-bound, sync)."""
    pcm = _load_mono_16k(path)
    if len(pcm) < _RATE:
        return None
    times, f0 = _yin_f0(pcm)
    _, rms_db = _frame_rms_db(pcm)
    if len(times) == 0:
        return None

    # Per-word aggregates (deterministic join on the ASR word axis).
    word_rows: list[dict[str, Any]] = []
    f0_voiced_all = f0[f0 > 0]
    f0_mean = float(np.mean(f0_voiced_all)) if len(f0_voiced_all) else 0.0
    f0_std = float(np.std(f0_voiced_all)) if len(f0_voiced_all) else 1.0
    for i, w in enumerate(words):
        s, e = float(w.get("start", 0)), float(w.get("end", 0))
        mask = (times >= s) & (times < e)
        wf0 = f0[mask & (f0 > 0)]
        wrms = rms_db[mask]
        word_rows.append(
            {
                "i": i,
                "f0_hz": round(float(np.median(wf0)), 1) if len(wf0) else None,
                "rms_db": round(float(np.max(wrms)), 1) if len(wrms) else None,
            }
        )
    rms_vals = np.array([r["rms_db"] for r in word_rows if r["rms_db"] is not None])
    rms_mean = float(np.mean(rms_vals)) if len(rms_vals) else 0.0
    rms_std = float(np.std(rms_vals)) or 1.0
    for row in word_rows:
        row["f0_z"] = (
            round((row["f0_hz"] - f0_mean) / f0_std, 2) if row["f0_hz"] is not None and f0_std > 0 else None
        )
        row["energy_z"] = (
            round((row["rms_db"] - rms_mean) / rms_std, 2) if row["rms_db"] is not None else None
        )

    # Acoustic emphasis candidates (channel-tagged — never merged with the
    # semantic channel; disagreement is downstream signal).
    peaks: list[dict[str, Any]] = []
    for row, w in zip(word_rows, words):
        kinds = []
        if row["f0_z"] is not None and row["f0_z"] >= _EMPHASIS_Z:
            kinds.append("f0")
        if row["energy_z"] is not None and row["energy_z"] >= _EMPHASIS_Z:
            kinds.append("energy")
        if kinds:
            peaks.append(
                {
                    "t": round(float(w.get("start", 0)), 3),
                    "word_i": row["i"],
                    "word": str(w.get("word", "")).strip(),
                    "kind": "+".join(kinds),
                    "f0_z": row["f0_z"],
                    "energy_z": row["energy_z"],
                }
            )

    # Filler regions: lexicon tokens + dead-air gaps between words.
    fillers: list[dict[str, Any]] = []
    for i, w in enumerate(words):
        tok = str(w.get("word", "")).strip().lower().strip(".,!?，。、 ")
        if tok in _FILLER_TOKENS:
            fillers.append(
                {"start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3), "kind": "filler", "token": tok}
            )
        if i + 1 < len(words):
            gap = float(words[i + 1].get("start", 0)) - float(w.get("end", 0))
            if gap >= _DEAD_AIR_S:
                fillers.append(
                    {"start": round(float(w["end"]), 3), "end": round(float(words[i + 1]["start"]), 3), "kind": "dead_air"}
                )

    return {
        "version": PROSODY_VERSION,
        "hop_s": _HOP / _RATE,
        "global": {
            "f0_mean_hz": round(f0_mean, 1),
            "f0_std_hz": round(f0_std, 1),
            "energy_mean_db": round(rms_mean, 1),
            "energy_std_db": round(rms_std, 2),
        },
        "words": word_rows,
        "emphasis_peaks": peaks,
        "filler_regions": fillers,
    }


async def prosody_processor(asset, prior) -> "Any":
    """VIDEO/AUDIO's prosody processor (after ASR): reads the prior result's
    words; degrade-on-error (speaker_map precedent) — never fails the asset."""
    from app.pipeline.asset_processing import ProcessResult  # avoid cycle at import time
    from app.providers.storage import download_to_temp

    words = (prior.meta or {}).get("words") or []
    if not words or not asset.file_url:
        return ProcessResult()
    path = await download_to_temp(asset.file_url)
    if path is None:
        return ProcessResult()
    try:
        prosody = await asyncio.to_thread(build_prosody, path, words)
        if prosody is None:
            return ProcessResult()
        logger.info(
            "prosody_built",
            asset_id=str(asset.id),
            words=len(prosody["words"]),
            peaks=len(prosody["emphasis_peaks"]),
        )
        return ProcessResult(meta={"prosody": prosody})
    except Exception as e:  # noqa: BLE001 — degrade to no prosody, keep ASR's result
        logger.error("prosody_failed", asset_id=str(asset.id), error=str(e))
        return ProcessResult()
    finally:
        path.unlink(missing_ok=True)


def _selftest() -> None:
    """120 Hz harmonic stack must read ≈120 Hz median; white noise unvoiced."""
    t = np.arange(_RATE * 3) / _RATE
    harmonic = sum(np.sin(2 * math.pi * 120 * k * t) / k for k in range(1, 6)).astype(np.float32)
    _, f0 = _yin_f0(harmonic)
    voiced = f0[f0 > 0]
    med = float(np.median(voiced)) if len(voiced) else 0.0
    print(f"120Hz harmonic stack → median F0 {med:.1f} Hz (expect 120 ±3)")
    assert abs(med - 120.0) < 3.0, f"YIN off: {med}"
    noise = np.random.default_rng(7).standard_normal(_RATE * 2).astype(np.float32) * 0.1
    _, f0n = _yin_f0(noise)
    voiced_share = float(np.mean(f0n > 0))
    print(f"white noise → voiced share {voiced_share:.2f} (expect < 0.3)")
    assert voiced_share < 0.3, f"noise voiced too often: {voiced_share}"
    print("prosody selftest OK")


if __name__ == "__main__":
    _selftest()
