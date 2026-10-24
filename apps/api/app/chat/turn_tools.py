"""The chat turn's tool set (ADR-077 判词② — action union 的机械翻译).

Declarations only: name + model-facing description + params model. The
executions live with the turn runners (``plan_turn.py`` / ``propose_turn.py``)
because they need the service layer's machinery (the ask_user machinery,
the run birthplace, the wiring door) — this module deliberately imports NOTHING from
the chat service so the import DAG stays one-directional:

    schemas ← turn_tools ← intent ← service ← plan_turn / propose_turn

    (turn_tools ← perception: the read registry's executes import the
    pipeline layer DEFERRED, so this module's own import stays light)

Tool names are model-facing only — they never surface in user copy (简报 §3
禁令). The PLAN_TOOLS / CHAT_TOOLS lists are the TERMINAL set (终态工具一调
即停); the NON-terminal read tools are the perception family's projections
below (T2b — ``app/chat/perception/`` is their registry home).

Description discipline (注册表条目扰动 = prompt 扰动): terse behavioral
contracts — WHEN to call, what the call does, what speech must precede it.
The parameter semantics live in the params models' Field descriptions; the
asking strategy / naming / disclosure rules stay in the system templates.
"""

import re

from app.agents.tool_loop import ChatTool, ToolRejected, prune_wire_parameters
from app.chat.perception import perception_chat_tools
from app.models.schemas import (
    ChatAnswerArgs,
    ChatAskArgs,
    DesignStoryboardArgs,
    EditGraphArgs,
    EditOutputArgs,
    PlanAnswerArgs,
    PlanAskArgs,
    PresentPlanArgs,
    ProposeTasksArgs,
    ReviseOutputArgs,
    StartRunArgs,
)

# The plan path (pre-first-run intent router) — InferredIntent's four actions:
# draft → present_plan, ask → ask_user, start → start_run, answer → answer.
# design_storyboard (ADR-129 非终态): the film family's design beat is a
# NON-terminal call — the system drafts and validates the board inside
# execute, settles the design activity with its real elapsed, and hands the
# SAVED board's full fact sheet back to the model, whose ONE next message
# is the board's only presentation (2026-10-18 裁决 — 工具产生真实分镜,
# LLM 负责唯一表达; no program markdown row exists). The model then
# answers or — when the CURRENT message carries production intent —
# enters the proposal tools after the full presentation. A bare revision or
# review-only request closes through answer instead of docking production.
_DESIGN_STORYBOARD_DESCRIPTION = (
    "Design the film's storyboard — the website film's (a URL's captured "
    "pages) or the text film's (the copy riding `text`) — or revise the "
    "presented one: a change you can name the scene or element for "
    "(copy / timing / window / placement / music / voiceover) rides "
    "`edits` — the patch path below is the DEFAULT whenever a version "
    "exists; only a whole-film direction change rides "
    "`specific_instruction` (an open redraft — the copy is never named "
    "there: for a text film a redraft keeps the base version's text "
    "source unless YOU re-author `text` yourself, so a copy rewrite "
    "that keeps the user's other choices is an edit, never a redraft). "
    "The system drafts and validates the board "
    "inside the call and saves it with its version — no plan docks "
    "and nothing starts here. The call returns the saved board's FULL "
    "facts (execution timeline, per-scene content and narration), and a "
    "patch also returns its system-computed change summary; your ONE next "
    "message is the board's only presentation — introduce it, render the "
    "complete current scene table from those facts verbatim, then the "
    "cumulative settings and next step. When the CURRENT message carries "
    "production intent, follow with the film plan (present_plan / "
    "propose_tasks) carrying the same params after that presentation. A "
    "bare modification or review-only request closes through answer "
    "instead of docking production; an old run or older-version approval "
    "never supplies production intent for a revised version. Call it once the "
    "creative direction is agreed (a 'yes' to your direction "
    "question, an explicit storyboard request, or new feedback on the "
    "presented board) — a pasted text or URL whose creative direction "
    "is still open is NOT yet agreed: discuss that first. Within one turn the call drafts ONE first version plus bounded "
    "corrections of THAT version — a further change the user names in the "
    "same breath (「改完开工」) is a correction of the version this turn "
    "just produced, never a reason to stop; the cap refusal says so when "
    "the budget is spent. This tool carries NO production_intent flag — "
    "it designs only; the production-intent assertion rides the dock "
    "tools (present_plan / propose_tasks / edit_graph / propose_plans / "
    "revise_plan / revise_selects), never this call."
)
# 同回合纠正道 (7276ef13 修复批 ②): ONE turn drafts ONE first version plus
# bounded corrections OF IT (each correction revises the version THIS turn
# produced — the in-turn base, never a re-read of the committed world).
# The cap bounds the repair loop; past it the refusal below names the
# standing version and the honest-presentation duty (the refused change
# rides the turn's shortfall — the dock's confirmation law holds the
# spend, see lifecycle.confirmation_need's ``unmet_condition``).
MAX_DESIGN_CORRECTIONS_PER_TURN = 2


