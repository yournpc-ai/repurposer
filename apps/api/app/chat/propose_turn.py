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
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.context import build_context
from app.agents.tool_loop import ToolObservation
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
    TaskListProposal,
    WiringProposal,
)
from app.models.tables import Asset, Message, Output, Project, WorkflowRun
from app.operations.service import OpConflict, OpRejected, apply_operations
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
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.conversation_id = UUID(str(conversation.id))
        self.project = project
        self.text = text
        self.on_phase = on_phase
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
        if name == "propose_tasks":
            assert isinstance(params, ProposeTasksArgs)
            return await self._propose_tasks(params, prose)
        if name == "apply_edit_ops":
            assert isinstance(params, ApplyEditOpsArgs)
            return await self._apply_edit_ops(params, prose)
        if name == "edit_graph":
            assert isinstance(params, EditGraphArgs)
            return await self._edit_graph(params, prose)
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
            specific_instruction=text or None,
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
    ) -> None:
        """The chat path's ONE plan-docking seat (Phase 4 B2/B3): PendingPlan
        + task_book question + estimate + canonical draft preview (inside
        sync_plan_question) — the caption-replay pattern verbatim; Start
        reads intent.tasks / specific_instruction / caption_mode / pins off
        the stored pending. Sets the turn's outcome to the docked question
        (never a run)."""
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
                project.pending_brief.get("persona_id")
                if isinstance(project.pending_brief, dict)
                else None
            ),
            source_asset_id=source_pin,
            exemplar_asset_id=exemplar_pin,
            derived=[],
        ).model_dump(mode="json")
        bailed_run_ids = await sync_plan_question(
            db, self.user_id, project, intent, self.text,
            reasons=project.pending_brief["reasons"],
            brief=preserved_brief,
            echo=intent.answer,
            estimate=await _safe_task_estimate(db, project, intent.tasks),
        )
        docked = await latest_pending_question(db, self.conversation_id)
        self.outcome = (docked, None, bailed_run_ids, self.settled_question)

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
        (ADR-057 K4), gated by the Deterministic Scope Classifier (ADR-087
        §4 + D4, Phase 4 B2): the ops land through the graph's ONLY write
        door inside a savepoint, then the door's RESULTING paid execution
        scope is adjudicated against the pre-op run-born graph —

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

        The door's own rejections ARE the loop's feedback."""
        db, project = self.db, self.project
        from app.pipeline.graph_store import WiringRejected, apply_wiring_ops
        from app.pipeline.graph_revise import tasks_for_graph_nodes
        from app.pipeline.scope_classifier import (
            CONTINUATION,
            classify_graph_scope,
            load_graph_facts,
        )
        from app.models.tables import GraphNode

        proposal = WiringProposal(ops=params.ops, summary=prose, name=params.name)

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
            # stored pending).
            source_pin, exemplar_pin = await self._role_pins_for(tasks)
            await self._dock_plan_as_question(
                tasks=tasks,
                answer=p.summary or "",
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
            db, self.conversation_id, "assistant", prose,
            workflow_run_id=run_id,
            intent=proposal.model_dump(mode="json"),
        )
        self.outcome = (assistant_message, run_id, [], self.settled_question)
        return None

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
) -> ProposeTurnOutcome:
    """The chat path's turn: assemble → the bounded tool loop → the outcome
    mapping. Provider failure keeps its retired posture: the ask-back line is
    the only failure form (prohibition #7) — EXCEPT the tier gate (ADR-077
    判词④), which fails LOUD: a tools-blind client is a deployment error,
    never the ask-back line."""
    turn = ChatTurn(db, user_id, conversation, project, text, on_phase=on_phase)
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
