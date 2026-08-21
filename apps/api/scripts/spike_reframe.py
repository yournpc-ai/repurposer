"""Reframe spike (ADR-045 前置闸): dual validation on the curated samples.

- xy_1 (two-person static interview): YuNet detection rate + mouth-energy
  turn attribution, with blind montage sheets for manual ground-truthing.
- xy_2 (single-person stage talk): tracking continuity — detection rate,
  miss streaks, center-jump distribution, tier escalation recovery.

Detection-space policy under calibration: interview 640-wide tier, stage
native (960 here) tier, 1280 upscale as the small-face escalation (the 2x2
tile fallback's cheap cousin — same effective zoom, one detect call).

Usage:
  uv run python scripts/spike_reframe.py asr-xy1        # whisper -> words cache
  uv run python scripts/spike_reframe.py attribute-xy1  # turns + attribution + montages
  uv run python scripts/spike_reframe.py track-xy2      # continuity metrics
  uv run python scripts/spike_reframe.py score-xy1 L,R,R,...  # score blind labels
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app.providers.vision import FaceDetection, detect_faces

XY1 = "/Users/sylas/xy_1.mp4"
XY2 = "/Users/sylas/xy_2.mp4"
OUT = Path("/tmp/spike")
WORDS_CACHE = OUT / "xy1_words.json"
PRED_CACHE = OUT / "xy1_predictions.json"

TURN_GAP = 0.6  # whisper word gap that cuts a turn (ADR-045)
ENERGY_RATIO = 1.6  # attribution confidence threshold (initial, tune on film)
TURN_FPS = 8  # energy sampling rate inside a turn


# ---------------------------------------------------------------- frames ----


def probe(path: str) -> tuple[float, int, int, int]:
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return fps, n, w, h


def det_size(width: int, height: int, det_w: int) -> tuple[int, int]:
    """Detection space for a given width tier, height rounded to /16."""
    det_h = max(16, round(det_w * height / width / 16) * 16)
    return (det_w, det_h)


def frames_every(path: str, step: int, start_f: int = 0, end_f: int | None = None):
    """Yield (frame_index, bgr) scanning sequentially every `step` frames."""
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    f = start_f
    end = end_f if end_f is not None else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    while f < end:
        ok, frame = cap.read()
        if not ok:
            break
        yield f, frame
        for _ in range(step - 1):
            if not cap.grab():
                break
        f += step
    cap.release()


def frame_at(path: str, idx: int) -> np.ndarray:
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    cap.release()
    assert ok, f"frame {idx} unreadable"
    return frame


# ---------------------------------------------------------------- xy1 ASR ---


def asr_xy1() -> None:
    """Transcribe xy_1 with the production ASR seam and cache word timestamps."""
    from app.providers.asr import transcribe

    result = transcribe(Path(XY1))
    WORDS_CACHE.write_text(json.dumps(result))
    words = result["words"]
    print(f"language={result['language']} duration={result['duration']:.1f}s words={len(words)}")
    print("transcript head:", result["transcript"][:200])


def load_turns() -> list[dict]:
    data = json.loads(WORDS_CACHE.read_text())
    words = data["words"]
    turns: list[dict] = []
    cur: dict | None = None
    for w in words:
        if cur is None or w["start"] - cur["end"] >= TURN_GAP:
            if cur is not None:
                turns.append(cur)
            cur = {"start": w["start"], "end": w["end"], "text": w["word"]}
        else:
            cur["end"] = w["end"]
            cur["text"] += w["word"]
    if cur is not None:
        turns.append(cur)
    return turns


# ----------------------------------------------------- xy1 mouth attribution


@dataclass
class Slot:
    """One static-camera person's running position anchor."""

    cx: float
    cy: float
    w: float
    n: int = 0

    def update(self, d: FaceDetection) -> None:
        (cx, cy), bw = d.center, d.bbox[2]
        k = 1 / min(self.n + 1, 50)  # slow-running average
        self.cx += (cx - self.cx) * k
        self.cy += (cy - self.cy) * k
        self.w += (bw - self.w) * k
        self.n += 1


def mouth_energy(frames: list[np.ndarray], det: list[FaceDetection | None]) -> float:
    """Median consecutive-frame absdiff inside the mouth ROI (gray, normalized
    to 64x32). `det[i]` is the slot's detection in frames[i] (None = missed)."""
    rois: list[np.ndarray] = []
    for frame, d in zip(frames, det):
        if d is None:
            continue
        x, y, w, h = d.mouth_roi()
        H, W = frame.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        roi = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        rois.append(cv2.resize(roi, (64, 32), interpolation=cv2.INTER_AREA))
    if len(rois) < 3:
        return 0.0
    diffs = [
        float(np.mean(cv2.absdiff(a, b))) for a, b in zip(rois, rois[1:])
    ]
    return float(np.median(diffs))


