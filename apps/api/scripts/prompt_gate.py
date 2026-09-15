"""Prompt gate (ADR-071 Consequences, T2 2026-09-12): the pre-deploy
behavioral threshold for the intent router's system prompt.

NOT an A/B instrument (that is `scratch/router_ab_probe.py`, for prompt
editing sessions) — this gate asserts ABSOLUTE minimum rates for the LIVE
prompt, so a regression is caught before deploy, not after. Three probes,
same contexts as the A/B instrument:

- A:start-call — a book on the table + "looks good, start" must call
  start_run (never a same-chain re-plan). Measured band 9-11/12 across all
  prompt versions; threshold 8 catches a real regression (the 2/5-era
  degradation) with flake headroom.
- B:slot-handshake — pending topic question + free-text answer must propose
  brief.topic user-stated on the terminal call (else the user's answer falls
  on the floor). Measured 8/8 and 12/12; threshold 8/12 fails a return to
  the old prompt's ~2/3 band.
- C:rootless-wish — a rootless wish must end at ask_user slot='topic'. The
  stub execute MIRRORS the production guardrail (a rootless present_plan is
  rejected with the gate's feedback), so both the direct ask and the
  corrected-after-rejection path count — only docking groundless work or
  answering away fails. Measured 11-12/12; threshold 10.

Tool-loop form (ADR-077 判词②, 2026-09-14): the agent is the ToolLoopAgent,
the action IS the terminal tool call, and the predicates read
``LoopResult`` — the thresholds are UNCHANGED. T2b (2026-09-15): the gate's
agent carries the production tool set INCLUDING the book path's read tools
(BOOK_READ_TOOLS — the registry perturbation is the thing being gated), and
the stub execute answers reads with a ToolObservation so the loop iterates
to its terminal call exactly like production.

A gate failure means: re-run once (provider drift exists even at these
thresholds), then bisect with the A/B instrument — never tune the
thresholds to make a regression pass.

Usage (from apps/api):
    uv run python scripts/prompt_gate.py [--n 12] [--probe A|B|C]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel  # noqa: E402

from app.agents.tool_loop import (  # noqa: E402
    LoopResult,
    ToolLoopAgent,
    ToolObservation,
)
from app.chat.intent import _assemble_book_turn  # noqa: E402
from app.chat.perception import PERCEPTION_TOOLS  # noqa: E402
from app.chat.prompts import intent_router_system  # noqa: E402
from app.chat.turn_tools import BOOK_READ_TOOLS, BOOK_TOOLS  # noqa: E402
from app.models.schemas import BriefLedger, BriefSlotSource  # noqa: E402
from app.models.tables import Message  # noqa: E402

# (probe, minimum passes out of N)
THRESHOLDS = {"A": 8, "B": 8, "C": 10}

LEDGER_ANSWERED = BriefLedger.model_validate(
    {
        "topic": {"value": "EU AI Act for researchers", "source": "user-stated"},
        "audience": {"value": "researchers", "source": "user-stated"},
        "material_state": {"value": "none", "source": "default"},
        "asked": ["topic"],
    }
)
LEDGER_EMPTY_ASKED = BriefLedger.model_validate(
    {
        "material_state": {"value": "none", "source": "default"},
        "asked": ["topic"],
    }
)
TOPIC_QUESTION = Message(
    role="assistant",
    content="What topic should the post cover?",
    question={
        "question": "What topic should the post cover — one phrase is enough?",
        "options": [],
        "slot": "topic",
        "default_path": "skip and I'll draft from your persona's style",
        "allow_freeform": True,
    },
)

PROBE_A = {
    "message": "looks good, start",
    "brief": LEDGER_ANSWERED,
    "presented_book": "write_post (language: en) — 'EU AI Act post for researchers'",
    "recent": [
        "user: I want a social post.",
        "assistant: What topic should the post cover — one phrase is enough?",
        "user: Make it about the EU AI Act for researchers.",
        "assistant: Got it — a post on the EU AI Act for researchers, drafted "
        "in your persona's style. Start it as-is, or tell me what to adjust.",
    ],
}
PROBE_B = {
    "message": "Make it about the EU AI Act for researchers.",
    "brief": LEDGER_EMPTY_ASKED,
    "pending_question": TOPIC_QUESTION,
    "recent": [
        "user: I want a social post.",
        "assistant: What topic should the post cover — one phrase is enough?",
    ],
}
# Scenario users have NO persona (scripts/chat_scenarios.py persona_exists:
# False) — the gate matches or the pantry changes the judgment surface.
PROBE_C = {"message": "I want a social post."}


async def _gate_execute(name: str, params: BaseModel | None, prose: str):
    """The gate's execution stub — accepts everything EXCEPT the rootless
    present_plan (mirrors the production 出书门槛 probe C measures: no
    user-stated topic, no material, and the topic never asked → the gate
    rejects toward ask_user). None = accepted (terminal). T2b: a read tool
    answers with a ToolObservation (the probe contexts have nothing readable)
    so the loop iterates on to its terminal call exactly like production."""
    if name in PERCEPTION_TOOLS:
        return ToolObservation(
            "(gate stub: nothing readable in this probe context)"
        )
    if name == "present_plan":
        brief = getattr(params, "brief", None)
        topic = brief.topic if brief else None
        rooted = (
            topic is not None
            and bool((topic.value or "").strip())
            and topic.source == BriefSlotSource.USER_STATED
        ) or bool((getattr(params, "material_text", None) or "").strip())
        if not rooted:
            return (
                "the brief has no root (no topic, no material, no explicitly "
                "named grounded recipe) and the topic was never asked — a "
                "rootless plan never docks. Call ask_user with slot='topic' "
                "asking the ONE topic question."
            )
    return None


def _passed(probe: str, r: LoopResult) -> bool:
    if probe == "A":
        return r.tool_name == "start_run"
    if probe == "B":
        brief = getattr(r.params, "brief", None)
        topic = brief.topic if brief else None
        return (
            topic is not None
            and bool((topic.value or "").strip())
            and topic.source == BriefSlotSource.USER_STATED
        )
    # C: the direct ask OR the corrected-after-rejection ask — the terminal
    # call must be the topic question either way.
    return r.tool_name == "ask_user" and getattr(r.params, "slot", None) == "topic"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--probe", choices=["A", "B", "C"], default=None)
    args = parser.parse_args()

    agent = ToolLoopAgent(
        name="prompt_gate_router",
        prompt="intent_router.j2",
        system=intent_router_system(),
        temperature=0.2,
        assemble=_assemble_book_turn,
        tools=[*BOOK_TOOLS, *BOOK_READ_TOOLS],
        max_iterations=6,
    )
    probes = {"A": PROBE_A, "B": PROBE_B, "C": PROBE_C}
    failed = False
    for name, ctx in probes.items():
        if args.probe and name != args.probe:
            continue
        outcomes = []
        for _ in range(args.n):
            try:
                r = await agent.call_loop(_gate_execute, **ctx)
                outcomes.append(_passed(name, r))
            except Exception as e:  # noqa: BLE001 — provider errors count as failures
                outcomes.append(False)
                print(f"  probe {name} call error: {type(e).__name__}", file=sys.stderr)
        hits = sum(outcomes)
        need = THRESHOLDS[name]
        ok = hits >= need
        failed |= not ok
        print(f"probe {name}: {hits}/{args.n} (threshold {need}) — {'PASS' if ok else 'FAIL'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