def _edit_op_signature(op) -> str:
    """One op's mechanical key: op name + target handles + the PRESENT
    payload fields (presence = ``model_fields_set``; dict-typed fields
    expand one key level). The target VALUE joins only where the value IS
    the target identity (a reorder's arrangement, set_music's mood,
    set_voiceover's on/off); field values otherwise never enter the key —
    a repair retry that only fixes the offending value signs identically
    to its failure, while a different FIELD on the same scene/element
    signs differently (the 同一幕换背景 ≠ 修复动画时序 hole)."""
    head = ":".join(
        [
            getattr(op, "op", "?"),
            getattr(op, "scene_id", None) or "",
            getattr(op, "element_id", None) or "",
        ]
    )
    fields: list[str] = []
    present = (getattr(op, "model_fields_set", None) or set()) - {
        "op",
        "scene_id",
        "element_id",
    }
    for name in present:
        value = getattr(op, name, None)
        if isinstance(value, dict):
            fields.extend(f"{name}.{key}" for key in sorted(value))
        elif name == "order":  # reorder: the arrangement IS the handle
            fields.append("order=" + ">".join(str(v) for v in value or []))
        elif name in ("mood", "enabled"):  # the value IS the target
            fields.append(f"{name}={value}")
        else:
            fields.append(name)
    return f"{head}[{','.join(sorted(fields))}]"


def design_call_signature(params) -> str:
    """一次 design 调用的机械签名（7276ef13 定点收尾① — shortfall 台账条
    目的 key 半边）: patch = 每 op 的机械键（`_edit_op_signature`）按**执
    行顺序**串；compose 一族同键。签名只做机械配对索引，**永不声称证明了
    用户目标的完成**；不同 op / 目标 / 字段的成功永不同键，永不清掉它没
    碰过的失败。op 顺序参与签名（2026-10-23 拍板）：同一幕先改深底再改
    浅底与反过来结果不同——执行序即语义，不当等价归并。"""
    edits = getattr(params, "edits", None)
    if edits:
        return "patch:" + ",".join(_edit_op_signature(op) for op in edits)
    return "compose"


def design_call_record(params) -> dict:
    """shortfall 台账条目（复审再收紧——「同字段不同值」洞）: ``key`` =
    机械签名（`design_call_signature`）；``target`` = 本次请求**在场字段
    的规范化目标值**（canonical JSON，对象内部键排序——值即身份的三个
    字段同样在内）。**op 的执行顺序保留**（2026-10-23 拍板：同一幕先改
    深底再改浅底，与反过来的结果不同——排序后当等价是错账）；规范化的
    只是每个 op 对象内部的字段顺序。销账律：仅当成功落版的条目 key **且
    target 完全相等**才消——模型改用其他目标值、删掉了原请求的字段
    （字段进 key，天然不同键）、或无法证明等价时，失败记录全部保留，确
    认要求随之保留。「已经呈现」永远不等于用户接受；用户看过当前方案后
    的明示接受（含事后明示 Start）是确认机制既有的出路，不在此建设语义
    判定。"""
    import json

    edits = getattr(params, "edits", None)
    if not edits:
        return {"key": "compose", "target": ""}
    per_op = []
    for op in edits:
        present = (getattr(op, "model_fields_set", None) or set()) - {
            "op",
            "scene_id",
            "element_id",
        }
        per_op.append(
            {name: getattr(op, name, None) for name in sorted(present)}
        )
    return {
        "key": design_call_signature(params),
        # default=str: nested models (FilmFocus / FilmViewRef) ride their
        # pydantic repr — deterministic per equal value, equivalence-safe.
        "target": json.dumps(
            per_op,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ),
    }


