"""speaker_map — the asset-level who-speaks-when fact (ADR-045 D4).

VIDEO's second processor, chained after ASR in ``asset_processing.py``. The
form gate runs first so single-person material never pays for attribution:

- gate = 人数本地聚合（逐帧人脸计数的多数决——个别帧出现第三人永不升级
  multi）+ M3 3x3 frame grid 只判 scene 语义（turn density picks the M3
  budget: 1 grid call for monologic material, a confirmation grid for
  dialogic/low-confidence）;
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
     "speakers": [{"id": "left", "screen_hint": "left",
                   "anchor": {"cx": …, "cy": …, "w": …, "n": …}}, ...],
     "turns": [{"start": 2.9, "end": 5.0, "speaker": "left"}, ...]}

``anchor`` (interview only) is the person's position anchor — reframe's
interview_switch reads it instead of re-running the bootstrap scan per clip
(剪辑复用座). The gate's raw scan rides the sibling ``Asset.meta.face_scan``
digest: per-sample face counts + derived face-free / extra-people spans
(B-roll / cutaway candidates) — one scan feeds the form verdict AND the
downstream editing facts.
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
from app.providers.vision import FaceDetection, detect_faces

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
SCAN_STRIDE_S = 2.0  # form-gate face-count sampling stride
SPAN_MIN_SAMPLES = 2  # a face_scan span needs this many consecutive samples

# A frame → detections callable in full-resolution coordinates (plain or tiled).
Detect = Callable[[np.ndarray], list[FaceDetection]]


# ------------------------------------------------------------ frame access --
# Frame-grid assembly / turn segmentation / window picking are 工序 — they
# live here (the processor), never in tools/ (ADR-045 D1; vision.py is the
# engine seam only).


def probe(path: Path) -> tuple[float, int, int, int]:
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


def frames_every(path: Path, step: int, start_f: int = 0, end_f: int | None = None):
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


def detect_tiled(tile_det_w: int = 640) -> Detect:
    """远景小脸兜底: 2x2 tiles, each detected at a >=2x zoom, coords mapped
    back to full-frame space. Escalation stage only — 4 detect calls a frame."""

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
    def detect(frame: np.ndarray) -> list[FaceDetection]:
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


async def _form_gate(path: Path, turns: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Decide the asset's speaker form + the reusable face-scan digest.
    形态是统计不是绝对值 (2026-10-06 用户拍板): the PEOPLE count comes from
    a local aggregate — every sampled frame's face count votes, the majority
    count wins, and a third person appearing in a few frames NEVER upgrades
    the form to multi (a real interview cut to audience shots is still an
    interview). The LLM grid keeps only what aggregation can't see: the
    SCENE semantics. Turn density still picks the M3 budget (monologic = one
    grid; dialogic + low confidence = one confirmation grid)."""
    _fps, n_frames, _w, _h = probe(path)

    durations = [t["end"] - t["start"] for t in turns]
    median_turn = float(np.median(durations)) if durations else 0.0
    monologic = len(turns) <= 2 or median_turn >= 20.0

    people, people_share, _faced, counts = await asyncio.to_thread(
        _people_count_by_majority, path
    )
    scan = _face_scan_digest(counts, people, people_share)

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

    # The verdict carries only scene + confidence — the people count is the
    # local aggregate above (the LLM sees 9 compressed frames and once
    # miscounted a two-host interview as 3+; the majority count is the law).
    if people == 2 and verdict.scene == "interview":
        return "interview", scan
    if people == 1:
        return "single", scan
    if people >= 3:
        return "multi", scan
    return "unknown", scan


def _detection_tiers(w: int, h: int) -> list[tuple[str, "Detect"]]:
    """The escalating detection tiers (bootstrap_slots' precedent, shared):
    640-wide → native (when wider) → 2x2 tiles. Small/far/masked faces that
    the 640 tier misses surface on the later tiers."""
    tiers: list[tuple[str, Detect]] = [("640", _plain_detect(_det_size(w, h, 640)))]
    if w > 640:
        tiers.append(("native", _plain_detect((w, h))))
    tiers.append(("tiles", detect_tiled()))
    return tiers


def _majority_people(counts: list[int]) -> tuple[int, float, int]:
    """Pure majority vote over per-sample face counts → (people, share,
    faced). Frames with zero faces (B-roll / 空镜) don't dilute the speaking
    setup; 3+ collapses to one bucket; a count needs a strict majority
    (>50%) of face-bearing samples to win — no majority reads as 0
    (unknown), never a coin flip."""
    from collections import Counter

    faced = [min(c, 3) for c in counts if c > 0]
    if not faced:
        return 0, 0.0, 0
    mode, mode_n = Counter(faced).most_common(1)[0]
    share = mode_n / len(faced)
    if share <= 0.5:
        return 0, share, len(faced)
    return mode, share, len(faced)


