# Unambiguous tail probe: save EVERY frame in [270, 390) of the spike mp4,
# filename = frame index from pts, zero matching logic. Then the scene
# boundary at frame 300 is checked directly.
# Run: cd apps/api && uv run python scratch/film_spike_tail_dump.py
from pathlib import Path

import av

MP4 = Path("/Users/sylas/repurposer/apps/render/scratch-spike/video-scene/out/video-scene-spike.mp4")
OUT = MP4.parent / "mp4-probes" / "tail"
OUT.mkdir(parents=True, exist_ok=True)

container = av.open(str(MP4))
stream = container.streams.video[0]
fps = float(stream.average_rate)
tb = stream.time_base
n = 0
for frame in container.decode(stream):
    if frame.pts is None:
        continue
    idx = round(float(frame.pts * tb) * fps)
    if 270 <= idx < 390 and idx % 10 == 0:
        img = frame.to_image()
        img.thumbnail((480, 480))
        img.save(OUT / f"f{idx:04d}.png")
        n += 1
print("dumped", n, "frames")
