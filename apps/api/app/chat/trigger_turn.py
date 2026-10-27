"""Trigger turns — the chat edge agent's proactive speech (ADR-077 判词③, T3).

A trigger turn is a STANDARD bounded tool-loop turn whose "user message" is
a system event instead of human words. The trigger whitelist is the whole
proactivity boundary (简报 §4 挂账③ — outside it the agent NEVER speaks
first):

- ``run_completed`` — a run reached its terminal state
  (``orchestrator.maybe_finalize_run``; 旅程一⑦ the closing reviewer).
  The fire gate mirrors ADR-074②'s closing-line truth: a successful run OR
  a partial failure with landed products (done + output_refs); a run where
  nothing landed fires ``run_failed`` instead (ADR-135). Iter-3 S5
  (ADR-088 §8 R21): the turn's event line carries the deterministic
  DELIVERY FACTS block (``run_review``'s pure core — the latest tool/run
  outcome); the delivery turn's branch law lives in
  ``delivery_system.j2``.
- ``run_failed`` — a run FAILED and nothing landed
  (``orchestrator.maybe_finalize_run``; ADR-135). The receipt alone can
  carry neither the reason nor the next step, so the turn speaks: the
  event line carries the deterministic FAILURE FACTS block (one line per
  failed verdict step — the baked user-facing error line, never
  re-derived), and the one next step docks as 1-2 pickable options, each
  a step that can plausibly succeed (never a verbatim retry of a
  deterministic failure).
- ``craft_decompiled`` — the pinned reference video's craft skeleton
  landed (``decompile``; 旅程二④ the remix offer).

The loop itself: the perception family's reads are the agent's eyes for
run_failed / craft_decompiled (look BEFORE speaking — read-before-speak is
the reviewer's honesty base); run_completed rides the READLESS
``delivery_agent`` and its dedicated ``delivery_system.j2`` (deterministic
outcome facts + conversation context, one matching reply branch). ONE terminal tool (``wrap_up``) closes the turn with the
spoken review plus 0-3 next-step option labels that dock as a REAL
numbered options question on the review row (ADR-081 选项语法统一律 — the
pill form is retired; the picked label rides the answer endpoint's generic
continuation into the next chat turn as the user's own say).

Worker-side seats: both fire points are pipeline code (no request context),
so the turn opens its OWN session (the ``dock_interrupt_question``
precedent), mirrors the speech language of the conversation's own user
messages (2026-10-15 修订 — the interface-language stamp survives only as
the no-signal floor and the chrome fallback's base; never the material's,
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
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.context import build_context, recent_history_within_budget
from app.agents.tool_loop import ChatTool, ToolLoopAgent
from app.chat.intent import _speech_language_line
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.prompts import delivery_system, trigger_system
from app.chat.service import (
    _create_message,
    _dock_question,
    _get_or_create_project_conversation,
    _prefers_zh,
    finalize_bailed_runs,
    stamp_suggestions,
)
from app.chat.turn_tools import CHAT_READ_TOOLS
from app.metering import bind_conversation_turn, fold_conversation_usage
from app.models.schemas import Option, QuestionPayload, SuggestionItem, WrapUpArgs
from app.models.tables import (
    Conversation,
    Message,
    Output,
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.trigger_events import (
    TRIGGER_RUN_COMPLETED,
    TRIGGER_RUN_FAILED,
    TRIGGER_WHITELIST,
    run_id_from_trigger_ref,
)
from app.platform.conversation_context import (
    is_pending_plan,
    latest_pending_question,
)

logger = structlog.get_logger(__name__)

# The proactivity boundary (白名单 — canonical seat ``app.pipeline.trigger_events``,
# re-exported here): a turn fires ONLY from these seats.

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
        "0-3 next-step option labels grounded in the turn's own records "
        "(the event line's facts block and anything you read — they dock "
        "as a numbered options question — ADR-081). Speak first, then "
        "call this."
    ),
    params_model=WrapUpArgs,
)


def _chrome_language(speech: str, floor: str) -> str:
    """The code-side chrome's language (the suggestion dock's title) follows
    the speech the model ACTUALLY wrote (2026-10-15 语言律修订): the speech
    mirrors the conversation's own messages (the assembly's directive), so
    the chrome keys on it — never on the interface floor alone. A
    CJK-bearing speech gets the zh title; anything else falls to the floor
    (残留列账: an en-UI conversation in German still gets the English title
    — one chrome string, only when the suggestion dock lands)."""
    return "zh" if _prefers_zh(speech) else floor


def _trigger_question_line(language: str) -> str:
    """The suggestion dock's bare question (ask 三分解剖 ② — code-assembled,
    never the LLM's voice, same doctrine as the reminder tail): the review
    prose already framed why; the dock title only asks which next step."""
    return "接下来做什么？" if language.startswith("zh") else "What's next?"


def _suggestions_payload(suggestions: list[SuggestionItem], language: str) -> QuestionPayload:
    """The suggestion dock's question payload (ADR-081 选项语法统一律):
    the trigger's send-labels become a REAL options question — numbered
    options (id = 1-based position, the autoResume/digital-badge grammar),
    freeform pencil on, blocking per the 形态律. 一问拍一体化 (2026-09-27):
    each option carries its one-line reason (description) and at most one
    is marked recommended (the verdict's lean, same pick the speech named).
    No slot, no run marker: the answer endpoint's generic continuation
    carries the picked label into the next chat turn as the user's own
    say."""
    return QuestionPayload(
        kind="question",
        question=_trigger_question_line(language),
        options=[
            Option(id=str(index + 1), label=item.label, description=item.description)
            for index, item in enumerate(suggestions)
        ],
        allow_freeform=True,
        recommended_id=next(
            (
                str(index + 1)
                for index, item in enumerate(suggestions)
                if item.recommended
            ),
            None,
        ),
    )


def _trigger_language(
    run: WorkflowRun | None,
    history: list[Message],
    conversation: Conversation | None = None,
) -> str:
    """The speech-language FLOOR for a worker-born turn (2026-10-15 语言律
    修订 — the interface owner was previously ABSOLUTE for trigger turns,
    which split the single narrator: an English UI chatting in Chinese got
    a Chinese chat but an English delivery). The speech itself mirrors the
    conversation's own user messages (the assembly's directive does the
    judging — the history rides the context); this chain only names the
    floor for a no-signal history and the chrome fallback's base: the
    conversation's stamped ``ui_language`` owner first, then the run's
    pinned ui_language, then the latest user message's script, then
    English — the project's content language default is NOT a speech
    signal, so it never votes here."""
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
    ``build_context`` the chat turns read) + the resolved speech-language
    directive (worker-born — no middleware pin exists here)."""
    return (
        {
            "context_text": context_text,
            "event_line": event_line,
            "speech_language": _speech_language_line(language, mirror=False),
        },
        [],
    )


