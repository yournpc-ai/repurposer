"""System Status labels for the chat SSE ``assistant.thinking`` frames
(三概念分家, ADR-087 §1/§3: phase = System Status 宏观态, never work
evidence — the agent's work rides the Activity channel). Emitted ONLY at
a real macro-state switch; a label earns its place only when the state
structurally differs from thinking (2026-09-04 user ruling). Phase 3
Batch B retired every stand-in: ③ took drafting / inspecting(+key) /
repairing (their beats are the Activity projector's name-known /
rejection seats now), ⑤ took creating_run after the B4 CDP dead-window
forensics proved it never renders as the sole cover (the Activity RUN
milestone + the run surface own that segment). Sole survivor: composing
(判词 3 保留义 — the read→think takeover below).
The read→think takeover (交互完整性批 C, 2026-09-17): an ACCEPTED read's
observation is on the wire and the loop enters a QUIET decision iteration
(15-25s of LLM time) — without this frame the row would keep wearing a
stale label for work that already finished (the 「Caption styles checked →
putting it together」gap). Emitted at the observation's acceptance, never
for a rejection (the repair ACTIVITY owns that window now).

Seat (Phase 3 Batch C): one home for the System Status vocabulary, and the
callback is public so propose_turn / plan_turn stop importing a private
name across modules (ADR-087 §6).
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
