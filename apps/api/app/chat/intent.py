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
apply_edit_ops / edit_graph / ask_user / answer — the five proposal states,
mechanically). The LLM proposes; ``compile_graph`` / the operations registry
/ ``apply_wiring_ops`` adjudicate — their rejections ARE the loop's
feedback.
"""

from typing import Any

from app.agents.tool_loop import ToolLoopAgent
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


def _speech_language_line(lang: str) -> str:
    """The speech-language directive riding every LLM turn (2026-09-04 用户
    拍板: 言语语言一律 = 用户设置的系统语言). The value is the request's
    Accept-Language captured by the middleware (app.ui_locale — the same
    plumbing the run side already pins into run.context): this is the
    language of OUR messages to the user (questions, option labels, prose,
    summaries), never the CONTENT's language — task language params follow
    their own rules. Without this line "the user's language" was left for
    the LLM to infer, and a Chinese persona pantry dragged an English
    conversation's question AND option labels into Chinese."""
    return (
        f"Interface language: {lang} — ALL user-facing text you write (the "
        "question, every option label, prose, the summary, default_path) is "
        "in this language. Never infer your speech language from the user's "
        "message, the persona, or the material: translate pantry-sourced "
        "option values into the interface language. (Content-language task "
        "params follow their own rules.)"
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
    asset_lines: list[str] | None = None,
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
    ``asset_lines``: every attached file as one roster line (≥2 files only —
    ADR-078: the remix judgment must SEE the full roster to know a role
    question decides the plan; the single-file surface stays filename +
    excerpt).
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
            "recent": recent,
            "file_language": file_language,
            "material_excerpt": material_excerpt,
            "asset_lines": asset_lines,
            # None outside a request (worker / scenario script) → the
            # directive is simply omitted and the LLM falls back to the
            # message's language (pre-2026-09-04 behavior).
            "speech_language": (
                _speech_language_line(speech_language) if speech_language else None
            ),
        },
        [],
    )


# The registries are static once imported (the tools door opens them), so
# the system prompts are built once at declaration time.
#
# max_iterations=6 (报价 = fold, 简报「初值 ≤6」): the terminal call plus
# headroom for the perception family's reads (a designed flow tops at
# read → read → terminal) and one rejection iteration — the bound is what
# makes an unquoted chat turn safe.
intent_router = ToolLoopAgent(
    name="intent_router",
    prompt="intent_router.j2",
    system=intent_router_system(),
    temperature=0.2,
    assemble=_assemble_plan_turn,
    tools=[*PLAN_TOOLS, *PLAN_READ_TOOLS],
    max_iterations=6,
)


def _assemble_chat_turn(message: str, context: dict[str, Any]):
    """Chat-turn inputs: the user message plus the deterministic context
    digest (``agents/contexts.py``). Adjudication feedback never passes
    through here — it is the funnel's reserved ``repair_feedback`` kwarg."""
    context_text = context.get("text", "")
    lang = current_ui_language()
    if lang:
        # Same speech-language law as the plan path (2026-09-04) — the chat
        # loop's ask/answer/prose follows the UI language, never the
        # message's or the material's.
        context_text = (
            f"{context_text}\n\n{_speech_language_line(lang)}"
            if context_text
            else _speech_language_line(lang)
        )
    return ({"context_text": context_text, "message": message}, [])


chat_intent_agent = ToolLoopAgent(
    name="chat_intent",
    prompt="chat_intent.j2",
    system=chat_intent_system(),
    temperature=0.2,
    assemble=_assemble_chat_turn,
    tools=[*CHAT_TOOLS, *CHAT_READ_TOOLS],
    max_iterations=6,
)