def design_correction_cap_refusal(version: int) -> str:
    """The correction-cap refusal (both design seats' one text): the
    standing version is named and the model's presentation duty is stated
    — the change did NOT land, so the standing version is never presented
    as if it had; the user's next message re-enters the correction."""
    return (
        f"This turn's storyboard corrections are exhausted — version "
        f"{version} stands as this turn's design, and the last change you "
        f"attempted did NOT land on it. Present version {version} honestly: "
        f"name the change that did not land (never present this version as "
        f"if it carried the fix), and let the user answer — their next "
        f"message re-enters the correction against version {version}."
    )


def design_begin_refusal_feedback(refusal: str) -> str:
    """The begin refusal's ONE observation text (all four begin seats):
    world facts + the closed-entry law. ``in_flight`` is the ONLY refusal
    that may narrate a live design (a committed marker names it); a
    row-lock conflict's holder is UNKNOWN — never narrated as another
    design or a production. The entry is closed for the rest of the turn
    (the latch): the model's one remaining move is the honest close, and
    a repeated design_storyboard call ends the turn deterministically
    (TerminalRefusal) instead of burning the loop budget on a hold that
    is not this turn's to wait out."""
    fact = (
        "another storyboard design is in flight on this project (a live "
        "committed design marker names it)"
        if refusal == "in_flight"
        else "starting the design hit a state conflict on the project row "
        "— the holder is unknown (a concurrent request's transaction), so "
        "never narrate this as another design or a production"
    )
    return (
        f"The design did NOT start: {fact}. The design entry is CLOSED for "
        "the rest of this turn — a repeated design_storyboard call cannot "
        "recover it here and ends the turn on the spot. Your one remaining "
        "move is to speak the honest close: no storyboard was designed this "
        "time; the user's next message re-enters the design."
    )


def film_revision_proposal_guard(
    *,
    designed_version: int | None,
    tasks: list,
    production_intent: bool | None,
) -> str | None:
    """Keep a film design/revision presentation ahead of a production dock.

    This is deliberately a structural gate, not a second intent classifier:
    the existing dock argument is the sole semantic assertion. A successful
    film design in this turn plus a launch_film proposal without that
    assertion must close through ``answer``; an explicit current-turn
    delegation (``True``) keeps the existing proposal, quote and Start path.
    """
    if designed_version is None or production_intent is True:
        return None
    if not any(
        (task.get("tool") if isinstance(task, dict) else getattr(task, "tool", None))
        == "launch_film"
        for task in tasks
    ):
        return None
    return (
        f"Film storyboard version {designed_version} is saved, but the current "
        "message does not assert production intent. No production dock or run "
        "has been created. Do not say the film is being remade and do not dock "
        "launch_film in this beat. Call answer using the FULL current "
        "saved-board facts already returned and, for a revision, the system "
        "change summary: say the storyboard is updated and the film has not been "
        "regenerated, show the complete Markdown scene table and cumulative "
        "settings/open items, then ask whether to remake this version. If "
        "the user explicitly asked to review only, stop after that full "
        "presentation without a production question. A direct current-turn "
        "‘edit and make’ delegation belongs in production_intent=true on the "
        "proposal call; never inherit it from an old run or an older "
        "version's approval."
    )


