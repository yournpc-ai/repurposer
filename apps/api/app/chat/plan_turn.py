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
the turn's prose), and an ask turn's brief-only ``pending_brief`` row is
byte-identical. The 判词⑦ hybrid-flip machinery retired structurally — a
tool call IS one action; the impossible hybrid shapes have no wire form
anymore (their outcomes survive as rejections).

T2b 感知族 (ADR-077 判词②): the read tools (``app/chat/perception/``)
dispatch straight from ``execute`` — never a brief write, never an
outcome — and ride back as a ToolObservation the loop feeds back.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tool_loop import (
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
from app.chat.intent import intent_router
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.perception.executes import speaker_form_lines, understanding_digest_lines
from app.chat.service import (
    _active_run_line,
    _ask_content,
    _auto_start_docked_plan,
    _bare_question,
    _cannot_do_text,
    _checkpoint_callback,
    _compute_plan_reasons,
    _create_message,
    _derive_chat_caption_mode,
    _dock_question,
    _draft_from_persona_echo,
    _needs_media,
    _prefers_zh,
    _estimate_tail,
    _reminder_tail,
    _safe_task_estimate,
    _topic_gate_question,
    answer_question,
    is_pending_plan,
    latest_pending_question,
    merge_brief,
    resolve_confirmation_need,
    resolve_suggestion_note,
    sync_plan_question,
)
from app.models.schemas import (
    AnswerPayload,
    AssetStatus,
    AssetType,
    Brief,
    BriefSlot,
    BriefSlotSource,
    ChatRequest,
    DesignStoryboardArgs,
    InferredIntent,
    MaterialUnderstanding,
    PendingPlan,
    PlanAnswerArgs,
    PlanAskArgs,
    PresentPlanArgs,
    QuestionPayload,
    QuestionProposal,
    StartAnswerRequest,
    StartRunArgs,
    resolve_recommended_id,
)
from app.models.tables import Asset, ExplorationRow, Message, Persona, Project, User
from app.pipeline.asset_processing import has_any_text_material
from app.pipeline.assets import (
    asset_text_content,
    create_transcript_asset_from_text,
    create_web_page_assets_committed_from_urls,
    prime_web_page_captures_from_text,
)
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
from app.pipeline.scope_compile import decision_package_plans
from app.platform.project_context import resolve_default_persona
from app.platform.user_settings import read_confirmation_prefs
from app.tools import ToolRejected, validate_task_list

logger = structlog.get_logger()

# The return shape the service layer's callers hold (unchanged):
# (assistant message, started run id, answered task-book question,
# cascade-bailed run ids). The assistant message is None when the turn
# closes without a row (the degrade paths land their own shape).
PlanTurnOutcome = tuple[Message | None, UUID | None, Message | None, list[UUID]]


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
        on_activity=None,
        on_candidates=None,
        on_row_append=None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.conversation_id = UUID(str(conversation.id))
        self.project = project
        self.request = request
        self.on_phase = on_phase
        # 工作会话里程碑通道 (iter-2 ⑥): the SSE pump's projector feed —
        # called at the exploration door's successes; None = the one-shot
        # path (no stream, no frames).
        self.on_activity = on_activity
        self.on_candidates = on_candidates
        # Retired with the program-markdown publication (2026-10-18 裁决):
        # the design beat no longer lands its own row mid-turn — the
        # presenting model's ONE message carries the board. The param stays
        # for the runner's signature parity (the channel is generic).
        self.on_row_append = on_row_append
        # 呈现关联挂号 (2026-10-18 裁决): set by a successful design execute
        # ({"version": N}); the turn's finish stamps the TERMINAL speech
        # row's id onto film_presented_message_id — only after that row
        # actually persists, version-guarded (presentation_stamp_update).
        self._presentation_pending: dict | None = None
        # Turn state (filled by the assembly below and the executions):
        self.text = ""
        self.stored: PendingPlan | None = None
        self.pending_q: Message | None = None
        self.plan_pending = False
        self.assets: list[Asset] = []
        self.has_text_material = False
        self.persona: Persona | None = None
        # (execution, credits) — the turn's confirmation prefs (ADR-117 D1),
        # loaded in assemble; default ("auto", "auto") until then.
        self.confirmation: tuple[str, str] = ("auto", "auto")
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
        self.deferred: DeferredFrames | None = None
        # 建议点选 provenance (ADR-099 §4): this turn's message IS a
        # suggestion pick → the resolution note rides into the router's
        # message (never into self.text — the gates and keyword detectors
        # read the user's own words only).
        self.suggestion_note: str | None = None

    # ---- assembly (the retired _plan_turn's pre-call block, verbatim) ------

    def _current_pending(self) -> PendingPlan | None:
        """The ONE current-PendingPlan seat for this turn. The plan path's
        loop is non-terminal through design_storyboard, so a dock/re-dock
        seat that follows the design beat must read the version that beat
        just persisted — never the turn-assembly snapshot."""
        self.stored = (
            PendingPlan.model_validate(self.project.pending_brief)
            if isinstance(self.project.pending_brief, dict)
            else None
        )
        return self.stored

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

        # 建议点选落地解算 (ADR-099 §4): a pick-carrying request resolves
        # its provenance NOW — the note (fresh = the control event named;
        # stale = WHAT moved + re-grounding advice) rides the router-facing
        # message below; an unresolvable ref simply yields no note.
        if request.suggestion_ref is not None:
            self.suggestion_note = await resolve_suggestion_note(
                db,
                self.conversation_id,
                UUID(str(project.id)),
                request.suggestion_ref,
            )

        stored = self._current_pending()
        # ADR-052 B2 D2-C2: the accumulated prompt narrative is retired — the
        # brief is the dialog's structured state (code-merged), and this
        # turn's message is judged on its own words. The archive already holds
        # each turn as its own user message; stored.prompt stays the birth
        # prompt, frozen at the first dock (never re-accumulated).

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

        # 方向回合采集预热 (2026-10-17 用户拍板): a URL the user's own
        # message carries births its WEB_PAGE capture asset at turn ASSEMBLY
        # — the capture runs in the background through the direction
        # conversation instead of starting cold at the design beat (the
        # direction beat lawfully ends in a bare reply, where NO tool absorb
        # seat runs — the 2026-10-17 f5743045 incident burned 151s of the
        # design budget on a cold capture wait). Committed in its own
        # transaction (the creation seat), so the query below already sees
        # the newborn; idempotent per capture_url, best-effort per URL.
        await prime_web_page_captures_from_text(
            UUID(str(project.id)), self.user_id, text
        )
        assets = list(
            (
                await db.execute(
                    select(Asset)
                    .where(
                        Asset.project_id == project.id,
                        # A captured page has no bytes by design (file_url
                        # stays NULL) yet IS attached material — the film
                        # family's whole input.
                        or_(
                            Asset.file_url.isnot(None),
                            Asset.type == AssetType.WEB_PAGE,
                        ),
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
        filename = first_file.display_name if first_file else None
        # Multi-asset block (ADR-078): with ≥2 files the router must SEE the
        # roster to judge the remix shape (which is the user's material, which
        # the reference) — the single-file filename/excerpt surface stays for
        # the common case; this lists every file in upload order.
        asset_lines: list[str] | None = None
        if len(assets) > 1:
            lines = []
            for a in assets:
                name = a.display_name or "(text)"
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
        # asset carrying text, capped — the ONE text seat (ADR-113) picks
        # the layer (transcript beats extracted_text).
        material_excerpt = next(
            (
                excerpt
                for a in assets
                if (excerpt := asset_text_content(a).strip())
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

            understanding_digest = asset_digest(assets)
            understanding_row = await find_reusable_understanding(
                db, project, understanding_digest
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
            # 服务员话术律 (2026-10-06 用户拍板): the pre-read speech is a
            # WAITER line only — you haven't seen the content, so no
            # proposals, no direction suggestions, no question ride it; the
            # plan talk comes after the read, never before. (The line lands
            # as its own checkpoint segment — tool_loop's iteration-0 seat.)
            material_pending_line = (
                f"Material status: {processing_count} uploaded file(s) are "
                "STILL PROCESSING — their content is not readable yet. If "
                "this turn's answer depends on their content, call "
                "get_understanding: the read waits until the content lands "
                "(it never returns while the material is still processing), "
                "so the answer can ground itself this turn. Before that call, "
                "say ONLY a short waiter line in the user's language — you "
                "have their file, you're going to look at it, the first look "
                "takes a few minutes. You haven't seen the content, so the "
                "line carries NO proposals, NO direction suggestions, NO "
                "question — the plan talk comes after the read, never before."
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
        # ADR-117 D1: the turn's confirmation prefs ride the assembled
        # context as a FACT line (the mode-conditional law stays in the
        # static system template — 一法一座, prefix-cache intact). The
        # server-side enforcement reads the SAME two prefs fresh at the
        # dock (resolve_confirmation_need), never this assembly.
        user_row = await db.get(User, self.user_id)
        self.confirmation = read_confirmation_prefs(
            user_row.settings if user_row is not None else None
        )
        # The docked decision package (iter-2 ⑦): when a plan-sourced dock is
        # on the table, its Content Plans render as the package block so a
        # change ask can name its plan_id (revise_plan's唯一指认面 — the LLM
        # never invents an id).
        plans_lines: list[str] | None = None
        if stored is not None and stored.plans:
            lines = []
            for p in stored.plans:
                outputs = ", ".join(
                    str(o.get("kind", "?"))
                    + (f" ({o['language']})" if o.get("language") else "")
                    for o in (p.get("outputs") or [])
                )
                lines.append(
                    f"- plan_id {p.get('plan_id')}: "
                    f"{p.get('title') or '(unnamed)'} — {outputs}"
                )
            plans_lines = lines or None
        self.infer_kwargs = dict(
            message=(
                f"{text}\n{self.suggestion_note}"
                if self.suggestion_note
                else text
            ),
            brief=brief_in,
            persona=persona,
            pending_question=pending_q,
            filename=filename,
            presented_plan=presented_plan,
            plans_lines=plans_lines,
            recent=recent_lines or None,
            # The transform-target rule's authoritative signal (同源语言护栏 —
            # the plan surface's only other language hint is the filename).
            file_language=(first_file.meta or {}).get("language") if first_file else None,
            material_excerpt=material_excerpt,
            understanding_lines=understanding_lines,
            # The footage's speaker form (deterministic, off asset.meta —
            # independent of the understanding row's readiness): the framing
            # direction's evidence seat, so a vertical ask on interview /
            # single-speaker footage never silently defaults to center crop.
            speaker_form_lines=speaker_form_lines(assets) or None,
            asset_lines=asset_lines,
            material_pending_line=material_pending_line,
            # The sender's surface (2026-09-25 canvas↔chat 联动): "canvas" =
            # the plan's draft graph lives beside the conversation — the
            # review invitation may name that home; None/"chat" = the
            # surface-neutral law stands.
            surface=request.surface,
            # ADR-117 D1 — the confirmation-settings fact (the system
            # template's mode-conditional close law reads it).
            confirmation=self.confirmation,
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

    async def _absorb(
        self,
        brief: Brief | None,
        material_text: str | None,
        material_urls: list[str] | None = None,
    ) -> Brief:
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

        # Declared-URL capture (网页资产化): the router judged the link
        # MATERIAL ("make a film of https://…"), so it becomes a WEB_PAGE
        # asset through the singular creation seat — committed in its own
        # transaction so the capture worker can claim it while this chat
        # turn stays open (the dock-seat storyboard waits for that capture;
        # a flush-only row would deadlock the wait). Idempotent per page:
        # an existing project asset with the same capture_url is reused,
        # never duplicated. CaptureBlocked propagates (the creation seat's
        # SSRF gate).
        if material_urls:
            created_ids = await create_web_page_assets_committed_from_urls(
                UUID(str(self.project.id)), self.user_id, material_urls
            )
            if created_ids:
                born = list(
                    (
                        await db.execute(
                            select(Asset)
                            .where(Asset.id.in_(created_ids))
                            .execution_options(populate_existing=True)
                        )
                    )
                    .scalars()
                    .all()
                )
                born_by_id = {str(a.id): a for a in born}
                for asset_id in created_ids:
                    asset = born_by_id.get(str(asset_id))
                    if asset is not None:
                        self.assets.append(asset)

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
                if any(
                    a.file_url or a.type == AssetType.WEB_PAGE for a in self.assets
                )
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
            return await run_perception_tool(
                self.db,
                self.project,
                name,
                params,
            )
        # 插话判定结算 (ADR-053 R2 — the plan-path seat, 2026-09-27 一问拍
        # 一体化): the disposition rides every terminal call's envelope, the
        # chat path's `_settle_by_disposition` mirror — judgment is the LLM's,
        # settlement is code's. "answer" settles the pending plain question
        # as freeform with the user's OWN WORDS (原话一视同仁: an answer, a
        # deferral like "你更推荐什么？", an option discussion all engage the
        # question); "skip" bails it; "none" leaves it (the reply gets the
        # reminder tail below). The slot absorb (_absorb) is the narrower
        # code fast path and composes — it sees pending_q=None after this.
        # Plan-path plain questions are never parked interrupts (prepare
        # filters workflow_run_id), so there is no wake branch here.
        disposition = (
            getattr(params, "pending_disposition", "none") if params is not None else "none"
        )
        await self._settle_pending_by_disposition(disposition)
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
        if name == "present_plan":
            assert isinstance(params, PresentPlanArgs)
            return await self._present_plan(params, prose)
        if name == "design_storyboard":
            assert isinstance(params, DesignStoryboardArgs)
            return await self._design_storyboard(params, prose)
        if name == "ask_user":
            assert isinstance(params, PlanAskArgs)
            return await self._ask_user(params, prose)
        if name == "start_run":
            assert isinstance(params, StartRunArgs)
            return await self._start_run(params, prose)
        if name == "answer":
            assert isinstance(params, PlanAnswerArgs)
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

    async def _settle_pending_by_disposition(self, disposition: str) -> None:
        """Settle the pending plain question by the accepted call's judgment
        (2026-09-27, the plan path's seat — the chat path's
        ``_settle_by_disposition`` mirror). A blank turn never settles (the
        judgable law — the chat path's ``pending_judgable`` guard's plan
        twin); the reminder tail keys off ``self.pending_q``, so a settled
        row also silences the tail."""
        pending = self.pending_q
        if pending is None or disposition == "none" or not self.text.strip():
            return
        pending.answer = AnswerPayload(
            kind="freeform" if disposition == "answer" else "bail",
            text=self.text if disposition == "answer" else None,
            answered_at=datetime.now(UTC),
        ).model_dump(mode="json")
        await self.db.flush()
        self.settled_pending = pending
        self.pending_q = None

    async def _stamp_presentation(self, message) -> None:
        """The presented-message association (2026-10-18 裁决 — LLM 唯一
        呈现): fires from ``finish`` when a design beat this turn is owed
        its presentation and a TERMINAL speech row actually persisted
        (the outcome row / the bare-reply floor). Degrade rows (cannot-do
        / exhaustion) never stamp — a board the user never saw stays
        honestly unpresented. Version-guarded by
        ``presentation_stamp_update`` (a newer draft owns its own
        presentation); the write rides the turn's one transaction, so a
        failed/cancelled turn never leaves a phantom "presented" mark."""
        pending = self._presentation_pending
        self._presentation_pending = None
        if pending is None or message is None:
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
            self.stored = PendingPlan.model_validate(updated)

    async def _design_storyboard(self, params: DesignStoryboardArgs, prose: str) -> str | ToolObservation:
        """design_storyboard → the film family's design beat (ADR-129 非终
        态): draft (or fingerprint-reuse) the storyboard, stamp the
        VERSIONED film state onto the PendingPlan (version / params /
        content digest / execution snapshot / review hold / draft token —
        the dock, start and worker seats only READ it), and hand the saved
        board's FULL fact sheet back to the loop (2026-10-18 裁决 — 工具
        产生真实分镜, LLM 负责唯一表达): the model's ONE next message is
        the presentation; ``finish`` stamps its provenance once that row
        persists (``_stamp_presentation``). NO plan docks, NO run starts,
        NO program markdown row."""
        db, project = self.db, self.project
        stored = self._current_pending()
        # Non-terminal checkpoint law: with an on_checkpoint channel, the
        # framing prose has already been emitted and is deliberately absent
        # from the execute speech. Empty prose here is legal, never a
        # "missing explanation" rejection.
        from app.tools.film.storyboard import (  # deferred: tool seam
            begin_film_draft,
            clear_film_draft_marker,
            film_design_state,
            prepare_dock_storyboard,
            read_committed_film_marker,
            resolve_film_revision_base,
        )

        # 修订基准 (ADR-129): 钉恒胜 — an explicit @output pin names THE
        # film whose board the revision re-enters, beating any live pending
        # draft (the user named the object; the current draft is not it).
        # An unrecoverable pinned target yields NO base (a fresh draft) —
        # never a silent swap to another film's board. Without a pin: the
        # live pending design wins; after a Start cleared pending_brief the
        # current board recovers from the latest film run's provenance
        # (read-only) so the revision continues its version line.
        mentioned_output = next(
            (m for m in (self.request.mentions or []) if m.type == "output"),
            None,
        )
        if mentioned_output is not None:
            design_base = await resolve_film_revision_base(
                db, project, output_id=UUID(str(mentioned_output.id))
            )
        elif stored is not None and stored.film_storyboard:
            design_base = stored
        else:
            design_base = await resolve_film_revision_base(db, project)

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

        # 并发护栏 BEGIN: the in-flight marker lands COMMITTED before the
        # long draft — Start fails closed while it stands, a concurrent
        # design's begin is refused (never queued), and the publish below
        # only lands if the committed marker still names THIS draft. No
        # turn-transaction fallback: a marker the Start gate cannot see is
        # worse than a refusal.
        draft_id = await begin_film_draft(
            db,
            project,
            base_version=(
                design_base.film_storyboard_version if design_base else None
            ),
            user_message_id=str(authorized_by) if authorized_by else None,
        )
        if draft_id is None:
            return (
                "another storyboard design (or a production start) holds "
                "this project right now — wait for it to settle, then call "
                "design_storyboard again; never draft over an in-flight "
                "design."
            )

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
            # fingerprint's params half), or it steers back here.
            design_params = {
                k: v
                for k, v in {
                    "focus": params.focus,
                    "language": params.language,
                    "voiceover": params.voiceover,
                    "music_mood": params.music_mood,
                    "aspect": params.aspect,
                }.items()
                if v is not None
            }
            tasks = [{"tool": "launch_film", "params": design_params}]
            # Birth-narrative freeze (present_plan's same law — stored.prompt
            # wins): the approval dock reads this same prompt back, so the
            # design beat's fingerprint IS the dock's.
            birth_prompt = stored.prompt if stored and stored.prompt else self.text
            film = await prepare_dock_storyboard(
                db,
                project,
                on_progress=self.on_phase,
                tasks=tasks,
                instruction=birth_prompt,
                fresh_instruction=params.specific_instruction or None,
                cached_storyboard=design_base.film_storyboard if design_base else None,
                cached_fingerprint=design_base.film_storyboard_fingerprint if design_base else None,
            )
        except BaseException:
            # 并发护栏 step 3: failure/timeout/cancel — capture failures
            # included — clears ONLY this draft's marker (committed side
            # channel; the turn holds no project lock on this path).
            await clear_film_draft_marker(db, project, draft_id=draft_id)
            raise
        assert film is not None  # the synthetic task always carries launch_film

        # 并发护栏 PUBLISH (step 2): publish only while the COMMITTED marker
        # still names THIS draft on ITS base version — a concurrent design's
        # begin (or a Start that consumed the pending plan) since our begin
        # discards this draft wholesale.
        live_marker = await read_committed_film_marker(UUID(str(project.id)))
        if not (
            isinstance(live_marker, dict)
            and live_marker.get("draft_id") == draft_id
            and live_marker.get("base_version")
            == (design_base.film_storyboard_version if design_base else None)
        ):
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
        pending = PendingPlan(
            prompt=birth_prompt,
            intent=stored.intent if stored else None,
            brief=stored.brief if stored else Brief(),
            reasons=stored.reasons if stored else [],
            persona_id=(
                self.request.persona_id
                or (stored.persona_id if stored else None)
            ),
            derived=stored.derived if stored else [],
            plans=stored.plans if stored else [],
            plan_task_map=stored.plan_task_map if stored else None,
            **version_state,
            **self._role_pins(),
        )
        project.pending_brief = pending.model_dump(mode="json")
        self.stored = pending
        # 呈现挂号 (2026-10-18 裁决): no program message publishes — the
        # model's ONE next message presents the board, and finish stamps
        # the association once that row persists (version-guarded).
        self._presentation_pending = {
            "version": version_state["film_storyboard_version"]
        }
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
        return ToolObservation(
            f"Storyboard version {version_state['film_storyboard_version']} "
            f"designed and saved ({draft_fact}; {hold_fact}; no plan docked, "
            "nothing started). Your next message is its ONLY presentation — "
            "no system message carries the board. Present it per the "
            "WEBSITE FILM CONVERSATION law: a short intro, the scene table "
            "built from THESE facts verbatim, then ONE direct question — "
            "whether to start making the film with THIS version (never an "
            "internal-step question like 'shall I put the plan up').\n"
            "SAVED BOARD (execution truth — the times ARE the render "
            "timeline, never recompute them):\n"
            + film.presentation
            + "\nLaw: with production intent already present and review "
            "hold off, present the board and continue to present_plan with "
            "these design params verbatim; with review hold on, present "
            "and wait for an explicit production request. The user's "
            "APPROVAL of the presented board docks the proposal with the "
            "same params and ONE honest setup line — it never re-designs, "
            "never re-prints the table. Global confirmation settings govern "
            "whether the docked plan starts. Board feedback re-enters "
            "through design_storyboard's specific_instruction — the user's "
            "change words only, never a restated direction; an explanation "
            "question gets an answer, never a redraft."
        )

    async def _present_plan(self, params: PresentPlanArgs, prose: str) -> str | None:
        """draft → the plan docks. Guardrails first (a rejection writes
        nothing): the empty-prose guard, the chain adjudication, then the
        出书门槛."""
        db, project = self.db, self.project
        stored = self._current_pending()
        merged_brief = await self._absorb(
            params.brief,
            params.material_text,
            getattr(params, "material_urls", None),
        )

        # 空散文护栏 (ask_user 座的同形对称): the plan card carries no title
        # — the echo IS its introduction (three duties), so a silent dock
        # leaves the user facing a canvas they cannot read. Reject into the
        # repair iteration instead of docking speech-less.
        if not prose.strip():
            return (
                "a plan never docks without its introduction speech — the "
                "card has no title of its own, your message IS the "
                "introduction. Speak what you saw, the plan in your own "
                "words, and what 'done' looks like as your message text, "
                "then call present_plan."
            )

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
        # ADR-117 §4: the confirmation need is computed ONCE here — the
        # echo's held clause (keyed on the stamped reason: the auto
        # regime's guardrail/unquotable trip carries the honest
        # correction) and the dock payload's stamp read the same object
        # (passed through below).
        need = await resolve_confirmation_need(db, self.user_id, task_estimate)

        # The late-turn guard: a concurrent Start committed while this refine
        # was in flight — docking now would raise a plan over an active
        # run (the zombie dock). Degrade to the active-run line.
        active_line = await _active_run_line(db, project, self.text)
        if active_line is not None:
            assistant_message = await _create_message(
                db,
                self.conversation_id,
                "assistant",
                active_line,
            )
            self.outcome = (assistant_message, None, self.settled_pending, [])
            return None

        # The birth prompt freezes at the first dock (stored.prompt wins on every
        # later write) — the brief is the accumulated state now, the prompt is
        # only the plan's birth narrative (Start's instruction fallback).
        birth_prompt = stored.prompt if stored and stored.prompt else self.text

        # 分镜节拍守卫 (ADR-129 — 分镜不是开工, 分镜也不是方案 dock): every
        # film dock reads the CURRENT persisted version through ONE resolver.
        # It first restores the presented version's canonical launch_film
        # params (fresh wording is not drift), then validates the fingerprint,
        # version, content digest, execution digest and draft token. A miss
        # steers back to design_storyboard; a dock NEVER redrafts, and a
        # non-empty specific_instruction remains plan feedback only.
        from app.tools.film.storyboard import (  # deferred: tool seam
            resolve_film_dock_state,
        )

        film_resolution = resolve_film_dock_state(
            stored, params.tasks, birth_prompt
        )
        if isinstance(film_resolution, str):
            return film_resolution
        film_state = film_resolution.state

        # 估价尾行 (ADR-111 §2 — dock 卡面退役后总估价的新家): the dock echo
        # carries the code-composed estimate whisper (BILLING §2.1 披露义务 —
        # capture 前可见). Appended AFTER the prose so the tail lands with
        # the envelope's settled content (the reminder tail's seat); the
        # per-task half lives on the canvas's draft nodes. intent.answer and
        # the question row share the same tailed echo, so the flow's
        # content-match (echo 实体化) keeps holding. 展示一座 (ADR-129): the
        # storyboard markdown's presentation seat is the design beat's own
        # message — a dock echo NEVER re-embeds it.
        echo = echo + _estimate_tail(self.text, task_estimate, reason=need.reason)
        # Caption mode (ADR-099 §8 default absorption): what the call didn't
        # set rides the shared funnel — the user's own words (literal
        # bilingual keyword) > the previous dock's value > source_only when a
        # distinct second language makes the choice real. The stamped value
        # rides the intent end-to-end (dock → pending_brief → Start) as a
        # stated default — the user revises it with one sentence, never a
        # blocking question.
        if caption_mode is None:
            caption_mode = await _derive_chat_caption_mode(
                db, project, params.tasks, self.text
            )
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
            **film_state,
            **self._role_pins(),
        ).model_dump(mode="json")
        self._fire_mention_warm()
        bailed_run_ids = await sync_plan_question(
            db, self.user_id, project, intent, birth_prompt, reasons=reasons,
            derived=derived,
            brief=merged_brief,
            echo=echo,
            estimate=task_estimate,
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
        question = await latest_pending_question(db, self.conversation_id)
        assert question is not None  # sync_plan_question just docked it
        self.outcome = (question, None, self.settled_pending, bailed_run_ids)
        # ADR-117 §2 auto 开工道: when the dock owes no confirm beat, the
        # SAME start machine fires on presentation (None = the dock waits
        # for the user's beat — ask modes / guardrail / structural hold).
        auto = await _auto_start_docked_plan(
            db,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            project=project,
        )
        if auto is not None:
            answered_q, auto_run_id = auto
            self.outcome = (question, auto_run_id, answered_q, bailed_run_ids)
        return None

    # ---- the exploration seats (iter-2 ③/⑤ — ADR-088 旅程四 chain) -----------

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
        """plans → the decision package docks (ADR-089 §4 R16, iter-2 ③).

        双门 (R14): the pre-flight compile + the door birth live in
        ``exploration_compile.compile_plans_package`` (iter-3 S2 — ONE
        compile law shared with the chat path): an uncompilable package
        rejects back into the loop with zero writes (an uncompilable plan
        never reaches the canvas or the dock), then the door births the
        rows (its validation re-runs as the authority). The dock below
        carries the three faces: the plans reading layer + the compiled
        task evidence + the credits quote (费用语义五面)."""
        db, project = self.db, self.project
        stored = self._current_pending()
        merged_brief = await self._absorb(None, None)

        persona_id = UUID(str(self.persona.id)) if self.persona is not None else None
        package = await compile_plans_package(
            db, project, params.plans, persona_id=persona_id
        )
        if isinstance(package, str):
            return package
        born = package.plans
        compiled = package.tasks
        await self._emit_milestone("chat.explore.plansReady", len(born))

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
        task_estimate = await _safe_task_estimate(db, project, compiled)
        # 估价尾行 (ADR-111 §2 — present_plan dock 的同座同律): the package
        # dock's echo carries the code-composed estimate whisper too — the
        # disclosure duty (BILLING §2.1) holds on every dock seat, and the
        # tailed echo rides intent.answer so the re-dock replay stays
        # single-tailed. The held clause (ADR-117 §4) keys on the stamped
        # reason — the auto regime's guardrail/unquotable trip only.
        need = await resolve_confirmation_need(db, self.user_id, task_estimate)
        # The birth prompt freezes at the first dock (stored.prompt wins on
        # every later write) — the same preserve law as present_plan.
        birth_prompt = stored.prompt if stored and stored.prompt else self.text
        # 分镜先行 + dock 只读当前版本 (present_plan 的同座同律): a
        # film-carrying package docks only against the CURRENT presented
        # version. The shared resolver restores its canonical params first,
        # then validates fingerprint/version/digests/token; this seat never
        # drafts and never re-embeds the design beat's markdown.
        from app.tools.film.storyboard import (  # deferred: tool seam
            resolve_film_dock_state,
        )

        film_resolution = resolve_film_dock_state(stored, compiled, birth_prompt)
        if isinstance(film_resolution, str):
            return film_resolution
        film_state = film_resolution.state
        prose = prose + _estimate_tail(self.text, task_estimate, reason=need.reason)
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

        # The late-turn guard (same zombie-dock law as present_plan): a
        # concurrent Start committed while this turn was in flight — docking
        # now would raise a plan over an active run.
        active_line = await _active_run_line(db, project, self.text)
        if active_line is not None:
            assistant_message = await _create_message(
                db,
                self.conversation_id,
                "assistant",
                active_line,
            )
            self.outcome = (assistant_message, None, self.settled_pending, [])
            return None

        # 决策包阅读层 (R16): the Content Plans ride BOTH the pending-brief
        # row (the restore path reads it) and the dock payload (the live
        # envelope) — one stamp, two seats. The R20 router substrate
        # (plan_task_map, re-keyed onto the born rows) rides with them.
        package_plans = decision_package_plans(born)
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=intent,
            brief=merged_brief,
            reasons=reasons,
            persona_id=persona_id,
            derived=derived,
            plans=package_plans,
            plan_task_map=package.plan_task_map,
            **film_state,
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
        question = await latest_pending_question(db, self.conversation_id)
        assert question is not None  # sync_plan_question just docked it
        self.outcome = (question, None, self.settled_pending, bailed_run_ids)
        # ADR-117 §2 auto 开工道 (the same seat as _present_plan): a package
        # dock that owes no confirm beat starts the work on presentation.
        auto = await _auto_start_docked_plan(
            db,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            project=project,
        )
        if auto is not None:
            answered_q, auto_run_id = auto
            self.outcome = (question, auto_run_id, answered_q, bailed_run_ids)
        return None

    async def _revise_plan(self, params: RevisePlanArgs, prose: str) -> str | None:
        """revise_plan → the door revises the row in place → the WHOLE
        journey re-compiles → the decision package re-docks (iter-2 ⑦,
        contract §4.8). 恒重确认 (R15 最保守读法): every plan-level revision
        re-docks for confirmation — zero autonomy. The revised row lands
        even when the recompile then rejects (draft with issues re-stamped
        = the canvas's honest surface); the rejection rides back as the
        loop echo and the LLM repairs the PLAN, never the chain. The dock
        tail lives in ``_redock_journey_package`` (iter-3 S4 — ONE seat,
        shared with revise_selects)."""
        db, project = self.db, self.project
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

        # Recompile the journey's WHOLE package (a revise targets one plan;
        # the decision package re-docks with every plan of the journey) —
        # the shared recompile seat (iter-3 S2).
        package = await recompile_journey_package(
            db, project, UUID(str(revised.journey_id))
        )
        if isinstance(package, str):
            return package
        # 真实修改只走 design_storyboard (ADR-129): the user's revision words
        # are PLAN feedback — they re-dock the package; a storyboard change
        # re-enters through design_storyboard (which revises the CURRENT
        # board), never through a dock-time redraft.
        steering = await self._redock_journey_package(package, prose)
        return steering

    async def _redock_journey_package(
        self, package, prose: str
    ) -> str | None:
        """The decision package's re-dock tail (决策包可编辑律 — the SAME
        confirmation seat, never a new confirmation ritual: sync_plan_question
        supersedes the still-open task_book row in place). ONE seat for every
        package-level revision (iter-3 S4): revise_plan's whole-journey
        recompile and revise_selects' docked re-quote / post-run mini package
        all land here. The package's name survives from the stored intent
        (the LLM named the work; code never renames the package — a plan's
        own title is the revision's renaming seat); caption_mode re-derives
        from the current rows, inheriting the stored answer when unnamed
        (同一律 — read as a DICT off the spec JSONB: the iter-2 attribute
        access on it was a latent crash for quotes+caption_mode rows).
        Returns None when docked; a STRING is the film guardrail's steering
        observation (present_plan 的同座同律 — the board was never presented
        in this exact form, nothing docked)."""
        db, project = self.db, self.project
        stored = self._current_pending()
        merged_brief = await self._absorb(None, None)
        plans = package.plans
        compiled = package.tasks
        await self._emit_milestone("chat.explore.plansReady", len(plans))

        stored_intent = stored.intent if stored else None
        caption_mode = next(
            (
                o.get("caption_mode")
                for row in plans
                for o in (row.spec or {}).get("outputs") or []
                if o.get("kind") == "quotes" and o.get("caption_mode")
            ),
            None,
        ) or (stored_intent.caption_mode if stored_intent else None)
        task_estimate = await _safe_task_estimate(db, project, compiled)
        # 估价尾行 (ADR-111 §2 — present_plan dock 的同座同律): the revision
        # re-dock's echo carries the code-composed estimate whisper too;
        # the held clause (ADR-117 §4) keys on the stamped reason — the
        # auto regime's guardrail/unquotable trip only.
        need = await resolve_confirmation_need(db, self.user_id, task_estimate)
        birth_prompt = stored.prompt if stored and stored.prompt else self.text
        # 分镜节拍守卫 + dock 只读当前版本 (present_plan 的同座同律 — the
        # revision re-dock rides the SAME seat): the shared resolver first
        # restores the presented version's canonical params, then validates
        # fingerprint/version/digests/token. No fresh_instruction ever rides
        # here — a dock NEVER redrafts.
        from app.tools.film.storyboard import (  # deferred: tool seam
            resolve_film_dock_state,
        )

        film_resolution = resolve_film_dock_state(stored, compiled, birth_prompt)
        if isinstance(film_resolution, str):
            return film_resolution
        film_state = film_resolution.state
        prose = (
            prose
            # 展示一座 (ADR-129): the storyboard markdown's presentation seat
            # is the design beat's own message — a re-dock echo NEVER
            # re-embeds it.
            + _estimate_tail(self.text, task_estimate, reason=need.reason)
        )
        intent = InferredIntent(
            action="draft",
            tasks=compiled,
            answer=prose,
            caption_mode=caption_mode,
            name=(stored_intent.name if stored_intent else None),
        )
        reasons = await _compute_plan_reasons(db, project, intent)
        from app.pipeline.orchestrator import derive_plan_preview

        try:
            derived = await derive_plan_preview(db, project, compiled)
        except (ToolRejected, ValueError):
            derived = []

        # The late-turn guard (same zombie-dock law as present_plan).
        active_line = await _active_run_line(db, project, self.text)
        if active_line is not None:
            assistant_message = await _create_message(
                db,
                self.conversation_id,
                "assistant",
                active_line,
            )
            self.outcome = (assistant_message, None, self.settled_pending, [])
            return None

        persona_id = (
            self.request.persona_id
            or (stored.persona_id if stored else None)
            or (UUID(str(self.persona.id)) if self.persona is not None else None)
        )
        package_plans = decision_package_plans(plans)
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=intent,
            brief=merged_brief,
            reasons=reasons,
            persona_id=persona_id,
            derived=derived,
            plans=package_plans,
            plan_task_map=package.plan_task_map,
            **film_state,
            **self._role_pins(),
        ).model_dump(mode="json")
        self._fire_mention_warm()
        # The old dock's supersede rides the EXISTING mechanism (contract
        # §4.8): sync_plan_question retires the still-open task_book row.
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
        question = await latest_pending_question(db, self.conversation_id)
        assert question is not None  # sync_plan_question just docked it
        self.outcome = (question, None, self.settled_pending, bailed_run_ids)
        # ADR-117 §2 auto 开工道 (the same seat as _present_plan): a
        # revision's re-dock owes no confirm beat in auto modes either —
        # the revised plan starts on presentation (guardrail unchanged).
        auto = await _auto_start_docked_plan(
            db,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            project=project,
        )
        if auto is not None:
            answered_q, auto_run_id = auto
            self.outcome = (question, auto_run_id, answered_q, bailed_run_ids)
        return None

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
            self.outcome = (assistant_message, None, self.settled_pending, [])
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
                for p in await read_journey_plans(db, project.id, journey_id)
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
        return await self._redock_journey_package(package, prose)

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

    async def _ask_user(self, params: PlanAskArgs, prose: str) -> str | None:
        """ask → the ONE question docks through the ask_user machinery.
        Guards first: the pending-question law and the asked-roll bound
        the loop."""
        stored = self._current_pending()
        merged_brief = await self._absorb(
            params.brief,
            params.material_text,
            getattr(params, "material_urls", None),
        )
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
        from app.tools.film.storyboard import film_carry_state  # deferred

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
            plans=stored.plans if stored else [],
            plan_task_map=stored.plan_task_map if stored else None,
            # The versioned storyboard survives an interjection ask verbatim
            # (review hold included — only a proposal dock releases it).
            **film_carry_state(stored),
            **self._role_pins(),
        ).model_dump(mode="json")
        self._fire_mention_warm()
        # ask 三分解剖 (2026-09-08): the row's content carries the framing
        # prose (解剖 ① — it streams as the turn's echo and replays in the
        # flow); the bare question rides the payload (解剖 ② — dock title,
        # QA archive, reminder tail). Prose-less asks fall back to content =
        # the bare question, the legacy shape every consumer still reads.
        # 推荐标记 (2026-09-27 一问拍一体化): the shared validation lives in
        # resolve_recommended_id — the asset_role code-built options
        # invalidate any LLM-written id the same way.
        recommended_id = resolve_recommended_id(params.recommended_id, params.options)
        ask = QuestionProposal(
            prose=prose or "",
            question=params.question,
            options=params.options,
            allow_freeform=params.allow_freeform,
            recommended_id=recommended_id,
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
                recommended_id=recommended_id,
                slot=params.slot,
                default_path=params.default_path,
            ),
            intent=intent.model_dump(mode="json"),
        )
        self.outcome = (assistant_message, None, self.settled_pending, bailed_run_ids)
        return None

    async def _start_run(self, params: StartRunArgs, prose: str) -> str | None:
        """start → the docked plan is answered kind=start (G-1 path: the
        run comes from the only birthplace, answer_question — which commits;
        zero bypass). The turn's speech (the work-start line, ADR-093 §2)
        lands as a plain assistant row first — created before the run
        births, so its stamp orders before the task list by construction,
        and answer_question's commit lands it atomically with the run."""
        db = self.db
        stored = self._current_pending()
        pending_question = await latest_pending_question(db, self.conversation_id)
        if (
            is_pending_plan(pending_question)
            and stored is not None
            and stored.intent is not None
        ):
            assert pending_question is not None  # is_pending_plan guarantees the row
            # 旧 Start 失效 (ADR-129): the docked task_book presents a film
            # draft version — a newer design beat minted a new draft token,
            # so this Start would confirm a board the user is no longer
            # reviewing. Steer back to the current draft (re-dock, then
            # start), never a silent old-version run.
            if stored.film_storyboard:
                from app.tools.film.storyboard import (  # deferred: tool seam
                    film_draft_inflight_live,
                    film_start_draft_match,
                )

                if film_draft_inflight_live(stored.film_draft_inflight):
                    return (
                        "a storyboard redesign is in flight right now — the "
                        "docked confirmation is void until the new version "
                        "lands. Wait for the design to settle, re-dock the "
                        "plan with present_plan, then start."
                    )
                question_payload = pending_question.question or {}
                effective_tasks = (
                    list(self.request.prior_intent.tasks)
                    if self.request.prior_intent is not None
                    else list(stored.intent.tasks)
                )
                if not film_start_draft_match(
                    stored,
                    effective_tasks,
                    stored.prompt,
                    question_payload.get("film_draft_token"),
                    question_payload.get("film_storyboard_version"),
                ):
                    return (
                        "the docked plan no longer matches the current "
                        "storyboard draft — a newer version was designed or "
                        "the film params moved. Re-dock the plan with "
                        "present_plan so the user confirms the CURRENT "
                        "board, then start."
                    )
            # 起始句 = 普通 assistant 行 (ADR-093 §2): the model's own words
            # persist or nothing does — an empty prose stays an honest
            # absence (a template fill-in is prohibited speech), keeping
            # the envelope's assistant_message on the answered plan row.
            start_message = None
            if prose.strip():
                start_message = await _create_message(
                    db,
                    self.conversation_id,
                    "assistant",
                    prose.strip(),
                )
            answered, _follow_up = await answer_question(
                db, self.user_id, UUID(str(pending_question.id)),
                # The review panel's edited plan rides along (typed Start
                # parity): dropping prior_intent here would execute the
                # stored chain and silently discard the user's panel edits.
                StartAnswerRequest(
                    kind="start",
                    intent=self.request.prior_intent,
                ),
                # ④ snapshot channel (N-57): the confirmation arrived as a
                # chat reply (the start_run tool), not the dock pill.
                confirmed_via="chat_reply",
            )
            # answer_question commits — the run, the answer and the cleared
            # pending brief land in one transaction.
            self.outcome = (
                start_message or answered,
                UUID(str(answered.workflow_run_id)),
                answered,
                [],
            )
            return None
        if stored is not None and stored.intent is not None:
            # Nothing startable right now. Never overwrite a stored plan
            # with a start-call misfire: re-dock the stored plan unchanged.
            # Unless a run started concurrently — then the plan is moot and
            # re-docking would raise a plan over an active run.
            active_line = await _active_run_line(db, self.project, self.text)
            if active_line is not None:
                assistant_message = await _create_message(
                    db,
                    self.conversation_id,
                    "assistant",
                    active_line,
                )
                self.outcome = (assistant_message, None, self.settled_pending, [])
                return None
            bailed_run_ids = await sync_plan_question(
                db, self.user_id, self.project, stored.intent, stored.prompt,
                reasons=stored.reasons, derived=stored.derived,
                brief=stored.brief,
                echo=stored.intent.answer,
                estimate=await _safe_task_estimate(db, self.project, stored.intent.tasks),
                # The re-dock replays the stored echo verbatim; the film
                # version's token + number ride so the Start gate compares
                # against the CURRENT draft (ADR-129).
                film_draft_token=stored.film_draft_token,
                film_storyboard_version=stored.film_storyboard_version,
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
        await self._absorb(
            params.brief,
            params.material_text,
            getattr(params, "material_urls", None),
        )
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
            self.db,
            self.conversation_id,
            "assistant",
            content,
        )
        self.outcome = (assistant_message, None, self.settled_pending, [])
        return None

    # ---- the outcome mapping -------------------------------------------------

    async def finish(self, result) -> PlanTurnOutcome:
        """LoopResult → the caller's 4-tuple. An accepted execution stashed
        its outcome already; the bare reply and the exhaustion degrade land
        here (an honest degrade, never a fabricated success)."""
        if self.outcome is not None:
            # 呈现关联 (2026-10-18 裁决): a design beat this turn owes its
            # presentation — the TERMINAL row IS the presentation message;
            # stamp its provenance now that the row persisted.
            await self._stamp_presentation(self.outcome[0])
            return self.outcome
        # The degrade paths land their own message — resolve any still-armed
        # queue FIRST so its frames precede the envelope: a clean bare reply
        # flushes (the queued prose IS the reply), a rejection-marked queue
        # drops (every queued word was rejected speech).
        await self._resolve_deferred()
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
                self.db,
                self.conversation_id,
                "assistant",
                content,
            )
            # The bare reply IS the presentation when the model closed a
            # design beat without a further call — same association seat.
            await self._stamp_presentation(assistant_message)
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
            stored = self._current_pending()
            merged_brief = self.merged_brief or Brief()
            merged_brief.asked = [*merged_brief.asked, "topic"]
            from app.tools.film.storyboard import film_carry_state  # deferred

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
                plans=stored.plans if stored else [],
                plan_task_map=stored.plan_task_map if stored else None,
                **film_carry_state(stored),
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
            self.db,
            self.conversation_id,
            "assistant",
            _cannot_do_text(self.text),
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
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
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
    one-shot path. ``on_row_append`` is the generic persisted-row channel
    (currently unused by this path — the design beat's program-markdown
    publication retired with the 2026-10-18 裁决)."""
    turn = PlanTurn(db, user_id, conversation, project, request, on_phase=on_phase, on_activity=on_activity, on_candidates=on_candidates, on_row_append=on_row_append)
    await turn.assemble(recent)
    # 言语提交协议武装 (speech-commit protocol, ADR-099 §7): on the SSE path
    # every turn arms the terminal buffer — iteration 0 is the only
    # streaming iteration, so its prose / preview frames are exactly the
    # speech a terminal rejection would retract. The one-shot path streams
    # nothing and needs no buffer. The buffer holds delta + tool_ready ONLY
    # (三通道分家): on_tool_call stays LIVE — it feeds the Activity
    # projector's name_known (the read/repair work evidence + G1's
    # cancelled-frame rejection forensics ride their own undeferred
    # channel) and the phase-clear is liveness chrome, never adjudication-
    # dependent speech. The rejection seat is the wrapped on_loop_event:
    # any ToolRejected retracts the stale queue at once (RETRY re-arms by
    # construction) and marks the turn frame-silent; the checkpoint channel
    # flushes the queue FIRST (prose spoken before a read lands before the
    # read EXECUTES — the emission seat sits pre-execute, ADR-104 发射时点
    # 修订, so a waiting read never holds the waiter line hostage), then
    # streams live — the buffer stays armed through it.
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
        base_on_checkpoint = _checkpoint_callback(db, turn.conversation_id, on_checkpoint)

        async def on_checkpoint_after_flush(text: str) -> None:
            if deferred.armed:
                await deferred.flush()
            await base_on_checkpoint(text)

        checkpoint_hook = on_checkpoint_after_flush
    else:
        checkpoint_hook = _checkpoint_callback(db, turn.conversation_id, on_checkpoint)
    result = await intent_router.call_loop(
        turn.execute,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_tool_call=on_tool_call,
        on_tool_ready=on_tool_ready,
        on_checkpoint=checkpoint_hook,
        on_loop_event=on_loop_event,
        **turn.infer_kwargs,
    )
    return await turn.finish(result)


__all__ = ["run_plan_turn", "PlanTurn", "PlanTurnOutcome"]
