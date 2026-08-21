"""speaker_map — the asset-level who-speaks-when fact (ADR-045 D4).

VIDEO's second processor, chained after ASR in ``asset_processing.py``. The
form gate runs first so single-person material never pays for attribution:

- gate = whisper turn density (picks the M3 budget: 1 grid call for
  monologic material, a confirmation grid for dialogic/low-confidence) + an
  M3 3x3 frame grid judging people count and scene;
- ``interview`` → full attribution: mouth-ROI frame-diff energy per turn
  (the 08-19 spike's validated metric — 95.2% argmax / 100% confident on
  xy_1), ambiguous turns (energy ratio < 1.6) go to M3 strip arbitration,
  1-5 calls per asset cap, overflow falls back to the energy argmax;
- ``single`` → every turn attributed to the one speaker, zero extra compute;
- ``multi`` / ``unknown`` → no attribution (honest empty, consumers treat an
  absent/unattributed map as unknown).

AUDIO assets get no speaker_map at all: the attribution signal is visual
(mouth ROI) and audio diarization stays out (ADR-045 Alternatives).

Detection-space policy (spike-calibrated): interview bootstrap starts at the
640-wide tier and escalates 640 → native → 2x2 tiles (2x zoom) until the
two-face rate reaches 95%; the winning tier's detector is reused for the
attribution pass. Detection pixels only find boxes; every stored or rendered
coordinate is full-resolution source space. Turns shorter than
MIN_TURN_SECONDS are speech fragments and are dropped from the map (a
listener's "嗯" must not switch a camera).

Lands on ``Asset.meta.speaker_map``::

    {"version": 1,
     "form": "single" | "interview" | "multi" | "unknown",
     "speakers": [{"id": "left", "screen_hint": "left"}, ...],
     "turns": [{"start": 2.9, "end": 5.0, "speaker": "left"}, ...]}
"""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from app.agents.base import Agent
from app.models.schemas import MediaInput, MediaInputType, SpeakerArbitration, SpeakerFormGate

if TYPE_CHECKING:
    from app.models.tables import Asset
    from app.pipeline.asset_processing import ProcessResult

logger = structlog.get_logger()

SPEAKER_MAP_VERSION = 1

TURN_GAP = 0.6  # whisper word gap that cuts a turn (ADR-045)
MIN_TURN_SECONDS = 0.8  # shorter fragments are dropped from the map
ENERGY_RATIO = 1.6  # attribution confidence threshold (spike-validated)
TURN_FPS = 8  # energy sampling rate inside a turn
TWO_FACE_GATE = 0.95  # bootstrap two-face rate that stops tier escalation
ARBITRATION_CALL_CAP = 5  # ADR-045: 每片 1~5 次封顶

# A frame → detections callable in full-resolution coordinates (plain or tiled).
Detect = Callable[[np.ndarray], list["FaceDetection"]]  # string fwd-ref: the real import is deferred (import cycle — the tools door re-enters this closure)


# ------------------------------------------------------------ frame access --
# Frame-grid assembly / turn segmentation / window picking are 工序 — they
# live here (the processor), never in tools/ (ADR-045 D1; vision.py is the
# engine seam only).


def _probe(path: Path) -> tuple[float, int, int, int]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return fps, n, w, h


def _det_size(width: int, height: int, det_w: int) -> tuple[int, int]:
    """Detection space for a width tier, height rounded to /16."""
    return (det_w, max(16, round(det_w * height / width / 16) * 16))


