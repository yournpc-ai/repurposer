"""Golden timing law for the editing domain (VIDEO_PROJECT §6).

Pins the Python implementation of the ONE quantize seat against
``packages/video-spec/fixtures/timing_golden.json`` — the same fixture file
the TS package's tests read, so the two implementations cannot drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.editing.timing import (
    SOURCE_TIMEBASE,
    seconds_to_ticks,
    source_ticks_to_output_ticks,
    ticks_to_frames,
    ticks_to_seconds,
)

FIXTURE = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "video-spec"
        / "fixtures"
        / "timing_golden.json"
    ).read_text()
)


def test_ticks_to_frames_golden():
    for c in FIXTURE["ticks_to_frames"]:
        assert (
            ticks_to_frames(c["ticks"], c["rate"], c["fps_num"], c["fps_den"])
            == c["frames"]
        ), c


def test_seconds_to_ticks_golden():
    for c in FIXTURE["seconds_to_ticks"]:
        assert seconds_to_ticks(c["seconds"], c["rate"]) == c["ticks"], c


def test_negative_ticks_rejected():
    with pytest.raises(ValueError):
        ticks_to_frames(-1, 90000, 30)
    with pytest.raises(ValueError):
        seconds_to_ticks(-0.5, 90000)


def test_source_ticks_rescale_keeps_duration():
    # The 1× law: a source window keeps its DURATION across the unit change.
    # 4s of source media at SOURCE_TIMEBASE stays 4s at any version timebase.
    four_seconds_source = 4 * SOURCE_TIMEBASE
    assert source_ticks_to_output_ticks(four_seconds_source, 90000) == four_seconds_source
    assert source_ticks_to_output_ticks(four_seconds_source, 1000) == 4000


def test_ticks_to_seconds_display_inverse():
    assert ticks_to_seconds(45000) * 2 == 1
