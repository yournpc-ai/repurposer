"""The B-UI shared viewer's persisted identity and ordering projection."""
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from app.models.tables import Output
from app.pipeline.outputs import chat_delivery_output_ids, is_delivered_output


def _message(run_id, trigger):
    return SimpleNamespace(
        workflow_run_id=run_id,
        intent={"type": "trigger_review", "trigger": trigger},
    )


def _step(run_id, seq, refs):
    return SimpleNamespace(id=uuid4(), run_id=run_id, seq=seq, output_refs=refs)


def test_chat_outputs_follow_delivery_transcript_then_persisted_ref_order():
    first_run, second_run = uuid4(), uuid4()
    first, second, repeated, other = (uuid4() for _ in range(4))
    # The second run started earlier but delivered later; plan/start run links
    # are not delivery seats and must not reorder the shared browser.
    messages = [
        SimpleNamespace(workflow_run_id=second_run, intent={"type": "task_book"}),
        SimpleNamespace(workflow_run_id=first_run, intent={"type": "task_book"}),
        _message(first_run, "run_completed"),
        _message(second_run, "run_completed"),
        _message(first_run, "run_completed"),
    ]
    steps = [
        _step(second_run, 2, [other]),
        _step(first_run, 2, [repeated, second]),
        _step(first_run, 1, [first, repeated]),
        _step(second_run, 1, [repeated]),
    ]

    assert chat_delivery_output_ids(messages, steps) == [first, repeated, second, other]


def test_silent_delivery_keeps_its_persisted_run_receipt_seat():
    run_id = uuid4()
    output_id = uuid4()
    messages = [SimpleNamespace(workflow_run_id=run_id, intent={"type": "task_book"})]
    assert chat_delivery_output_ids(messages, [_step(run_id, 1, [output_id])]) == [output_id]


def test_materialized_quote_images_keep_their_producing_steps_delivery_seat():
    run_id, quotes, image = uuid4(), uuid4(), uuid4()
    step = _step(run_id, 1, [quotes])
    images = [SimpleNamespace(id=image, workflow_step_id=step.id)]
    assert chat_delivery_output_ids([_message(run_id, "run_completed")], [step], images) == [quotes, image]


def _video(render_status, files=None, *, archived_at=None) -> Output:
    return cast(Output, SimpleNamespace(
        type="video",
        render_status=render_status,
        files={"video": "exact-output.mp4"} if files is None else files,
        archived_at=archived_at,
    ))


def test_only_completed_real_media_enters_the_delivery_viewer():
    assert is_delivered_output(_video("completed", archived_at=object()))
    assert not is_delivered_output(_video("pending"))
    assert not is_delivered_output(_video("failed"))
    assert not is_delivered_output(_video("completed", files={}))
    assert not is_delivered_output(_video("completed", files={"video": ""}))
