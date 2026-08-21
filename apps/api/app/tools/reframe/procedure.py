"""reframe_clip 工序 (ADR-045 D6): speaker_map + face positions → crop_track.

The anti-dizzy constraints are WRITE-SIDE (they live here, never serialized
into the contract — the renderer's sampler only ever smoothsteps). Initial
values from the 08-19 spike, tuned by watching real footage:

- MIN_DWELL_SECONDS: a switch needs an incoming turn at least this long —
  a listener's backchannel never pulls the camera.
- SWITCH_LEAD_SECONDS: the cut lands slightly BEFORE the new speaker's turn.
- FOLLOW_DEADZONE / FOLLOW_INTERVAL / FOLLOW_SLEW: speaker_follow moves only
  when the subject leaves the deadzone, at most one keyframe per interval,
  each move capped — the camera glides, never hunts.
- Framing: FACE_FRACTION_* (face width as a fraction of frame width) and
  FACE_TOP (face rides this far above center). MAX_SCALE bounds the upscale.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from app.pipeline.clip_spec import CROP_EASE_SECONDS
from app.pipeline.speaker_map import (
    _bootstrap_slots,
    _detect_tiled,
    _frames_every,
    _probe,
    _Slot,
)
from app.tools.vision import FaceDetection, detect_faces

logger = structlog.get_logger()

# ---- mode resolution -------------------------------------------------------

def resolve_mode(speaker_map: dict | None, requested: str) -> str:
    """auto picks by the asset's speaker_map form; an explicit mode is
    honored as-is (its prerequisites are checked by the caller)."""
    if requested != "auto":
        return requested
    form = (speaker_map or {}).get("form")
    if form == "interview":
        return "interview_switch"
    if form == "single":
        return "speaker_follow"
    return "static_center"


# ---- framing math ----------------------------------------------------------

FACE_FRACTION_INTERVIEW = 0.25  # face width / frame width — medium close-up
FACE_FRACTION_FOLLOW = 0.15  # stage medium shot (upper body reads)
FACE_TOP = 0.42  # the face rides this high in the frame (0.5 = dead center)
MAX_SCALE = 3.0  # upscale bound (source-resolution honesty)

MIN_DWELL_SECONDS = 1.2  # 防眩晕: shortest shot a switch may create
SWITCH_LEAD_SECONDS = 0.2  # 切提前: the cut lands just before the turn starts

FOLLOW_INTERVAL_SECONDS = 0.5  # at most one keyframe per this
FOLLOW_DEADZONE = 0.08  # fraction of the window width the subject may drift
FOLLOW_SLEW = 0.15  # max center movement per emitted keyframe (window widths)
FOLLOW_EVERY_FRAMES = 3  # dense detection tier (ADR-045: 3~5 帧一检出轨迹)


def _aspect_ratio(aspect: str, src_w: int, src_h: int) -> float:
    """Composition width/height ratio (window shape) for an aspect tier."""
    return {"9:16": 1080 / 1920, "1:1": 1.0, "16:9": 1920 / 1080}.get(
        aspect, src_w / src_h
    )


def frame_window(
    cx: float,
    cy: float,
    face_w: float,
    src_w: int,
    src_h: int,
    ar: float,
    face_fraction: float,
    max_scale: float = MAX_SCALE,
) -> dict[str, float]:
    """Normalized crop value (window-center semantics) framing a face.

    The scale-1 window is the largest ``ar``-aspect region inside the source
    (the cover fit); scale zooms in from there. The center is clamped so the
    window never leaves the frame (no black edges, ever).
    """
    vis_w = min(src_w, src_h * ar)  # scale-1 window width in source px
    win_w = min(max(face_w / face_fraction, vis_w / max_scale), vis_w)
    scale = vis_w / win_w
    win_h = win_w / ar
    cx = min(max(cx, win_w / 2), src_w - win_w / 2)
    # FACE_TOP placement: the window center sits BELOW the face center.
    cy = cy + (0.5 - FACE_TOP) * win_h
    cy = min(max(cy, win_h / 2), src_h - win_h / 2)
    return {
        "x": round(cx / src_w, 6),
        "y": round(cy / src_h, 6),
        "scale": round(scale, 6),
    }


@dataclass
class _Window:
    start: float
    end: float


def _kept_windows(spec: dict) -> list[_Window]:
    """Kept MAIN-SOURCE segment windows, SOURCE-ORDERED: crop decisions are
    source-timeline facts — an output-side reorder must not change them
    (dedupe / window-head backdate / the final sort all walk source time).
    Hetero donor segments are skipped: their seconds live in the donor's
    timeline — a main-source crop keyframe would sample wrong there (the
    last keyframe simply holds through them). Overlapping windows merge into
    their union: an overlap is one continuous shown range — keeping the
    split would let the shared boundary emit duplicate-t keyframes (the
    strictly-ascending contract rejects them) and detect the overlap twice.
    """
    out = []
    for s in spec.get("segments") or []:
        if s.get("hidden") or s.get("asset_id") or s.get("url"):
            continue
        out.append(_Window(start=float(s["start"]), end=float(s["end"])))
    out.sort(key=lambda w: (w.start, w.end))
    merged: list[_Window] = []
    for w in out:
        if merged and w.start < merged[-1].end:
            merged[-1].end = max(merged[-1].end, w.end)
        else:
            merged.append(w)
    return merged


# ---- interview_switch ------------------------------------------------------


def _interview_keyframes(
    turns: list[dict[str, Any]],
    windows: list[_Window],
    anchors: dict[str, _Slot],
    src_w: int,
    src_h: int,
    ar: float,
) -> list[dict[str, float]]:
    """One keyframe per speaker switch: at the incoming turn's start (led by
    SWITCH_LEAD), framing that speaker's anchor. Dwell-filtered."""
    out: list[dict[str, float]] = []
    last_speaker: str | None = None
    prev_end = 0.0
    for w in windows:
        first_in_window = True
        for turn in turns:
            t0, t1 = max(turn["start"], w.start), min(turn["end"], w.end)
            if t1 - t0 < MIN_DWELL_SECONDS:
                continue
            speaker = turn["speaker"]
            anchor = anchors.get(speaker)
            if anchor is None or anchor.n == 0:
                continue
            t = max(turn["start"] - SWITCH_LEAD_SECONDS, w.start)
            if out and speaker == last_speaker:
                continue  # same-speaker run: the framing already holds
            # No prior framing anywhere → open the window ON the speaker
            # (no lead room before a window edge).
            if not out and t > w.start:
                t = w.start
            if first_in_window and out and t <= w.start + 1e-9:
                # A cut must LAND framed: the sampler eases into a keyframe
                # over CROP_EASE_SECONDS, so a keyframe sitting exactly at a
                # window head would open the new segment with 8 frames of the
                # previous speaker's framing. Backdate into the source gap
                # (free — nothing shows it); source-contiguous windows keep
                # the cut-point ease (clamped at the previous window's end).
                t = max(w.start - CROP_EASE_SECONDS, prev_end)
            kf = frame_window(
                anchor.cx, anchor.cy, anchor.w, src_w, src_h, ar,
                FACE_FRACTION_INTERVIEW,
            )
            out.append({"t": round(t, 3), **kf})
            last_speaker = speaker
            first_in_window = False
        prev_end = w.end
    return out


