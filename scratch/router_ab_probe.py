"""A/B probe: pre-diet vs post-diet router system prompt on the two S1
failure judgments (2026-09-11, ADR-071 diet regression hunt).

Probe A — start verdict: book on the table + "looks good, start" must
judge action='start' (S1 failure A judged 'draft').
Probe B — slot handshake: pending topic question + free-text answer must
propose brief.topic user-stated (S1 failure B emitted brief=None and
stuffed the topic into task params).

Run (from apps/api):
    uv run python ../../scratch/router_ab_probe.py [N]
"""

import asyncio
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.agents.base import StreamingAgent  # noqa: E402
from app.chat.intent import _assemble_book_turn  # noqa: E402
from app.models.schemas import BriefLedger, InferredIntent  # noqa: E402
from app.models.tables import Message  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 6

SNAP = REPO / "scratch" / "prompts_before_split.py"
old_mod = types.ModuleType("prompts_before_split")
old_mod.__dict__["__file__"] = str(SNAP)
exec(compile(SNAP.read_text(), str(SNAP), "exec"), old_mod.__dict__)

from app.chat.prompts import intent_router_system as new_system  # noqa: E402

SYSTEMS = {"old": old_mod.intent_router_system(), "new": new_system()}

# Build-up variant s1 (2026-09-11, bisect direction flip): the OLD system
# prompt + only the surgical, probe-worth-testing deltas applied by string
# patch. Every patch must apply (assert) or the variant is lying.
_s1 = old_mod.intent_router_system()


def _patch(s: str, old: str, new: str) -> str:
    assert old in s, f"patch anchor missing: {old[:60]!r}"
    return s.replace(old, new, 1)


# 1. confidence is dead weight (zero consumers) — drop the rule line.
_s1 = _patch(
    _s1,
    "- confidence: 0.0-1.0 indicating how clearly the intent was expressed.\n",
    "",
)
# 2. Zero-hardcoded-default-chain (ADR-071 判词②): the vague default chain
#    is deleted, not replaced.
_s1 = _patch(
    _s1,
    "  - Default chain when the request is vague ('帮我做内容', 'repurpose "
    "this'): with a media file attached → select_clips, write_post, "
    "write_quotes, write_article; text only → write_post, write_quotes, "
    "write_article. Set tasks_explicit false in this case.\n",
    "",
)
# 3. Media gating is stated twice (the no-material block above says it) —
#    drop the tasks-section duplicate.
_s1 = _patch(
    _s1,
    "  - Media gating (split per tool family — 2026-08-24):\n"
    "    • select_clips / translate_clip / dub_clip / remove_filler /\n"
    "      add_music / reframe_clip need an attached media file\n"
    "      (video, audio, or image). When the user's request asks for\n"
    "      any of these and no file is attached, propose them ONLY\n"
    "      IF material_text carries synthesizable content — otherwise\n"
    "      drop them and explain in echo prose.\n"
    "    • write_post / write_quotes / write_carousel / write_article\n"
    "      do NOT need source material. They draft from the user's\n"
    "      prompt + persona style. When the user has nothing, they\n"
    "      still work — the no-material echo (EXCEPTION 2 above)\n"
    "      carries the soft signal to the user.\n",
    "",
)
# 4. Sediment tags out of tokens (ADR-071 判词③) — archaeology parentheses
#    and ADR refs stripped, rule bodies verbatim.
_s1 = _patch(_s1, "'draft' has NO hard material requirement (2026-08-24 lift):", "'draft' has NO hard material requirement:")
_s1 = _patch(_s1, "applies ONLY\n    to the safety-net ask-back (the prompt below would have refused\n    any chain without material). It", "applies ONLY to the ask-back refusal. It")
_s1 = _patch(_s1, " in the user's language (2026-09-02 任务书瘦身 — the old 2-4-sentence restatement said four times what the card's rows already say once). Sentence 1:", " in the user's language. Sentence 1:")
_s1 = _patch(_s1, "never a form field (顾问姿态 law 3). ", "never a form field. ")
_s1 = _patch(_s1, "a single word (顾问姿态: 每问可一词答), phrased", "a single word, phrased")
_s1 = _patch(_s1, "DENSITY (ADR-054):", "DENSITY:")
_s1 = _patch(_s1, "EXCEPTION 2 — text-only generation (2026-08-24):", "EXCEPTION 2 — text-only generation:")
_s1 = _patch(_s1, "the brief-ledger update you propose this turn (ADR-052 B2).", "the brief-ledger update you propose this turn.")
_s1 = _patch(_s1, "(ADR-064 顺形律: a plain array of sourced items; never wrap the list in an object)", "(a plain array of sourced items; never wrap the list in an object)")
# (ADR-070's surface-neutral Start sentence is already in the snapshot —
# it was taken after that edit; no patch needed here.)

SYSTEMS["s1"] = _s1


def make_agent(tag: str, system: str) -> StreamingAgent:
    return StreamingAgent(
        name=f"probe_router_{tag}",
        prompt="intent_router.j2",
        schema=InferredIntent,
        system=system,
        temperature=0.2,
        assemble=_assemble_book_turn,
    )


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

# Probe C — rootless wish (S1 first-turn degrade hunt): must judge ask with
# slot=topic. A draft verdict with EMPTY tasks is the poisoned shape — the
# repair funnel has no path back to ask (retry.tasks empty → degrade to the
# refusal line), so this misjudgment rate is the S1 first-assertion flake.
# The scenario user has NO persona (scripts/chat_scenarios.py:848
# persona_exists=False) — the probe must match or the pantry changes the
# judgment surface.
PROBE_C = {
    "message": "I want a social post.",
}


async def main() -> None:
    agents = {tag: make_agent(tag, system) for tag, system in SYSTEMS.items()}
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    for probe_name, ctx in (
        ("A:start-verdict", PROBE_A),
        ("B:slot-handshake", PROBE_B),
        ("C:rootless-wish", PROBE_C),
    ):
        if only and not probe_name.startswith(only):
            continue
        print(f"\n=== probe {probe_name} (N={N}, round-robin) ===")
        outcomes: dict[str, list[str]] = {tag: [] for tag in agents}
        # Round-robin across variants per call — provider state drifts over
        # minutes, and sequential per-variant batches confound the variant
        # with time (caught 2026-09-11: s1 measured after old+new looked
        # worse than old on pure deletions, an implausible direction).
        tags = list(agents)
        for i in range(N):
            for tag in tags:
                try:
                    r = await agents[tag].call(**ctx)
                except Exception as e:  # noqa: BLE001
                    outcomes[tag].append(f"ERROR:{type(e).__name__}")
                    continue
                if probe_name.startswith("A"):
                    outcomes[tag].append(r.action)
                elif probe_name.startswith("C"):
                    slot = r.ask.slot if r.ask else None
                    outcomes[tag].append(f"{r.action}/slot={slot}/tasks={len(r.tasks)}")
                else:
                    topic = r.brief.topic if r.brief else None
                    src = topic.source if topic else None
                    outcomes[tag].append(f"{r.action}/topic={src}")
        for tag, o in outcomes.items():
            print(f"  {tag}: {o}")


asyncio.run(main())
