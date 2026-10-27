"""The chat path's tool-loop runner (ADR-077 判词② — T2a 内核半边).

The retired ``_propose_turn`` dispatch, re-homed: the chat intent
agent closes its turn with ONE terminal tool call — the proposal states'
mechanical translation (task_list → ``propose_tasks``, wiring →
``edit_graph``, craft → ``revise_output``, precise edit → ``edit_output``,
ask → ``ask_user``, answer → ``answer``). The write doors never moved:

- ``propose_tasks`` NEVER births a run (Phase 4 B3, ADR-087 §4 + Frozen
  Rule 1/3 — a natural-language request is Task Intent, never Paid
  Execution Authorization): every new-work proposal docks as a PendingPlan
  + task_book question through ``_dock_plan_as_question`` — the ONE shared
  dock seat — and the run births only on the user's explicit Start (the
  propose path and the plan path share ONE authorization seat; same-turn
  create_run is forbidden here). ``edit_graph``'s approved continuations
  still come from ``_create_run_from_tasks`` — the ONLY run birthplace
  (wiring resolves its subgraph through ``apply_wiring_ops`` first, the
  graph's only write door).
  Phase 4 B2 (ADR-087 §4 + D4): ``edit_graph``'s run births are gated by the
  Deterministic Scope Classifier — the door's RESULTING paid execution scope
  is adjudicated against the pre-op run-born graph inside a savepoint; an
  approved continuation runs autonomously (Frozen Rule 5), an expansion /
  unprovable scope rolls the door's mutation back and docks as a PendingPlan
  + task_book question instead (Rule 6/10 — never a silent paid run on new
  scope);
- ``edit_output`` (Final Hardening B1 — the chat path's ONLY edit verb;
  the raw-ops ``apply_edit_ops`` retired 2026-09-24) compiles one
  controlled registry op and journals it through the operations registry's
  ``apply_operations`` with message lineage;
- every adjudication rejection (registry / wiring door / transform targets)
  IS the loop's feedback — the retired funnel repair round's seat, one
  bounded iteration each; a rejection writes nothing.

插话判定结算 (ADR-053 R2) rides the accepted call's ``pending_disposition``
seat — judged settlement is code's (a rejected call never settles). A judged
answer on a parked interrupt wakes its run and the tool's own dispatch is
skipped (the wake IS the continuation, unchanged).

Storage shapes preserved: message.intent still carries the proposal dumps
(TaskListProposal / WiringProposal / QuestionProposal /
AnswerProposal, built here from the accepted call's params plus the turn's
prose).

T2b 感知族 (ADR-077 判词②): the read tools (``app/chat/perception/``)
dispatch straight from ``execute`` — they never carry a disposition, never
touch the outcome, and return a ToolObservation the loop feeds back.

iter-3 S2 (R6 parity): the exploration chain rides this path too — a
post-run discovery goal ('再挑两条关于定价的') opens a NEW journey and lands
its decision package through the SAME dock seat (``_dock_plan_as_question``
gained the package faces as additive kwargs); the compile law itself lives
in ``app/chat/exploration_compile.py`` (ONE seat shared with the plan path
— the two loops can never drift on it).
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.context import build_context
from app.agents.tool_loop import (
    TerminalRefusal,
    ToolObservation,
    ToolRejected as LoopToolRejected,  # alias: app.tools.ToolRejected (the
    # chain-adjudication exception, imported below) shadows the loop event's
    # name in this module — the retract seat must match the LOOP's class
)
from app.chat.deferred_frames import DeferredFrames
from app.chat.exploration_compile import (
    compile_plan_rows_package,
    compile_plans_package,
    recompile_journey_package,
)
from app.chat.exploration_tools import (
    EXPLORATION_TOOLS,
    ProposeCandidatesArgs,
    ProposePlansArgs,
    ProposeSelectsArgs,
    RevisePlanArgs,
    ReviseSelectsArgs,
    candidates_observation,
    selects_observation,
)
from app.chat.intent import chat_intent_agent
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.turn_tools import film_rejection_stop
from app.chat.service import (
    _ASK_BACK_TEXT,
    _ask_content,
    _auto_start_docked_plan,
    _bare_question,
    _cannot_do_text,
    _checkpoint_callback,
    _compute_plan_reasons,
    _create_message,
    _create_run_from_tasks,
    _derive_chat_caption_mode,
    _design_blocked_text,
    _design_no_progress_text,
    _dock_question,
    _estimate_tail,
    _prefers_zh,
    _parked_interrupt_run,
    _resume_ack_line,
    _reminder_tail,
    _safe_task_estimate,
    latest_pending_question,
    resolve_confirmation_need,
    resolve_suggestion_note,
    sync_plan_question,
)
from app.models.schemas import (
    AnswerPayload,
    AnswerProposal,
    AssetType,
    Brief,
    ChatAnswerArgs,
    ChatAskArgs,
    ChatMention,
    DesignStoryboardArgs,
    DesignVideoArgs,
    EditGraphArgs,
    EditOutputArgs,
    FilmStoryboard,
    InferredIntent,
    PendingPlan,
    PlanEstimate,
    ProposeTasksArgs,
    QuestionPayload,
    QuestionProposal,
    RenderStatus,
    RetryUploadArgs,
    ReviseOutputArgs,
    ReviseVideoArgs,
    SuggestionRef,
    WiringProposal,
    edit_kind_for_params,
    resolve_recommended_id,
)
from app.models.tables import (
    Asset,
    ExplorationRow,
    GraphNode,
    Message,
    Output,
    Persona,
    Project,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.operations.service import OpConflict, OpRejected, apply_operations
from app.pipeline.assets import create_web_page_assets_committed_from_urls
from app.pipeline.edit_ops import EditRefusal, assemble_edit_op
from app.pipeline.edit_span import resolve_quote_span
from app.pipeline.exploration_store import (
    PHASE_DOCKED,
    PHASE_PRE_DOCK,
    ExplorationRejected,
    propose_candidates,
    propose_selects,
    journey_summary_line,
    read_journey_evidence,
    read_journey_plan_rows,
    read_journey_plans,
    read_journey_summaries,
    revise_plan,
    revise_selects,
    select_revision_phase,
    supersede_plan,
)
from app.pipeline.scope_compile import (
    assemble_craft_revision,
    decision_package_plans,
    route_revision,
)
from app.platform.project_context import resolve_default_persona
from app.platform.user_settings import read_confirmation_prefs
from app.providers.llm.base import LLMError
from app.tools import ToolRejected, validate_task_list

logger = structlog.get_logger()

# The return shape the service layer's callers hold (unchanged):
# (assistant message, dispatched run id, cascade-bailed run ids, the pending
# question this turn settled by judgment). The assistant message is None
# when the turn closes without a row (the degrade paths land their own
# shape).
ProposeTurnOutcome = tuple[Message | None, UUID | None, list[UUID], Message | None]

# _dock_plan_as_question's estimate kwarg sentinel: None is a REAL value
# (an unquotable plan — the gate compared it and chose direct), distinct
# from "not computed yet" (compile here, the pre-gate behavior).
_ESTIMATE_UNSET: Any = object()


def pinned_output_id(mentions: list, llm_output_id: str | None) -> str | None:
    """B4 (Final Hardening, 2026-09-24 — MENTIONS 指认族契约的写门化): exactly
    one @output pin in the turn IS the definite edit/revision target; the
    LLM's relay of it through tool params is advisory only. Live evidence
    (drive 1/2 拍2): the model twice edited its conversational-focus clip
    while the user had pinned the OTHER one, honestly reporting the wrong
    clip's real numbers. The pin is user truth — the server resolves it
    deterministically. Zero or 2+ output pins: the LLM's relay stands
    (ambiguity rides the existing refusals)."""
    pins = [m for m in mentions if getattr(m, "type", None) == "output"]
    if len(pins) == 1:
        return str(pins[0].id)
    return llm_output_id


def _edit_fact_echo(kind: str, op: dict, *, zh: bool) -> str:
    """The precise edit's world-witnessed fact sentence (展示文案二源律 —
    the applied op's REAL numbers/state, code-composed, never the LLM's
    claim and never a frozen template). Appended under the agent's prose."""
    p = op["params"]
    if kind == "remove_range":
        return (
            f"我把 {p['start']:.1f}–{p['end']:.1f}s 这段去掉了，正在重新渲染。"
            if zh
            else f"I cut the {p['start']:.1f}–{p['end']:.1f}s span — re-rendering now."
        )
    if kind == "set_trim":
        return (
            f"结尾已收紧到 {p['end']:.1f}s，正在重新渲染。"
            if zh
            else f"The end is tightened to {p['end']:.1f}s — re-rendering now."
        )
    if kind == "set_caption_style":
        return (
            f"字幕样式已换成 {p['preset']}，正在重新渲染。"
            if zh
            else f"Captions are now {p['preset']} — re-rendering now."
        )
    return (
        f"标题已改成「{p['text']}」，正在重新渲染。"
        if zh
        else f"The title is now “{p['text']}” — re-rendering now."
    )


