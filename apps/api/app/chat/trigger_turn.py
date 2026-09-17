"""Trigger turns — the chat edge agent's proactive speech (ADR-077 判词③, T3).

A trigger turn is a STANDARD bounded tool-loop turn whose "user message" is
a system event instead of human words. The trigger whitelist is the whole
proactivity boundary (简报 §4 挂账③ — outside it the agent NEVER speaks
first):

- ``understanding_warmed`` — the upload-time material understanding
  materialized (``node_runners.warm_understanding``; 旅程一② 「我看了——
  你在讲 X」);
- ``run_completed`` — a run reached its terminal state
  (``orchestrator.maybe_finalize_run``; 旅程一⑦ the closing reviewer).
  The fire gate mirrors ADR-074②'s closing-line truth: a successful run OR
  a partial failure with landed products (done + output_refs); a run where
  nothing landed fires nothing — the receipt IS its failure surface.

The loop itself: the perception family's reads are the agent's eyes (look
BEFORE speaking — read-before-speak is the reviewer's honesty base), and
ONE terminal tool (``wrap_up``) closes the turn with the spoken review plus
0-3 next-step option labels that dock as a REAL numbered options question
on the review row (ADR-081 选项语法统一律 — the pill form is retired; the
picked label rides the answer endpoint's generic continuation into the
next chat turn as the user's own say).

Worker-side seats: both fire points are pipeline code (no request context),
so the turn opens its OWN session (the ``dock_interrupt_question``
precedent), inherits the speech language from the conversation's stamped
interface-language owner (ADR-080 单一叙事者律 — never the material's,
never a per-writer derivation), and persists the review as a PLAIN
assistant row — ``intent`` carries the trigger dump
``{type: "trigger_review", trigger, ref, suggestions}`` (the row replays
verbatim on refresh / another device; 刷新/跨设备恢复 = 消息行持久化).
Fire-and-forget: a trigger failure logs and never raises into the pipeline
— the world event already landed truthfully (the understanding row, the
run verdict); the speech layer degrades to silence, never to a
fabrication.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contexts import _build_context
from app.agents.tool_loop import ChatTool, ToolLoopAgent
from app.chat.intent import _speech_language_line
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.prompts import trigger_system
from app.chat.service import (
    _create_message,
    _dock_question,
    _get_or_create_project_conversation,
    _prefers_zh,
    finalize_bailed_runs,
    is_pending_plan,
    latest_pending_question,
)
from app.chat.turn_tools import CHAT_READ_TOOLS
from app.models.schemas import Option, QuestionPayload, WrapUpArgs
from app.models.tables import Conversation, Message, Project, WorkflowRun

logger = structlog.get_logger(__name__)

# The proactivity boundary (白名单): a turn fires ONLY from these seats.
TRIGGER_UNDERSTANDING = "understanding_warmed"
TRIGGER_RUN_COMPLETED = "run_completed"
TRIGGER_CRAFT_DECOMPILED = "craft_decompiled"  # 案例拆解完成 (ADR-078, 旅程二④)
TRIGGER_WHITELIST = frozenset(
    {TRIGGER_UNDERSTANDING, TRIGGER_RUN_COMPLETED, TRIGGER_CRAFT_DECOMPILED}
)

# The assistant row's intent-dump discriminator — the dedup guard and the
# frontend's arrival channel read it. Since ADR-081 the row MAY also dock
# its options question (the suggestion labels' seat); the dump stays the
# forensics/identity layer (type + trigger + ref + labels).
TRIGGER_DUMP_TYPE = "trigger_review"

# Turn admission (交互完整性批 B, 2026-09-17; ADR-080 单一叙事者律升格 —
# conversation-level turn ownership): a proactive turn NEVER overtakes an
# in-flight user turn, and NEVER talks over a docked plan. The 2026-09-16
# incident: the understanding warm fired 36s into the user's first plan
# turn, the trigger's own session read an empty conversation (the user row
# wasn't durable yet), and the review spoke blind — three off-request
# suggestion pills competing with the plan the agent was still building.
# Two static predicates (no arbiter layer): in-flight → defer in bounded
# cycles (the user row is durable from the turn's first beat — 交互完整性
# 批 A — so the gate is a plain DB read); pending task_book → silence (the
# plan echo already narrates); exhaustion → the silence doctrine (a blind
# review is worse than none — the world event already landed truthfully on
# its own).
_TRIGGER_DEFER_SECONDS = 20
_TRIGGER_DEFER_MAX_ATTEMPTS = 15  # 15 × 20s = a 5-minute politeness bound
# A stranded in_flight row (a crashed turn whose 'failed' stamp never
# landed) ages out past this bound — the gate never deadlocks on a corpse.
_TURN_IN_FLIGHT_STALE_SECONDS = 600


def _trigger_admission(in_flight: bool, attempt: int, max_attempts: int) -> str:
    """The gate's pure decision: "proceed" | "defer" | "drop" (drop = the
    politeness bound ran out — silence, never blind speech)."""
    if not in_flight:
        return "proceed"
    return "drop" if attempt >= max_attempts else "defer"


async def _project_turn_in_flight(project_id: UUID) -> bool:
    """The gate's read: a durable user row still owned by a live turn
    (turn_state='in_flight', younger than the stale bound) anywhere in the
    project's conversation. Short-lived session — this runs between defer
    cycles, outside the turn's own session."""
    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    cutoff = datetime.now(UTC) - timedelta(seconds=_TURN_IN_FLIGHT_STALE_SECONDS)
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(Message.id)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.project_id == project_id,
                    Message.role == "user",
                    Message.turn_state == "in_flight",
                    Message.created_at >= cutoff,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return row is not None


