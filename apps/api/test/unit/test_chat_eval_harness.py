"""Layer 0 deterministic tests for the Layer 3 Chat-Origin audiovisual eval harness."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from scripts.eval_chat_e2e import (
    SCENARIOS,
    check_internal_id_leaks,
    collect_sse_telemetry,
    parse_sse_frames,
    probe_mp4_audiovisual,
    render_eval_report,
    score_chat_turn,
)
from test.support.media_helpers import encode_mp4


def test_sse_parser_and_turn_scorer_clean_pass_and_leak_detection():
    clean_sse = "\n".join(
        [
            'event: focus',
            'data: {"focus": "正在构思三幕动效节奏"}',
            '',
            'event: steps',
            'data: {"steps": [{"title": "创建三幕初稿", "status": "in_progress"}]}',
            '',
            'event: activity',
            'data: {"call_id": "c1", "tool_name": "create_video", "detail": "创建三幕动效短片"}',
            '',
            'event: delta',
            'data: {"delta": "已为你创建三幕宣传片 [v1 草稿](#workbench:version/11111111-2222-3333-4444-555555555555)。"}',
            '',
            'event: done',
            'data: {"message_id": "msg-1", "conversation_id": "conv-1", "content": "已为你创建三幕宣传片 [v1 草稿](#workbench:version/11111111-2222-3333-4444-555555555555)。"}',
            '',
        ]
    )
    frames = parse_sse_frames(clean_sse)
    telemetry = collect_sse_telemetry(frames)
    score = score_chat_turn(
        turn_index=1,
        prompt="做一个三幕短片",
        telemetry=telemetry,
        elapsed_seconds=4.2,
        require_steps_or_focus=True,
    )
    assert score.passed is True
    assert score.tool_names == ["create_video"]
    assert score.focus_count == 1
    assert score.steps_count == 1
    assert score.detail_count == 1
    assert score.internal_id_leaks == []
    assert score.assistant_message_id == "msg-1"

    # Leaking raw clip_id or composition_id fails deterministically
    leaks = check_internal_id_leaks("Updated clp_intro_01 on composition_id 11111111-2222-3333-4444-555555555555")
    kinds = {leak["kind"] for leak in leaks}
    assert {"clip_id", "composition_id_label", "raw_uuid"} <= kinds


def test_mp4_audiovisual_probe_validates_1080p_h264_48khz_aac_and_extracts_frames(tmp_path: Path):
    good_mp4 = encode_mp4(
        tmp_path / "good.mp4",
        width=1920,
        height=1080,
        frames=30,
        fps=30,
        audio=True,
        audio_rate=48000,
        tone_hz=440.0,
        fill_rgb=(40, 120, 210),
    )
    frames_dir = tmp_path / "frames"
    report = probe_mp4_audiovisual(good_mp4, frame_out_dir=frames_dir)
    assert report.passed is True, report
    assert report.video_codec == "h264"
    assert report.audio_codec == "aac"
    assert report.audio_sample_rate == 48000
    assert report.non_black_frames == report.sampled_frames == 3
    assert len(report.extracted_pngs) == 3
    assert all(Path(p).exists() for p in report.extracted_pngs)

    # All-black silent MP4 fails visual + audible checks
    bad_mp4 = encode_mp4(
        tmp_path / "black_silent.mp4",
        width=1920,
        height=1080,
        frames=30,
        fps=30,
        audio=True,
        audio_rate=48000,
        tone_hz=None,
        fill_rgb=(0, 0, 0),
        motion_stripe=False,
    )
    bad_report = probe_mp4_audiovisual(bad_mp4)
    assert bad_report.passed is False
    assert bad_report.checks["non_black_visuals"] is False
    assert bad_report.checks["audio_audible"] is False

    # Markdown report renderer works cleanly
    md = render_eval_report(
        {
            "scenario": "motion_block_promo",
            "title": SCENARIOS["motion_block_promo"].title,
            "total_elapsed_seconds": 12.5,
            "turns": [],
            "feedback_snapshot_verified": True,
            "media_probe": asdict(report),
            "passed": True,
        }
    )
    assert "Chat-Origin Eval Report" in md
    assert "48000 Hz" in md
