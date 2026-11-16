"""Current saved-video render ownership and recovery folds."""

from app.pipeline.render_ownership import (
    CLOSED_STEP_STATUSES,
    StepView,
    needs_render_reconcile,
    prune_writer_barrier,
    writer_steps_for_output,
)


def _step(id: str, kind: str, seq: int, inputs: tuple[str, ...] = ()) -> StepView:
    return StepView(id=id, kind=kind, seq=seq, inputs=inputs, fork=False, target_output_id=None)


def test_saved_video_waits_for_its_birth_step():
    steps = [_step("produce", "produce_video", 10)]
    assert writer_steps_for_output(steps, birth_step_id="produce", output_id="video") == ["produce"]


def test_no_legacy_morph_can_join_a_new_render_barrier():
    steps = [
        _step("produce", "produce_video", 10),
        _step("legacy", "dub_clip", 20, ("produce",)),
    ]
    assert writer_steps_for_output(steps, birth_step_id="produce", output_id="video") == ["produce"]
    assert writer_steps_for_output(steps, birth_step_id=None, output_id="old") == []


def test_only_closed_steps_leave_a_barrier():
    assert CLOSED_STEP_STATUSES == ("failed", "skipped")
    assert prune_writer_barrier(["a", "b", "c"], ["b"]) == ["a", "c"]


def test_reconcile_targets_only_unmirrored_pending_outputs():
    assert needs_render_reconcile(has_render_spec=True, render_status=None, archived=False, has_pending_render_step=False) is True
    assert needs_render_reconcile(has_render_spec=True, render_status="rendering", archived=False, has_pending_render_step=False) is False
    assert needs_render_reconcile(has_render_spec=True, render_status=None, archived=True, has_pending_render_step=False) is False
    assert needs_render_reconcile(has_render_spec=False, render_status=None, archived=False, has_pending_render_step=False) is False
