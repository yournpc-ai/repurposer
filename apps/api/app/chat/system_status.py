"""Status phases on the existing assistant.thinking channel.

Accepted reads switch to composing. Dock-stage film preparation reports
capturing, storyboarding and storyboard_revision at real transitions.
These refine the generic draft activity; empty heartbeat frames never
change the current phase. Completed work remains on the activity channel.
"""

THINKING_PHASE_COMPOSING = "composing"


def observe_phase_callback(on_phase):
    """Map the loop's accepted-read signal (``on_observe``) onto the SSE
    phase pipe — the read→think takeover frame (THINKING_PHASE_COMPOSING).
    None-safe like the repair callback (the one-shot path has no pipe)."""
    if on_phase is None:
        return None

    async def _emit(_tool_name: str) -> None:
        await on_phase(THINKING_PHASE_COMPOSING)

    return _emit
