"""Pure tests for the decompiler's deterministic half + skeleton schema (ADR-078).

批次⑥ T5 Commit ①. Scope: craft_scan is deterministic computer vision over
SYNTHETIC numpy frames — no DB, no LLM, no video fixture. The acceptance
assertion 骨架确定性字段零 LLM 介入 is gated twice: structurally
(CraftJudgment carries exactly the LLM seats and nothing else, so the agent
CANNOT write a deterministic field) and by a source scan (craft_scan
imports no provider/agent module). The caption-preset Literal drift gate
mirrors the perception catalog's import-time assert (executes.py).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, get_args, get_origin

import numpy as np
import pytest
from pydantic import ValidationError

from app.pipeline import craft_scan
from app.models.schemas import (
    ClipSpec,
    CraftCaptionScan,
    CraftJudgment,
    CraftRhythm,
    CraftShot,
    CraftSkeleton,
)


# ---------------------------------------------------------------------------
# 零 LLM 介入 — the acceptance assertion's two gates
# ---------------------------------------------------------------------------


def test_zero_llm_craft_scan_imports_no_provider():
    """The deterministic layer's module source carries no LLM import —
    top-level OR lazy (both appear as import lines)."""
    src = Path(craft_scan.__file__).read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in src.splitlines()
        if re.match(r"^(import|from)\s", line.strip())
    ]
    banned = ("app.providers", "app.agents", "openai", "anthropic")
    for line in import_lines:
        assert not any(b in line for b in banned), (
            f"an LLM import leaked into the deterministic layer: {line}"
        )


def test_zero_llm_judgment_schema_has_no_deterministic_seat():
    """CraftJudgment = exactly the LLM seats; CraftSkeleton = deterministic ∪
    LLM — the agent's output schema structurally CANNOT carry aspect / shots
    / rhythm / captions."""
    det = {"version", "aspect", "duration_seconds", "shots", "rhythm", "captions"}
    llm = {"music_mood", "hook_device", "gaps"}
    assert set(CraftJudgment.model_fields) == llm
    assert set(CraftSkeleton.model_fields) == det | llm


def test_caption_preset_literal_mirrors_clip_spec():
    """Drift gate: CraftCaptionScan.preset's Literal == ClipSpec's (which
    mirrors packages/clip/src/captions.ts — the behavior source of truth)."""
    spec_ids = set(get_args(ClipSpec.model_fields["caption_style_preset"].annotation))
    scan_ann = CraftCaptionScan.model_fields["preset"].annotation
    scan_ids: set[str] = set()
    for arg in get_args(scan_ann):
        if get_origin(arg) is Literal:
            scan_ids.update(get_args(arg))
    assert scan_ids == spec_ids


# ---------------------------------------------------------------------------
# synthetic frames (detection space is whatever we hand it — no resize here)
# ---------------------------------------------------------------------------

_W, _H = 144, 256  # portrait; the band is y∈[140,243), x∈[8,135)


def _blank(color=(0, 0, 0)) -> np.ndarray:
    img = np.zeros((_H, _W, 3), dtype=np.uint8)
    img[:] = color
    return img


def _with_line(img: np.ndarray, color, y0: int, y1: int, x0: int = 20, x1: int = 120) -> np.ndarray:
    """Paint a caption-like line (absolute frame coords inside the band)."""
    img[y0:y1, x0:x1] = color
    return img


def _frames(images: list[np.ndarray], tick: float = 0.5) -> list[craft_scan.SampledFrame]:
    return [craft_scan.SampledFrame(t=i * tick, image=img) for i, img in enumerate(images)]


_WHITE = (255, 255, 255)
_YELLOW = (0, 255, 255)  # BGR


# ---------------------------------------------------------------------------
# shot segmentation + rhythm
# ---------------------------------------------------------------------------


def test_detect_shots_abrupt_cut():
    images = [_blank((0, 0, 0)) for _ in range(8)] + [_blank(_WHITE) for _ in range(8)]
    shots = craft_scan.detect_shots(_frames(images), 8.0)
    assert len(shots) == 2
    assert shots[0]["start"] == 0.0 and abs(shots[0]["end"] - 4.0) < 0.6
    assert shots[1]["end"] == 8.0


def test_detect_shots_steady_single_span():
    shots = craft_scan.detect_shots(_frames([_blank() for _ in range(4)]), 2.0)
    assert shots == [{"start": 0.0, "end": 2.0}]


def test_detect_shots_merges_sub_min_runs():
    """A one-tick flash (a cut artifact) merges into the previous shot."""
    images = (
        [_blank((0, 0, 0)) for _ in range(5)]
        + [_blank(_WHITE)]
        + [_blank((0, 0, 0)) for _ in range(5)]
    )
    shots = craft_scan.detect_shots(_frames(images, tick=0.2), 2.0)
    assert len(shots) == 2
    assert abs(shots[0]["end"] - 1.2) < 1e-6


def test_rhythm_bands():
    fast = craft_scan.rhythm_of(
        [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 2.0}, {"start": 2.0, "end": 3.0}],
        3.0,
    )
    assert fast["pace"] == "fast" and fast["shot_count"] == 3
    assert fast["cuts_per_minute"] == pytest.approx(40.0)
    steady = craft_scan.rhythm_of([{"start": 0.0, "end": 3.0}, {"start": 3.0, "end": 6.0}], 6.0)
    assert steady["pace"] == "steady"
    slow = craft_scan.rhythm_of([{"start": 0.0, "end": 8.0}], 8.0)
    assert slow["pace"] == "slow" and slow["cuts_per_minute"] == 0.0


def test_aspect_nearest_tier():
    assert craft_scan.aspect_of(1080, 1920) == "9:16"
    assert craft_scan.aspect_of(1920, 1080) == "16:9"
    assert craft_scan.aspect_of(1000, 1000) == "1:1"
    assert craft_scan.aspect_of(1200, 1000) == "1:1"
    assert craft_scan.aspect_of(1400, 1000) == "16:9"
    assert craft_scan.aspect_of(0, 0) == "9:16"  # degenerate input degrades, never crashes


# ---------------------------------------------------------------------------
# caption band scan — visual nearest-neighbor best-fit over the contract enums
# ---------------------------------------------------------------------------

_SPEC_PRESET_IDS = set(get_args(ClipSpec.model_fields["caption_style_preset"].annotation))


def test_caption_absent_on_blank():
    scan = craft_scan.analyze_caption_band(_frames([_blank() for _ in range(6)]))
    assert scan == {"present": False, "presence": 0.0}


def test_caption_static_white_reads_clean_bottom():
    images = [_with_line(_blank(), _WHITE, 180, 200) for _ in range(6)]
    scan = craft_scan.analyze_caption_band(_frames(images))
    assert scan["present"] is True
    assert scan["preset"] in _SPEC_PRESET_IDS  # best-fit never leaves the enum
    assert scan["preset"] == "clean-bottom"
    assert scan["color"] == craft_scan.CAPTION_COLOR_PALETTE["white"]
    assert 0.55 <= scan["position_y"] <= 0.95


def test_caption_karaoke_sweep_reads_karaoke_highlight():
    """Stable line geometry, the saturated (yellow) share sweeping upward =
    the karaoke signal — and the color snaps to the palette's yellow."""
    images = []
    for share in (0.0, 0.1, 0.4, 0.6):
        img = _with_line(_blank(), _WHITE, 180, 200)
        split = 20 + int(100 * share)
        if share > 0:
            img[180:200, 20:split] = _YELLOW
        images.append(img)
    scan = craft_scan.analyze_caption_band(_frames(images))
    assert scan["preset"] == "karaoke-highlight"
    assert scan["color"] == craft_scan.CAPTION_COLOR_PALETTE["yellow"]


