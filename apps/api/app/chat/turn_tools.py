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

from app.agents.tool_loop import ChatTool
from app.chat.perception import perception_chat_tools
from app.models.schemas import (
    ApplyEditOpsArgs,
    ChatAnswerArgs,
    ChatAskArgs,
    EditGraphArgs,
    PlanAnswerArgs,
    PlanAskArgs,
    PresentPlanArgs,
    ProposeTasksArgs,
    ReviseOutputArgs,
)

# The plan path (pre-first-run intent router) — InferredIntent's four actions:
# draft → present_plan, ask → ask_user, start → start_run, answer → answer.
PLAN_TOOLS = [
    ChatTool(
        name="present_plan",
        description=(
            "Present the plan for the user's work request: the proposed "
            "plan docks for their confirmation — it never starts a run by "
            "itself. Speak the plan's short introduction as your message text "
            "BEFORE calling this."
        ),
        params_model=PresentPlanArgs,
    ),
    ChatTool(
        name="ask_user",
        description=(
            "Ask the ONE question whose answer most decides quality. The "
            "question docks with its options; the user's answer (or a safe "
            "skip) continues the conversation. Speak around the question "
            "first — claim the request, say why this one question decides it."
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
        params_model=None,
    ),
    ChatTool(
        name="answer",
        description=(
            "Reply with information only — capability questions, explanations "
            "of the project, small talk. No plan, no question, no run: your "
            "spoken message IS the reply."
        ),
        params_model=PlanAnswerArgs,
    ),
]

# The chat path (post-run projects) — IntentResult's five proposal states:
# task_list → propose_tasks, edit_ops → apply_edit_ops, wiring → edit_graph,
# ask → ask_user, answer → answer.
CHAT_TOOLS = [
    ChatTool(
        name="propose_tasks",
        description=(
            "Propose new work as a task list that docks for the user's "
            "confirmation — it never starts a run by itself; the run starts "
            "only after the user confirms. Speak the proposal's summary as "
            "your message text BEFORE calling this."
        ),
        params_model=ProposeTasksArgs,
    ),
    ChatTool(
        name="apply_edit_ops",
        description=(
            "Edit one existing output with clip-spec-level operations, "
            "targeted by its output id. Speak the summary of what you'll "
            "change BEFORE calling this."
        ),
        params_model=ApplyEditOpsArgs,
    ),
    ChatTool(
        name="edit_graph",
        description=(
            "Revise the project's persistent graph (add_node / connect / "
            "edit_prompt / delete_node / run). A revision inside the "
            "already-confirmed work re-fills the affected subgraph directly; "
            "one that adds new paid work docks for the user's confirmation "
            "instead — it does not run. Speak the summary of the revision "
            "BEFORE calling this."
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
            "makes) is revise_plan, never this. Speak what you'll change "
            "BEFORE calling this."
        ),
        params_model=ReviseOutputArgs,
    ),
    ChatTool(
        name="ask_user",
        description=(
            "Ask the ONE question whose answer most decides the next step. "
            "The question docks with its options. Speak around the question "
            "first — claim the request, say why this one question decides it."
        ),
        params_model=ChatAskArgs,
    ),
    ChatTool(
        name="answer",
        description=(
            "Reply with information only — capability questions, run-progress "
            "readouts (call get_run_status first), explanations of existing "
            "outputs, small talk. Work requests go to the proposal tools; an "
            "ambiguous reading goes to ask_user — answer is never the lazy out."
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
PLAN_READ_TOOLS = perception_chat_tools(
    "get_understanding",
    "get_asset",
    "get_craft_skeleton",
    "search_music",
    "list_caption_styles",
    # 证据 reads (迭代一): material reads by family — a discovery goal's
    # first turn is plan-path (fresh project), so the transcript evidence
    # substrate rides here too (2026-09-22).
    "search_transcript",
    "get_segment",
    "get_artifact",
)
CHAT_READ_TOOLS = perception_chat_tools(
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
)
