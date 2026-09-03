"""Intent agents (two distinct jobs behind the SINGLE chat surface, NAMING §5).

Both are declared instances of the funnel's one sanctioned subclass
(``StreamingAgent``, N-30 — the streaming special form, N-26); the declared
fallback / the adjudication repair echo are funnel stages, not bespoke code.
The model-facing prose lives one file over (``chat/prompts.py``, Mastra
instructions.md-style same-site extraction); this module is declarations +
turn assembly only.

``intent_router`` — the task-book builder (book path, CHAT_ARCH §3): free-form
text → a structured task book (language/outputs/tone) plus the four-action
verdict (draft / ask / answer / start). Invoked only from the chat service's
book path — first-turn projects and pending-task-book refinement turns.
Provider failures propagate as MiniMaxError: the route boundary answers 502
with the localized provider line (2026-08-14 裁定 — a fabricated default
book looks like a real plan and Start would spend a paid run on it; an
honest failure beats a wrong plan, and the user_key taxonomy makes the
failure presentable).

``chat_intent_agent`` — the chat loop's intent proposer (CHAT_ARCH §3): one
user message + assembled context → a four-state ``IntentProposal``
(task_list / edit_ops / ask / answer — N-18 + N-21). Single
tool-calling-style call per turn, never a ReAct loop; the LLM proposes and
``compile_graph`` adjudicates.
"""

from typing import Any

from app.agents.base import StreamingAgent
from app.chat.prompts import chat_intent_system, intent_router_system
from app.models.schemas import BriefLedger, InferredIntent, IntentResult
from app.models.tables import Persona


def _assemble_book_turn(
    message: str,
    brief: BriefLedger | None = None,
    persona: Persona | None = None,
    filename: str | None = None,
    presented_book: str | None = None,
    recent: list[str] | None = None,
    file_language: str | None = None,
    material_excerpt: str | None = None,
):
    """Book-turn inputs (ADR-052 B2 D2-C2 — the ledger is the state).

    ``message``: this turn's own words — never an accumulated prompt (the
    ledger carries the accumulated state; ``MAX_ACCUM_PROMPT_CHARS``'s
    head/tail bookkeeping retired with the switch).
    ``brief``: the code-merged ledger BEFORE this turn's proposal (material
    state freshly stamped) — rendered as the ledger block: valued slots with
    their source, the material line always, and the asked roll (the router
    reads it for the root judgment and never re-asks an asked slot).
    ``persona``: the turn's persona row (the caller resolves: explicit pick →
    pending book's → project mount → user default) — rendered as a few
    audience / identity / domain lines, asking strategy ②'s pantry: the
    one-word option values come from here first (the C2 fix — the rule was
    written but its pantry was never assembled, so options starved).
    ``presented_book``: one-line digest of the docked task book, when one is
    on the table — the start/revise verdict needs to SEE the plan being
    confirmed, not imagine it (a bare "开始吧" after a vague first turn
    otherwise reads as "go draft it").
    ``recent``: the conversation's latest rounds (pre-formatted lines,
    current message excluded) — the material/content judgment needs to SEE
    what just happened (e.g. the assistant asking for source material), not
    read the text in a vacuum (G-7).
    ``file_language``: the uploaded file's ASR-detected language — the
    transform-target rule's authoritative signal (2026-08-17 同源语言护栏).
    ``material_excerpt``: the material's opening excerpt (track-model §7.4
    折中版 — the plan layer is no longer blind to what the material SAYS;
    mechanical slice, zero extra LLM).
    """
    brief_lines: list[str] | None = None
    if brief is not None:
        lines = []
        for name in ("topic", "audience", "tone"):
            slot = getattr(brief, name)
            if slot.value:
                lines.append(f"- {name}: {slot.value} ({slot.source})")
        if brief.constraints.value:
            lines.append(
                f"- constraints: {', '.join(brief.constraints.value)} "
                f"({brief.constraints.source})"
            )
        # The material line always renders — the root judgment reads it.
        lines.append(f"- material: {brief.material_state.value or 'none'}")
        if brief.asked:
            lines.append(f"- already asked: {', '.join(brief.asked)}")
        brief_lines = lines
    # Persona block (Memory 单向注入 — the consumer pulls): restrained on
    # purpose — enough for strategy ② to pick concrete one-word options
    # (audience / domain terms), NOT the whole identity card.
    persona_lines: list[str] | None = None
    if persona is not None:
        lines = []
        if persona.name:
            lines.append(f"- name: {persona.name}")
        if persona.title:
            lines.append(f"- title: {persona.title}")
        if persona.audience:
            lines.append(f"- audience: {persona.audience}")
        values = [str(v) for v in (persona.core_values or []) if v][:6]
        if values:
            lines.append(f"- core values: {', '.join(values)}")
        if persona.emotional_tone:
            lines.append(f"- tone: {persona.emotional_tone}")
        persona_lines = lines or None
    return (
        {
            "message": message,
            "brief_lines": brief_lines,
            "persona_lines": persona_lines,
            "filename": filename,
            "presented_book": presented_book,
            "recent": recent,
            "file_language": file_language,
            "material_excerpt": material_excerpt,
        },
        [],
    )


# The registries are static once imported (the tools door opens them), so
# the system prompts are built once at declaration time.
intent_router: StreamingAgent[InferredIntent] = StreamingAgent(
    name="intent_router",
    prompt="intent_router.j2",
    schema=InferredIntent,
    system=intent_router_system(),
    temperature=0.2,
    assemble=_assemble_book_turn,
)


def _assemble_chat_turn(message: str, context: dict[str, Any]):
    """Chat-turn inputs: the user message plus the deterministic context
    digest (``agents/contexts.py``). Adjudication feedback never passes
    through here — it is the funnel's reserved ``repair_feedback`` kwarg."""
    return ({"context_text": context.get("text", ""), "message": message}, [])


chat_intent_agent: StreamingAgent[IntentResult] = StreamingAgent(
    name="chat_intent",
    prompt="chat_intent.j2",
    schema=IntentResult,
    system=chat_intent_system(),
    temperature=0.2,
    assemble=_assemble_chat_turn,
)
