"""Project editor tool-loop declaration and user context assembly."""


from app.agents.tool_loop import ToolLoopAgent
from app.chat.prompts import intent_router_system
from app.chat.turn_tools import (
    PLAN_READ_TOOLS,
    PLAN_TOOLS,
)
from app.models.schemas import Brief
from app.models.tables import Message, Persona

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
    speaker_form_lines: list[str] | None = None,
    asset_lines: list[str] | None = None,
    material_pending_line: str | None = None,
    plans_lines: list[str] | None = None,
    surface: str | None = None,
    confirmation: tuple[str, str] | None = None,
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
    ``speaker_form_lines``: each form-bearing video's deterministic
    speaker-form fact (interview / single-speaker + turn count, off
    ``asset.meta`` — independent of the understanding row's readiness) —
    the framing direction's evidence seat: with it in context a vertical
    ask never silently defaults to a center crop; None when no map exists.
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
    ``surface``: the sender's surface (2026-09-25 canvas↔chat 联动, user
    ruling — the client judges it from the page width). "canvas" renders
    the surface line: the plan is laid out as an inspectable graph beside
    the conversation, so the review invitation may name that home (the
    system template's law governs the usage); anything else renders
    nothing and the surface-neutral default stands.
    ``confirmation``: the user's two confirmation prefs (ADR-117 D1 —
    (execution, credits) ∈ {auto, ask}) — rendered as one fact line the
    system template's mode-conditional close law reads; None renders
    nothing (the law's default branch then reads as auto, the
    server-enforced default).
    """
    brief_lines: list[str] | None = None
    if brief is not None:
        lines = []
        direction_fields = (
            ("production_direction",) if brief.production_direction.value else ("purpose", "narrative_mode")
        )
        for name in (
            "topic", "audience", "tone", *direction_fields,
            "target_seconds", "narration_language", "subtitle_languages", "aspect",
            "voice_requirements", "must_include", "avoid", "success_criteria",
        ):
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
            lines.append(f"- 已问字段：{', '.join(brief.asked)}")
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
            lines.append(f"- 核心价值观：{', '.join(values)}")
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
        for item in payload.get("items") or []:
            item_options = "; ".join(
                f"{option.get('id')}) {option.get('label')}"
                for option in item.get("options") or []
            )
            lines.append(
                f"- item {item.get('slot')}: {item.get('question')}"
                + (f" [{item_options}]" if item_options else "")
            )
        if payload.get("slot"):
            lines.append(f"- slot: {payload['slot']}")
        if payload.get("default_path"):
            lines.append(f"- 未答时的默认路径：{payload['default_path']}")
        pending_lines = lines
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
            "speaker_form_lines": speaker_form_lines,
            "asset_lines": asset_lines,
            "material_pending_line": material_pending_line,
            # The surface FACT (2026-09-25; 用户话术改口 2026-09-27 — v4.2
            # 封板⑪: the user's word is workspace/工作空间, the internal
            # enum stays "canvas"): a plain statement of where the plan
            # sits when the client reports the workspace. 2026-10-15 清扫
            # (画蛇添足裁决): this line is the workspace noun's ONLY seat —
            # the system templates carry no conditional naming law, so a
            # chat-surface turn's prompt contains zero workspace tokens and
            # the model cannot point at a home it never saw.
            "surface_line": (
                "当前对话与方案工作空间并列，展示的方案也以可检查的图显示在那里。可按用户的语言称“工作空间”或“the workspace”，不用方位词。"
                if surface == "canvas"
                else None
            ),
            # The confirmation-settings FACT (ADR-117 D1): the system
            # template carries the mode-conditional close law (one law,
            # one seat); this line is only the world fact it keys on.
            "confirmation_line": (
                f"确认设置：execution={confirmation[0]}, spending={confirmation[1]}。"
                if confirmation is not None
                else None
            ),
        },
        [],
    )


# The registries are static once imported (the tools door opens them), so
# the system prompts are built once at declaration time.
#
# max_iterations=20 (报价 = fold): discovery and direct video authoring ride
# ONE turn, with bounded read/preparation/correction headroom. The separate
# no-progress policy still stops repeated failed writes before this ceiling;
# the bound keeps an unquoted chat turn finite, never open-ended.
intent_router = ToolLoopAgent(
    name="intent_router",
    prompt="chat/user.j2",
    system=intent_router_system(),
    temperature=0.2,
    assemble=_assemble_plan_turn,
    # The current Composition authoring and production tools share one loop.
    tools=[*PLAN_TOOLS, *PLAN_READ_TOOLS],
    max_iterations=20,
    service_per_call=True,
)
