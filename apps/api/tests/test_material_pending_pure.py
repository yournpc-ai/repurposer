"""Pure tests for the material-pending lane's land-time suppression
(落地时刻压制批) — the marked commitment re-reads the world at land time and
never lands stale.

No DB, no LLM, no HTTP (suite discipline). What is gated HERE:

- ``pending_commitment_verdict``'s truth table: suppress only when the model
  marked the commitment AND the understanding beat already landed AND no
  plan sits docked (a docked plan self-silences the review turn — the
  commitment must stay or nobody speaks);
- the ``material_pending`` lane marker's wire contract on both answer
  schemas: absent / explicit null reads as False (打字机律牙① — a rejected
  iteration never streams), True rides, and ``extra="forbid"`` stays the
  unknown-key alarm;
- ``ChatResponse.assistant_message`` tolerates None (the silent close's
  envelope);
- ``DeferredFrames`` (言语提交协议's four-state machine — OPEN → BUFFERING →
  ACCEPT→FLUSH / REJECT→DROP→RETRY): arrival order survives a flush, a
  retract clears the stale queue at once and marks the turn frame-silent,
  a flush stays armed (mid-turn release replays each frame exactly once),
  a drop discards unsent and disarms, a disarmed buffer passes frames
  through live, and a None hook wraps to None (the one-shot path arms
  nothing).
"""

import pytest
from pydantic import ValidationError

from app.chat.deferred_frames import DeferredFrames
from app.chat.service import pending_commitment_verdict
from app.models.schemas import ChatAnswerArgs, ChatResponse, PlanAnswerArgs


class TestPendingCommitmentVerdict:
    def test_marked_with_beat_and_no_plan_suppresses(self) -> None:
        assert (
            pending_commitment_verdict(
                lane_marked=True, beat_landed=True, plan_docked=False
            )
            == "suppress"
        )

    def test_unmarked_answer_never_suppresses(self) -> None:
        """A capability answer with uploads draining in the background must
        never vanish. The lane's identity is a DOUBLE gate — the model's
        marker AND the assemble stamp (files pending at assemble); the turn
        composes both into ``lane_marked``, so an unmarked input releases
        even with a beat on file (an old warm's beat has no review coming)."""
        assert (
            pending_commitment_verdict(
                lane_marked=False, beat_landed=True, plan_docked=False
            )
            == "release"
        )

    def test_no_beat_releases(self) -> None:
        """Processing still runs — the commitment is the bridge."""
        assert (
            pending_commitment_verdict(
                lane_marked=True, beat_landed=False, plan_docked=False
            )
            == "release"
        )

    def test_docked_plan_releases(self) -> None:
        """A docked plan self-silences the review turn (单一叙事者律第二谓词)
        — suppressing here would leave nobody speaking."""
        assert (
            pending_commitment_verdict(
                lane_marked=True, beat_landed=True, plan_docked=True
            )
            == "release"
        )


class TestLaneMarkerWireContract:
    def test_plan_answer_defaults_false(self) -> None:
        assert PlanAnswerArgs.model_validate({}).material_pending is False

    def test_plan_answer_explicit_null_reads_as_default(self) -> None:
        args = PlanAnswerArgs.model_validate({"material_pending": None})
        assert args.material_pending is False

    def test_plan_answer_true_rides(self) -> None:
        args = PlanAnswerArgs.model_validate({"material_pending": True})
        assert args.material_pending is True

    def test_plan_answer_unknown_key_still_rejects(self) -> None:
        with pytest.raises(ValidationError):
            PlanAnswerArgs.model_validate({"material_pendingg": True})

    def test_chat_answer_defaults_false(self) -> None:
        assert ChatAnswerArgs.model_validate({}).material_pending is False

    def test_chat_answer_explicit_null_reads_as_default(self) -> None:
        args = ChatAnswerArgs.model_validate({"material_pending": None})
        assert args.material_pending is False

    def test_chat_answer_true_rides(self) -> None:
        args = ChatAnswerArgs.model_validate({"material_pending": True})
        assert args.material_pending is True

    def test_chat_answer_unknown_key_still_rejects(self) -> None:
        with pytest.raises(ValidationError):
            ChatAnswerArgs.model_validate({"material_pendingg": True})


class TestChatResponseToleratesSilentClose:
    def test_assistant_message_defaults_to_none(self) -> None:
        """The suppressed turn's envelope carries no assistant row."""
        field = ChatResponse.model_fields["assistant_message"]
        assert field.default is None