def _frames_every(path: Path, step: int, start_f: int = 0, end_f: int | None = None):
    """Yield (frame_index, bgr) scanning sequentially every ``step`` frames."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    f = start_f
    end = end_f if end_f is not None else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    while f < end:
        ok, frame = cap.read()
        if not ok:
            break
        yield f, frame
        # A failed grab mid-skip = a corrupt packet: stop — resuming would
        # label later frames with indices ahead of their real stream
        # positions (keyframe times would drift late on damaged files).
        for _ in range(step - 1):
            if not cap.grab():
                cap.release()
                return
        f += step
    cap.release()


def _frame_at(path: Path, idx: int) -> np.ndarray:
    import cv2

    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"frame {idx} unreadable in {path}")
    return frame


def _detect_tiled(tile_det_w: int = 640) -> Detect:
    """远景小脸兜底: 2x2 tiles, each detected at a >=2x zoom, coords mapped
    back to full-frame space. Escalation stage only — 4 detect calls a frame."""

    from app.tools.vision import FaceDetection, detect_faces  # deferred: import cycle

    def detect(frame: np.ndarray) -> list[FaceDetection]:
        h, w = frame.shape[:2]
        out: list[FaceDetection] = []
        for ty in range(2):
            for tx in range(2):
                x0, y0 = tx * w // 2, ty * h // 2
                tile = frame[y0 : y0 + h // 2, x0 : x0 + w // 2]
                th, tw = tile.shape[:2]
                for d in detect_faces(tile, _det_size(tw, th, tile_det_w), score_threshold=0.6):
                    bx, by, bw, bh = d.bbox
                    lm = d.landmarks.copy()
                    lm[:, 0] += x0
                    lm[:, 1] += y0
                    out.append(
                        FaceDetection(
                            bbox=(bx + x0, by + y0, bw, bh), landmarks=lm, score=d.score
                        )
                    )
        return out

    return detect


def _plain_detect(size: tuple[int, int]) -> Detect:
    from app.tools.vision import detect_faces  # deferred: import cycle

    def detect(frame: np.ndarray) -> list["FaceDetection"]:
        return detect_faces(frame, size, score_threshold=0.6)

    return detect


def _jpeg_data_url(img: np.ndarray, quality: int = 80) -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


# ------------------------------------------------------------ turn segments --


def _words_to_turns(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Segment ASR words into speech turns (gap >= TURN_GAP cuts a turn)."""
    turns: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for w in words:
        start, end = float(w["start"]), float(w["end"])
        if cur is None or start - cur["end"] >= TURN_GAP:
            if cur is not None:
                turns.append(cur)
            cur = {"start": start, "end": end, "text": str(w["word"])}
        else:
            cur["end"] = end
            cur["text"] += str(w["word"])
    if cur is not None:
        turns.append(cur)
    return turns


# ------------------------------------------------------------- form gate ----


def _form_gate_assemble(grid: MediaInput):
    return {}, [grid]


speaker_form_gate: Agent[SpeakerFormGate] = Agent(
    name="speaker_form_gate",
    prompt="speaker_form_gate.j2",
    schema=SpeakerFormGate,
    system=(
        "You classify the visible speaker setup of a video from a frame grid. "
        "You only output valid JSON, with no additional commentary."
    ),
    temperature=0.0,
    assemble=_form_gate_assemble,
)


def _arbitrate_assemble(clip: MediaInput):
    return {}, [clip]


speaker_arbitrate: Agent[SpeakerArbitration] = Agent(
    name="speaker_arbitrate",
    prompt="speaker_arbitrate.j2",
    schema=SpeakerArbitration,
    system=(
        "You judge which interview participant is speaking in a short clip "
        "(audio + both faces visible). You only output valid JSON, with no "
        "additional commentary."
    ),
    temperature=0.0,
    assemble=_arbitrate_assemble,
)


def _frame_grid(path: Path, n_frames: int, offset: float = 0.0) -> np.ndarray:
    """3x3 grid of frames sampled evenly across the video (form-gate input);
    ``offset`` shifts the sampling phase for the confirmation pass."""
    import cv2

    picks = [int(n_frames * (i + 0.5 + offset) / 9) % max(n_frames, 1) for i in range(9)]
    tiles = []
    for idx in picks:
        frame = _frame_at(path, idx)
        h, w = frame.shape[:2]
        tiles.append(
            cv2.resize(frame, (320, max(1, round(320 * h / w))), interpolation=cv2.INTER_AREA)
        )
    rows = [cv2.hconcat(tiles[r * 3 : (r + 1) * 3]) for r in range(3)]
    return cv2.vconcat(rows)