class ChatTurn:
    """One chat-path turn: the context assembly, the five tool executions,
    and the outcome mapping. One instance per turn."""

    def __init__(
        self,
        db: AsyncSession,
        user_id: UUID,
        conversation,
        project: Project | None,
        text: str,
        on_phase=None,
        on_activity=None,
        on_candidates=None,
        on_row_append=None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.conversation_id = UUID(str(conversation.id))
        # 环境能力位 (ADR-118 §6 双键): the conversation-stamped client
        # capability (prepare_chat_turn 的 last-wins 盖章, ui_language 同律
        # 座) — the assembly's canvas_available source on request-born
        # turns; None = never reported → the Environment line stays out.
        self.canvas_available = conversation.canvas_available
        self.project = project
        self.text = text
        self.on_phase = on_phase
        # 工作会话里程碑通道 (iter-3 S2 — the plan path's iter-2 ⑥ channel,
        # threaded here for the post-run discovery chain's door successes;
        # None = the one-shot path, no stream, no frames).
        self.on_activity = on_activity
        self.on_candidates = on_candidates
        # Retired with the program-markdown publication (2026-10-18 裁决,
        # the plan path's mirror): the design beat no longer lands its own
        # row mid-turn — the presenting model's ONE message carries the
        # board. The param stays for the runner's signature parity.
        self.on_row_append = on_row_append
        # 呈现关联挂号 (2026-10-18 裁决, the plan path's mirror): set by a
        # successful design execute ({"version": N}); finish stamps the
        # TERMINAL speech row's id onto film_presented_message_id — only
        # after that row actually persists, version-guarded.
        self._presentation_pending: dict | None = None
        # 视频呈现挂号 (ADR-145 phase B, the plan path's mirror): a
        # successful design_video / revise_video stashes the saved
        # version's read dict; finish stamps the receipt + the storyboard
        # block onto the persisted terminal row (shared seat:
        # video_turn_seats).
        self._video_presentation_pending: dict | None = None
        self._video_call_counter: int = 0
        # 同回合纠正道 (7276ef13 修复批 ②, the plan path's mirror — its
        # init comment carries the full forensics): a successful design's
        # version number; further design_storyboard calls THIS turn are
        # CORRECTIONS of that standing version — drafted against the
        # in-turn version under the turn's own standing marker (never a
        # second begin — the self-lock), bounded by
        # MAX_DESIGN_CORRECTIONS_PER_TURN.
        self._designed_this_turn: int | None = None
        # The turn's own committed marker's draft id (the correction
        # publish guard compares against it).
        self._design_draft_id: str | None = None
        # 首 begin 拒绝锁存 (the begin-refusal latch — the plan path's
        # mirror): a refused FIRST begin latches the refusal reason here
        # ("in_flight" / "locked" / "gone"); every later design_storyboard
        # call this turn ends the loop deterministically (TerminalRefusal)
        # instead of re-hitting the row, and finish() speaks the
        # busy/conflict line — never _cannot_do_text.
        self._design_begin_refusal: str | None = None
        # Corrections admitted this turn (counted at ADMISSION).
        self._design_corrections: int = 0
        # 带条件授权守卫 (7276ef13 ③, the plan path's mirror; 定点收尾①签名
        # 台账, 复审两度收紧销账律): a record ledger of THIS turn's failed
        # design calls — every failed exit appends its
        # ``design_call_record`` (mechanical key + requested normalized
        # target values); the ONE clearing seat is a successful PATCH whose
        # record is EXACTLY EQUIVALENT (key AND target — a different value
        # or a dropped field never clears); a COMPOSE success NEVER clears;
        # the dock seat passes ``bool(...)`` as ``unmet_condition``.
        self._design_shortfalls: list[dict] = []
        self.pending: Message | None = None
        self.pending_judgable = False
        self.context: dict = {"text": ""}
        self.mentions: list[ChatMention] = []
        self.settled_question: Message | None = None
        self.outcome: ProposeTurnOutcome | None = None
        self._bailed_on_skip: list[UUID] = []
        self.deferred: DeferredFrames | None = None
        # 建议点选 provenance (ADR-099 §4): this turn's message IS a
        # suggestion pick → the resolution note rides into the agent-facing
        # message at the call_loop seat (self.text stays the user's own
        # words).
        self.suggestion_note: str | None = None

    async def assemble(
        self,
        mentions: list[ChatMention],
        recent: list[Message],
        suggestion_ref: SuggestionRef | None = None,
    ) -> None:
        db, project = self.db, self.project
        self.mentions = mentions
        if suggestion_ref is not None:
            self.suggestion_note = await resolve_suggestion_note(
                db,
                self.conversation_id,
                UUID(str(project.id)) if project is not None else None,
                suggestion_ref,
            )
        pending = (
            await latest_pending_question(db, self.conversation_id) if project else None
        )
        # A pending task_book rides the context as before, but it is never a
        # judgment subject on this path — its answers are the dock's Start /
        # plan-path turns (the same exclusion as prepare_chat_turn's
        # autoResume); judged settlement and the reminder tail apply to plain
        # questions only.
        self.pending = pending
        self.pending_judgable = (
            pending is not None
            and (pending.question or {}).get("kind") == "question"
            # A blank turn (attachment-only: this path receives request.message
            # verbatim — the stand-in line is a plan-path local) carries nothing
            # to judge, so the question is not a judgment subject this turn,
            # period. "A blank message never auto-answers a docked question"
            # is a law, not a judgment (2026-09-05 S6d).
            and bool(self.text.strip())
        )
        # ADR-117 D1: the confirmation-settings fact rides the chat context
        # (the chat_intent system template's close law is mode-conditional)
        # — read tolerant, fresh per turn, rendered by build_context's seat.
        confirmation: tuple[str, str] | None = None
        if project:
            user_row = await db.get(User, self.user_id)
            confirmation = read_confirmation_prefs(
                user_row.settings if user_row is not None else None
            )
        self.context = (
            await build_context(
                db, project, recent, mentions, pending,
                canvas_available=self.canvas_available,
                confirmation=confirmation,
            )
            if project
            else {"text": ""}
        )

    # ---- 资产角色 pins (ADR-078 判词④), the chat path's dispatch seat --------

    async def _role_pins_for(self, tasks) -> tuple[str | None, str | None]:
        """(source, exemplar) pins for a proposed chain — only when the chain
        reaches the clips producer (derived off NODE_KINDS via
        node_for_output, never a name list); every other chain runs pin-less.

        An asset @-mention on a project video pins THIS run's source (the
        mentioned video is the material to cut — the mention outranks the
        inherited pin). Without a mention, the conversation's settled pins
        inherit (the pending plan's, else the latest run's — reference 常驻).
        角色反转: a mention colliding with the inherited exemplar flips the
        roles — the mention wins the source seat, the exemplar seat clears
        for this run (the case cuts itself, no self-imitation).
        """
        from app.chat.perception.executes import _conversation_role_pins
        from app.pipeline.graph import node_for_output

        def _task_tool(t) -> str | None:
            # Shape-tolerant read (the launch_film params seat's same
            # convention): the proposal seats pass TaskItem objects, the
            # film design beat's synthetic chain is plain dicts.
            return t.get("tool") if isinstance(t, dict) else getattr(t, "tool", None)

        project = self.project
        if project is None:
            return (None, None)
        clips_node = node_for_output("clips")
        if clips_node is None or not any(
            _task_tool(t) == clips_node.kind for t in tasks
        ):
            return (None, None)
        source_pin: str | None = None
        mentioned = next((m for m in self.mentions if m.type == "asset"), None)
        if mentioned is not None:
            asset = await self.db.get(Asset, mentioned.id)
            if (
                asset is not None
                and str(asset.project_id) == str(project.id)
                and asset.type == AssetType.VIDEO
                and asset.file_url
            ):
                source_pin = str(asset.id)
        inh_source, exemplar_pin = await _conversation_role_pins(self.db, project)
        source_pin = source_pin or inh_source
        if exemplar_pin is not None and exemplar_pin == source_pin:
            exemplar_pin = None
        return (source_pin, exemplar_pin)

    # ---- the pending-disposition preamble (ADR-053 R2) ----------------------

    async def _settle_by_disposition(self, disposition: str) -> bool:
        """The accepted call's pending-question judgment, settled by code.
        Returns True when the turn ENDS here (a parked interrupt's answer —
        the wake IS the continuation, the tool's own dispatch is skipped)."""
        if not self.pending_judgable or disposition == "none":
            return False
        db, pending, text = self.db, self.pending, self.text
        assert pending is not None
        if disposition == "answer":
            pending.answer = AnswerPayload(
                kind="freeform",
                text=text,
                answered_at=datetime.now(UTC),
            ).model_dump(mode="json")
            await db.flush()
            self.settled_question = pending
            self.pending = None
            if pending.workflow_run_id is not None:
                from app.pipeline.orchestrator import resume_waiting_interrupt

                run = await _parked_interrupt_run(db, pending.workflow_run_id)
                if run is not None:
                    outcome = await resume_waiting_interrupt(db, run, pending.answer)
                    decided = (pending.answer or {}).get("text") or ""
                    # Same deterministic acknowledgment as the option-hit wake in
                    # prepare_chat_turn — R1 B3: a blocked arbitration (another
                    # run holds the authority) speaks the parked line instead.
                    assistant_message = await _create_message(
                        db,
                        self.conversation_id,
                        "assistant",
                        _resume_ack_line(decided, outcome),
                    )
                    self.outcome = (assistant_message, None, [], self.settled_question)
                    return True
            return False
        # "skip" — an explicit decline settles bail (the text question's only
        # ×); the tool's own dispatch still runs.
        pending.answer = AnswerPayload(
            kind="bail",
            answered_at=datetime.now(UTC),
        ).model_dump(mode="json")
        await db.flush()
        self.settled_question = pending
        if pending.workflow_run_id is not None:
            from app.pipeline.orchestrator import bail_waiting_interrupt

            run = await db.get(WorkflowRun, pending.workflow_run_id)
            if run is not None and await bail_waiting_interrupt(db, run) is not None:
                self._bailed_on_skip = [UUID(str(run.id))]
        self.pending = None
        return False

    # ---- the loop's execute dispatch ----------------------------------------

    async def execute(self, name: str, params, prose: str) -> str | None | ToolObservation | TerminalRefusal:
        """The LoopExecute seat: the disposition preamble, then the tool's
        validate → (reject: feedback, zero writes) → accept: writes + the
        outcome stashed → None (terminal stop). A PERCEPTION call never
        carries a disposition and never ends the turn — it dispatches to the
        family registry and rides back as a ToolObservation."""
        if name in PERCEPTION_TOOLS:
            if name == "get_video_version" and params.present:
                from app.chat.video_turn_seats import read_video_for_presentation
                read, feedback = await read_video_for_presentation(self.db, self.project, params)
                if read is not None:
                    self._video_presentation_pending = read
                return feedback
            return await run_perception_tool(
                self.db,
                self.project,
                name,
                params,
            )
        disposition = (
            getattr(params, "pending_disposition", "none") if params is not None else "none"
        )
        if await self._settle_by_disposition(disposition):
            result: str | None | ToolObservation = None  # the parked interrupt's wake IS the continuation
        else:
            result = await self._dispatch(name, params, prose)
        # The speech-commit resolution (言语提交协议): a terminal accept
        # closes the frame buffer (a rejection-marked turn drops — its
        # words were retracted speech). Rejections retract at the loop's
        # ToolRejected event (the runner's wrapped on_loop_event — one seat
        # catches all four rejection kinds); ToolObservations are
        # non-terminal (reads) — the queue stays armed.
        if result is None:
            await self._resolve_deferred()
        return result

    async def _dispatch(self, name: str, params, prose: str) -> str | None | ToolObservation:
        if name in EXPLORATION_TOOLS:
            return await self._explore(name, params, prose)
        if name == "propose_tasks":
            assert isinstance(params, ProposeTasksArgs)
            return await self._propose_tasks(params, prose)
        if name == "design_storyboard":
            assert isinstance(params, DesignStoryboardArgs)
            return await self._design_storyboard(params, prose)
        if name == "design_video":
            assert isinstance(params, DesignVideoArgs)
            return await self._design_video(params)
        if name == "revise_video":
            assert isinstance(params, ReviseVideoArgs)
            return await self._revise_video(params)
        if name == "edit_graph":
            assert isinstance(params, EditGraphArgs)
            return await self._edit_graph(params, prose)
        if name == "retry_upload":
            assert isinstance(params, RetryUploadArgs)
            return await self._retry_upload(params, prose)
        if name == "revise_output":
            assert isinstance(params, ReviseOutputArgs)
            return await self._revise_output(params, prose)
        if name == "edit_output":
            assert isinstance(params, EditOutputArgs)
            return await self._edit_output(params, prose)
        if name == "ask_user":
            assert isinstance(params, ChatAskArgs)
            return await self._ask_user(params, prose)
        if name == "answer":
            assert isinstance(params, ChatAnswerArgs)
            return await self._answer(params, prose)
        return f"unknown tool {name!r}"  # unreachable — the driver gates names

    async def _resolve_deferred(self) -> None:
        """The accepted terminal's frame release: flush the queue in order
        and disarm, or drop it when a rejection marked the turn (retracted
        speech — the settled envelope paces out whole, the zero-delta
        path's law)."""
        deferred = self.deferred
        if deferred is None or not deferred.armed:
            return
        if deferred.rejected:
            deferred.drop()
        else:
            await deferred.flush()
            deferred.disarm()

    async def _propose_tasks(self, params: ProposeTasksArgs, prose: str) -> str | None:
        """task_list → the caption gate, then the Confirmation Dock (ADR-087
        §4, Phase 4 B3): a natural-language request is Task Intent, never
        Paid Execution Authorization (Frozen Rules 1/3) — EVERY new-work
        proposal docks as a PendingPlan + task_book question (estimate +
        charge semantics + canonical draft preview), and the run births
        only on the user's explicit Start. Same-turn create_run is
        forbidden on this path (统一 Paid Authorization path — the propose
        path and the plan path share ONE authorization seat). The
        registry's ToolRejected rides back as the loop's feedback —
        adjudication stays immediate and only registry-valid chains ever
        dock; the birthplace's remaining constraints (media gates /
        transform targets / active-run guard) fire at Start, the plan
        path's own posture."""
        db, project, text = self.db, self.project, self.text
        assert project is not None  # propose_tasks is project-bound
        from app.chat.video_turn_seats import video_proposal_guard
        video_guard = await video_proposal_guard(db, project, params.tasks,
            pending_read=self._video_presentation_pending, production_intent=params.production_intent, mentions=self.mentions)
        if video_guard is not None:
            return video_guard
        if not params.tasks:
            return (
                "empty task list — to ask the user first, call ask_user; for "
                "a purely informational reply, call answer."
            )
        try:
            validate_task_list(params.tasks)
        except ToolRejected as e:
            # The registry's rejection IS the feedback — one bounded loop
            # iteration (the retired repair round's seat) — the same
            # adjudication _create_run_from_tasks ran at the birthplace,
            # now BEFORE the dock so only registry-valid chains ever dock.
            return f"{e} (available: {getattr(e, 'suggestions', [])})"
        from app.chat.turn_tools import film_revision_proposal_guard

        revision_guard = film_revision_proposal_guard(
            designed_version=self._designed_this_turn,
            tasks=params.tasks,
            production_intent=params.production_intent,
        )
        if revision_guard is not None:
            return revision_guard
        # Declared-URL capture (same absorb seat as the plan path): a link
        # the user offered as material becomes a WEB_PAGE asset BEFORE the
        # dock — committed in its own transaction so the capture worker can
        # claim it while this chat turn stays open (the dock-seat storyboard
        # waits for that capture; a flush-only row would deadlock the wait).
        # CaptureBlocked propagates (the creation seat's SSRF gate).
        if params.material_urls:
            await create_web_page_assets_committed_from_urls(
                UUID(str(project.id)), self.user_id, params.material_urls
            )
        # Caption mode (ADR-099 §8 default absorption): the funnel derives
        # what the user didn't name — fresh keyword > the previous dock's
        # value > source_only when a distinct second language makes the
        # choice real — and the stamped value rides the docked intent;
        # Start reads intent.caption_mode off the stored pending.
        caption_mode = await _derive_chat_caption_mode(db, project, params.tasks, text)
        source_pin, exemplar_pin = await self._role_pins_for(params.tasks)
        # 守卫传播 (分镜不是开工): a STRING return is the film guardrail's
        # steering observation — it rides back as the tool loop's feedback.
        return await self._dock_plan_as_question(
            tasks=params.tasks,
            answer=prose,
            # P0-② 对账 (2026-09-22): the distilled EXTRA instruction wins
            # when the model supplies it (the one contract with the plan
            # path — schemas.py / intent_router_system.j2); an absent field
            # falls back to the turn's raw text (the pre-fix behavior), so
            # the writers' trust chain never loses the instruction whole.
            specific_instruction=params.specific_instruction or text or None,
            caption_mode=caption_mode,
            name=params.name or None,
            source_pin=source_pin,
            exemplar_pin=exemplar_pin,
            production_intent=params.production_intent,
        )

    async def _stamp_presentation(self, message) -> None:
        """The presented-message association (2026-10-18 裁决 — LLM 唯一
        呈现, the plan path's mirror): fires from ``finish`` when a design
        beat this turn is owed its presentation and a TERMINAL speech row
        actually persisted. Degrade rows (ask-back / cannot-do) never
        stamp — a board the user never saw stays honestly unpresented.
        Version-guarded by ``presentation_stamp_update``; the write rides
        the turn's one transaction, so a failed/cancelled turn never
        leaves a phantom "presented" mark."""
        await self._stamp_video_presentation(message)
        pending = self._presentation_pending
        self._presentation_pending = None
        if pending is None or message is None or self.project is None:
            return
        from app.tools.film.storyboard import (  # deferred: tool seam
            presentation_stamp_update,
        )

        updated = presentation_stamp_update(
            self.project.pending_brief,
            version=pending["version"],
            message_id=str(message.id),
        )
        if updated is not None:
            self.project.pending_brief = updated

    async def _stamp_video_presentation(self, message) -> None:
        """The video family's presentation association (ADR-145 phase B,
        the plan path's mirror): delegates to the shared seat
        (video_turn_seats) — the receipt + the storyboard block land on
        the persisted terminal row, never on a degrade row."""
        pending = self._video_presentation_pending
        self._video_presentation_pending = None
        if self.project is None:
            return
        from app.chat.video_turn_seats import (  # deferred: same layer
            stamp_video_presentation,
        )

        stamp_video_presentation(self.project, message, pending)

    async def _design_video(self, params: DesignVideoArgs) -> str | ToolObservation:
        """design_video → the video family's design beat (ADR-145 phase B,
        the plan path's mirror): the shared seat saves the version through
        the write door on its OWN session; the model's ONE next message
        presents the saved facts. NO plan docks, NO run starts."""
        if self.project is None:
            return "a video work lives in a project — there is no project context here."
        from app.chat.video_turn_seats import (  # deferred: same layer
            design_video_seat,
            video_request_id,
        )

        self._video_call_counter += 1
        read, feedback = await design_video_seat(
            project=self.project,
            args=params,
            request_id=await video_request_id(self.db, self.conversation_id, self._video_call_counter),
        )
        if read is None:
            return feedback
        self._video_presentation_pending = read
        return feedback

    async def _revise_video(self, params: ReviseVideoArgs) -> str | ToolObservation:
        """revise_video → the targeted-revision beat (ADR-145 phase B, the
        plan path's mirror): the shared seat applies the ops through the
        write door; the observation carries the system-computed change set
        + the full current facts. The revision alone never starts
        production."""
        if self.project is None:
            return "a video work lives in a project — there is no project context here."
        from app.chat.video_turn_seats import (  # deferred: same layer
            revise_video_seat,
            video_request_id,
        )

        from app.chat.video_turn_seats import video_mention_guard
        guard = await video_mention_guard(self.db, self.project, self.mentions, params.base_ref.composition_id)
        if guard:
            return guard
        self._video_call_counter += 1
        read, feedback = await revise_video_seat(
            project=self.project,
            args=params,
            request_id=await video_request_id(self.db, self.conversation_id, self._video_call_counter),
        )
        if read is None:
            return feedback
        self._video_presentation_pending = read
        return feedback

    async def _design_storyboard(self, params: DesignStoryboardArgs, prose: str) -> str | ToolObservation | TerminalRefusal:
        """design_storyboard → the film family's design beat (ADR-129 非终
        态, the plan path's mirror): draft (or fingerprint-reuse) the
        storyboard, stamp the VERSIONED film state onto the PendingPlan
        (version / params / content digest / execution snapshot / review
        hold / draft token — the dock, start and worker seats only READ
        it), and hand the saved board's FULL fact sheet back to the loop
        (2026-10-18 裁决): the model's ONE next message is the
        presentation; ``finish`` stamps its provenance once that row
        persists. NO plan docks, NO run starts, NO program markdown
        row."""
        # 同回合纠正道 (the plan path's mirror — the flag's init comment
        # carries the forensics): a further design call this turn is a
        # CORRECTION of the standing version — admitted within the cap,
        # never a second begin; past the cap the refusal names the standing
        # version and marks the shortfall (the dock's confirmation law then
        # holds the spend).
        from app.chat.turn_tools import (  # deferred: same layer
            MAX_DESIGN_CORRECTIONS_PER_TURN,
            design_begin_refusal_feedback,
            design_call_record,
            design_correction_cap_refusal,
        )

        correction = self._designed_this_turn is not None
        if correction:
            if self._design_corrections >= MAX_DESIGN_CORRECTIONS_PER_TURN:
                # 台账记账 (定点收尾①): the cap refusal is a FAILED design
                # call — its signature joins the ledger so the dock's
                # unmet_condition hold survives until a matching success.
                entry = design_call_record(params)
                if entry not in self._design_shortfalls:
                    self._design_shortfalls.append(entry)
                return design_correction_cap_refusal(self._designed_this_turn)
            self._design_corrections += 1
        if not correction and self._design_begin_refusal is not None:
            # 入口锁存 (the latch's repeat seat — the plan path's mirror):
            # the begin was already refused this turn; the repeat never
            # touches the database and ends the loop deterministically
            # (TerminalRefusal). The failed call still joins the ledger.
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            return TerminalRefusal(
                "design entry closed: the begin was already refused this "
                "turn (a same-turn retry cannot recover it)"
            )
        db, project = self.db, self.project
        assert project is not None
        # Non-terminal checkpoint law (the plan path's mirror): with an
        # on_checkpoint channel, the framing prose has already been emitted
        # and is deliberately absent from the execute speech. Empty prose
        # here is legal, never a "missing explanation" rejection.
        from app.tools.film.storyboard import (  # deferred: tool seam
            begin_film_draft,
            clear_film_draft_marker,
            film_design_state,
            film_draft_inflight_live,
            film_text_drift_next,
            film_text_source_birth_pin,
            film_subtitles_birth_pin,
            film_verbatim_birth_pin,
            film_voiceover_birth_pin,
            prepare_dock_storyboard,
            read_committed_film_marker,
            resolve_film_revision_base,
            text_source_drift_note,
        )

        # The authorizing message (设计授权消息): the current turn's user
        # row — the direction yes / the design request / the revision words.
        authorized_by = (
            await db.execute(
                select(Message.id)
                .where(
                    Message.conversation_id == self.conversation_id,
                    Message.role == "user",
                )
                .order_by(Message.seq.desc().nulls_last(), Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        stored_pb = project.pending_brief if isinstance(project.pending_brief, dict) else {}
        stored = (
            PendingPlan.model_validate(stored_pb) if stored_pb else None
        )
        # Birth-narrative freeze (the plan path's same law — stored.prompt
        # wins): the approval dock reads this same prompt back, so the
        # design beat's fingerprint IS the dock's.
        birth_prompt = (
            stored.prompt if stored is not None and stored.prompt else None
        ) or self.text
        # 修订基准 (ADR-129, the plan path's mirror): 钉恒胜 — an explicit
        # @output pin names THE film whose board the revision re-enters,
        # beating any live pending draft; an unrecoverable pinned target
        # yields NO base (a fresh draft), never a silent swap. Without a
        # pin: the live pending design wins; after a Start cleared
        # pending_brief the current board recovers from run provenance.
        # A correction's base is fixed BY CONSTRUCTION (the plan path's
        # mirror): the version THIS turn just published — an @output pin
        # never reroutes a same-turn correction onto another film.
        mentioned_output_id = (
            pinned_output_id(self.mentions, None) if not correction else None
        )
        base_is_live_pending = False
        if mentioned_output_id is not None:
            design_base = await resolve_film_revision_base(
                db, project, output_id=UUID(str(mentioned_output_id))
            )
        elif stored is not None and stored.film_storyboard:
            design_base = stored
            base_is_live_pending = True
        else:
            design_base = await resolve_film_revision_base(db, project)
        # The patch path (编辑拍): targeted ops against the resolved base —
        # its own seat, never a director re-design. The capability is
        # deployment-gated (settings.film_edits_enabled — internal-test
        # while the edit journey closes up): with the gate OFF the model
        # was never told about edits (the wire view prunes schema,
        # description, prompt law and read-back hints), and a direct call
        # still refuses here — declaration and enforcement gate together;
        # the compose path is unaffected.
        if params.edits:
            from app.config import settings  # deferred: config leaf

            if not settings.film_edits_enabled:
                # 台账记账 (定点收尾①): the gate-off refusal is a FAILED
                # design call — the requested edits never landed.
                entry = design_call_record(params)
                if entry not in self._design_shortfalls:
                    self._design_shortfalls.append(entry)
                return (
                    "design_storyboard does not accept edits in this "
                    "deployment — no change was made and the current "
                    "version stands untouched. Re-issue the call WITHOUT "
                    "edits: open feedback rides specific_instruction alone."
                )
            return await self._design_storyboard_patch(
                params,
                design_base=design_base,
                stored=stored,
                birth_prompt=birth_prompt,
                authorized_by=authorized_by,
                base_is_live_pending=base_is_live_pending,
                base_is_pinned=mentioned_output_id is not None,
                correction=correction,
            )
        # 并发护栏 BEGIN (the plan path's mirror): the in-flight marker
        # lands COMMITTED before the long draft — Start fails closed while
        # it stands, a concurrent begin is refused (never queued), and the
        # publish below only lands if the committed marker still names THIS
        # draft. No turn-transaction fallback. A CORRECTION never
        # re-begins: the turn's first begin's committed marker still
        # stands and a second side-session NOWAIT would read the turn's
        # OWN row lock — the self-lock.
        if correction:
            draft_id = self._design_draft_id
            assert draft_id is not None  # set by this turn's first begin
        else:
            begin = await begin_film_draft(
                db,
                project,
                base_version=(
                    design_base.film_storyboard_version if design_base else None
                ),
                user_message_id=str(authorized_by) if authorized_by else None,
            )
            if begin.draft_id is None:
                # 台账记账 (定点收尾①): the begin refusal is a FAILED design
                # call — the requested change never landed. The refusal
                # REASON latches (入口锁存): the entry closes for the rest
                # of the turn, so this turn never polls the hold.
                entry = design_call_record(params)
                if entry not in self._design_shortfalls:
                    self._design_shortfalls.append(entry)
                refusal = begin.refusal or "locked"
                self._design_begin_refusal = refusal
                return design_begin_refusal_feedback(refusal)
            draft_id = begin.draft_id
            self._design_draft_id = draft_id
        try:
            # Declared-URL capture (the proposal seats' same absorb law):
            # the design beat DRAFTS from the captured page, so a URL the
            # conversation carries becomes a WEB_PAGE asset BEFORE the
            # draft — committed in its own transaction so the capture
            # worker can claim it while this chat turn stays open (the
            # draft waits for that capture; a flush-only row would deadlock
            # the wait). CaptureBlocked propagates — through the marker
            # cleanup below, like every drafting failure.
            if params.material_urls:
                await create_web_page_assets_committed_from_urls(
                    UUID(str(project.id)), self.user_id, params.material_urls
                )

            # The synthetic launch_film task carries ONLY the design params —
            # the approval dock's real task must repeat them verbatim (the
            # fingerprint's params half), or it steers back here. Voiceover
            # pins EXPLICITLY at birth (默认无配音 — the one seat is
            # film_voiceover_birth_pin: a new film defaults off, a redraft
            # inherits the base version's pinned setting).
            # Text-source fields inherit at redraft (the one seat is
            # film_text_source_birth_pin): an open-feedback redraft that
            # does not re-paste the copy keeps the base version's source —
            # never falls into the website chain.
            _text_pin, _target_pin, _count_pin, _group_pin = film_text_source_birth_pin(
                params.text,
                params.target_seconds,
                params.scene_count,
                params.group_chars,
                (
                    design_base.film_storyboard_params
                    if design_base
                    else None
                ),
                base_present=design_base is not None,
                target_seconds_present="target_seconds" in params.model_fields_set,
                scene_count_present="scene_count" in params.model_fields_set,
                group_chars_present="group_chars" in params.model_fields_set,
            )
            design_params = {
                k: v
                for k, v in {
                    "focus": params.focus,
                    "language": params.language,
                    "voiceover": film_voiceover_birth_pin(
                        params.voiceover,
                        (
                            design_base.film_storyboard_params
                            if design_base
                            else None
                        ),
                        base_present=design_base is not None,
                    ),
                    "subtitles": film_subtitles_birth_pin(
                        params.subtitles,
                        (
                            design_base.film_storyboard_params
                            if design_base
                            else None
                        ),
                        base_present=design_base is not None,
                        base_storyboard=(
                            design_base.film_storyboard if design_base else None
                        ),
                    ),
                    "music_mood": params.music_mood,
                    "aspect": params.aspect,
                    # Text source (ADR-138 §7.6): the copy pins verbatim with
                    # its role — verbatim's birth pin (贴文 ≠ 逐字): an unset
                    # verbatim inherits the base version's pinned mode; only a
                    # first text version reads null as preserve (never a
                    # re-guess from the mere fact text was pasted).
                    "text": _text_pin,
                    "verbatim": film_verbatim_birth_pin(
                        params.verbatim,
                        (
                            design_base.film_storyboard_params
                            if design_base
                            else None
                        ),
                        base_present=design_base is not None,
                        text_present=bool(_text_pin),
                    ),
                    "target_seconds": _target_pin,
                    "scene_count": _count_pin,
                    "group_chars": _group_pin,
                }.items()
                if v is not None
            }
            # 抄录漂移注记 (7276ef13 v3 取证, the plan path's mirror): a
            # verbatim redraft that RE-PASTES a drifted copy publishes (a
            # deliberate copy edit stays legal) with the honest
            # clause-level note riding the observation.
            drift_note = (
                text_source_drift_note(
                    params.text,
                    (design_base.film_storyboard_params or {}).get("text")
                    if design_base
                    else None,
                )
                if design_params.get("verbatim") is True
                and params.text is not None
                else None
            )
            tasks = [{"tool": "launch_film", "params": design_params}]
            # Pinned media (ADR-140 发现面): the @asset selections on the
            # request lead the director's candidate listing — a pick beyond
            # the print cap still reaches its context (tenant scoping is
            # enforced at the listing seat, never by trusting these ids).
            pinned_asset_ids = [
                str(m.id)
                for m in (self.mentions or [])
                if getattr(m, "type", None) == "asset"
            ] or None
            film = await prepare_dock_storyboard(
                db,
                project,
                on_progress=self.on_phase,
                tasks=tasks,
                instruction=birth_prompt,
                fresh_instruction=params.specific_instruction or None,
                cached_storyboard=design_base.film_storyboard if design_base else None,
                cached_fingerprint=design_base.film_storyboard_fingerprint if design_base else None,
                pinned_asset_ids=pinned_asset_ids,
            )
        except BaseException:
            # 并发护栏 step 3: failure/timeout/cancel — capture failures
            # included — clears ONLY this draft's marker (committed side
            # channel; the turn holds no project lock on this path). A
            # CORRECTION's failure never clears: the marker belongs to the
            # turn's first begin and must keep Start failed-closed until
            # the turn commits.
            if not correction:
                await clear_film_draft_marker(db, project, draft_id=draft_id)
            # 台账记账 (定点收尾①): the exception path is a failed design
            # call too — if the turn survives to dock, the hold must stand.
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            raise
        assert film is not None  # the synthetic task always carries launch_film
        # 并发护栏 PUBLISH (step 2): publish only while the COMMITTED marker
        # still names THIS draft on ITS base version AND still LIVE (the
        # patch branch's same liveness half — 定点收尾③ consistency fix).
        # A CORRECTION builds on THIS turn's own (still uncommitted)
        # version, so the committed marker's base_version legitimately
        # names the PRE-turn base — the guard then checks only that the
        # marker still names this turn's draft (a lapsed-budget takeover
        # discards honestly).
        live_marker = await read_committed_film_marker(UUID(str(project.id)))
        marker_ok = (
            isinstance(live_marker, dict)
            and live_marker.get("draft_id") == draft_id
            and film_draft_inflight_live(live_marker)
        )
        if marker_ok and not correction:
            marker_ok = live_marker.get("base_version") == (
                design_base.film_storyboard_version if design_base else None
            )
        if not marker_ok:
            # The discard releases its OWN marker before answering (the
            # clear is draft-scoped — a newer draft's marker is never
            # touched); a leaked marker would block redesigns and Start
            # until the staleness sweep. A CORRECTION's discard never
            # clears (the marker it read is the takeover's or gone). Either
            # path is a FAILED design call: the failure joins the ledger
            # (定点收尾①).
            if not correction:
                await clear_film_draft_marker(db, project, draft_id=draft_id)
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            logger.info(
                "film_draft_publish_superseded",
                project_id=str(project.id),
                draft_id=draft_id,
            )
            return (
                "a newer storyboard design (or a production start) landed "
                "while this draft was in flight — this draft is discarded; "
                "the current version stands. Call design_storyboard again "
                "to revise the CURRENT board."
            )
        version_state = film_design_state(
            design_base,
            film=film,
            design_params=design_params,
            review_hold=params.review_hold,
            authorized_by=str(authorized_by) if authorized_by else None,
        )
        # 未接受文字漂移 (定点收尾②复审, the plan path's mirror — the A→B→
        # 继承 B hole): the drift state rides the VERSION ENVELOPE, computed
        # against the LAST PROVABLY-ACCEPTED baseline — an inherited drifted
        # copy CARRIES the hold; only restore / user-pasted / the dock's
        # explicit confirm releases it.
        if design_params.get("verbatim") is True and design_params.get("text"):
            version_state["film_text_drift"] = film_text_drift_next(
                getattr(design_base, "film_text_drift", None),
                (design_base.film_storyboard_params or {}).get("text")
                if design_base
                else None,
                design_params["text"],
                self.text,
            )
        else:
            version_state["film_text_drift"] = (
                getattr(design_base, "film_text_drift", None)
                if design_base
                else None
            )
        source_pin, exemplar_pin = await self._role_pins_for(tasks)
        from app.editing.service import video_carry_state  # deferred: editing seam
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=stored.intent if stored else None,
            brief=stored.brief if stored else Brief(),
            reasons=stored.reasons if stored else [],
            persona_id=stored.persona_id if stored else None,
            source_asset_id=source_pin,
            exemplar_asset_id=exemplar_pin,
            derived=stored.derived if stored else [],
            plans=stored.plans if stored else [],
            plan_task_map=stored.plan_task_map if stored else None,
            **version_state,
            **video_carry_state(stored),
        ).model_dump(mode="json")
        # 呈现挂号 (2026-10-18 裁决, the plan path's mirror): no program
        # message publishes — the model's ONE next message presents the
        # board, and finish stamps the association once that row persists.
        self._presentation_pending = {
            "version": version_state["film_storyboard_version"]
        }
        self._designed_this_turn = version_state["film_storyboard_version"]
        # 台账不销 (定点收尾复审①, the plan path's mirror): a landed COMPOSE
        # NEVER clears the ledger — 重稿成功不证明原请求落实. The ONE
        # clearing seat is the patch branch's matching-signature success.
        hold_fact = (
            "review hold ON — production waits for the user's explicit request"
            if version_state["film_review_hold"]
            else "review hold off"
        )
        draft_fact = (
            "re-presented unchanged"
            if film.reused
            else "new draft — any earlier film confirmation is void"
        )
        # base 引用协议 step 1 (the read-time mint): the saved version's
        # identity reference rides the observation — targeted edits to THIS
        # version echo it back as base_ref. The mint is part of the gated
        # edit capability: gate OFF = no reference line at all (the model
        # is never invited to a patch the deployment refuses).
        from app.config import settings  # deferred: config leaf

        base_ref_line = ""
        if settings.film_edits_enabled:
            from app.tools.film.edits import (  # deferred: tool seam
                film_base_cut,
                film_version_identity_digest,
            )

            minted_base_ref = film_version_identity_digest(
                FilmStoryboard.model_validate(version_state["film_storyboard"]),
                version_state["film_storyboard_params"] or {},
                version=version_state["film_storyboard_version"],
                cut=film_base_cut(version_state),
            )
            base_ref_line = (
                f"\nThis version's base_ref: {minted_base_ref} — targeted edits "
                "(one scene's view or narration, a reorder, a removal, a music "
                "or voiceover swap) ride design_storyboard's edits with this "
                "reference echoed verbatim (re-read via get_output_spec if "
                "lost); open feedback keeps riding specific_instruction "
                "WITHOUT edits."
            )
        return ToolObservation(
            f"Storyboard version {version_state['film_storyboard_version']} "
            f"designed and saved ({draft_fact}; {hold_fact}; no plan docked, "
            "no run started, and no film has been produced). Your next "
            "message is its ONLY presentation — no system message carries "
            "the board. Present a short intro, the COMPLETE scene table "
            "built from THESE facts verbatim, then the cumulative production "
            "settings and any concrete unresolved items. A storyboard is not "
            "a rendered film: never say production is underway or complete "
            "before a real run says so.\n"
            "SAVED BOARD (execution truth — the times ARE the render "
            "timeline, never recompute them):\n"
            + film.presentation
            + "\nLaw: the next step keys on the CURRENT request's production "
            "intent, not on an older run or approval. With production intent "
            "present, present the full board and continue to propose_tasks "
            "with these design params verbatim; the existing review-hold "
            "release and global confirmation settings govern starting, with "
            "no extra approval question invented. Without production intent, "
            "call answer: an ordinary design/revision asks the ONE direct "
            "question whether to make THIS version, while an explicit "
            "review-only request stops after the full presentation with no "
            "production question. The user's later APPROVAL of the presented "
            "board docks the proposal with the same params and ONE honest "
            "setup line — it never re-designs or re-prints the table. Board "
            "feedback re-enters through design_storyboard's "
            "specific_instruction — the user's change words only, never a "
            "restated direction; an explanation question gets an answer, "
            "never a redraft."
            + base_ref_line
            + (f"\n{drift_note}" if drift_note else "")
        )

    async def _design_storyboard_patch(
        self,
        params: DesignStoryboardArgs,
        *,
        design_base,
        stored,
        birth_prompt: str,
        authorized_by,
        base_is_live_pending: bool,
        base_is_pinned: bool,
        correction: bool = False,
    ) -> str | ToolObservation:
        """The design beat's PATCH branch (the plan path's mirror): targeted
        ops against the resolved base version — applied atomically by the
        SYSTEM (``prepare_film_patch``), validated by the real validator,
        published as a new version with the system-computed change_set. NO
        director call lives here (闸 2: the edit path burns zero
        orchestration), NO silent overwrite of the current version.

        base 引用协议: ``params.base_ref`` is the READ-TIME reference the
        model echoes verbatim — checked against the resolved base BEFORE the
        begin marker (a stale read rejects without churn) and re-checked by
        the apply seat; the publish beat then re-reads the COMMITTED state
        and compares FULL identity (content + canonical params + ordered
        scene ids + version + frozen cut — the same
        ``film_version_identity_digest`` seats), never a version-number or
        content-digest handshake: a base that rode the live pending must
        still find it standing and identical; a provenance-recovered base
        that met no pending at read time tolerates only a byte-identical
        re-committed world (anything else, and any unprovable legacy
        envelope, discards honestly). An explicit @output pin branches from
        THAT version — the live pending's movement is then irrelevant by
        design (永不静默换最新版)."""
        db, project = self.db, self.project
        assert project is not None
        from app.chat.turn_tools import (  # deferred
            design_begin_refusal_feedback,
            design_call_record,
        )
        from app.tools.film.edits import (  # deferred: tool seam
            FilmEditError,
            committed_film_state_identity,
            film_base_cut,
            film_edit_repair_echo,
            film_version_identity_digest,
            prepare_film_patch,
        )
        from app.tools.film.storyboard import (  # deferred: tool seam
            begin_film_draft,
            clear_film_draft_marker,
            film_design_state,
            film_draft_inflight_live,
            film_text_drift_next,
            read_committed_film_state,
        )

        if design_base is None or not getattr(design_base, "film_storyboard", None):
            # 台账记账 (定点收尾①): a FAILED design call — no base exists and
            # the requested edits never landed.
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            return (
                "there is no film storyboard version to edit yet — design one "
                "first (design_storyboard without edits), or @-mention the "
                "film output whose version you mean."
            )
        # Fast stale reject (no marker churn): the reference must name the
        # base AS RESOLVED NOW. A corrupt stored base rejects honestly too.
        try:
            current_ref = film_version_identity_digest(
                FilmStoryboard.model_validate(design_base.film_storyboard),
                design_base.film_storyboard_params or {},
                version=design_base.film_storyboard_version,
                cut=film_base_cut(design_base),
            )
        except (TypeError, ValueError):
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            return (
                "the stored base version no longer parses — re-read the "
                "current version (get_output_spec on the film output) before "
                "editing."
            )
        if params.base_ref != current_ref:
            # 台账记账 (定点收尾①): the stale-base_ref refusal is a FAILED
            # design call — the edits were minted against a moved version.
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            return (
                "the film's current version moved since these edits were "
                "minted — re-read the current version (get_output_spec on the "
                "film output) and re-issue the edits with its base_ref. The "
                "current version stands untouched."
            )
        # 并发护栏 BEGIN (the compose branch's same law): the in-flight
        # marker lands COMMITTED before the patch; Start fails closed while
        # it stands, a concurrent begin is refused, and the publish below
        # lands only while the committed marker still names THIS draft. A
        # CORRECTION never re-begins — the turn's own marker still stands
        # (the plan path's compose branch carries the self-lock forensics).
        if correction:
            draft_id = self._design_draft_id
            assert draft_id is not None  # set by this turn's first begin
        else:
            begin = await begin_film_draft(
                db,
                project,
                base_version=design_base.film_storyboard_version,
                user_message_id=str(authorized_by) if authorized_by else None,
            )
            if begin.draft_id is None:
                # 台账记账 (定点收尾①): the begin refusal is a FAILED design
                # call — the requested change never landed. The refusal
                # REASON latches (入口锁存 — the compose branch's law): the
                # entry closes for the rest of the turn.
                entry = design_call_record(params)
                if entry not in self._design_shortfalls:
                    self._design_shortfalls.append(entry)
                refusal = begin.refusal or "locked"
                self._design_begin_refusal = refusal
                return design_begin_refusal_feedback(refusal)
            draft_id = begin.draft_id
            self._design_draft_id = draft_id
        try:
            prepared = await prepare_film_patch(
                db,
                project,
                base=design_base,
                ops=params.edits,
                base_ref=params.base_ref or "",
                instruction=birth_prompt,
            )
        except FilmEditError as exc:
            # A structured op rejection is LOOP FEEDBACK, not a turn failure:
            # clear only this draft's marker and hand the model the repair
            # echo — the base version stands untouched. A CORRECTION's
            # rejection never clears: the marker belongs to the turn's first
            # begin and keeps Start failed-closed until the turn commits.
            if not correction:
                await clear_film_draft_marker(db, project, draft_id=draft_id)
            # 台账记账 (定点收尾①): the rejected ops never landed — the
            # failure joins the ledger; the repair retry's matching
            # signature is what clears it.
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            logger.info(
                "film_patch_rejected",
                project_id=str(project.id),
                code=exc.code,
                detail=exc.detail[:300],
            )
            return film_edit_repair_echo(exc)
        except BaseException:
            if not correction:
                await clear_film_draft_marker(db, project, draft_id=draft_id)
            # 台账记账 (定点收尾①): the exception path is a failed design
            # call too — if the turn survives to dock, the hold must stand.
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            raise
        # 并发护栏 PUBLISH (base 引用协议 step 4 — the commit-time recheck):
        # the COMMITTED marker must still name THIS draft on ITS base AND
        # still be LIVE (our own staleness = ownership expired by the
        # protocol's own rules — fail closed, never overwrite a takeover's
        # world), and every NON-PINNED base must still BE the committed
        # world — compared by FULL identity (``committed_film_state_identity``
        # vs the read-time reference: content + canonical params + ordered
        # scene ids + version + frozen cut), never a version-number or
        # content-digest handshake. A base that rode the live pending
        # re-proves unconditionally (a vanished pending = a moved world); a
        # provenance-recovered base that met NO pending at read time meets
        # an appeared one here: byte-identical identity = the same version
        # state re-committed (safe to build on), ANYTHING ELSE = a moved
        # world — and an unprovable committed envelope (a legacy row whose
        # board/params/version no longer parse) discards honestly rather
        # than passing on a version number. An explicit @output pin is the
        # ONE exemption (branch semantics — 钉恒胜). The residual
        # check→commit window: the write rides the turn transaction
        # (version + presentation commit atomically — deliberate), so a
        # world moving strictly AFTER this read still lands under our
        # commit; the marker protocol covers it while our marker is live
        # (a concurrent begin is refused, Start fails closed), and the
        # liveness precondition above fails our own publish closed once the
        # design budget lapses — the straddle that remains needs a full
        # concurrent turn nested inside this turn's final seconds after a
        # near-exhausted budget, and is accepted over moving the version
        # write out of the turn's atomicity.
        live_marker, committed_film = await read_committed_film_state(
            UUID(str(project.id))
        )
        superseded = not (
            isinstance(live_marker, dict)
            and live_marker.get("draft_id") == draft_id
            and film_draft_inflight_live(live_marker)
        )
        # A CORRECTION's base is this turn's own (uncommitted) version, so
        # the committed world legitimately reads PRE-turn (the plan path's
        # mirror): only the marker's draft ownership guards the publish —
        # the base_version and committed-identity halves would discard
        # every correction by construction.
        if not correction:
            superseded = superseded or (
                isinstance(live_marker, dict)
                and live_marker.get("base_version")
                != design_base.film_storyboard_version
            )
            if not superseded and not base_is_pinned:
                if committed_film is None:
                    superseded = base_is_live_pending
                elif committed_film_state_identity(committed_film) != current_ref:
                    superseded = True
        if superseded:
            # The discard releases its OWN marker before answering (the
            # clear is draft-scoped: a marker already taken over by a newer
            # draft is never touched) — a leaked marker would block later
            # edits and Start until the staleness sweep. A CORRECTION's
            # discard never clears (the standing marker is the turn's own
            # or the takeover's). Either path is a FAILED design call: the
            # failure joins the ledger (定点收尾①).
            if not correction:
                await clear_film_draft_marker(db, project, draft_id=draft_id)
            entry = design_call_record(params)
            if entry not in self._design_shortfalls:
                self._design_shortfalls.append(entry)
            logger.info(
                "film_patch_publish_superseded",
                project_id=str(project.id),
                draft_id=draft_id,
            )
            return (
                "a newer storyboard design (or a production start) landed "
                "while this edit was in flight — this patch is discarded; "
                "the current version stands. Re-read the current version and "
                "re-issue the edits with its base_ref."
            )
        version_state = film_design_state(
            design_base,
            film=prepared.film,
            design_params=prepared.params,
            review_hold=params.review_hold,
            authorized_by=str(authorized_by) if authorized_by else None,
            created_via="patch",
            change_set=prepared.change_set.model_dump(mode="json"),
            kept_frames=prepared.kept_frames,
            kept_reveal_onsets=prepared.kept_reveal_onsets,
        )
        # 未接受文字漂移 (定点收尾②复审, the plan path's mirror): a
        # structured copy patch CAN create an unproven drift; it carries a
        # standing hold and releases only on the provable paths (baseline
        # restored / the user pasted the standing copy). Exact before/after
        # copy facts ride the patch presentation for review.
        if (prepared.params or {}).get("verbatim") is True and (
            prepared.params or {}
        ).get("text"):
            version_state["film_text_drift"] = film_text_drift_next(
                getattr(design_base, "film_text_drift", None),
                (design_base.film_storyboard_params or {}).get("text"),
                prepared.params["text"],
                self.text,
            )
        else:
            version_state["film_text_drift"] = getattr(
                design_base, "film_text_drift", None
            )
        tasks = [{"tool": "launch_film", "params": prepared.params}]
        source_pin, exemplar_pin = await self._role_pins_for(tasks)
        from app.editing.service import video_carry_state  # deferred: editing seam
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=stored.intent if stored else None,
            brief=stored.brief if stored else Brief(),
            reasons=stored.reasons if stored else [],
            persona_id=stored.persona_id if stored else None,
            source_asset_id=source_pin,
            exemplar_asset_id=exemplar_pin,
            derived=stored.derived if stored else [],
            plans=stored.plans if stored else [],
            plan_task_map=stored.plan_task_map if stored else None,
            **version_state,
            **video_carry_state(stored),
        ).model_dump(mode="json")
        # 呈现挂号 (the compose branch's same seat): the model's ONE next
        # message presents the change_set, finish stamps its provenance.
        self._presentation_pending = {
            "version": version_state["film_storyboard_version"]
        }
        self._designed_this_turn = version_state["film_storyboard_version"]
        # 台账销账 (定点收尾①, the plan path's mirror; 复审再收紧): a
        # landed PATCH removes only the EXACTLY EQUIVALENT record (key AND
        # requested target values) — a different value, a dropped field, or
        # an unrelated change never clears; 「已经呈现」≠ 用户接受.
        _landed = design_call_record(params)
        self._design_shortfalls = [
            e for e in self._design_shortfalls if e != _landed
        ]
        hold_fact = (
            "review hold ON — production waits for the user's explicit request"
            if version_state["film_review_hold"]
            else "review hold off"
        )
        drift_fact = ""
        if isinstance(version_state.get("film_text_drift"), dict):
            drift_fact = (
                "\nCOPY REVIEW REQUIRED: this version still carries "
                "unaccepted wording drift from the last accepted copy. "
                "The exact before/after copy facts in CHANGES show this "
                "patch's actual delta; the full current board below is the "
                "wording to review. Never call it the original unchanged, "
                "and never treat this notice as production authorization."
            )
        return ToolObservation(
            f"Storyboard version {version_state['film_storyboard_version']} "
            f"saved — a PATCH of version {design_base.film_storyboard_version} "
            f"({len(params.edits)} ops applied atomically; {hold_fact}; no "
            "plan docked, no run started, and no new film has been produced). "
            "The previous film remains unchanged. Your next message is its "
            "ONLY presentation — no system message carries the revision. "
            "Say the STORYBOARD is updated, never that a new film is already "
            "being made. Present BOTH the system-computed change summary "
            "(including every exact before/after copy fact) and the COMPLETE "
            "CURRENT SAVED BOARD as a Markdown scene table, followed by the "
            "cumulative production settings and concrete unresolved items. "
            "Use the facts below, not an old table plus an inferred diff; "
            "scene_id, base_ref and digests are internal and never user copy.\n"
            "CHANGES:\n"
            + prepared.change_presentation
            + "\nFULL CURRENT SAVED BOARD (execution truth — keep scene "
            "order, time windows, copy, motion/camera and narration exactly "
            "as given):\n"
            + prepared.film.presentation
            + f"\nEdits against THIS new version carry base_ref "
            f"{prepared.next_base_ref} (echo it verbatim; re-read via "
            "get_output_spec if lost).\n"
            "The next step keys on the CURRENT request, never on an old "
            "run's completion or an older version's approval. If this "
            "message explicitly delegates making THIS revised version "
            "(production_intent=true), present the full facts and continue "
            "to propose_tasks with the same params; do not add a second "
            "approval question, and the existing review-hold, drift, quote "
            "and Start guards still decide execution. Otherwise call "
            "answer, NOT propose_tasks: an ordinary modification ends with "
            "the one question whether to remake this version, while an "
            "explicit review-only request stops after the full presentation "
            "with no production question. Review hold off never creates "
            "production intent; review hold on still requires an explicit "
            "production request. Open feedback on the board still rides "
            "specific_instruction WITHOUT edits; the next targeted change "
            "rides edits again with the new base_ref."
            + drift_fact
        )

    async def _dock_plan_as_question(
        self,
        *,
        tasks: list,
        answer: str,
        specific_instruction: str | None,
        caption_mode: str | None,
        name: str | None,
        source_pin: str | None,
        exemplar_pin: str | None,
        plans: list[dict] | None = None,
        plan_task_map: dict[str, list[int]] | None = None,
        derived: list[dict] | None = None,
        persona_id=None,
        estimate: PlanEstimate | None | object = _ESTIMATE_UNSET,
        production_intent: bool | None = None,
    ) -> str | None:
        """The chat path's ONE plan-docking seat (Phase 4 B2/B3): PendingPlan
        + task_book question + estimate + canonical draft preview (inside
        sync_plan_question) — the caption-replay pattern verbatim; Start
        reads intent.tasks / specific_instruction / caption_mode / pins off
        the stored pending. Sets the turn's outcome to the docked question
        (never a run). Returns None when docked; a STRING is the film
        guardrail's steering observation (the storyboard was never presented
        for this exact chain — the call never docked, the tool loop's repair
        iteration carries the redirect to design_storyboard).

        iter-3 S2 (R6 parity): the exploration dock rides the SAME seat —
        ``plans`` (the decision package's reading layer) + ``plan_task_map``
        (the R20 router substrate) + ``derived`` (the "you'll get" preview)
        + an explicitly resolved ``persona_id`` (the exploration door's
        provenance) are additive kwargs; the router-drafted callers
        (propose_tasks / edit_graph's expansion dock) pass none and keep
        their exact pre-S2 shape (derived=[], no plans, persona preserved
        from the stored pending)."""
        db, project = self.db, self.project
        assert project is not None  # the dock seat is project-bound
        # Resolve the dock's quote BEFORE the intent so the echo tail reads
        # it (ADR-111 §2 — the plan path's present_plan seat's same law):
        # the chat path's dock echo carries the code-composed estimate
        # whisper as its tail — the card row's retirement left no other
        # total-price face here, and the disclosure duty (BILLING §2.1)
        # holds on every dock seat. The tailed answer rides intent.answer,
        # so a stored-echo re-dock replays it single-tailed.
        resolved_estimate = (
            await _safe_task_estimate(db, project, tasks)
            if estimate is _ESTIMATE_UNSET
            else estimate
        )
        # ADR-117 §4: one confirmation-need computation per dock — the
        # echo's held clause (keyed on the stamped reason) reads it, the
        # payload stamp takes it by pass-through below.
        from app.tools.film.storyboard import (
            film_text_drift_held,
        )  # deferred: tool seam

        need = await resolve_confirmation_need(
            db,
            self.user_id,
            resolved_estimate,
            # ADR-139: the dock's birth-turn production request — None
            # (unasserted) reads as ABSENT (the safe side: the dock waits
            # with its Start pill standing, never spends on unproven
            # intent).
            production_intent=production_intent,
            # 7276ef13 ③: a change refused THIS turn holds the auto start.
            unmet_condition=bool(self._design_shortfalls),
            # 定点收尾②复审: the drift hold reads the STANDING VERSION's
            # persisted state (world truth — a rebuilt turn never loses
            # it), never a turn-local flag.
            copy_drift=film_text_drift_held(project.pending_brief),
        )
        # 分镜节拍守卫 + dock 只读当前版本 (the plan path's dock seats'
        # same law — the chat path docks through the SAME seat, ADR-129):
        # the shared resolver first restores the CURRENT presented version's
        # canonical launch_film params (fresh wording is not drift), then
        # validates fingerprint/version/digests/token. A miss steers back to
        # design_storyboard. The dock NEVER redrafts — a non-empty
        # specific_instruction remains plan feedback only.
        from app.tools.film.storyboard import (  # deferred: tool seam
            resolve_film_dock_state,
        )

        stored_pb = project.pending_brief if isinstance(project.pending_brief, dict) else {}
        stored = (
            PendingPlan.model_validate(stored_pb) if stored_pb else None
        )
        # Birth-prompt freeze (the plan path's same law): the fingerprint
        # keys on the plan's BIRTH narrative, so an unrelated re-dock's new
        # wording never flips the storyboard into a blind redraft.
        birth_prompt = (
            stored.prompt if stored is not None and stored.prompt else None
        ) or self.text
        film_resolution = resolve_film_dock_state(stored, tasks, birth_prompt)
        if isinstance(film_resolution, str):
            return film_resolution
        film_state = film_resolution.state
        answer = (
            (answer or "")
            # 展示一座 (ADR-129): the storyboard markdown's presentation seat
            # is the design beat's own message — a dock echo NEVER
            # re-embeds it.
            + _estimate_tail(self.text, resolved_estimate, reason=need.reason)
        )
        intent = InferredIntent(
            action="draft",
            tasks=tasks,
            answer=answer,
            specific_instruction=specific_instruction,
            caption_mode=caption_mode,
            name=name,
        )
        preserved_brief = (
            Brief.model_validate(project.pending_brief["brief"])
            if isinstance(project.pending_brief, dict)
            and isinstance(project.pending_brief.get("brief"), dict)
            else Brief()
        )
        from app.editing.service import video_carry_state  # deferred: editing seam
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=intent,
            brief=preserved_brief,
            reasons=await _compute_plan_reasons(db, project, intent),
            persona_id=(
                persona_id
                or (
                    project.pending_brief.get("persona_id")
                    if isinstance(project.pending_brief, dict)
                    else None
                )
            ),
            source_asset_id=source_pin,
            exemplar_asset_id=exemplar_pin,
            derived=derived or [],
            plans=plans or [],
            plan_task_map=plan_task_map,
            **film_state,
            **video_carry_state(stored),
        ).model_dump(mode="json")
        bailed_run_ids = await sync_plan_question(
            db, self.user_id, project, intent, self.text,
            reasons=project.pending_brief["reasons"],
            brief=preserved_brief,
            echo=intent.answer,
            estimate=resolved_estimate,
            derived=derived,
            plans=plans,
            need=need,
            film_draft_token=(
                film_state["film_draft_token"]
                if film_resolution.film_chain
                else None
            ),
            film_storyboard_version=(
                film_state["film_storyboard_version"]
                if film_resolution.film_chain
                else None
            ),
        )
        docked = await latest_pending_question(db, self.conversation_id)
        self.outcome = (docked, None, bailed_run_ids, self.settled_question)
        # ADR-117 §2 auto 开工道 (the plan path's dock seats' same law — the
        # chat path's expansion destination included): a dock that owes no
        # confirm beat starts the work on presentation.
        auto = await _auto_start_docked_plan(
            db,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            project=project,
        )
        if auto is not None:
            _answered_q, auto_run_id = auto
            self.outcome = (docked, auto_run_id, bailed_run_ids, self.settled_question)

    # ---- the exploration seats (iter-3 S2 — R6 parity with the plan path) ----

    async def _emit_milestone(self, key: str, count: int) -> None:
        """Fire one work-session milestone frame (iter-2 ⑥, N-57) at a door
        success — in-session interleave only, never persisted. No-op on the
        one-shot path."""
        if self.on_activity is not None:
            await self.on_activity(key, count)

    async def _emit_candidates(self, payload: dict) -> None:
        """Candidate Surface 信道 (Workspace 合同 v4.2 C8-c, 2026-09-26):
        the candidate card's payload rides its OWN SSE frame
        (``assistant.candidates``) at the door's success — the milestone's
        count-only whitelist never carries members. The SSE route ALSO
        collects every emitted payload and persists them as ONE
        ``candidates_log`` message row at turn settle (the activity_log
        precedent), so a refresh rebuilds the surface from the archive —
        数据链全程消息载, no endpoint. No-op on the one-shot path."""
        if self.on_candidates is not None:
            await self.on_candidates(payload)

    @staticmethod
    def _candidate_set_payload(node: ExplorationRow) -> dict:
        """The ``set`` event: the persisted spec IS the authority (an
        idempotent replay re-emits the stored members, never the request's)."""
        spec = node.spec or {}
        members = []
        for m in spec.get("members") or []:
            if not isinstance(m, dict):
                continue
            members.append(
                {
                    "start": m.get("start"),
                    "end": m.get("end"),
                    "excerpt": str(m.get("excerpt") or ""),
                    "speaker": m.get("speaker") or None,
                }
            )
        return {
            "kind": "set",
            "candidate_set_id": str(node.id),
            "topic": str(spec.get("topic") or ""),
            "asset_id": str(spec.get("asset_id") or ""),
            "members": members,
        }

    async def _selection_payloads(self, rows: list[ExplorationRow]) -> list[dict]:
        """The ``selection`` event(s) after a selects door success: per
        touched candidate set, the set's FULL current selection (sorted
        ordinals-as-addresses, 0-based member indexes) — the client REPLACES,
        never unions, so a revise re-point drops the old pick by
        construction."""
        by_journey: dict[UUID, set[str]] = {}
        for n in rows:
            spec = n.spec or {}
            set_id = spec.get("candidate_set_id")
            if set_id:
                by_journey.setdefault(UUID(str(n.journey_id)), set()).add(
                    str(set_id)
                )
        events = []
        for journey_id, set_ids in by_journey.items():
            selects, _candidate_sets = await read_journey_evidence(
                self.db, UUID(str(self.project.id)), journey_id
            )
            for set_id in sorted(set_ids):
                picked: set[int] = set()
                for s in selects:
                    sspec = s.spec or {}
                    if str(sspec.get("candidate_set_id")) != set_id:
                        continue
                    idx = sspec.get("member_index")
                    if isinstance(idx, int):
                        picked.add(idx)
                events.append(
                    {
                        "kind": "selection",
                        "candidate_set_id": set_id,
                        "selected": sorted(picked),
                    }
                )
        return events

    async def _resolve_persona(self) -> Persona | None:
        """The chat path's persona resolution for exploration births (the
        plan path's chain minus request/stored — a post-run turn has
        neither): the project's mounted persona, else the user's default."""
        project = self.project
        persona: Persona | None = None
        if project is not None and project.persona_id:
            persona = (
                await self.db.execute(
                    select(Persona).where(Persona.id == project.persona_id)
                )
            ).scalar_one_or_none()
        if persona is None:
            persona = await resolve_default_persona(self.db, self.user_id)
        return persona

    async def _explore(
        self, name: str, params, prose: str
    ) -> str | None | ToolObservation:
        """The discovery chain's chat-path dispatch (iter-3 S2, R6 parity —
        a post-run '再挑两条' opens a NEW journey on the SAME chain law):
        candidates/selects ride back as observations (NON-terminal, the
        loop iterates; the observation builders are the plan path's ONE
        wording); propose_plans / revise_plan are TERMINAL — landing (or
        re-landing) the plans docks the decision package through THIS
        path's dock seat, which IS the paid-boundary stop (R15)."""
        if self.project is None:
            # A project-less defensive turn has no canvas to land on — an
            # honest boundary, never a crash.
            return f"{name}: this conversation has no project to explore."
        if name == "propose_candidates":
            assert isinstance(params, ProposeCandidatesArgs)
            try:
                node = await propose_candidates(
                    self.db,
                    self.project,
                    asset_id=params.asset_id,
                    topic=params.topic,
                    members=params.members,
                    goal_text=params.goal or None,
                    journey_id=params.journey_id,
                )
            except ExplorationRejected as e:
                return f"The door rejected the proposal: {e}"
            await self._emit_milestone(
                "chat.explore.candidatesReady", len(params.members)
            )
            await self._emit_candidates(self._candidate_set_payload(node))
            return ToolObservation(
                text=candidates_observation(
                    node, topic=params.topic, member_count=len(params.members)
                )
            )
        if name == "propose_selects":
            assert isinstance(params, ProposeSelectsArgs)
            try:
                born = await propose_selects(
                    self.db,
                    self.project,
                    candidate_set_id=params.candidate_set_id,
                    selects=[s.model_dump() for s in params.selects],
                )
            except ExplorationRejected as e:
                return f"The door rejected the proposal: {e}"
            await self._emit_milestone("chat.explore.selectsReady", len(born))
            for event in await self._selection_payloads(born):
                await self._emit_candidates(event)
            return ToolObservation(text=await self._selects_text(born))
        if name == "propose_plans":
            assert isinstance(params, ProposePlansArgs)
            return await self._propose_plans(params, prose)
        if name == "revise_selects":
            assert isinstance(params, ReviseSelectsArgs)
            return await self._revise_selects(params, prose)
        if name == "revise_plan":
            assert isinstance(params, RevisePlanArgs)
            return await self._revise_plan(params, prose)
        return f"unknown exploration tool {name!r}"  # unreachable — gated above

    async def _propose_plans(self, params: ProposePlansArgs, prose: str) -> str | None:
        """plans → the decision package docks (iter-3 S2, R6 parity). The
        compile law lives in ``exploration_compile`` (ONE seat, shared with
        the plan path — the double door: pre-flight compile rejects with
        zero writes, then the door births); the dock rides this path's ONE
        plan-docking seat with the package's three faces (plans reading
        layer + compiled task evidence + the quote), so Start reads
        intent.tasks / plans / plan_task_map off the stored pending exactly
        like a plan-path dock (ONE authorization seat)."""
        db, project = self.db, self.project
        assert project is not None  # _explore gates project-less turns
        persona = await self._resolve_persona()
        package = await compile_plans_package(
            db,
            project,
            params.plans,
            persona_id=UUID(str(persona.id)) if persona is not None else None,
        )
        if isinstance(package, str):
            return package
        compiled = package.tasks
        await self._emit_milestone("chat.explore.plansReady", len(package.plans))

        # Caption form for quote cards (same derive law as the plan path):
        # named on a quotes output → stamped onto the intent; unnamed = the
        # runtime default, never invented.
        caption_mode = next(
            (
                o.caption_mode
                for p in params.plans
                for o in p.outputs
                if o.kind == "quotes" and o.caption_mode
            ),
            None,
        )
        source_pin, exemplar_pin = await self._role_pins_for(compiled)
        from app.pipeline.orchestrator import derive_plan_preview  # deferred

        try:
            derived = await derive_plan_preview(db, project, compiled)
        except (ToolRejected, ValueError):
            derived = []
        # The dock's quote, computed once here so sync_plan_question never
        # recomputes it.
        task_estimate = await _safe_task_estimate(db, project, compiled)
        return await self._dock_plan_as_question(
            tasks=compiled,
            answer=prose,
            specific_instruction=None,
            caption_mode=caption_mode,
            name=params.name or None,
            source_pin=source_pin,
            exemplar_pin=exemplar_pin,
            plans=decision_package_plans(package.plans),
            plan_task_map=package.plan_task_map,
            derived=derived,
            persona_id=UUID(str(persona.id)) if persona is not None else None,
            estimate=task_estimate,
            production_intent=params.production_intent,
        )

    async def _revise_plan(self, params: RevisePlanArgs, prose: str) -> str | None:
        """revise_plan → the door revises the row in place → the WHOLE
        journey re-compiles → the decision package re-docks through the
        SAME seat (iter-3 S2; 恒重确认 R15: every plan-level revision
        re-confirms — zero autonomy; 决策包可编辑律: the re-dock lands on
        the SAME confirmation seat, never a new ritual — sync_plan_question
        supersedes the still-open task_book row). The revised row lands
        even when the recompile then rejects (draft with issues re-stamped
        = the canvas's honest surface); the rejection rides back as the
        loop echo and the LLM repairs the PLAN, never the chain. The dock
        tail lives in ``_redock_journey_package`` (iter-3 S4 — ONE seat,
        shared with revise_selects)."""
        db, project = self.db, self.project
        assert project is not None  # _explore gates project-less turns
        try:
            revised = await revise_plan(
                db,
                project,
                plan_id=params.plan_id,
                title=params.title or None,
                outputs=[o.model_dump() for o in params.outputs],
            )
        except ExplorationRejected as e:
            return f"The door rejected the revision: {e}"
        package = await recompile_journey_package(
            db, project, UUID(str(revised.journey_id))
        )
        if isinstance(package, str):
            return package
        return await self._redock_journey_package(
            package, prose, production_intent=params.production_intent
        )

    async def _redock_journey_package(
        self, package, prose: str, production_intent: bool | None = None
    ) -> str | None:
        """The chat path's re-dock tail (决策包可编辑律 — the SAME
        confirmation seat, never a new ritual; iter-3 S4 — ONE seat shared
        by revise_plan's whole-journey recompile and revise_selects' docked
        re-quote / post-run mini package): the package's name survives from
        the stored pending intent; caption_mode re-derives from the current
        rows, inheriting the stored answer when unnamed (同一律); the dock
        rides this path's ONE plan-docking seat."""
        db, project = self.db, self.project
        assert project is not None  # _explore gates project-less turns
        await self._emit_milestone("chat.explore.plansReady", len(package.plans))

        stored_intent = (
            project.pending_brief.get("intent")
            if isinstance(project.pending_brief, dict)
            and isinstance(project.pending_brief.get("intent"), dict)
            else {}
        )
        caption_mode = next(
            (
                o.get("caption_mode")
                for row in package.plans
                for o in (row.spec or {}).get("outputs") or []
                if o.get("kind") == "quotes" and o.get("caption_mode")
            ),
            None,
        ) or stored_intent.get("caption_mode")
        source_pin, exemplar_pin = await self._role_pins_for(package.tasks)
        from app.pipeline.orchestrator import derive_plan_preview  # deferred

        try:
            derived = await derive_plan_preview(db, project, package.tasks)
        except (ToolRejected, ValueError):
            derived = []
        persona = await self._resolve_persona()
        task_estimate = await _safe_task_estimate(db, project, package.tasks)
        return await self._dock_plan_as_question(
            tasks=package.tasks,
            answer=prose,
            specific_instruction=None,
            caption_mode=caption_mode,
            name=stored_intent.get("name") or None,
            source_pin=source_pin,
            exemplar_pin=exemplar_pin,
            plans=decision_package_plans(package.plans),
            plan_task_map=package.plan_task_map,
            derived=derived,
            persona_id=UUID(str(persona.id)) if persona is not None else None,
            estimate=task_estimate,
            production_intent=production_intent,
        )

    async def _revise_selects(self, params: ReviseSelectsArgs, prose: str) -> str | None:
        """revise_selects → the door re-points the pick → the three money
        states (iter-3 S4, N-58 / 决策包可编辑律):

        - PRE-DOCK (no plan rides the pick yet): the door revision alone,
          zero ceremony — the prose IS the one-line acknowledgment, nothing
          docks (the plans follow at THEIR birth: the compile dereferences
          the live select).
        - DOCKED (live riding plans): the whole-journey recompile re-docks
          through the SAME confirmation seat (``_redock_journey_package``).
        - POST-RUN (settled riding plans): the riding compiled plans
          supersede (E3 继任 — the spec carries over verbatim: the swap
          changes the SOURCE, never the deliverables), the live riding rows
          compile as the MINI package (只含变化) and re-dock for
          re-confirmation.
        """
        db, project = self.db, self.project
        assert project is not None  # _explore gates project-less turns
        try:
            revised = await revise_selects(
                db, project, selects=[s.model_dump() for s in params.selects]
            )
        except ExplorationRejected as e:
            return f"The door rejected the revision: {e}"
        # C8-c: the re-pointed pick repaints the candidate surface's
        # selection highlight in EVERY phase (pre-dock included — the card
        # is the selection state's one seat).
        for event in await self._selection_payloads(revised):
            await self._emit_candidates(event)
        journey_id = UUID(str(revised[0].journey_id))
        revised_ids = {str(n.id) for n in revised}
        riding = [
            p
            for p in await read_journey_plan_rows(db, project.id, journey_id)
            if (p.spec or {}).get("select_id") in revised_ids
        ]
        phase = select_revision_phase([p.state for p in riding])
        if phase == PHASE_PRE_DOCK:
            # 零仪式 + 一句确认叙事: the prose IS the acknowledgment; empty
            # prose falls to the code-composed fact line (打字机律牙② — the
            # beat never lands empty).
            content = prose.strip() or self._select_swap_note(revised)
            assistant_message = await _create_message(
                db,
                self.conversation_id,
                "assistant",
                content,
            )
            self.outcome = (assistant_message, None, [], self.settled_question)
            return None
        if phase == PHASE_DOCKED:
            package = await recompile_journey_package(db, project, journey_id)
        else:
            try:
                for p in riding:
                    if p.state == "compiled":
                        await supersede_plan(db, project, plan_id=p.id)
            except ExplorationRejected as e:
                return f"The door rejected the revision: {e}"
            live_riding = [
                p
                for p in await read_journey_plans(db, UUID(str(project.id)), journey_id)
                if (p.spec or {}).get("select_id") in revised_ids
            ]
            if not live_riding:
                return (
                    "the pick swapped, but no live plan rides it — nothing "
                    "to re-confirm. Tell the user the swap is on the canvas."
                )
            package = await compile_plan_rows_package(
                db, project, journey_id, live_riding
            )
        if isinstance(package, str):
            return package
        return await self._redock_journey_package(
            package, prose, production_intent=params.production_intent
        )

    def _select_swap_note(self, revised) -> str:
        """The pre-dock swap's empty-prose floor (code-composed fact line,
        the reminder-tail precedent — 世界自证, never the LLM's voice): the
        new picks' own verdicts, bounded."""
        labels = [
            str((n.spec or {}).get("verdict") or "").strip() for n in revised
        ]
        labels = [label for label in labels if label]
        shown = ", ".join(labels[:3]) + (" …" if len(labels) > 3 else "")
        if _prefers_zh(self.text):
            return f"已换成新选段：{shown}。"
        return f"Swapped the pick: {shown}."

    async def _selects_text(self, born) -> str:
        """The selects observation + the exemplar tail (iter-3 S6, E5 —
        Memory 窄切 ③): the project's LAST other journey rides as one fact
        line so 「照上次的样子」 grounds on a real reference. Reference only
        — exemplar facts are NEVER silently applied as defaults."""
        text = selects_observation(born)
        exemplars = await read_journey_summaries(
            self.db,
            self.project.id,
            cap=1,
            exclude_journey_id=UUID(str(born[0].journey_id)),
        )
        if exemplars:
            text += (
                "\nLast time (reference only — reuse only if the user asks): "
                + journey_summary_line(exemplars[0])
            )
        return text

    async def _edit_graph(self, params: EditGraphArgs, prose: str) -> str | None:
        """wiring → 修订 = edit_prompt(node) + run({node} ∪ downstream)
        (ADR-057 K4). The dispatch law lives in ``_run_wiring_proposal``
        (ONE seat — iter-3 S3's revise_output rides the same machinery with
        code-assembled ops); the door's own rejections ARE the loop's
        feedback."""
        proposal = WiringProposal(
            ops=params.ops,
            summary=prose,
            name=params.name,
            production_intent=params.production_intent,
        )
        return await self._run_wiring_proposal(proposal, prose)

    async def _run_wiring_proposal(
        self,
        proposal: WiringProposal,
        prose: str,
        *,
        content_note: str | None = None,
    ) -> str | None:
        """The wiring revision's ONE dispatch seat (edit_graph's own path +
        iter-3 S3 revise_output's code-assembled ops), gated by the
        Deterministic Scope Classifier (ADR-087 §4 + D4, Phase 4 B2): the
        ops land through the graph's ONLY write door inside a savepoint,
        then the door's RESULTING paid execution scope is adjudicated
        against the pre-op run-born graph —

        - ``continuation`` (provably approved scope): the run births
          autonomously through the ONLY run birthplace (Frozen Rule 5),
          exactly as before;
        - ``expansion`` / ``unproven`` (new paid work, or scope provable
          neither way): the savepoint rolls the door's mutation back and
          the translated chain docks as a PendingPlan + task_book question
          (Rule 6/10) through the SAME machinery the plan path / the
          caption replay use — estimate, draft-graph preview with
          canonical fill keys, Start filling in place. A bail restores the
          graph exactly, and an LLM add_node spec missing fill_key can
          never twin a node at Start.

        ``content_note`` (iter-3 S3): a deterministic disclosure line the
        CODE appends to the turn's landing text (continuation: the assistant
        message; dock: the package's answer) — the reminder-tail precedent
        (世界自证: a partial cover says what it skipped, never silent)."""
        db, project = self.db, self.project
        from app.chat.turn_tools import film_wiring_guard
        from app.pipeline.graph_store import WiringRejected, apply_wiring_ops
        from app.pipeline.graph_revise import tasks_for_graph_nodes
        from app.pipeline.scope_classifier import (
            CONTINUATION,
            classify_graph_scope,
            load_graph_facts,
        )
        from app.models.tables import GraphNode

        async def _dispatch(p: WiringProposal) -> UUID | None:
            """Returns the born run's id, or None when the turn lands as a
            dock (an expansion / unproven scope ALWAYS docks — the ask
            regimes wait for the user's confirmation there; the auto
            regime's presentation-time start fires off the dock itself,
            ADR-117 §2 — never a silent direct start either way) or as a
            pure graph edit with nothing to execute."""
            if project is None or not p.ops:
                raise WiringRejected("wiring: no ops to apply")
            project_id = UUID(str(project.id))
            # The approved-scope baseline (Batch 1 preflight ①): the pre-op
            # run-born graph. The classifier never sees ops — it compares
            # plain facts gathered before and after the door (D4).
            pre_nodes, pre_edges = await load_graph_facts(db, project_id)
            film_guard = film_wiring_guard(ops=p.ops, pre_nodes=pre_nodes)
            if film_guard is not None:
                raise WiringRejected(film_guard)
            # The dock's quote — computed on the dock branch so
            # sync_plan_question never recomputes it.
            estimate: PlanEstimate | None = None
            nested = await db.begin_nested()
            try:
                delta = await apply_wiring_ops(db, project_id, p.ops)
                if not delta.run_nodes:
                    # A pure graph edit with no run (e.g. a delete) lands
                    # as-is — no paid execution was requested.
                    await nested.commit()
                    return None
                run_nodes = list(
                    (
                        await db.execute(
                            select(GraphNode).where(GraphNode.id.in_(delta.run_nodes))
                        )
                    )
                    .scalars()
                    .all()
                )
                by_id = {str(n.id): n for n in run_nodes}
                ordered = [by_id[str(nid)] for nid in delta.run_nodes if str(nid) in by_id]
                tasks = tasks_for_graph_nodes(ordered)
                if not tasks:
                    raise WiringRejected("run: the resolved subgraph has nothing executable")
                film_guard = film_wiring_guard(tasks=tasks)
                if film_guard is not None:
                    raise WiringRejected(film_guard)
                post_nodes, post_edges = await load_graph_facts(db, project_id)
                verdict = classify_graph_scope(
                    pre_nodes=pre_nodes,
                    pre_edges=pre_edges,
                    post_nodes=post_nodes,
                    post_edges=post_edges,
                    run_node_ids=tuple(str(nid) for nid in delta.run_nodes),
                )
                if verdict.decision == CONTINUATION:
                    await nested.commit()
                else:
                    # An expansion / unproven scope ALWAYS docks — never a
                    # silent direct start (ask regimes: the dock waits for
                    # the user's confirmation; auto regime: the presentation
                    # fires the start off the dock, ADR-117 §2). Roll the
                    # door's mutation back — the dock's own draft stamp
                    # (inside sync_plan_question) previews the plan with
                    # canonical fill keys instead.
                    estimate = await _safe_task_estimate(db, project, tasks)
                    await nested.rollback()
            except BaseException:
                if nested.is_active:
                    await nested.rollback()
                raise
            # The edited programs pin the run's instruction (the writers'
            # GenerationContext.instruction steers the rewrite); the
            # summary-only fallback keeps the run's plan honest.
            instruction = "\n".join(
                str(op.get("prompt")) for op in p.ops
                if op.get("op") == "edit_prompt" and op.get("prompt")
            )
            if verdict.decision == CONTINUATION:
                # 判词④ pins inherit on a revision run too (the conversation's
                # resident state) — a remix revision keeps honoring the roles.
                source_pin, exemplar_pin = await self._role_pins_for(tasks)
                return await _create_run_from_tasks(
                    db, project, tasks, p.summary, instruction=instruction or None,
                    source_asset_id=source_pin, exemplar_asset_id=exemplar_pin,
                    name=p.name or None,
                )
            # Expansion / unproven → Confirmation Dock (Rule 6/10): the
            # translated chain docks through the ONE shared seat (Start
            # reads intent.tasks / specific_instruction / pins off the
            # stored pending). iter-3 S3: this is also revise_output's MINI
            # decision package (the changed subgraph + the differential
            # quote — the dock's estimate reads only these tasks).
            source_pin, exemplar_pin = await self._role_pins_for(tasks)
            return await self._dock_plan_as_question(
                tasks=tasks,
                answer=(p.summary or "") + (content_note or ""),
                specific_instruction=instruction or None,
                caption_mode=None,
                name=p.name or None,
                source_pin=source_pin,
                exemplar_pin=exemplar_pin,
                estimate=estimate,
                production_intent=p.production_intent,
            )

        try:
            run_id = await _dispatch(proposal)
        except (WiringRejected, ToolRejected, ValueError) as e:
            return str(e)
        if self.outcome is not None:
            # The dock path set the outcome inside _dispatch — the docked
            # task_book question IS the turn's assistant message; no run,
            # no duplicate prose line on top.
            return None
        assistant_message = await _create_message(
            db, self.conversation_id, "assistant",
            (prose or "") + (content_note or ""),
            workflow_run_id=run_id,
            intent=proposal.model_dump(mode="json"),
        )
        self.outcome = (assistant_message, run_id, [], self.settled_question)
        return None

    async def _retry_upload(self, params: RetryUploadArgs, prose: str) -> str | None:
        """retry_upload → reopen only the failed render/upload stage.

        This is recovery inside an already authorized run: no proposal, no
        new paid work, no new run. The Output queue performs the upload after
        this chat transaction commits.
        """
        if not prose.strip():
            return (
                "an empty recovery message says nothing — tell the user the "
                "upload is being retried, then call retry_upload."
            )
        from app.pipeline.rendering import (  # deferred: chat → pipeline leaf
            queue_upload_retry,
            resolve_upload_retry,
        )

        output_id = pinned_output_id(
            self.mentions,
            str(params.output_id) if params.output_id is not None else None,
        )
        target = await resolve_upload_retry(
            self.db,
            self.project,
            output_id=UUID(output_id) if output_id is not None else None,
        )
        if isinstance(target, str):
            return target
        run_id = await queue_upload_retry(self.db, self.project, target)
        if isinstance(run_id, str):
            return run_id
        assistant_message = await _create_message(
            self.db,
            self.conversation_id,
            "assistant",
            prose,
            workflow_run_id=run_id,
        )
        self.outcome = (assistant_message, run_id, [], self.settled_question)
        return None

    # ---- revise_output (iter-3 S3, N-58 — R19 修订二分律的 craft 半边) --------

    async def _latest_confirmed_scope(self, project: Project) -> dict | None:
        """The R20 router's substrate: the NEWEST run's confirmed-scope
        snapshot (Start stamps it at the paid boundary). Scan is bounded
        (latest 10 runs); legacy runs carry no snapshot → None → the
        router's honest degrade."""
        runs = list(
            (
                await self.db.execute(
                    select(WorkflowRun)
                    .where(WorkflowRun.project_id == project.id)
                    .order_by(WorkflowRun.created_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
        for r in runs:
            ctx = r.context if isinstance(r.context, dict) else {}
            snapshot = ctx.get("confirmed_scope")
            if isinstance(snapshot, dict):
                return snapshot
        return None

    def _uncovered_note(self, labels: list[str]) -> str:
        """The partial-cover disclosure (code-composed, the reminder-tail
        precedent — 世界自证, never the LLM's voice): names the deterministic
        steps the revision could not touch."""
        shown = ", ".join(labels[:3]) + (" …" if len(labels) > 3 else "")
        if _prefers_zh(self.text):
            return f"\n\n（未改动：{shown}——这些步骤没有文字稿可改；要改它们，说说要调整哪个方案的产出。）"
        return (
            f"\n\n(Not touched: {shown} — those steps have no wording to "
            "revise; to change them, say which plan's deliverables to adjust.)"
        )

    async def _revise_output(self, params: ReviseOutputArgs, prose: str) -> str | None:
        """revise_output → the craft-level revision (E4): the R20 router
        resolves the pointing (plan_ref / @output pin) against the confirmed
        snapshot to the live node set → the prompt-consumer gate assembles
        edit_prompt + run ops in CODE (the LLM never writes wiring) → the
        shared wiring dispatch (savepoint + classifier裁决 consumption —
        continuation runs autonomously, expansion/unproven rolls back and
        docks the MINI decision package through the one dock seat).

        诚实降级三态 (none are silent): no snapshot / unresolvable pointing
        → the router's reason echoes back (the @output fallback ask);
        all-deterministic targets → an echo naming what CAN change; partial
        cover → the editable subset executes + the disclosure line names
        the rest."""
        db, project = self.db, self.project
        if project is None:
            return "nothing to revise yet — this conversation has no project."
        target = params.target
        plan_ref = (target.plan_ref or "").strip()
        output_id = str(target.output_id) if target.output_id else None
        output_id = pinned_output_id(self.mentions, output_id)  # B4: 钉恒胜
        instruction = params.instruction.strip()
        if not plan_ref and not output_id:
            return (
                "revise_output needs its target — relay the user's pointing "
                "(plan_ref) or the @output pin (output_id); if the message "
                "points at nothing definite, call ask_user to clarify which "
                "plan or output they mean."
            )
        if not instruction:
            return (
                "the instruction is empty — restate the user's change ask "
                "in one compact line."
            )
        snapshot = await self._latest_confirmed_scope(project)
        nodes = list(
            (
                await db.execute(
                    select(GraphNode).where(GraphNode.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        route = route_revision(
            snapshot, nodes, plan_ref=plan_ref or None, output_id=output_id
        )
        if route.status == "degrade":
            return (
                f"{route.reason} — never guess the target; if the user can "
                "point at the product, ask (ask_user) with the @output "
                "pin as the way out."
            )
        by_id = {str(n.id): n for n in nodes}
        routed = [by_id[nid] for nid in route.node_ids if nid in by_id]
        craft = assemble_craft_revision(routed, instruction)
        if craft is None:
            labels = [
                str((n.spec or {}).get("summary") or n.type) for n in routed
            ]
            return (
                "the target resolves to deterministic steps only "
                f"({'; '.join(labels)}) — they have no wording program to "
                "revise. What CAN change: a text product's wording (name "
                "that plan/output) or the plan's deliverables themselves "
                "(revise_plan). Tell the user what can be revised and offer "
                "that path — never pretend the revision landed."
            )
        note = self._uncovered_note(list(craft.uncovered)) if craft.uncovered else None
        proposal = WiringProposal(ops=list(craft.ops), summary=prose, name="")
        return await self._run_wiring_proposal(proposal, prose, content_note=note)

    # ---- edit_output (精确编辑迭代 S3, N-59, ADR-090 — 受控终态工具) --------

    async def _edit_output(self, params: EditOutputArgs, prose: str) -> str | None:
        """edit_output → the precise edit (ADR-090): R20 dual-channel target
        resolution → quote→range adjudication (S2 置信谱) → ONE registry op
        journaled through the existing operations door → re-pend + the
        mirror step rebirth (ADR-074② 台账律 — op 写 + re-pend + 镜像 one
        transaction, E4). Every refusal rides the loop as feedback with its
        answerable form; success is terminal with the world-witnessed fact
        echo (展示文案二源律 — the applied op's real numbers, never a
        frozen template)."""
        db, project, text = self.db, self.project, self.text
        if project is None:
            return "nothing to edit yet — this conversation has no project."
        # Final Hardening B1: the verb decodes from WHICH param is filled
        # (schemas.edit_kind_for_params) — the schema has no ``kind`` field,
        # so the LLM can never contradict the pairing law.
        kind = edit_kind_for_params(params.params)
        if not kind:
            return (
                "edit_output takes exactly ONE filled param — quote "
                "(remove_range) / seconds (set_trim) / style "
                "(set_caption_style) / title (set_title); an open-ended "
                "change goes to revise_output, a deliverables change to "
                "revise_plan."
            )
        target = params.target
        plan_ref = (target.plan_ref or "").strip()
        output_id = str(target.output_id) if target.output_id else None
        output_id = pinned_output_id(self.mentions, output_id)  # B4: 钉恒胜
        if not plan_ref and not output_id:
            return (
                "edit_output needs its target — relay the user's pointing "
                "(plan_ref) or the @output pin (output_id); if the message "
                "points at nothing definite, call ask_user to clarify which "
                "clip they mean."
            )

        # Target resolution: the @output pin lands directly; plan_ref rides
        # the R20 snapshot → the plan's nodes → their ACTIVE clip outputs
        # (multiple clips = ambiguity, never a guess — the @ pin is the
        # named way out).
        output: Output | None = None
        if output_id:
            row = await db.get(Output, UUID(output_id))
            if (
                row is None
                or UUID(str(row.project_id)) != UUID(str(project.id))
                or row.type != "clip"
                or row.archived_at is not None
            ):
                return (
                    f"output {output_id} is not an active clip of this "
                    "project — never guess the target; ask the user to pin "
                    "the clip with @."
                )
            output = row
        else:
            snapshot = await self._latest_confirmed_scope(project)
            nodes = list(
                (
                    await db.execute(
                        select(GraphNode).where(GraphNode.project_id == project.id)
                    )
                ).scalars().all()
            )
            route = route_revision(snapshot, nodes, plan_ref=plan_ref)
            if route.status == "degrade":
                return (
                    f"{route.reason} — never guess the target; if the user "
                    "can point at the clip, ask (ask_user) with the @output "
                    "pin as the way out."
                )
            by_id = {str(n.id): n for n in nodes}
            clip_ids = [
                UUID(str(oid))
                for nid in route.node_ids
                if nid in by_id
                for oid in ((by_id[nid].spec or {}).get("output_ids") or [])
            ]
            clips = (
                list(
                    (
                        await db.execute(
                            select(Output).where(
                                Output.id.in_(clip_ids),
                                Output.type == "clip",
                                Output.archived_at.is_(None),
                            )
                        )
                    ).scalars().all()
                )
                if clip_ids
                else []
            )
            if not clips:
                return (
                    "that plan resolves to no active clip — pin the clip "
                    "with @ instead."
                )
            if len(clips) > 1:
                return (
                    f"that plan has {len(clips)} active clips — which one? "
                    "The user can say 'the second' or pin it with @; never "
                    "guess."
                )
            output = clips[0]

        spec = output.render_spec or {}
        if not spec:
            return (
                "that clip has no editable spec — a precise edit needs the "
                "clip's spec; an open-ended change goes to revise_output."
            )

        raw = params.params.model_dump(mode="python")
        span = None
        if kind == "remove_range":
            span = resolve_quote_span(spec.get("caption_track") or [], raw.get("quote"))
        assembled = assemble_edit_op(kind, raw, spec=spec, span=span)
        if isinstance(assembled, EditRefusal):
            return assembled.feedback

        assistant_message = await _create_message(
            db,
            self.conversation_id,
            "assistant",
            prose,
            intent={
                "type": "edit_output",
                "kind": kind,
                "target_output_id": str(output.id),
            },
        )
        try:
            await apply_operations(
                db,
                output.id,
                [assembled],
                source="chat",
                user_id=self.user_id,
                message_id=UUID(str(assistant_message.id)),
                commit=False,  # E4: op 写 + re-pend + 镜像 = one transaction
            )
        except (OpRejected, OpConflict) as e:
            return str(e)  # zero writes — the door's feedback rides the loop
        except HTTPException as e:
            return str(e.detail)

        # Re-pend + mirror rebirth through the ONE seat (ADR-096 §1): the
        # barrier folds over the output's BIRTH run — a terminal run's steps
        # are all done, so the render fires immediately; a live run's barrier
        # waits out any still-pending writers of the row. A legacy row
        # without its birth step re-pends output-driven only (the undo/redo
        # precedent — NULL barrier lifts at once).
        await db.refresh(output)
        step = (
            await db.get(WorkflowStep, output.workflow_step_id)
            if output.workflow_step_id
            else None
        )
        run = await db.get(WorkflowRun, step.run_id) if step is not None else None
        if run is not None:
            from app.pipeline.render_ownership import (  # deferred: heavy
                pend_outputs_for_render,
            )

            await pend_outputs_for_render(db, run, [output])
        else:
            output.render_status = RenderStatus.PENDING
            output.render_claim_token = None
            output.render_error = None
            output.render_attempt = 0  # intent re-pend = new budget

        fact = _edit_fact_echo(kind, assembled, zh=_prefers_zh(text))
        assistant_message.content = (
            f"{prose.rstrip()}\n\n{fact}" if prose.strip() else fact
        )
        await db.commit()
        self.outcome = (assistant_message, None, [], self.settled_question)
        return None

    async def _ask_user(self, params: ChatAskArgs, prose: str) -> str | None:
        """ask → the agent's question docks through the ask_user machinery
        (task_book questions are raised solely by the plan path, never
        here). slot stays None — a post-run question never backfills the
        brief."""
        # 空散文护栏 (answer 裸调用护栏的对称座): an LLM ask without its
        # framing speech is NEVER legitimate (schema's empty-prose tolerance
        # exists for code-composed questions only) — reject it into the
        # repair iteration instead of docking a silent blocking card.
        if not prose.strip():
            return (
                "an ask never docks without its framing speech — speak what "
                "you understood and your lean as your message text, then "
                "call ask_user."
            )
        if not params.question.strip():
            return (
                "empty question — speak the framing as your message text and "
                "pass the ONE bare question, or call another tool."
            )
        # ask 三分解剖: content carries the framing prose (the turn's echo),
        # the bare question rides the payload. 推荐标记 (2026-09-27 一问拍
        # 一体化): the shared validation lives in resolve_recommended_id.
        recommended_id = resolve_recommended_id(params.recommended_id, params.options)
        ask = QuestionProposal(
            prose=prose or "",
            question=params.question,
            options=params.options,
            allow_freeform=params.allow_freeform,
            recommended_id=recommended_id,
            default_path=params.default_path,
        )
        assistant_message, bailed_run_ids = await _dock_question(
            self.db,
            self.conversation_id,
            _ask_content(ask),
            QuestionPayload(
                kind="question",
                question=params.question,
                options=params.options,
                allow_freeform=params.allow_freeform,
                recommended_id=recommended_id,
                default_path=params.default_path,
            ),
            intent=ask.model_dump(mode="json"),
        )
        self.outcome = (
            assistant_message, None, bailed_run_ids, self.settled_question
        )
        return None

    async def _answer(self, params: ChatAnswerArgs, prose: str) -> str | None:
        """answer → a purely informational reply lands as a plain assistant
        message — no task, no run, no docked question (G-4, N-21; the same
        archival shape as a plan-path answer turn)."""
        if not prose.strip():
            return (
                "an empty reply says nothing — speak the answer as your "
                "message text, then call answer."
            )
        assistant_message = await _create_message(
            self.db,
            self.conversation_id,
            "assistant",
            prose,
            intent=AnswerProposal(text=prose).model_dump(mode="json"),
        )
        self.outcome = (assistant_message, None, [], self.settled_question)
        return None

    # ---- the outcome mapping -------------------------------------------------

    async def finish(self, result) -> ProposeTurnOutcome:
        """LoopResult → the caller's 4-tuple + the reminder tail (ADR-053 R2):
        the pre-turn question survived unsettled and unsuperseded (an
        interjection) — the reply ends with the code-composed reminder."""
        if self.outcome is not None:
            assistant_message, run_id, bailed_run_ids, settled = self.outcome
            # 呈现关联 (2026-10-18 裁决, the plan path's mirror): a design
            # beat this turn owes its presentation — the TERMINAL row IS
            # the presentation message; stamp it now that it persisted.
            await self._stamp_presentation(assistant_message)
        else:
            # The degrade/bare paths land their own message — resolve any
            # still-armed queue FIRST so its frames precede the envelope: a
            # clean bare reply flushes (the queued prose IS the reply), a
            # rejection-marked queue drops (every word was rejected speech).
            await self._resolve_deferred()
            if result is not None and result.no_progress_tool is not None:
                assistant_message = await _create_message(
                    self.db,
                    self.conversation_id,
                    "assistant",
                    _design_no_progress_text(
                        self.text,
                        version_saved=self._designed_this_turn is not None,
                    ),
                )
                run_id, bailed_run_ids, settled = None, [], self.settled_question
            elif result is not None and result.ended_by is not None:
                # The deterministic close (begin 锁存, the plan path's
                # mirror): the loop ended on the TerminalRefusal — the
                # model spent its one honest-close chance on a re-entry —
                # so the CODE line speaks the true failure class (a blocked
                # design start, never a capability refusal).
                assistant_message = await _create_message(
                    self.db,
                    self.conversation_id,
                    "assistant",
                    _design_blocked_text(self.text, self._design_begin_refusal),
                )
                run_id, bailed_run_ids, settled = None, [], self.settled_question
            elif result is None or result.exhausted:
                # result None = provider failure (the caller maps LLMError here);
                # exhausted = every call rejected. ask-back is the only failure
                # form (prohibition #7); adjudication exhaustion reads as
                # cannot-do (the retired degrade's honest line) — EXCEPT a
                # latched begin refusal, which speaks the busy/conflict line.
                content = (
                    _design_blocked_text(self.text, self._design_begin_refusal)
                    if (result is not None and self._design_begin_refusal is not None)
                    else _ASK_BACK_TEXT if result is None else _cannot_do_text(self.text)
                )
                if result is not None:
                    logger.info("chat_turn_loop_exhausted", calls=result.calls)
                assistant_message = await _create_message(
                    self.db,
                    self.conversation_id,
                    "assistant",
                    content,
                )
                run_id, bailed_run_ids, settled = None, [], self.settled_question
            else:
                # The bare final reply (no tool called) — the read-tolerant
                # answer floor: the prose IS the reply.
                assistant_message = await _create_message(
                    self.db,
                    self.conversation_id,
                    "assistant",
                    result.prose,
                    intent=AnswerProposal(text=result.prose).model_dump(mode="json"),
                )
                # The bare reply IS the presentation when the model closed
                # a design beat without a further call — same seat.
                await self._stamp_presentation(assistant_message)
                run_id, bailed_run_ids, settled = None, [], self.settled_question
        bailed_run_ids = [*self._bailed_on_skip, *bailed_run_ids]
        if (
            assistant_message is not None
            and self.pending_judgable
            and self.pending is not None
            and assistant_message.question is None
        ):
            still_open = await latest_pending_question(self.db, self.conversation_id)
            if still_open is not None and still_open.id == self.pending.id:
                assistant_message.content = (
                    assistant_message.content or ""
                ) + _reminder_tail(
                    self.text,
                    _bare_question(self.pending),
                    (self.pending.question or {}).get("default_path"),
                )
        return assistant_message, run_id, bailed_run_ids, settled


async def run_propose_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation,
    project: Project | None,
    text: str,
    mentions: list[ChatMention],
    recent: list[Message],
    suggestion_ref: SuggestionRef | None = None,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
) -> ProposeTurnOutcome:
    """The chat path's turn: assemble → the bounded tool loop → the outcome
    mapping. Provider failure keeps its retired posture: the ask-back line is
    the only failure form (prohibition #7) — EXCEPT the tier gate (ADR-077
    判词④), which fails LOUD: a tools-blind client is a deployment error,
    never the ask-back line. ``on_row_append`` is the generic persisted-row
    channel (currently unused by this path — the design beat's
    program-markdown publication retired with the 2026-10-18 裁决)."""
    turn = ChatTurn(db, user_id, conversation, project, text, on_phase=on_phase,
                    on_activity=on_activity, on_candidates=on_candidates,
                    on_row_append=on_row_append)
    await turn.assemble(mentions, recent, suggestion_ref)
    # 言语提交协议武装 (speech-commit protocol, ADR-099 §7, the plan path's
    # mirror): on the SSE path every turn arms the terminal buffer —
    # iteration 0 is the only streaming iteration, so its prose / preview
    # frames are exactly the speech a terminal rejection would retract. The
    # buffer holds delta + tool_ready ONLY (三通道分家): on_tool_call stays
    # LIVE — it feeds the Activity projector's name_known (the read/repair
    # work evidence + G1's cancelled-frame rejection forensics ride their
    # own undeferred channel) and the phase-clear is liveness chrome, never
    # adjudication-dependent speech. The rejection seat is the wrapped
    # on_loop_event (any ToolRejected retracts the stale queue at once;
    # RETRY re-arms by construction); the checkpoint channel flushes the
    # queue FIRST, then streams live — the buffer stays armed through it.
    if on_delta is not None:
        deferred = DeferredFrames({"delta": on_delta, "tool_ready": on_tool_ready})
        turn.deferred = deferred
        on_delta = deferred.wrap("delta")
        on_tool_ready = deferred.wrap("tool_ready")
        base_on_loop_event = on_loop_event

        async def on_loop_event_with_retract(event) -> None:
            if isinstance(event, LoopToolRejected):
                deferred.retract()
            if base_on_loop_event is not None:
                await base_on_loop_event(event)

        on_loop_event = on_loop_event_with_retract
        base_on_checkpoint = (
            _checkpoint_callback(db, turn.conversation_id, on_checkpoint)
            if turn.project is not None
            else None
        )

        async def on_checkpoint_after_flush(text: str) -> None:
            if deferred.armed:
                await deferred.flush()
            if base_on_checkpoint is not None:
                await base_on_checkpoint(text)

        checkpoint_hook = on_checkpoint_after_flush
    else:
        # ADR-085: the checkpoint channel (persist + SSE forward) — a
        # project-less defensive turn has no conversation to persist into,
        # so the channel stays closed there.
        checkpoint_hook = (
            _checkpoint_callback(db, turn.conversation_id, on_checkpoint)
            if turn.project is not None
            else None
        )
    try:
        result = await chat_intent_agent.call_loop(
            turn.execute,
            message=(
                f"{text}\n{turn.suggestion_note}"
                if turn.suggestion_note
                else text
            ),
            context=turn.context,
            on_delta=on_delta,
            on_reasoning=on_reasoning,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_loop_event=on_loop_event,
            on_checkpoint=checkpoint_hook,
            should_stop_rejection=film_rejection_stop,
        )
    except LLMError as exc:
        if (exc.user_key or "").startswith("film_storyboard_"):
            raise
        capabilities = getattr(chat_intent_agent.client, "capabilities", None)
        if capabilities is None or not capabilities.supports_native_tools:
            raise  # the tier gate fails loud, never the ask-back line
        result = None
    return await turn.finish(result)


__all__ = ["run_propose_turn", "ChatTurn", "ProposeTurnOutcome"]
