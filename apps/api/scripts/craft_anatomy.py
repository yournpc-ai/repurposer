"""craft anatomy (产物质量线 期 0 解剖): measure rendered clips against the
§2.1 craft rule sheet — the ruler before the axe.

Three evidence sources per clip:
1. **clip-spec** (Output.render_spec) — the planned timeline: segments,
   caption cues, crop keyframes, music, brand cards.
2. **ASR word axis** (Asset.meta["words"] via spec.source.asset_id) — the
   deterministic ground truth of speech timing (align_stills' estimated
   timeline for the stills family, same shape).
3. **The MP4 itself** — decoded with PyAV: integrated loudness (BS.1770),
   silence map, energy envelope, and per-frame face geometry (vendored YuNet).

Every metric reports its §2.1 prior next to the measured value. Priors are
NOT gates (简报 §6.3) — verdicts are informational until calibrated by this
very anatomy. Frame forensics discipline: frames land in a per-take dir named
``<label>-<content_md5[:8]>`` so a frame can never be attributed to the wrong
video (the /tmp cross-take lesson).

Usage:
    uv run python scripts/craft_anatomy.py --output-id <uuid> [--output-id ...]
    uv run python scripts/craft_anatomy.py --run-id <uuid>
    uv run python scripts/craft_anatomy.py --local <mp4> [--spec spec.json] [--words words.json]
    uv run python scripts/craft_anatomy.py --selftest     # audio-chain validation
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# §2.1 priors (编辑部惯例先验 — calibration targets, NOT acceptance gates)
# ---------------------------------------------------------------------------

PRIORS = {
    "hook_delay_s": 0.300,
    "cut_boundary_s": 0.180,
    "cut_in_pad_s": (0.100, 0.150),
    "cut_out_pad_s": (0.150, 0.200),
    "dead_air_s": (0.600, 0.800),
    "karaoke_words": (1, 3),
    "karaoke_dur_s": (0.200, 0.800),
    "caption_sync_s": 0.030,
    "max_static_shot_s": (8.0, 10.0),
    "end_hold_s": 1.8,
    "eye_line_y": (0.35, 0.45),
    "face_width": (0.30, 0.50),
    "image_dwell_s": (2.4, 4.8),
    "image_dwell_hard": (1.3, 4.0),  # never below 1.3, never above 4 (emphasis 1.6–2.4)
    "ken_burns_zoom": (1.05, 1.20),
    "image_cut_at_meaning_s": 0.200,
    "emphasis_isolation": 0.60,
    "breathing_reset_s": (12.0, 18.0),
    "ducking_db": (-22.0, -18.0),
    "voice_lufs": (-15.0, -13.0),  # -14 ±1
}

FILLER_TOKENS = {
    "um", "uh", "er", "ah", "eh", "mm", "hmm",
    "呃", "嗯", "啊", "那个", "就是", "然后",
}

# ---------------------------------------------------------------------------
# Audio: decode → PCM mono 48k; BS.1770 loudness; RMS envelope; silence
# ---------------------------------------------------------------------------

AUDIO_RATE = 48000


def decode_audio_pcm(mp4_path: Path) -> np.ndarray:
    """Decode the first audio stream to mono float32 @48kHz (PyAV, no ffmpeg CLI)."""
    import av  # lazy: heavy

    container = av.open(str(mp4_path))
    try:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.zeros(0, dtype=np.float32)
        resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=AUDIO_RATE)
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                arr = out.to_ndarray()  # (1, n) planar float32
                chunks.append(arr.reshape(-1))
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    finally:
        container.close()


def _biquad_lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Direct Form II transposed biquad (dependency-free scipy.signal.lfilter twin)."""
    n = len(x)
    y = np.empty(n, dtype=np.float64)
    z1 = z2 = 0.0
    b0, b1, b2 = b
    _, a1, a2 = a
    for i in range(n):
        xi = x[i]
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y


# ITU-R BS.1770-4 K-weighting, stage 1 (high shelf) + stage 2 (RLB high-pass),
# coefficients specified at 48 kHz.
_K1_B = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
_K1_A = np.array([1.0, -1.69065929318241, 0.73248077421585])
_K2_B = np.array([1.0, -2.0, 1.0])
_K2_A = np.array([1.0, -1.99004745483398, 0.99007225036621])


