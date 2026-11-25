"""Flagship eval must fail closed when any part of the Chat delivery is missing."""

from types import SimpleNamespace

import pytest
from PIL import Image

from scripts.eval_chat_e2e import SCENARIOS, MediaProbeReport
from scripts.eval_flagship import mid_act_seconds, score_cut, score_delivery, screenshots


def test_flagship_registration_and_screenshots(tmp_path):
    scenario = SCENARIOS["rookie_flagship_launch"]
    assert len(scenario.turns) >= 2
    assert "/" not in scenario.turns[0] and "kinetic-launch" not in scenario.turns[0]
    assert {"load_skill", "save_composition_as_skill", "export_video"} <= set(
        scenario.expected_tools
    )
    with pytest.raises(ValueError, match="--assets-dir"):
        screenshots(tmp_path)
    path = tmp_path / "product.JPG"
    Image.new("RGB", (4, 4)).save(path)
    assert screenshots(tmp_path) == [path]


def test_flagship_cut_requires_used_screens_no_speech_and_a_timed_recipe():
    from app.editing.catalog import SOUND_ENGINE_NAME

    ranges = [
        {"start": 0, "end": 5000},
        {"start": 5000, "end": 18000},
        {"start": 18000, "end": 26000},
    ]
    scenes = [{"range": r} for r in ranges]
    assert mid_act_seconds(scenes, 1000) == (2.5, 11.5, 22)
    assert not mid_act_seconds(scenes[:1], 1000)
    clip = {
        "clip_id": "hit",
        "range": {"start": 4910, "end": 5800},
        "source": {"snapshot_id": "sound"},
        "object": {"kind": "audio"},
    }
    visual = {
        "range": ranges[0],
        "object": {"kind": "motion_block", "resources": [{"snapshot_id": "screen"}]},
    }
    tracks = [{"role": "main", "clips": [visual]}, {"role": "effect", "clips": [clip]}]
    version = SimpleNamespace(
        timeline={"tracks": tracks}, scenes=scenes, settings={"timebase": 1000}
    )
    origin = {
        "kind": "sound_recipe",
        "engine": SOUND_ENGINE_NAME,
        "engine_version": 3,
        "acoustics": {"peak_offset_ms": 90},
    }
    snaps = {
        "sound": SimpleNamespace(kind="audio", meta={"origin": origin}),
        "screen": SimpleNamespace(kind="image", asset_id="upload", meta={}),
    }

    def checks():
        return score_cut(version, snaps, {"upload"})

    assert all(checks().values())
    origin["acoustics"]["peak_offset_ms"] = 200
    assert not checks()["sound_engine_peak_on_beat_or_cut"]
    origin["acoustics"]["peak_offset_ms"] = 90
    origin["engine_version"] = 2
    assert not checks()["sound_engine_peak_on_beat_or_cut"]
    visual["object"] = {"kind": "speech"}
    assert not checks()["zero_narration"] and not checks()["uploaded_screenshot_in_cut"]
    tracks[1]["clips"] = []
    assert not checks()["effect_track_nonempty"]
    assert not any(score_cut(None, {}, set()).values())


def test_flagship_delivery_requires_opening_call_numbered_slots_and_actual_media():
    load = {"tool": "load_skill", "ok": True, "arguments": {"skill_id": "kinetic-launch"}}
    save = {"tool": "save_composition_as_skill", "ok": True, "arguments": {}}
    turns = [[load], [save]]
    preview = {"slots": [{"code": "[01]"}], "copyable_checklist": "[01] product"}
    media = MediaProbeReport(
        path="export.mp4",
        exists=True,
        passed=True,
        duration_seconds=26,
        extracted_pngs=["one", "two", "three"],
        non_black_frames=3,
    )
    assert all(score_delivery(turns, 200, preview, media).values())
    assert not score_delivery([[save], [load]], 200, preview, media)["autonomous_kinetic_launch"]
    load["arguments"]["skill_id"] = "other"
    assert not score_delivery(turns, 200, preview, media)["autonomous_kinetic_launch"]
    assert not score_delivery(turns, 404, preview, media)["slot_blueprint_v1_numbered_preview"]
    preview["slots"][0]["code"] = "[02]"
    assert not score_delivery(turns, 200, preview, media)["slot_blueprint_v1_numbered_preview"]
    media.duration_seconds, media.extracted_pngs, media.passed = 15, [], False
    checks = score_delivery(turns, 200, preview, media)
    assert not checks["launch_duration_25_to_30_seconds"]
    assert not checks["cross_act_midpoint_pngs"] and not checks["export_media_probe"]
    assert not any(score_delivery([], None, {}, None).values())
