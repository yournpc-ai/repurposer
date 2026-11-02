"""Pure seams of the first exact-Output content-review journey."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.schemas import ReviewVideoArgs
from app.tools.video.output_checks import OUTPUT_CHECKER_VERSION
from app.tools.video.review import (
    ContentReviewAnswer,
    ReviewAttemptFailed,
    ReviewFinding,
    ReviewFrame,
    _extract_frames,
    _previous_review_facts,
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
        "schema_version": 2,
        "media_inspection": {"checker_version": OUTPUT_CHECKER_VERSION},
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


def test_reports_without_the_current_deterministic_checker_are_not_reused():
    output_id, report, args = _review_reuse_fixture()
    legacy = {**report, "schema_version": 1}
    old_checker = {
        **report,
        "media_inspection": {"checker_version": "output-checks-v0"},
    }

    assert _reusable_report({"content_review": legacy}, output_id, args) is None
    assert _reusable_report({"content_review": old_checker}, output_id, args) is None


def test_reviewer_prompt_matches_the_real_schema_without_synonym_guidance():
    prompt = (Path(__file__).parents[1] / "app/prompts/video_reviewer.j2").read_text()
    assert set(ContentReviewAnswer.model_fields) == {"summary", "findings"}
    assert set(ReviewFinding.model_fields) == {
        "kind", "frame_id", "observed", "requirement", "evidence", "suggestion",
        "clip_id", "object_id",
    }
    assert ReviewFinding.model_fields["kind"].is_required()
    assert ReviewFinding.model_fields["frame_id"].is_required()
    assert ReviewFinding.model_fields["observed"].is_required()
    assert ReviewFinding.model_fields["suggestion"].is_required()
    for field in (
        "summary", "findings", "kind", "frame_id", "observed", "requirement",
        "evidence", "suggestion", "clip_id", "object_id",
    ):
        assert f"`{field}`" in prompt
    for wrong_field in ("inspection_scope", "requirement_affected", "recommendation"):
        assert wrong_field not in prompt


@pytest.mark.parametrize("payload, error", [
    ({"summary": "Checked two frames", "findings": [], "inspection_scope": {}}, "inspection_scope"),
    ({"findings": [{
        "frame_id": "F04", "observed_issue": "The title disappeared",
        "requirement_affected": "Keep the title visible",
        "smallest_useful_change": "Check its visibility",
    }]}, "kind"),
    ({"findings": [{
        "kind": "observed_issue", "frame_id": "F04", "observed_issue": "The title disappeared",
        "requirement": "Keep the title visible", "recommendation": "Check its visibility",
    }]}, "suggestion"),
])
def test_undeclared_review_payloads_still_fail_schema_validation(payload, error):
    with pytest.raises(ValueError, match=error):
        ContentReviewAnswer.model_validate(payload)


def test_prior_review_facts_carry_audio_checks_but_not_old_prose_or_frames():
    previous = {
        "requirements": "Check the whole delivered video",
        "at_seconds": None,
        "reviewed_at": "2026-11-02T07:36:00Z",
        "scope": {"audio_signal_checked": True},
        "media_inspection": {"audio": {"decode_ok": True, "rms_dbfs": -24.0}},
        "summary": "Old prose is not new evidence",
        "findings": [{"frame_id": "F02", "observed": "Old finding"}],
        "frames": [{"frame_id": "F01"}],
    }
    facts = _previous_review_facts(previous)
    assert facts == {
        "requirements": previous["requirements"],
        "at_seconds": None,
        "reviewed_at": previous["reviewed_at"],
        "scope": previous["scope"],
        "media_inspection": previous["media_inspection"],
    }

    from app.tools.video.agents import _assemble_review, video_reviewer

    assert video_reviewer.schema is ContentReviewAnswer
    assert "deterministic media checks" in video_reviewer.system
    context, media = _assemble_review(
        requirements="Recheck the entrance",
        output_facts="{}",
        storyboard="saved content",
        frame_facts="new F01",
        deterministic_checks=json.dumps(previous["media_inspection"]),
        previous_review_facts=json.dumps(facts),
        frames=["new-frame-only"],
    )
    assert context["deterministic_checks"].endswith("-24.0}")
    assert json.loads(context["previous_review_facts"])["scope"]["audio_signal_checked"] is True
    assert "Old prose" not in context["previous_review_facts"]
    assert media == ["new-frame-only"]


@pytest.mark.asyncio
async def test_failed_focused_recheck_closes_from_the_first_real_report(monkeypatch):
    from app.agents.tool_loop import LoopResult, TerminalRefusal
    from app.chat.propose_turn import ChatTurn
    from app.chat.video_turn_seats import review_video_seat
    from app.config import settings
    from app.tools.video import review

    previous = {
        "summary": "两个采样帧中的原文完整，未见裁切。",
        "frames": [{"frame_id": "F01"}, {"frame_id": "F02"}],
        "findings": [],
        "scope": {
            "deterministic_output_checks": True,
            "audio_signal_checked": True,
        },
    }

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def fail_review(*args, **kwargs):
        raise ReviewAttemptFailed(previous_report=previous)

    monkeypatch.setattr(settings, "video_project_enabled", True)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(review, "review_video", fail_review)
    refusal = await review_video_seat(
        project=SimpleNamespace(user_id=UUID("260e3883-9fe0-4f99-b1ce-fd2211126682")),
        args=ReviewVideoArgs(
            output_id=UUID("260e3883-9fe0-4f99-b1ce-fd2211126682"),
            requirements="复查清晰表达入场",
            at_seconds=[3.4, 3.5, 3.6, 3.9],
        ),
    )
    assert isinstance(refusal, TerminalRefusal)
    refusal_facts = refusal.facts
    assert refusal_facts is not None
    assert refusal_facts["previous_report"] is previous

    turn = object.__new__(ChatTurn)
    turn.outcome = None
    turn.deferred = None
    turn.text = "请检查刚刚交付的成片"
    turn.settled_question = None
    turn._bailed_on_skip = []
    turn.pending_judgable = False
    turn.db = None
    turn.conversation_id = UUID("3659c5ef-1265-45c4-87b2-2875e3531984")

    async def capture_message(db, conversation_id, role, content, **kwargs):
        return SimpleNamespace(role=role, content=content, question=None)

    monkeypatch.setattr("app.chat.propose_turn._create_message", capture_message)
    outcome = await turn.finish(LoopResult(
        prose="", tool_name=None, params=None, iterations=2,
        ended_by="review_video", refusal_facts=refusal_facts,
    ))
    message = outcome[0]
    assert message is not None
    content = message.content
    assert "上一次检查已完成" in content and "2 个采样帧" in content
    assert "音频流与 RMS/峰值" in content
    assert "3.4、3.5、3.6、3.9 秒的定点复查没有完成" in content
    assert "没有内容发现" in content and "主观听感仍未检查" in content
    assert "could you be more specific" not in content
    assert message.role == "assistant" and outcome[1] is None


def test_first_review_failure_has_no_invented_prior_facts():
    from app.chat.service import _video_review_failure_text

    zh = _video_review_failure_text("检查这个成片", {"previous_report": None})
    en = _video_review_failure_text("Review this video", {"previous_report": None})
    assert "这次成片检查没有完成" in zh and "上一次" not in zh
    assert "did not complete" in en and "earlier review" not in en