def integrated_loudness_lufs(pcm: np.ndarray, rate: int = AUDIO_RATE) -> float | None:
    """BS.1770-4 integrated loudness with absolute + relative gating."""
    if len(pcm) < rate // 2:
        return None
    x = _biquad_lfilter(_K1_B, _K1_A, pcm.astype(np.float64))
    x = _biquad_lfilter(_K2_B, _K2_A, x)
    block = int(0.400 * rate)  # 400ms blocks, 75% overlap
    hop = block // 4
    n_blocks = 1 + max(0, (len(x) - block) // hop)
    if n_blocks < 1:
        return None
    energies = np.array(
        [np.mean(x[i * hop : i * hop + block] ** 2) for i in range(n_blocks)]
    )
    loud = -0.691 + 10.0 * np.log10(np.maximum(energies, 1e-20))
    gated = energies[loud > -70.0]
    if len(gated) == 0:
        return None
    rel_gate = -0.691 + 10.0 * math.log10(max(float(np.mean(gated)), 1e-20)) - 10.0
    final = energies[loud > max(-70.0, rel_gate)]
    if len(final) == 0:
        return None
    return -0.691 + 10.0 * math.log10(max(float(np.mean(final)), 1e-20))


@dataclass
class AudioAnalysis:
    duration_s: float
    loudness_lufs: float | None
    peak_dbfs: float | None
    rms_times: np.ndarray  # window centers (s)
    rms_db: np.ndarray  # window RMS in dBFS
    silence_runs: list[tuple[float, float]]  # (start, end) below threshold
    lead_silence_s: float  # time to first non-silent window
    energy_peaks: list[tuple[float, float]]  # (t, dB above local median)


def analyze_audio(pcm: np.ndarray, rate: int = AUDIO_RATE, *, window_s: float = 0.100) -> AudioAnalysis:
    """RMS envelope + silence map + energy peaks. Silence = window below
    -45 dBFS (whisper's turn-gap floor; conservative vs -60 digital zero)."""
    duration = len(pcm) / rate if rate else 0.0
    if len(pcm) == 0:
        return AudioAnalysis(0.0, None, None, np.zeros(0), np.zeros(0), [], 0.0, [])
    win = int(window_s * rate)
    n = max(1, len(pcm) // win)
    rms = np.array(
        [float(np.sqrt(np.mean(pcm[i * win : (i + 1) * win] ** 2) + 1e-20)) for i in range(n)]
    )
    rms_db = 20.0 * np.log10(np.maximum(rms, 1e-10))
    times = (np.arange(n) + 0.5) * window_s

    threshold_db = -45.0
    silent = rms_db < threshold_db
    runs: list[tuple[float, float]] = []
    i = 0
    while i < n:
        if silent[i]:
            j = i
            while j < n and silent[j]:
                j += 1
            runs.append((float(times[i] - window_s / 2), float(times[j - 1] + window_s / 2)))
            i = j
        else:
            i += 1
    lead = 0.0
    for k in range(n):
        if not silent[k]:
            lead = float(times[k] - window_s / 2)
            break
    else:
        lead = duration

    # Energy peaks: local maxima ≥3 dB above a ±2 s rolling median, ≥0.5 s apart.
    peaks: list[tuple[float, float]] = []
    half = int(2.0 / window_s)
    last_peak_t = -1.0
    for k in range(n):
        lo, hi = max(0, k - half), min(n, k + half + 1)
        med = float(np.median(rms_db[lo:hi]))
        if rms_db[k] >= med + 3.0 and rms_db[k] == float(np.max(rms_db[lo:hi])):
            if times[k] - last_peak_t >= 0.5:
                peaks.append((float(times[k]), float(rms_db[k] - med)))
                last_peak_t = float(times[k])

    peak_dbfs = float(20.0 * math.log10(float(np.max(np.abs(pcm))) + 1e-10)) if len(pcm) else None
    return AudioAnalysis(
        duration_s=duration,
        loudness_lufs=integrated_loudness_lufs(pcm, rate),
        peak_dbfs=peak_dbfs,
        rms_times=times,
        rms_db=rms_db,
        silence_runs=runs,
        lead_silence_s=lead,
        energy_peaks=peaks,
    )


# ---------------------------------------------------------------------------
# Frames: per-take extraction + YuNet face geometry
# ---------------------------------------------------------------------------


def extract_frames(mp4_path: Path, out_dir: Path, fps: float = 1.0) -> list[tuple[float, Path]]:
    """Extract frames at ``fps`` into out_dir (per-take, content-md5 named).

    Returns [(source_seconds, frame_path)] in timeline order.
    """
    import av  # lazy

    out_dir.mkdir(parents=True, exist_ok=True)
    container = av.open(str(mp4_path))
    taken: list[tuple[float, Path]] = []
    try:
        stream = next(s for s in container.streams if s.type == "video")
        next_t = 0.0
        for frame in container.decode(stream):
            t = float(frame.pts * stream.time_base) if frame.pts is not None else None
            if t is None:
                t = next_t
            if t + 1e-6 < next_t:
                continue
            next_t = t + 1.0 / fps
            arr = frame.to_ndarray(format="rgb24")
            p = out_dir / f"f{taken and len(taken) or 0:05d}.jpg"
            import cv2

            cv2.imwrite(str(p), cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
            taken.append((t, p))
    finally:
        container.close()
    return taken


def face_geometry(frame_paths: list[tuple[float, Path]]) -> dict[str, Any]:
    """YuNet per-frame face geometry → eye-line y / face-width distributions.

    Eye-line = the two-eye landmark midpoint's y as a frame-height fraction;
    face width = the largest detected face's bbox width as a frame-width
    fraction (the talking-head rule speaks of ONE subject).
    """
    from app.providers.vision import detect_faces  # vendored YuNet seam

    import cv2

    eye_ys: list[float] = []
    face_ws: list[float] = []
    detected = 0
    for _t, p in frame_paths:
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        faces = detect_faces(img, (w, h))
        if not faces:
            continue
        detected += 1
        main = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
        eye_y = float((main.landmarks[0][1] + main.landmarks[1][1]) / 2.0) / h
        eye_ys.append(eye_y)
        face_ws.append(float(main.bbox[2]) / w)
    n = len(frame_paths)

    def _stats(xs: list[float]) -> dict[str, float] | None:
        if not xs:
            return None
        arr = np.array(xs)
        return {
            "median": float(np.median(arr)),
            "p10": float(np.percentile(arr, 10)),
            "p90": float(np.percentile(arr, 90)),
        }

    return {
        "frames": n,
        "detected": detected,
        "coverage": (detected / n) if n else 0.0,
        "eye_line_y": _stats(eye_ys),
        "face_width": _stats(face_ws),
    }


# ---------------------------------------------------------------------------
# Word-axis helpers
# ---------------------------------------------------------------------------


def _wf(w: dict[str, Any], key: str) -> float:
    return float(w.get(key, 0.0))


def kept_words(words: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [w for w in words if _wf(w, "start") >= start - 1e-6 and _wf(w, "end") <= end + 0.05]


def sentence_boundary_times(words: list[dict[str, Any]]) -> list[float]:
    """Word-end times whose token closes a sentence/clause (punctuation tail)."""
    times: list[float] = []
    for w in words:
        tok = str(w.get("word", "")).rstrip()
        if tok and tok[-1] in ".!?。！？;；,，、:：":
            times.append(_wf(w, "end"))
    return times


# ---------------------------------------------------------------------------
# Metric assembly
# ---------------------------------------------------------------------------


@dataclass
class Metric:
    key: str
    value: Any
    prior: Any = None
    verdict: str = "info"  # ok | gap | info | n/a
    evidence: Any = None

    def row(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "prior": self.prior, "verdict": self.verdict, "evidence": self.evidence}


def _verdict_in(value: float | None, rng: tuple[float, float]) -> str:
    if value is None:
        return "n/a"
    return "ok" if rng[0] <= value <= rng[1] else "gap"


def talking_head_metrics(spec: dict[str, Any], words: list[dict[str, Any]], audio: AudioAnalysis) -> list[Metric]:
    from app.pipeline.clip_spec import intro_seconds, outro_seconds, video_duration_seconds

    ms: list[Metric] = []
    kept = [s for s in spec.get("segments") or [] if not s.get("hidden")]
    if not kept:
        return [Metric("family", "talking_head", verdict="gap", evidence="no kept segments")]
    video_dur = video_duration_seconds(spec)
    intro = intro_seconds(spec)
    outro = outro_seconds(spec)
    # Chain shape: a single kept segment spanning ~the whole source with no
    # crop decisions = materialized full source (subs card). Cut pacing / end
    # hold / dead air there are the SOURCE's own rhythm, not our decisions.
    src_dur = (spec.get("source") or {}).get("duration")
    materialized = (
        len(kept) == 1
        and not (spec.get("crop_track") or [])
        and src_dur is not None
        and (float(kept[0]["end"]) - float(kept[0]["start"])) >= 0.98 * float(src_dur)
    )
    scope = "source" if materialized else "product"

    # T1 hook delay — planned (first kept word's output-clock offset) + actual (audio onset).
    first = kept[0]
    fwords = kept_words(words, float(first["start"]), float(first["end"]))
    planned_hook = intro + (float(fwords[0]["start"]) - float(first["start"]) if fwords else 0.0)
    ms.append(Metric(
        "hook_delay_s",
        round(planned_hook, 3),
        prior=f"≤{PRIORS['hook_delay_s']}",
        verdict="ok" if planned_hook <= PRIORS["hook_delay_s"] + 1e-9 else "gap",
        evidence={"planned_intro_s": intro, "actual_audio_onset_s": round(audio.lead_silence_s, 3)},
    ))

    # T3 thought-boundary cuts. Two measurements per edge:
    # - pad WITHIN the cut: air before the first word / after the last word
    #   (locate_span snaps to word boundaries — zero pad by construction is
    #   the "robotic jump cut" source the rule guards against);
    # - boundary context OUTSIDE the cut: the pause the edge sits in and the
    #   nearest clause boundary (was a boundary cut even possible?).
    bounds = sentence_boundary_times(words)
    cut_ev: list[dict[str, Any]] = []
    for idx, seg in enumerate(kept):
        s, e = float(seg["start"]), float(seg["end"])
        in_words = kept_words(words, s, e)
        prev_words = [w for w in words if _wf(w, "end") <= s + 1e-6]
        next_words = [w for w in words if _wf(w, "start") >= e - 1e-6]
        pre_pad = (_wf(in_words[0], "start") - s) if in_words else None
        post_pad = (e - _wf(in_words[-1], "end")) if in_words else None
        pause_before = (s - _wf(prev_words[-1], "end")) if prev_words else None
        pause_after = (_wf(next_words[0], "start") - e) if next_words else None
        nearest_b = min((abs(s - b) for b in bounds), default=None)
        straddle = any(_wf(w, "start") < s < _wf(w, "end") or _wf(w, "start") < e < _wf(w, "end") for w in words)
        cut_ev.append({
            "seg": idx,
            "pre_pad_s": round(pre_pad, 3) if pre_pad is not None else None,
            "post_pad_s": round(post_pad, 3) if post_pad is not None else None,
            "pause_available_before_s": round(pause_before, 3) if pause_before is not None else None,
            "pause_available_after_s": round(pause_after, 3) if pause_after is not None else None,
            "in_nearest_boundary_s": round(nearest_b, 3) if nearest_b is not None else None,
            "mid_word_cut": straddle,
        })
    ms.append(Metric("cut_boundaries", cut_ev, prior=f"in-pad {PRIORS['cut_in_pad_s']}, out-pad {PRIORS['cut_out_pad_s']}; edge within ±{PRIORS['cut_boundary_s']}s of a clause boundary", verdict="info"))

    # T4 dead air & filler inside kept spans.
    dead: list[dict[str, float]] = []
    fillers: list[str] = []
    for seg in kept:
        ws = kept_words(words, float(seg["start"]), float(seg["end"]))
        for a, b in zip(ws, ws[1:]):
            gap = _wf(b, "start") - _wf(a, "end")
            if gap >= PRIORS["dead_air_s"][0]:
                dead.append({"at": round(_wf(a, "end"), 2), "gap_s": round(gap, 2)})
        for w in ws:
            tok = str(w.get("word", "")).strip().lower().strip(".,!?，。、 ")
            if tok in FILLER_TOKENS:
                fillers.append(tok)
    ms.append(Metric(
        "dead_air",
        {"count": len(dead), "runs": dead[:10]},
        prior=f"pauses >{PRIORS['dead_air_s'][0]}–{PRIORS['dead_air_s'][1]}s removed",
        verdict="info" if materialized else ("ok" if not dead else "gap"),
        evidence={"scope": scope},
    ))
    ms.append(Metric(
        "filler_kept",
        {"count": len(fillers), "tokens": fillers[:12]},
        prior="um/uh-class fillers removed (intentional beats excepted)",
        verdict="ok" if not fillers else "gap",
    ))

    # T5 emphasis follows prosody — count emphasis EVENTS in the spec vs energy peaks.
    # (Zoom/pop/caption-burst mechanisms: none exist in today's contract.)
    ms.append(Metric(
        "emphasis_events",
        {"spec_events": 0, "audio_energy_peaks": len(audio.energy_peaks)},
        prior="emphasis aligned to pitch/energy peaks",
        verdict="gap" if audio.energy_peaks else "n/a",
        evidence={"peaks_top": audio.energy_peaks[:8]},
    ))

    # T6 caption rhythm — cues are word-level; display groups into 7-word
    # lines. The §2.1 rule is two styles: karaoke bursts (1–3 words, timed) OR
    # phrase style (≤2 lines, 32–42 chars/line) — measure BOTH axes.
    cues = spec.get("caption_track") or []
    line_size = 7
    lines_ = [cues[i : i + line_size] for i in range(0, len(cues), line_size)]
    line_durs = [float(ln[-1]["end"]) - float(ln[0]["start"]) for ln in lines_ if ln]
    line_chars = [len(" ".join(str(c["text"]) for c in ln)) for ln in lines_ if ln]
    ms.append(Metric(
        "caption_rhythm",
        {
            "cue_level": "word",
            "words_per_line": line_size,
            "line_dur_median_s": round(float(np.median(line_durs)), 3) if line_durs else None,
            "line_dur_max_s": round(max(line_durs), 3) if line_durs else None,
            "line_chars_median": float(np.median(line_chars)) if line_chars else None,
            "line_chars_p90": float(np.percentile(line_chars, 90)) if line_chars else None,
        },
        prior=f"karaoke bursts {PRIORS['karaoke_words']} words / {PRIORS['karaoke_dur_s']}s; or phrase ≤2 lines 32–42 chars",
        verdict="info",
    ))

    # T7 cut-frequency envelope — segment boundaries + crop keyframe switches.
    # crop_track t is SOURCE-clock (ADR-045 D5); remap to the output clock
    # before measuring intervals (the source-clock artifact once read 682s).
    from app.pipeline.clip_spec import output_time_at_source_time

    switches: list[float] = []
    kf_deltas: list[float] = []
    track = sorted((spec.get("crop_track") or []), key=lambda k: float(k["t"]))
    for prev, cur in zip(track, track[1:]):
        # Perceptual delta: |Δx|+|Δy| in frame fractions + relative zoom change.
        dx = abs(float(cur["x"]) - float(prev["x"]))
        dy = abs(float(cur["y"]) - float(prev["y"]))
        dz = abs(float(cur["scale"]) - float(prev["scale"])) / max(float(prev["scale"]), 1e-6)
        kf_deltas.append(round(dx + dy + dz, 4))
    for k in track:
        out_t = output_time_at_source_time(spec, float(k["t"]))
        if out_t is not None:
            switches.append(out_t - intro)
    switches = sorted({round(s, 3) for s in switches if 0 <= s <= video_dur})
    boundaries_t = [0.0] + switches + [video_dur]
    intervals = [round(b - a, 3) for a, b in zip(boundaries_t, boundaries_t[1:]) if b - a > 0.01]
    max_static = max(intervals) if intervals else video_dur
    burst = sum(1 for a, b in zip(switches, switches[1:]) if b - a < 1.0)
    ms.append(Metric(
        "cut_frequency",
        {
            "intervals_s": intervals,
            "max_static_s": round(max_static, 2),
            "sub_1s_switches": burst,
            "keyframe_deltas": kf_deltas,
            "keyframes_perceptual": sum(1 for d in kf_deltas if d >= 0.05),
        },
        prior=f"no >2 consecutive cuts <1s; no static shot >{PRIORS['max_static_shot_s']}s",
        verdict=("info" if materialized else ("ok" if max_static <= PRIORS["max_static_shot_s"][1] and burst == 0 else "gap")),
        evidence={"scope": scope, "note": "keyframe delta = |Δx|+|Δy|+relΔscale; ≥0.05 reads as a perceptual reframe, micro-drift does not"},
    ))

    # T8 ending — tail hold after the last word (+ outro card seconds).
    last_end = max((_wf(w, "end") for w in kept_words(words, kept[-1]["start"], kept[-1]["end"])), default=None)
    tail_hold = (video_dur - (last_end - float(kept[0]["start"]) if last_end else video_dur)) if last_end else None
    tail_total = (tail_hold + outro) if tail_hold is not None else None
    ms.append(Metric(
        "end_hold_s",
        round(tail_total, 3) if tail_total is not None else None,
        prior=f"≥{PRIORS['end_hold_s']}s",
        verdict=("info" if materialized else ("ok" if tail_total is not None and tail_total >= PRIORS["end_hold_s"] else "gap")),
        evidence={"video_tail_s": round(tail_hold, 3) if tail_hold is not None else None, "outro_card_s": outro, "scope": scope},
    ))
    return ms


def stills_metrics(spec: dict[str, Any], words: list[dict[str, Any]], audio: AudioAnalysis) -> list[Metric]:
    from app.pipeline.clip_spec import video_duration_seconds

    ms: list[Metric] = []
    images = (spec.get("source") or {}).get("image_urls") or []
    n = len(images)
    dur = video_duration_seconds(spec)
    cues = spec.get("caption_track") or []

    # S2 dwell — the renderer's splitFrames even split (last absorbs remainder).
    dwells = [dur / n] * n if n else []
    if n and dur:
        base = max(1.0, math.floor(dur * 30 / n) / 30)  # splitFrames in frames
        dwells = [base] * (n - 1) + [max(1 / 30, dur - base * (n - 1))]
    uniform = len({round(d, 1) for d in dwells}) <= 1  # frame-quantized ≈ uniform
    ms.append(Metric(
        "image_dwell_s",
        {"per_image": [round(d, 3) for d in dwells], "uniform": uniform},
        prior=f"sweet zone {PRIORS['image_dwell_s']}s; never <{PRIORS['image_dwell_hard'][0]}s / >{PRIORS['image_dwell_hard'][1]}s; emphasis {1.6}–{2.4}s",
        verdict="ok" if dwells and all(PRIORS["image_dwell_hard"][0] <= d <= PRIORS["image_dwell_hard"][1] for d in dwells) and len(set(round(d, 2) for d in dwells)) > 1 else "gap",
        evidence="uniform dwell = reading-pace even split; no content awareness",
    ))

    # S3 motion with a reason — Ken Burns zoom events in the spec: none exist.
    ms.append(Metric(
        "ken_burns",
        {"events": 0},
        prior=f"zoom {PRIORS['ken_burns_zoom']}× per image, alternating direction, ease 200–300ms",
        verdict="gap",
        evidence="contract carries no stills motion field — static hard-cut slideshow (splitFrames)",
    ))

    # S4 cuts on meaning — image cut times vs estimated-word sentence boundaries.
    cut_times = [float(np.cumsum(dwells)[i]) for i in range(n - 1)] if n > 1 else []
    bounds = sentence_boundary_times(words)
    dists = [round(min((abs(t - b) for b in bounds), default=-1.0), 3) for t in cut_times]
    aligned = sum(1 for d in dists if 0 <= d <= PRIORS["image_cut_at_meaning_s"])
    ms.append(Metric(
        "image_cuts_at_meaning",
        {"cuts": cut_times, "nearest_boundary_s": dists, "within_prior": f"{aligned}/{len(dists)}"},
        prior=f"±{PRIORS['image_cut_at_meaning_s']}s of a clause boundary / emphasis word",
        verdict="ok" if dists and aligned == len(dists) else "gap",
    ))

    # S5 emphasis isolation / S6 structural breathing — no such events exist.
    ms.append(Metric(
        "emphasis_isolation",
        {"events": 0},
        prior=f"≥{int(PRIORS['emphasis_isolation'] * 100)}% emphasis words get hold/push-in/caption-pop",
        verdict="gap",
        evidence="no emphasis mechanism in contract",
    ))
    ms.append(Metric(
        "structural_breathing",
        {"resets": 0},
        prior=f"one reset (wider/slower/pause) every {PRIORS['breathing_reset_s']}s",
        verdict="gap" if dur >= PRIORS["breathing_reset_s"][0] else "n/a",
    ))

    # S7 audio ducking & loudness — music-only track here (silent speech).
    music = spec.get("music") or {}
    ms.append(Metric(
        "audio_mix",
        {
            "music_enabled": bool(music.get("enabled")),
            "music_gain_db": music.get("gain_db"),
            "output_lufs": round(audio.loudness_lufs, 2) if audio.loudness_lufs is not None else None,
        },
        prior=f"voice {PRIORS['voice_lufs']} LUFS; BGM duck {PRIORS['ducking_db']}dB under voice",
        verdict="info",
        evidence="stills family carries no speech track — ducking n/a; loudness = music bed level",
    ))

    # Caption rhythm on the stills family (estimated word axis).
    if cues:
        line_size = 7
        line_durs = [
            float(cues[min(i + line_size, len(cues)) - 1]["end"]) - float(cues[i]["start"])
            for i in range(0, len(cues), line_size)
        ]
        ms.append(Metric(
            "caption_rhythm",
            {
                "cue_level": "word (estimated timeline)",
                "words_per_line": line_size,
                "line_dur_median_s": round(float(np.median(line_durs)), 3),
            },
            prior=f"karaoke bursts {PRIORS['karaoke_words']} words / {PRIORS['karaoke_dur_s']}s",
            verdict="info",
        ))
    return ms


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class ClipCase:
    label: str
    mp4_path: Path
    spec: dict[str, Any] | None = None
    words: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


async def _load_output_case(db: Any, output_id: str) -> ClipCase:
    from uuid import UUID

    from app.models.tables import Asset, Output
    from app.providers.storage import download_to_temp

    out = await db.get(Output, UUID(output_id))
    if out is None:
        raise SystemExit(f"output {output_id} not found")
    spec = out.render_spec or {}
    video_key = (out.files or {}).get("video")
    if not video_key:
        raise SystemExit(f"output {output_id} has no files.video (render_status={out.render_status})")
    mp4 = await download_to_temp(video_key)
    assert mp4 is not None
    words: list[dict[str, Any]] = []
    asset_id = (spec.get("source") or {}).get("asset_id")
    if asset_id:
        asset = await db.get(Asset, UUID(str(asset_id)))
        if asset is not None:
            words = (asset.meta or {}).get("words") or []
    return ClipCase(
        label=f"out-{output_id[:8]}",
        mp4_path=mp4,
        spec=spec,
        words=words,
        meta={"output_id": output_id, "run_id": str(out.workflow_step_id), "video_key": video_key, "type": out.type},
    )


def _family_of(spec: dict[str, Any] | None) -> str:
    if not spec:
        return "unknown"
    kind = (spec.get("source") or {}).get("kind")
    return "stills" if kind == "stills" else "talking_head"


def anatomize(case: ClipCase, frames_root: Path, *, frame_fps: float = 1.0, keep_frames: bool = False) -> dict[str, Any]:
    """One clip → the full three-source measurement."""
    content_md5 = hashlib.md5(case.mp4_path.read_bytes()).hexdigest()
    take_dir = frames_root / f"{case.label}-{content_md5[:8]}"

    pcm = decode_audio_pcm(case.mp4_path)
    audio = analyze_audio(pcm)

    frames: list[tuple[float, Path]] = []
    faces: dict[str, Any] = {"frames": 0, "detected": 0, "coverage": 0.0}
    family = _family_of(case.spec)
    want_faces = family != "stills"  # a photo's people are content, not framing
    if frame_fps > 0 and want_faces:
        frames = extract_frames(case.mp4_path, take_dir / "frames", fps=frame_fps)
        faces = face_geometry(frames)
        if not keep_frames:
            for _t, p in frames:
                p.unlink(missing_ok=True)

    metrics: list[Metric] = [
        Metric("duration_s", round(audio.duration_s, 3)),
        Metric(
            "integrated_loudness_lufs",
            round(audio.loudness_lufs, 2) if audio.loudness_lufs is not None else None,
            prior=f"voice {PRIORS['voice_lufs']} LUFS (-14 ±1)",
            verdict="info",
            evidence={"peak_dbfs": round(audio.peak_dbfs, 2) if audio.peak_dbfs is not None else None},
        ),
        Metric("lead_silence_s", round(audio.lead_silence_s, 3), prior="hook ≤0.3s", verdict="ok" if audio.lead_silence_s <= PRIORS["hook_delay_s"] else "gap"),
        Metric(
            "silence_runs",
            {"count": len(audio.silence_runs), "total_s": round(sum(e - s for s, e in audio.silence_runs), 2)},
            evidence=[(round(s, 2), round(e, 2)) for s, e in audio.silence_runs[:12]],
        ),
    ]
    if case.spec:
        if family == "stills":
            metrics += stills_metrics(case.spec, case.words, audio)
        else:
            metrics += talking_head_metrics(case.spec, case.words, audio)
    if faces["frames"]:
        eye = faces.get("eye_line_y") or {}
        fw = faces.get("face_width") or {}
        # Framing agency: the 35–45% / 30–50% priors judge OUR framing. A chain
        # with no reframe (materialized full source) inherits the source's
        # framing — report the numbers as info, never as our gap.
        has_crop = bool(case.spec and ((case.spec.get("crop_track") or []) or (case.spec.get("crop") or {}) not in ({}, {"x": 0.5, "y": 0.5, "scale": 1.0})))
        inherited = case.spec is not None and not has_crop
        metrics.append(Metric(
            "eye_line_y",
            eye,
            prior=f"{PRIORS['eye_line_y']} of frame height",
            verdict=("info" if inherited else _verdict_in(eye.get("median"), PRIORS["eye_line_y"])),
            evidence={"coverage": faces["coverage"], "frames": faces["frames"], **({"framing": "source-inherited (no reframe in chain)"} if inherited else {})},
        ))
        metrics.append(Metric(
            "face_width",
            fw,
            prior=f"{PRIORS['face_width']} of frame width",
            verdict=("info" if inherited else _verdict_in(fw.get("median"), PRIORS["face_width"])),
            evidence={"framing": "source-inherited (no reframe in chain)"} if inherited else None,
        ))

    return {
        "label": case.label,
        "family": family,
        "content_md5": content_md5,
        "frames_dir": str(take_dir),
        **case.meta,
        # Raw contract + word count ride the evidence JSON so fixed metrics can
        # be recomputed offline without re-running the pipeline.
        "spec": case.spec,
        "word_count": len(case.words),
        "metrics": [m.row() for m in metrics],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# craft anatomy report", ""]
    for clip in report["clips"]:
        lines.append(f"## {clip['label']} ({clip['family']}) md5={clip['content_md5'][:8]}")
        lines.append("")
        lines.append("| metric | value | prior (先验) | verdict |")
        lines.append("|---|---|---|---|")
        for m in clip["metrics"]:
            v = m["value"]
            if isinstance(v, (dict, list)):
                v = f"`{json.dumps(v, ensure_ascii=False)[:160]}`"
            prior = m["prior"] if m["prior"] is not None else "—"
            lines.append(f"| {m['key']} | {v} | {prior} | {m['verdict']} |")
        lines.append("")
    return "\n".join(lines)


def _selftest() -> None:
    """Audio-chain validation: a full-scale 1 kHz sine (peak 0 dBFS, RMS
    -3.01 dBFS) must read ≈ -3.0 LUFS — K-weighting has ~0 dB gain at 1 kHz."""
    t = np.arange(AUDIO_RATE * 10) / AUDIO_RATE
    sine = (1.0 * np.sin(2 * math.pi * 1000 * t)).astype(np.float32)
    lufs = integrated_loudness_lufs(sine)
    print(f"1kHz full-scale sine → {lufs:.2f} LUFS (expect ≈ -3.01 ±0.1)")
    assert lufs is not None and abs(lufs - (-3.01)) < 0.1, "loudness chain off"
    silence_then_tone = np.concatenate([np.zeros(AUDIO_RATE, dtype=np.float32), sine])
    a = analyze_audio(silence_then_tone)
    print(f"1s lead silence → lead={a.lead_silence_s:.3f}s (expect ≈1.0)")
    assert 0.9 <= a.lead_silence_s <= 1.1
    print("selftest OK")


async def _main() -> None:
    ap = argparse.ArgumentParser(description="craft anatomy (期 0 解剖)")
    ap.add_argument("--output-id", action="append", default=[])
    ap.add_argument("--run-id")
    ap.add_argument("--local", type=Path)
    ap.add_argument("--spec", type=Path)
    ap.add_argument("--words", type=Path)
    ap.add_argument("--label", default=None)
    ap.add_argument("--frames-root", type=Path, default=Path("data/anatomy"))
    ap.add_argument("--fps", type=float, default=1.0, help="frame extraction rate (0 = audio/spec only)")
    ap.add_argument("--keep-frames", action="store_true")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return

    cases: list[ClipCase] = []
    if args.local:
        spec = json.loads(args.spec.read_text()) if args.spec else None
        words = json.loads(args.words.read_text()) if args.words else []
        cases.append(ClipCase(label=args.label or args.local.stem, mp4_path=args.local, spec=spec, words=words))
    else:
        from app.models.database import AsyncSessionLocal
        from app.models.tables import Output

        async with AsyncSessionLocal() as db:
            output_ids = list(args.output_id)
            if args.run_id:
                from sqlalchemy import select

                from app.models.tables import WorkflowStep

                rows = (
                    await db.execute(
                        select(Output)
                        .join(WorkflowStep, Output.workflow_step_id == WorkflowStep.id)
                        .where(WorkflowStep.run_id == args.run_id)
                    )
                ).scalars().all()
                output_ids += [str(o.id) for o in rows if (o.files or {}).get("video")]
            for oid in output_ids:
                cases.append(await _load_output_case(db, oid))

    if not cases:
        ap.error("nothing to anatomize — pass --output-id / --run-id / --local")

    report = {"clips": [anatomize(c, args.frames_root, frame_fps=args.fps, keep_frames=args.keep_frames) for c in cases]}
    md = render_markdown(report)
    print(md)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        (args.report.with_suffix(".md")).write_text(md)
        print(f"\nreport → {args.report} (+ .md)")


if __name__ == "__main__":
    asyncio.run(_main())