trigger_agent = ToolLoopAgent(
    name="trigger_turn",
    prompt="trigger.j2",
    system=trigger_system(),
    temperature=0.3,
    assemble=_assemble_trigger_turn,
    # run_failed / craft_decompiled keep the perception reads plus the ONE
    # terminal. design_storyboard is filtered OUT: a system-initiated beat
    # never launches the minutes-long design beat. run_completed uses the
    # separate readless delivery_agent below.
    tools=[
        WRAP_UP,
        *(t for t in CHAT_READ_TOOLS if t.name != "design_storyboard"),
    ],
    max_iterations=6,
)

# run_completed rides its OWN readless agent: conversation context supplies
# the request and the deterministic DELIVERY FACTS supply the latest outcome.
# The delivery= line selects one reply branch before the model speaks.
# run_failed / craft_decompiled keep the read-bearing agent because their
# causes and skeleton gaps are not pre-assembled facts.
delivery_agent = ToolLoopAgent(
    name="trigger_delivery",
    prompt="trigger.j2",
    system=delivery_system(),
    temperature=0.3,
    assemble=_assemble_trigger_turn,
    tools=[WRAP_UP],
    max_iterations=3,
)


def _delivery_event_line(ref: str, review_lines: list[str]) -> str:
    """The delivery turn's latest-outcome payload.

    The event names a delivery review, not a successful run: the facts'
    ``delivery=`` line alone selects the failed / partial / delivered reply
    branch. Conversation context supplies the original request; these lines
    supply what the latest tools actually produced.
    """
    if review_lines:
        return (
            f"Delivery turn for run {ref}. Use the conversation context for "
            "the user's request and the DELIVERY FACTS below for the latest "
            "tool outcome. Reply with the one matching delivery branch, "
            "then close with wrap_up."
            "\n\nDELIVERY FACTS (deterministic world records, not user copy):\n"
            + "\n".join(review_lines)
        )
    return (
        f"Delivery turn for run {ref}. No deterministic delivery facts "
        "could be assembled. Give only the plain completion the receipt "
        "proves, never invent details you cannot see, then close with wrap_up."
    )


