"""Dump one frame per segment midpoint (from the detected cut list)."""
import sys
from pathlib import Path
import av

src, outdir = sys.argv[1], Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
bounds = [0.0, 4.4, 8.4, 12.4, 16.4, 24.4, 26.4, 34.4, 36.4, 44.4, 50.4,
          52.4, 55.4, 62.4, 63.8, 78.4, 84.4, 90.4]
mids = [(a + b) / 2 for a, b in zip(bounds, bounds[1:])]
c = av.open(src)
targets = sorted(mids)
ti = 0
for frame in c.decode(video=0):
    t = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
    while ti < len(targets) and t >= targets[ti]:
        img = frame.to_image()
        img.save(outdir / f"seg{ti:02d}_{targets[ti]:.1f}s.png")
        print(f"seg{ti:02d} @ {targets[ti]:.1f}s (mid of {bounds[ti]}-{bounds[ti+1]})")
        ti += 1
    if ti >= len(targets):
        break