async def _form_gate(path: Path, turns: list[dict[str, Any]]) -> str:
    """Decide the asset's speaker form. Turn density picks the M3 budget:
    monologic material (<=2 turns or median turn >= 20s) gets one grid call;
    dialogic material gets one confirmation grid when the first is unsure."""
    _fps, n_frames, _w, _h = _probe(path)

    durations = [t["end"] - t["start"] for t in turns]
    median_turn = float(np.median(durations)) if durations else 0.0
    monologic = len(turns) <= 2 or median_turn >= 20.0

    grid = MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/jpeg",
        data_url=_jpeg_data_url(await asyncio.to_thread(_frame_grid, path, n_frames)),
        caption="A 3x3 grid of frames sampled evenly across the video.",
    )
    verdict = await speaker_form_gate.call(grid=grid)
    if verdict.confidence == "low" and not monologic:
        grid2 = MediaInput(
            type=MediaInputType.IMAGE,
            mime="image/jpeg",
            data_url=_jpeg_data_url(await asyncio.to_thread(_frame_grid, path, n_frames, 0.5)),
            caption="A second 3x3 frame grid from the same video (shifted sampling).",
        )
        verdict = await speaker_form_gate.call(grid=grid2)

    if verdict.people == 2 and verdict.scene == "interview":
        return "interview"
    if verdict.people == 1:
        return "single"
    if verdict.people >= 3:
        return "multi"
    return "unknown"


# ------------------------------------------------------ interview attribution


@dataclass
class _Slot:
    """One static-camera person's running position anchor."""

    cx: float
    cy: float
    w: float
    n: int = 0

    def update(self, d: FaceDetection) -> None:
        (cx, cy), bw = d.center, d.bbox[2]
        k = 1 / min(self.n + 1, 50)
        self.cx += (cx - self.cx) * k
        self.cy += (cy - self.cy) * k
        self.w += (bw - self.w) * k
        self.n += 1


def _assign(det: list[FaceDetection], slots: list[_Slot]) -> list[FaceDetection | None]:
    """Assign a frame's detections to slots by center distance (<= 1.5x width)."""
    out: list[FaceDetection | None] = [None] * len(slots)
    for d in det:
        cx, _ = d.center
        dists = [abs(cx - s.cx) for s in slots]
        i = int(np.argmin(dists))
        if dists[i] <= 1.5 * slots[i].w and out[i] is None:
            out[i] = d
    return out


def _bootstrap_slots(path: Path) -> tuple[list[_Slot], Detect, float]:
    """Sparse 2s scan anchoring the left/right persons, escalating detection
    tiers (640 → native → 2x2 tiles) until the two-face rate reaches 95%.
    Returns the slots, the winning tier's detector, and its two-face rate."""
    fps, _n, w, h = _probe(path)
    candidates: list[tuple[str, Detect]] = [("640", _plain_detect(_det_size(w, h, 640)))]
    if w > 640:
        candidates.append(("native", _plain_detect((w, h))))
    candidates.append(("tiles", _detect_tiled()))

    best: tuple[list[_Slot], Detect, float] | None = None
    for name, detect in candidates:
        slots = [
            _Slot(cx=w * 0.25, cy=h * 0.4, w=w * 0.05),
            _Slot(cx=w * 0.75, cy=h * 0.4, w=w * 0.05),
        ]
        scanned = two_face = 0
        for _, frame in _frames_every(path, step=max(1, int(2 * fps))):
            det = detect(frame)
            scanned += 1
            if len(det) >= 2:
                two_face += 1
            for d in det:
                (slots[0] if d.center[0] < w / 2 else slots[1]).update(d)
        rate = two_face / max(scanned, 1)
        logger.info("speaker_map_bootstrap", tier=name, two_face_rate=round(rate, 3))
        if best is None or rate > best[2]:
            best = (slots, detect, rate)
        if rate >= TWO_FACE_GATE:
            return slots, detect, rate
    assert best is not None  # candidates is never empty
    logger.warning("speaker_map_bootstrap_low", two_face_rate=round(best[2], 3))
    return best


