"""Chat delivery ownership and the video-only Chat display gate."""
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from app.models.tables import Output
from app.pipeline.outputs import (
    chat_delivery_output_ids,
    delivered_output_refs,
    is_chat_video_output,
    is_delivered_output,
)


def _message(run_id, trigger, refs=None):
    intent = {"type": "trigger_review", "trigger": trigger}
    if refs is not None:
        intent["output_refs"] = [str(ref) for ref in refs]
    return SimpleNamespace(workflow_run_id=run_id, intent=intent)


def _step(run_id, seq, refs):
    return SimpleNamespace(id=uuid4(), run_id=run_id, seq=seq, output_refs=refs)


def test_chat_outputs_follow_each_delivery_messages_own_ref_order():
    first_run, second_run = uuid4(), uuid4()
    first, second, repeated, other = (uuid4() for _ in range(4))
    messages = [
        SimpleNamespace(workflow_run_id=second_run, intent={"type": "task_book"}),
        _message(first_run, "run_completed", [first, repeated]),
        _message(second_run, "run_completed", [other]),
        _message(first_run, "run_completed", [second, repeated]),
    ]

    assert chat_delivery_output_ids(messages) == [first, repeated, other, second]


def test_missing_output_refs_never_falls_back_to_run_steps():
    run_id = uuid4()
    messages = [
        _message(run_id, "run_completed"),
        SimpleNamespace(workflow_run_id=run_id, intent={"type": "task_book"}),
    ]
    # No Run-level collection remains: neither a step nor a neighbouring
    # receipt can assign an Output to a message.
    assert chat_delivery_output_ids(messages) == []


def test_zero_delivery_failure_message_has_an_honest_empty_collection():
    message = _message(uuid4(), "run_failed", [])
    assert chat_delivery_output_ids([message]) == []


def test_delivery_snapshot_filters_pending_failed_and_missing_media():
    run_id = uuid4()
    ready, pending, failed, empty = (uuid4() for _ in range(4))
    steps = [_step(run_id, 1, [ready, pending, failed, empty])]
    outputs = [
        _video("completed"),
        _video("rendering"),
        _video("failed"),
        _video("completed", files={}),
    ]
    for output, output_id in zip(outputs, [ready, pending, failed, empty], strict=True):
        output.id = output_id
    assert delivered_output_refs(steps, outputs) == [str(ready)]


def _video(render_status, files=None, *, archived_at=None) -> Output:
    return cast(Output, SimpleNamespace(
        type="video",
        render_status=render_status,
        files={"video": "exact-output.mp4"} if files is None else files,
        archived_at=archived_at,
    ))


def test_chat_gate_admits_only_delivered_video_without_changing_domain_delivery():
    ready = _video("completed", archived_at=object())
    assert is_delivered_output(ready)
    assert is_chat_video_output(ready)
    assert not is_chat_video_output(_video("pending"))
    assert not is_chat_video_output(_video("failed"))
    assert not is_chat_video_output(_video("completed", files={}))
    assert not is_chat_video_output(_video("completed", files={"video": ""}))

    post = cast(Output, SimpleNamespace(type="post", render_status=None, files={}))
    assert is_delivered_output(post)
    assert not is_chat_video_output(post)