def _wrap_up_rejection(trigger: str, suggestions: list[SuggestionItem]) -> str | None:
    """wrap_up 边界护栏 (2026-09-30 用户拍板 — execute_guardrail 同族):
    the suggestions count is checked against the trigger's journey law
    BEFORE the turn may close — a violation rejects back into the loop
    (the model self-repairs; the user only ever sees the repaired turn).

    - ``run_completed``: hard ceiling of 0 — the completed work's next
      move rides the closing sentence, never a dock (prompt law).
    - ``run_failed``: ceiling of 2 (ADR-135) — nothing landed, so there is
      no card for the next step to ride; it docks as pickable options,
      each one a step that can plausibly SUCCEED (prompt law: never a
      verbatim retry of a deterministic failure)."""
    if trigger == TRIGGER_RUN_COMPLETED and suggestions:
        return (
            f"on {trigger} the next move rides your closing sentence or "
            "the landed card itself, never a dock — call wrap_up again "
            "with suggestions=[]."
        )
    if trigger == TRIGGER_RUN_FAILED and len(suggestions) > 2:
        return (
            f"on {trigger} the dock carries the one next step (a real "
            "fallback at most) — call wrap_up again with at most 2 "
            "suggestions."
        )
    return None


def _trigger_dump(
    trigger: str, ref: str, suggestions: list[SuggestionItem]
) -> dict[str, Any]:
    """The assistant row's self-describing dump — the dedup guard reads
    (trigger, ref) off these keys; ``suggestions`` keeps the option labels
    for forensics (the dock itself rebuilds from the row's ``question``
    payload, never from here)."""
    return {
        "type": TRIGGER_DUMP_TYPE,
        "trigger": trigger,
        "ref": ref,
        "suggestions": [item.label for item in suggestions],
    }


