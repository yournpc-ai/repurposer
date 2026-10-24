# Video-scene spike verdict: extract frames from the REAL rendered MP4 at
# probe times (renderStill showed seek-flakiness; the mp4 is the artifact).
# Output timeline: words 0-2s | video1 (src 10-14s) 2-6s | video2 (src
# 14-18s) 6-10s | end 10-13s.
# Run: cd apps/api && uv run python scratch/film_spike_extract_frames.py
import av  # noqa: F401  (PyAV)
from pathlib import Path

MP4 = Path(
    "/Users/sylas/repurposer/apps/render/scratch-spike/video-scene/out/video-scene-spike.mp4"
)
OUT = MP4.parent / "mp4-probes"
OUT.mkdir(exist_ok=True)

PROBES = [1.0, 3.0, 4.9, 6.5, 9.0, 12.0]  # seconds

container = av.open(str(MP4))
stream = container.streams.video[0]
fps = float(stream.average_rate)
duration = float(stream.duration * stream.time_base)
print(f"mp4: {duration:.2f}s @ {fps:.0f}fps, streams: {[s.type for s in container.streams]}")

targets = {int(t * fps): t for t in PROBES}
for frame in container.decode(stream):
    if frame.pts is None:
        continue
    t = float(frame.pts * stream.time_base)
    hit = next((p for p in PROBES if abs(t - p) < 1.0 / fps / 2), None)
    if hit is not None and hit in targets.values():
        img = frame.to_image()
        img.save(OUT / f"t{hit:.1f}s.png")
        print(f"saved t={hit}s (actual {t:.3f}s)")
        targets = {k: v for k, v in targets.items() if v != hit}
    if not targets:
        break
print("missing:", sorted(targets.values()) if targets else "none")
