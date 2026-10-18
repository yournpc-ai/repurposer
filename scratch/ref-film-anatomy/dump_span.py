import sys
from pathlib import Path
import av
src, outdir = sys.argv[1], Path(sys.argv[2])
targets = [64.5, 66.5, 68.5, 70.5, 72.5, 74.5, 76.5, 78.0]
c = av.open(src)
ti = 0
for frame in c.decode(video=0):
    t = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
    while ti < len(targets) and t >= targets[ti]:
        frame.to_image().save(outdir / f"reveal_{targets[ti]:.1f}s.png")
        print(f"reveal_{targets[ti]:.1f}s")
        ti += 1
    if ti >= len(targets):
        break