WRAP_UP = ChatTool(
    name="wrap_up",
    description=(
        "Close the proactive turn: your spoken message is the review; carry "
        "0-3 next-step option labels grounded in what you actually read "
        "(they dock as a numbered options question — ADR-081). Speak "
        "first, then call this."
    ),
    params_model=WrapUpArgs,
)


def _trigger_question_line(language: str) -> str:
    """The suggestion dock's bare question (ask 三分解剖 ② — code-assembled,
    never the LLM's voice, same doctrine as the reminder tail): the review
    prose already framed why; the dock title only asks which next step."""
    return "接下来做什么？" if language.startswith("zh") else "What's next?"


def _suggestions_payload(labels: list[str], language: str) -> QuestionPayload:
    """The suggestion dock's question payload (ADR-081 选项语法统一律):
    the trigger's send-labels become a REAL options question — numbered
    options (id = 1-based position, the autoResume/digital-badge grammar),
    freeform pencil on, blocking per the 形态律. No slot, no run marker:
    the answer endpoint's generic continuation carries the picked label
    into the next chat turn as the user's own say."""
    return QuestionPayload(
        kind="question",
        question=_trigger_question_line(language),
        options=[
            Option(id=str(index + 1), label=label)
            for index, label in enumerate(labels)
        ],
        allow_freeform=True,
    )


def _trigger_language(
    run: WorkflowRun | None,
    history: list[Message],
    conversation: Conversation | None = None,
) -> str:
    """The speech language for a worker-born turn (ADR-080 界面语言唯一
    owner): the conversation's stamped ``ui_language`` owner FIRST (the
    request chain's locale, re-stamped every user turn — the ONE fact all
    assistant writers inherit), then the run's pinned ui_language, then the
    latest user message's script (owner 缺席时的兜底推导), then English —
    the project's content language default is NOT a speech signal, so it
    never votes here."""
    owner = (conversation.ui_language if conversation is not None else None) or ""
    if owner:
        return owner.lower()
    ui = ((run.context or {}) if run is not None else {}).get("ui_language")
    if isinstance(ui, str) and ui:
        return ui.lower()
    for m in reversed(history):
        if m.role == "user" and (m.content or "").strip():
            return "zh" if _prefers_zh(m.content) else "en"
    return "en"


def _assemble_trigger_turn(
    event_line: str,
    context_text: str,
    language: str,
) -> tuple[dict[str, Any], list]:
    """Trigger-turn inputs: the system event as the 'user message' (the
    turn's only new information) + the identity-level digest (the same
    ``_build_context`` the chat turns read) + the resolved speech-language
    directive (worker-born — no middleware pin exists here)."""
    return (
        {
            "context_text": context_text,
            "event_line": event_line,
            "speech_language": _speech_language_line(language),
        },
        [],
    )


