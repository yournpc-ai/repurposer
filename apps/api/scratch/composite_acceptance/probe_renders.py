"""Probe the five composite-acceptance renders frame-by-frame / second-by-second
(PyAV + numpy only — no OCR): the fixture's every frame self-identifies (hue
band = source second, S/F markers), so the probe reads WHICH source second
shows at WHICH output time, WHERE the text ink is, and WHAT pitch the kept
original audio carries.

Acceptance legs (docs/tasks/film-storyboard-orchestration-execution.md §0.11):
  A anchor            — source 10–18s on the right from output 3s; left text
                        output 4–10s, word-by-word 0.3s; nothing freezes.
  B bg_image/bg_plain — the SAME text cadence over other backgrounds.
  C edited_v2         — real apply_film_edits chain: text changed (content /
                        interval / until 7→6), video element byte-identical.
  E anchor_keep_audio — keep_audio=false leaks nothing; =true pitch-maps
                        output second → source second (220+20·sec Hz).

Usage: uv run python scratch/composite_acceptance/probe_renders.py
"""

import colorsys
from pathlib import Path

import av
import numpy as np

HERE = Path(__file__).parent
RENDERS = HERE / "renders"

W, H = 1920, 1080
# Video element rect (x .5–1, y 0–1): the fixture's hue band lands in the
# top ~135px of the region (cover 1.5×).
VIDEO_STRIP = (slice(10, 120), slice(1000, 1900))
VIDEO_FULL = (slice(0, H), slice(960, W))
# Text element rect (x .06–.44, y .2–.8).
TEXT_REGION = (slice(216, 864), slice(115, 845))

CHECKS: list[str] = []
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    CHECKS.append(label)
    if not ok:
        FAILURES.append(f"{label}: {detail}")
    print(f"  {'ok ' if ok else 'FAIL'} {label} {detail}")


def frames_at(path: Path, targets: list[float]) -> dict[float, np.ndarray]:
    """Decode once, keep the nearest frame to each target output second."""
    remaining = dict.fromkeys(targets)
    out: dict[float, np.ndarray] = {}
    with av.open(str(path)) as c:
        for frame in c.decode(video=0):
            t = float(frame.pts * frame.time_base)
            for want in list(remaining):
                if abs(t - want) < 1 / 60:  # within half a frame
                    out[want] = frame.to_ndarray(format="rgb24")
                    del remaining[want]
            if not remaining:
                break
    missing = [f"{t}s" for t in remaining]
    assert not missing, f"{path.name}: no frame near {missing}"
    return out


def source_second(img: np.ndarray) -> tuple[int, float]:
    """Read the hue band → the fixture second it encodes (hue = sec·14°)."""
    strip = img[VIDEO_STRIP].reshape(-1, 3).mean(axis=0) / 255.0
    h, s, _v = colorsys.rgb_to_hsv(*strip)
    return round(h * 360 / 14) % 360, s


def text_ink(img: np.ndarray) -> int:
    """Dark-ink pixel count inside the text rect (tone=dark on light canvas)."""
    region = img[TEXT_REGION].astype(np.int32)
    lum = region @ [0.299, 0.587, 0.114]
    return int((lum < 90).sum())


def dominant_freq(path: Path, t: float) -> float | None:
    """Peak FFT frequency of the 1s window centered at t+0.5 (mono mix)."""
    with av.open(str(path)) as c:
        if not any(s.type == "audio" for s in c.streams):
            return None
        chunks: list[np.ndarray] = []
        rate = 48000
        for frame in c.decode(audio=0):
            rate = frame.sample_rate
            arr = frame.to_ndarray()
            if arr.ndim == 2:  # planar (channels, samples)
                arr = arr.mean(axis=0)
            start = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
            chunks.append((start, arr))
        samples = np.concatenate([a for _s, a in sorted(chunks, key=lambda x: x[0])])
    i0 = int(t * rate)
    window = samples[i0 : i0 + rate].astype(np.float64)
    if len(window) < rate // 2:
        return None
    spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
    freqs = np.fft.rfftfreq(len(window), 1 / rate)
    return float(freqs[int(spectrum[50:].argmax()) + 50])  # ignore DC/rumble