def film_rejection_stop(
    current: ToolRejected, previous: tuple[ToolRejected, ...]
) -> bool:
    """Bound failed Film design attempts without touching other tool loops.

    An exact repeated signature stops on the second failure. Different
    validation/execution errors may still be genuine repairs, so they retain
    two more attempts; the third design rejection in one turn ends the loop
    regardless of signature. Accepted reads and successful designs do not
    erase the failure budget: this is a per-turn failed-design cap, not the
    deferred unified nested-LLM budget.
    """
    if current.tool_name != "design_storyboard":
        return False
    history = (*previous, current)
    if previous:
        last = previous[-1]
        if (
            last.tool_name == current.tool_name
            and last.kind == current.kind
            and last.detail == current.detail
        ):
            return True
    return sum(
        event.tool_name == "design_storyboard" for event in history
    ) >= 3


def film_wiring_guard(
    *,
    ops: list[dict] | tuple = (),
    pre_nodes: list | tuple = (),
    tasks: list | tuple = (),
) -> str | None:
    """Keep chat-born film work on the versioned storyboard/Start path.

    ``edit_prompt`` on an existing launch_film node and any resolved run
    containing launch_film are rejected before their graph savepoint can
    commit. Other wiring revisions keep their existing continuation/dock
    behavior. The generic chat run dispatcher calls the same guard as a
    backstop, so a future caller cannot accidentally reintroduce the bare
    film-run bypass.
    """
    film_nodes = {
        str(node.id)
        for node in pre_nodes
        if getattr(node, "tool", None) == "launch_film"
    }
    targets_film_prompt = any(
        isinstance(op, dict)
        and op.get("op") == "edit_prompt"
        and str(op.get("node")) in film_nodes
        for op in ops
    )
    runs_film = any(
        (task.get("tool") if isinstance(task, dict) else getattr(task, "tool", None))
        == "launch_film"
        for task in tasks
    )
    if not targets_film_prompt and not runs_film:
        return None
    return (
        "launch_film is bound to a presented storyboard version, not to "
        "edit_graph prompt revision or the generic wiring run. No graph "
        "change or run was committed. To make the unchanged pending version, "
        "use its normal versioned Start path; to change the film, call "
        "design_storyboard and then present_plan/propose_tasks with the "
        "resulting version. Never regenerate a film from a launch slot."
    )


