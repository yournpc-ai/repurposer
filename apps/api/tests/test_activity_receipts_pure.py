"""Pure coverage for review report → Activity receipt → model-wire isolation."""
from __future__ import annotations

from typing import Any

import pytest

from app.agents.tool_loop import (
    ChatTool,
    ReadAccepted,
    ReadExecuting,
    ToolObservation,
    ToolRejected,
)
from app.chat.activity import ActivityProjector, frame_persistence
from app.chat.activity_receipts import video_review_receipt
from test_tool_loop_pure import EchoArgs, StubClient, _call, _make_agent


def _report() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "output_id": "output-internal-id",
        "summary": "Model summary must stay out of Activity",
        "execution_digest": "digest-internal",
        "video_sha256": "sha-internal",
        "frames": [
            {
                "frame_id": "F01",
                "time_seconds": 1.5,
                "frame": 45,
                "scene_id": "scene-internal",
                "storage_key": "video-review/internal.jpg",
                "digest": "frame-digest",
            },
            {
                "frame_id": "F02",
                "time_seconds": 3,
                "frame": 90,
                "storage_key": "video-review/internal-2.jpg",
                "digest": "frame-digest-2",
            },
        ],
        "findings": [
            {
                "kind": "observed_issue",
                "frame_id": "F01",
                "observed": "The title is clipped at the right edge.",
                "suggestion": "Reduce the title width.",
                "clip_id": "clip-internal",
            },
            {
                "kind": "aesthetic_suggestion",
                "frame_id": "F02",
                "observed": "The closing frame has little visual hierarchy.",
                "suggestion": "Increase the title's emphasis.",
            },
        ],
        "media_inspection": {
            "issues": [
                {"code": "AUDIO_QUIET", "observed": "Measured audio is quiet."},
                {"code": "AUDIO_FUTURE_CODE", "observed": "Unknown future fact."},
            ],
            "audio": {"rms_dbfs": -31.2, "peak_dbfs": -8.0},
            "visual": {"flat_frame_candidates": [{"mean_luma": 0.2}]},
        },
        "scope": {
            "actual_output_decoded": True,
            "static_frames_checked": True,
            "deterministic_output_checks": True,
            "sampled_frame_signals_checked": True,
            "audio_signal_checked": True,
            "motion_and_transitions_checked": False,
            "audio_and_av_sync_checked": False,
        },
    }


def test_report_maps_exactly_to_the_user_safe_receipt() -> None:
    report = _report()
    receipt = video_review_receipt(report)
    assert receipt is not None
    assert receipt.model_dump(mode="json") == {
        "kind": "video_review",
        "frames": [
            {"frame_id": "F01", "time_seconds": 1.5},
            {"frame_id": "F02", "time_seconds": 3.0},
        ],
        "findings": [
            {
                "kind": "observed_issue",
                "frame_id": "F01",
                "observed": "The title is clipped at the right edge.",
            },
            {
                "kind": "aesthetic_suggestion",
                "frame_id": "F02",
                "observed": "The closing frame has little visual hierarchy.",
            },
        ],
        "output_issue_codes": ["AUDIO_QUIET"],
        "scope": report["scope"],
    }
    # Translation is a read-only projection; the original full report survives.
    assert report["media_inspection"]["issues"][1]["code"] == "AUDIO_FUTURE_CODE"
    assert report["summary"] == "Model summary must stay out of Activity"


def test_empty_findings_and_malformed_reports_keep_their_distinct_semantics() -> None:
    report = _report()
    report["findings"] = []
    receipt = video_review_receipt(report)
    assert receipt is not None and receipt.findings == []
    assert "summary" not in receipt.model_dump()

    malformed = _report()
    del malformed["scope"]["audio_signal_checked"]
    assert video_review_receipt(malformed) is None


def _review_projector() -> tuple[ActivityProjector, list]:
    projector = ActivityProjector()
    assert projector.name_known("review_video") == []
    return projector, projector.feed_event(ReadExecuting(tool_name="review_video"))


