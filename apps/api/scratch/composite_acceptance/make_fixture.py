"""Generate the composite-acceptance fixture: a 25s 30fps video whose EVERY
frame is self-identifying (burned source-second + frame markers + per-second
hue) and whose audio track pitch-encodes the source second (220 + 20·sec Hz
sine), so a rendered cut can be probed frame-by-frame for WHICH source
second shows at WHICH output time, and the original audio can be pitch-read
for source/output alignment.

Usage: uv run python scratch/composite_acceptance/make_fixture.py
Output: scratch/composite_acceptance/source_25s.mp4 (+ a probe printout)
"""

from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FPS = 30
DURATION_S = 25
W, H = 1280, 720
SR = 48000
OUT = Path(__file__).parent / "source_25s.mp4"

FONT_BIG = ImageFont.load_default(size=220)
FONT_SMALL = ImageFont.load_default(size=60)


def _frame_image(f: int) -> np.ndarray:
    import colorsys

    sec, fin = divmod(f, FPS)
    hue = (sec * 14) % 360
    img = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(img)
    # Per-second hue band across the top — a second is identifiable by color
    # alone (no OCR needed).
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, 0.75, 0.9))
    d.rectangle([0, 0, W, 90], fill=(r, g, b))
    # Big second marker + small frame-in-second marker.
    d.text((60, 200), f"S{sec:02d}", font=FONT_BIG, fill=(245, 245, 240))
    d.text((60, 480), f"F{fin:02d}", font=FONT_SMALL, fill=(200, 200, 195))
    # Frame-in-second position bar: 30 cells, the current one lit.
    for i in range(FPS):
        x0 = 60 + i * 38
        d.rectangle(
            [x0, 620, x0 + 30, 660],
            fill=(250, 240, 120) if i == fin else (60, 60, 66),
        )
    return np.asarray(img)


def main() -> None:
    container = av.open(str(OUT), "w")
    vstream = container.add_stream("h264", rate=FPS)
    vstream.width, vstream.height, vstream.pix_fmt = W, H, "yuv420p"
    astream = container.add_stream("aac", rate=SR)
    astream.layout = "stereo"

    audio_pts = 0
    for sec in range(DURATION_S):
        for fin in range(FPS):
            f = sec * FPS + fin
            vf = av.VideoFrame.from_ndarray(_frame_image(f), format="rgb24")
            vf.pts = f
            vf.time_base = Fraction(1, FPS)
            for pkt in vstream.encode(vf):
                container.mux(pkt)
        # One source second of pitched sine (220 + 20·sec Hz).
        t = np.arange(SR, dtype=np.float64) / SR
        freq = 220.0 + 20.0 * sec
        tone = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
        stereo = np.stack([tone, tone])  # (channels, samples) planar
        af = av.AudioFrame.from_ndarray(stereo, format="s16p", layout="stereo")
        af.sample_rate = SR
        af.pts = audio_pts
        af.time_base = Fraction(1, SR)
        audio_pts += SR
        for pkt in astream.encode(af):
            container.mux(pkt)

    for pkt in vstream.encode(None):
        container.mux(pkt)
    for pkt in astream.encode(None):
        container.mux(pkt)
    container.close()

    # Honest probe: container duration + stream inventory.
    with av.open(str(OUT)) as check:
        dur = (check.duration or 0) / 1_000_000
        streams = [(s.type, getattr(s, "frames", None)) for s in check.streams]
    print(f"wrote {OUT} duration={dur:.3f}s streams={streams}")


if __name__ == "__main__":
    main()