# The patch path's paragraph — a deployment-gated capability slice
# (settings.film_edits_enabled, internal-test while the edit journey closes
# up): the wire view below strips it (and the edits/base_ref schema fields)
# whenever the gate is off, so the model is never told about a capability
# the execution branch would refuse. Aspect honesty law: an aspect CHANGE
# is not a redesign request — while variants are unimplemented the model
# answers 'not supported yet', never routes the user into a full redesign
# as a workaround.
_DESIGN_STORYBOARD_EDITS_PARAGRAPH = (
    "\nTARGETED EDITS (the patch path): a change to the CURRENT version "
    "rides edits — update_scene (view / seconds / focuses / narration / "
    "the scene type's copy slots; a words plane also takes motion "
    "static|push|pull, enter lines|words, dark true|false — the "
    "background polarity: deep/light are the only two stops, never an "
    "arbitrary color — and precise timing in scene-relative seconds: "
    "enter_start / enter_interval / enter_duration / enter_hold_until "
    "for the selected word-token or whole-line entrance (an absent hold "
    "means scene end; a set hold is the leave moment). For words copy_slots "
    "is exactly {\"lines\":[\"first line\",\"second line\"]} — a string "
    "array with no 'words' wrapper. Strict sequential pure sliding uses "
    "enter='lines', enter_style='slide', and enter_interval>=enter_duration; "
    "when switching between word and line units, explicitly set or clear "
    "every existing timing key in the same op), "
    "plus motion_start / motion_end for a push/pull window, "
    "exit_duration (the words fade OUT over the window's final stretch — "
    "the background never fades), motion_scale (the push/pull amplitude; "
    "subtle ≈ 1.02–1.04), and the style knobs align left|center, "
    "size small|medium|large, accent_style chip|color (color = *emphasis* "
    "spans render in the theme accent instead of the inverted tile), "
    "enter_style rise|fade|slide (the entrance EFFECT — fade = opacity "
    "only; slide = translate only, no opacity ramp or blur; orthogonal to "
    "enter's lines/words organization). "
    "Explicit "
    "null restores a timing/style default; explicit 0 is a real value. The "
    "version's read shows each set value with its quantized frame AND "
    "the frame's realized seconds, plus the last token/line's computed "
    "start / fully-in landing; an arrangement beyond the scene window "
    "rejects with the "
    "concrete conflict — never shorten it silently), "
    "update_element (ONE element inside a composite scene, addressed by "
    "scene_id + element_id from the version's read: a text element's "
    "lines / tone (light|dark|accent — accent = the whole block in the "
    "theme accent) / enter-motion timing / the same exit_duration, "
    "motion_scale, align, size, accent_style and enter_style knobs, any element's at / until / rect "
    "/ z, a media element's fit, a video element's source_start / "
    "source_end / duration / keep_audio — a source window keeps inside "
    "the material's real length, which the read shows; fields that do "
    "not apply to the element's kind reject with the reason, an absent "
    "field keeps its value, explicit null restores its default; changing "
    "WHICH asset an element cites is not an edit — a different video is "
    "a different composition), "
    "reorder_scenes (the full id "
    "permutation), remove_scene, set_music (mood + retime "
    "keep_cut|recut; mood 'off' switches the bed off for good), "
    "set_voiceover (false = silent cut; true = re-open synthesis of the "
    "board's own narration lines — a board with none rejects: author the "
    "lines with update_scene first) — always with the "
    "base_ref echoed verbatim from the version's presentation or a "
    "get_output_spec read. The system applies the ops atomically and "
    "answers with the computed change summary PLUS the complete current "
    "saved-board facts (the next message presents both: the delta, the "
    "full Markdown scene table, and the cumulative settings/open items). "
    "The revision alone never starts a run or regenerates the film. "
    "Nothing else exists: no scene insertion (an "
    "added beat is open feedback) — open "
    "feedback like that rides specific_instruction WITHOUT edits. An "
    "aspect change is NOT available — answer honestly that it is not "
    "supported yet; never offer a redesign as the workaround."
)


def _design_storyboard_wire_view(description: str, parameters: dict) -> tuple[str, dict]:
    """The edit capability's declaration gate (one seat, spec-time): gate
    ON = the full description + schema; gate OFF = the base description and
    a schema with ``edits``/``base_ref`` pruned — unreferenced ``$defs``
    (the op models) garbage-collected so no op vocabulary leaks onto the
    wire. The execution branch refuses the same slice independently. When
    the gate is on, the copy-slot description carries a live projection of
    the edit whitelist and storyboard validator's own numeric bounds."""
    from app.config import settings  # deferred: config leaf, import-light module

    if settings.film_edits_enabled:
        from app.tools.film.edits import film_edit_copy_constraints  # deferred: tool seam

        copy_slots = parameters["$defs"]["FilmEditUpdateScene"]["properties"][
            "copy_slots"
        ]
        copy_slots["description"] = (
            copy_slots.get("description", "") + "\n\n" + film_edit_copy_constraints()
        ).strip()
        return description, parameters
    return _DESIGN_STORYBOARD_DESCRIPTION, prune_wire_parameters(
        parameters, {"edits", "base_ref"}
    )


_DESIGN_STORYBOARD_TOOL = ChatTool(
    name="design_storyboard",
    terminal=False,
    description=_DESIGN_STORYBOARD_DESCRIPTION + _DESIGN_STORYBOARD_EDITS_PARAGRAPH,
    params_model=DesignStoryboardArgs,
    wire_view=_design_storyboard_wire_view,
)

