"""PTS-ordered frame grabber — B-frames make decode order ≠ display order.

Usage: python -I grab_frames_pts.py <video> <out_dir> <t1,t2,...>  (seconds)
"""
import sys
from pathlib import Path

import av


def main() -> None:
    video_path, out_dir = sys.argv[1], Path(sys.argv[2])
    wanted_s = sorted(float(x) for x in sys.argv[3].split(","))
    out_dir.mkdir(parents=True, exist_ok=True)

    container = av.open(video_path)
    stream = container.streams.video[0]
    fps = float(stream.average_rate)
    print(f"{stream.frames} frames @ {fps:.2f}fps; grabbing t={wanted_s}")

    frames = []
    for frame in container.decode(stream):
        t = float(frame.pts * frame.time_base) if frame.pts is not None else None
        if t is not None:
            frames.append((t, frame))
    frames.sort(key=lambda tf: tf[0])
    container.close()

    for want in wanted_s:
        t, frame = min(frames, key=lambda tf: abs(tf[0] - want))
        p = out_dir / f"t{want:05.2f}s_actual{t:.2f}s.png"
        frame.to_image().save(p)
        print(f"  want {want:.2f}s -> actual {t:.2f}s -> {p.name}")


if __name__ == "__main__":
    main()
