# Harness calibration: dense probe strip over BOTH the spike output mp4 and
# the source mp4 (the source doubles as the ground-truth timeline: what
# SHOULD appear at output t = 2s+(src-10s) etc.). Saves small thumbs.
# Run: cd apps/api && uv run python scratch/film_spike_calibrate.py
from pathlib import Path

import av

OUT = Path("/Users/sylas/repurposer/apps/render/scratch-spike/video-scene/out/mp4-probes")
OUT.mkdir(exist_ok=True)

JOBS = {
    "spike": (Path("/Users/sylas/repurposer/apps/render/scratch-spike/video-scene/out/video-scene-spike.mp4"),
              [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]),
    "source": (Path("/Users/sylas/repurposer/apps/render/scratch-spike/video-scene/public/source.mp4"),
               [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0]),
}

for tag, (mp4, probes) in JOBS.items():
    container = av.open(str(mp4))
    stream = container.streams.video[0]
    fps = float(stream.average_rate)
    remaining = set(probes)
    saved = []
    for frame in container.decode(stream):
        if frame.pts is None:
            continue
        t = float(frame.pts * stream.time_base)
        hit = next((p for p in remaining if abs(t - p) < 1.0 / fps / 2), None)
        if hit is not None:
            img = frame.to_image()
            img.thumbnail((640, 640))
            img.save(OUT / f"{tag}-t{hit:.1f}.png")
            saved.append(hit)
            remaining.discard(hit)
        if not remaining:
            break
    print(tag, "saved:", saved, "missing:", sorted(remaining))
