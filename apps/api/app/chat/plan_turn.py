"""The plan path's tool-loop runner (ADR-077 判词② — T2a 内核半边).

The retired ``_plan_turn`` dispatch, re-homed: the intent router
closes its turn with ONE terminal tool call — the four actions' mechanical
translation (draft → ``present_plan``, ask → ``ask_user``, start →
``start_run``, answer → ``answer``) — and the guardrails live INSIDE the
tool executions:

- 出书门槛 = ``present_plan``'s in-execution validation (media without
  material / rootless + topic unasked → a REJECTION whose feedback names
  the right tool; rootless after the topic was asked → an accept carrying
  the code-composed draft-from-persona declaration);
- ``start_run`` still runs through ``answer_question`` → ``create_run`` —
  the only run birthplace, zero bypass, its transaction untouched;
- chain adjudication (``validate_task_list`` / ``check_transform_targets``)
  rejections ARE the loop's feedback — the retired funnel repair round's
  seat, now one bounded iteration each.

A rejected call writes nothing. An accepted call's writes are flush-only —
the caller commits (except ``start_run``, where ``answer_question`` commits,
unchanged). The envelope absorb (declared-material promotion + brief merge +
the pending-slot handshake) is idempotent per turn: it may run on several
iterations, it writes at most once, and every gate reads the ONE merged
brief (出书决策只看 brief).

Storage shapes preserved: docked rows and ``message.intent`` still carry
``InferredIntent`` dumps (built here from the accepted call's params plus
the turn's prose), the caption-mode stash stays a bare ``InferredIntent``
dump, and an ask turn's brief-only ``pending_brief`` row is byte-identical.
The 判词⑦ hybrid-flip machinery retired structurally — a tool call IS one
action; the impossible hybrid shapes have no wire form anymore (their
outcomes survive as rejections).

T2b 感知族 (ADR-077 判词②): the read tools (``app/chat/perception/``)
dispatch straight from ``execute`` — never a brief write, never an
outcome — and ride back as a ToolObservation the loop feeds back.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tool_loop import ToolObservation
from app.chat.exploration_tools import (
    EXPLORATION_TOOLS,
    ProposeCandidatesArgs,
    ProposePlansArgs,
    ProposeSelectsArgs,
    candidates_observation,
    selects_observation,
)
from app.chat.intent import intent_router
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.perception.executes import understanding_digest_lines
from app.chat.service import (
    _active_run_line,
    _ask_content,
    _bare_question,
    _build_caption_mode_question,
    _cannot_do_text,
    _caption_choice_is_meaningful,
    _checkpoint_callback,
    _compute_plan_reasons,
    _create_message,
    _detect_caption_mode,
    _dock_question,
    _draft_from_persona_echo,
    _has_resolved_caption_mode,
    _needs_caption_mode_question,
    _needs_media,
    _reminder_tail,
    _resolved_caption_mode,
    _safe_task_estimate,
    _topic_gate_question,
    answer_question,
    is_pending_plan,
    latest_pending_question,
    merge_brief,
    sync_plan_question,
)
from app.chat.system_status import observe_phase_callback
from app.models.schemas import (
    AnswerPayload,
    AssetStatus,
    AssetType,
    Brief,
    BriefSlot,
    BriefSlotSource,
    ChatRequest,
    InferredIntent,
    MaterialUnderstanding,
    PendingPlan,
    PlanAnswerArgs,
    PlanAskArgs,
    PresentPlanArgs,
    QuestionPayload,
    QuestionProposal,
    StartAnswerRequest,
)
from app.models.tables import Asset, GraphNode, Message, Persona, Project
from app.pipeline.asset_processing import has_any_text_material
from app.pipeline.assets import create_transcript_asset_from_text
from app.pipeline.exploration_store import (
    KIND_SELECT,
    STATE_DRAFT,
    STATE_READY,
    ContentPlanSpec,
    ExplorationRejected,
    plan_completeness_issues,
    propose_candidates,
    propose_plans,
    propose_selects,
    read_journey_evidence,
)
from app.pipeline.product_graph import EXPLORATION_NODE_TYPE
from app.pipeline.scope_compile import (
    ScopeCompileRejected,
    compile_plans,
    decision_package_plans,
)
from app.platform.project_context import resolve_default_persona
from app.tools import ToolRejected, validate_task_list

logger = structlog.get_logger()

# The return shape the service layer's callers hold (unchanged):
# (assistant message, started run id, answered task-book question,
# cascade-bailed run ids).
PlanTurnOutcome = tuple[Message, UUID | None, Message | None, list[UUID]]


@dataclass
class _PlanPreview:
    """The pre-flight compile's in-memory stand-in for a Content Plan row
    (R14 双门, iter-2 ③): the compile passes BEFORE the door births anything,
    so the duck-typed fields (id / state / spec) mirror what
    ``compile_plans`` reads off a real row."""

    id: str
    state: str
    spec: dict


class PlanTurn:
    """One plan-path turn: the pre-call assembly, the four tool executions,
    and the outcome mapping. Created by ``run_plan_turn``; one instance per
    turn (the idempotency guards are its fields)."""

    def __init__(
        self,
        db: AsyncSession,
        user_id: UUID,
        conversation,
        project: Project,
        request: ChatRequest,
        on_phase=None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.conversation_id = UUID(str(conversation.id))
        self.project = project
        self.request = request
        self.on_phase = on_phase
        # Turn state (filled by the assembly below and the executions):
        self.text = ""
        self.stored: PendingPlan | None = None
        self.pending_q: Message | None = None
        self.plan_pending = False
        self.assets: list[Asset] = []
        self.has_text_material = False
        self.persona: Persona | None = None
        self.infer_kwargs: dict[str, Any] = {}
        # Loop state:
        self.material_asset: Asset | None = None
        self.merged_brief: Brief | None = None
        self.settled_pending: Message | None = None
        self.outcome: PlanTurnOutcome | None = None
        self.saw_rootless_rejection = False
        self.echo_override: str | None = None
        self.reasons_extra: list[str] = []
        # 资产角色 (ADR-078 判词④): this turn's mention-settled exemplar pin
        # (None = no asset mention this turn — the stored plan's pins ride).
        self.mention_exemplar_id: str | None = None

    # ---- assembly (the retired _plan_turn's pre-call block, verbatim) ------

    async def assemble(self, recent: list[Message] | None) -> None:
        db, project, request = self.db, self.project, self.request
        text = request.message
        if not text.strip() and request.attachments:
            # Attachment-only turn (files staged in the overlay's input group,
            # sent with no text): the persisted user message stays empty (the
            # chips carry the record), but the inference needs honest words —
            # the files themselves are listed in the Assets context block.
            names = ", ".join(a.name for a in request.attachments)
            text = (
                f"(I just attached new source files: {names}. "
                "No note — treat them as material for what I asked, or ask what "
                "I'd like made from them.)"
            )
        self.text = text

        stored = (
            PendingPlan.model_validate(project.pending_brief)
            if isinstance(project.pending_brief, dict)
            else None
        )
        # ADR-052 B2 D2-C2: the accumulated prompt narrative is retired — the
        # brief is the dialog's structured state (code-merged), and this
        # turn's message is judged on its own words. The archive already holds
        # each turn as its own user message; stored.prompt stays the birth
        # prompt, frozen at the first dock (never re-accumulated).
        self.stored = stored

        # 插话支持 (ADR-053 R2): a still-open plain question rides the router's
        # context explicitly (the pending block) — a user-stated proposal for
        # ITS slot is the answer (code settles the row in the absorb below),
        # anything else is an interjection (the question stays open and the
        # answer tool's reply gets the reminder tail). A pending task_book is
        # this path's own confirmation target (G-1), never a judgment subject.
        pending_q = await latest_pending_question(db, self.conversation_id)
        # Remember a pending task_book before the null below: raising a fresh
        # plain question would supersede the plan row and orphan the
        # confirmation (S5, 2026-09-12) — the ask_user execution rejects
        # while either kind is pending.
        self.plan_pending = (
            pending_q is not None
            and pending_q.workflow_run_id is None
            and (pending_q.question or {}).get("kind") == "task_book"
        )
        if pending_q is not None and (
            pending_q.workflow_run_id is not None
            or (pending_q.question or {}).get("kind") != "question"
        ):
            pending_q = None
        self.pending_q = pending_q

        assets = list(
            (
                await db.execute(
                    select(Asset)
                    .where(
                        Asset.project_id == project.id,
                        Asset.file_url.isnot(None),
                    )
                    # Deterministic "first asset" for filename/excerpt picks —
                    # the repo convention (jobs.py / projects.py).
                    .order_by(Asset.created_at)
                )
            )
            .scalars()
            .all()
        )
        self.assets = assets
        first_file = next((a for a in assets if a.file_url), None)
        filename = first_file.file_url.rsplit("/", 1)[-1] if first_file else None
        # Multi-asset block (ADR-078): with ≥2 files the router must SEE the
        # roster to judge the remix shape (which is the user's material, which
        # the reference) — the single-file filename/excerpt surface stays for
        # the common case; this lists every file in upload order.
        asset_lines: list[str] | None = None
        if len(assets) > 1:
            lines = []
            for a in assets:
                name = a.file_url.rsplit("/", 1)[-1] if a.file_url else "(text)"
                kind_bits = [a.type.value]
                if a.duration_seconds:
                    kind_bits.append(f"{int(a.duration_seconds)}s")
                lang = (a.meta or {}).get("language")
                if lang:
                    kind_bits.append(str(lang))
                lines.append(f"- {name} ({' · '.join(kind_bits)})")
            asset_lines = lines
        # 资产角色 mention 结算 (判词④ — code settles, the LLM never pins):
        # an @asset mention on the PLAN path names the EXEMPLAR ("做成
        # @这个 那样" — the mentioned video is the reference whose craft the
        # run mirrors). The latest mention wins a re-pin; mentioning the
        # stored SOURCE re-points the roles (the old source seat clears —
        # one asset never holds both roles).
        for mention in request.mentions or []:
            if mention.type != "asset":
                continue
            mentioned = next(
                (a for a in assets if str(a.id) == mention.id), None
            )
            if mentioned is not None and mentioned.type == AssetType.VIDEO:
                self.mention_exemplar_id = str(mentioned.id)
        # The plan layer reads the material's opening, not just its filename
        # (track-model §7.4 折中版 — mechanical slice, zero extra LLM): the first
        # asset carrying text (transcript beats extracted_text), capped.
        material_excerpt = next(
            (
                excerpt
                for a in assets
                if (excerpt := (a.transcript or a.extracted_text or "").strip())
            ),
            None,
        )
        if material_excerpt:
            material_excerpt = material_excerpt[:800]
        # 信任锚注入 (ADR-083, 2026-09-17): the READY material understanding
        # rides the context at assemble time — a plain DB read off the
        # content-addressed row (zero LLM, zero extra round), so the echo's
        # judgment duty has top-tier semantic evidence in iteration 0
        # instead of needing a get_understanding detour (which would break
        # the speak-first streaming beat with a transition filler). Not
        # ready / stale shape → absent, the grounding hierarchy falls
        # through to the excerpt / the user's own words.
        understanding_lines: list[str] | None = None
        if assets:
            from app.pipeline.node_runners import (  # deferred: pipeline weight
                find_reusable_understanding,
            )
            from app.pipeline.step_context import asset_digest

            understanding_row = await find_reusable_understanding(
                db, project, asset_digest(assets)
            )
            if understanding_row is not None:
                try:
                    understanding_lines = understanding_digest_lines(
                        MaterialUnderstanding.model_validate(
                            understanding_row.payload
                        )
                    ) or None
                except Exception:  # noqa: BLE001 — a stale-shaped row reads as absent
                    understanding_lines = None

        # Readiness gate (I-PFA-07, 2026-09-18): the attached-but-unready fact
        # is CODE-stamped into the context — the router never infers readiness
        # from absent evidence (a missing excerpt/understanding used to be the
        # only signal, so the model faced the unready world alone and could
        # improvise「I can't read it」). Pasted-text material lands ready
        # (transcript at birth), so the predicate rides file assets only.
        processing_count = sum(
            1
            for a in assets
            if a.file_url
            and a.processing_status
            in (AssetStatus.PENDING, AssetStatus.PROCESSING)
        )
        failed_count = sum(
            1
            for a in assets
            if a.file_url and a.processing_status == AssetStatus.FAILED
        )
        material_pending_line: str | None = None
        if processing_count:
            material_pending_line = (
                f"Material status: {processing_count} uploaded file(s) are "
                "STILL PROCESSING — their content is not readable this turn "
                "(no transcript, no understanding yet). The content read "
                "lands automatically when processing finishes."
            )
        elif failed_count:
            material_pending_line = (
                f"Material status: {failed_count} uploaded file(s) FAILED "
                "processing — their content will not become readable."
            )

        recent_lines: list[str] = []
        for m in recent or []:
            attached = [a.get("name") for a in (m.attachments or []) if a.get("name")]
            if not m.content and not attached:
                continue
            line = f"- {m.role}: {(m.content or '')[:200]}"
            if attached:
                line += f" [attached: {', '.join(attached)}]"
            recent_lines.append(line)
        # The presented chain (ADR-043): the panel's current task list when the
        # caller sends one (hand edits ride along), else the stored plan's. The
        # intent router sees it as a JSON chain and re-emits the WHOLE refined chain
        # — panel edits survive because the LLM preserves what the message does
        # not revise (chat revisions always win; the field-level merge machinery
        # died with the slots grammar).
        prior = request.prior_intent or (stored.intent if stored else None)
        # The LLM revises the exact chain, not a prose digest — ship the JSON.
        presented_plan = (
            json.dumps([t.model_dump(mode="json") for t in prior.tasks], ensure_ascii=False)
            if prior is not None and prior.tasks
            else None
        )
        # The brief the router reads (ADR-052 B2): the stored brief with the
        # material state freshly code-stamped (the router reads it for the root
        # judgment, never proposes it). This turn's own proposal merges in the
        # absorb — LLM proposes, code decides.
        self.has_text_material = await has_any_text_material(db, UUID(str(project.id)))
        brief_in = (stored.brief if stored else Brief()).model_copy(deep=True)
        brief_in.material_state = BriefSlot(
            value=(
                "attached"
                if any(a.file_url for a in assets)
                else "pasted"
                if self.has_text_material
                else "none"
            ),
            source=BriefSlotSource.DEFAULT,
        )
        # Asking strategy ②'s pantry (C2): resolve the turn's persona so the
        # router can source concrete one-word option values from it (explicit
        # pick → the pending plan's → the project mount → the user default —
        # the same precedence resolve_run_persona stamps at start). Without
        # this block the "3 concrete options" rule had no material and
        # questions starved to bare text.
        persona_id = (
            request.persona_id
            or (stored.persona_id if stored else None)
            or project.persona_id
        )
        persona: Persona | None = None
        if persona_id:
            persona = (
                await db.execute(select(Persona).where(Persona.id == persona_id))
            ).scalar_one_or_none()
        if persona is None:
            persona = await resolve_default_persona(db, self.user_id)
        self.persona = persona
        self.infer_kwargs = dict(
            message=text,
            brief=brief_in,
            persona=persona,
            pending_question=pending_q,
            filename=filename,
            presented_plan=presented_plan,
            recent=recent_lines or None,
            # The transform-target rule's authoritative signal (同源语言护栏 —
            # the plan surface's only other language hint is the filename).
            file_language=(first_file.meta or {}).get("language") if first_file else None,
            material_excerpt=material_excerpt,
            understanding_lines=understanding_lines,
            asset_lines=asset_lines,
            material_pending_line=material_pending_line,
        )

    def _role_pins(self) -> dict[str, str | None]:
        """The role pins to persist on a PendingPlan write (判词④ — the same
        preserve law as persona_id: a turn that never touched the roles must
        not clobber an earlier settle). Mention this turn > stored."""
        stored = self.stored
        source = stored.source_asset_id if stored else None
        exemplar = stored.exemplar_asset_id if stored else None
        if self.mention_exemplar_id is not None:
            exemplar = self.mention_exemplar_id
            if source == exemplar:
                source = None  # one asset never holds both roles
        return {"source_asset_id": source, "exemplar_asset_id": exemplar}

    def _fire_mention_warm(self) -> None:
        """A mention-pinned exemplar warms its skeleton as the pin PERSISTS
        (the role question's answer has _stamp_role_pins; the mention has no
        settle branch of its own, and an already-processed asset's
        processing-completion seat has passed). Called after each PendingPlan
        write — the pin only earns its warm by landing. The warm re-guards
        everything itself (VIDEO / COMPLETED / reuse hit → early return)."""
        if self.mention_exemplar_id is None:
            return
        from app.pipeline.decompile import (  # deferred: pipeline edge
            fire_warm_craft_skeleton,
        )

        fire_warm_craft_skeleton(
            UUID(str(self.project.id)), UUID(self.mention_exemplar_id)
        )

    # ---- the envelope absorb (once per turn, idempotent) -------------------

    async def _absorb(self, brief: Brief | None, material_text: str | None) -> Brief:
        """The turn's envelope absorb — the retired pre-branch block, run at
        the head of every tool execution that carries the seats. Idempotent:
        the material promotion writes at most once per turn, the merge is a
        pure function of the stored brief + THIS call's proposal (the last
        call's merge is what a dock persists), the slot handshake settles the
        pending row once."""
        db = self.db
        # Declared-material promotion (2026-08-05 手测决策): the user explicitly
        # said "this is my transcript/content" — the pasted text becomes a real
        # TRANSCRIPT asset (visible, named). Never inferred from text length.
        if (
            self.material_asset is None
            and material_text
            and material_text.strip()
        ):
            self.material_asset = await create_transcript_asset_from_text(
                db, UUID(str(self.project.id)), self.user_id, material_text.strip()
            )
            self.assets.append(self.material_asset)

        # brief (ADR-052 B2): the call's update proposal lands by source
        # precedence, then the material state is code-stamped over it. Every
        # downstream decision — the ask-loop guard, the 出书门槛, the dock
        # write — reads this ONE merged brief (出书决策只看 brief).
        merged_brief = merge_brief(
            brief, self.stored.brief if self.stored else Brief()
        )
        merged_brief.material_state = BriefSlot(
            value=(
                "attached"
                if any(a.file_url for a in self.assets)
                else "pasted"
                if self.has_text_material or self.material_asset is not None
                else "none"
            ),
            source=BriefSlotSource.DEFAULT,
        )
        self.merged_brief = merged_brief

        # 插话判定结算 (ADR-053 R2): the router saw the pending question in
        # context; a user-stated proposal for ITS OWN slot is the answer —
        # code settles the row (freeform, the user's stated value) and the
        # enriched brief drives the gates below.
        pending_q = self.pending_q
        if pending_q is not None:
            p_slot = (pending_q.question or {}).get("slot")
            proposed_slot = (
                getattr(brief, p_slot, None)
                if p_slot and brief is not None
                else None
            )
            if (
                proposed_slot is not None
                and proposed_slot.source == BriefSlotSource.USER_STATED
                and isinstance(proposed_slot.value, str)
                and proposed_slot.value.strip()
            ):
                pending_q.answer = AnswerPayload(
                    kind="freeform",
                    text=proposed_slot.value.strip(),
                    answered_at=datetime.now(UTC),
                ).model_dump(mode="json")
                await db.flush()
                self.settled_pending = pending_q
                self.pending_q = None
        return merged_brief

    # ---- the loop's execute dispatch ----------------------------------------

    async def execute(self, name: str, params, prose: str) -> str | None | ToolObservation:
        """The LoopExecute seat: validate → (reject: feedback, zero writes) →
        accept: writes + the outcome stashed → None (terminal stop). A
        PERCEPTION call short-circuits the seats above: reads are dispatched
        to the family registry and ride back as a ToolObservation (the loop
        iterates — 终态工具一调即停 covers the terminal tools only)."""
        if name in PERCEPTION_TOOLS:
            return await run_perception_tool(self.db, self.project, name, params)
        if name in EXPLORATION_TOOLS:
            return await self._explore(name, params, prose)
        if name == "present_plan":
            assert isinstance(params, PresentPlanArgs)
            return await self._present_plan(params, prose)
        if name == "ask_user":
            assert isinstance(params, PlanAskArgs)
            return await self._ask_user(params, prose)
        if name == "start_run":
            return await self._start_run()
        if name == "answer":
            assert isinstance(params, PlanAnswerArgs)
            return await self._answer(params, prose)
        return f"unknown tool {name!r}"  # unreachable — the driver gates names

    async def _present_plan(self, params: PresentPlanArgs, prose: str) -> str | None:
        """draft → the plan docks. Guardrails first (a rejection writes
        nothing): the chain adjudication, then the 出书门槛."""
        db, project, stored = self.db, self.project, self.stored
        merged_brief = await self._absorb(params.brief, params.material_text)

        if not params.tasks:
            return (
                "empty task list — a plan needs at least one task. If one "
                "missing answer most decides quality, call ask_user; for a "
                "purely informational reply, call answer."
            )
        # Chain adjudication (ADR-043): the registry validates the proposed
        # task list — the rejection rides back as the loop's feedback (the
        # retired repair round's seat), then the call retries bounded. The
        # same-language adjudication rides the same door (2026-09-13): a
        # translate/dub target that IS the faced source language is doomed by
        # construction — the feedback names the fix ("中英双语 on an en source
        # → target zh") before the user ever confirms.
        from app.pipeline.morph import check_transform_targets
        from app.ui_locale import current_ui_language

        try:
            validate_task_list(params.tasks)
        except (ToolRejected, ValueError) as e:
            return f"{e} (available: {getattr(e, 'suggestions', [])})"
        try:
            await check_transform_targets(
                db,
                project,
                params.tasks,
                zh=(current_ui_language() or "").startswith("zh"),
            )
        except (ToolRejected, ValueError) as e:
            return str(e)

        # 出书门槛 (ADR-052 B2 D2-C2 — the gate reads only the merged brief +
        # the adjudicated chain):
        #  - media-needing chain with material "none" and no plan on the table →
        #    the missing root is the material itself: REJECT, the model answers
        #    with the upload guidance in its own voice (the retired code line's
        #    disclosure payload survives as the feedback's instruction);
        #  - rootless (no topic / no material / no explicit grounded recipe) →
        #    REJECT toward ask_user slot='topic' (the topic asks once);
        #  - still rootless after the topic was asked → ACCEPT and dock with
        #    the code-composed draft-from-persona declaration (提问策略③ — a
        #    code-forced dock never borrows the LLM's voice).
        plan_on_table = stored is not None and stored.intent is not None
        media_blocked = (
            not plan_on_table
            and merged_brief.material_state.value == "none"
            and any(_needs_media(t.tool) for t in params.tasks)
        )
        if media_blocked:
            return (
                "media-needing work (clips / dub / subtitles) but no source "
                "material is attached or pasted — the missing root is the "
                "material itself. Do NOT present this plan: call answer and "
                "tell the user, in their language, that clips and voice dub "
                "need a video, audio, or image upload — they can upload one "
                "or paste their transcript to unlock them, or ask for the "
                "text work only."
            )
        has_root = (
            bool((merged_brief.topic.value or "").strip())
            # S2 语义缝 (2026-09-12): a topic the model INFERRED after the
            # user skipped the topic ask is not a root — the skip chose
            # the default path (draft-from-persona, reason + code echo),
            # and an inferred re-root silently bypasses both. Only the
            # user's own words re-root a skipped slot. (With material
            # attached the next clause roots the plan anyway, so the
            # infer-from-material path is untouched.)
            and (
                merged_brief.topic.source == BriefSlotSource.USER_STATED
                or "topic" not in merged_brief.asked
            )
        ) or (
            merged_brief.material_state.value != "none"
            or (
                params.tasks_explicit
                and bool((params.specific_instruction or "").strip())
            )
        )
        if not has_root and "topic" not in merged_brief.asked:
            self.saw_rootless_rejection = True
            return (
                "the brief has no root (no topic, no material, no explicitly "
                "named grounded recipe) and the topic was never asked — a "
                "rootless plan never docks. Call ask_user with slot='topic' "
                "asking the ONE topic question (options from the persona "
                "pantry; the default path = draft from the persona's style)."
            )
        if not has_root:
            # Asked once, still rootless → the default path docks: the
            # chain is the LLM's (registry-adjudicated), the declaration
            # is code.
            self.reasons_extra = ["draft_from_persona"]
            self.echo_override = _draft_from_persona_echo(self.text)

        # The intent object the storage shapes are built from (the accepted
        # call's params + the turn's echo — the same fields the action
        # union carried).
        caption_mode = params.caption_mode
        echo = self.echo_override if self.echo_override is not None else prose
        reasons = await _compute_plan_reasons(db, project, InferredIntent(
            action="draft",
            tasks=params.tasks,
            specific_instruction=params.specific_instruction,
            tasks_explicit=params.tasks_explicit,
            caption_mode=caption_mode,
            brief=params.brief,
            name=params.name,
        ))
        reasons = [*reasons, *self.reasons_extra]

        # A turn that omits persona_id must not clobber the persona choice an
        # earlier turn made.
        persona_id = self.request.persona_id
        if persona_id is None and isinstance(project.pending_brief, dict):
            persona_id = project.pending_brief.get("persona_id")

        # Derived preview (ADR-043): dry-run the chain through compile_graph and
        # project what it will make — the plan card's "you'll get" section. A
        # chain that can't compile here (e.g. transform with no media anywhere)
        # still docks, flagged by its reason — the birthplace rejects for real.
        from app.pipeline.orchestrator import derive_plan_preview

        try:
            derived = await derive_plan_preview(db, project, params.tasks)
        except (ToolRejected, ValueError):
            derived = []
        # Dock 载荷的估价面 (BILLING §7): the same dry-run compile's credits
        # quotation (total + per-task marginal), degraded exactly like the
        # preview — an unquotable/uncompilable chain docks quote-less.
        task_estimate = await _safe_task_estimate(db, project, params.tasks)

        # The late-turn guard: a concurrent Start committed while this refine
        # was in flight — docking now would raise a plan over an active
        # run (the zombie dock). Degrade to the active-run line.
        active_line = await _active_run_line(db, project, self.text)
        if active_line is not None:
            assistant_message = await _create_message(
                db, self.conversation_id, "assistant", active_line
            )
            self.outcome = (assistant_message, None, self.settled_pending, [])
            return None
        # Caption mode for captioned-video runs (Phase 1 plan-path fix,
        # 2026-08-25, RECIPES §4.7): dock the bilingual/source/target choice
        # before the task_book; the accepted call's InferredIntent dump rides
        # the question's `intent` field, the answer path replays it verbatim
        # back into PendingPlan.
        if (
            _needs_caption_mode_question(params.tasks)
            and caption_mode is None
            and _detect_caption_mode(self.text) is None
            and _detect_caption_mode(params.specific_instruction or "") is None
            and not _has_resolved_caption_mode(project)
        ):
            if await _caption_choice_is_meaningful(db, project, params.tasks):
                caption_question = _build_caption_mode_question(self.text)
                stashed_intent = InferredIntent(
                    action="draft",
                    tasks=params.tasks,
                    answer=echo,
                    specific_instruction=params.specific_instruction,
                    tasks_explicit=params.tasks_explicit,
                    brief=params.brief,
                    material_text=params.material_text,
                    name=params.name,
                ).model_dump(mode="json")
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
                    intent=stashed_intent,
                )
                self.outcome = (
                    assistant_message, None, self.settled_pending, bailed_run_ids
                )
                return None
            # §2.3/D4 (2026-08-28): no distinct alt language exists (the source
            # material's language equals every candidate) — bilingual would
            # print one language twice. Skip the question entirely and stamp
            # source_only; the run falls through to the plan dock.
            caption_mode = "source_only"
        # Caption-mode keyword auto-classification: an unambiguous bilingual
        # keyword ("双语" / "bilingual" / "中英对照" / "双语字幕" / "中英双语")
        # stamps the mode even when the call didn't set it. Source/target-only
        # keywords stay unset here — they're ambiguous without knowing the
        # source language, the chat question handles them.
        keyword_mode = _detect_caption_mode(self.text)
        if keyword_mode is not None and caption_mode is None:
            caption_mode = keyword_mode
        # Inherit the answered caption mode before the pending_brief write
        # (2026-08-29 追问丢答 root-fix): the fresh call's caption_mode is
        # None on any refinement turn that doesn't re-mention it — without the
        # inherit, "answer bilingual → 改成 5 张 → Start" landed a run with no
        # caption_mode and the NEXT turn re-asked the already-answered
        # question. Precedence: call-set > fresh keyword > stashed answer.
        if caption_mode is None:
            stashed_mode = _resolved_caption_mode(project)
            if stashed_mode is not None:
                caption_mode = stashed_mode
        # Inherit the previous dock's NAME on an identical-chain re-dock
        # (2026-09-09 取证): a bare confirmation the router misjudged as a
        # draft re-proposes the SAME chain unnamed — the inherited name IS the
        # LLM's own earlier naming of the same work, preserving it invents
        # nothing.
        name = params.name
        if (
            not (name or "").strip()
            and stored is not None
            and stored.intent is not None
            and (stored.intent.name or "").strip()
            and [t.model_dump(mode="json") for t in params.tasks]
            == [t.model_dump(mode="json") for t in stored.intent.tasks]
        ):
            name = stored.intent.name

        intent = InferredIntent(
            action="draft",
            tasks=params.tasks,
            answer=echo,
            specific_instruction=params.specific_instruction,
            tasks_explicit=params.tasks_explicit,
            caption_mode=caption_mode,
            brief=params.brief,
            material_text=params.material_text,
            name=name,
        )
        # The birth prompt freezes at the first dock (stored.prompt wins on every
        # later write) — the brief is the accumulated state now, the prompt is
        # only the plan's birth narrative (Start's instruction fallback).
        birth_prompt = stored.prompt if stored and stored.prompt else self.text
        # Phase 3 Batch B ③: the retired "drafting" System Status label used
        # to fire here — the draft ACTIVITY frame (opened at this call's
        # name-known beat, settled at its acceptance) is the work's only
        # user-safe face now (三通道分家).
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=intent,
            # brief (ADR-052 B2): the ONE merged brief — the call's update
            # landed by source precedence + the material state code-stamped in
            # the absorb; the gate and the ask execution read this same object.
            brief=merged_brief,
            reasons=reasons,
            persona_id=persona_id,
            derived=derived,
            **self._role_pins(),
        ).model_dump(mode="json")
        self._fire_mention_warm()
        bailed_run_ids = await sync_plan_question(
            db, self.user_id, project, intent, birth_prompt, reasons=reasons,
            derived=derived,
            brief=merged_brief,
            echo=echo,
            estimate=task_estimate,
        )
        question = await latest_pending_question(db, self.conversation_id)
        assert question is not None  # sync_plan_question just docked it
        self.outcome = (question, None, self.settled_pending, bailed_run_ids)
        return None

    # ---- the exploration seats (iter-2 ③/⑤ — ADR-088 旅程四 chain) -----------

    async def _explore(
        self, name: str, params, prose: str
    ) -> str | None | ToolObservation:
        """The discovery chain's dispatch (R2 免费探索区连续工作 — one turn
        carries search → candidates → selects → plans): candidates/selects
        ride back as observations (NON-terminal, the loop iterates; the
        observation builders are the harness seat's ONE wording);
        propose_plans is TERMINAL — landing the plans compiles and docks
        the decision package, which IS the paid-boundary stop (R15)."""
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
            return ToolObservation(text=selects_observation(born))
        if name == "propose_plans":
            assert isinstance(params, ProposePlansArgs)
            return await self._propose_plans(params, prose)
        return f"unknown exploration tool {name!r}"  # unreachable — gated above

    async def _propose_plans(self, params: ProposePlansArgs, prose: str) -> str | None:
        """plans → the decision package docks (ADR-089 §4 R16, iter-2 ③).

        双门 (R14): the PRE-FLIGHT compile runs BEFORE the door birth — an
        uncompilable package rejects back into the loop with zero writes
        (an uncompilable plan never reaches the canvas or the dock). Only
        then does the exploration door birth the rows, and the dock carries
        the three faces: the plans reading layer + the compiled task
        evidence + the credits quote (费用语义五面)."""
        db, project = self.db, self.project
        merged_brief = await self._absorb(None, None)

        # Journey resolution: the params carry select ids and the journey
        # rides structurally from them (one call plans one journey — the
        # door's own law, mirrored here so the pre-flight has its evidence).
        select_ids = [UUID(str(p.select_id)) for p in params.plans]
        rows = list(
            (
                await db.execute(
                    select(GraphNode).where(
                        GraphNode.project_id == project.id,
                        GraphNode.type == EXPLORATION_NODE_TYPE,
                        GraphNode.id.in_(select_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {str(n.id): n for n in rows}
        journey_ids: set[str] = set()
        for sid in select_ids:
            row = by_id.get(str(sid))
            if row is None or (row.spec or {}).get("exploration_kind") != KIND_SELECT:
                return (
                    f"select: node {sid} is not one of this project's "
                    "selects — re-read the propose_selects observation."
                )
            journey_ids.add(str(row.journey_id))
        if len(journey_ids) > 1:
            return (
                "propose_plans: one call plans one journey — the selects "
                "span two. Split the call."
            )
        journey_id = UUID(journey_ids.pop())
        selects, candidate_sets = await read_journey_evidence(
            db, UUID(str(project.id)), journey_id
        )

        persona_id = UUID(str(self.persona.id)) if self.persona is not None else None
        # The pre-flight compile (R12 编译移出 LLM): in-memory previews of
        # the rows the door WOULD birth (same completeness self-check, same
        # states) — a rejection here writes nothing.
        previews: list[_PlanPreview] = []
        for p in params.plans:
            issues = plan_completeness_issues(p.outputs)
            payload = ContentPlanSpec(
                select_id=str(p.select_id),
                title=p.title.strip(),
                outputs=p.outputs,
                persona_id=str(persona_id) if persona_id else None,
            ).model_dump()
            if issues:
                payload["issues"] = issues
            previews.append(
                _PlanPreview(
                    id=f"preview:{p.select_id}",
                    state=STATE_DRAFT if issues else STATE_READY,
                    spec=payload,
                )
            )
        from app.pipeline.derivative_dispatch import (  # deferred: pipeline weight
            project_source_language,
        )
        from app.pipeline.morph import check_transform_targets
        from app.ui_locale import current_ui_language

        try:
            compiled = compile_plans(
                previews,
                selects,
                candidate_sets,
                source_language=await project_source_language(db, project),
                default_language=project.language or current_ui_language() or "en",
            )
        except ScopeCompileRejected as e:
            return str(e)
        # The router-drafted dock's own backstop rides too (同源语言护栏 etc.).
        try:
            await check_transform_targets(
                db,
                project,
                compiled,
                zh=(current_ui_language() or "").startswith("zh"),
            )
        except (ToolRejected, ValueError) as e:
            return str(e)

        # Pre-flight passed — the door births the rows (its validation
        # re-runs as the authority; a door rejection rides back as the echo).
        try:
            born = await propose_plans(
                db,
                project,
                plans=[p.model_dump() for p in params.plans],
                persona_id=persona_id,
            )
        except ExplorationRejected as e:
            return f"The door rejected the proposal: {e}"

        # Caption form for quote cards: named on a quotes output → stamped
        # onto the intent (the same field the caption question's answer
        # stamps); unnamed = the runtime default, never invented.
        caption_mode = next(
            (
                o.caption_mode
                for p in params.plans
                for o in p.outputs
                if o.kind == "quotes" and o.caption_mode
            ),
            None,
        )
        intent = InferredIntent(
            action="draft",
            tasks=compiled,
            answer=prose,
            caption_mode=caption_mode,
            name=params.name or None,
        )
        reasons = await _compute_plan_reasons(db, project, intent)
        from app.pipeline.orchestrator import derive_plan_preview

        try:
            derived = await derive_plan_preview(db, project, compiled)
        except (ToolRejected, ValueError):
            derived = []
        task_estimate = await _safe_task_estimate(db, project, compiled)

        # The late-turn guard (same zombie-dock law as present_plan): a
        # concurrent Start committed while this turn was in flight — docking
        # now would raise a plan over an active run.
        active_line = await _active_run_line(db, project, self.text)
        if active_line is not None:
            assistant_message = await _create_message(
                db, self.conversation_id, "assistant", active_line
            )
            self.outcome = (assistant_message, None, self.settled_pending, [])
            return None

        # The birth prompt freezes at the first dock (stored.prompt wins on
        # every later write) — the same preserve law as present_plan.
        birth_prompt = (
            self.stored.prompt if self.stored and self.stored.prompt else self.text
        )
        # 决策包阅读层 (R16): the Content Plans ride BOTH the pending-brief
        # row (the restore path reads it) and the dock payload (the live
        # envelope) — one stamp, two seats.
        package_plans = decision_package_plans(born)
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=intent,
            brief=merged_brief,
            reasons=reasons,
            persona_id=persona_id,
            derived=derived,
            plans=package_plans,
            **self._role_pins(),
        ).model_dump(mode="json")
        self._fire_mention_warm()
        bailed_run_ids = await sync_plan_question(
            db,
            self.user_id,
            project,
            intent,
            birth_prompt,
            reasons=reasons,
            derived=derived,
            brief=merged_brief,
            echo=prose,
            estimate=task_estimate,
            plans=package_plans,
        )
        question = await latest_pending_question(db, self.conversation_id)
        assert question is not None  # sync_plan_question just docked it
        self.outcome = (question, None, self.settled_pending, bailed_run_ids)
        return None

    async def _ask_user(self, params: PlanAskArgs, prose: str) -> str | None:
        """ask → the ONE question docks through the ask_user machinery.
        Guards first: the pending-question law and the asked-roll bound
        the loop."""
        stored = self.stored
        merged_brief = await self._absorb(params.brief, params.material_text)
        if not params.question.strip():
            return (
                "empty question — speak the framing as your message text and "
                "pass the ONE bare question, or call present_plan / answer "
                "instead."
            )
        # 判词⑦ 扩座 (2026-09-12, S5) as a REJECTION (its structural form):
        # ANY ask while a question is still pending is an interjection, never
        # a new dock — docking supersedes the pending row, and for a
        # task_book that orphans the confirmation.
        if self.plan_pending or self.pending_q is not None:
            return (
                "a question of yours is still awaiting the user's answer — "
                "this message is an interjection, not a new question. Call "
                "answer with your reply instead (the pending question stays "
                "open and the code adds the reminder tail); never raise a "
                "second question while one is pending."
            )
        if params.slot is not None and params.slot in merged_brief.asked:
            # The ask loop is bounded (一轮一问决定槽, each slot asks at most
            # once): the router re-asked an already-asked slot — the turn is
            # a plan turn; the 出书门槛 docks the draft-from-persona plan
            # instead of looping the question.
            return (
                f"slot '{params.slot}' was already asked once this plan "
                "phase — each slot asks at most once. Call present_plan to "
                "dock the plan now (the gate handles rootlessness)."
            )
        # ask 一等动作 (ADR-052 B2, 案 A 双实例): the pre-run router's ONE
        # question docks through the same machinery the chat path's ask_user
        # uses — with the plan-path handshake on the payload (slot → the
        # answer backfills the brief user-stated; default_path → the dock's
        # muted second line). The brief merge lands as a brief-only row: the
        # stored plan's intent is preserved verbatim (an ask never clobbers
        # the plan), and a fresh project's row carries intent=None (never
        # startable).
        if params.slot is not None:
            merged_brief.asked = [*merged_brief.asked, params.slot]
        if params.slot == "asset_role":
            # 资产角色消歧 (ADR-078 判词④): the question's options are
            # CODE-BUILT from the project's videos (option id = asset id,
            # label = filename) — the LLM frames the speech, code guarantees
            # the ids resolve at the answer's settle. Fewer than two videos =
            # nothing to disambiguate: reject back into the loop.
            from app.chat.service import _build_role_question

            role_question = _build_role_question(self.text, self.assets)
            if role_question is None:
                return (
                    "fewer than two video files are attached — there is no "
                    "role ambiguity to ask about. Call present_plan with the "
                    "chain, or answer."
                )
            params = params.model_copy(
                update={
                    "question": role_question.question,
                    "options": role_question.options,
                    "allow_freeform": role_question.allow_freeform,
                    "default_path": role_question.default_path or params.default_path,
                }
            )
        self.project.pending_brief = PendingPlan(
            # The birth prompt stays frozen (stored.prompt wins) — the
            # accumulated narrative retired with the brief switch.
            prompt=stored.prompt if stored and stored.prompt else self.text,
            intent=stored.intent if stored else None,
            brief=merged_brief,
            reasons=stored.reasons if stored else [],
            persona_id=(
                self.request.persona_id
                or (stored.persona_id if stored else None)
            ),
            derived=stored.derived if stored else [],
            **self._role_pins(),
        ).model_dump(mode="json")
        self._fire_mention_warm()
        # ask 三分解剖 (2026-09-08): the row's content carries the framing
        # prose (解剖 ① — it streams as the turn's echo and replays in the
        # flow); the bare question rides the payload (解剖 ② — dock title,
        # QA archive, reminder tail). Prose-less asks fall back to content =
        # the bare question, the legacy shape every consumer still reads.
        ask = QuestionProposal(
            prose=prose or "",
            question=params.question,
            options=params.options,
            allow_freeform=params.allow_freeform,
            slot=params.slot,
            default_path=params.default_path,
        )
        intent = InferredIntent(
            action="ask",
            ask=ask,
            brief=params.brief,
            material_text=params.material_text,
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
                slot=params.slot,
                default_path=params.default_path,
            ),
            intent=intent.model_dump(mode="json"),
        )
        self.outcome = (assistant_message, None, self.settled_pending, bailed_run_ids)
        return None

    async def _start_run(self) -> str | None:
        """start → the docked plan is answered kind=start (G-1 path: the
        run comes from the only birthplace, answer_question — which commits;
        zero bypass)."""
        db, stored = self.db, self.stored
        pending_question = await latest_pending_question(db, self.conversation_id)
        if (
            is_pending_plan(pending_question)
            and stored is not None
            and stored.intent is not None
        ):
            answered, _follow_up = await answer_question(
                db, self.user_id, UUID(str(pending_question.id)),
                # The review panel's edited plan rides along (typed Start
                # parity): dropping prior_intent here would execute the
                # stored chain and silently discard the user's panel edits.
                StartAnswerRequest(
                    kind="start",
                    intent=self.request.prior_intent,
                ),
            )
            # answer_question commits — the run, the answer and the cleared
            # pending brief land in one transaction.
            self.outcome = (answered, UUID(str(answered.workflow_run_id)), answered, [])
            return None
        if stored is not None and stored.intent is not None:
            # Nothing startable right now. Never overwrite a stored plan
            # with a start-call misfire: re-dock the stored plan unchanged.
            # Unless a run started concurrently — then the plan is moot and
            # re-docking would raise a plan over an active run.
            active_line = await _active_run_line(db, self.project, self.text)
            if active_line is not None:
                assistant_message = await _create_message(
                    db, self.conversation_id, "assistant", active_line
                )
                self.outcome = (assistant_message, None, self.settled_pending, [])
                return None
            bailed_run_ids = await sync_plan_question(
                db, self.user_id, self.project, stored.intent, stored.prompt,
                reasons=stored.reasons, derived=stored.derived,
                brief=stored.brief,
                echo=stored.intent.answer,
                estimate=await _safe_task_estimate(db, self.project, stored.intent.tasks),
            )
            question = await latest_pending_question(db, self.conversation_id)
            assert question is not None  # sync_plan_question just docked it
            self.outcome = (question, None, self.settled_pending, bailed_run_ids)
            return None
        return (
            "no plan is on the table — nothing to start. If the user "
            "wants work, call present_plan with the chain; if one missing "
            "answer decides quality, call ask_user. A start call can never "
            "create a plan."
        )

    async def _answer(self, params: PlanAnswerArgs, prose: str) -> str | None:
        """answer → a plain assistant message; the stored plan stays
        untouched. The envelope seats still absorb (an answer can carry the
        user's declared material)."""
        await self._absorb(params.brief, params.material_text)
        if not prose.strip():
            return (
                "an empty reply says nothing — speak the answer as your "
                "message text, then call answer."
            )
        # Capability question: the reply lands as a plain assistant message
        # and the stored plan stays untouched — an answer turn never
        # overwrites the plan the user is confirming. When a question
        # survived the turn unsettled (an interjection, ADR-053 R2), the
        # reply ends with the code-composed reminder tail (the question +
        # its default path — never the LLM's voice).
        content = prose
        if self.pending_q is not None:
            content += _reminder_tail(
                self.text,
                _bare_question(self.pending_q),
                (self.pending_q.question or {}).get("default_path"),
            )
        assistant_message = await _create_message(
            self.db, self.conversation_id, "assistant", content
        )
        self.outcome = (assistant_message, None, self.settled_pending, [])
        return None

    # ---- the outcome mapping -------------------------------------------------

    async def finish(self, result) -> PlanTurnOutcome:
        """LoopResult → the caller's 4-tuple. An accepted execution stashed
        its outcome already; the bare reply and the exhaustion degrade land
        here (an honest degrade, never a fabricated success)."""
        if self.outcome is not None:
            return self.outcome
        if not result.exhausted:
            # The bare final reply (no tool called) — the read-tolerant
            # answer floor: the prose IS the reply.
            content = result.prose.strip() or _cannot_do_text(self.text)
            if self.pending_q is not None:
                content += _reminder_tail(
                    self.text,
                    _bare_question(self.pending_q),
                    (self.pending_q.question or {}).get("default_path"),
                )
            assistant_message = await _create_message(
                self.db, self.conversation_id, "assistant", content
            )
            return assistant_message, None, self.settled_pending, []
        # Exhaustion — every call rejected. When the rootless rejection was
        # among them, the code-composed topic question docks (the asked roll
        # stamped — the bound holds); anything else degrades to the
        # cannot-do line. Never a docked broken plan.
        logger.info(
            "plan_turn_loop_exhausted",
            calls=result.calls,
            rootless=self.saw_rootless_rejection,
        )
        if self.saw_rootless_rejection:
            stored = self.stored
            merged_brief = self.merged_brief or Brief()
            merged_brief.asked = [*merged_brief.asked, "topic"]
            self.project.pending_brief = PendingPlan(
                prompt=stored.prompt if stored and stored.prompt else self.text,
                intent=stored.intent if stored else None,
                brief=merged_brief,
                reasons=stored.reasons if stored else [],
                persona_id=(
                    self.request.persona_id
                    or (stored.persona_id if stored else None)
                ),
                derived=stored.derived if stored else [],
                **self._role_pins(),
            ).model_dump(mode="json")
            self._fire_mention_warm()
            topic_ask = _topic_gate_question(self.text)
            topic_intent = InferredIntent(
                action="ask",
                ask=QuestionProposal(
                    question=topic_ask["question"],
                    options=[],
                    allow_freeform=True,
                    slot="topic",
                    default_path=topic_ask["default_path"],
                ),
            )
            assistant_message, bailed_run_ids = await _dock_question(
                self.db,
                self.conversation_id,
                topic_ask["question"],
                QuestionPayload(
                    kind="question",
                    question=topic_ask["question"],
                    options=[],
                    allow_freeform=True,
                    slot="topic",
                    default_path=topic_ask["default_path"],
                ),
                intent=topic_intent.model_dump(mode="json"),
            )
            return assistant_message, None, self.settled_pending, bailed_run_ids
        assistant_message = await _create_message(
            self.db, self.conversation_id, "assistant", _cannot_do_text(self.text)
        )
        return assistant_message, None, self.settled_pending, []


async def run_plan_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation,
    project: Project,
    request: ChatRequest,
    recent: list[Message] | None = None,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_checkpoint=None,
    on_loop_event=None,
) -> PlanTurnOutcome:
    """The plan path's turn: assemble → the bounded tool loop → the outcome
    mapping. ``intent_router`` provider failures propagate as LLMError — no
    fabricated default plan (2026-08-14 裁定); the route boundary turns it
    into a 502 with the localized provider line. on_delta streams the prose
    channel (it IS the reply now); on_tool_call/on_tool_ready carry the
    structure frames (the phase beat / the question preview); on_phase labels
    the real phase switches; on_checkpoint (ADR-085) is the checkpoint
    channel's SSE seat — the runner wraps it with persistence (the checkpoint
    row is this turn's own message, intent type 'checkpoint'). None = the
    one-shot path."""
    turn = PlanTurn(db, user_id, conversation, project, request, on_phase=on_phase)
    await turn.assemble(recent)
    result = await intent_router.call_loop(
        turn.execute,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_observe=observe_phase_callback(on_phase),
        on_checkpoint=_checkpoint_callback(db, turn.conversation_id, on_checkpoint),
        on_loop_event=on_loop_event,
        **turn.infer_kwargs,
    )
    return await turn.finish(result)


__all__ = ["run_plan_turn", "PlanTurn", "PlanTurnOutcome"]