PLAN_TOOLS = [
    ChatTool(
        name="present_plan",
        description=(
            "Present the plan for the user's work request: the proposed "
            "plan docks — the context's confirmation settings key whether "
            "the run starts on presentation or waits for the user's "
            "confirmation (the system starts it; this call never does)."
        ),
        params_model=PresentPlanArgs,
    ),
    ChatTool(
        name="ask_user",
        description=(
            "Ask the ONE question whose answer most decides quality. The "
            "question docks with its options; the user's answer (or a safe "
            "skip) continues the conversation. Also the home of open "
            "exploration and browsing questions — concrete directions worth "
            "choosing between dock as its options with your lean marked, "
            "the safe skip keeping it an offer, never a demand."
        ),
        params_model=PlanAskArgs,
    ),
    ChatTool(
        name="start_run",
        description=(
            "Start the confirmed plan's run. Only when the user confirms "
            "a docked plan (a 'looks good, go ahead' in the confirm phase — "
            "a revision is present_plan, not this)."
        ),
        params_model=StartRunArgs,
    ),
    ChatTool(
        name="answer",
        description=(
            "Reply with information only — capability questions, explanations "
            "of the project, small talk. No plan or run: your "
            "spoken message IS the reply. Work the user has explicitly "
            "named docks as a plan once its creative direction is agreed. The "
            "website-film direction stage may end here with its grounded "
            "summary and next-step question. Always speak the "
            "reply as your message text ALONGSIDE the call — a bare answer "
            "call that says nothing is rejected."
        ),
        params_model=PlanAnswerArgs,
    ),
]

# The chat path (post-run projects) — the terminal proposal states:
# task_list → propose_tasks, wiring → edit_graph, craft → revise_output,
# precise edit → edit_output, ask → ask_user, answer → answer.
# (Final Hardening B1, 2026-09-24: the raw-ops verb ``apply_edit_ops`` is
# RETIRED — the Agent's only edit entry is edit_output's controlled enum;
# raw clip-spec ops never enter the LLM vocabulary. The REST operations
# door stays for the editor surface.)
CHAT_TOOLS = [
    ChatTool(
        name="propose_tasks",
        description=(
            "Propose new work as a task list that docks — the context's "
            "confirmation settings key whether the run starts on "
            "presentation or waits for the user's confirmation (the system "
            "starts it; this call never does)."
        ),
        params_model=ProposeTasksArgs,
    ),
    ChatTool(
        name="edit_graph",
        description=(
            "Revise the project's persistent graph (add_node / connect / "
            "edit_prompt / delete_node / run). A revision inside "
            "the already-confirmed work re-fills the affected subgraph "
            "directly; one that adds new paid work docks first — the "
            "context's confirmation settings key whether it then runs on "
            "presentation or waits for the user's confirmation."
        ),
        params_model=EditGraphArgs,
    ),
    # iter-3 S3 (N-58, ADR-089 §6): the craft-level revision verb — product
    # semantics (a plan / an output + the user's words), NEVER wiring ops.
    ChatTool(
        name="revise_output",
        description=(
            "Revise an already-produced work's CRAFT (the how: 'plan 2 的字幕"
            "太长了', 'make the hook sharper') — targeted by the user's "
            "pointing (plan_ref relayed verbatim, or the @output pin). The "
            "system routes the target, rewrites the affected programs, and "
            "reruns inside the confirmed scope; new paid work re-docks as a "
            "mini decision package. A plan's DELIVERABLES change (what it "
            "makes) is revise_plan, never this."
        ),
        params_model=ReviseOutputArgs,
    ),
    # 精确编辑迭代 S3 (N-59, ADR-090): the PRECISE edit verb — mechanically
    # executable changes only, the controlled enum; raw ops never surface.
    ChatTool(
        name="edit_output",
        description=(
            "Edit an already-produced clip PRECISELY — a mechanically "
            "executable change: 'delete this line' (remove_range, params.quote "
            "= the words verbatim) / 'N seconds shorter' (set_trim, "
            "params.seconds) / 'captions to karaoke' (set_caption_style, "
            "params.style = a preset from list_caption_styles) / 'retitle to X' "
            "(set_title, params.title). Target by the @output pin (output_id) "
            "or the plan ordinal (plan_ref verbatim). The system resolves the "
            "quote to seconds, applies, and re-renders. An open-ended craft "
            "ask ('make it tighter') goes to revise_output; a change you "
            "cannot name mechanically goes to ask_user — never guess."
        ),
        params_model=EditOutputArgs,
    ),
    ChatTool(
        name="ask_user",
        description=(
            "Ask the ONE question whose answer most decides the next step. "
            "The question docks with its options. Also the home of open "
            "exploration and browsing questions — concrete directions worth "
            "choosing between dock as its options with your lean marked, "
            "the safe skip keeping it an offer, never a demand."
        ),
        params_model=ChatAskArgs,
    ),
    ChatTool(
        name="answer",
        description=(
            "Reply with information only — capability questions, run-progress "
            "readouts (call get_run_status first), explanations of existing "
            "outputs, small talk. Work requests go to the proposal tools; an "
            "ambiguous reading goes to ask_user — answer is never the lazy out. "
            "The website-film creative-direction stage may end here before "
            "a proposal exists; other work docks as a proposal or the "
            "fitting revision verb. Always speak "
            "the reply as your message text ALONGSIDE the call — a bare "
            "answer call that says nothing is rejected."
        ),
        params_model=ChatAnswerArgs,
    ),
]