def test_only_accepted_settled_video_review_done_carries_a_receipt() -> None:
    receipt = video_review_receipt(_report())
    projector, active = _review_projector()
    assert len(active) == 1 and active[0].receipt is None
    assert frame_persistence(active[0]) is None

    settled = projector.feed_event(
        ReadAccepted(tool_name="review_video", receipt=receipt)
    )
    assert len(settled) == 1
    assert settled[0].key == "chat.activity.videoReviewDone"
    assert settled[0].receipt is receipt
    assert frame_persistence(settled[0]) == "append"
    assert projector.settled_frames() == settled
    dumped = settled[0].to_dict()
    assert dumped["receipt"]["kind"] == "video_review"
    assert "summary" not in dumped["receipt"]
    assert "media_inspection" not in dumped["receipt"]


def test_rejected_cancelled_failed_and_non_review_frames_never_gain_receipts() -> None:
    receipt = video_review_receipt(_report())

    rejected, active = _review_projector()
    cancelled = rejected.feed_event(
        ToolRejected("execute_guardrail", "review_video", 0, "no", 1)
    )
    assert active[0].receipt is None
    assert cancelled[0].status == "cancelled" and cancelled[0].receipt is None

    failed, _ = _review_projector()
    swept = failed.sweep("failed")
    assert swept[0].status == "failed" and swept[0].receipt is None

    other = ActivityProjector()
    other.name_known("design_video")
    other.feed_event(ReadExecuting(tool_name="design_video"))
    done = other.feed_event(ReadAccepted(tool_name="design_video", receipt=receipt))
    assert done[0].key == "chat.activity.videoDesignDone"
    assert done[0].receipt is None
    assert "receipt" not in done[0].to_dict()


def test_review_without_a_valid_report_receipt_is_quietly_failed() -> None:
    projector, _ = _review_projector()
    settled = projector.feed_event(ReadAccepted(tool_name="review_video", receipt=None))
    assert settled[0].status == "failed"
    assert settled[0].key == "chat.activity.videoReview"
    assert settled[0].receipt is None


def test_failed_second_review_never_overwrites_the_first_done_receipt() -> None:
    projector, _ = _review_projector()
    receipt = video_review_receipt(_report())
    first = projector.feed_event(
        ReadAccepted(tool_name="review_video", receipt=receipt)
    )[0]

    projector.name_known("review_video")
    projector.feed_event(ReadExecuting(tool_name="review_video"))
    second = projector.feed_event(
        ToolRejected("execute_guardrail", "review_video", 1, "no valid report", 20)
    )[0]
    projector.sweep("completed")

    assert first.status == "completed"
    assert first.key == "chat.activity.videoReviewDone" and first.receipt is receipt
    assert second.status == "cancelled"
    assert second.key == "chat.activity.videoReview" and second.receipt is None
    assert second.key != "chat.activity.videoReviewDone"
    assert projector.settled_frames() == [first, second]


@pytest.mark.asyncio
async def test_receipt_sideband_never_changes_the_model_tool_wire() -> None:
    receipt = video_review_receipt(_report())
    review = ChatTool("review_video", "Review it.", None, terminal=False)
    echo = ChatTool("echo", "Echo the text.", EchoArgs)
    client = StubClient([
        _call("review_video", {}, prose="I checked the exact video"),
        _call("echo", {"text": "done"}, prose="The title is clipped"),
    ])
    events: list[object] = []

    async def execute(name: str, params: Any, prose: str):
        if name == "review_video":
            return ToolObservation("the original full report", receipt=receipt)
        return None

    agent = _make_agent("tl_activity_receipt", client, tools=[review, echo])
    result = await agent.call_loop(execute, on_loop_event=events.append)
    assert result.calls == ["review_video", "echo"]
    assert client.seen_messages[1][3] == {
        "role": "tool",
        "tool_call_id": "c1",
        "name": "review_video",
        "content": "the original full report",
    }
    accepted = next(event for event in events if isinstance(event, ReadAccepted))
    assert accepted.receipt is receipt
