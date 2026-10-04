"""Pure tests for the speech-commit state machine (言语提交协议, G2) and its
static seats.

No DB, no LLM, no HTTP (suite discipline). What is gated HERE:

- ``ChatResponse.assistant_message`` tolerates None (the silent close's
  envelope);
- ``DeferredFrames`` (the four-state machine — OPEN → BUFFERING →
  ACCEPT→FLUSH / REJECT→DROP→RETRY): arrival order survives a flush, a
  retract clears the stale queue at once and marks the turn frame-silent,
  a flush stays armed (mid-turn release replays each frame exactly once),
  a drop discards unsent and disarms, a disarmed buffer passes frames
  through live, and a None hook wraps to None (the one-shot path arms
  nothing);
- the retract seat's static lock: both turn modules isinstance-match the
  LOOP's ToolRejected class, never app.tools' registry exception.
"""

import pytest

from app.chat.deferred_frames import DeferredFrames
from app.models.schemas import ChatResponse


class TestChatResponseToleratesSilentClose:
    def test_assistant_message_defaults_to_none(self) -> None:
        """A turn that closes without an assistant row (the degrade paths)
        carries None in the envelope."""
        field = ChatResponse.model_fields["assistant_message"]
        assert field.default is None


class TestRetractSeatMatchesTheLoopClass:
    """The 2026-10-03 leak's static lock: both turn modules carry TWO
    ``ToolRejected`` names (the tool_loop event AND app.tools' chain-
    adjudication exception — the later import shadows the former). The
    retract seat must isinstance-match the LOOP's class, or every
    ToolRejected forwards without retracting and the rejected turn's
    queued prose flushes at the close (the leak, reproduced in-process
    before the alias fix)."""

    def test_plan_turn_retract_seat_is_the_loop_event_class(self) -> None:
        import app.agents.tool_loop as tool_loop
        import app.chat.plan_turn as plan_turn

        assert plan_turn.LoopToolRejected is tool_loop.ToolRejected

    def test_propose_turn_retract_seat_is_the_loop_event_class(self) -> None:
        import app.agents.tool_loop as tool_loop
        import app.chat.propose_turn as propose_turn

        assert propose_turn.LoopToolRejected is tool_loop.ToolRejected

    def test_the_two_tool_rejected_classes_are_distinct(self) -> None:
        """The shadow hazard itself stays on file: app.tools.ToolRejected
        (the registry exception) is NOT the loop event — a bare
        ``ToolRejected`` reference in either turn module resolves to the
        registry's, never the loop's."""
        import app.agents.tool_loop as tool_loop
        from app.tools import ToolRejected as RegistryRejected

        assert RegistryRejected is not tool_loop.ToolRejected


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
        """A dropped queue never sends — the close-without-speech primitive
        (generic; the failure/abort seat)."""
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