def _people_count_by_majority(path: Path) -> tuple[int, float, int, list[int]]:
    """The form gate's local people count: scan every SCAN_STRIDE_S and
    majority-vote (形态是统计不是绝对值 — a third person in a few frames
    never upgrades the form). Escalates detection tiers only while a tier
    sees ZERO faces anywhere (a pure-PPT deck's honest unknown still costs
    one 640 scan; the pricier tiers exist for small/far faces). Returns
    (people, share, faced, counts) — counts rides into the face_scan digest
    so downstream editing reuses the scan instead of re-running it."""
    fps, _n, w, h = probe(path)
    step = max(1, int(SCAN_STRIDE_S * fps))
    counts: list[int] = []
    tier = "640"
    for name, detect in _detection_tiers(w, h):
        counts = [len(detect(frame)) for _, frame in frames_every(path, step=step)]
        tier = name
        if any(c > 0 for c in counts):
            break
    people, share, faced = _majority_people(counts)
    logger.info(
        "speaker_form_scan",
        tier=tier,
        samples=len(counts),
        people=people,
        share=round(share, 3),
        faced_frames=faced,
    )
    return people, share, faced, counts


def _runs(counts: list[int], pred: "Callable[[int], bool]") -> list[list[float]]:
    """Maximal runs of consecutive samples satisfying ``pred``, as
    [start_s, end_s] (1 decimal). A run shorter than SPAN_MIN_SAMPLES is a
    blip (a transition frame), never a span."""
    spans: list[list[float]] = []
    start: int | None = None
    for i, c in enumerate(counts):
        if pred(c):
            if start is None:
                start = i
        elif start is not None:
            if i - start >= SPAN_MIN_SAMPLES:
                spans.append([round(start * SCAN_STRIDE_S, 1), round(i * SCAN_STRIDE_S, 1)])
            start = None
    if start is not None and len(counts) - start >= SPAN_MIN_SAMPLES:
        spans.append([round(start * SCAN_STRIDE_S, 1), round(len(counts) * SCAN_STRIDE_S, 1)])
    return spans


def _face_scan_digest(counts: list[int], majority: int, share: float) -> dict[str, Any]:
    """The gate scan's reusable digest (剪辑复用座): the raw per-sample
    counts plus the two derived span families downstream editing reasons
    about — face-free stretches (B-roll / 空镜 candidates) and
    extra-people stretches (audience / reaction-shot cutaway candidates).
    Extra-people is only defined against a majority form."""
    return {
        "version": 1,
        "stride_s": SCAN_STRIDE_S,
        "counts": counts,
        "majority": majority,
        "share": round(share, 3),
        "face_free_spans": _runs(counts, lambda c: c == 0),
        "extra_people_spans": (
            _runs(counts, lambda c: c > majority) if majority > 0 else []
        ),
    }


# ------------------------------------------------------ interview attribution


@dataclass
class Slot:
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


def _assign(det: list[FaceDetection], slots: list[Slot]) -> list[FaceDetection | None]:
    """Assign a frame's detections to slots by center distance (<= 1.5x width)."""
    out: list[FaceDetection | None] = [None] * len(slots)
    for d in det:
        cx, _ = d.center
        dists = [abs(cx - s.cx) for s in slots]
        i = int(np.argmin(dists))
        if dists[i] <= 1.5 * slots[i].w and out[i] is None:
            out[i] = d
    return out


