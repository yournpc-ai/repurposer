"""Probe the reference film: duration/streams + scene-change frame dump."""
import sys
from pathlib import Path

import av

src = sys.argv[1]
outdir = Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)

c = av.open(src)
v = c.streams.video[0]
dur = float(c.duration / av.time_base) if c.duration else None
print(f"container: duration={dur:.2f}s" if dur else "container: duration=?")
print(f"video: {v.codec_context.name} {v.codec_context.width}x{v.codec_context.height} "
      f"fps={float(v.average_rate):.2f} frames={v.frames}")
for s in c.streams:
    if s.type == "audio":
        print(f"audio: {s.codec_context.name} rate={s.codec_context.sample_rate} ch={s.codec_context.channels}")

# Scene-cut detection: mean abs diff between consecutive downscaled frames,
# dump the frame at each cut plus t=0.5s.
import numpy as np

prev = None
cuts = []
t = 0.0
fps = float(v.average_rate)
thumb_w, thumb_h = 64, 36
for frame in c.decode(video=0):
    t = float(frame.pts * frame.time_base) if frame.pts is not None else t + 1.0 / fps
    img = frame.to_ndarray(format="gray", width=thumb_w, height=thumb_h).astype(np.int16)
    if prev is not None:
        diff = float(np.abs(img - prev).mean())
        if diff > 14.0:  # cut threshold (empirical for hard cuts)
            cuts.append((t, diff))
    prev = img
print(f"cuts ({len(cuts)}):")
for ct, d in cuts:
    print(f"  {ct:7.2f}s  diff={d:.1f}")
