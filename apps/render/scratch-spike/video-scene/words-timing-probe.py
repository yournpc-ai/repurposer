"""Batch B words-timing probe: decodes words-timing-spike.mp4 with PyAV and
verifies the frame landing of the parameterized entrance.

Expected (30fps, nearest-frame halves-up quantization):
- scene 1 (comp f0–119): tokens enter at f9, f13, f17, f21, f25, f29; each
  entrance lasts 8 frames → all motion settled by f37; hold = scene end.
- scene 2 (comp f120–239): legacy cadence control (no timing keys).
- scene 3 (comp f240–359): push motion bounded to scene f45–f105
  (comp f285–f345; 1.5s–3.5s — clear of the lines entrance's settle).
- no music / no voiceover → the container carries NO audio stream.

Run: cd apps/api && uv run python ../render/scratch-spike/video-scene/words-timing-probe.py
"""
from pathlib import Path

import av
import numpy as np

MP4 = Path(__file__).parent / "out" / "words-timing-spike.mp4"

container = av.open(str(MP4))
streams = container.streams
print("streams:", [(s.type, s.index) for s in streams])
# Remotion's h264 mux always carries an audio track (the production chain
# does not pass muted either) — the no-music/no-voiceover law here is that
# the track is SILENT, not absent.
video = streams.video[0]
fps = float(video.average_rate)
print(f"video: {video.frames} frames @ {fps:g} fps")
assert fps == 30.0

frames: dict[int, np.ndarray] = {}
want = set(range(0, 70)) | set(range(120, 235)) | set(range(240, 360))
idx = 0
for packet in container.demux(video):
    for frame in packet.decode():
        if idx in want:
            frames[idx] = frame.to_ndarray(format="gray").astype(np.int16)
        idx += 1
print(f"decoded {idx} frames, kept {len(frames)}")
assert idx == 360

# The audio pass seeks back to the start (demux is a one-way iterator).
container.seek(0)
audio_streams = [s for s in streams if s.type == "audio"]
peak = 0.0
for s in audio_streams:
    for packet in container.demux(s):
        for frame in packet.decode():
            arr = frame.to_ndarray()
            if arr.size:
                peak = max(peak, float(np.abs(arr.astype(np.float64)).max()))
print(f"audio streams: {len(audio_streams)}, peak amplitude: {peak:g}")
assert peak == 0.0, "expected a silent audio track (no music, no voiceover)"
print("silent container confirmed ✓")
container.close()

def diff_count(a: np.ndarray, b: np.ndarray, thresh: int = 12) -> int:
    return int((np.abs(a - b) > thresh).sum())

# --- scene 1: token entrance landing ---------------------------------------
baseline = frames[8]  # Fade settles at f7; the first token's zero point is f9
activity = {f: diff_count(frames[f], baseline) for f in range(8, 62)}
print("\nscene 1 — changed pixels vs f8 (token entrances):")
prev = 0
jumps = []
for f in range(8, 62):
    delta = activity[f] - prev
    prev = activity[f]
    if delta > 400:
        jumps.append(f)
        print(f"  f{f:3d}: +{delta} px (cumulative {activity[f]})")
print("entrance jump frames:", jumps)
# The named frame is the spring's ZERO point (spring(frame: 0) == 0, so the
# frame itself is pixel-identical to its predecessor); the first VISIBLE
# pixel lands one frame later. Jump frames must be exactly start+1, spaced
# exactly 4 apart (0.12s → f4), and f9 itself must carry no jump.
expected_zero = [9, 13, 17, 21, 25, 29]
assert jumps[:6] == [f + 1 for f in expected_zero], (
    f"token entrances {jumps[:6]} != zero points {expected_zero} + 1"
)
assert all(
    activity[f] - activity[f - 1] <= 400 for f in expected_zero
), "a zero-point frame moved pixels — the start did not land on its frame"
print("token zero points land on f9/f13/f17/f21/f25/f29 (0.3s→f9, 0.12s→f4) ✓")

# entrances settled: after the last token's start (f29) + duration (8f) = f37
tail = [activity[f] for f in range(40, 62)]
assert max(tail) - min(tail) < 50, f"scene not settled after f40: {tail[:5]}…"
print("scene 1 settled after f37 (last token start f29 + 8f duration) ✓")

# --- scene 2: legacy cadence control (smoke) -------------------------------
# The unparameterized spring keeps pixels moving for ~1s, so exact per-token
# landing is not pixel-separable here; the byte-preservation proof for the
# no-timing path is CODE-level (with all keys absent the schedule reduces to
# the old expressions: step = the same 2–4f formula, delay = cursor, the
# enter() call takes the undefined-duration branch). What the render proves:
# the scene still animates word-by-word (onset clusters at the legacy ~4f
# spacing, starting immediately — never the parameterized f9 start) and every
# token reaches full visibility.
base2 = frames[128]

def newly_active(f: int, base: np.ndarray, thresh: int = 25) -> int:
    now = np.abs(frames[f] - base) > thresh
    before = np.abs(frames[f - 1] - base) > thresh
    return int((now & ~before).sum())

new2 = {f: newly_active(f, base2) for f in range(129, 155)}
onsets = [f - 120 for f in range(129, 155) if new2[f] > 10000]
print("\nscene 2 (legacy control) onset frames (scene-local):", onsets)
assert len(onsets) >= 4, f"expected repeated word-by-word onsets, got {onsets}"
assert min(onsets) <= 12, (
    f"first onset at scene f{min(onsets)} — a parameterized schedule would "
    "hold the plane blank until f9+; legacy starts immediately"
)
gaps = [b - a for a, b in zip(onsets, onsets[1:])]
assert all(g <= 5 for g in gaps), f"legacy step drifted from ~f4: {gaps}"
full = diff_count(frames[128 + 90], frames[128], thresh=25)
assert full > 50000, f"tokens never reached full visibility ({full} px)"
print("legacy control animates word-by-word at ~f4 spacing, all tokens land ✓")

# --- scene 3: motion window scene f45–f105 (comp f285–f345) -----------------
# Measured signature: fade+entrance settle by comp f267; QUIET until f285;
# drift f286–f345 (~5k px/frame — the push); quiet f346+ until the scene's
# fade-out (f353+). The window boundaries are exactly motion_start 1.5s→f45
# (comp 240+45=f285, first drift f286) and motion_end 3.5s→f105 (comp f345).
motion = {f: diff_count(frames[f], frames[f - 1]) for f in range(250, 359)}
quiet_before = max(motion[f] for f in range(268, 286))
active = [f for f in range(286, 346) if motion[f] > 400]
quiet_after = max(motion[f] for f in range(346, 353))
print(
    "\nscene 3 — quiet before:", quiet_before,
    "| active frames:", active[0], "…", active[-1], f"({len(active)} frames)",
    "| quiet after:", quiet_after,
)
assert quiet_before <= 400, f"drift before the window: {quiet_before} px"
assert len(active) == 60 and active[0] == 286 and active[-1] == 345, (
    f"motion window drifted: {active[0]}…{active[-1]} ({len(active)} frames), "
    "expected f286…f345 (60 frames)"
)
assert quiet_after <= 400, f"motion past motion_end: {quiet_after} px"
print("push bounded to exactly the 1.5s–3.5s window (f285–f345 boundary) ✓")

print("\nALL TIMING PROBES PASS")