def bootstrap_slots(path: Path) -> tuple[list[Slot], Detect, float]:
    """Sparse 2s scan anchoring the left/right persons, escalating detection
    tiers (640 → native → 2x2 tiles) until the two-face rate reaches 95%.
    Returns the slots, the winning tier's detector, and its two-face rate."""
    fps, _n, w, h = probe(path)
    candidates = _detection_tiers(w, h)

    best: tuple[list[Slot], Detect, float] | None = None
    for name, detect in candidates:
        slots = [
            Slot(cx=w * 0.25, cy=h * 0.4, w=w * 0.05),
            Slot(cx=w * 0.75, cy=h * 0.4, w=w * 0.05),
        ]
        scanned = two_face = 0
        for _, frame in frames_every(path, step=max(1, int(2 * fps))):
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
    slots: list[Slot],
    detect: Detect,
) -> list[dict[str, Any]]:
    """Per-turn mouth energy per slot + argmax attribution + confidence."""
    fps, _n, _w, _h = probe(path)
    out: list[dict[str, Any]] = []
    for ti, turn in enumerate(turns):
        f0, f1 = int(turn["start"] * fps), int(turn["end"] * fps)
        step = max(1, round(fps / TURN_FPS))
        frames: list[np.ndarray] = []
        per_slot: list[list[FaceDetection | None]] = [[], []]
        for _, frame in frames_every(path, step=step, start_f=f0, end_f=f1 + 1):
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

    fps, _n, src_w, src_h = probe(path)
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
    speaker id; the caller falls back to the energy argmax for the rest.
    并行仲裁 (2026-10-06 用户拍板): the capped rows are independent — clips
    cut and verdict calls run concurrently (sequential was conservatism,
    not a dependency; ~95s → ~one slowest call on a 5-clip batch)."""
    hardest_first = sorted(rows, key=lambda r: r["ratio"])
    overflow = max(0, len(hardest_first) - ARBITRATION_CALL_CAP)

    async def _judge(row: dict[str, Any]) -> tuple[int, str] | None:
        clip = await asyncio.to_thread(_cut_turn_clip, path, row["start"], row["end"])
        if clip is None:
            return None
        media = MediaInput(
            type=MediaInputType.VIDEO,
            mime="video/mp4",
            data_url="data:video/mp4;base64," + base64.b64encode(clip).decode(),
        )
        result = await speaker_arbitrate.call(clip=media)
        if result.speaker in ("left", "right"):
            return row["turn"], result.speaker
        return None

    judged = await asyncio.gather(
        *(_judge(row) for row in hardest_first[:ARBITRATION_CALL_CAP])
    )
    verdicts = {turn: speaker for pair in judged if pair for turn, speaker in [pair]}
    if overflow > 0:
        logger.warning("speaker_map_arbitration_overflow", fallback_turns=overflow)
    return verdicts


# ---------------------------------------------------------------- processor --


async def build_speaker_map(
    asset_file: Path, words: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the speaker_map for a VIDEO asset's local file, plus the gate's
    reusable face-scan digest (剪辑复用座 — one scan feeds the form verdict
    AND the downstream editing facts). CPU-bound detection passes run in
    threads; M3 calls stay async. Returns (speaker_map, face_scan)."""
    turns = _words_to_turns(words)
    form, face_scan = await _form_gate(asset_file, turns)
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
        }, face_scan
    if form != "interview" or not real_turns:
        return {
            "version": SPEAKER_MAP_VERSION,
            "form": form,
            "speakers": [],
            "turns": [],
        }, face_scan

    slots, detect, _rate = await asyncio.to_thread(bootstrap_slots, asset_file)
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
            # The position anchor rides the map (剪辑复用座): reframe's
            # interview_switch reads it instead of re-running the full-video
            # bootstrap scan per clip.
            {
                "id": "left",
                "screen_hint": "left",
                "anchor": {"cx": slots[0].cx, "cy": slots[0].cy, "w": slots[0].w, "n": slots[0].n},
            },
            {
                "id": "right",
                "screen_hint": "right",
                "anchor": {"cx": slots[1].cx, "cy": slots[1].cy, "w": slots[1].w, "n": slots[1].n},
            },
        ],
        "turns": out_turns,
    }, face_scan


async def speaker_map_processor(asset: Asset, prior: ProcessResult) -> ProcessResult:
    """VIDEO's second processor (after ASR). Needs the ASR words from the
    prior result; a gate failure must never fail the asset — ASR's outputs
    are already in hand, so any speaker_map error degrades to no map."""
    from app.pipeline.asset_processing import ProcessResult
    from app.providers.storage import download_to_temp

    words = (prior.meta or {}).get("words") or []
    if not asset.file_url:
        return ProcessResult()
    path = prior.local_path
    own_copy = False
    if path is None:
        path = await download_to_temp(asset.file_url)
        own_copy = path is not None
    if path is None:
        return ProcessResult()
    try:
        speaker_map, face_scan = await build_speaker_map(path, words)
        return ProcessResult(meta={"speaker_map": speaker_map, "face_scan": face_scan})
    except Exception as e:  # noqa: BLE001 — degrade to no map, keep ASR's result
        logger.error("speaker_map_failed", asset_id=str(asset.id), error=str(e))
        return ProcessResult()
    finally:
        if own_copy:
            path.unlink(missing_ok=True)
