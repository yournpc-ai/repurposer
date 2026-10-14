"""Extract exact frames by INDEX (sequential decode, no seeking — seek lands on
keyframes and lies about timestamps).

Usage: python -I grab_frames.py <video> <out_dir> <idx1,idx2,...>
"""
import sys
from pathlib import Path

import av


def main() -> None:
    video_path, out_dir = sys.argv[1], Path(sys.argv[2])
    wanted = sorted(int(x) for x in sys.argv[3].split(","))
    out_dir.mkdir(parents=True, exist_ok=True)

    container = av.open(video_path)
    stream = container.streams.video[0]
    fps = float(stream.average_rate)
    total = stream.frames
    print(f"{total} frames @ {fps:.2f}fps; grabbing {wanted}")

    wi = 0
    for i, frame in enumerate(container.decode(stream)):
        while wi < len(wanted) and wanted[wi] == i:
            p = out_dir / f"f{i:04d}_{i / fps:.2f}s.png"
            frame.to_image().save(p)
            print(f"  frame {i} ({i / fps:.2f}s) -> {p.name}")
            wi += 1
        if wi >= len(wanted):
            break
    container.close()


if __name__ == "__main__":
    main()