def assign(det: list[FaceDetection], slots: list[Slot]) -> list[FaceDetection | None]:
    """Assign a frame's detections to slots by center distance (<= 1.5x slot width)."""
    out: list[FaceDetection | None] = [None] * len(slots)
    for d in det:
        cx, _ = d.center
        dists = [abs(cx - s.cx) for s in slots]
        i = int(np.argmin(dists))
        if dists[i] <= 1.5 * slots[i].w and out[i] is None:
            out[i] = d
    return out


def attribute_xy1() -> None:
    fps, n_frames, W, H = probe(XY1)
    print(f"xy1: {W}x{H} fps={fps:.2f} dur={n_frames / fps:.1f}s")
    turns = load_turns()
    print(f"turns: {len(turns)}")

    size = det_size(W, H, 640)

    # Pass 1: bootstrap slot anchors from a sparse scan (1 per 2s).
    left = Slot(cx=W * 0.25, cy=H * 0.4, w=W * 0.05)
    right = Slot(cx=W * 0.75, cy=H * 0.4, w=W * 0.05)
    slots = [left, right]
    det_frames = 0
    two_face_frames = 0
    for _, frame in frames_every(XY1, step=int(2 * fps)):
        det = detect_faces(frame, size, score_threshold=0.6)
        det_frames += 1
        if len(det) >= 2:
            two_face_frames += 1
        for d in det:
            (slots[0] if d.center[0] < W / 2 else slots[1]).update(d)
    print(
        f"detection rate (sparse, 640 tier): {two_face_frames}/{det_frames} "
        f"= {two_face_frames / max(det_frames, 1):.1%} frames with both faces"
    )
    print(f"slot anchors: L=({left.cx:.0f},{left.cy:.0f},w{left.w:.0f}) "
          f"R=({right.cx:.0f},{right.cy:.0f},w{right.w:.0f})")

    # Pass 2: per-turn energy attribution.
    predictions = []
    for ti, turn in enumerate(turns):
        f0, f1 = int(turn["start"] * fps), int(turn["end"] * fps)
        step = max(1, round(fps / TURN_FPS))
        frames: list[np.ndarray] = []
        dets: list[list[FaceDetection]] = []
        for _, frame in frames_every(XY1, step=step, start_f=f0, end_f=f1 + 1):
            frames.append(frame)
            dets.append(detect_faces(frame, size, score_threshold=0.6))
        per_slot: list[list[FaceDetection | None]] = [[], []]
        for det in dets:
            a = assign(det, slots)
            per_slot[0].append(a[0])
            per_slot[1].append(a[1])
        e = [mouth_energy(frames, per_slot[0]), mouth_energy(frames, per_slot[1])]
        presence = [
            sum(1 for d in per_slot[s] if d is not None) / max(len(frames), 1)
            for s in (0, 1)
        ]
        best = int(np.argmax(e))
        other = 1 - best
        ratio = e[best] / max(e[other], 1e-6)
        confident = ratio >= ENERGY_RATIO and presence[best] >= 0.5
        predictions.append(
            {
                "turn": ti,
                "start": round(turn["start"], 2),
                "end": round(turn["end"], 2),
                "text": turn["text"][:80],
                "pred": "L" if best == 0 else "R",
                "confident": confident,
                "e_left": round(e[0], 2),
                "e_right": round(e[1], 2),
                "presence": [round(p, 2) for p in presence],
                "frames": [int((f0 + (f1 - f0) * q)) for q in (0.25, 0.5, 0.75)],
            }
        )
    PRED_CACHE.write_text(json.dumps(predictions, ensure_ascii=False, indent=1))
    conf = sum(1 for p in predictions if p["confident"])
    print(f"attributed: {conf}/{len(predictions)} confident (ratio>={ENERGY_RATIO})")

    # Blind montage sheets: 3 face crops per slot per turn, row index only.
    sheet_rows: list[np.ndarray] = []
    row_h = 96
    for p in predictions:
        crops: list[np.ndarray] = []
        for fi in p["frames"]:
            frame = frame_at(XY1, fi)
            det = detect_faces(frame, size, score_threshold=0.6)
            a = assign(det, slots)
            for s in (0, 1):
                d = a[s]
                if d is None:
                    crops.append(np.zeros((row_h, row_h, 3), dtype=np.uint8))
                    continue
                x, y, w, h = (int(v) for v in d.bbox)
                pad = int(0.5 * w)
                x0, y0 = max(0, x - pad), max(0, y - pad)
                x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
                crop = frame[y0:y1, x0:x1]
                scale = row_h / crop.shape[0]
                crops.append(
                    cv2.resize(
                        crop,
                        (max(1, int(crop.shape[1] * scale)), row_h),
                        interpolation=cv2.INTER_AREA,
                    )
                )
        row = cv2.hconcat([_pad_h(c, row_h) for c in crops])
        cv2.putText(
            row, f"#{p['turn']}", (4, row_h - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2,
        )
        sheet_rows.append(row)
    rows_per_sheet = 12
    for si in range(0, len(sheet_rows), rows_per_sheet):
        chunk = sheet_rows[si : si + rows_per_sheet]
        width = max(r.shape[1] for r in chunk)
        sheet = cv2.vconcat([_pad_w(r, width) for r in chunk])
        cv2.imwrite(str(OUT / f"sheet_{si // rows_per_sheet:02d}.jpg"), sheet)
    print(f"sheets: {(len(sheet_rows) + rows_per_sheet - 1) // rows_per_sheet}")


def _pad_h(img: np.ndarray, h: int) -> np.ndarray:
    if img.shape[0] == h:
        return img
    return cv2.copyMakeBorder(img, 0, h - img.shape[0], 0, 0, cv2.BORDER_CONSTANT)


def _pad_w(img: np.ndarray, w: int) -> np.ndarray:
    if img.shape[1] == w:
        return img
    return cv2.copyMakeBorder(img, 0, 0, 0, w - img.shape[1], cv2.BORDER_CONSTANT, value=(32, 32, 32))


def score_xy1(labels: list[str]) -> None:
    """Compare blind labels (L/R/? per turn) with the energy predictions."""
    preds = json.loads(PRED_CACHE.read_text())
    assert len(labels) == len(preds), f"{len(labels)} labels vs {len(preds)} turns"
    n_conf = n_hit = n_all_hit = 0
    misses = []
    for p, lab in zip(preds, labels):
        if lab == "?":
            continue
        hit = lab == p["pred"]
        n_all_hit += hit
        if p["confident"]:
            n_conf += 1
            n_hit += hit
            if not hit:
                misses.append(p["turn"])
    graded = sum(1 for l in labels if l != "?")
    print(f"accuracy (all labeled): {n_all_hit}/{graded} = {n_all_hit / max(graded,1):.1%}")
    print(f"accuracy (confident only): {n_hit}/{n_conf} = {n_hit / max(n_conf,1):.1%}")
    print(f"confident misses: {misses}")
    for p, lab in zip(preds, labels):
        if lab != "?" and lab != p["pred"]:
            print(
                f"  MISS turn {p['turn']} [{p['start']}-{p['end']}] pred={p['pred']} "
                f"truth={lab} eL={p['e_left']} eR={p['e_right']} conf={p['confident']} "
                f"text={p['text'][:40]}"
            )


# ------------------------------------------------------------- xy2 tracking -


def track_xy2() -> None:
    fps, n_frames, W, H = probe(XY2)
    dur = n_frames / fps
    print(f"xy2: {W}x{H} fps={fps:.2f} dur={dur:.1f}s frames={n_frames}")
    step = 3  # dense tier: every 3rd frame (ADR-045: 3~5 帧一检出轨迹)

    results: dict[int, dict[int, FaceDetection]] = {}
    for tier in (640, 960):
        size = det_size(W, H, tier)
        found: dict[int, FaceDetection] = {}
        for f_idx, frame in frames_every(XY2, step=step):
            det = detect_faces(frame, size, score_threshold=0.6)
            if det:
                # single-person stage: keep the best-scoring face
                found[f_idx] = max(det, key=lambda d: d.score)
        results[tier] = found
        sampled = len(range(0, n_frames, step))
        print(f"tier {tier}: detected {len(found)}/{sampled} = {len(found) / sampled:.1%}")
        _continuity(found, step)

    # Escalation: retry 960-tier misses at 1280.
    missed = [f for f in range(0, n_frames, step) if f not in results[960]]
    if missed:
        size = det_size(W, H, 1280)
        recovered = 0
        for f in missed:
            det = detect_faces(frame_at(XY2, f), size, score_threshold=0.6)
            if det:
                recovered += 1
        print(f"escalation 1280 on 960-misses: recovered {recovered}/{len(missed)}")


def _continuity(found: dict[int, "FaceDetection"], step: int) -> None:
    keys = sorted(found)
    if not keys:
        return
    # miss streaks (consecutive sampled frames with no detection)
    streaks: list[int] = []
    cur = 0
    for f in range(0, max(keys) + 1, step):
        if f in found:
            streaks.append(cur)
            cur = 0
        else:
            cur += 1
    streaks.append(cur)
    jumps = []
    for a, b in zip(keys, keys[1:]):
        if b - a != step:
            continue
        da, db = found[a], found[b]
        (ax, ay), (bx, by) = da.center, db.center
        dist = float(np.hypot(bx - ax, by - ay)) / max(da.bbox[2], 1.0)
        jumps.append(dist)
    j = np.array(jumps)
    print(
        f"  max miss streak: {max(streaks)} samples; center jump (face-width units) "
        f"p50={np.percentile(j, 50):.2f} p95={np.percentile(j, 95):.2f} max={j.max():.2f}"
    )


if __name__ == "__main__":
    mode = sys.argv[1]
    OUT.mkdir(exist_ok=True)
    if mode == "asr-xy1":
        asr_xy1()
    elif mode == "attribute-xy1":
        attribute_xy1()
    elif mode == "score-xy1":
        score_xy1(sys.argv[2].split(","))
    elif mode == "track-xy2":
        track_xy2()
    else:
        sys.exit(f"unknown mode {mode}")
