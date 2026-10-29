"""Pure seams of the first exact-Output content-review journey."""
from __future__ import annotations

import hashlib
from uuid import UUID

import pytest

from app.models.schemas import ReviewVideoArgs
from app.tools.video.review import (
    ContentReviewAnswer,
    ReviewFinding,
    ReviewFrame,
    _extract_frames,
    _report_findings,
    _reusable_report,
    _scene_targets,
)
from test_render_probe_pure import _encode_mp4


def _spec() -> dict:
    return {
        "family": "video",
        "fps": {"num": 30, "den": 1},
        "duration_frames": 60,
        "tracks": [{
            "kind": "visual",
            "clips": [{
                "clip_id": "clp_title",
                "scene_id": "scn_hero",
                "start_frame": 0,
                "end_frame": 30,
                "object": {"kind": "text", "object_id": "obj_title", "text": "Readable"},
            }, {
                "clip_id": "clp_web",
                "scene_id": "scn_walk",
                "start_frame": 30,
                "end_frame": 60,
                "object": {"kind": "web", "object_id": "obj_web"},
            }],
        }],
    }


def test_scene_targets_come_from_executed_windows():
    targets = _scene_targets(_spec())
    assert [(float(target), scene) for target, scene in targets] == [(15.0, "scn_hero"), (45.0, "scn_walk")]


@pytest.mark.asyncio
async def test_actual_output_decode_preserves_frame_time_and_requested_time(tmp_path, monkeypatch):
    video = _encode_mp4(tmp_path / "review.mp4", frames=60, audio=False).read_bytes()

    async def store(data: bytes):
        digest = hashlib.sha256(data).hexdigest()
        return f"video-review/{digest}.jpg", digest

    monkeypatch.setattr("app.tools.video.review._store_frame", store)
    frames = await _extract_frames(video, _spec(), [1.5])
    assert [(frame.frame_id, frame.frame, frame.time_seconds) for frame in frames] == [
        ("F01", 45, 1.5),
    ]
    assert all(frame.jpeg.startswith(b"\xff\xd8") for frame in frames)


def test_findings_keep_real_time_and_drop_unproven_object_identity():
    frame = ReviewFrame("F01", 15, 0.5, "scn_hero", b"jpg", "d" * 64, "video-review/d.jpg")
    answer = ContentReviewAnswer(findings=[ReviewFinding(
        kind="observed_issue",
        frame_id="F01",
        observed="The title is clipped",
        requirement="The title must be readable",
        evidence="Its right edge is outside the picture",
        suggestion="Reduce the title size",
        clip_id="clp_title",
        object_id="obj_invented",
    )])
    finding = _report_findings(answer, [frame], _spec(), "Keep the title readable")[0]
    assert finding["time_seconds"] == 0.5 and finding["frame"] == 15
    assert finding["clip_id"] == "clp_title"
    assert finding["object_id"] is None


def test_findings_reject_an_undecoded_frame_reference():
    frame = ReviewFrame("F01", 15, 0.5, "scn_hero", b"jpg", "d" * 64, "video-review/d.jpg")
    answer = ContentReviewAnswer(findings=[ReviewFinding(
        kind="observed_issue", frame_id="F99", observed="Invented",
        requirement="Readable", evidence="No such frame", suggestion="None",
    )])
    with pytest.raises(ValueError, match="unknown frame"):
        _report_findings(answer, [frame], _spec(), "Report only decoded evidence")


def test_review_schema_normalizes_only_witnessed_aliases_and_identity_echoes():
    answer = ContentReviewAnswer.model_validate({
        "output_id": "echoed-server-owned-id",
        "composition_id": "echoed-server-owned-id",
        "composition_version_id": "echoed-server-owned-id",
        "summary": "One visible issue.",
        "findings": [{
            "type": "observed_issue",
            "frame_id": "F01",
            "observed_issue": "The title is clipped.",
            "visual_evidence": "Its final letters are outside the right edge.",
            "smallest_useful_change": "Reduce the title size.",
            "actual_time_seconds": 12.0,
            "scene_id": "echoed-scene",
        }],
    })
    finding = answer.findings[0]
    assert finding.kind == "observed_issue"
    assert finding.observed == "The title is clipped."
    assert finding.evidence == "Its final letters are outside the right edge."
    assert finding.suggestion == "Reduce the title size."
    with pytest.raises(ValueError, match="severity"):
        ContentReviewAnswer.model_validate({"findings": [{
            "kind": "observed_issue", "frame_id": "F01", "observed": "Clipped",
            "suggestion": "Resize", "severity": "high",
        }]})


def test_missing_requirement_and_evidence_reuse_request_and_observation():
    frame = ReviewFrame("F01", 15, 0.5, "scn_hero", b"jpg", "d" * 64, "video-review/d.jpg")
    answer = ContentReviewAnswer(findings=[ReviewFinding(
        kind="observed_issue", frame_id="F01", observed="The title is clipped",
        suggestion="Reduce the title size",
    )])
    finding = _report_findings(answer, [frame], _spec(), "Titles must remain readable")[0]
    assert finding["requirement"] == "Titles must remain readable"
    assert finding["evidence"] == "The title is clipped"


def _review_reuse_fixture(requirements="Check readability", at_seconds=None):
    output_id = UUID("260e3883-9fe0-4f99-b1ce-fd2211126682")
    report = {
        "output_id": str(output_id),
        "requirements": requirements,
        "at_seconds": at_seconds,
        "findings": [],
    }
    args = ReviewVideoArgs(
        output_id=output_id,
        requirements=requirements,
        at_seconds=at_seconds,
    )
    return output_id, report, args


def test_saved_report_reuse_requires_the_exact_same_request_and_sample():
    output_id, report, args = _review_reuse_fixture(at_seconds=[48.1])
    quality = {"content_review": report}

    assert _reusable_report(quality, output_id, args) is report
    assert _reusable_report(quality, output_id, args.model_copy(update={"refresh": True})) is None


def test_changed_requirements_or_legacy_metadata_never_reuse_a_report():
    output_id, report, args = _review_reuse_fixture()
    quality = {"content_review": report}

    changed = args.model_copy(update={"requirements": "Check the whole film"})
    assert _reusable_report(quality, output_id, changed) is None
    legacy = {"content_review": {key: value for key, value in report.items() if key != "at_seconds"}}
    assert _reusable_report(legacy, output_id, args) is None
    other_output = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert _reusable_report(quality, other_output, args) is None


def test_focused_recheck_never_stands_in_for_whole_film_sampling():
    output_id, focused, focused_args = _review_reuse_fixture(at_seconds=[48.1])
    whole_film_args = focused_args.model_copy(update={"at_seconds": None})
    quality = {"content_review": focused}

    assert _reusable_report(quality, output_id, whole_film_args) is None
    assert _reusable_report(quality, output_id, focused_args) is focused

    _, whole_film, _ = _review_reuse_fixture()
    assert _reusable_report({"content_review": whole_film}, output_id, focused_args) is None
