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
    TaskItem,
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


# ---------------------------------------------------------------------------
# compile-time injection + node/agent declaration (批次⑥ T5 ②)
# ---------------------------------------------------------------------------

import app.tools  # noqa: F401,E402 — the registry door (populates NODE_KINDS)
from app.agents.base import AGENTS  # noqa: E402
from app.pipeline.graph import NODE_KINDS  # noqa: E402
from app.pipeline.orchestrator import TaskSpec, compile_graph  # noqa: E402
from app.tools import TOOL_REGISTRY  # noqa: E402


def _compile(tasks: list[TaskItem], **kw):
    return compile_graph(TaskSpec(tasks=tasks, **kw), materialize_profile="media")


def test_decompile_injected_only_when_exemplar_pinned():
    pinned = _compile(
        [TaskItem(tool="select_clips")], exemplar_asset_id="11111111-1111-1111-1111-111111111111"
    )
    kinds = [n.kind for n in pinned]
    assert "decompile" in kinds
    decompile = next(n for n in pinned if n.kind == "decompile")
    plan = next(n for n in pinned if n.kind == "plan")
    assert decompile.inputs == [0]  # off preprocess, parallel to understand
    assert pinned.index(decompile) < pinned.index(plan)
    assert pinned.index(decompile) in plan.inputs  # planning waits for the skeleton
    assert decompile.spec["asset_id"] == "11111111-1111-1111-1111-111111111111"
    # The pin's compile spec carries ONLY the asset id — the skeleton itself
    # is a run-time product, never compile-time state.
    assert set(decompile.spec) == {"asset_id"}

    unpinned = _compile([TaskItem(tool="select_clips")])
    assert "decompile" not in [n.kind for n in unpinned]


def test_decompile_injection_survives_review_tier():
    nodes = _compile(
        [TaskItem(tool="select_clips")],
        exemplar_asset_id="11111111-1111-1111-1111-111111111111",
        autonomy="review",
    )
    kinds = [n.kind for n in nodes]
    assert kinds[:5] == ["preprocess", "persona_bootstrap", "understand", "decompile", "interrupt"]
    plan = nodes[5]
    assert plan.kind == "plan"
    assert set(plan.inputs) == {3, 4}  # interrupt + decompile


def test_decompile_skipped_on_modifier_only_chain():
    """v1 documented seat: no plan prelude → no injection (the exemplar
    honors would find no skeleton and fall to defaults anyway)."""
    nodes = _compile([TaskItem(tool="add_music")], exemplar_asset_id="x")
    kinds = [n.kind for n in nodes]
    assert "decompile" not in kinds
    assert "materialize_source" in kinds  # sanity: the chain still compiled


def test_task_spec_pins_store_verbatim():
    """The pins ride TaskSpec → run.context verbatim (the model_dump seat)."""
    spec = TaskSpec(
        tasks=[TaskItem(tool="select_clips")],
        source_asset_id="s1",
        exemplar_asset_id="e1",
    )
    dumped = spec.model_dump(mode="json")
    assert dumped["source_asset_id"] == "s1"
    assert dumped["exemplar_asset_id"] == "e1"


def test_decompile_node_declaration():
    """Internal crew standing: registered in NODE_KINDS, NEVER in the
    proposal-space TOOL_REGISTRY; its agent reference resolves."""
    node = NODE_KINDS["decompile"]
    assert node.task_name and node.task_name_zh
    assert "decompile" not in TOOL_REGISTRY
    assert all(a.name in AGENTS for a in node.agents)


def test_decompile_assemble_signature_carries_no_deterministic_seat():
    """Purity is signature-enforced (ADR-039): the decompile agent's inputs
    are facts/media/catalog only — no deterministic field can be passed."""
    import inspect

    from app.agents.registry import _assemble_decompile

    params = set(inspect.signature(_assemble_decompile).parameters)
    assert params == {"facts", "mood_catalog", "keyframes", "transcript_excerpt"}
    assert params.isdisjoint({"aspect", "shots", "rhythm", "captions"})


def test_decompile_mood_clamped_to_catalog():
    from app.agents.registry import _clamp_judgment

    off = _clamp_judgment(
        CraftJudgment(music_mood="epic-trailer", hook_device="title card"),
        {"mood_catalog": ["calm", "uplifting"]},
    )
    assert off.music_mood is None  # an off-catalog pick never reaches a spec
    assert off.hook_device == "title card"
    on = _clamp_judgment(CraftJudgment(music_mood="calm"), {"mood_catalog": ["calm"]})
    assert on.music_mood == "calm"


