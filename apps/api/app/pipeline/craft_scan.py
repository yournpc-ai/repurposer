"""Craft scan — the decompiler's deterministic half (ADR-078 判词①).

Zero LLM by construction (验收断言「骨架确定性字段零 LLM 介入」): this
module imports no provider and never calls one — frames in, measurements
out. Shot segmentation / rhythm / aspect / the caption-band scan are
classic computer vision over decoded frames (PyAV decode, no system
ffmpeg — the asr.py precedent); the caption preset and color are a visual
NEAREST-NEIGHBOR best-fit over the contract enums (the captions.ts preset
ids / the palette below), never a free invention. The LLM half (music
mood / hook device / out-of-contract gaps) lives in
``pipeline/decompile.py`` — the two halves join at the CraftSkeleton
assembly there.

Family shape = prosody / visual_anchors: pure CPU-bound functions over
numpy frames, degrade-on-error at the caller, a ``--selftest`` at the
bottom. Everything here is unit-testable with synthetic frames — no video
fixture required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

CRAFT_SCAN_VERSION = 1

# ---- sampling ---------------------------------------------------------------
_SAMPLE_INTERVAL_S = 0.5  # 2 fps detection grid
_SAMPLE_MAX_FRAMES = 240  # beyond 2 min the grid stretches to fit
_DET_LONG_SIDE = 256  # detection-space cap (signatures/masks), aspect kept
_KEYFRAME_LONG_SIDE = 720  # the LLM's keyframes (decompile.py consumes)
_KEYFRAME_CAP = 8  # at most this many shot keyframes reach the LLM

# ---- shot detection ---------------------------------------------------------
# A cut = consecutive-frame HSV histogram correlation below the floor. The
# floor adapts to the video's own correlation spread (a talking head sits
# near 1.0; a montage swings) but never below the absolute floor; the
# sub-_MIN_SHOT_S merge then absorbs single-grid-tick dips (fast pans).
_CUT_CORR_FLOOR = 0.55
_CUT_CORR_RELATIVE_SIGMA = 4.0
_MIN_SHOT_S = 0.4  # shorter runs merge into the previous shot (cut artifacts)

# ---- caption band scan ------------------------------------------------------
# The scan window: lower-center of the frame, where burned captions live
# (title cards at the top are NOT this channel — the hook device is the
# LLM's judgment seat).
_BAND_Y0, _BAND_Y1 = 0.55, 0.95
_BAND_X0, _BAND_X1 = 0.06, 0.94
# A frame "carries a caption" when the text mask fills at least this share
# of the band AND spans at least this share of its width (a caption line is
# a wide contiguous run; speckle noise fails both).
_MIN_FILL = 0.0015
_MIN_SPAN = 0.15
# The video "has captions" when at least this share of sampled frames carry
# one (a montage's occasional title card stays under it).
_MIN_PRESENCE = 0.25
# Karaoke: within a stable line (bbox IoU high across consecutive frames),
# the saturated (highlight) share of the text mask sweeps upward.
_KARAOKE_MIN_IOU = 0.5
_KARAOKE_SWEEP_LO, _KARAOKE_SWEEP_HI = 0.2, 0.5
# Stacking: the text block's TOP edge climbs while the bottom holds (lines
# accumulate) across at least this many consecutive carrying frames.
_STACK_MIN_RUN = 3
_STACK_TOP_DRIFT_PX = 4  # in detection-space band pixels

# The caption text-color palette (best-fit targets — the snap keeps the
# skeleton honest: a measured color only ever lands as the nearest palette
# member, never a raw pixel value). Hex values are the contract's own
# vocabulary (ClipBrand.caption_color is a free hex; the palette is the
# enum-shaped discipline ADR-078 asks this channel to keep).
CAPTION_COLOR_PALETTE: dict[str, str] = {
    "white": "#FFFFFF",
    "yellow": "#FDE047",
    "green": "#22C55E",
    "cyan": "#22D3EE",
    "red": "#EF4444",
    "black": "#111111",
}

_ASPECT_TIERS = {"9:16": 9 / 16, "1:1": 1.0, "16:9": 16 / 9}


@dataclass
class SampledFrame:
    """One decoded frame on the sampling grid (detection space, BGR)."""

    t: float  # source second
    image: Any  # np.ndarray uint8 BGR, downscaled to _DET_LONG_SIDE


def aspect_of(width: int, height: int) -> str:
    """Nearest contract aspect tier by log-ratio distance (deterministic).

    The exemplar's OWN shape names the remix's target — "original" is not a
    tier here (the skeleton pins a concrete tier so the chain's aspect param
    has a real value to map).
    """
    if width <= 0 or height <= 0:
        return "9:16"
    ratio = width / height
    return min(_ASPECT_TIERS, key=lambda tier: abs(math.log(ratio / _ASPECT_TIERS[tier])))


def nearest_palette_color(rgb: tuple[float, float, float]) -> str:
    """Snap an RGB sample to the palette (nearest member by euclidean RGB)."""
    best_name, best_dist = "white", float("inf")
    for name, hexv in CAPTION_COLOR_PALETTE.items():
        pr, pg, pb = int(hexv[1:3], 16), int(hexv[3:5], 16), int(hexv[5:7], 16)
        dist = (rgb[0] - pr) ** 2 + (rgb[1] - pg) ** 2 + (rgb[2] - pb) ** 2
        if dist < best_dist:
            best_name, best_dist = name, dist
    return CAPTION_COLOR_PALETTE[best_name]


def _hist_signature(image: Any) -> Any:
    """HSV histogram signature of one detection-space frame (V included —
    a luminance jump with steady chroma, black↔white, IS a cut)."""
    import cv2  # lazy: heavy

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256]
    )
    cv2.normalize(hist, hist)
    return hist


def detect_shots(frames: list[SampledFrame], duration_s: float) -> list[dict[str, float]]:
    """Scene-cut segmentation: hard cuts via histogram-correlation drops.

    Gradual transitions (fades/dissolves) read as a short run of
    low-correlation frames and collapse into ONE cut at the run's head —
    v1 makes no cut/transition distinction (the observed transition EFFECT
    is the LLM's gap-list seat, not this channel's). Returns ``[{start,
    end}]`` spans covering [0, duration]; empty input ⇒ the single whole
    span.
    """
    if not frames:
        return [{"start": 0.0, "end": float(duration_s)}] if duration_s > 0 else []
    sigs = [_hist_signature(f.image) for f in frames]
    import cv2  # lazy: heavy

    corrs = [
        float(cv2.compareHist(sigs[i], sigs[i + 1], cv2.HISTCMP_CORREL))
        for i in range(len(sigs) - 1)
    ]
    if corrs:
        median = float(np.median(corrs))
        mad = float(np.median(np.abs(np.asarray(corrs) - median)))
        if mad > 1e-6:
            floor = median - _CUT_CORR_RELATIVE_SIGMA * mad * 1.4826
            floor = max(_CUT_CORR_FLOOR, min(floor, 0.98))
        else:
            floor = _CUT_CORR_FLOOR
    else:
        floor = _CUT_CORR_FLOOR
    cut_times = [frames[i + 1].t for i, c in enumerate(corrs) if c < floor]
    bounds = [0.0, *cut_times, float(duration_s)]
    shots = [
        {"start": bounds[i], "end": bounds[i + 1]} for i in range(len(bounds) - 1)
    ]
    # Merge sub-_MIN_SHOT_S runs into the previous shot (cut artifacts).
    merged: list[dict[str, float]] = []
    for shot in shots:
        if merged and shot["end"] - shot["start"] < _MIN_SHOT_S:
            merged[-1]["end"] = shot["end"]
        else:
            merged.append(dict(shot))
    return merged


def rhythm_of(shots: list[dict[str, float]], duration_s: float) -> dict[str, Any]:
    """Cut rhythm off the shot list (deterministic): count / cuts-per-minute
    / median shot length / the coarse pace class (<2s fast, ≤4s steady)."""
    count = len(shots)
    lengths = [max(0.0, s["end"] - s["start"]) for s in shots]
    median_s = float(np.median(lengths)) if lengths else 0.0
    cpm = (max(0, count - 1) / duration_s * 60.0) if duration_s > 0 else 0.0
    pace = "fast" if median_s < 2.0 else "steady" if median_s <= 4.0 else "slow"
    return {
        "shot_count": count,
        "cuts_per_minute": round(cpm, 1),
        "median_shot_seconds": round(median_s, 2),
        "pace": pace,
    }


def _caption_mask(band_bgr: Any) -> tuple[Any, Any, Any]:
    """One band crop → (text mask, saturated-only mask, saturated hue values).

    Text strokes are high-contrast against the video: near-white (low
    saturation, high value) or strongly saturated (a colored/highlight
    glyph). The saturated-only mask doubles as the karaoke channel's
    signal; its hue values feed the color read (kept per frame so the band
    images themselves never accumulate).
    """
    import cv2  # lazy: heavy

    hsv = cv2.cvtColor(band_bgr, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.int16)
    v = hsv[:, :, 2].astype(np.int16)
    bright = (v >= 180) & (s <= 90)
    saturated = (v >= 140) & (s >= 110)
    hues = hsv[:, :, 0][saturated].astype(np.float32)
    return bright | saturated, saturated, hues


def _mask_row(mask: Any) -> dict[str, Any] | None:
    """One frame's caption-mask summary: fill / span / bbox / saturated share.

    None = the frame carries no caption (fill or span under the floors).
    """
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    h, w = mask.shape
    fill = len(xs) / (h * w)
    span = (xs.max() - xs.min() + 1) / w
    if fill < _MIN_FILL or span < _MIN_SPAN:
        return None
    return {
        "x0": float(xs.min()),
        "x1": float(xs.max()),
        "y0": float(ys.min()),
        "y1": float(ys.max()),
        "fill": fill,
    }


def _bbox_iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"])
    area_b = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def analyze_caption_band(frames: list[SampledFrame]) -> dict[str, Any]:
    """Burned-caption scan (deterministic best-fit): presence, band position,
    palette-snapped text color, and the nearest preset member.

    The preset read keys off TEMPORAL behavior at the 2 fps grid: a karaoke
    highlight = the saturated share sweeps upward inside a stable line; a
    stack = the text block's top edge climbs while its bottom holds.
    Entrance animations (fade / pop / slide) are not resolvable at this
    grid — they collapse to ``clean-bottom`` (the calm static member),
    documented honest best-fit.
    """
    rows: list[tuple[float, dict[str, Any] | None, Any, Any]] = []
    hue_samples: list[Any] = []
    for frame in frames:
        img = frame.image
        h, w = img.shape[:2]
        band = img[
            int(h * _BAND_Y0) : int(h * _BAND_Y1),
            int(w * _BAND_X0) : int(w * _BAND_X1),
        ]
        if band.size == 0:
            rows.append((frame.t, None, None, None))
            continue
        text_mask, sat_mask, hues = _caption_mask(band)
        summary = _mask_row(text_mask)
        if summary is not None and hues.size:
            hue_samples.append(hues)
        rows.append((frame.t, summary, text_mask, sat_mask))

    carrying = [(t, s, tm, sm) for t, s, tm, sm in rows if s is not None]
    presence = len(carrying) / len(rows) if rows else 0.0
    present = presence >= _MIN_PRESENCE
    if not present:
        return {"present": False, "presence": round(presence, 3)}

    # Position: median text-block center across carrying frames, normalized
    # back to FULL-frame coordinates.
    ys = [(s["y0"] + s["y1"]) / 2 for _, s, _, _ in carrying]
    band_h = max(1, int(frames[0].image.shape[0] * (_BAND_Y1 - _BAND_Y0)))
    center_y_band = float(np.median(ys)) / band_h
    position_y = _BAND_Y0 + center_y_band * (_BAND_Y1 - _BAND_Y0)

    # Color: when saturated text is common, the circular mean hue snapped to
    # the palette (never a raw sample); otherwise white. Dark text on a
    # light chip stays unsampled in v1 — the bright channel reads it as
    # absent and the snap falls to white; honest best-fit, documented.
    sat_total = sum(int(sm.sum()) for _, _, _, sm in carrying)
    text_total = sum(int(tm.sum()) for _, _, tm, _ in carrying)
    color_rgb = (255.0, 255.0, 255.0)
    if text_total and sat_total / text_total >= 0.15 and hue_samples:
        all_hues = np.concatenate(hue_samples)
        # OpenCV hue h ∈ [0, 179] ↔ 2h degrees; circular mean over the ring.
        rad = all_hues * (2.0 * math.pi / 180.0)
        angle = math.atan2(float(np.sin(rad).mean()), float(np.cos(rad).mean()))
        color_rgb = _hue_to_rgb(math.degrees(angle) % 360.0)
    color_hex = nearest_palette_color(color_rgb)

    # Karaoke sweep: within a stable line (IoU-gated consecutive frames) the
    # saturated share climbs through the sweep band.
    karaoke = False
    run: list[tuple[dict[str, Any], Any, Any]] = []
    for _, s, tm, sm in carrying:
        if run and _bbox_iou(run[-1][0], s) >= _KARAOKE_MIN_IOU:
            run.append((s, tm, sm))
        else:
            run = [(s, tm, sm)]
        shares = [float(sm.sum()) / max(1.0, float(tm.sum())) for _, tm, sm in run]
        if len(shares) >= 3 and shares[0] <= _KARAOKE_SWEEP_LO and shares[-1] >= _KARAOKE_SWEEP_HI:
            karaoke = True
            break

    # Stacking: the text block's top edge climbs while the bottom holds over
    # a run of carrying frames.
    stacking = False
    drift_run = 1
    for (_, prev, _, _), (_, cur, _, _) in zip(carrying, carrying[1:]):
        if (
            prev["y1"] - _STACK_TOP_DRIFT_PX <= cur["y1"] <= prev["y1"] + _STACK_TOP_DRIFT_PX
            and cur["y0"] < prev["y0"] - _STACK_TOP_DRIFT_PX
        ):
            drift_run += 1
            if drift_run >= _STACK_MIN_RUN:
                stacking = True
                break
        else:
            drift_run = 1

    preset = (
        "karaoke-highlight" if karaoke else "stacking" if stacking else "clean-bottom"
    )
    return {
        "present": True,
        "presence": round(presence, 3),
        "position_y": round(position_y, 4),
        "color": color_hex,
        "preset": preset,
    }


def _hue_to_rgb(hue_deg: float) -> tuple[float, float, float]:
    """Pure hue (full saturation/value) → RGB, for palette snapping."""
    import colorsys

    r, g, b = colorsys.hsv_to_rgb((hue_deg % 360.0) / 360.0, 1.0, 1.0)
    return (r * 255.0, g * 255.0, b * 255.0)


def sample_video_frames(
    path: Path,
    duration_s: float | None,
    *,
    interval_s: float = _SAMPLE_INTERVAL_S,
    max_frames: int = _SAMPLE_MAX_FRAMES,
) -> list[SampledFrame]:
    """Decode a video onto the detection grid (PyAV, no system ffmpeg).

    Sequential decode, one frame kept per grid tick (nearest by timestamp),
    downscaled to the detection space. The grid stretches when the cap would
    overflow (a 10-minute case samples coarser, same cap). CPU-bound — the
    caller runs it in a thread.
    """
    import cv2  # lazy: heavy
    import av  # lazy: heavy; the faster-whisper dep precedent

    container = av.open(str(path))
    try:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            return []
        if duration_s is None or duration_s <= 0:
            duration_s = float(stream.duration * stream.time_base) if stream.duration else 0.0
        interval = interval_s
        if duration_s > 0 and duration_s / interval_s > max_frames:
            interval = duration_s / max_frames

        frames: list[SampledFrame] = []
        next_tick = 0.0
        for packet in container.demux(stream):
            for frame in packet.decode():
                t = float(frame.pts * stream.time_base) if frame.pts is not None else float(frame.time or 0.0)
                if t < next_tick:
                    continue
                img = frame.to_ndarray(format="bgr24")
                h, w = img.shape[:2]
                scale = _DET_LONG_SIDE / max(h, w)
                if scale < 1.0:
                    img = cv2.resize(
                        img,
                        (max(32, int(w * scale)), max(32, int(h * scale))),
                        interpolation=cv2.INTER_AREA,
                    )
                frames.append(SampledFrame(t=t, image=img))
                next_tick += interval
                if len(frames) >= max_frames:
                    return frames
        return frames
    finally:
        container.close()


def grab_keyframes(
    path: Path, shots: list[dict[str, float]]
) -> list[dict[str, Any]]:
    """One mid-shot keyframe per shot (cap _KEYFRAME_CAP, evenly spread) at
    the LLM's resolution — the decompile agent's visual evidence.

    Sequential decode grabbing the frame nearest each midpoint; returns
    ``[{"t": float, "png": bytes}]`` ordered by t.
    """
    import cv2  # lazy: heavy
    import av  # lazy: heavy

    if not shots:
        return []
    midpoints = [(s["start"] + s["end"]) / 2.0 for s in shots]
    if len(midpoints) > _KEYFRAME_CAP:
        idxs = np.linspace(0, len(midpoints) - 1, _KEYFRAME_CAP)
        picks = sorted({int(round(i)) for i in idxs})
        midpoints = [midpoints[i] for i in picks]

    container = av.open(str(path))
    try:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            return []
        out: list[dict[str, Any]] = []
        target_i = 0
        for packet in container.demux(stream):
            for frame in packet.decode():
                t = float(frame.pts * stream.time_base) if frame.pts is not None else float(frame.time or 0.0)
                if t < midpoints[target_i]:
                    continue
                img = frame.to_ndarray(format="bgr24")
                h, w = img.shape[:2]
                scale = _KEYFRAME_LONG_SIDE / max(h, w)
                if scale < 1.0:
                    img = cv2.resize(
                        img,
                        (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA,
                    )
                ok, buf = cv2.imencode(".png", img)
                if ok:
                    out.append({"t": round(t, 3), "png": buf.tobytes()})
                target_i += 1
                if target_i >= len(midpoints):
                    return out
        return out
    finally:
        container.close()


def scan_video(path: Path, duration_s: float | None) -> dict[str, Any]:
    """The full deterministic pass (CPU-bound, sync): frames → shots →
    rhythm → caption band → aspect. The skeleton's deterministic layer in
    one dict; the LLM keyframes are decompile.py's separate grab (it decides
    whether the LLM call happens at all)."""
    frames = sample_video_frames(path, duration_s)
    if not frames:
        return {}
    if duration_s is None or duration_s <= 0:
        duration_s = frames[-1].t
    h, w = frames[0].image.shape[:2]
    # Aspect from the SOURCE's real pixels, not the detection space (the
    # detection space preserved the ratio, so it agrees — but meta-probed
    # dims win when the caller passes them; see decompile.py).
    shots = detect_shots(frames, float(duration_s))
    return {
        "version": CRAFT_SCAN_VERSION,
        "duration_seconds": round(float(duration_s), 3),
        "aspect": aspect_of(w, h),
        "shots": shots,
        "rhythm": rhythm_of(shots, float(duration_s)),
        "captions": analyze_caption_band(frames),
    }


def _selftest() -> None:
    """Synthetic frames: an abrupt switch must read as a cut; a two-shot
    sequence must yield the right rhythm; the caption scan on a blank frame
    reads absent."""
    black = np.zeros((144, 256, 3), dtype=np.uint8)
    white = np.full((144, 256, 3), 255, dtype=np.uint8)
    frames = [
        *[SampledFrame(t=i * 0.5, image=black) for i in range(8)],
        *[SampledFrame(t=4.0 + i * 0.5, image=white) for i in range(8)],
    ]
    shots = detect_shots(frames, 8.0)
    assert len(shots) == 2, f"expected 2 shots, got {shots}"
    assert abs(shots[0]["end"] - 4.0) < 0.6
    rhythm = rhythm_of(shots, 8.0)
    assert rhythm["shot_count"] == 2 and rhythm["pace"] == "steady"
    assert aspect_of(1080, 1920) == "9:16"
    assert aspect_of(1920, 1080) == "16:9"
    assert aspect_of(1000, 1000) == "1:1"
    scan = analyze_caption_band(frames[:4])
    assert scan["present"] is False
    assert nearest_palette_color((250, 230, 70)) == CAPTION_COLOR_PALETTE["yellow"]
    print("craft_scan selftest OK")


if __name__ == "__main__":
    _selftest()
