"""The chat turn's tool set (ADR-077 判词② — 判决 union 的机械翻译).

Declarations only: name + model-facing description + params model. The
executions live with the turn runners (``book_turn.py`` / ``propose_turn.py``)
because they need the service layer's machinery (the 提问机器, the run
birthplace, the wiring door) — this module deliberately imports NOTHING from
the chat service so the import DAG stays one-directional:

    schemas ← turn_tools ← intent ← service ← book_turn / propose_turn

Tool names are model-facing only — they never surface in user copy (简报 §3
禁令). Every tool here is terminal (终态工具一调即停); the non-terminal read
tools arrive with the perception family (T2b).

Description discipline (注册表条目扰动 = prompt 扰动): terse behavioral
contracts — WHEN to call, what the call does, what speech must precede it.
The parameter semantics live in the params models' Field descriptions; the
asking strategy / naming / disclosure rules stay in the system templates.
"""

from app.agents.tool_loop import ChatTool
from app.models.schemas import (
    ApplyEditOpsArgs,
    BookAnswerArgs,
    BookAskArgs,
    ChatAnswerArgs,
    ChatAskArgs,
    EditGraphArgs,
    PresentPlanArgs,
    ProposeTasksArgs,
)

# The book path (pre-first-run intent router) — InferredIntent's four actions:
# draft → present_plan, ask → ask_user, start → start_run, answer → answer.
BOOK_TOOLS = [
    ChatTool(
        name="present_plan",
        description=(
            "Present the task book for the user's work request: the proposed "
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
        params_model=BookAskArgs,
    ),
    ChatTool(
        name="start_run",
        description=(
            "Start the confirmed task book's run. Only when the user confirms "
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
        params_model=BookAnswerArgs,
    ),
]

# The chat path (post-run projects) — IntentResult's five proposal states:
# task_list → propose_tasks, edit_ops → apply_edit_ops, wiring → edit_graph,
# ask → ask_user, answer → answer.
CHAT_TOOLS = [
    ChatTool(
        name="propose_tasks",
        description=(
            "Propose new work as a task list for the user's confirmation — it "
            "never starts a run by itself. Speak the proposal's summary as "
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
            "edit_prompt / delete_node / run) and re-fill the affected "
            "subgraph. Speak the summary of the revision BEFORE calling this."
        ),
        params_model=EditGraphArgs,
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
            "readouts, explanations of existing outputs, small talk. Work "
            "requests go to the proposal tools; an ambiguous reading goes to "
            "ask_user — answer is never the lazy out."
        ),
        params_model=ChatAnswerArgs,
    ),
]
