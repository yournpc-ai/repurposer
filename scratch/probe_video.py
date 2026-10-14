"""Probe a video's metadata and extract evenly-spaced frames as PNGs.

Usage: python -I probe_video.py <video_path> <out_dir> [n_frames]
"""
import sys
from pathlib import Path

import av


def main() -> None:
    video_path = sys.argv[1]
    out_dir = Path(sys.argv[2])
    n_frames = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    out_dir.mkdir(parents=True, exist_ok=True)

    container = av.open(video_path)
    stream = container.streams.video[0]
    duration_s = float(container.duration or 0) / 1_000_000
    print(f"codec={stream.codec_context.name} {stream.width}x{stream.height} "
          f"fps={float(stream.average_rate):.2f} frames={stream.frames} "
          f"duration={duration_s:.2f}s")
    for s in container.streams:
        print(f"  stream: {s.type} codec={s.codec_context.name} duration={float(s.duration * s.time_base) if s.duration else '?'}s")
    container.close()

    # Re-open and grab frames at evenly spaced timestamps via seek.
    targets = [duration_s * (i + 0.5) / n_frames for i in range(n_frames)]
    container = av.open(video_path)
    stream = container.streams.video[0]
    for i, t in enumerate(targets):
        container.seek(int(t / stream.time_base), stream=stream, any_frame=False, backward=True)
        frame = None
        for f in container.decode(stream):
            frame = f
            break
        if frame is None:
            print(f"frame {i} @ {t:.2f}s: MISS")
            continue
        img = frame.to_image()
        p = out_dir / f"frame_{i:02d}_{t:.1f}s.png"
        img.save(p)
        print(f"frame {i} @ {t:.2f}s -> {p.name} {img.size}")
    container.close()


if __name__ == "__main__":
    main()
