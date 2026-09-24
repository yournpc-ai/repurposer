"""Intent agents (two distinct jobs behind the SINGLE chat surface, NAMING §5).

Both are declared ``ToolLoopAgent`` instances (ADR-077 判词② — the bounded
tool-loop form, 2026-09-14): the action union retired into the tool set
(type field = tool name, per-state fields = params — a mechanical
translation), prose rides the content channel (it streams; the typewriter
law's key-order tooth retired with the JSON payload), and the adjudication
repair round re-homed into the loop (a rejected call's reason echoes back,
bounded by ``max_iterations``). The model-facing prose lives one file over
(``chat/prompts.py``, Mastra instructions.md-style same-site extraction);
the tool declarations in ``chat/turn_tools.py``; this module is declarations
+ turn assembly only.

``intent_router`` — the plan builder (plan path, CHAT_ARCH §3): free-form
text → present_plan (draft/refine the plan) / ask_user (the ONE deciding
question) / start_run (prose confirmation of the docked plan) / answer.
Invoked only from the chat service's plan path — first-turn projects and
pending-plan refinement turns. Provider failures propagate as LLMError:
the route boundary answers 502 with the localized provider line (2026-08-14
裁定 — a fabricated default plan looks like a real plan and Start would
spend a paid run on it; an honest failure beats a wrong plan, and the
user_key taxonomy makes the failure presentable).

``chat_intent_agent`` — the chat loop's intent proposer (CHAT_ARCH §3): one
user message + assembled context → one terminal call (propose_tasks /
edit_output / revise_output / edit_graph / ask_user / answer — the terminal
proposal states, mechanically — plus the iter-3 S2 exploration verbs: a post-run discovery
goal runs the SAME candidates → selects → plans chain as the plan path and
docks its decision package through this path's own seat, R6 parity). The
LLM proposes; ``compile_graph`` / the operations registry /
``apply_wiring_ops`` adjudicate — their rejections ARE the loop's
feedback.
"""

from typing import Any

from app.agents.tool_loop import ToolLoopAgent
from app.chat.exploration_tools import exploration_chat_tools
from app.chat.prompts import chat_intent_system, intent_router_system
from app.chat.turn_tools import (
    CHAT_READ_TOOLS,
    CHAT_TOOLS,
    PLAN_READ_TOOLS,
    PLAN_TOOLS,
)
from app.models.schemas import Brief
from app.models.tables import Message, Persona
from app.ui_locale import current_ui_language


_LANG_NATIVE = {"zh": "中文", "en": "English"}


def _speech_language_line(lang: str, mirror: bool = True) -> str:
    """The speech-language directive riding every LLM turn (2026-09-24 用户
    拍板，修订 2026-09-04 的「一律 = 系统语言」): speech MIRRORS the
    language of the user's own message — the LLM judges that itself
    (中文提问中文答 / English question English answer); the request's
    Accept-Language (app.ui_locale) named here is only the FLOOR for
    messages with no clear language signal. This governs OUR messages to
    the user (questions, option labels, prose, summaries), never the
    CONTENT's language — task language params follow their own rules, and
    the 2026-09-04 pantry-drag guard still holds: the persona's and the
    material's languages never steer speech. The floor language is named
    in its own tongue (中文 / English) — a bare subtag was empirically too
    weak against an all-English system prompt.

    mirror=False is the worker-born trigger turn's form: the turn's 'user
    message' there is a system EVENT line (English), not the user's voice,
    so mirroring is meaningless and the pinned language is absolute."""
    native = _LANG_NATIVE.get(lang, lang)
    if not mirror:
        return (
            f"Speech language: {native} ({lang}) — the interface language, "
            f"absolute for this turn (the event line above is a system "
            f"signal, not the user's voice). ALL user-facing text you "
            f"write (prose, every suggestion label) is in {native} "
            f"({lang}). (Content-language task params follow their own "
            f"rules.)"
        )
    return (
        f"Speech language: reply in the language of the user's CURRENT "
        f"message — judge it yourself (a pasted text or quoted fragment "
        f"inside the message is content, not the user's voice). If the "
        f"message gives no clear signal, use the interface language: "
        f"{native} ({lang}). ALL user-facing text you write (the question, "
        f"every option label, prose, the summary, default_path) follows "
        f"this choice. Never infer your speech language from the persona "
        f"or the material. (Content-language task params follow their own "
        f"rules.)"
    )


