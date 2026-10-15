"""Pure tests for the music beat-grid analysis (ADR-121 B3).

Deterministic synthetic audio: stdlib ``wave`` writes s16 PCM, numpy lays a
click track at a known tempo — PyAV decodes it exactly as it would a catalog
mp3. No DB, no network, no fixtures.
"""

from __future__ import annotations

import io
import wave

import numpy as np

from app.tools.music.beats import _RATE, analyze_beat_grid


def _click_track_wav(bpm: float, seconds: float) -> bytes:
    """Mono WAV: a 30ms sine burst on every beat, silence elsewhere."""
    n = int(seconds * _RATE)
    pcm = np.zeros(n, dtype=np.float32)
    period = 60.0 / bpm
    t = 0.0
    burst = int(0.03 * _RATE)
    while t < seconds:
        start = int(t * _RATE)
        end = min(start + burst, n)
        tt = np.arange(end - start) / _RATE
        pcm[start:end] = 0.9 * np.sin(2 * np.pi * 800 * tt)
        t += period
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def test_analyze_beat_grid_finds_the_tempo():
    grid = analyze_beat_grid(_click_track_wav(120.0, 12.0))
    assert grid is not None
    assert abs(grid["bpm"] - 120.0) < 1.5
    beats = grid["beats"]
    assert len(beats) >= 20
    # Alignment: every grid beat lands on a click (clicks every 0.5s) — the
    # first click is invisible to the onset diff, so the grid may start at
    # the second; what matters is the grid rides the clicks throughout.
    for b in beats:
        assert min(abs(b - 0.5 * k) for k in range(25)) < 0.08
    # No drift: the last beat is as aligned as the first (sub-frame tempo).
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert all(abs(g - 0.5) < 0.03 for g in gaps)


def test_analyze_beat_grid_other_tempo():
    grid = analyze_beat_grid(_click_track_wav(90.0, 12.0))
    assert grid is not None
    assert abs(grid["bpm"] - 90.0) < 1.5


def test_analyze_beat_grid_too_short_is_honest_none():
    assert analyze_beat_grid(_click_track_wav(120.0, 3.0)) is None


def test_analyze_beat_grid_silence_is_honest_none():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        w.writeframes(np.zeros(10 * _RATE, dtype="<i2").tobytes())
    assert analyze_beat_grid(buf.getvalue()) is None