def test_caption_stacking_reads_stacking():
    """The text block's top edge climbs while the bottom holds = stacking."""
    images = [
        _with_line(_blank(), _WHITE, 210, 220),  # band-local 70..80
        _with_line(_blank(), _WHITE, 200, 220),  # 60..80
        _with_line(_blank(), _WHITE, 190, 220),  # 50..80
    ]
    scan = craft_scan.analyze_caption_band(_frames(images))
    assert scan["preset"] == "stacking"


def test_palette_snap_membership():
    palette = craft_scan.CAPTION_COLOR_PALETTE
    assert craft_scan.nearest_palette_color((250, 230, 70)) == palette["yellow"]
    assert craft_scan.nearest_palette_color((255, 255, 255)) == palette["white"]
    assert craft_scan.nearest_palette_color((20, 20, 20)) == palette["black"]
    for rgb in [(120, 200, 240), (10, 240, 120), (250, 40, 40)]:
        assert craft_scan.nearest_palette_color(rgb) in palette.values()


# ---------------------------------------------------------------------------
# skeleton assembly
# ---------------------------------------------------------------------------


def test_skeleton_roundtrip_from_scan_shape():
    """The scan's dict feeds the deterministic seats verbatim; the LLM layer
    defaults to None/[] (a degraded call leaves the deterministic layer
    intact — 声明化兜底, not silent)."""
    skeleton = CraftSkeleton(
        aspect="9:16",
        duration_seconds=8.0,
        shots=[CraftShot(start=0.0, end=4.0), CraftShot(start=4.0, end=8.0)],
        rhythm=CraftRhythm(shot_count=2, cuts_per_minute=7.5, median_shot_seconds=4.0, pace="steady"),
        captions=CraftCaptionScan(present=False),
    )
    assert skeleton.music_mood is None and skeleton.hook_device is None
    assert skeleton.gaps == []


def test_skeleton_rejects_out_of_enum_preset():
    with pytest.raises(ValidationError):
        CraftCaptionScan(present=True, preset="glitter-blast")


def test_selftest_runs():
    craft_scan._selftest()
