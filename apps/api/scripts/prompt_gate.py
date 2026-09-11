"""Prompt gate (ADR-071 Consequences, T2 2026-09-12): the pre-deploy
behavioral threshold for the intent router's system prompt.

NOT an A/B instrument (that is `scratch/router_ab_probe.py`, for prompt
editing sessions) — this gate asserts ABSOLUTE minimum rates for the LIVE
prompt, so a regression is caught before deploy, not after. Three probes,
same contexts as the A/B instrument:

- A:start-verdict — a book on the table + "looks good, start" must judge
  'start' (never a same-chain re-draft). Measured band 9-11/12 across all
  prompt versions; threshold 8 catches a real regression (the 2/5-era
  degradation) with flake headroom.
- B:slot-handshake — pending topic question + free-text answer must propose
  brief.topic user-stated (else the user's answer falls on the floor).
  Current prompt measured 8/8 and 12/12; threshold 8/12 fails a return to
  the old prompt's ~2/3 band.
- C:rootless-wish — a rootless wish must produce the topic ask. PASS counts
  both the direct ask verdict AND the harmless hybrid (draft + empty tasks
  + ask(topic)) that 判词⑦ re-reads as ask; only drafting groundless work
  or answering away fails. Current prompt measured 11-12/12; threshold 10.

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

from app.agents.base import StreamingAgent  # noqa: E402
from app.chat.intent import _assemble_book_turn  # noqa: E402
from app.chat.prompts import intent_router_system  # noqa: E402
from app.models.schemas import BriefLedger, InferredIntent  # noqa: E402
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


def _passed(probe: str, r: InferredIntent) -> bool:
    if probe == "A":
        return r.action == "start"
    if probe == "B":
        topic = r.brief.topic if r.brief else None
        return topic is not None and topic.source == "user-stated"
    # C: the direct ask OR the 判词⑦-harmless hybrid (draft + empty tasks +
    # ask(topic)) — the code re-reads the hybrid as the ask verdict.
    slot = r.ask.slot if r.ask else None
    if r.action == "ask":
        return slot == "topic"
    return r.action == "draft" and not r.tasks and slot == "topic"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--probe", choices=["A", "B", "C"], default=None)
    args = parser.parse_args()

    agent = StreamingAgent(
        name="prompt_gate_router",
        prompt="intent_router.j2",
        schema=InferredIntent,
        system=intent_router_system(),
        temperature=0.2,
        assemble=_assemble_book_turn,
    )
    probes = {"A": PROBE_A, "B": PROBE_B, "C": PROBE_C}
    failed = False
    for name, ctx in probes.items():
        if args.probe and name != args.probe:
            continue
        outcomes = []
        for _ in range(args.n):
            try:
                r = await agent.call(**ctx)
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
