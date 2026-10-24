"""Extract frames from the reference video for visual inspection (read-only)."""
import sys

import av

SRC = "/Users/sylas/Downloads/WhatsApp Video 2026-10-21 at 02.43.31.mp4"
OUT = "/tmp/refvideo"

def main() -> None:
    container = av.open(SRC)
    stream = container.streams.video[0]
    fps = float(stream.average_rate or 30)
    dur = float(stream.duration * stream.time_base) if stream.duration else 0
    print(f"fps={fps:.3f} duration={dur:.2f}s frames={stream.frames} size={stream.width}x{stream.height}")
    # Extract 2 frames per second plus the very first/last frame.
    wanted = set()
    n = 0
    for frame in container.decode(stream):
        idx = frame.pts * fps * float(stream.time_base) if frame.pts is not None else n
        n += 1
        sec = n / fps
        half = int(sec * 2)
        if half not in wanted:
            wanted.add(half)
            img = frame.to_image()
            img.save(f"{OUT}/f{n:04d}_t{sec:05.2f}.png")
    print(f"wrote {len(wanted)} frames to {OUT}")

main()