trigger_agent = ToolLoopAgent(
    name="trigger_turn",
    prompt="trigger.j2",
    system=trigger_system(),
    temperature=0.3,
    assemble=_assemble_trigger_turn,
    # The full perception family rides (the run-completed review reads runs
    # and outputs; a mid-life re-warm may legitimately look at them too) —
    # plus the ONE terminal. 7 tools, well under the hallucination line.
    tools=[WRAP_UP, *CHAT_READ_TOOLS],
    max_iterations=6,
)


def _trigger_dump(
    trigger: str, ref: str, suggestions: list[str]
) -> dict[str, Any]:
    """The assistant row's self-describing dump — the dedup guard reads
    (trigger, ref) off these keys; ``suggestions`` keeps the option labels
    for forensics (the dock itself rebuilds from the row's ``question``
    payload, never from here)."""
    return {
        "type": TRIGGER_DUMP_TYPE,
        "trigger": trigger,
        "ref": ref,
        "suggestions": list(suggestions),
    }


async def _already_spoke(
    db: AsyncSession, conversation_id: UUID, trigger: str, ref: str
) -> bool:
    """The once-only guard: one review per (trigger, ref) per project —
    concurrent fires (the warm's double-materialization race) and repeat
    invocations collapse onto the first landed row."""
    existing = (
        await db.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.intent["type"].astext == TRIGGER_DUMP_TYPE,
                Message.intent["trigger"].astext == trigger,
                Message.intent["ref"].astext == ref,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return existing is not None


async def run_trigger_turn(
    project_id: UUID, trigger: str, ref: str
) -> Message | None:
    """One proactive turn: dedup → assemble → the bounded loop (reads +
    wrap_up) → persist the review row. NEVER raises — a trigger failure is
    silence, not a pipeline error (the world event landed truthfully on its
    own)."""
    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    if trigger not in TRIGGER_WHITELIST:
        logger.warning("trigger_turn_rejected_off_whitelist", trigger=trigger)
        return None
    try:
        # The admission gate (交互完整性批 B): never overtake an in-flight
        # user turn — defer in bounded cycles, drop into silence at the
        # bound. Inside the try: the fire-and-forget doctrine covers the
        # gate's own reads too (a DB hiccup is silence, never a task crash).
        for attempt in range(_TRIGGER_DEFER_MAX_ATTEMPTS + 1):
            verdict = _trigger_admission(
                await _project_turn_in_flight(project_id),
                attempt,
                _TRIGGER_DEFER_MAX_ATTEMPTS,
            )
            if verdict == "proceed":
                break
            if verdict == "drop":
                logger.info(
                    "trigger_turn_admission_deferred_out", trigger=trigger, ref=ref
                )
                return None
            logger.info(
                "trigger_turn_admission_defer",
                trigger=trigger,
                ref=ref,
                attempt=attempt,
            )
            await asyncio.sleep(_TRIGGER_DEFER_SECONDS)
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, project_id)
            if project is None:
                return None
            run: WorkflowRun | None = None
            if trigger == TRIGGER_RUN_COMPLETED:
                run = await db.get(WorkflowRun, UUID(ref))
                if run is None:
                    # The run row is gone (deleted mid-flight) — there is
                    # nothing truthful left to review.
                    return None
            conversation = await _get_or_create_project_conversation(
                db, UUID(str(project.user_id)), project_id
            )
            conversation_id = UUID(str(conversation.id))
            if await _already_spoke(db, conversation_id, trigger, ref):
                logger.info(
                    "trigger_turn_deduped", trigger=trigger, ref=ref
                )
                return None
            # 单一叙事者律第二谓词 (ADR-080): no turn in flight, but a plan
            # sits docked awaiting Start — the plan's own echo prose already
            # narrates "what I saw / what I'll do", so a proactive review
            # now is pure microphone-grabbing (the 2026-09-16 contradiction:
            # "review the plan and hit Start" vs "already queued, how about
            # these three other things"). Silence, not defer — a pending
            # plan can sit for hours, and the world event already landed
            # truthfully on the canvas.
            if is_pending_plan(
                await latest_pending_question(db, conversation_id)
            ):
                logger.info(
                    "trigger_turn_silenced_pending_plan",
                    trigger=trigger,
                    ref=ref,
                )
                return None
            history = list(
                (
                    await db.execute(
                        select(Message)
                        .where(Message.conversation_id == conversation_id)
                        .order_by(Message.created_at.asc())
                    )
                ).scalars()
            )
            context = await _build_context(
                db,
                project,
                history[-6:],
                [],
                await latest_pending_question(db, conversation_id),
            )
            language = _trigger_language(run, history, conversation)
            event_line = (
                f"Run {ref} just reached its terminal state. Review what it "
                "produced (read the run status, then the landed outputs "
                "themselves), then close with your judgment and next steps."
                if trigger == TRIGGER_RUN_COMPLETED
                else "The material understanding for this project's current "
                "assets just completed. Read it, then tell the user what "
                "their material says and what it could become."
            )

            outcome: dict[str, Any] = {}

            async def execute(name: str, params, prose: str):
                """The LoopExecute seat: reads dispatch to the perception
                family (never terminal); ``wrap_up``'s labels are already
                dock-worthy by schema (blank dropped, overlong rejected into
                the loop) — persist the review row and stop the loop."""
                if name in PERCEPTION_TOOLS:
                    return await run_perception_tool(db, project, name, params)
                assert isinstance(params, WrapUpArgs)
                if not prose.strip():
                    return (
                        "an empty review says nothing — speak your judgment "
                        "as your message text, then call wrap_up."
                    )
                outcome["suggestions"] = params.suggestions
                return None

            result = await trigger_agent.call_loop(
                execute,
                event_line=event_line,
                context_text=context.get("text", ""),
                language=language,
            )
            if result.exhausted:
                logger.info(
                    "trigger_turn_exhausted",
                    trigger=trigger,
                    ref=ref,
                    calls=result.calls,
                )
                return None
            speech = result.prose.strip()
            if not speech:
                return None
            suggestions: list[str] = outcome.get("suggestions", [])
            if suggestions:
                # 选项语法统一律 (ADR-081): the next-step labels dock as a
                # REAL options question on the review row (blocking 形态律,
                # × = the graceful not-now). The single-pending invariant's
                # supersede may cascade-bail a parked interrupt run —
                # finalize those after our commit.
                message, bailed_run_ids = await _dock_question(
                    db,
                    conversation_id,
                    speech,
                    _suggestions_payload(suggestions, language),
                    intent=_trigger_dump(trigger, ref, suggestions),
                )
                if trigger == TRIGGER_RUN_COMPLETED:
                    message.workflow_run_id = UUID(ref)
                await db.commit()
                if bailed_run_ids:
                    await finalize_bailed_runs(bailed_run_ids)
            else:
                message = await _create_message(
                    db,
                    conversation_id,
                    "assistant",
                    speech,
                    workflow_run_id=(
                        UUID(ref) if trigger == TRIGGER_RUN_COMPLETED else None
                    ),
                    intent=_trigger_dump(trigger, ref, suggestions),
                )
                await db.commit()
            logger.info(
                "trigger_turn_spoke",
                trigger=trigger,
                ref=ref,
                project_id=str(project_id),
                suggestions=len(suggestions),
            )
            return message
    except Exception as e:  # noqa: BLE001 — fire-and-forget: silence, never a pipeline failure
        logger.warning(
            "trigger_turn_failed", trigger=trigger, ref=ref, error=str(e)
        )
        return None


_trigger_tasks: set[asyncio.Task] = set()


def fire_trigger(project_id: UUID, trigger: str, ref: str) -> None:
    """The pipeline's fire seat (the ``warm_understanding`` task-set
    precedent): schedule the turn, track the task against GC, move on — the
    worker's tick never waits on the agent's speech."""
    task = asyncio.create_task(run_trigger_turn(project_id, trigger, ref))
    _trigger_tasks.add(task)
    task.add_done_callback(_trigger_tasks.discard)


__all__ = [
    "TRIGGER_WHITELIST",
    "TRIGGER_DUMP_TYPE",
    "TRIGGER_UNDERSTANDING",
    "TRIGGER_RUN_COMPLETED",
    "WRAP_UP",
    "fire_trigger",
    "run_trigger_turn",
    "trigger_agent",
]