# The perception family (ADR-077 判词②, T2b — read-only, NON-terminal): the
# agent's eyes. Plan path: pre-first-run there are no outputs and no runs
# yet, so only the material/catalog reads ride (registering the dead seats
# would invite hallucinated calls) — plus get_craft_skeleton: a remix's
# FIRST turn is plan-path (two uploads, 「照这个案例做」), and a role-pinned
# exemplar's skeleton may already be warm. Chat path: the full family.
# get_artifact rides BOTH paths (iter-3 S6): the exploration artifacts the
# discovery chain births are plan-path rows too, and revise_selects (its
# edit-prep reader) lives on both paths.
# design_storyboard (ADR-129 非终态) rides BOTH paths' NON-terminal sets:
# the design beat observes and iterates like a read — the loop's checkpoint
# seat carries its framing speech, the observation carries the design facts,
# the model answers or enters the proposal tools afterwards.
def _film_composite_read_tools() -> list[ChatTool]:
    """The media-composition journey's read seats ride the film edit
    capability's deployment gate (settings.film_edits_enabled — the same
    gate the edit path and the composite birth ride): gate OFF, the
    discovery read never reaches the production wire (the registry entry
    stays; the loop's tool sets are built ONCE at import, so the gate reads
    at process start — declaration and enforcement gate together)."""
    from app.config import settings  # deferred: config leaf

    if not settings.film_edits_enabled:
        return []
    return list(perception_chat_tools("list_project_media"))


PLAN_READ_TOOLS = [
    *perception_chat_tools(
        "get_understanding",
        "get_asset",
        "get_craft_skeleton",
        "search_music",
        # get_output_spec (2026-10-23 T3 取证): the edit path itself lives on
        # this path (plan_turn's design_storyboard patch branch), and a patch
        # is formable ONLY off this read's base_ref + scene/element ids —
        # without it the law's named re-read seat is a dead tool here
        # (unknown_tool) and every element-named change collapses into an
        # open redraft. Symmetric with the chat path's always-on read; the
        # observation's edit facts adapt to the capability gate themselves.
        "get_output_spec",
        "list_caption_styles",
        # 证据 reads (迭代一): material reads by family — a discovery goal's
        # first turn is plan-path (fresh project), so the transcript evidence
        # substrate rides here too (2026-09-22).
        "search_transcript",
        "get_segment",
        "get_artifact",
        # get_graph (ADR-111 §7): the plan-ready reveal shows the canvas BEFORE
        # any run — the plan path's model must be able to read what it shows.
        "get_graph",
        # The web pair: a link can arrive on the very first turn (「这个网站你
        # 看看？」/「帮我做支网站介绍短片」) — reading it is altitude-free.
        "get_web_page",
        "search_web",
    ),
    *_film_composite_read_tools(),
    _DESIGN_STORYBOARD_TOOL,
]
CHAT_READ_TOOLS = [
    *perception_chat_tools(
        "get_output_spec",
        "get_node",
        "get_understanding",
        "list_caption_styles",
        "search_music",
        "get_run_status",
        "list_runs",
        "get_pending_plan",
        "get_asset",
        "get_craft_skeleton",
        "search_transcript",
        "get_segment",
        "get_artifact",
        "get_graph",
        "get_web_page",
        "search_web",
    ),
    *_film_composite_read_tools(),
    _DESIGN_STORYBOARD_TOOL,
]