# ---- speaker_follow --------------------------------------------------------


def _follow_keyframes(
    video_path: Path,
    windows: list[_Window],
    src_w: int,
    src_h: int,
    fps: float,
    ar: float,
) -> list[dict[str, float]]:
    """Dense track → deadzone/slew-capped keyframes. Detection at the native
    tier (spike: 640 misses far faces, native hits 99.9%), tiles on a miss."""
    tiled = _detect_tiled()

    def candidates(frame: np.ndarray) -> list[FaceDetection]:
        det = detect_faces(frame, (src_w, src_h), score_threshold=0.6)
        return det if det else tiled(frame)

    out: list[dict[str, float]] = []
    prev_end = 0.0
    for w in windows:
        # [start, end) — an inclusive end would collide with the next
        # window's first frame on the same t (strictly-ascending contract).
        f0, f1 = int(w.start * fps), int(w.end * fps)
        points: list[tuple[float, FaceDetection]] = []
        last_c: tuple[float, float] | None = None
        for f_idx, frame in _frames_every(video_path, step=FOLLOW_EVERY_FRAMES, start_f=f0, end_f=f1):
            cands = candidates(frame)
            if not cands:
                continue
            # Track inertia: with several faces, stay near the last position;
            # otherwise the strongest detection.
            if last_c is None:
                d = max(cands, key=lambda x: x.score)
            else:
                d = min(
                    cands,
                    key=lambda x: (x.center[0] - last_c[0]) ** 2 + (x.center[1] - last_c[1]) ** 2,
                )
            last_c = d.center
            points.append((f_idx / fps, d))
        if len(points) < 2:
            prev_end = w.end
            continue
        face_w = float(np.median([d.bbox[2] for _, d in points]))
        win_w = min(
            max(face_w / FACE_FRACTION_FOLLOW, min(src_w, src_h * ar) / MAX_SCALE),
            min(src_w, src_h * ar),
        )
        deadzone = FOLLOW_DEADZONE * win_w
        slew = FOLLOW_SLEW * win_w

        last_kf: tuple[float, float] | None = None
        last_emit_t = -1e9
        for t, d in points:
            cx, cy = d.center
            if last_kf is None:
                if out:
                    # Window head after a source gap: land the cut already
                    # framed (interview_switch 同款回退).
                    t = max(w.start - CROP_EASE_SECONDS, prev_end)
                target = (cx, cy)
            else:
                dx, dy = cx - last_kf[0], cy - last_kf[1]
                if abs(dx) < deadzone and abs(dy) < deadzone:
                    continue
                if t - last_emit_t < FOLLOW_INTERVAL_SECONDS:
                    continue
                # slew cap: move at most `slew` toward the target per keyframe
                step = min(1.0, slew / max(abs(dx), abs(dy), 1e-6))
                target = (last_kf[0] + dx * step, last_kf[1] + dy * step)
            kf = frame_window(target[0], target[1], face_w, src_w, src_h, ar, FACE_FRACTION_FOLLOW)
            out.append({"t": round(t, 3), **kf})
            last_kf = target
            last_emit_t = t
        prev_end = w.end
    return out