def _mouth_energy(frames: list[np.ndarray], det: list[FaceDetection | None]) -> float:
    """Median consecutive-frame absdiff inside the mouth ROI (gray, 64x32)."""
    import cv2

    rois: list[np.ndarray] = []
    for frame, d in zip(frames, det):
        if d is None:
            continue
        x, y, w, h = d.mouth_roi()
        fh, fw = frame.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(fw, x + w), min(fh, y + h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        roi = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        rois.append(cv2.resize(roi, (64, 32), interpolation=cv2.INTER_AREA))
    if len(rois) < 3:
        return 0.0
    return float(np.median([float(np.mean(cv2.absdiff(a, b))) for a, b in zip(rois, rois[1:])]))


def _turn_energies(
    path: Path,
    turns: list[dict[str, Any]],
    slots: list[_Slot],
    detect: Detect,
) -> list[dict[str, Any]]:
    """Per-turn mouth energy per slot + argmax attribution + confidence."""
    fps, _n, _w, _h = _probe(path)
    out: list[dict[str, Any]] = []
    for ti, turn in enumerate(turns):
        f0, f1 = int(turn["start"] * fps), int(turn["end"] * fps)
        step = max(1, round(fps / TURN_FPS))
        frames: list[np.ndarray] = []
        per_slot: list[list[FaceDetection | None]] = [[], []]
        for _, frame in _frames_every(path, step=step, start_f=f0, end_f=f1 + 1):
            frames.append(frame)
            a = _assign(detect(frame), slots)
            per_slot[0].append(a[0])
            per_slot[1].append(a[1])
        e = [_mouth_energy(frames, per_slot[0]), _mouth_energy(frames, per_slot[1])]
        presence = [
            sum(1 for d in per_slot[s] if d is not None) / max(len(frames), 1)
            for s in (0, 1)
        ]
        best = int(np.argmax(e))
        ratio = e[best] / max(e[1 - best], 1e-6)
        confident = ratio >= ENERGY_RATIO and presence[best] >= 0.5
        out.append(
            {
                "turn": ti,
                "start": turn["start"],
                "end": turn["end"],
                "slot": best,
                "ratio": ratio,
                "confident": confident,
            }
        )
    return out


def _cut_turn_clip(
    path: Path, start: float, end: float, max_seconds: float = 5.0, width: int = 960
) -> bytes | None:
    """Cut a mid-turn mp4 (video + mono audio, PyAV) for M3 arbitration.

    The audio is the decisive signal (lip-sync matching beats frame grids —
    08-19: strips went 60%, clips 3/3); the width stays near-native because
    aggressive downscales shrink faces below M3's lip-read floor (480-wide
    misjudged a turn that 960-wide gets right). None when the source has no
    audio.
    """
    import av

    fps, _n, src_w, src_h = _probe(path)
    width = min(width, src_w)
    dur = min(max_seconds, end - start)
    mid = (start + end) / 2
    begin = max(0.0, mid - dur / 2)
    stop = begin + dur

    inp = av.open(str(path))
    if not inp.streams.audio:
        inp.close()
        return None
    buf = io.BytesIO()
    out = av.open(buf, "w", format="mp4")
    height = int(src_h * (width / src_w)) & ~1
    vout = out.add_stream("h264", rate=max(1, round(fps)))
    vout.width, vout.height = width, height
    vout.pix_fmt = "yuv420p"
    aout = out.add_stream("aac", rate=44100)
    aout.layout = "mono"

    vin = inp.streams.video[0]
    inp.seek(int(begin / vin.time_base), stream=vin)
    for frame in inp.decode(video=0):
        t = float(frame.pts * vin.time_base)
        if t < begin:
            continue
        if t > stop:
            break
        for packet in vout.encode(frame.reformat(width=width, height=height)):
            out.mux(packet)
    ain = inp.streams.audio[0]
    inp.seek(int(begin / ain.time_base), stream=ain)
    for frame in inp.decode(audio=0):
        t = float(frame.pts * ain.time_base)
        if t < begin:
            continue
        if t > stop:
            break
        for packet in aout.encode(frame):
            out.mux(packet)
    for packet in vout.encode():
        out.mux(packet)
    for packet in aout.encode():
        out.mux(packet)
    out.close()
    inp.close()
    return buf.getvalue()


async def _arbitrate(
    path: Path,
    rows: list[dict[str, Any]],
) -> dict[int, str]:
    """M3 video-clip arbitration for ambiguous turns, hardest-first (lowest
    energy ratio), 1-5 calls per asset (ADR-045 cap). Returns turn-index →
    speaker id; the caller falls back to the energy argmax for the rest."""
    verdicts: dict[int, str] = {}
    hardest_first = sorted(rows, key=lambda r: r["ratio"])
    overflow = max(0, len(hardest_first) - ARBITRATION_CALL_CAP)
    for row in hardest_first[:ARBITRATION_CALL_CAP]:
        clip = await asyncio.to_thread(_cut_turn_clip, path, row["start"], row["end"])
        if clip is None:
            continue
        media = MediaInput(
            type=MediaInputType.VIDEO,
            mime="video/mp4",
            data_url="data:video/mp4;base64," + base64.b64encode(clip).decode(),
        )
        result = await speaker_arbitrate.call(clip=media)
        if result.speaker in ("left", "right"):
            verdicts[row["turn"]] = result.speaker
    if overflow > 0:
        logger.warning("speaker_map_arbitration_overflow", fallback_turns=overflow)
    return verdicts


# ---------------------------------------------------------------- processor --


async def build_speaker_map(
    asset_file: Path, words: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the speaker_map for a VIDEO asset's local file. CPU-bound
    detection passes run in threads; M3 calls stay async."""
    turns = _words_to_turns(words)
    form = await _form_gate(asset_file, turns)
    logger.info("speaker_map_form", form=form, turns=len(turns))

    real_turns = [t for t in turns if t["end"] - t["start"] >= MIN_TURN_SECONDS]

    if form == "single":
        return {
            "version": SPEAKER_MAP_VERSION,
            "form": form,
            "speakers": [{"id": "main", "screen_hint": "full"}],
            "turns": [
                {"start": round(t["start"], 3), "end": round(t["end"], 3), "speaker": "main"}
                for t in real_turns
            ],
        }
    if form != "interview" or not real_turns:
        return {
            "version": SPEAKER_MAP_VERSION,
            "form": form,
            "speakers": [],
            "turns": [],
        }

    slots, detect, _rate = await asyncio.to_thread(_bootstrap_slots, asset_file)
    rows = await asyncio.to_thread(_turn_energies, asset_file, real_turns, slots, detect)
    ambiguous = [r for r in rows if not r["confident"]]
    verdicts = await _arbitrate(asset_file, ambiguous) if ambiguous else {}

    speaker_ids = ["left", "right"]
    out_turns: list[dict[str, Any]] = []
    for r in rows:
        if r["confident"]:
            speaker = speaker_ids[r["slot"]]
        else:
            # M3 verdict, else the energy argmax as the last-resort fallback.
            speaker = verdicts.get(r["turn"]) or speaker_ids[r["slot"]]
        out_turns.append(
            {"start": round(r["start"], 3), "end": round(r["end"], 3), "speaker": speaker}
        )
    return {
        "version": SPEAKER_MAP_VERSION,
        "form": "interview",
        "speakers": [
            {"id": "left", "screen_hint": "left"},
            {"id": "right", "screen_hint": "right"},
        ],
        "turns": out_turns,
    }


async def speaker_map_processor(asset: Asset, prior: ProcessResult) -> ProcessResult:
    """VIDEO's second processor (after ASR). Needs the ASR words from the
    prior result; a gate failure must never fail the asset — ASR's outputs
    are already in hand, so any speaker_map error degrades to no map."""
    from app.pipeline.asset_processing import ProcessResult
    from app.tools.storage import download_to_temp

    words = (prior.meta or {}).get("words") or []
    if not asset.file_url:
        return ProcessResult()
    path = await download_to_temp(asset.file_url)
    if path is None:
        return ProcessResult()
    try:
        speaker_map = await build_speaker_map(path, words)
        return ProcessResult(meta={"speaker_map": speaker_map})
    except Exception as e:  # noqa: BLE001 — degrade to no map, keep ASR's result
        logger.error("speaker_map_failed", asset_id=str(asset.id), error=str(e))
        return ProcessResult()
    finally:
        path.unlink(missing_ok=True)