# ── 工具名回响 sanitizer (2026-09-30 用户拍板 — 彻底删掉) ──────────────────
# The model sometimes echoes the tool it is calling as a BARE bracketed line
# of prose ('[start_run]'): the name saturates its prompt (it must — it is
# the tool's name), and the bracket shape is the function-call markup of its
# pretraining. The real call rides the native tool channel; the echo is pure
# noise the spoken sentence already covers — and the user should never see
# machine vocabulary. Strip lines that are EXACTLY one registered tool's
# name in brackets; a name mentioned mid-sentence is prose and stays.
_TOOL_ECHO_NAMES = frozenset(
    tool.name for tool in [*PLAN_TOOLS, *CHAT_TOOLS, *CHAT_READ_TOOLS]
) | {"wrap_up"}  # the trigger turn's terminal (its module imports ours)
_TOOL_ECHO_LINE = re.compile(r"^\[[a-z_]+\]\s*$")
# A tail fragment that could still complete INTO a bare echo line — the
# stream filter holds exactly these undecided (fails fast on any non
# [a-z_] character, so legit prose like a markdown link releases after
# a character or two).
_TOOL_ECHO_PREFIX = re.compile(r"^\[[a-z_]*(\]\s*)?$")


def strip_tool_echoes(content: str) -> str:
    """Remove bare [tool_name] echo lines from assistant prose (pure)."""
    if "[" not in content:
        return content
    kept = []
    for line in content.split("\n"):
        stripped = line.strip()
        if _TOOL_ECHO_LINE.match(stripped) and stripped.strip("[]").strip() in _TOOL_ECHO_NAMES:
            continue
        kept.append(line)
    # The echo rides as its own paragraph — collapse the blank run its
    # removal leaves so the seam never shows.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip("\n")


def _is_tool_echo_line(line: str) -> bool:
    stripped = line.strip()
    return bool(_TOOL_ECHO_LINE.match(stripped)) and stripped.strip("[]").strip() in _TOOL_ECHO_NAMES


def make_tool_echo_delta_filter(emit):
    """Stream-side gate of the same law (2026-09-30 同批拍板): iteration-0
    deltas are RAW model fragments, so a bare '[tool]' echo line would flash
    live long before the persistence-layer strip runs. Wrap the on_delta
    hook: hold any '['-initial tail line undecided until its newline proves
    it (bare registered echo → dropped with its newline; anything else →
    released byte-exact). A registered echo held at stream end is never
    flushed — the settled (sanitized) envelope replaces the bubble, so the
    echo simply never exists for the user.
    """
    held = ""

    async def on_delta(fragment: str) -> None:
        nonlocal held
        text = held + fragment
        held = ""
        if not text:
            return
        *body, tail = text.split("\n")
        # The decided (newline-terminated) segment gets the same transform
        # as the persistence strip: echo text out, 3+ newline runs collapse
        # to the paragraph seam — so the live bubble and the settled row
        # read identically.
        out = ""
        if body:
            kept = [line for line in body if not _is_tool_echo_line(line)]
            segment = "".join(line + "\n" for line in kept)
            out = re.sub(r"\n{3,}", "\n\n", segment)
        if tail:
            if not _TOOL_ECHO_PREFIX.match(tail):
                out += tail  # can never complete into an echo — prose
            elif _TOOL_ECHO_LINE.match(tail.strip()) and not _is_tool_echo_line(tail):
                out += tail  # a complete bracket line, but unregistered — prose
            else:
                held = tail  # undecided: still forming toward a registered echo
        if out:
            await emit(out)

    return on_delta