# ---- dispatch --------------------------------------------------------------


def compute_crop_track(
    video_path: Path,
    spec: dict,
    speaker_map: dict | None,
    mode: str,
) -> tuple[list[dict[str, float]] | None, str]:
    """The skill's single entry: (keyframes, resolved_mode). ``None`` =
    static_center — the caller clears any existing track and the clip's
    static crop speaks again; an empty list = the resolved mode found
    nothing honest to say (no interview turns, no trackable face, an
    undecodable source) — the caller leaves the spec untouched."""
    if mode == "static_center":
        return None, mode
    fps, _n, src_w, src_h = _probe(video_path)
    if fps <= 0 or src_w <= 0 or src_h <= 0:
        # An undecodable source has no frames to frame on — skip honestly
        # (also keeps a zero fps out of the frame-index math below).
        logger.warning("reframe_probe_failed", path=str(video_path))
        return [], mode
    ar = _aspect_ratio(str(spec.get("aspect") or "9:16"), src_w, src_h)
    windows = _kept_windows(spec)
    if not windows:
        return None, "static_center"

    kfs: list[dict[str, float]]
    if mode == "interview_switch":
        turns = (speaker_map or {}).get("turns") or []
        if (speaker_map or {}).get("form") != "interview" or not turns:
            return [], mode  # caller degrades: nothing honest to switch on
        slots, _detect, _rate = _bootstrap_slots(video_path)
        anchors = {"left": slots[0], "right": slots[1]}
        kfs = _interview_keyframes(turns, windows, anchors, src_w, src_h, ar)
    elif mode == "speaker_follow":
        kfs = _follow_keyframes(video_path, windows, src_w, src_h, fps, ar)
    else:
        raise ValueError(f"unknown reframe mode: {mode}")

    # Windows are generated source-ordered (_kept_windows); this sort is the
    # strictly-ascending contract's safety net, not the ordering mechanism.
    kfs.sort(key=lambda k: k["t"])
    # Equal-t collisions stay possible at exactly-touching window boundaries
    # (a contiguous-clamped backdate meeting a led turn on the same second) —
    # keep the LATER decision, matching the sampler's latest-wins semantics.
    # The contract validator never runs on the write path (model_copy), so
    # this is the only place a duplicate t can be stopped from poisoning the
    # spec (a duplicate fails every later ClipSpec validation → uneditable).
    deduped: list[dict[str, float]] = []
    for kf in kfs:
        if deduped and kf["t"] <= deduped[-1]["t"]:
            deduped[-1] = kf
        else:
            deduped.append(kf)
    kfs = deduped
    logger.info(
        "reframe_crop_track", mode=mode, windows=len(windows), keyframes=len(kfs)
    )
    return kfs, mode