# ---------------------------------------------------------------------------
# exemplar param mapping (批次⑥ T5 ③ — 判词⑤: code maps, the LLM never
# writes a spec; precedence = explicit > exemplar > defaults)
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from app.models.schemas import AssetType, Point  # noqa: E402


def _skeleton(**over) -> CraftSkeleton:
    base: dict = {
        "aspect": "9:16",
        "duration_seconds": 30.0,
        "shots": [CraftShot(start=0.0, end=3.0), CraftShot(start=3.0, end=6.0)],
        "rhythm": CraftRhythm(
            shot_count=2, cuts_per_minute=4.0, median_shot_seconds=3.0, pace="steady"
        ),
        "captions": CraftCaptionScan(present=False),
    }
    base.update(over)
    return CraftSkeleton(**base)


def test_skeleton_clip_count_clamps_to_declared_limits():
    from app.pipeline.decompile import skeleton_clip_count

    assert skeleton_clip_count(None, (1, 10)) is None
    assert skeleton_clip_count(_skeleton(), (1, 10)) == 2
    fast = _skeleton(
        rhythm=CraftRhythm(shot_count=42, cuts_per_minute=84.0, median_shot_seconds=0.7, pace="fast")
    )
    # The birthplace C3 bounds bind code-mapped values too.
    assert skeleton_clip_count(fast, (1, 10)) == 10
    empty = _skeleton(
        rhythm=CraftRhythm(shot_count=0, cuts_per_minute=0.0, median_shot_seconds=0.0, pace="slow")
    )
    assert skeleton_clip_count(empty, (1, 10)) is None


def test_skeleton_caption_overrides_absence_is_not_a_strip_signal():
    from app.pipeline.decompile import skeleton_caption_overrides

    assert skeleton_caption_overrides(None) == {}
    assert skeleton_caption_overrides(_skeleton()) == {}  # present=False ⇒ skin defaults keep
    present = _skeleton(
        captions=CraftCaptionScan(
            present=True,
            preset="stacking",
            color="#FDE047",
            position=Point(x=0.5, y=0.8),
        )
    )
    assert skeleton_caption_overrides(present) == {
        "preset": "stacking",
        "color": "#FDE047",
        "position": {"x": 0.5, "y": 0.8},
    }


def test_assemble_plan_carries_the_skeleton_seat():
    """判词⑤'s assemble-side seat: plan receives the skeleton as read-only
    facts; the self-sufficiency contract holds (no raw-source seats)."""
    import inspect

    from app.agents.registry import _assemble_plan

    params = set(inspect.signature(_assemble_plan).parameters)
    assert "craft_skeleton" in params
    assert params.isdisjoint({"assets", "source_blocks", "asset_media"})


# ---- render-source role honoring (判词④) ------------------------------------


def _fake_asset(asset_id: str, asset_type: AssetType, words: bool = True):
    return SimpleNamespace(
        id=asset_id,
        type=asset_type,
        file_url=f"file://{asset_id}",
        meta={"words": [{"w": "x"}]} if words else {},
        slide_pages=None,
    )


@pytest.mark.asyncio
async def test_render_source_pin_wins_exemplar_excluded_reversible():
    from app.tools.clips.node import resolve_render_source

    source = _fake_asset("s", AssetType.VIDEO)
    exemplar = _fake_asset("e", AssetType.VIDEO)
    node = SimpleNamespace(inputs=[])  # no align_stills upstream → db untouched

    # The pinned source wins the pick; the exemplar is not material.
    picked, kind, _ = await resolve_render_source(
        None, node, [exemplar, source], source_asset_id="s", exclude_asset_id="e"
    )
    assert picked is source and kind == "video"

    # Exclusion alone: the exemplar never becomes the material pool's pick.
    picked2, _, _ = await resolve_render_source(None, node, [exemplar], exclude_asset_id="e")
    assert picked2 is None

    # Role reversal (用案例本身也剪一条): the caller passes exclude=None when
    # source == exemplar — the case itself renders.
    picked3, _, _ = await resolve_render_source(
        None, node, [exemplar], source_asset_id="e", exclude_asset_id=None
    )
    assert picked3 is exemplar

    # A pinned source without a word axis falls through to the pool rules.
    silent = _fake_asset("silent", AssetType.VIDEO, words=False)
    other = _fake_asset("o", AssetType.VIDEO)
    picked4, _, _ = await resolve_render_source(
        None, node, [silent, other], source_asset_id="silent"
    )
    assert picked4 is other