class TestDeferredFrames:
    """The speech-commit state machine's six-item checklist (批次 G2):
    ① reject→zero leak; ② retry→only the final envelope, no A+B double
    flush; ③ accept→frame order stable; ④ (the disconnect seat is the
    S-int-14 scenario) — here: a buffer replays each frame exactly once;
    ⑤ zero-delta→the rejected turn's close drops, the envelope paces whole;
    ⑥ two iterations→the stale buffer is cleared at the rejection."""

    @pytest.mark.asyncio
    async def test_flush_replays_in_arrival_order(self) -> None:
        """③ accept→frame order stable."""
        calls: list[tuple[str, tuple]] = []

        async def hook(*args) -> None:
            calls.append(("real", args))

        deferred = DeferredFrames({"delta": hook, "tool_call": hook})
        on_delta = deferred.wrap("delta")
        on_tool_call = deferred.wrap("tool_call")
        assert on_delta is not None and on_tool_call is not None
        await on_delta("好")
        await on_delta("的")
        await on_tool_call("answer")
        assert calls == []  # nothing streamed while armed
        await deferred.flush()
        assert calls == [
            ("real", ("好",)),
            ("real", ("的",)),
            ("real", ("answer",)),
        ]
        assert deferred.armed  # a flush STAYS armed — the close disarms
        deferred.disarm()
        assert not deferred.armed

    @pytest.mark.asyncio
    async def test_reject_leaks_zero_and_retry_sees_only_the_envelope(self) -> None:
        """①+②+⑤: a retracted turn's frames never reach the hooks — the
        stale queue clears AT the rejection, the retry's own frames queue
        fresh, and the rejected close drops them too (the settled envelope
        paces the final words whole, the zero-delta path's law)."""
        calls: list[tuple] = []

        async def hook(*args) -> None:
            calls.append(args)

        deferred = DeferredFrames({"delta": hook, "tool_call": hook})
        on_delta = deferred.wrap("delta")
        on_tool_call = deferred.wrap("tool_call")
        assert on_delta is not None and on_tool_call is not None
        # iteration 0: the at-risk speech queues
        await on_delta("给你做成中文配音版")
        await on_tool_call("present_plan")
        # REJECT: the stale buffer clears at once, the turn marks
        deferred.retract()
        assert deferred.rejected
        assert deferred.armed  # RETRY re-arms by construction
        # the retry (quiet iteration) queues its own structure frames fresh
        await on_tool_call("present_plan")
        # the rejected close drops — zero frames ever reached the hooks
        deferred.drop()
        assert calls == []
        assert not deferred.armed

    @pytest.mark.asyncio
    async def test_mid_turn_flush_replays_each_frame_exactly_once(self) -> None:
        """④'s process-internal half: the checkpoint channel's flush-first
        replays the queue once and STAYS armed — later frames queue fresh,
        never a double replay of the pre-flush ones."""
        calls: list[tuple] = []

        async def hook(*args) -> None:
            calls.append(args)

        deferred = DeferredFrames({"delta": hook})
        on_delta = deferred.wrap("delta")
        assert on_delta is not None
        await on_delta("先读一段")
        await deferred.flush()  # the checkpoint's flush-first
        assert calls == [("先读一段",)]
        assert deferred.armed
        await on_delta("收口")
        await deferred.flush()  # the clean close
        assert calls == [("先读一段",), ("收口",)]  # no A+B double flush
        deferred.disarm()

    @pytest.mark.asyncio
    async def test_passthrough_after_disarm(self) -> None:
        calls: list[tuple] = []

        async def hook(*args) -> None:
            calls.append(args)

        deferred = DeferredFrames({"delta": hook})
        on_delta = deferred.wrap("delta")
        assert on_delta is not None
        await deferred.flush()
        deferred.disarm()
        await on_delta("live")
        assert calls == [("live",)]

    @pytest.mark.asyncio
    async def test_drop_discards_unsent(self) -> None:
        """The material-pending suppress seat: the stale commitment's queue
        never sends, the turn closes silent."""
        calls: list[tuple] = []

        async def hook(*args) -> None:
            calls.append(args)

        deferred = DeferredFrames({"delta": hook})
        on_delta = deferred.wrap("delta")
        assert on_delta is not None
        await on_delta("读完就跟你说")
        deferred.drop()
        assert calls == []
        assert not deferred.armed

    @pytest.mark.asyncio
    async def test_flush_after_drop_is_a_no_op(self) -> None:
        calls: list[tuple] = []

        async def hook(*args) -> None:
            calls.append(args)

        deferred = DeferredFrames({"delta": hook})
        deferred.drop()
        await deferred.flush()
        assert calls == []

    def test_none_hook_wraps_to_none(self) -> None:
        deferred = DeferredFrames({"delta": None})
        assert deferred.wrap("delta") is None

    def test_retract_marks_and_clears_stale(self) -> None:
        """⑥: two iterations — the first's queued frames clear AT the
        rejection (never linger into the retry), the rejected flag sticks
        for the close."""
        deferred = DeferredFrames({})
        assert deferred.rejected is False
        deferred.retract()
        assert deferred.rejected is True
        assert deferred.armed  # the retry re-arms by construction
