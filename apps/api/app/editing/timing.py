"""Time law for the editing domain (VIDEO_PROJECT §6).

One law, mirrored in ``packages/video-spec/src/timing.ts`` — the golden
fixtures in ``packages/video-spec/fixtures/timing_golden.json`` pin both
implementations to the same numbers.

- Times are integer ``ticks`` at a ``rate`` (ticks per second), never bare
  float seconds. Content ranges ride the version's ``settings.timebase``;
  source-media facts (SourceSnapshot durations, Clip ``source_range``) ride
  the fixed ``SOURCE_TIMEBASE``.
- Every range is ``[start, end)`` — half-open, ``end > start``.
- Frame numbers derive from ticks through ONE quantize seat
  (``ticks_to_frames``): exact rational round-half-up, computed in integers
  on both sides. Neither the API nor a renderer rounds on its own.
- ``fps`` is a rational ``num/den`` (30/1 today; 30000/1001 stays legal).
  ``timecode`` is a display format only and never stored.
"""

from __future__ import annotations

from fractions import Fraction

# Ticks per second for source-media facts (SourceSnapshot.duration_ticks,
# Clip.source_range). Content ranges use the version's own timebase, which
# defaults to the same value (VersionSettings.timebase).
SOURCE_TIMEBASE = 90000

# Default content timebase (VersionSettings.timebase when unspecified).
DEFAULT_TIMEBASE = SOURCE_TIMEBASE


def seconds_to_ticks(seconds: float | int | str, rate: int = DEFAULT_TIMEBASE) -> int:
    """Seconds → ticks, exact rational round-half-up.

    The float goes through ``str()`` first so decimal inputs (0.3) parse as
    exact rationals instead of binary dust. Times are non-negative by domain
    rule — enforced here. The formula below is floor(x + 1/2) for x ≥ 0.
    """
    x = Fraction(str(seconds)) * rate
    if x < 0:
        raise ValueError("seconds must be non-negative")
    return (2 * x.numerator + x.denominator) // (2 * x.denominator)


def ticks_to_seconds(ticks: int, rate: int = DEFAULT_TIMEBASE) -> Fraction:
    """Ticks → exact seconds (display/probe use; never stored as truth)."""
    return Fraction(ticks, rate)


def ticks_to_frames(ticks: int, rate: int, fps_num: int, fps_den: int = 1) -> int:
    """Ticks → output frame number, exact round-half-up in integer math.

    frame = floor(ticks * fps / rate + 1/2). The renderer never re-derives
    frames from seconds — the compiler runs every range through this seat
    and the spec carries only integer frames.
    """
    if ticks < 0:
        raise ValueError("ticks must be non-negative")
    return (2 * ticks * fps_num + rate * fps_den) // (2 * rate * fps_den)


def frames_to_ticks(frame: int, rate: int, fps_num: int, fps_den: int = 1) -> int:
    """Frame boundary → ticks (the inverse map, exact at frame boundaries)."""
    if frame < 0:
        raise ValueError("frame must be non-negative")
    x = Fraction(frame * fps_den * rate, fps_num)
    return (2 * x.numerator + x.denominator) // (2 * x.denominator)


def source_ticks_to_output_ticks(
    source_ticks: int,
    version_timebase: int,
) -> int:
    """Source-time ticks → version-timebase ticks (exact rational rescale).

    The 1× play-rate law lives here: a source window keeps its DURATION
    across the mapping; only the tick unit changes.
    """
    if source_ticks < 0:
        raise ValueError("source ticks must be non-negative")
    x = Fraction(source_ticks, SOURCE_TIMEBASE) * version_timebase
    return (2 * x.numerator + x.denominator) // (2 * x.denominator)