def max_rms(path: Path) -> float | None:
    with av.open(str(path)) as c:
        if not any(s.type == "audio" for s in c.streams):
            return None
        peak = 0.0
        for frame in c.decode(audio=0):
            arr = frame.to_ndarray().astype(np.float64) / 32768.0
            peak = max(peak, float(np.sqrt((arr**2).mean())))
    return peak


def main() -> None:
    # ---- A: the anchor -----------------------------------------------------
    print("A: anchor.mp4")
    a = frames_at(RENDERS / "anchor.mp4", [2.0, 3.5, 4.4, 7.5, 9.5, 10.5, 12.0])
    sec2, sat2 = source_second(a[2.0])
    check("A t=2.0 no video yet (words scene)", sat2 < 0.15, f"strip saturation {sat2:.2f}")
    # (the t=2.0 words scene's own headline legitimately paints the text
    # rect — "text not entered" is proven inside the composite at t=3.5.)
    sec35, _ = source_second(a[3.5])
    check("A t=3.5 right = source S10", sec35 == 10, f"read S{sec35}")
    check("A t=3.5 text not entered (at=1s)", text_ink(a[3.5]) == 0, f"ink={text_ink(a[3.5])}")
    sec44, _ = source_second(a[4.4])
    full = text_ink(a[7.5])
    part = text_ink(a[4.4])
    check("A t=4.4 right = source S11", sec44 == 11, f"read S{sec44}")
    check("A t=4.4 text mid-entrance", 500 < part < full * 0.95, f"ink={part} vs full={full}")
    sec75, _ = source_second(a[7.5])
    check("A t=7.5 right = source S14", sec75 == 14, f"read S{sec75}")
    check("A t=7.5 text fully in", full > 2000, f"ink={full}")
    sec95, _ = source_second(a[9.5])
    check("A t=9.5 right = source S16, text still in", sec95 == 16 and text_ink(a[9.5]) > 2000,
          f"S{sec95} ink={text_ink(a[9.5])}")
    sec105, _ = source_second(a[10.5])
    check("A t=10.5 right = source S17, text GONE (until=7→output 10s)",
          sec105 == 17 and text_ink(a[10.5]) == 0, f"S{sec105} ink={text_ink(a[10.5])}")
    _sec12, sat12 = source_second(a[12.0])
    check("A t=12.0 tail words, video NOT frozen", sat12 < 0.15, f"strip saturation {sat12:.2f}")

    # ---- B: same text cadence over image / plain backgrounds ----------------
    print("B: bg_image.mp4")
    b = frames_at(RENDERS / "bg_image.mp4", [3.5, 7.5, 10.5])
    check("B bg_image t=3.5 no text", text_ink(b[3.5]) == 0, f"ink={text_ink(b[3.5])}")
    check("B bg_image t=7.5 text in", text_ink(b[7.5]) > 2000, f"ink={text_ink(b[7.5])}")
    check("B bg_image t=10.5 text gone", text_ink(b[10.5]) == 0, f"ink={text_ink(b[10.5])}")
    region = b[7.5][VIDEO_FULL].reshape(-1, 3).mean(axis=0)
    check("B bg_image right = red IMG panel",
          region[0] > 150 and region[1] < 130 and region[2] < 130,
          f"rgb=({region[0]:.0f},{region[1]:.0f},{region[2]:.0f})")

    # bg_plain = a MEDIA-FREE composite: two independent text elements over
    # the bare theme canvas (legal since the 2026-10-23 review removed the
    # media-element requirement). The title rides window A (output 4–10s),
    # the bottom note window B (output 5–9s) — each leaves on its own clock.
    print("B: bg_plain.mp4 (media-free composite, two text elements)")
    NOTE_REGION = (slice(900, 1020), slice(115, 845))  # rect y .82–.96, x .06–.44
    bp = frames_at(RENDERS / "bg_plain.mp4", [3.5, 4.5, 5.5, 9.5, 10.5])

    def note_ink(img: np.ndarray) -> int:
        region = img[NOTE_REGION].astype(np.int32)
        return int(((region @ [0.299, 0.587, 0.114]) < 90).sum())

    check("B bg_plain t=3.5 neither text entered",
          text_ink(bp[3.5]) == 0 and note_ink(bp[3.5]) == 0,
          f"title={text_ink(bp[3.5])} note={note_ink(bp[3.5])}")
    check("B bg_plain t=4.5 title in, note NOT yet (at=2→output 5s)",
          text_ink(bp[4.5]) > 500 and note_ink(bp[4.5]) == 0,
          f"title={text_ink(bp[4.5])} note={note_ink(bp[4.5])}")
    check("B bg_plain t=5.5 both in",
          text_ink(bp[5.5]) > 500 and note_ink(bp[5.5]) > 200,
          f"title={text_ink(bp[5.5])} note={note_ink(bp[5.5])}")
    check("B bg_plain t=9.5 note GONE (until=6→output 9s), title stays",
          text_ink(bp[9.5]) > 2000 and note_ink(bp[9.5]) == 0,
          f"title={text_ink(bp[9.5])} note={note_ink(bp[9.5])}")
    check("B bg_plain t=10.5 both gone (until=7→output 10s)",
          text_ink(bp[10.5]) == 0 and note_ink(bp[10.5]) == 0,
          f"title={text_ink(bp[10.5])} note={note_ink(bp[10.5])}")
    # The right half stays bare canvas: measure its saturation directly.
    sat = float(
        colorsys.rgb_to_hsv(
            *(bp[5.5][VIDEO_STRIP].reshape(-1, 3).mean(axis=0) / 255.0)
        )[1]
    )
    check("B bg_plain no video anywhere", sat < 0.15, f"strip saturation {sat:.2f}")

    # ---- C: edited_v2 — text changed, video untouched -----------------------
    print("C: edited_v2.mp4 vs anchor")
    e = frames_at(RENDERS / "edited_v2.mp4", [5.0, 7.5, 8.0, 9.5])
    av_frames = frames_at(RENDERS / "anchor.mp4", [5.0, 7.5])
    for t in (5.0, 7.5):
        diff = np.abs(
            e[t][VIDEO_FULL].astype(np.int32) - av_frames[t][VIDEO_FULL].astype(np.int32)
        ).mean()
        check(f"C t={t} video element identical to anchor", diff < 3.0, f"mean|Δ|={diff:.2f}")
    check("C t=5.0 edited text present", text_ink(e[5.0]) > 1500, f"ink={text_ink(e[5.0])}")
    check("C t=9.5 edited text GONE early (until 7→6)", text_ink(e[9.5]) == 0,
          f"ink={text_ink(e[9.5])}")
    # Cadence is compared WITHIN the edited render (glyph ink mass differs
    # between the two scripts, so cross-render ink counts are invalid):
    # at local 2.0s (interval .5) 5/10 tokens have entered; by local 5.0s all.
    check("C slower cadence: still entering at local 2.0s, full by 5.0s",
          text_ink(e[8.0]) > text_ink(e[5.0]) * 1.5,
          f"t=5.0 ink={text_ink(e[5.0])} → t=8.0 ink={text_ink(e[8.0])}")

    # ---- E: keep_audio ------------------------------------------------------
    print("E: audio legs")
    silent = max_rms(RENDERS / "anchor.mp4")
    check("E anchor (keep_audio=false) silent",
          silent is None or silent < 1e-3,
          "no audio stream" if silent is None else f"max RMS {silent:.5f}")
    audio_ok = True
    details = []
    for t in range(4, 11):
        got = dominant_freq(RENDERS / "anchor_keep_audio.mp4", t)
        want = 220.0 + 20.0 * (t + 7)  # output t ↦ source floor(10 + t+0.5 − 3) = t+7
        details.append(f"t={t}:{got and round(got)}Hz≈{round(want)}")
        if got is None or abs(got - want) > 10:
            audio_ok = False
    check("E keep_audio pitch-maps output→source second", audio_ok, " ".join(details))

    print(f"\n{len(CHECKS)} checks, {len(FAILURES)} failures")
    if FAILURES:
        print("FAILURES:")
        for f in FAILURES:
            print(" -", f)
        raise SystemExit(1)
    print("ALL COMPOSITE ACCEPTANCE PROBES GREEN")


if __name__ == "__main__":
    main()