async def _already_spoke(
    db: AsyncSession, conversation_id: UUID, trigger: str, ref: str
) -> bool:
    """The once-only guard: one review per (trigger, ref) per project —
    concurrent fires and repeat invocations collapse onto the first landed
    row."""
    existing = (
        await db.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                and_(
                    Message.intent["type"].astext == TRIGGER_DUMP_TYPE,
                    Message.intent["trigger"].astext == trigger,
                    Message.intent["ref"].astext == ref,
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return existing is not None


async def _run_review_lines(db: AsyncSession, run: WorkflowRun) -> list[str]:
    """The closing audit's fact block (iter-3 S5, ADR-088 §8 R21 / N-58):
    the deterministic 兑现事实清单 for the run_completed turn — the world's
    self-evidence (the run's Confirmed Scope Snapshot, the landed outputs'
    baked specs), adjudicated by ``run_review``'s PURE core and bounded by
    its rendering caps. Zero LLM here; the branch-specific prose law lives
    in ``delivery_system.j2``. Spend is never a closing-beat fact, so no
    capture query rides here. Any read failure degrades to the empty block;
    the delivery turn then gives only the plain receipt fallback and never
    invents unseen details."""
    from app.pipeline.run_review import (  # deferred: pipeline weight
        compute_run_review,
        landed_fact,
        review_fact_lines,
    )

    steps = list(
        (
            await db.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        )
        .scalars()
        .all()
    )
    output_ids = [oid for step in steps for oid in (step.output_refs or [])]
    outputs = []
    if output_ids:
        outputs = list(
            (
                await db.execute(select(Output).where(Output.id.in_(output_ids)))
            )
            .scalars()
            .all()
        )
    ctx = run.context or {}
    # The film confirmed-vs-landed check reads the version THIS run consumed
    # (stamped on the context at Start) — never the current live draft
    # (d08af2af: the closing beat fabricated a drift when no fact existed).
    film_confirmed = None
    if isinstance(ctx.get("prepared_storyboard"), dict):
        film_confirmed = {
            "board": ctx["prepared_storyboard"],
            "params": ctx.get("film_storyboard_params") or {},
            "version": ctx.get("film_storyboard_version"),
            "digest": ctx.get("film_storyboard_content_digest"),
        }
    review = compute_run_review(
        confirmed_scope=ctx.get("confirmed_scope"),
        landed=[landed_fact(o, film_confirmed=film_confirmed,
                            video_confirmed=ctx.get("version_ref")) for o in outputs],
    )
    return review_fact_lines(review)


def _with_upload_retry_suggestion(
    items: list[SuggestionItem], language: str
) -> list[SuggestionItem]:
    """The upload recovery offer is code-stamped from the failure fact.

    The model keeps at most one genuine fallback; it cannot omit the recovery
    or mark a different option as the recommendation.
    """
    zh = language.startswith("zh")
    retry = SuggestionItem(
        label="重新上传" if zh else "Retry upload",
        description=(
            "只重传已生成的视频；缓存失效时会说明需要重新渲染。"
            if zh
            else "Upload the generated video only; if its cache expired, "
            "the system will say a render is needed."
        ),
        recommended=True,
    )
    fallbacks = [
        item.model_copy(update={"recommended": False})
        for item in items
        if item.label != retry.label
    ]
    return [retry, *fallbacks[:1]]


_FAILURE_FACT_CAP = 6


def _failure_fact_lines(
    steps: list[WorkflowStep], fanout_kinds: frozenset[str]
) -> list[str]:
    """The FAILURE FACTS block's pure core (ADR-135): one line per failed
    step, including render/upload fan-out failures. ``step.error`` is already the baked user-facing line in the
    run's UI locale (bake-at-write discipline, errors.py) — the turn
    narrates it verbatim, never re-derives a cause. Bounded by
    ``_FAILURE_FACT_CAP`` (a dying run rarely fails more steps than a
    reader should have to scan)."""
    lines: list[str] = []
    for step in steps:
        if step.status != "failed":
            continue
        lines.append(
            f"FAILED STEP: {step.kind} — {step.error or 'no error recorded'}"
        )
        if len(lines) >= _FAILURE_FACT_CAP:
            break
    return lines


async def _run_failure_lines(db: AsyncSession, run: WorkflowRun) -> list[str]:
    """Fetch the failed run's steps and project the FAILURE FACTS block
    (ADR-135). Zero LLM here, same doctrine as ``_run_review_lines``; the
    prose law lives in ``trigger_system.j2``."""
    from app.pipeline.graph import runtime_fanout_kinds  # deferred: pipeline weight

    steps = list(
        (
            await db.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        )
        .scalars()
        .all()
    )
    return _failure_fact_lines(steps, runtime_fanout_kinds()) or ([f"DELIVERY FAILED: {run.error}"] if run.error else [])


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
            run_id: UUID | None = None
            if trigger in (TRIGGER_RUN_COMPLETED, TRIGGER_RUN_FAILED):
                run_id = run_id_from_trigger_ref(ref)
                run = await db.get(WorkflowRun, run_id)
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
            pending_question = await latest_pending_question(db, conversation_id)
            if is_pending_plan(pending_question):
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
            context = await build_context(
                db,
                project,
                # 滑动窗口装配 (ADR-117 D4): one budget predicate, never a
                # fixed-count slice — world state survives by construction.
                await recent_history_within_budget(db, history),
                [],
                await latest_pending_question(db, conversation_id),
                # 环境能力位 (ADR-118 §6): the worker-born turn has no
                # request — it inherits the conversation-stamped bit
                # (last-wins, prepare_chat_turn 的 ui_language 同律座);
                # None = never reported → Environment line omitted, the
                # handoff gate stays closed (未知恒闭, 永不编造).
                canvas_available=conversation.canvas_available,
            )
            language = _trigger_language(run, history, conversation)
            upload_retry_available = False
            if trigger == TRIGGER_RUN_COMPLETED:
                assert run is not None
                # 交付收敛 (修复批 B): the event line IS the delivery's
                # whole record (the deterministic fact block rides it —
                # the world's self-evidence, bounded by review_fact_lines'
                # own caps) and the readless delivery_agent writes once.
                event_line = _delivery_event_line(
                    str(run_id), await _run_review_lines(db, run)
                )
            elif trigger == TRIGGER_RUN_FAILED:
                assert run is not None
                event_line = (
                    f"Run {run_id} FAILED and nothing landed — the user got "
                    "no result. Read what happened, then close with the "
                    "honest reason and the one next step."
                )
                # 失败事实注入 (ADR-135): the failed verdict steps' baked
                # user-facing lines ride the event line — deterministic,
                # narrate-never-contradict, same doctrine as DELIVERY FACTS.
                failure_lines = await _run_failure_lines(db, run)
                from app.pipeline.rendering import (  # deferred
                    UPLOAD_RETRY_AMBIGUOUS,
                    resolve_upload_retry,
                )

                upload_target = await resolve_upload_retry(db, project, run_id=run.id)
                upload_retry_available = (
                    not isinstance(upload_target, str)
                    or upload_target == UPLOAD_RETRY_AMBIGUOUS
                )
                if upload_retry_available:
                    event_line += (
                        "\n\nUPLOAD RETRY AVAILABLE: the finished video can be "
                        "offered for upload-only recovery; the system appends "
                        "that option after your turn."
                    )
                if failure_lines:
                    event_line += (
                        "\n\nFAILURE FACTS (deterministic, from the run's own "
                        "records — narrate them, never contradict them, never "
                        "invent a cause beyond them):\n"
                        + "\n".join(failure_lines)
                    )
            else:
                # craft_decompiled — the pinned case's skeleton is the
                # event; the prompt's own law orders the read first.
                event_line = (
                    "The pinned reference video's craft skeleton just "
                    "landed. Read it, then tell the user what a remix will "
                    "borrow from the case."
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
                rejection = _wrap_up_rejection(trigger, params.suggestions)
                if rejection is not None:
                    return rejection
                outcome["suggestions"] = params.suggestions
                return None

            with bind_conversation_turn() as _usage_bind:
                # run_completed rides the READLESS delivery agent (修复批 B)
                # — the facts block is its whole record, so the review is
                # written once and closed; the other triggers keep the
                # read-bearing agent (look before you speak).
                agent = (
                    delivery_agent
                    if trigger == TRIGGER_RUN_COMPLETED
                    else trigger_agent
                )
                result = await agent.call_loop(
                    execute,
                    event_line=event_line,
                    context_text=context.get("text", ""),
                    language=language,
                )
            # 会话层计量 (ADR-117 D3): the proactive turn IS a conversation
            # turn — its usage row rides the review row's own commit below
            # (a silenced landing never commits, so it never writes either).
            await fold_conversation_usage(
                db,
                user_id=UUID(str(project.user_id)),
                project_id=project_id,
                accrued=_usage_bind.accrued,
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
            # 落点拍 (ADR-080 第二谓词补齐, 2026-09-21 拍板): the admission
            # check ran before our LLM loop — a user turn may have docked a
            # plan since (S16-P2 实证: the review's suggestion dock landed
            # the same second as present_plan and superseded it, stealing
            # the confirmation seat). Re-check at the landing beat: a plan
            # now pending holds the microphone — the world event already
            # landed truthfully on the canvas, so silence overall (never a
            # dock, never a bare message). Not deduped: once the plan
            # clears, a later fire of the same world event may speak.
            landing_question = await latest_pending_question(db, conversation_id)
            if is_pending_plan(landing_question):
                logger.info(
                    "trigger_turn_silenced_pending_plan_at_landing",
                    trigger=trigger,
                    ref=ref,
                )
                return None
            suggestions: list[SuggestionItem] = outcome.get("suggestions", [])
            chrome_language = _chrome_language(speech, language)
            if upload_retry_available:
                suggestions = _with_upload_retry_suggestion(suggestions, chrome_language)
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
                    _suggestions_payload(suggestions, chrome_language),
                    intent=_trigger_dump(trigger, ref, suggestions),
                )
                if trigger in (TRIGGER_RUN_COMPLETED, TRIGGER_RUN_FAILED):
                    message.workflow_run_id = run_id
                # 建议谱系 provenance (ADR-099 §4 — the trigger path's
                # pre-existing gap: a pick used to lose its source): the
                # options stamp onto the SAME row's interaction block, so
                # the answer endpoint can reconstruct the pick's ref (the
                # row = source turn, the option id = suggestion id) and the
                # directed stale check has its snapshot.
                await stamp_suggestions(db, message, suggestions, project_id)
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
                        run_id
                        if trigger in (TRIGGER_RUN_COMPLETED, TRIGGER_RUN_FAILED)
                        else None
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
    except IntegrityError:
        # 唯一索引收口 (migration n4d7e0a3b6c9, 2026-09-28): a cross-process
        # twin committed the same (conversation, trigger, ref) review first
        # — the race loser dedups late. Silence (the fire-and-forget
        # doctrine), but named for forensics, distinct from a real failure.
        logger.info("trigger_turn_race_lost", trigger=trigger, ref=ref)
        return None
    except Exception as e:  # noqa: BLE001 — fire-and-forget: silence, never a pipeline failure
        logger.warning(
            "trigger_turn_failed", trigger=trigger, ref=ref, error=str(e)
        )
        return None


_trigger_tasks: set[asyncio.Task] = set()
# In-flight turn registry (2026-09-28 — project 600d4a13's double-dock
# race): two fires of the same (project, trigger, ref) within one process
# collapse HERE — the turn's ``_already_spoke`` SELECT only sees COMMITTED
# reviews, so without this registry two concurrent turns both speak (the
# second supersedes the first and the user's option click 409s). The
# trigger_review unique index (migration n4d7e0a3b6c9) is the cross-process
# backstop — the loser's commit fails into the turn's fire-and-forget
# silence. The key releases at task completion: by then the review row is
# committed and ``_already_spoke`` is authoritative again.
_trigger_inflight: set[tuple[UUID, str, str]] = set()


def fire_trigger(project_id: UUID, trigger: str, ref: str) -> None:
    """The pipeline's fire seat (the ``warm_understanding`` task-set
    precedent): schedule the turn, track the task against GC, move on — the
    worker's tick never waits on the agent's speech."""
    key = (project_id, trigger, ref)
    if key in _trigger_inflight:
        logger.info("trigger_turn_skip_inflight", trigger=trigger, ref=ref)
        return
    _trigger_inflight.add(key)
    task = asyncio.create_task(run_trigger_turn(project_id, trigger, ref))
    _trigger_tasks.add(task)

    def _release(done: asyncio.Task) -> None:
        _trigger_tasks.discard(done)
        _trigger_inflight.discard(key)

    task.add_done_callback(_release)


__all__ = [
    "TRIGGER_WHITELIST",
    "TRIGGER_DUMP_TYPE",
    "TRIGGER_RUN_COMPLETED",
    "WRAP_UP",
    "delivery_agent",
    "fire_trigger",
    "run_trigger_turn",
    "trigger_agent",
]