def _assemble_plan_turn(
    message: str,
    brief: Brief | None = None,
    persona: Persona | None = None,
    pending_question: Message | None = None,
    filename: str | None = None,
    presented_plan: str | None = None,
    recent: list[str] | None = None,
    file_language: str | None = None,
    material_excerpt: str | None = None,
    understanding_lines: list[str] | None = None,
    asset_lines: list[str] | None = None,
    material_pending_line: str | None = None,
    plans_lines: list[str] | None = None,
):
    """Plan-turn inputs (ADR-052 B2 D2-C2 — the brief is the state).

    ``message``: this turn's own words — never an accumulated prompt (the
    brief carries the accumulated state; ``MAX_ACCUM_PROMPT_CHARS``'s
    head/tail bookkeeping retired with the switch).
    ``brief``: the code-merged brief BEFORE this turn's proposal (material
    state freshly stamped) — rendered as the brief block: valued slots with
    their source, the material line always, and the asked roll (the router
    reads it for the root judgment and never re-asks an asked slot).
    ``persona``: the turn's persona row (the caller resolves: explicit pick →
    pending plan's → project mount → user default) — rendered as a few
    audience / identity / domain lines, asking strategy ②'s pantry: the
    one-word option values come from here first (the C2 fix — the rule was
    written but its pantry was never assembled, so options starved).
    ``pending_question``: the conversation's still-open plain question, when
    one awaits (ADR-053 R2 插话支持) — rendered as the pending block so the
    router judges THIS message against it first: a user-stated proposal for
    the pending slot IS the answer (code settles the row), anything else is
    an interjection (the question stays open, the reply gets the reminder
    tail).
    ``presented_plan``: one-line digest of the docked plan, when one is
    on the table — the start/revise call needs to SEE the plan being
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
    ``understanding_lines``: the READY material understanding's digest
    (ADR-083 信任锚注入 — top-tier semantic evidence for the echo's
    judgment duty, injected at assemble time off the content-addressed
    row: zero LLM, zero extra loop round; None when not yet materialized —
    the grounding hierarchy then falls through to the excerpt / the user's
    own words).
    ``asset_lines``: every attached file as one roster line (≥2 files only —
    ADR-078: the remix judgment must SEE the full roster to know a role
    question decides the plan; the single-file surface stays filename +
    excerpt).
    ``material_pending_line``: the readiness gate's code-stamped fact
    (I-PFA-07, 2026-09-18) — "N file(s) still processing / failed
    processing", rendered verbatim when uploads haven't drained; None when
    every file is readable. The router never infers readiness from absent
    evidence (the missing excerpt/understanding was the only signal, and
    absence invited「I can't read it」improvisation).
    ``plans_lines``: the docked decision package's plan roster (iter-2 ⑦)
    — plan_id + title + outputs digest per plan, rendered as the package
    block so a change ask can name its revise_plan target; None when the
    dock on the table is router-drafted (no Content Plans behind it).
    """
    brief_lines: list[str] | None = None
    if brief is not None:
        lines = []
        for name in ("topic", "audience", "tone"):
            slot = getattr(brief, name)
            if slot.value:
                lines.append(f"- {name}: {slot.value} ({slot.source})")
        if brief.constraints:
            # 顺形律 (ADR-064): constraints = 来源化条目数组；装配面只渲染
            # 条目文本（逐项来源对路由判断无增量，user-stated 约束已由
            # merge 的 precedence 保证存活）。
            lines.append(
                "- constraints: "
                + ", ".join(c.value for c in brief.constraints if c.value)
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
    pending_lines: list[str] | None = None
    if pending_question is not None:
        payload = pending_question.question or {}
        # The BARE question is the pending block's referent (ask 三分解剖 ②)
        # — content may carry the framing prose, which is noise for the
        # judge-THIS-message-against-it decision (legacy rows fall back to
        # content, where the bare question lives).
        lines = [f"- question: {payload.get('question') or pending_question.content or ''}"]
        options = payload.get("options") or []
        if options:
            lines.append(
                "- options: "
                + "; ".join(f"{o.get('id')}) {o.get('label')}" for o in options)
            )
        if payload.get("slot"):
            lines.append(f"- slot: {payload['slot']}")
        if payload.get("default_path"):
            lines.append(f"- if the user skips: {payload['default_path']}")
        pending_lines = lines
    speech_language = current_ui_language()
    return (
        {
            "message": message,
            "brief_lines": brief_lines,
            "persona_lines": persona_lines,
            "pending_lines": pending_lines,
            "filename": filename,
            "presented_plan": presented_plan,
            "plans_lines": plans_lines,
            "recent": recent,
            "file_language": file_language,
            "material_excerpt": material_excerpt,
            "understanding_lines": understanding_lines,
            "asset_lines": asset_lines,
            "material_pending_line": material_pending_line,
            # None outside a request (worker / scenario script) → the
            # directive is omitted and the LLM simply mirrors the
            # message's language.
            "speech_language": (
                _speech_language_line(speech_language) if speech_language else None
            ),
        },
        [],
    )


# The registries are static once imported (the tools door opens them), so
# the system prompts are built once at declaration time.
#
# max_iterations=12 (报价 = fold): the discovery chain (iter-2 ⑤, R2 免费
# 探索区连续工作) rides ONE turn — search_transcript → (get_segment reads)
# → propose_candidates → propose_selects → propose_plans = up to 6 calls on
# the designed flow. Live evidence (2026-09-23 S-explore-2 runs): the
# realistic chain is 8-10 — the model reads every range it means to judge
# as evidence before proposing (the door's verbatim law makes that
# thoroughness legitimate; 6 reads observed on a two-island transcript),
# and ProposePlansArgs is the router's most complex params shape (plans ×
# outputs nested lists), so its malformed-call recovery needs real budget:
# at 8 one rejection starved the plans call; at 10 a plans params
# rejection at iteration 9 left no recovery room. 12 = realistic 9-10 + 2
# recovery headroom; the bound stays what makes an unquoted chat turn
# safe (bounded, never open-ended).
intent_router = ToolLoopAgent(
    name="intent_router",
    prompt="intent_router.j2",
    system=intent_router_system(),
    temperature=0.2,
    assemble=_assemble_plan_turn,
    # iter-2 ⑤ (R6): the exploration verbs ride the production projection —
    # candidates/selects NON-terminal (the turn chains the discovery), only
    # propose_plans is terminal (the dock = the paid-boundary stop, R15).
    tools=[*PLAN_TOOLS, *PLAN_READ_TOOLS, *exploration_chat_tools()],
    max_iterations=12,
)


def _assemble_chat_turn(message: str, context: dict[str, Any]):
    """Chat-turn inputs: the user message plus the deterministic context
    digest (``agents/contexts.py``). Adjudication feedback never passes
    through here — it is the funnel's reserved ``repair_feedback`` kwarg."""
    context_text = context.get("text", "")
    lang = current_ui_language()
    if lang:
        # Same speech-language law as the plan path (2026-09-24, mirror the
        # message / UI floor) — the chat loop's ask/answer/prose follows it,
        # never the persona's or the material's language.
        line = _speech_language_line(lang)
        context_text = f"{context_text}\n\n{line}" if context_text else line
    return ({"context_text": context_text, "message": message}, [])


chat_intent_agent = ToolLoopAgent(
    name="chat_intent",
    prompt="chat_intent.j2",
    system=chat_intent_system(),
    temperature=0.2,
    assemble=_assemble_chat_turn,
    # iter-3 S2 (R6 parity): the exploration verbs ride the chat path too —
    # candidates/selects NON-terminal (one turn carries the post-run
    # discovery chain), propose_plans / revise_plan terminal (the dock = the
    # paid-boundary stop, R15).
    tools=[*CHAT_TOOLS, *CHAT_READ_TOOLS, *exploration_chat_tools()],
    # max_iterations 6→12 (iter-3 E8): the discovery chain rides ONE turn —
    # search → reads → candidates → selects → plans is 8-10 realistic calls
    # on the plan path's live evidence (2026-09-23, S-explore-2), and the
    # ProposePlansArgs params shape needs real rejection-recovery headroom;
    # 12 = realistic 9-10 + 2 recovery. The bound stays what makes an
    # unquoted chat turn safe (bounded, never open-ended).
    max_iterations=12,
)
