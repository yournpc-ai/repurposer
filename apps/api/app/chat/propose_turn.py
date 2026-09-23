"""The chat path's tool-loop runner (ADR-077 判词② — T2a 内核半边).

The retired ``_propose_turn`` dispatch, re-homed: the chat intent
agent closes its turn with ONE terminal tool call — the five proposal
states' mechanical translation (task_list → ``propose_tasks``, edit_ops →
``apply_edit_ops``, wiring → ``edit_graph``, ask → ``ask_user``, answer →
``answer``). The write doors never moved:

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
- ``apply_edit_ops`` still goes through the operations registry's
  ``apply_operations`` with message lineage;
- every adjudication rejection (registry / wiring door / transform targets)
  IS the loop's feedback — the retired funnel repair round's seat, one
  bounded iteration each; a rejection writes nothing.

插话判定结算 (ADR-053 R2) rides the accepted call's ``pending_disposition``
seat — judged settlement is code's (a rejected call never settles). A judged
answer on a parked interrupt wakes its run and the tool's own dispatch is
skipped (the wake IS the continuation, unchanged).

Storage shapes preserved: message.intent still carries the proposal dumps
(TaskListProposal / EditOpsProposal / WiringProposal / QuestionProposal /
AnswerProposal, built here from the accepted call's params plus the turn's
prose), and the caption-mode stash stays a TaskListProposal dump.

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
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.context import build_context
from app.agents.tool_loop import ToolObservation
from app.chat.exploration_compile import (
    compile_plans_package,
    recompile_journey_package,
)
from app.chat.exploration_tools import (
    EXPLORATION_TOOLS,
    ProposeCandidatesArgs,
    ProposePlansArgs,
    ProposeSelectsArgs,
    RevisePlanArgs,
    candidates_observation,
    selects_observation,
)
from app.chat.intent import chat_intent_agent
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.service import (
    _ASK_BACK_TEXT,
    _ask_content,
    _bare_question,
    _build_caption_mode_question,
    _cannot_do_text,
    _caption_choice_is_meaningful,
    _checkpoint_callback,
    _compute_plan_reasons,
    _create_message,
    _create_run_from_tasks,
    _derive_chat_caption_mode,
    _detect_caption_mode,
    _dock_question,
    _edit_op_items,
    _has_resolved_caption_mode,
    _needs_caption_mode_question,
    _prefers_zh,
    _resume_ack_line,
    _reminder_tail,
    _safe_task_estimate,
    _validate_edit_ops,
    latest_pending_question,
    sync_plan_question,
)
from app.chat.system_status import observe_phase_callback
from app.models.schemas import (
    AnswerPayload,
    AnswerProposal,
    ApplyEditOpsArgs,
    AssetType,
    Brief,
    ChatAnswerArgs,
    ChatAskArgs,
    ChatMention,
    EditGraphArgs,
    EditOpsProposal,
    InferredIntent,
    PendingPlan,
    ProposeTasksArgs,
    QuestionPayload,
    QuestionProposal,
    ReviseOutputArgs,
    TaskListProposal,
    WiringProposal,
)
from app.models.tables import (
    Asset,
    GraphNode,
    Message,
    Output,
    Persona,
    Project,
    WorkflowRun,
)
from app.operations.service import OpConflict, OpRejected, apply_operations
from app.pipeline.exploration_store import (
    ExplorationRejected,
    propose_candidates,
    propose_selects,
    revise_plan,
)
from app.pipeline.scope_compile import (
    assemble_craft_revision,
    decision_package_plans,
    route_revision,
)
from app.platform.project_context import resolve_default_persona
from app.providers.llm.base import LLMError
from app.tools import ToolRejected, validate_task_list

logger = structlog.get_logger()

# The return shape the service layer's callers hold (unchanged):
# (assistant message, dispatched run id, cascade-bailed run ids, the pending
# question this turn settled by judgment).
ProposeTurnOutcome = tuple[Message, UUID | None, list[UUID], Message | None]


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
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.conversation_id = UUID(str(conversation.id))
        self.project = project
        self.text = text
        self.on_phase = on_phase
        # 工作会话里程碑通道 (iter-3 S2 — the plan path's iter-2 ⑥ channel,
        # threaded here for the post-run discovery chain's door successes;
        # None = the one-shot path, no stream, no frames).
        self.on_activity = on_activity
        self.pending: Message | None = None
        self.pending_judgable = False
        self.context: dict = {"text": ""}
        self.mentions: list[ChatMention] = []
        self.settled_question: Message | None = None
        self.outcome: ProposeTurnOutcome | None = None
        self._bailed_on_skip: list[UUID] = []

    async def assemble(self, mentions: list[ChatMention], recent: list[Message]) -> None:
        db, project = self.db, self.project
        self.mentions = mentions
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
        self.context = (
            await build_context(db, project, recent, mentions, pending)
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

        project = self.project
        if project is None:
            return (None, None)
        clips_node = node_for_output("clips")
        if clips_node is None or not any(
            t.tool == clips_node.kind for t in tasks
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

                outcome = "idle"
                run = await db.get(WorkflowRun, pending.workflow_run_id)
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

    async def execute(self, name: str, params, prose: str) -> str | None | ToolObservation:
        """The LoopExecute seat: the disposition preamble, then the tool's
        validate → (reject: feedback, zero writes) → accept: writes + the
        outcome stashed → None (terminal stop). A PERCEPTION call never
        carries a disposition and never ends the turn — it dispatches to the
        family registry and rides back as a ToolObservation."""
        if name in PERCEPTION_TOOLS:
            return await run_perception_tool(self.db, self.project, name, params)
        disposition = (
            getattr(params, "pending_disposition", "none") if params is not None else "none"
        )
        if await self._settle_by_disposition(disposition):
            return None  # the parked interrupt's wake IS the continuation
        if name in EXPLORATION_TOOLS:
            return await self._explore(name, params, prose)
        if name == "propose_tasks":
            assert isinstance(params, ProposeTasksArgs)
            return await self._propose_tasks(params, prose)
        if name == "apply_edit_ops":
            assert isinstance(params, ApplyEditOpsArgs)
            return await self._apply_edit_ops(params, prose)
        if name == "edit_graph":
            assert isinstance(params, EditGraphArgs)
            return await self._edit_graph(params, prose)
        if name == "revise_output":
            assert isinstance(params, ReviseOutputArgs)
            return await self._revise_output(params, prose)
        if name == "ask_user":
            assert isinstance(params, ChatAskArgs)
            return await self._ask_user(params, prose)
        if name == "answer":
            assert isinstance(params, ChatAnswerArgs)
            return await self._answer(prose)
        return f"unknown tool {name!r}"  # unreachable — the driver gates names

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
        if not params.tasks:
            return (
                "empty task list — to ask the user first, call ask_user; for "
                "a purely informational reply, call answer."
            )
        proposal = TaskListProposal(tasks=params.tasks, summary=prose, name=params.name)
        # Caption mode for captioned-video runs (RECIPES §4.7): when the chain
        # asks for a quote card and the user didn't name a caption mode, dock
        # the choice BEFORE letting the run start — the answer rides
        # run.context.caption_mode downstream. The stashed TaskListProposal
        # dump rides the question's `intent` field; the answer path replays
        # it once the user picks a mode.
        if (
            _needs_caption_mode_question(params.tasks)
            and _detect_caption_mode(text) is None
            and not _has_resolved_caption_mode(project)
            and await _caption_choice_is_meaningful(db, project, params.tasks)
        ):
            caption_question = _build_caption_mode_question(text)
            stashed_proposal = proposal.model_dump(mode="json")
            assistant_message, bailed_run_ids = await _dock_question(
                db,
                self.conversation_id,
                caption_question.question,
                QuestionPayload(
                    kind="question",
                    question=caption_question.question,
                    options=caption_question.options,
                    allow_freeform=caption_question.allow_freeform,
                ),
                intent=stashed_proposal,
            )
            self.outcome = (
                assistant_message, None, bailed_run_ids, self.settled_question
            )
            return None
        try:
            validate_task_list(params.tasks)
        except ToolRejected as e:
            # The registry's rejection IS the feedback — one bounded loop
            # iteration (the retired repair round's seat) — the same
            # adjudication _create_run_from_tasks ran at the birthplace,
            # now BEFORE the dock so only registry-valid chains ever dock.
            return f"{e} (available: {getattr(e, 'suggestions', [])})"
        # Caption-mode resolution rides the DOCKED intent now (was: the
        # same-turn run's TaskSpec): keyword > stashed answer >
        # source_only-if-no-distinct-alt — one shared funnel; Start reads
        # intent.caption_mode off the stored pending.
        caption_mode = await _derive_chat_caption_mode(db, project, params.tasks, text)
        source_pin, exemplar_pin = await self._role_pins_for(params.tasks)
        await self._dock_plan_as_question(
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
        )
        return None

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
    ) -> None:
        """The chat path's ONE plan-docking seat (Phase 4 B2/B3): PendingPlan
        + task_book question + estimate + canonical draft preview (inside
        sync_plan_question) — the caption-replay pattern verbatim; Start
        reads intent.tasks / specific_instruction / caption_mode / pins off
        the stored pending. Sets the turn's outcome to the docked question
        (never a run).

        iter-3 S2 (R6 parity): the exploration dock rides the SAME seat —
        ``plans`` (the decision package's reading layer) + ``plan_task_map``
        (the R20 router substrate) + ``derived`` (the "you'll get" preview)
        + an explicitly resolved ``persona_id`` (the exploration door's
        provenance) are additive kwargs; the router-drafted callers
        (propose_tasks / edit_graph's expansion dock) pass none and keep
        their exact pre-S2 shape (derived=[], no plans, persona preserved
        from the stored pending)."""
        db, project = self.db, self.project
        intent = InferredIntent(
            action="draft",
            tasks=tasks,
            answer=answer or "",
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
        project.pending_brief = PendingPlan(
            prompt=self.text,
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
        ).model_dump(mode="json")
        bailed_run_ids = await sync_plan_question(
            db, self.user_id, project, intent, self.text,
            reasons=project.pending_brief["reasons"],
            brief=preserved_brief,
            echo=intent.answer,
            estimate=await _safe_task_estimate(db, project, intent.tasks),
            derived=derived,
            plans=plans,
        )
        docked = await latest_pending_question(db, self.conversation_id)
        self.outcome = (docked, None, bailed_run_ids, self.settled_question)

    # ---- the exploration seats (iter-3 S2 — R6 parity with the plan path) ----

    async def _emit_milestone(self, key: str, count: int) -> None:
        """Fire one work-session milestone frame (iter-2 ⑥, N-57) at a door
        success — in-session interleave only, never persisted. No-op on the
        one-shot path."""
        if self.on_activity is not None:
            await self.on_activity(key, count)

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
            return ToolObservation(text=selects_observation(born))
        if name == "propose_plans":
            assert isinstance(params, ProposePlansArgs)
            return await self._propose_plans(params, prose)
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
        await self._dock_plan_as_question(
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
        )
        return None

    async def _revise_plan(self, params: RevisePlanArgs, prose: str) -> str | None:
        """revise_plan → the door revises the row in place → the WHOLE
        journey re-compiles → the decision package re-docks through the
        SAME seat (iter-3 S2; 恒重确认 R15: every plan-level revision
        re-confirms — zero autonomy; 决策包可编辑律: the re-dock lands on
        the SAME confirmation seat, never a new ritual — sync_plan_question
        supersedes the still-open task_book row). The revised row lands
        even when the recompile then rejects (draft with issues re-stamped
        = the canvas's honest surface); the rejection rides back as the
        loop echo and the LLM repairs the PLAN, never the chain."""
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
        await self._emit_milestone("chat.explore.plansReady", len(package.plans))

        # The package's name survives the revision (same law as the plan
        # path) — the pending row's intent carries it when one survives;
        # caption_mode re-derives from the restated outputs, inheriting the
        # stored answer when unnamed (同一律).
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
        await self._dock_plan_as_question(
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
        )
        return None

    async def _apply_edit_ops(self, params: ApplyEditOpsArgs, prose: str) -> str | None:
        """edit_ops → the operations registry. Validation rejections ride the
        loop; the ownership check is an honest boundary (never a retry)."""
        db, text = self.db, self.text
        proposal = EditOpsProposal(
            target_output_id=params.target_output_id, ops=params.ops, summary=prose
        )
        ops_items = _edit_op_items(proposal)
        try:
            _validate_edit_ops(ops_items)
        except OpRejected as e:
            return str(e)
        # Mentions forward client-pinned ids verbatim (MENTIONS §35) —
        # authorize before any write: the target must be an output of THIS
        # project (the chat surface's cross-tenant IDOR fix).
        target = await db.get(Output, params.target_output_id)
        if (
            self.project is None
            or target is None
            or UUID(str(target.project_id)) != UUID(str(self.project.id))
        ):
            assistant_message = await _create_message(
                db, self.conversation_id, "assistant", _cannot_do_text(text)
            )
            self.outcome = (assistant_message, None, [], self.settled_question)
            return None
        # Create the assistant message first (flush for the id), then apply
        # with message_id lineage — one commit at the tail.
        assistant_message = await _create_message(
            db,
            self.conversation_id,
            "assistant",
            prose,
            intent=proposal.model_dump(mode="json"),
        )
        try:
            await apply_operations(
                db,
                params.target_output_id,
                ops_items,
                source="chat",
                user_id=self.user_id,
                message_id=UUID(str(assistant_message.id)),
            )
        except (OpRejected, OpConflict):
            assistant_message.content = _cannot_do_text(text)
        except HTTPException as e:
            # e.g. target has no render_spec — a legitimate "can't do that".
            assistant_message.content = str(e.detail)
        self.outcome = (assistant_message, None, [], self.settled_question)
        return None

    async def _edit_graph(self, params: EditGraphArgs, prose: str) -> str | None:
        """wiring → 修订 = edit_prompt(node) + run({node} ∪ downstream)
        (ADR-057 K4). The dispatch law lives in ``_run_wiring_proposal``
        (ONE seat — iter-3 S3's revise_output rides the same machinery with
        code-assembled ops); the door's own rejections ARE the loop's
        feedback."""
        proposal = WiringProposal(ops=params.ops, summary=prose, name=params.name)
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
        from app.pipeline.graph_store import WiringRejected, apply_wiring_ops
        from app.pipeline.graph_revise import tasks_for_graph_nodes
        from app.pipeline.scope_classifier import (
            CONTINUATION,
            classify_graph_scope,
            load_graph_facts,
        )
        from app.models.tables import GraphNode

        async def _dispatch(p: WiringProposal) -> UUID | None:
            if project is None or not p.ops:
                raise WiringRejected("wiring: no ops to apply")
            project_id = UUID(str(project.id))
            # The approved-scope baseline (Batch 1 preflight ①): the pre-op
            # run-born graph. The classifier never sees ops — it compares
            # plain facts gathered before and after the door (D4).
            pre_nodes, pre_edges = await load_graph_facts(db, project_id)
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
                    # Roll the door's mutation back — the dock's own draft
                    # stamp (inside sync_plan_question) previews the plan
                    # with canonical fill keys instead.
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
            await self._dock_plan_as_question(
                tasks=tasks,
                answer=(p.summary or "") + (content_note or ""),
                specific_instruction=instruction or None,
                caption_mode=None,
                name=p.name or None,
                source_pin=source_pin,
                exemplar_pin=exemplar_pin,
            )
            return None

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
            db, self.conversation_id, "assistant", (prose or "") + (content_note or ""),
            workflow_run_id=run_id,
            intent=proposal.model_dump(mode="json"),
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

    async def _ask_user(self, params: ChatAskArgs, prose: str) -> str | None:
        """ask → the agent's question docks through the ask_user machinery
        (task_book questions are raised solely by the plan path, never
        here). slot stays None — a post-run question never backfills the
        brief."""
        if not params.question.strip():
            return (
                "empty question — speak the framing as your message text and "
                "pass the ONE bare question, or call another tool."
            )
        # ask 三分解剖: content carries the framing prose (the turn's echo),
        # the bare question rides the payload.
        ask = QuestionProposal(
            prose=prose or "",
            question=params.question,
            options=params.options,
            allow_freeform=params.allow_freeform,
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
                default_path=params.default_path,
            ),
            intent=ask.model_dump(mode="json"),
        )
        self.outcome = (
            assistant_message, None, bailed_run_ids, self.settled_question
        )
        return None

    async def _answer(self, prose: str) -> str | None:
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
        elif result is None or result.exhausted:
            # result None = provider failure (the caller maps LLMError here);
            # exhausted = every call rejected. ask-back is the only failure
            # form (prohibition #7); adjudication exhaustion reads as
            # cannot-do (the retired degrade's honest line).
            content = _ASK_BACK_TEXT if result is None else _cannot_do_text(self.text)
            if result is not None:
                logger.info("chat_turn_loop_exhausted", calls=result.calls)
            assistant_message = await _create_message(
                self.db, self.conversation_id, "assistant", content
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
            run_id, bailed_run_ids, settled = None, [], self.settled_question
        bailed_run_ids = [*self._bailed_on_skip, *bailed_run_ids]
        if self.pending_judgable and self.pending is not None and assistant_message.question is None:
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
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
    on_loop_event=None,
    on_activity=None,
) -> ProposeTurnOutcome:
    """The chat path's turn: assemble → the bounded tool loop → the outcome
    mapping. Provider failure keeps its retired posture: the ask-back line is
    the only failure form (prohibition #7) — EXCEPT the tier gate (ADR-077
    判词④), which fails LOUD: a tools-blind client is a deployment error,
    never the ask-back line."""
    turn = ChatTurn(db, user_id, conversation, project, text, on_phase=on_phase,
                    on_activity=on_activity)
    await turn.assemble(mentions, recent)
    try:
        result = await chat_intent_agent.call_loop(
            turn.execute,
            message=text,
            context=turn.context,
            on_delta=on_delta,
            on_reasoning=on_reasoning,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_observe=observe_phase_callback(on_phase),
            on_loop_event=on_loop_event,
            on_checkpoint=(
                # ADR-085: the checkpoint channel (persist + SSE forward) —
                # a project-less defensive turn has no conversation to
                # persist into, so the channel stays closed there.
                _checkpoint_callback(db, turn.conversation_id, on_checkpoint)
                if turn.project is not None
                else None
            ),
        )
    except LLMError:
        capabilities = getattr(chat_intent_agent.client, "capabilities", None)
        if capabilities is None or not capabilities.supports_native_tools:
            raise  # the tier gate fails loud, never the ask-back line
        result = None
    return await turn.finish(result)


__all__ = ["run_propose_turn", "ChatTurn", "ProposeTurnOutcome"]
