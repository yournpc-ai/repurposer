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
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.tools.video.design import CompositionDesignVideoArgs

from app.agents.candidate_correction import CandidateRejected, CandidateScope
from app.agents.tool_loop import (
    TerminalRefusal,
    ToolObservation,
)
from app.agents.tool_loop import (
    ToolRejected as LoopToolRejected,  # alias: app.tools.ToolRejected (the
    # chain-adjudication exception, imported below) shadows the loop event's
    # name in this module — the retract seat must match the LOOP's class
)
from app.agents.working_drafts import WorkingDraftRejected, WorkingDraftUpdated
from app.chat.context import build_context
from app.chat.deferred_frames import DeferredFrames
from app.chat.intent import chat_intent_agent
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.service import (
    _ask_content,
    _auto_start_docked_plan,
    _bare_question,
    _compute_plan_reasons,
    _create_message,
    _design_no_progress_text,
    _dock_question,
    _interim_prose_callback,
    _loop_incomplete_text,
    _parked_interrupt_run,
    _prefers_zh,
    _reminder_block,
    _resume_ack_line,
    _safe_task_estimate,
    _sfx_import_failure_text,
    _video_capability_text,
    _video_review_failure_text,
    _video_review_report_text,
    latest_pending_question,
    resolve_confirmation_need,
    resolve_suggestion_note,
    sync_plan_question,
)
from app.chat.turn_tools import video_rejection_stop
from app.models.schemas import (
    AnnotateNarrationArgs,
    AnswerPayload,
    AnswerProposal,
    AssetType,
    Brief,
    ChatAnswerArgs,
    ChatAskArgs,
    ChatMention,
    CreativeState,
    EditGraphArgs,
    GetNarrationAlignmentArgs,
    ImportSfxArgs,
    InferredIntent,
    PendingPlan,
    PlanEstimate,
    PrepareNarrationArgs,
    ProposeTasksArgs,
    QuestionPayload,
    QuestionProposal,
    RetryUploadArgs,
    ReviewVideoArgs,
    SearchSfxArgs,
    SelectMusicArgs,
    SelectVideoPresetArgs,
    ShowMusicCandidatesArgs,
    ShowVideoPresetsArgs,
    SkillReference,
    SuggestionRef,
    missing_brief_question_items,
    question_group_digest,
    resolve_recommended_id,
)
from app.models.tables import (
    Asset,
    Message,
    Project,
    User,
    WorkflowRun,
)
from app.pipeline.assets import create_web_page_assets_committed_from_urls
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
        skill: SkillReference | None = None,
        skill_ambiguity: list[str] | None = None,
        on_phase=None,
        on_activity=None,
        on_candidates=None,
        on_row_append=None,
        turn_id: UUID | None = None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.turn_id = turn_id
        self.conversation_id = UUID(str(conversation.id))
        # 环境能力位 (ADR-118 §6 双键): the conversation-stamped client
        # capability (prepare_chat_turn 的 last-wins 盖章, ui_language 同律
        # 座) — the assembly's canvas_available source on request-born
        # turns; None = never reported → the Environment line stays out.
        self.canvas_available = conversation.canvas_available
        self.project = project
        self.text = text
        self.skill = skill
        self.skill_ambiguity = skill_ambiguity or []
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
        # 视频呈现挂号 (ADR-145 phase B, the plan path's mirror): a
        # A successful design or preview keeps the saved
        # version's read dict; finish stamps the receipt + the storyboard
        # block onto the persisted terminal row (shared seat:
        # video_turn_seats).
        self._video_presentation_pending: dict | None = None
        # A completed review is a world fact even if the outer prose
        # continuation later fails; finish closes from this persisted report.
        self._video_review_report: dict | None = None
        self._video_call_counter: int = 0
        self.pending: Message | None = None
        self.pending_judgable = False
        self.context: dict = {"text": ""}
        self.mentions: list[ChatMention] = []
        self.settled_question: Message | None = None
        self.outcome: ProposeTurnOutcome | None = None
        self._bailed_on_skip: list[UUID] = []
        self._uploaded_output_refs: list[str] = []
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
                db, project, mentions, pending,
                canvas_available=self.canvas_available,
                confirmation=confirmation,
                skill=self.skill,
                skill_ambiguity=self.skill_ambiguity,
                include_pending=False,
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

    async def _wake_by_disposition(self, disposition: str) -> bool:
        """Wake a parked interrupt when its judged answer is the continuation.
        Ordinary tools settle their judgment only after terminal acceptance."""
        if not self.pending_judgable or disposition != "answer":
            return False
        db, pending, text = self.db, self.pending, self.text
        if pending is None or pending.workflow_run_id is None:
            return False
        from app.pipeline.orchestrator import resume_waiting_interrupt

        run = await _parked_interrupt_run(db, pending.workflow_run_id)
        if run is None:
            return False
        pending.answer = AnswerPayload(
            kind="freeform",
            text=text,
            answered_at=datetime.now(UTC),
        ).model_dump(mode="json")
        await db.flush()
        self.settled_question = pending
        self.pending = None
        self.pending_judgable = False
        outcome = await resume_waiting_interrupt(db, run, pending.answer)
        decided = (pending.answer or {}).get("text") or ""
        # A blocked arbitration (another run holds the authority) speaks the
        # parked line instead. The wake is the continuation; the proposed
        # tool's own dispatch is skipped.
        assistant_message = await _create_message(
            db,
            self.conversation_id,
            "assistant",
            _resume_ack_line(decided, outcome),
        )
        self.outcome = (assistant_message, None, [], self.settled_question)
        return True

    async def _settle_by_disposition(self, disposition: str) -> None:
        """Settle a pending question after the carrying tool was accepted."""
        if not self.pending_judgable or disposition == "none":
            return
        db, pending, text = self.db, self.pending, self.text
        if pending is None:
            self.pending_judgable = False
            return
        if disposition == "answer":
            pending.answer = AnswerPayload(
                kind="freeform",
                text=text,
                answered_at=datetime.now(UTC),
            ).model_dump(mode="json")
        else:
            # "skip" — an explicit decline settles bail (the text question's
            # only ×); the accepted tool's own dispatch has already run.
            pending.answer = AnswerPayload(
                kind="bail",
                answered_at=datetime.now(UTC),
            ).model_dump(mode="json")
        await db.flush()
        self.settled_question = pending
        if disposition != "answer" and pending.workflow_run_id is not None:
            from app.pipeline.orchestrator import bail_waiting_interrupt

            run = await db.get(WorkflowRun, pending.workflow_run_id)
            if run is not None and await bail_waiting_interrupt(db, run) is not None:
                self._bailed_on_skip = [UUID(str(run.id))]
        self.pending = None
        self.pending_judgable = False

    # ---- the loop's execute dispatch ----------------------------------------

    async def execute(self, name: str, params, prose: str) -> str | None | ToolObservation | TerminalRefusal | CandidateRejected | WorkingDraftRejected | WorkingDraftUpdated:
        """The LoopExecute seat: a parked wake, then the tool's validate →
        (reject: feedback, zero writes) → accept: writes + pending settlement
        + outcome. A PERCEPTION call never carries a disposition and never
        ends the turn — it dispatches to the family registry and rides back
        as a ToolObservation."""
        from app.chat.editor import EDITOR_NAMES, execute_editor

        if name in EDITOR_NAMES:
            return await execute_editor(self, name, params)
        if name == "read_conversation_context":
            return await self._conversation_context.read(params)
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
        if (
            name == "design_video"
            and self.pending_judgable
            and params is not None
            and "pending_disposition" not in params.model_fields_set
        ):
            return (
                "a question is pending and this write omitted pending_disposition. "
                "Judge the current message as answer/skip/none and retry the intended call "
                "with that field; no write was executed."
            )
        disposition = (
            getattr(params, "pending_disposition", "none") if params is not None else "none"
        )
        if await self._wake_by_disposition(disposition):
            result: str | None | ToolObservation | TerminalRefusal | CandidateRejected | WorkingDraftRejected | WorkingDraftUpdated = None
        else:
            result = await self._dispatch(name, params, prose)
            if result is None:
                await self._settle_by_disposition(disposition)
        # The speech-commit resolution (言语提交协议): a terminal accept
        # closes the frame buffer (a rejection-marked turn drops — its
        # words were retracted speech). Rejections retract at the loop's
        # ToolRejected event (the runner's wrapped on_loop_event — one seat
        # catches all four rejection kinds); ToolObservations are
        # non-terminal (reads) — the queue stays armed.
        if result is None:
            await self._resolve_deferred()
        return result

    def _remember_video_review(self, report: dict) -> None:
        self._video_review_report = report

    async def _dispatch(self, name: str, params, prose: str) -> str | None | ToolObservation | TerminalRefusal | CandidateRejected | WorkingDraftRejected | WorkingDraftUpdated:
        if name == "propose_tasks":
            assert isinstance(params, ProposeTasksArgs)
            return await self._propose_tasks(params, prose)
        if name in {"list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview"}:
            from app.chat.video_turn_seats import skill_read_seat
            return await skill_read_seat(
                project=self.project,
                skill=self.skill,
                package_sessions=self.__dict__.setdefault("_skill_package_sessions", {}),
                name=name,
                args=params,
            )
        if name == "analyze_brand":
            from app.chat.video_turn_seats import analyze_brand_seat
            return await analyze_brand_seat(project=self.project, args=params, user_text=self.text)
        if name == "prepare_video_materials":
            from app.chat.video_turn_seats import prepare_video_materials_seat
            return await prepare_video_materials_seat(
                project=self.project, args=params, turn_id=self.turn_id
            )
        if name == "capture_web":
            from app.chat.video_turn_seats import capture_web_seat
            return await capture_web_seat(project=self.project, args=params)
        if name == "design_video":
            from app.tools.video.design import CompositionDesignVideoArgs
            assert isinstance(params, CompositionDesignVideoArgs)
            return await self._design_video(params)
        if name == "review_working_draft":
            from app.chat.video_turn_seats import review_working_draft_seat
            return await review_working_draft_seat(project=self.project, args=params)
        if name == "review_video":
            assert isinstance(params, ReviewVideoArgs)
            from app.chat.video_turn_seats import review_video_seat
            return await review_video_seat(
                project=self.project,
                args=params,
                on_report=self._remember_video_review,
            )
        if name == "show_video_presets":
            assert isinstance(params, ShowVideoPresetsArgs)
            from app.chat.video_turn_seats import show_video_presets_seat
            return await show_video_presets_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "select_video_preset":
            assert isinstance(params, SelectVideoPresetArgs)
            from app.chat.video_turn_seats import select_video_preset_seat
            return await select_video_preset_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "search_sfx":
            assert isinstance(params, SearchSfxArgs)
            from app.chat.video_turn_seats import search_sfx_seat
            return await search_sfx_seat(
                project=self.project, args=params, user_text=self.text,
                on_candidates=self._emit_candidates,
            )
        if name == "import_sfx":
            assert isinstance(params, ImportSfxArgs)
            from app.chat.video_turn_seats import import_sfx_seat
            return await import_sfx_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "show_music_candidates":
            assert isinstance(params, ShowMusicCandidatesArgs)
            from app.chat.video_turn_seats import show_music_candidates_seat
            return await show_music_candidates_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "select_music":
            assert isinstance(params, SelectMusicArgs)
            from app.chat.video_turn_seats import select_music_seat
            return await select_music_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "prepare_narration":
            assert isinstance(params, PrepareNarrationArgs)
            from app.chat.video_turn_seats import prepare_narration_seat
            return await prepare_narration_seat(
                project=self.project, args=params, mentions=self.mentions
            )
        if name == "prepare_visual_assets":
            from app.chat.video_turn_seats import prepare_visual_assets_seat
            return await prepare_visual_assets_seat(project=self.project, args=params)
        if name == "prepare_music":
            from app.chat.video_turn_seats import prepare_music_seat
            return await prepare_music_seat(project=self.project, args=params)
        if name == "get_narration_alignment":
            assert isinstance(params, GetNarrationAlignmentArgs)
            from app.chat.video_turn_seats import get_narration_alignment_seat
            return await get_narration_alignment_seat(project=self.project, args=params)
        if name == "annotate_narration":
            assert isinstance(params, AnnotateNarrationArgs)
            from app.chat.video_turn_seats import annotate_narration_seat
            return await annotate_narration_seat(project=self.project, args=params)
        if name == "edit_graph":
            assert isinstance(params, EditGraphArgs)
            error = await self._edit_graph(params, prose)
            if error is not None:
                return error
            content = prose.strip() or (
                "已更新手动画布。" if _prefers_zh(self.text) else "Manual Canvas updated."
            )
            assistant_message = await _create_message(
                self.db,
                self.conversation_id,
                "assistant",
                content,
                intent=AnswerProposal(text=content).model_dump(mode="json"),
            )
            self.outcome = (assistant_message, None, [], self.settled_question)
            return None
        if name == "retry_upload":
            assert isinstance(params, RetryUploadArgs)
            return await self._retry_upload(params, prose)
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
        if getattr(self, "video_confirmation", None) and self.video_confirmation["action"] == "produce":
            from app.chat.video_turn_seats import confirmed_video_task

            params = params.model_copy(update={
                "tasks": [confirmed_video_task(self.video_confirmation)],
                "production_intent": True,
                "material_urls": None,
            })
        db, project, text = self.db, self.project, self.text
        assert project is not None  # propose_tasks is project-bound
        from app.chat.video_turn_seats import video_proposal_guard
        video_guard = await video_proposal_guard(db, project, params.tasks,
            pending_read=self._video_presentation_pending, production_intent=params.production_intent, mentions=self.mentions)
        if video_guard is not None:
            return video_guard
        if params.production_intent is None:
            return (
                "production_intent is required. Judge whether the user's current "
                "message asks for this work to be made now, set it explicitly "
                "true or false, then call propose_tasks again."
            )
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
        source_pin, exemplar_pin = await self._role_pins_for(params.tasks)
        # 守卫传播 (分镜不是开工): a STRING return is the film guardrail's
        # steering observation — it rides back as the tool loop's feedback.
        return await self._dock_plan_as_question(
            tasks=params.tasks,
            answer=prose,
            # P0-② 对账 (2026-09-22): the distilled EXTRA instruction wins
            # when the model supplies it (the one contract with the plan
            # path — schemas.py / plan_mode.j2); an absent field
            # falls back to the turn's raw text (the pre-fix behavior), so
            # the writers' trust chain never loses the instruction whole.
            specific_instruction=params.specific_instruction or text or None,
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
    async def _stamp_video_presentation(self, message) -> None:
        """The video family's presentation association (ADR-145 phase B,
        the plan path's mirror): delegates to the shared seat
        (video_turn_seats) — the receipt + the storyboard block land on
        the persisted row that actually presents the saved facts."""
        pending = self._video_presentation_pending
        self._video_presentation_pending = None
        if self.project is None:
            return
        from app.chat.video_turn_seats import (  # deferred: same layer
            requested_video_production,
            stamp_video_presentation,
        )

        stamp_video_presentation(
            self.project, message, pending,
            observed_ranges=self.__dict__.pop("_editor_preview_blocks", []),
            production_requested=bool(pending and pending.get("fresh_design"))
            and requested_video_production(self.text),
        )

    async def _design_video(self, params: "CompositionDesignVideoArgs") -> str | ToolObservation | CandidateRejected | WorkingDraftRejected | WorkingDraftUpdated:
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

        stopped = getattr(self, "_video_design_stopped", None)
        if stopped is not None:
            return stopped
        self._video_call_counter += 1
        read, feedback = await design_video_seat(
            project=self.project,
            args=params,
            request_id=await video_request_id(self.db, self.conversation_id, self._video_call_counter),
            skill=self.skill,
            skill_ambiguity=self.skill_ambiguity,
            package_sessions=self.__dict__.setdefault("_skill_package_sessions", {}),
            user_text=self.text,
        )
        if read is None:
            if isinstance(feedback, ToolObservation) and not feedback.ok:
                self._video_design_stopped = feedback
            return feedback
        await self._settle_by_disposition(params.pending_disposition)
        read["fresh_design"] = True
        self._video_presentation_pending = read
        return feedback

    async def _dock_plan_as_question(
        self,
        *,
        tasks: list,
        answer: str,
        specific_instruction: str | None,
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
        reads intent.tasks / specific_instruction / production pins off
        the stored pending. Sets the turn's outcome to the docked question
        (never a run). Returns None when docked; a STRING is the film
        guardrail's steering observation (the storyboard was never presented
        for this exact chain — the call never docked, the tool loop's repair
        iteration carries the redirect to design_video).

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
        # The shared dock seat turns this quote into a structured system
        # notice after the assistant's echo (BILLING §2.1 disclosure).
        resolved_estimate = (
            await _safe_task_estimate(db, project, tasks)
            if estimate is _ESTIMATE_UNSET
            else estimate
        )
        # ADR-117 §4: one confirmation-need computation per dock — the
        # echo's held clause (keyed on the stamped reason) reads it, the
        # payload stamp takes it by pass-through below.

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
            # 定点收尾②复审: the drift hold reads the STANDING VERSION's
            # persisted state (world truth — a rebuilt turn never loses
            # it), never a turn-local flag.
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
        # 展示一座 (ADR-129): the storyboard markdown's presentation seat
        # is the design beat's own message — a dock echo NEVER re-embeds it.
        answer = answer or ""
        intent = InferredIntent(
            action="draft",
            tasks=tasks,
            answer=answer,
            specific_instruction=specific_instruction,
            name=name,
        )
        preserved_brief = (
            Brief.model_validate(project.pending_brief["brief"])
            if isinstance(project.pending_brief, dict)
            and isinstance(project.pending_brief.get("brief"), dict)
            else Brief()
        )
        from app.chat.readiness import creative_state_for_pending, creative_state_with_brief
        from app.editing.service import video_carry_state  # deferred: editing seam
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=intent,
            brief=preserved_brief,
            creative_state=creative_state_with_brief(
                creative_state_for_pending(stored) or CreativeState(), preserved_brief
            ),
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
            turn_id=self.turn_id,
            defer_start_commit=True,
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
        ``candidates_log`` message row at turn settle (the activity-row
        precedent), so a refresh rebuilds the surface from the archive —
        数据链全程消息载, no endpoint. No-op on the one-shot path."""
        if self.on_candidates is not None:
            await self.on_candidates(payload)

    async def _edit_graph(self, params: EditGraphArgs, prose: str) -> str | None:
        from app.pipeline.graph_store import edit_manual_graph
        return await edit_manual_graph(self.db, self.project, params.ops)

    async def _retry_upload(self, params: RetryUploadArgs, prose: str) -> ToolObservation:
        from app.pipeline.upload_recovery import upload_finished_output

        output_id = pinned_output_id(
            self.mentions,
            str(params.output_id) if params.output_id is not None else None,
        )
        uploaded_id, detail = await upload_finished_output(
            self.project.id, self.project.user_id,
            UUID(output_id) if output_id is not None else None,
        )
        if uploaded_id is not None:
            self._uploaded_output_refs.append(str(uploaded_id))
        return ToolObservation(text=detail, ok=uploaded_id is not None)


    async def _ask_user(self, params: ChatAskArgs, prose: str) -> str | None:
        """ask → the agent's question docks through the ask_user machinery
        (task_book questions are raised solely by the plan path, never
        here). slot stays None — a post-run question never backfills the
        brief."""
        if not params.question.strip():
            return (
                "empty question — speak the framing as your message text and "
                "pass the bare question or group title, or call another tool."
            )
        from app.chat.readiness import (
            brief_with_user_constraints,
            creative_state_for_pending,
            creative_state_with_brief,
            infer_task_kind,
            website_promo_question_items,
        )
        stored = PendingPlan.model_validate(self.project.pending_brief or {})
        current_state = creative_state_for_pending(stored)
        brief = current_state.brief if current_state is not None else stored.brief
        source_text = (
            self.text if infer_task_kind(self.text) == "website_promo"
            else stored.prompt or self.text
        )
        website_promo = infer_task_kind(source_text) == "website_promo"
        if website_promo:
            if current_state is None or current_state.brand_profile is None:
                return "website promo clarification requires analyze_brand before ask_user; no question was docked"
            brief = brief_with_user_constraints(self.text, brief)
        group_items = []
        group_digest = None
        if website_promo:
            try:
                group_items = website_promo_question_items(params.items, brief)
            except ValueError as exc:
                return str(exc)
            group_digest = question_group_digest(group_items, brief)
        elif params.items:
            try:
                group_items = missing_brief_question_items(params.items, brief)
            except ValueError as exc:
                return str(exc)
            if not group_items:
                return "every requested Brief field is already present; do not re-ask it"
            group_digest = question_group_digest(group_items, brief)
        if group_items:
            brief.asked = list(dict.fromkeys([
                *brief.asked, *(item.slot for item in group_items)
            ]))
            stored.brief = brief
            stored.creative_state = creative_state_with_brief(
                current_state or CreativeState(),
                brief,
            )
            if not stored.prompt:
                stored.prompt = self.text
            self.project.pending_brief = stored.model_dump(mode="json")
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
            _ask_content(ask, has_dock_options=bool(group_items)),
            QuestionPayload(
                kind="question",
                question=params.question,
                options=params.options,
                allow_freeform=params.allow_freeform,
                recommended_id=recommended_id,
                default_path=params.default_path,
                items=group_items,
                group_digest=group_digest,
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
            intent={
                **AnswerProposal(text=prose).model_dump(mode="json"),
                "output_refs": self._uploaded_output_refs,
            },
        )
        self.outcome = (assistant_message, None, [], self.settled_question)
        return None

    # ---- the outcome mapping -------------------------------------------------

    async def finish(self, result) -> ProposeTurnOutcome:
        """LoopResult → the caller's 4-tuple + the reminder system block:
        the pre-turn question survived unsettled and unsuperseded (an
        interjection) — the reminder follows the assistant's prose."""
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
                video_read = self._video_presentation_pending
                assistant_message = await _create_message(
                    self.db,
                    self.conversation_id,
                    "assistant",
                    _design_no_progress_text(
                        self.text,
                        version_saved=(
                            video_read is not None
                        ),
                        video_read=video_read,
                    ),
                )
                # Preserve and present the direct video save that preceded the
                # unsuccessful correction; the first-version review hold remains.
                await self._stamp_video_presentation(assistant_message)
                run_id, bailed_run_ids, settled = None, [], self.settled_question
            elif result is not None and result.ended_by is not None:
                # Mirror the plan path: a media-capability refusal closes
                # with its standing-version facts, not the design-begin text.
                facts = result.refusal_facts or {}
                content = (
                    _sfx_import_failure_text(self.text)
                    if facts.get("kind") == "sfx_import_failure"
                    else _video_review_failure_text(self.text, facts)
                    if facts.get("kind") == "video_review_failure"
                    else _video_capability_text(self.text, facts)
                    if facts.get("kind") == "video_capability"
                    else _loop_incomplete_text(self.text, result)
                )
                assistant_message = await _create_message(
                    self.db,
                    self.conversation_id,
                    "assistant",
                    content,
                )
                run_id, bailed_run_ids, settled = None, [], self.settled_question
            elif result is None and getattr(self, "_video_review_report", None) is not None:
                assistant_message = await _create_message(
                    self.db,
                    self.conversation_id,
                    "assistant",
                    _video_review_report_text(self.text, self._video_review_report),
                )
                run_id, bailed_run_ids, settled = None, [], self.settled_question
            elif result is None or result.exhausted:
                # A provider failure without a completed review propagates to
                # the localized failure frame; this branch is loop exhaustion
                # (or a defensive None), never an ambiguity claim about the user.
                content = _loop_incomplete_text(self.text, result)
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
        if assistant_message is not None and self._uploaded_output_refs:
            assistant_message.intent = {
                **(assistant_message.intent or {}),
                "output_refs": self._uploaded_output_refs,
            }
        bailed_run_ids = [*self._bailed_on_skip, *bailed_run_ids]
        if (
            assistant_message is not None
            and self.pending_judgable
            and self.pending is not None
            and assistant_message.question is None
        ):
            still_open = await latest_pending_question(self.db, self.conversation_id)
            if still_open is not None and still_open.id == self.pending.id:
                assistant_message.blocks = [
                    *(assistant_message.blocks or []),
                    _reminder_block(
                        self.text,
                        _bare_question(self.pending),
                        (self.pending.question or {}).get("default_path"),
                    ),
                ]
        return assistant_message, run_id, bailed_run_ids, settled


async def run_propose_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation,
    project: Project | None,
    text: str,
    mentions: list[ChatMention],
    recent: list[Message],
    skill: SkillReference | None = None,
    skill_ambiguity: list[str] | None = None,
    suggestion_ref: SuggestionRef | None = None,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_interim_prose=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
    turn_id: UUID | None = None,
) -> ProposeTurnOutcome:
    """The chat path's turn: assemble → the bounded tool loop → the outcome
    mapping. Provider failure reaches the localized failure frame; a completed
    video review instead closes from its persisted report. The tier gate
    (ADR-077 判词④) fails LOUD: a tools-blind client is a deployment error.
    ``on_row_append`` is the generic persisted-row channel (currently unused
    by this path — the design beat's program-markdown publication retired
    with the 2026-10-18 裁决)."""
    turn = ChatTurn(
        db, user_id, conversation, project, text,
        skill=skill, skill_ambiguity=skill_ambiguity,
        on_phase=on_phase, on_activity=on_activity, on_candidates=on_candidates,
        on_row_append=on_row_append, turn_id=turn_id,
    )
    from app.chat.video_turn_seats import (
        prepare_bound_skill_context,
        requested_video_production,
        video_target_hint,
    )
    context_reader = await prepare_bound_skill_context(
        project=project, skill=skill, message=text,
        package_sessions=turn.__dict__.setdefault("_skill_package_sessions", {}),
    )
    await turn.assemble(mentions, recent, suggestion_ref)
    mention_target = await video_target_hint(db, project, mentions) if project is not None else None
    turn._editor_output_pin = mention_target
    opening = await db.get(Message, turn_id) if turn_id is not None else None
    confirmation = ((opening.intent or {}) if opening is not None else {}).get("video_confirmation")
    turn.video_confirmation = confirmation
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
    # RETRY re-arms by construction); the interim_prose channel flushes the
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
        base_on_interim_prose = (
            _interim_prose_callback(db, turn.conversation_id, on_interim_prose, turn_id)
            if turn.project is not None
            else None
        )

        async def on_interim_prose_after_flush(text: str) -> None:
            if deferred.armed:
                await deferred.flush()
            if base_on_interim_prose is not None:
                await base_on_interim_prose(text)

        interim_prose_hook = on_interim_prose_after_flush
    else:
        # ADR-085: the interim_prose channel (persist + SSE forward) — a
        # project-less defensive turn has no conversation to persist into,
        # so the channel stays closed there.
        interim_prose_hook = (
            _interim_prose_callback(db, turn.conversation_id, on_interim_prose, turn_id)
            if turn.project is not None
            else None
        )
    from app.chat.conversation_context import ConversationContext, conversation_context_tool
    from app.chat.turn_tools import tools_for_bound_skill
    conversation_context = (
        ConversationContext(conversation_id=turn.conversation_id, owner_id=turn.user_id,
                            turn_id=turn_id, skill=getattr(turn, "skill", None))
        if turn_id is not None else None
    )
    turn._conversation_context = conversation_context
    context_tools = [conversation_context_tool()] if conversation_context is not None else []

    try:
        from app.chat.context import conversation_messages
        from app.chat.prompts import assemble_video_round
        from app.chat.readiness import creative_state_for_pending, infer_task_kind, settled_website_question
        from app.chat.speech_language import conversation_speech_language
        from app.pipeline.assets import urls_in_text

        website_question_settled = settled_website_question(recent, turn_id)

        def assemble_round(**facts):
            current_pending = (
                PendingPlan.model_validate(project.pending_brief)
                if isinstance(project.pending_brief, dict) else None
            )
            source_text = (
                text if infer_task_kind(text) == "website_promo"
                else (current_pending.prompt if current_pending is not None else "") or text
            )
            assembly = assemble_video_round({
                **facts,
                "mode": "conversation",
                "website_question_settled": website_question_settled,
                "skill": getattr(turn, "skill", None),
                "user_text": text,
                "source_text": source_text,
                "video_confirmation": confirmation,
                "production_requested": requested_video_production(text),
                "pending_question": lambda: turn.pending,
                "last_preview": getattr(turn, "_editor_last_preview", None),
                "recent_edit": getattr(turn, "_editor_recent", None),
                "editor_labels": turn.__dict__.setdefault("_editor_labels", {}),
                "target_hint": mention_target,
                "material_pending": bool(urls_in_text(text) or mentions),
                "creative_state": creative_state_for_pending(current_pending),
                "package_sessions": turn.__dict__.setdefault("_skill_package_sessions", {}),
            })
            turn._video_base_ref = (
                (assembly.caller_state or {}).get("video_target") or {}
            ).get("base_ref")
            return assembly

        result = await chat_intent_agent.call_loop(
            turn.execute,
            tools=[*tools_for_bound_skill(chat_intent_agent.tools, getattr(turn, "skill", None)), *context_tools],
            round_assembler=assemble_round,
            dialogue=conversation_messages(recent),
            speech_language_hint=conversation_speech_language(recent),
            message=turn.suggestion_note or "",
            context=turn.context,
            on_delta=on_delta,
            on_reasoning=on_reasoning,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_loop_event=on_loop_event,
            on_interim_prose=interim_prose_hook,
            should_stop_rejection=video_rejection_stop,
            refresh_context=context_reader,
            restore_context=conversation_context.restore if conversation_context else None,
            on_context_event=conversation_context.record if conversation_context else None,
            candidate_scope=CandidateScope(owner_id=str(user_id), conversation_id=str(turn.conversation_id)),
        )
    except LLMError as exc:
        logger.warning(
            "chat_turn_provider_failed",
            agent="chat_intent",
            conversation_id=str(turn.conversation_id),
            turn_id=str(turn_id) if turn_id is not None else None,
            user_key=exc.user_key,
            error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )
        capabilities = getattr(chat_intent_agent.client, "capabilities", None)
        if capabilities is None or not capabilities.supports_native_tools:
            raise  # the tier gate fails loud, never the ask-back line
        if turn._video_review_report is None:
            raise  # the localized provider failure line, never a false ask-back
        result = None
    outcome = await turn.finish(result)
    if (
        outcome[0] is not None
        and turn_id is not None
        and outcome[0] is not outcome[3]
    ):
        outcome[0].turn_id = turn_id
    return outcome



__all__ = ["run_propose_turn", "ChatTurn", "ProposeTurnOutcome"]
